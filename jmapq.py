#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations
from typing import cast

import argparse
import concurrent.futures
import contextlib
import glob
import io
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import jast
import jast._jast as jnodes
from rich.console import Console
from rich.table import Table

ENCODING = "utf-8"
JSONScalar = str | int | float | bool | None
JSONValue = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]

QUERY_ALL_ANNOTATIONS = """
[
  .units[].classes[] as $c
  | $c.annotations[]?.name,
    $c.methods[]?.annotations[]?.name,
    $c.methods[]?.parameters[]?.annotations[]?.name,
    $c.methods[]?.return_type?.annotations[]?.name
]
| sort
| unique[]
""".strip()

QUERY_CLASS_NAMES = ".units[].classes[].qualified_name"

QUERY_PATH_CLASSES = """
.units[].classes[]
| select(any(.annotations[]?; .name == \"Path\"))
| select((.modifiers | map(.name) | index(\"Private\")) | not)
| .qualified_name
""".strip()

QUERY_PATH_METHODS = """
.units[].classes[] as $c
| $c.methods[]
| select(any(.annotations[]?; .name == \"Path\"))
| select((.modifiers | map(.name) | index(\"Private\")) | not)
| \"\\($c.qualified_name)#\\(.name)\"
""".strip()

QUERY_ENDPOINTS = """
def ann($anns; $name): first($anns[]? | select(.name == $name));
def ann_str($anns; $name):
  (ann($anns; $name).elements // null) as $e
  | if ($e|type) == \"array\" and ($e|length) > 0 and ($e[0]|type) == \"string\" then $e[0] else \"\" end;
def http_method($anns):
  first($anns[]?.name | select(test(\"^(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)$\")));
def leading_slash: if startswith(\"/\") then . else \"/\" + . end;
def trim_slashes: gsub(\"^/+|/+$\"; \"\");

[
  .units[].classes[] as $c
  | $c.methods[] as $m
  | (http_method($m.annotations) // \"\") as $verb
  | select($verb != \"\")
  | (ann_str($c.annotations; \"Path\")) as $base_raw
  | (ann_str($m.annotations; \"Path\")) as $method_raw
  | ($base_raw | if . == \"\" then \"/\" else (leading_slash | if endswith(\"/\") then . else . + \"/\" end) end) as $base
  | ($method_raw | trim_slashes) as $path
  | {
      method: $verb,
      base: $base,
      path: $path,
      uri_path: (if $path == \"\" then $base else ($base + $path) end),
      parameters: (reduce $m.parameters[]? as $p ({}; . + {
        ($p.name): {
          type: ($p.type.name // null),
          annotations: [$p.annotations[]?.name]
        }
      }))
    }
]
""".strip()

QUERY_MEDIA_TYPES = """
([.units[].classes[].annotations[]?, .units[].classes[].methods[]?.annotations[]?]) as $anns
| def media($name):
    [
      $anns[]
      | select(.name == $name)
      | (.elements // [])[]?
      | if type == \"array\" then .[] else . end
      | select(type == \"string\")
    ]
    | sort
    | unique;
  {
    Consumes: media(\"Consumes\"),
    Produces: media(\"Produces\")
  }
""".strip()


BUILTIN_QUERIES: dict[str, tuple[str, bool]] = {
    "annotations": (QUERY_ALL_ANNOTATIONS, True),
    "classes": (QUERY_CLASS_NAMES, True),
    "path-classes": (QUERY_PATH_CLASSES, True),
    "path-methods": (QUERY_PATH_METHODS, True),
    "endpoints": (QUERY_ENDPOINTS, False),
    "media-types": (QUERY_MEDIA_TYPES, False),
}


@dataclass(slots=True)
class SourceSpan:
    lineno: int | None
    end_lineno: int | None
    col_offset: int | None
    end_col_offset: int | None

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "lineno": self.lineno,
            "end_lineno": self.end_lineno,
            "col_offset": self.col_offset,
            "end_col_offset": self.end_col_offset,
        }


@dataclass(slots=True)
class ModifierInfo:
    name: str

    def to_dict(self) -> dict[str, JSONValue]:
        return {"name": self.name}


@dataclass(slots=True)
class AnnotationInfo:
    name: str
    elements: JSONValue
    span: SourceSpan | None

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "name": self.name,
            "elements": self.elements,
            "span": None if self.span is None else self.span.to_dict(),
        }


@dataclass(slots=True)
class TypeRef:
    name: str
    type_args: list[TypeRef]
    annotations: list[AnnotationInfo]

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "name": self.name,
            "type_args": [type_arg.to_dict() for type_arg in self.type_args],
            "annotations": [annotation.to_dict() for annotation in self.annotations],
        }


@dataclass(slots=True)
class ParameterInfo:
    name: str
    type_ref: TypeRef | None
    modifiers: list[ModifierInfo]
    annotations: list[AnnotationInfo]
    span: SourceSpan | None

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "name": self.name,
            "type": None if self.type_ref is None else self.type_ref.to_dict(),
            "modifiers": [modifier.to_dict() for modifier in self.modifiers],
            "annotations": [annotation.to_dict() for annotation in self.annotations],
            "span": None if self.span is None else self.span.to_dict(),
        }


@dataclass(slots=True)
class MethodInfo:
    name: str
    return_type: TypeRef | None
    parameters: list[ParameterInfo]
    throws: list[str]
    modifiers: list[ModifierInfo]
    annotations: list[AnnotationInfo]
    span: SourceSpan | None

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "name": self.name,
            "return_type": None
            if self.return_type is None
            else self.return_type.to_dict(),
            "parameters": [parameter.to_dict() for parameter in self.parameters],
            "throws": list(self.throws),
            "modifiers": [modifier.to_dict() for modifier in self.modifiers],
            "annotations": [annotation.to_dict() for annotation in self.annotations],
            "span": None if self.span is None else self.span.to_dict(),
        }


@dataclass(slots=True)
class ClassInfo:
    name: str
    qualified_name: str
    modifiers: list[ModifierInfo]
    annotations: list[AnnotationInfo]
    methods: list[MethodInfo]
    span: SourceSpan | None

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "name": self.name,
            "qualified_name": self.qualified_name,
            "modifiers": [modifier.to_dict() for modifier in self.modifiers],
            "annotations": [annotation.to_dict() for annotation in self.annotations],
            "methods": [method.to_dict() for method in self.methods],
            "span": None if self.span is None else self.span.to_dict(),
        }


@dataclass(slots=True)
class UnitInfo:
    path: str
    package: str | None
    imports: list[str]
    classes: list[ClassInfo]

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "path": self.path,
            "package": self.package,
            "imports": list(self.imports),
            "classes": [class_info.to_dict() for class_info in self.classes],
        }


def _node_type_name(node: object) -> str:
    return type(node).__name__


def _span_from_node(node: object) -> SourceSpan | None:
    lineno = getattr(node, "lineno", None)
    end_lineno = getattr(node, "end_lineno", None)
    col_offset = getattr(node, "col_offset", None)
    end_col_offset = getattr(node, "end_col_offset", None)
    if (
        lineno is None
        and end_lineno is None
        and col_offset is None
        and end_col_offset is None
    ):
        return None
    return SourceSpan(
        lineno=lineno,
        end_lineno=end_lineno,
        col_offset=col_offset,
        end_col_offset=end_col_offset,
    )


def _name_from_node(node: object | None) -> str:
    if node is None:
        return ""
    if isinstance(node, str):
        return node
    identifiers = getattr(node, "identifiers", None)
    if isinstance(identifiers, list) and all(
        isinstance(item, str) for item in identifiers
    ):
        return ".".join(identifiers)
    node_id = getattr(node, "id", None)
    if node_id is not None:
        return _name_from_node(node_id)
    value = getattr(node, "value", None)
    if isinstance(value, str):
        return value
    return str(node)


def _modifier_name(modifier: object) -> str:
    return _node_type_name(modifier)


def _normalize_unknown(node: object) -> dict[str, JSONValue]:
    payload: dict[str, JSONValue] = {
        "_kind": "UnknownNode",
        "node_type": _node_type_name(node),
        "repr": repr(node),
    }
    span = _span_from_node(node)
    if span is not None:
        payload["span"] = span.to_dict()
    return payload


def _normalize_node_value(node: object | None) -> JSONValue:
    if node is None:
        return None
    if isinstance(node, (str, int, float, bool)):
        return node
    if isinstance(node, list):
        return [_normalize_node_value(item) for item in node]
    if isinstance(node, tuple):
        return [_normalize_node_value(item) for item in node]
    if isinstance(node, dict):
        return {str(key): _normalize_node_value(value) for key, value in node.items()}

    if isinstance(node, jnodes.Constant):
        return _normalize_node_value(getattr(node, "value", None))
    if isinstance(node, jnodes.elementarrayinit):
        values = getattr(node, "values", [])
        if isinstance(values, list):
            return [_normalize_node_value(item) for item in values]
        return _normalize_unknown(node)
    if isinstance(node, jnodes.Annotation):
        return _extract_annotation(node).to_dict()
    if isinstance(node, jnodes.Member):
        return {
            "_kind": "Member",
            "value": _normalize_node_value(getattr(node, "value", None)),
            "member": _normalize_node_value(getattr(node, "member", None)),
        }
    if isinstance(node, jnodes.BinOp):
        return {
            "_kind": "BinOp",
            "op": _node_type_name(getattr(node, "op", object())),
            "left": _normalize_node_value(getattr(node, "left", None)),
            "right": _normalize_node_value(getattr(node, "right", None)),
        }

    if hasattr(node, "identifiers") or hasattr(node, "id"):
        return _name_from_node(node)

    return _normalize_unknown(node)


def _extract_annotation(annotation_node: jnodes.Annotation) -> AnnotationInfo:
    raw_elements = getattr(annotation_node, "elements", None)
    normalized_elements = _normalize_node_value(raw_elements)
    return AnnotationInfo(
        name=_name_from_node(getattr(annotation_node, "name", None)),
        elements=normalized_elements,
        span=_span_from_node(annotation_node),
    )


def _extract_type(type_node: object | None) -> TypeRef | None:
    if type_node is None:
        return None
    if isinstance(type_node, jnodes.Void):
        return TypeRef(name="void", type_args=[], annotations=[])

    if hasattr(type_node, "coits"):
        coits = getattr(type_node, "coits", [])
        if isinstance(coits, list) and coits:
            type_name = ".".join(_name_from_node(coit.id) for coit in coits)
            raw_type_args = getattr(coits[-1], "type_args", None)
        else:
            type_name = _name_from_node(type_node)
            raw_type_args = None
    else:
        type_name = _name_from_node(getattr(type_node, "id", type_node))
        raw_type_args = getattr(type_node, "type_args", None)

    if raw_type_args is not None and hasattr(raw_type_args, "types"):
        raw_type_args = getattr(raw_type_args, "types")
    type_args: list[TypeRef] = []
    if isinstance(raw_type_args, list):
        type_args = [
            extracted
            for item in raw_type_args
            if (extracted := _extract_type(item)) is not None
        ]

    raw_annotations = getattr(type_node, "annotations", [])
    annotations = [
        _extract_annotation(annotation)
        for annotation in raw_annotations
        if isinstance(annotation, jnodes.Annotation)
    ]

    return TypeRef(name=type_name, type_args=type_args, annotations=annotations)


def _extract_parameter(parameter_node: object) -> ParameterInfo:
    raw_identifier = getattr(parameter_node, "id", None)
    parameter_name = _name_from_node(getattr(raw_identifier, "id", raw_identifier))

    raw_modifiers = getattr(parameter_node, "modifiers", [])
    annotations = [
        _extract_annotation(modifier)
        for modifier in raw_modifiers
        if isinstance(modifier, jnodes.Annotation)
    ]
    modifier_infos = [
        ModifierInfo(name=_modifier_name(modifier))
        for modifier in raw_modifiers
        if not isinstance(modifier, jnodes.Annotation)
    ]

    return ParameterInfo(
        name=parameter_name,
        type_ref=_extract_type(getattr(parameter_node, "type", None)),
        modifiers=modifier_infos,
        annotations=annotations,
        span=_span_from_node(parameter_node),
    )


def _extract_method(method_node: jnodes.Method) -> MethodInfo:
    raw_modifiers = getattr(method_node, "modifiers", [])
    annotations = [
        _extract_annotation(modifier)
        for modifier in raw_modifiers
        if isinstance(modifier, jnodes.Annotation)
    ]
    modifier_infos = [
        ModifierInfo(name=_modifier_name(modifier))
        for modifier in raw_modifiers
        if not isinstance(modifier, jnodes.Annotation)
    ]

    params_container = getattr(method_node, "parameters", None)
    raw_parameters = (
        getattr(params_container, "parameters", [])
        if params_container is not None
        else []
    )
    parameters = [_extract_parameter(parameter) for parameter in raw_parameters]

    raw_throws = getattr(method_node, "throws", [])
    throws = [_name_from_node(item) for item in raw_throws]

    return MethodInfo(
        name=_name_from_node(getattr(method_node, "id", None)),
        return_type=_extract_type(getattr(method_node, "return_type", None)),
        parameters=parameters,
        throws=throws,
        modifiers=modifier_infos,
        annotations=annotations,
        span=_span_from_node(method_node),
    )


def _extract_class(class_node: jnodes.Class, package_name: str | None) -> ClassInfo:
    class_name = _name_from_node(getattr(class_node, "id", None))
    qualified_name = f"{package_name}.{class_name}" if package_name else class_name

    raw_modifiers = getattr(class_node, "modifiers", [])
    annotations = [
        _extract_annotation(modifier)
        for modifier in raw_modifiers
        if isinstance(modifier, jnodes.Annotation)
    ]
    modifier_infos = [
        ModifierInfo(name=_modifier_name(modifier))
        for modifier in raw_modifiers
        if not isinstance(modifier, jnodes.Annotation)
    ]

    methods = [
        _extract_method(item)
        for item in getattr(class_node, "body", [])
        if isinstance(item, jnodes.Method)
    ]

    return ClassInfo(
        name=class_name,
        qualified_name=qualified_name,
        modifiers=modifier_infos,
        annotations=annotations,
        methods=methods,
        span=_span_from_node(class_node),
    )


def extract_unit(path: Path) -> UnitInfo:
    source = path.read_text(encoding=ENCODING)
    with contextlib.redirect_stderr(io.StringIO()):
        tree = jast.parse(source)
    if not isinstance(tree, jnodes.CompilationUnit):
        raise TypeError(f"Unexpected root node: {_node_type_name(tree)}")

    package_name: str | None = None
    if getattr(tree, "package", None) is not None:
        package_name = _name_from_node(getattr(tree.package, "name", None))

    imports = [
        _name_from_node(getattr(import_node, "name", None))
        for import_node in tree.imports
    ]

    classes = [
        _extract_class(item, package_name)
        for item in tree.body
        if isinstance(item, jnodes.Class)
    ]

    return UnitInfo(
        path=str(path),
        package=package_name,
        imports=imports,
        classes=classes,
    )


def _collect_java_files(paths: list[str]) -> list[Path]:
    candidates: set[Path] = set()

    def add_path(path: Path) -> None:
        if path.is_file() and path.suffix == ".java":
            candidates.add(path)
            return
        if path.is_dir():
            for entry in path.rglob("*.java"):
                if entry.is_file():
                    candidates.add(entry)

    for raw_path in paths:
        has_glob_magic = glob.has_magic(raw_path)
        if has_glob_magic:
            matches = glob.glob(raw_path, recursive=True)
            for matched in matches:
                add_path(Path(matched))
            continue
        add_path(Path(raw_path))

    return sorted(candidates)


def _build_payload(paths: list[str]) -> dict[str, JSONValue]:
    units: list[dict[str, JSONValue]] = []
    errors: list[dict[str, JSONValue]] = []
    java_files = _collect_java_files(paths)

    def extract_one(
        java_file: Path,
    ) -> tuple[
        dict[str, JSONValue] | None,
        dict[str, JSONValue] | None,
    ]:
        try:
            unit_info = extract_unit(java_file)
        except Exception as exc:
            return (
                None,
                {
                    "path": str(java_file),
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                },
            )
        return unit_info.to_dict(), None

    max_workers = max(1, os.cpu_count() or 1)
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        for unit_payload, error_payload in executor.map(extract_one, java_files):
            if unit_payload is not None:
                units.append(unit_payload)
            if error_payload is not None:
                errors.append(error_payload)

    return cast(dict[str, JSONValue], {"units": units, "errors": errors})


def _resolve_query(
    query_name: str | None, custom_query: str | None
) -> tuple[str, bool] | None:
    if query_name and custom_query:
        raise ValueError("Use either --query or --jq, not both.")
    if custom_query:
        return custom_query, False
    if query_name:
        return BUILTIN_QUERIES[query_name]
    return None


def _run_jq(query: str, payload_json: str, raw_output: bool) -> str:
    if shutil.which("jq") is None:
        raise RuntimeError("jq binary is required but was not found in PATH")

    command = ["jq"]
    if raw_output:
        command.append("-r")
    command.append(query)

    process = subprocess.run(
        command,
        input=payload_json,
        text=True,
        capture_output=True,
        check=False,
    )
    if process.returncode != 0:
        stderr = process.stderr.strip() or "Unknown jq error"
        raise RuntimeError(f"jq failed: {stderr}")
    return process.stdout


def _get_payload_json(paths: list[str], output_path: Path) -> str:
    if paths:
        payload = _build_payload(paths)
        payload_json = json.dumps(payload, indent=4, ensure_ascii=False)
        output_path.write_text(payload_json, encoding=ENCODING)
        return payload_json

    if not output_path.exists():
        raise RuntimeError(
            f"Map file not found: {output_path}. Pass paths to generate it first."
        )
    return output_path.read_text(encoding=ENCODING)


def _endpoint_params_text(parameters: object) -> str:
    if not isinstance(parameters, dict):
        return ""

    parts: list[str] = []
    for param_name, meta in parameters.items():
        annotation_name = "Param"
        if isinstance(meta, dict):
            raw_annotations = meta.get("annotations")
            if isinstance(raw_annotations, list):
                names = [
                    item for item in raw_annotations if isinstance(item, str) and item
                ]
                if names:
                    annotation_name = names[0]
        parts.append(f"{annotation_name}: {param_name}")
    return " @ ".join(parts)


def _render_endpoints_plain(endpoints_json: str) -> str:
    try:
        parsed = json.loads(endpoints_json)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Expected JSON output for endpoints query") from exc

    if not isinstance(parsed, list):
        raise RuntimeError("Endpoints query must return a JSON array")

    console = Console(width=200)
    table = Table(show_header=True, header_style="bold")
    table.add_column("Method", no_wrap=True)
    table.add_column("Endpoint", no_wrap=True)
    table.add_column("Parameters", no_wrap=True)

    for item in parsed:
        if not isinstance(item, dict):
            continue
        method = str(item.get("method", ""))
        uri_path = str(item.get("uri_path", ""))
        params = _endpoint_params_text(item.get("parameters"))
        table.add_row(method, uri_path, params)

    with console.capture() as capture:
        console.print(table)
    return capture.get()


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=Path(sys.argv[0]).name,
        description="Collect normalized Java structure from decompiled sources.",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        help="Java file(s), directories, or glob patterns.",
    )
    parser.add_argument(
        "--query",
        choices=sorted(BUILTIN_QUERIES.keys()),
        help="Run built-in jq query on generated payload.",
    )
    parser.add_argument(
        "--jq", help="Run custom jq query on generated payload.", metavar="QUERY"
    )
    parser.add_argument(
        "--plain",
        action="store_true",
        help="Render --query endpoints as plain table output.",
    )
    parser.add_argument(
        "--output",
        "-o",
        default="map.json",
        help="Path to persisted payload JSON (default: map.json).",
    )
    return parser


def main() -> None:
    parser = _build_arg_parser()
    args = parser.parse_args()

    output_path = Path(args.output)

    try:
        payload_json = _get_payload_json(args.paths, output_path)
    except RuntimeError as exc:
        parser.error(str(exc))

    output = payload_json

    if args.plain and args.query != "endpoints":
        parser.error("--plain can only be used with --query endpoints")

    query_resolution = _resolve_query(args.query, args.jq)
    if query_resolution is not None:
        query, raw_output = query_resolution
        output = _run_jq(query, payload_json, raw_output)
        if args.plain:
            output = _render_endpoints_plain(output)

    print(output, end="")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Aborted", file=sys.stderr)
