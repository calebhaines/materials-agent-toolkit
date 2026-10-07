"""Launch a local server with the official MCP client and analyze water.

Install the package's optional MCP dependency, then run:
    python examples/mcp_client.py
"""

import json
import sys

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def analyze_water() -> dict:
    parameters = StdioServerParameters(
        command=sys.executable, args=["-m", "materials_agent_toolkit.mcp_server"]
    )
    with anyio.fail_after(30):
        async with stdio_client(parameters) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool("composition.analyze", {"formula": "H2O"})
                if result.isError:
                    raise RuntimeError(result.content)
                if result.structuredContent is None:
                    raise RuntimeError("Server did not return structured calculation content")
                return result.structuredContent


if __name__ == "__main__":
    print(json.dumps(anyio.run(analyze_water), indent=2, allow_nan=False))
