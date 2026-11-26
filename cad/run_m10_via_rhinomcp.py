"""Send the M10 Rhino build script to Rhino through RhinoMCP."""

import asyncio
import pathlib

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


SCRIPT = pathlib.Path(__file__).with_name("m10_shell_200x150_rhino.py")


async def main():
    failed = False
    server = StdioServerParameters(
        command="uvx",
        args=["--with", "mcp[cli]==1.10.1", "rhinomcp"],
        env={
            "RHINO_MCP_HOST": "127.0.0.1",
            "RHINO_MCP_PERCEPTION": "1",
            "RHINO_MCP_TIMEOUT": "120",
            "RHINO_MCP_LOG_LEVEL": "ERROR",
        },
    )
    async with stdio_client(server) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "execute_rhinoscript_python_code",
                {"code": SCRIPT.read_text(encoding="utf-8")},
            )
            for block in result.content:
                text = getattr(block, "text", None)
                if text:
                    print(text)
                    if '"success": false' in text.lower():
                        failed = True
            if result.isError:
                failed = True
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
