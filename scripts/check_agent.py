"""Проверка полной цепочки агент — MCP — адаптер."""

import json

from copy import deepcopy
from uuid import uuid4

from src.agent.loop import PVTAgent
from src.agent.mcp_adapter import McpPVTPAdapter


def main():

    agent = PVTAgent(
        adapter=McpPVTPAdapter(test_mode=True)
    )

    request = {
        "request_id": str(uuid4()),
        "task_type": "run_experiment",
        "model_id": "исходная_модель",
        "experiment": {
            "type": "CCE",
            "stream": "Stream 1",
            "parameters": {
                "temperature": {
                    "value": 90,
                    "unit": "degC",
                },
                "pressure_steps": [
                    {"value": 350, "unit": "BARa"},
                    {"value": 300, "unit": "BARa"},
                    {"value": 250, "unit": "BARa"},
                ],
            },
        },
    }

    print("\n=== 1. Корректный запрос ===")

    result = agent.handle(request).to_dict()

    print(json.dumps(
        result,
        ensure_ascii=False,
        indent=2,
    ))

    assert result["status"] == "SUCCESS"
    assert result["mcp_tool_called"] is True
    assert result["uses_test_adapter"] is True

    print("\n=== 2. Некорректный запрос ===")

    invalid_request = deepcopy(request)
    invalid_request["request_id"] = str(uuid4())

    invalid_request["experiment"]["parameters"][
        "temperature"
    ]["unit"] = "BARa"

    result = agent.handle(invalid_request).to_dict()

    print(json.dumps(
        result,
        ensure_ascii=False,
        indent=2,
    ))

    assert result["status"] == "REJECTED"
    assert result["mcp_tool_called"] is False
    assert result["error_code"] == "UNIT_INVALID"

    print("\nAgent integration: OK")


if __name__ == "__main__":
    main()