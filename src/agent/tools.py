"""Интерфейс инструментов агента и MCP-клиент."""

import asyncio
import json
import sys

from pathlib import Path
from typing import Any, Protocol

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


ROOT = Path(__file__).resolve().parents[2]


class ToolGateway(Protocol):

    def list_tools(self) -> list[dict[str, Any]]:
        ...

    def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        ...


class McpToolGateway:

    def __init__(
        self,
        server_url: str | None = None,
        test_mode: bool = False,
    ) -> None:

        if server_url is not None:
            raise ValueError(
                "Пока поддерживается только MCP stdio."
            )

        self._server_url = server_url

        self._params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "mcp_server.server"],
            cwd=str(ROOT),
            env={
                "PVT_TEST_MODE": "1" if test_mode else "0",
            },
        )

    async def _list_tools(self):

        async with stdio_client(self._params) as streams:
            async with ClientSession(*streams) as session:

                await session.initialize()
                result = await session.list_tools()

                return [
                    {
                        "name": tool.name,
                        "description": tool.description or "",
                        "input_schema": tool.inputSchema,
                    }
                    for tool in result.tools
                ]

    async def _call_tool(self, name, arguments):

        async with stdio_client(self._params) as streams:
            async with ClientSession(*streams) as session:

                await session.initialize()

                result = await session.call_tool(
                    name,
                    arguments=arguments,
                )

                if result.isError:
                    raise RuntimeError(str(result.content))

                structured = getattr(
                    result,
                    "structuredContent",
                    None,
                )

                if isinstance(structured, dict):
                    return structured

                for item in result.content:
                    if item.type == "text":
                        return json.loads(item.text)

                raise RuntimeError(
                    "MCP-сервер не вернул JSON-результат."
                )

    def list_tools(self) -> list[dict[str, Any]]:
        return asyncio.run(self._list_tools())

    def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:

        return asyncio.run(
            self._call_tool(name, arguments)
        )


def openai_tools(
    tools: list[dict[str, Any]],
    allowed: list[str],
) -> list[dict[str, Any]]:

    specs = []

    for tool in tools:

        if tool["name"] not in allowed:
            continue

        specs.append({
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": tool["input_schema"],
            },
        })

    return specs