import asyncio
import json
import os

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

MCP_SERVER_URL = os.environ.get("MCP_SERVER_URL", "http://127.0.0.1:8081/mcp")


async def call_tool(name: str, arguments: dict):
    async with streamable_http_client(MCP_SERVER_URL) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.call_tool(name=name, arguments=arguments)
    content = result.content[0] if result.content else None
    text = getattr(content, "text", "") if content is not None else ""
    if result.is_error:
        raise RuntimeError(f"MCP tool '{name}' failed: {text}")
    return json.loads(text)


def call_tool_sync(name: str, arguments: dict):
    """For sync FastAPI routes, which run in a worker thread with no event loop."""
    return asyncio.run(call_tool(name, arguments))