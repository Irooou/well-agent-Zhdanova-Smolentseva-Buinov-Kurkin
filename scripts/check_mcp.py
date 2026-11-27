"""Проверка соединения с MCP-сервером."""

import json

from src.agent.tools import McpToolGateway


def main():

    gateway = McpToolGateway(test_mode=True)

    print("\n1. Доступные MCP-инструменты:")

    tools = gateway.list_tools()

    for tool in tools:
        print("-", tool["name"])

    print("\n2. Состояние адаптера:")

    state = gateway.call_tool(
        "get_adapter_state",
        {},
    )

    print(json.dumps(
        state,
        ensure_ascii=False,
        indent=2,
    ))

    assert state["state"] == "ok"
    assert state["uses_test_adapter"] is True

    print("\nMCP connection: OK")


if __name__ == "__main__":
    main()