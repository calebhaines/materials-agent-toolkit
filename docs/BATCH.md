# Batch execution

Batch format version `1` executes 1–100 independent scientific requests through the Python registry or JSON CLI. The eight scientific tool contracts and their versions are unchanged. Each item uses the same request wrapper as a single CLI invocation.

## Request and discovery

```json
{
  "batch_version": "1",
  "requests": [
    {"tool": "composition.analyze", "input": {"formula": "H2O"}},
    {"tool": "composition.from_fractions", "input": {"fractions": {"Ni": 0.5, "Ti": 0.5}, "basis": "atomic"}}
  ]
}
```

`batch_version` defaults to `"1"` and rejects unsupported versions. The outer object accepts only `batch_version` and `requests`. The request list must contain 1–100 items. Empty batches, oversized batches, extra envelope fields and wrong outer types return `INVALID_BATCH` before any calculation runs.

Discover the version, bound, execution mode and JSON schemas:

```sh
uv run matkit batch-schema
```

The descriptor includes `batch_version`, `max_batch_size`, `execution`, `request_schema`, `response_schema` and `item_request_schema`. Its envelope schema deliberately leaves item types unrestricted: malformed items must produce their own errors rather than invalidate every sibling. `item_request_schema` documents the expected single-request wrapper. Scientific input/output schemas remain available through `matkit list` and `matkit describe TOOL`.

The Python equivalents are `describe_batch()`, `BatchRequest.model_json_schema()` and `BatchResponse.model_json_schema()` in `materials_agent_toolkit.registry`.

## Ordering, isolation and response

Items run sequentially in input order, with no deduplication, parallel workers, shared scientific result state or result cache. The `responses` array has exactly one ordinary `ToolResponse` for every item of a valid batch, at the same index as its request. A malformed request, unknown tool, unsupported tool version, invalid scientific input or domain failure affects that item. Later items still run. Unexpected item exceptions are redacted as `INTERNAL_ERROR` and processing continues; process interrupts are not swallowed.

Each successful item preserves the single-call result, warnings, scientific references, installed dependency versions and hash of validated inputs. Execution timestamps may differ. The batch's own `provenance` records its execution environment and creation time; its `input_sha256` is null. It does not hash raw items, which may contain invalid values. Scientific units and assumptions belong to each tool's descriptor.

| Batch `status` | Meaning for a valid envelope | CLI exit code |
| --- | --- | --- |
| `ok` | Every item succeeded | 0 |
| `partial` | Some items succeeded and some failed | 2 |
| `error` | Every item failed | 2 |

`summary` contains `total`, `succeeded` and `failed`. For a valid envelope, `total` equals the response count and the two outcome counts sum to that total. Top-level `error` is null, including when every item failed; inspect each response's error instead.

A rejected envelope has status `error`, top-level error code `INVALID_BATCH`, an empty `responses` list and zero summary counts. CLI decoding errors use this same response format. The JSON decoder rejects duplicate object keys and nonstandard `NaN`/`Infinity` constants before execution. An invalid envelope never returns a partial scientific result.

## CLI and Python examples

```sh
uv run matkit batch < examples/batch/mixed.json
uv run matkit batch --request '{"requests":[{"tool":"composition.analyze","input":{"formula":"H2O"}}]}'
```

The bundled mixed example returns successful NiTi and water calculations surrounding an `UNKNOWN_TOOL` item. Its batch status is `partial`, its summary is `{"total":3,"succeeded":2,"failed":1}`, and its process exit code is 2. Calculation stdout contains one complete JSON response; argparse usage errors use stderr as for the other CLI commands.

```python
from materials_agent_toolkit.registry import run_batch

response = run_batch(
    {
        "requests": [
            {"tool": "composition.analyze", "input": {"formula": "H2O"}},
            None,
            {
                "tool": "mechanics.isotropic_moduli",
                "input": {"young_modulus": 210, "poisson_ratio": 0.3},
            },
        ]
    }
)
assert response.status == "partial"
assert response.responses[1].error.code == "INVALID_REQUEST"
assert response.responses[2].status == "ok"
```

This interface batches local deterministic calculations; it is not a simulation job scheduler, a cross-item dependency graph or a transaction. MCP continues exposing the individual scientific tools. Larger workloads can be split into independently tracked batches of at most 100 requests; preserve each response's index and tool/version/provenance when collecting results.
