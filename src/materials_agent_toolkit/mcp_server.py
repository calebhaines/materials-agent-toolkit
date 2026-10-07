"""Optional MCP stdio adapter for the existing scientific tool registry.

Install ``materials-agent-toolkit[mcp]`` to use :func:`build_server` or the
``matkit-mcp`` command. Importing this module does not require the MCP SDK.
"""

from __future__ import annotations

import asyncio
import json
import sys
from typing import TYPE_CHECKING, Any

from materials_agent_toolkit import __version__, registry
from materials_agent_toolkit.catalog import catalog_json

if TYPE_CHECKING:
    from mcp.server import Server

CATALOG_URI = "materials://catalog"
RESPONSE_SCHEMA_URI = "materials://schemas/response"


class _MissingMCPDependencyError(ImportError):
    """The optional MCP SDK is unavailable."""


def _description(descriptor: dict[str, Any]) -> str:
    assumptions = "\n".join(f"- {value}" for value in descriptor["assumptions"])
    references = "\n".join(f"- {value}" for value in descriptor["references"])
    return (
        f"{descriptor['description']}\n\n"
        f"Tool version: {descriptor['version']}\n\n"
        f"Assumptions:\n{assumptions}\n\n"
        f"References:\n{references}"
    )


def build_server() -> Server:
    """Build the official MCP server without opening a transport.

    Tool inputs and execution errors are validated by the registry, preserving
    the same strict contracts and response envelope as the library and CLI.
    Raises ``ImportError`` with installation guidance when MCP is unavailable.
    """
    try:
        import mcp.types as types
        from mcp.server import Server
        from mcp.server.lowlevel.helper_types import ReadResourceContents
    except ModuleNotFoundError as exc:
        if exc.name != "mcp" and not (exc.name or "").startswith("mcp."):
            raise
        raise _MissingMCPDependencyError(
            "MCP support requires the optional dependency. "
            "Install it with: python -m pip install 'materials-agent-toolkit[mcp]'"
        ) from exc

    server = Server(
        "materials-agent-toolkit",
        version=__version__,
        instructions=(
            "Discover tool schemas and scientific assumptions before calling tools. "
            "Each tool returns the common ToolResponse envelope, including provenance "
            "and structured errors. Inputs are raw tool arguments."
        ),
    )
    response_schema = registry.ToolResponse.model_json_schema()

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name=descriptor["name"],
                description=_description(descriptor),
                inputSchema=descriptor["input_schema"],
                outputSchema=response_schema,
                annotations=types.ToolAnnotations(
                    readOnlyHint=True,
                    destructiveHint=False,
                    idempotentHint=True,
                    openWorldHint=False,
                ),
                _meta={"tool_version": descriptor["version"]},
            )
            for descriptor in registry.list_tools()
        ]

    # SDK schema validation would return text-only errors before the registry
    # can supply its shared, strict-validation error envelope.
    @server.call_tool(validate_input=False)
    async def call_tool(name: str, arguments: dict[str, Any]) -> types.CallToolResult:
        response = registry.run_tool(name, arguments)
        payload = response.model_dump(mode="json")
        return types.CallToolResult(
            content=[
                types.TextContent(
                    type="text",
                    text=json.dumps(payload, allow_nan=False, sort_keys=True),
                )
            ],
            structuredContent=payload,
            isError=response.status != "ok",
        )

    @server.list_resources()
    async def list_resources() -> list[types.Resource]:
        return [
            types.Resource(
                uri=CATALOG_URI,
                name="Materials tool catalog",
                description="Versioned scientific tool descriptors and common response schema.",
                mimeType="application/json",
            ),
            types.Resource(
                uri=RESPONSE_SCHEMA_URI,
                name="Materials ToolResponse schema",
                description="JSON schema for every tool's complete response envelope.",
                mimeType="application/json",
            ),
        ]

    @server.read_resource()
    async def read_resource(uri: Any) -> list[ReadResourceContents]:
        if str(uri) == CATALOG_URI:
            content = catalog_json()
        elif str(uri) == RESPONSE_SCHEMA_URI:
            content = json.dumps(response_schema, allow_nan=False, sort_keys=True)
        else:
            raise ValueError("Unsupported materials resource URI")
        return [
            ReadResourceContents(
                content=content,
                mime_type="application/json",
            )
        ]

    return server


async def _serve(server: Server) -> None:
    from mcp.server.stdio import stdio_server

    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main() -> int:
    """Run the MCP stdio transport; stdout is reserved for protocol messages."""
    try:
        server = build_server()
    except _MissingMCPDependencyError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    try:
        asyncio.run(_serve(server))
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
