
import asyncio


async def main() -> None:
    from _bootstrap import prepare_backend

    prepare_backend()

    import os
    from dotenv import load_dotenv
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    load_dotenv()

    url = os.getenv(
        "MCP_SERVER_URL",
        "http://127.0.0.1:8081/mcp",
    )

    async with streamable_http_client(url) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.list_tools()

            print("Connected to MCP server.")
            print("Available tools:")

            for tool in result.tools:
                print(f"- {tool.name}")


if __name__ == "__main__":
    asyncio.run(main())
