import json
import shutil
import tempfile
import unittest
from pathlib import Path

import main


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"


class MainExtractionTests(unittest.TestCase):
    def test_sample_has_qualified_name(self) -> None:
        unit = main.extract_unit(FIXTURES / "foo.java")
        self.assertEqual(unit.package, "com.foo.atlassian.jira.common.rest")
        self.assertEqual(len(unit.classes), 1)
        self.assertEqual(
            unit.classes[0].qualified_name,
            "com.foo.atlassian.jira.common.rest.DashboardItemResource",
        )

    def test_generics_and_throws(self) -> None:
        unit = main.extract_unit(FIXTURES / "generics_throws.java")
        klass = unit.classes[0]
        method = klass.methods[0]

        self.assertEqual(method.name, "findNames")
        self.assertIsNotNone(method.return_type)
        assert method.return_type is not None
        self.assertEqual(method.return_type.name, "java.util.List")
        self.assertEqual(len(method.return_type.type_args), 1)
        self.assertEqual(method.return_type.type_args[0].name, "String")
        self.assertEqual(method.throws, ["IOException", "IllegalStateException"])

    def test_nested_annotation_normalization(self) -> None:
        unit = main.extract_unit(FIXTURES / "nested_annotations.java")
        method = unit.classes[0].methods[0]
        anns = {ann.name: ann for ann in method.annotations}

        outer = anns["Outer"]
        self.assertIsInstance(outer.elements, list)
        assert isinstance(outer.elements, list)
        self.assertIsInstance(outer.elements[0], dict)
        self.assertEqual(outer.elements[0]["name"], "Inner")

        arr = anns["ArrayAnn"]
        self.assertIsInstance(arr.elements, list)
        assert isinstance(arr.elements, list)
        self.assertIsInstance(arr.elements[0], list)
        self.assertEqual(arr.elements[0][0]["name"], "Inner")
        self.assertIsNotNone(method.return_type)
        assert method.return_type is not None
        self.assertEqual(method.return_type.name, "void")

    def test_unknown_node_normalized_as_object(self) -> None:
        unknown = main._normalize_node_value(object())
        self.assertIsInstance(unknown, dict)
        assert isinstance(unknown, dict)
        self.assertEqual(unknown["_kind"], "UnknownNode")
        self.assertIn("node_type", unknown)
        self.assertIn("repr", unknown)

    def test_payload_is_json_serializable(self) -> None:
        payload = main._build_payload([str(FIXTURES), str(FIXTURES / "foo.java")])
        encoded = json.dumps(payload)
        self.assertTrue(encoded.startswith("{"))
        self.assertEqual(payload["errors"], [])
        self.assertGreaterEqual(len(payload["units"]), 3)

    def test_collect_java_files_with_glob(self) -> None:
        pattern = str(FIXTURES / "**" / "*.java")
        files = main._collect_java_files([pattern])
        names = sorted(path.name for path in files)
        self.assertEqual(
            names,
            ["foo.java", "generics_throws.java", "nested_annotations.java"],
        )

    def test_builtin_query_resolution(self) -> None:
        query = main._resolve_query("classes", None)
        self.assertIsNotNone(query)
        assert query is not None
        self.assertIn("qualified_name", query[0])
        self.assertTrue(query[1])

    def test_conflicting_query_options_raise(self) -> None:
        with self.assertRaises(ValueError):
            main._resolve_query("classes", ".units")

    def test_custom_jq_query_via_subprocess(self) -> None:
        if shutil.which("jq") is None:
            self.skipTest("jq not available")
        payload = {"units": [{"classes": [{"qualified_name": "a.b.C"}]}], "errors": []}
        payload_json = json.dumps(payload)
        result = main._run_jq(".units[].classes[].qualified_name", payload_json, True)
        self.assertEqual(result.strip(), "a.b.C")

    def test_media_types_builtin_query(self) -> None:
        if shutil.which("jq") is None:
            self.skipTest("jq not available")
        payload = main._build_payload([str(FIXTURES / "foo.java")])
        payload_json = json.dumps(payload)
        query = main.BUILTIN_QUERIES["media-types"][0]
        result = main._run_jq(query, payload_json, False)
        parsed = json.loads(result)
        self.assertEqual(parsed["Consumes"], ["application/json"])
        self.assertEqual(parsed["Produces"], ["application/json"])

    def test_endpoint_params_text(self) -> None:
        params = {
            "dashboardId": {"annotations": ["PathParam"]},
            "request": {"annotations": ["Context"]},
        }
        text = main._endpoint_params_text(params)
        self.assertEqual(text, "PathParam: dashboardId @ Context: request")

    def test_render_endpoints_plain_table(self) -> None:
        endpoints = [
            {
                "method": "GET",
                "uri_path": "/dashboard/{dashboardId}/items/{dashboardItemId}/toggle-editor",
                "parameters": {
                    "dashboardId": {"annotations": ["PathParam"]},
                    "request": {"annotations": ["Context"]},
                },
            }
        ]
        text = main._render_endpoints_plain(json.dumps(endpoints))
        self.assertIn("Method", text)
        self.assertIn("Endpoint", text)
        self.assertIn("Parameters", text)
        self.assertIn("GET", text)
        self.assertIn("PathParam: dashboardId @ Context: request", text)

    def test_parser_default_output_is_map_json(self) -> None:
        parser = main._build_arg_parser()
        args = parser.parse_args([])
        self.assertEqual(args.output, "map.json")
        self.assertEqual(args.paths, [])

    def test_get_payload_json_reads_existing_map_when_no_paths(self) -> None:
        payload = {"units": [{"path": "x.java"}], "errors": []}
        with tempfile.TemporaryDirectory() as tmp_dir:
            map_path = Path(tmp_dir) / "map.json"
            map_path.write_text(json.dumps(payload), encoding=main.ENCODING)
            loaded = main._get_payload_json([], map_path)
        loaded_obj = json.loads(loaded)
        self.assertEqual(loaded_obj["units"][0]["path"], "x.java")

    def test_get_payload_json_writes_map_when_paths_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            map_path = Path(tmp_dir) / "map.json"
            payload_json = main._get_payload_json(
                [str(FIXTURES / "foo.java")], map_path
            )
            self.assertTrue(map_path.exists())
            payload = json.loads(payload_json)
            self.assertEqual(payload["errors"], [])
            self.assertTrue(
                payload["units"][0]["path"].endswith("tests/fixtures/foo.java")
            )


if __name__ == "__main__":
    unittest.main()
