# jmapq

`jmapq` parses decompiled Java sources with `jast` and emits normalized JSON
that can be filtered with `jq`.

`jmapq` exists for a practical problem: when Java code is decompiled, it is
still readable, but no longer easy to analyze at scale. If you need to answer
questions like "what REST endpoints exist?", "which classes expose `@Path`
routes?", or "what media types are consumed/produced?", manual inspection
quickly becomes slow, error-prone, and incomplete.

This tool turns decompiled Java source into a normalized, queryable JSON map.
Instead of grepping raw files and stitching context by hand, you get a
structured model of units, classes, methods, annotations, and parameters that
can be filtered with `jq`. It is especially useful for API inventory and
migration work, security reviews, integration discovery, and documenting legacy
systems where original source or docs are missing.

In short: it converts noisy decompiled code into reliable data, so endpoint
discovery becomes a repeatable query, not a manual investigation.

## Generate JSON

```bash
python jmapq.py "tests/fixtures/**/*.java"
```

You can pass direct file paths, directories, or recursive glob patterns.

- Default map file is `map.json` (same as `-o map.json`).
- When paths are provided, a fresh payload is parsed and saved to map file.
- When paths are omitted, the tool reads existing `map.json` and runs jq
  queries against it.

See [schema](schema.md) for more details.

Once the tree map is generated, you can safely ditch `jmapq` and proceed with standard `jq` though
it has predefined useful queries.

## Run jq from CLI

`jmapq.py` can run `jq` internally via subprocess.

- Built-in queries: `--query annotations|classes|path-classes|path-methods|endpoints|media-types`
- Custom jq query: `--jq '<jq-expression>'`
- Plain table output (endpoints only): `--query endpoints --plain`

Examples:

```bash
python jmapq.py "tests/fixtures/**/*.java" --query annotations
python jmapq.py "tests/fixtures/**/*.java" --query endpoints
python jmapq.py "tests/fixtures/**/*.java" --query endpoints --plain
python jmapq.py "tests/fixtures/**/*.java" --query media-types
python jmapq.py "tests/fixtures/**/*.java" --jq '.units[].classes[].qualified_name'
python jmapq.py --query annotations
```

See [examples](examples.md) for more details.

## jq queries

### 1) List all available annotations across all scanned files (sorted, unique)

Built-in:

```bash
python jmapq.py "tests/fixtures/**/*.java" --query annotations
```

```bash
jq -r '
  [
    .units[].classes[] as $c
    | $c.annotations[]?.name,
      $c.methods[]?.annotations[]?.name,
      $c.methods[]?.parameters[]?.annotations[]?.name,
      $c.methods[]?.return_type?.annotations[]?.name
  ]
  | sort
  | unique[]
' map.json
```

### 2) List all class names

Built-in:

```bash
python jmapq.py "tests/fixtures/**/*.java" --query classes
```

```bash
jq -r '.units[].classes[].qualified_name' map.json
```

### 3) List all class names with `@Path` and not private

Built-in:

```bash
python jmapq.py "tests/fixtures/**/*.java" --query path-classes
```

```bash
jq -r '
  .units[].classes[]
  | select(any(.annotations[]?; .name == "Path"))
  | select((.modifiers | map(.name) | index("Private")) | not)
  | .qualified_name
' map.json
```

### 4) List all methods with `@Path` and not private

Built-in:

```bash
python jmapq.py "tests/fixtures/**/*.java" --query path-methods
```

```bash
jq -r '
  .units[].classes[] as $c
  | $c.methods[]
  | select(any(.annotations[]?; .name == "Path"))
  | select((.modifiers | map(.name) | index("Private")) | not)
  | "\($c.qualified_name)#\(.name)"
' map.json
```

### 5) Build endpoint objects with HTTP verb + class/method `@Path`

Built-in:

```bash
python jmapq.py "tests/fixtures/**/*.java" --query endpoints
python jmapq.py "tests/fixtures/**/*.java" --query endpoints --plain
```

This query builds records like:

```json
{"method":"GET","base":"/rest/v1.0/","path":"foo/bar","uri_path":"/rest/v1.0/foo/bar","parameters":{...}}
```

It also normalizes URI parts:

- prepends `/` when base path does not start with it
- ensures base ends with `/`
- strips leading/trailing `/` from method path
- joins into `uri_path`

```bash
jq '
  def ann($anns; $name): first($anns[]? | select(.name == $name));
  def ann_str($anns; $name):
    (ann($anns; $name).elements // null) as $e
    | if ($e|type) == "array" and ($e|length) > 0 and ($e[0]|type) == "string" then $e[0] else "" end;
  def http_method($anns):
    first($anns[]?.name | select(test("^(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)$")));
  def leading_slash: if startswith("/") then . else "/" + . end;
  def trim_slashes: gsub("^/+|/+$"; "");

  [
    .units[].classes[] as $c
    | $c.methods[] as $m
    | (http_method($m.annotations) // "") as $verb
    | select($verb != "")
    | (ann_str($c.annotations; "Path")) as $base_raw
    | (ann_str($m.annotations; "Path")) as $method_raw
    | ($base_raw | if . == "" then "/" else (leading_slash | if endswith("/") then . else . + "/" end) end) as $base
    | ($method_raw | trim_slashes) as $path
    | {
        method: $verb,
        base: $base,
        path: $path,
        uri_path: (if $path == "" then $base else ($base + $path) end),
        parameters: (reduce $m.parameters[]? as $p ({}; . + {
          ($p.name): {
            type: ($p.type.name // null),
            annotations: [$p.annotations[]?.name]
          }
        }))
      }
  ]
' map.json
```

### 6) List sorted unique media types from `@Consumes` and `@Produces`

Built-in:

```bash
python jmapq.py "tests/fixtures/**/*.java" --query media-types
```

Example output:

```json
{"Consumes":["application/xml","application/json"],"Produces":["application/json"]}
```

```bash
jq '
  ([.units[].classes[].annotations[]?, .units[].classes[].methods[]?.annotations[]?]) as $anns
  | def media($name):
      [
        $anns[]
        | select(.name == $name)
        | (.elements // [])[]?
        | if type == "array" then .[] else . end
        | select(type == "string")
      ]
      | sort
      | unique;
    {
      Consumes: media("Consumes"),
      Produces: media("Produces")
    }
' map.json
```
