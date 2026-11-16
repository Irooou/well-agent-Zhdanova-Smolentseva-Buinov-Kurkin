
"""Интерфейс инструментов агента и заготовка MCP-клиента."""

from typing import Any, Protocol


class ToolGateway(Protocol):
    """Порт, через который агент работает с внешними инструментами."""

    def list_tools(self) -> list[dict[str, Any]]:
        """Вернуть описания доступных инструментов."""
        ...

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Вызвать инструмент и вернуть структурированный результат."""
        ...


class McpToolGateway:
    """Заготовка клиента для подключения к MCP-серверу проекта."""

    def __init__(self, server_url: str | None) -> None:
        self._server_url = server_url

    def list_tools(self) -> list[dict[str, Any]]:
        """Получить список инструментов MCP.

        TODO: подключите MCP SDK и преобразуйте схемы инструментов в формат,
        который передаётся языковой модели.

        Пока MCP-клиент не подключён, возвращается пустой список.
        """
        return []

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Вызвать MCP-инструмент.

        TODO: реализуйте вызов через MCP SDK после выбора режима подключения:
        stdio для локального запуска или streamable HTTP для удалённого сервера.
        """
        raise NotImplementedError(
            f"MCP-клиент не настроен: tool={name!r}, server={self._server_url!r}"
        )


def openai_tools(tools: list[dict[str, Any]], allowed: list[str]) -> list[dict[str, Any]]:
    """Описания MCP → формат инструментов OpenAI API.

    tools — список инструментов, полученный от MCP-сервера.
    allowed — список имён инструментов, разрешённых для текущего запроса.

    Возвращает список инструментов в формате OpenAI function calling.
    """
    specs = []

    for tool in tools:
        if tool["name"] not in allowed:
            continue

        specs.append(
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": tool["input_schema"],
                },
            }
        )

    return specs
