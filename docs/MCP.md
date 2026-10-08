# Use the toolkit through MCP

The optional stdio MCP server lets compatible AI clients discover and invoke every installed tool. It uses the official Python MCP SDK and delegates validation and calculation to the existing registry. Package version 0.7.0 adds `screening.evaluate` at tool version 1 using base dependencies. `structure.analyze_cif` execution requires the separate `structures` extra. Existing tool versions and input contracts remain unchanged.

## Installation

From a cloned repository:

```sh
uv sync --locked --extra mcp
uv run --no-sync matkit-mcp
```

With pip:

```sh
python -m pip install -e '.[mcp]'
matkit-mcp
```

The executable waits for MCP messages on standard input and sends protocol messages on standard output. Start it from an MCP client; manually typing ordinary CLI requests into the process is not the MCP protocol. `python -m materials_agent_toolkit.mcp_server` starts the same server. If the extra is absent, the server command exits with code 2 and explains the installation step on stderr, while the base library and `matkit` CLI continue working.

## Client configuration

Clients that use an `mcpServers` configuration can launch a repository installation through uv. Replace the directory with the absolute path of your checkout:

```json
{
  "mcpServers": {
    "materials-agent-toolkit": {
      "command": "uv",
      "args": [
        "--directory", "/absolute/path/materials-agent-toolkit",
        "run", "--locked", "--extra", "mcp", "matkit-mcp"
      ]
    }
  }
}
```

Configuration formats vary between clients. The server uses local stdio and the client manages the subprocess. No web listener or account authentication is needed for these local scientific calculations.

## Discovery and invocation

`tools/list` advertises the same ten names as `matkit list`, including input schemas, full response-envelope output schemas, tool versions, scientific assumptions and references. All tools are declared read-only and have no external side effects. MCP annotations are descriptive metadata; the actual tools enforce the supported scientific domains.

For example, call the native MCP tool `mechanics.isotropic_moduli` with arguments:

```json
{"young_modulus": 210, "poisson_ratio": 0.3, "stress_unit": "GPa"}
```

These are the tool's input fields directly. The `{"tool": ..., "input": ...}` request wrapper is used by the JSON CLI, not by MCP's tool call arguments.

The MCP result contains:

- `structuredContent`: the common toolkit envelope with `status`, `tool`, `tool_version`, `result`, `warnings`, `provenance` and `error`.
- `content`: a text block containing the identical envelope encoded as JSON.
- `isError`: true for invalid requests, unknown tools, domain failures or internal failures; false for successful calculations.

Input and domain errors preserve the registry's structured error codes. Correcting the input and calling again does not require restarting the server. Protocol-level malformed MCP messages are handled by the SDK and may produce protocol errors rather than a scientific-tool envelope.

Result values, validated input hashes, scientific references and software versions match library invocation in the same environment. Each execution has its own timestamp. Callers should discover installed versions before invoking a tool; unsupported future tool versions are handled through registry contracts rather than extra MCP arguments that would conflict with scientific schemas.

## Resources

| URI | Content |
| --- | --- |
| `materials://catalog` | JSON with `catalog_version`, full `tools` descriptors and `response_schema` |
| `materials://schemas/response` | JSON schema for the common response envelope |

Catalog version `1` describes this resource format. Each descriptor includes its own tool version and the raw scientific output schema, while the native MCP tool output schema describes the containing response envelope.

The `materials://catalog` resource uses the same canonical UTF-8 JSON as `matkit catalog` and the committed [catalog artifact](../catalog/tool-catalog.json). Its version-1 three-field object is unchanged. [Standalone export and validation](CATALOG.md) use the base installation and do not require starting an MCP server.

## Python client example and validation

The bundled [client example](../examples/mcp_client.py) uses `ClientSession` and the SDK's stdio transport:

```sh
uv run --extra mcp python examples/mcp_client.py
```

Development checks include real subprocess initialization, tool discovery, analytical scientific cases, schema validation, error propagation, resource reads and continued operation after a failed calculation:

```sh
uv sync --locked --extra dev --extra mcp --extra structures
uv run --no-sync pytest
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
```

To execute CIF calls, also install `.[mcp,structures]` with pip or add `--extra structures` to the uv installation and client launch command. Without ASE, CIF calls return `MISSING_DEPENDENCY` with installation guidance; all ten tools remain discoverable.

The base installation has no dependency on MCP or ASE. The server exposes the currently registered deterministic calculators; external simulation jobs and additional scientific modules remain tracked in the backlog.
