"""MCP-сервер PVT-агента."""

import os
from uuid import uuid4

from mcp.server.fastmcp import FastMCP

from mcp_server.simulator.client import create_adapter
from src.agent.loop import load_rules
from src.agent.validation import Validator
from src.agent.adapter import (
    SoftwareUnavailableError,
    LicenseBusyError,
    NoSolutionError,
)


mcp = FastMCP("PVT-Agent")

TEST_MODE = os.getenv("PVT_TEST_MODE") == "1"
adapter = create_adapter(test_mode=TEST_MODE)


@mcp.tool()
def get_adapter_state(trace_id: str | None = None) -> dict:
    """Проверяет состояние адаптера расчётного ПО."""

    return {
        "state": "ok" if TEST_MODE else "not_configured",
        "source": "TEST_ADAPTER" if TEST_MODE else "PVTP",
        "uses_test_adapter": TEST_MODE,
        "trace_id": trace_id or str(uuid4()),
        "message": (
            "Тестовый адаптер подключён. PVTP не используется."
            if TEST_MODE
            else "Подключение PVTP ещё не настроено."
        ),
    }


@mcp.tool()
def run_experiment(
    model: dict,
    stream: str,
    experiment: str,
    temperature: dict,
    pressures: list[dict],
    trace_id: str | None = None,
) -> dict:
    """Проверяет условия и запускает эксперимент через адаптер."""

    trace_id = trace_id or str(uuid4())

    # Пока поддерживаем только исходную модель.
    if model.get("path") != "PVT/исходная_модель.xlsx":
        return {
            "status": "REJECTED",
            "message": "Модель не разрешена.",
            "trace_id": trace_id,
        }

    # SEP требует отдельного формата ступеней.
    if experiment not in ("PSAT", "CCE", "CVD"):
        return {
            "status": "REJECTED",
            "message": "Эксперимент пока не поддерживается.",
            "trace_id": trace_id,
        }

    # Преобразование формата JSON-схемы
    # в формат существующего валидатора.
    temperature = temperature.copy()

    units = {"C": "degC", "F": "degF"}

    unit = temperature.get("unit")

    if isinstance(unit, str):
        temperature["unit"] = units.get(unit, unit)

    request = {
        "request_id": trace_id,
        "task_type": "run_experiment",
        "model_id": "исходная_модель",
        "experiment": {
            "type": experiment,
            "stream": stream,
            "parameters": {
                "temperature": temperature,
                "pressure_steps": pressures,
            },
        },
    }

    errors, normalized = Validator(load_rules()).validate(request)

    if errors:
        return {
            "status": "REJECTED",
            "errors": [
                {
                    "field": error.field,
                    "reason": error.reason,
                }
                for error in errors
            ],
            "trace_id": trace_id,
        }

    if not TEST_MODE:
        return {
            "status": "NOT_CONFIGURED",
            "message": "Реальный адаптер PVTP ещё не подключён.",
            "trace_id": trace_id,
        }

    try:
        result = adapter.run_experiment(
            request["model_id"],
            normalized,
        )

        return {
            "status": "SUCCESS",
            "result": result,
            "uses_test_adapter": True,
            "check_status": "NOT_ASSESSED",
            "trace_id": trace_id,
        }

    except SoftwareUnavailableError as error:
        status = "SOFTWARE_UNAVAILABLE"
        message = str(error)

    except LicenseBusyError as error:
        status = "LICENSE_BUSY"
        message = str(error)

    except NoSolutionError as error:
        status = "NO_SOLUTION"
        message = str(error)

    return {
        "status": status,
        "message": message,
        "trace_id": trace_id,
    }


if __name__ == "__main__":
    mcp.run(transport="stdio")