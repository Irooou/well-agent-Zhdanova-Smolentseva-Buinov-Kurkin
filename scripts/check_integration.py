"""Интеграционные проверки PVT-агента."""

import json

from copy import deepcopy
from uuid import uuid4
from unittest.mock import patch

from agent import run
from src.agent.contracts import validate_result


CTX = {"test_mode": True}


def make_request(text):

    return {
        "request_id": str(uuid4()),
        "user_text": text,
    }


def check_result(result, expected_status):

    validate_result(result)

    assert result["status"] == expected_status, result
    assert result["trace"], "Отсутствует трассировка"

    print(
        f"PASS: {expected_status} | "
        f"{result['trace_id']}"
    )


def main():

    # 1. Корректный запрос на естественном языке.

    request = make_request(
        "Выполни CCE для исходной модели, "
        "поток Stream 1, температура 90 °C, "
        "давления 350, 300 и 250 BARa."
    )

    result = run(request, CTX)

    check_result(result, "SUCCESS")

    assert result["values"] == []
    assert "TEST_ADAPTER" in result["message"]

    assert any(
        step.get("tool") == "run_experiment"
        for step in result["trace"]
    )

    print("PASS: MCP и тестовый режим")


    # 2. Перефразированный запрос.

    paraphrased = make_request(
        "Для исходной модели на потоке Stream 1 "
        "нужно провести эксперимент CCE. "
        "Температура составляет 90 градусов Цельсия. "
        "Ступени абсолютного давления: "
        "350 BARa, 300 BARa, 250 BARa."
    )

    result2 = run(paraphrased, CTX)

    check_result(result2, "SUCCESS")

    def get_conditions(response):

        for step in response["trace"]:

            if step.get("tool") == "run_experiment":
                return step["response"]["conditions"]

        raise AssertionError("Нет результата MCP")

    assert get_conditions(result) == (
        get_conditions(result2)
    )

    print("PASS: одинаковые условия при перефразировании")


    # 3. Некорректная единица измерения.

    invalid = make_request(
        "Выполни CCE для исходной модели, "
        "поток Stream 1, температура 90 BARa, "
        "давления 350 и 300 BARa."
    )

    result3 = run(invalid, CTX)

    check_result(result3, "REJECTED")

    assert any(
        error["code"] == "UNIT_INVALID"
        for error in result3["errors"]
    )

    assert not any(
        step.get("tool") == "run_experiment"
        for step in result3["trace"]
    )

    print("PASS: отказ до вызова MCP")


    # 4. Отсутствующий параметр.

    missing = make_request(
        "Выполни CCE для исходной модели, "
        "поток Stream 1, давления 350 и 300 BARa."
    )

    result4 = run(missing, CTX)

    check_result(result4, "NEEDS_CLARIFICATION")

    assert any(
        error.get("field") ==
        "experiment.parameters.temperature"
        for error in result4["errors"]
    )

    assert not any(
        step.get("tool") == "run_experiment"
        for step in result4["trace"]
    )

    print("PASS: отсутствующая температура не придумана")


    # 5. Повторный запрос.

    duplicate = run(deepcopy(request), CTX)

    check_result(duplicate, "REJECTED")

    assert any(
        error["code"] == "DUPLICATE_REQUEST"
        for error in duplicate["errors"]
    )

    assert not any(
        step.get("tool") == "run_experiment"
        for step in duplicate["trace"]
    )

    print("PASS: повторный вызов заблокирован")


    # 6. Недоступность LLM.

    with patch(
        "src.agent.parser.ask_llm",
        side_effect=RuntimeError("LLM unavailable")
    ):

        result6 = run(
            make_request("Выполни CCE"),
            CTX,
        )

    check_result(result6, "FAILED")

    assert result6["errors"][0]["code"] == (
        "LLM_PARSE_FAILED"
    )

    assert not any(
        step.get("tool") == "run_experiment"
        for step in result6["trace"]
    )

    print("PASS: обработка недоступности LLM")

    print("\nIntegration tests: OK")


if __name__ == "__main__":
    main()