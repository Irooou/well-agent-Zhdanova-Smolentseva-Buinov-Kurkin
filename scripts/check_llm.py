"""Проверка цепочки LLM — агент — MCP."""

import json

from src.agent.parser import parse_request
from src.agent.loop import PVTAgent
from src.agent.mcp_adapter import McpPVTPAdapter


def main():

    agent = PVTAgent(
        adapter=McpPVTPAdapter(test_mode=True)
    )

    scenarios = [
        {
            "name": "Корректный запрос",
            "text": (
                "Выполни эксперимент CCE для исходной "
                "модели, поток Stream 1, температура "
                "90 °C, давления 350, 300 и 250 BARa."
            ),
            "expected_status": "SUCCESS",
            "expected_mcp": True,
        },
        {
            "name": "Некорректная единица температуры",
            "text": (
                "Выполни эксперимент CCE для исходной "
                "модели, поток Stream 1, температура "
                "90 BARa, давления 350 и 300 BARa."
            ),
            "expected_status": "REJECTED",
            "expected_mcp": False,
        },
        {
            "name": "Отсутствует температура",
            "text": (
                "Выполни эксперимент CCE для исходной "
                "модели, поток Stream 1, давления "
                "350 и 300 BARa."
            ),
            "expected_status": "NEEDS_CLARIFICATION",
            "expected_mcp": False,
        },
    ]

    for scenario in scenarios:

        print("\n===", scenario["name"], "===")

        print("\nЗапрос пользователя:")
        print(scenario["text"])

        request = parse_request(scenario["text"])

        print("\nJSON от LLM:")
        print(json.dumps(
            request,
            ensure_ascii=False,
            indent=2,
        ))

        result = agent.handle(request).to_dict()

        print("\nОтвет агента:")
        print(json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        ))

        assert result["status"] == (
            scenario["expected_status"]
        )

        assert result["mcp_tool_called"] == (
            scenario["expected_mcp"]
        )

    print("\nLLM integration: OK")


if __name__ == "__main__":
    main()