# Reproducible catalog export

Catalog format version `1` is a snapshot of the installed scientific contracts. It is available through the Python API, JSON CLI, committed artifacts and the MCP `materials://catalog` resource. All four use one generator.

## Format and discovery

The catalog contains exactly three top-level fields:

| Field | Content |
| --- | --- |
| `catalog_version` | Required string `"1"`; independent of package and scientific tool versions |
| `tools` | Scientific descriptors sorted by unique tool name |
| `response_schema` | Full JSON schema for the common `ToolResponse` envelope |

Each tool descriptor retains its name/version, description, raw input/output schemas, units and assumptions, scientific references, dependency names, side effects, network-access declaration and cost description. Individual scientific outputs validate against the descriptor's `output_schema`; their containing responses validate against `response_schema`. Embedded schemas are self-contained, including their own `$defs` when needed. Evaluate each embedded schema at its own root so local references resolve correctly.

The outer [catalog schema](../catalog/tool-catalog.schema.json) uses JSON Schema Draft 2020-12 and forbids extra catalog/descriptor fields. Embedded schemas are JSON objects in that outer contract; CI separately validates every embedded schema and the example inputs. The catalog describes tool contracts and does not execute examples or calculate results during generation.

Batch format discovery remains available through `matkit batch-schema` and `describe_batch()`. The batch descriptor is a separate contract; the version-1 tool catalog retains its existing three-field format.

## CLI and Python

```sh
uv sync --locked --extra dev
uv run --no-sync matkit catalog > tool-catalog.json
uv run --no-sync matkit catalog-schema > tool-catalog.schema.json
```

Both commands write canonical UTF-8 JSON to stdout with sorted object keys, two-space indentation and exactly one final line feed. The real CLI writes UTF-8 bytes directly, so a legacy stdout text encoding cannot change the artifact. Ordinary CLI usage errors follow the existing argparse conventions.

```python
from materials_agent_toolkit.catalog import (
    catalog_json,
    catalog_schema,
    catalog_schema_json,
    get_catalog,
)

catalog = get_catalog()
assert catalog["catalog_version"] == "1"
schema = catalog_schema()
catalog_bytes = catalog_json().encode("utf-8")
schema_bytes = catalog_schema_json().encode("utf-8")
```

Each API call returns fresh data. Mutating an exported object does not change later exports or the live tool registry. Non-finite or non-JSON-serializable metadata is rejected during export; it is not silently replaced with null. Generation uses base dependencies only, with no network requests or scientific execution. Installing the optional MCP SDK does not change the artifact.

## Regeneration and reproducibility

The repository tracks [tool-catalog.json](../catalog/tool-catalog.json) and [tool-catalog.schema.json](../catalog/tool-catalog.schema.json). Regenerate them after changing tool descriptors, request/response schemas, catalog models or package version:

```sh
uv sync --locked --extra dev
uv run --no-sync python scripts/export_catalog.py
uv run --no-sync python scripts/export_catalog.py --check
```

The script resolves artifact paths relative to its repository location. Normal mode writes both files as UTF-8 bytes. Check mode compares exact bytes without writing and exits nonzero for missing or stale files. CI runs check mode on Python 3.11–3.13 with MCP and on the base installation.

Reproducibility requires the same committed source and locked dependency versions. Different package versions or schema-library versions can change the catalog; regenerate rather than treating an old snapshot as the installed contract. Runtime timestamps and the host Python version are excluded from exports. Actual calculation responses still record their Python version at execution time. Package version remains a stable default in the response schema and changes deliberately with package releases.

Tests validate raw single-request examples against the request wrapper and the matching exported tool input schema. The mixed batch example validates against the batch envelope and individual wrapper contracts; its `missing.tool` entry is an intentional unknown-tool failure, so it has no scientific input schema in the catalog. Existing scientific and interface tests validate results and response envelopes.
