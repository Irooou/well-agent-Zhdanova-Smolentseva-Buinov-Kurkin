"""Проверка основной точки входа агента."""

import json

from copy import deepcopy
from uuid import uuid4

from agent import run
from src.agent.contracts import validate_result


def main():

    request = {
        "request_id": str(uuid4()),
        "user_text": (
            "Выполни CCE для исходной модели, "
            "поток Stream 1, температура 90 °C, "
            "давления 350, 300 и 250 BARa."
        ),
    }

    ctx = {
        "test_mode": True,
    }

    # Сценарий 1. Запрос на естественном языке.

    result = run(request, ctx)

    validate_result(result)

    print("\n=== Текстовый запрос ===")

    print(json.dumps(
        result,
        ensure_ascii=False,
        indent=2,
    ))

    assert result["status"] == "SUCCESS"
    assert result["values"] == []

    # Сценарий 2. Готовый типизированный запрос.

    structured = deepcopy(request)
    structured["request_id"] = str(uuid4())

    structured["task"] = {
        "task_type": "run_baseline",
        "model": {
            "path": "PVT/исходная_модель.xlsx",
        },
        "stream": "Stream 1",
        "experiments": [
            {
                "experiment": "CCE",
                "temperature": {
                    "value": 90,
                    "unit": "C",
                },
                "pressures": [
                    {"value": 350, "unit": "BARa"},
                    {"value": 300, "unit": "BARa"},
                    {"value": 250, "unit": "BARa"},
                ],
            }
        ],
        "dry_run": True,
    }

    result = run(structured, ctx)

    validate_result(result)

    print("\n=== Типизированный запрос ===")

    print(json.dumps(
        result,
        ensure_ascii=False,
        indent=2,
    ))

    assert result["status"] == "SUCCESS"

    # Сценарий 3. Некорректная единица.

    invalid = deepcopy(structured)
    invalid["request_id"] = str(uuid4())

    invalid["task"]["experiments"][0][
        "temperature"
    ]["unit"] = "BARa"

    result = run(invalid, ctx)

    validate_result(result)

    print("\n=== Некорректный запрос ===")

    print(json.dumps(
        result,
        ensure_ascii=False,
        indent=2,
    ))

    assert result["status"] == "VALIDATION_FAILED"

    # Сценарий 4. Реальное ПО не подключено.

    unavailable = deepcopy(structured)
    unavailable["request_id"] = str(uuid4())

    result = run(unavailable)

    validate_result(result)

    print("\n=== Реальное ПО ===")

    print(json.dumps(
        result,
        ensure_ascii=False,
        indent=2,
    ))

    assert result["status"] in (
        "SOFTWARE_UNAVAILABLE",
        "NOT_CONFIGURED",
    )

    print("\nEntrypoint integration: OK")


if __name__ == "__main__":
    main()