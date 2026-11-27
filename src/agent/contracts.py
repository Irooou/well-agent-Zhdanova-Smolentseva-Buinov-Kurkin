"""Согласование внутренних и внешних форматов агента."""

import json

from pathlib import Path
from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[2]

MODEL_PATH = "PVT/исходная_модель.xlsx"


def load_schema(filename: str) -> dict:

    path = ROOT / "schemas" / filename

    with path.open(encoding="utf-8") as file:
        return json.load(file)


def validate_request(request: dict) -> None:

    schema = load_schema("agent_request.json")

    Draft202012Validator(
        schema,
        format_checker=FormatChecker(),
    ).validate(request)


def validate_result(result: dict) -> None:

    schema = load_schema("agent_result.json")

    Draft202012Validator(
        schema,
        format_checker=FormatChecker(),
    ).validate(result)


def to_internal_request(request: dict) -> dict:

    task = request["task"]

    if task["task_type"] != "run_baseline":
        raise NotImplementedError(
            "Данный тип задачи пока не реализован."
        )

    model = task.get("model", {})

    if model.get("path") != MODEL_PATH:
        raise ValueError(
            "Разрешена только исходная модель."
        )

    if model.get("sha256"):
        raise NotImplementedError(
            "Проверка хеша модели пока не реализована."
        )

    experiments = task.get("experiments", [])

    if len(experiments) != 1:
        raise ValueError(
            "Укажите ровно один эксперимент."
        )

    experiment = experiments[0]

    if experiment["experiment"] not in (
        "PSAT", "CCE", "CVD"
    ):
        raise NotImplementedError(
            "Эксперимент пока не поддерживается."
        )

    temperature = experiment["temperature"].copy()

    units = {
        "C": "degC",
        "F": "degF",
    }

    temperature["unit"] = units.get(
        temperature["unit"],
        temperature["unit"],
    )

    pressures = experiment["pressures"]

    if any(
        p["unit"] == "psig"
        for p in pressures
    ):
        raise ValueError(
            "Пересчёт избыточного давления "
            "пока не согласован."
        )

    return {
        "request_id": request["request_id"],
        "task_type": "run_experiment",
        "model_id": "исходная_модель",
        "experiment": {
            "type": experiment["experiment"],
            "stream": task.get("stream"),
            "parameters": {
                "temperature": temperature,
                "pressure_steps": pressures,
            },
        },
    }

def load_trace(trace_id: str) -> list[dict]:

    log_path = ROOT / "logs" / "trace_log.jsonl"

    if not log_path.exists():
        return []

    with log_path.open(encoding="utf-8") as file:
        lines = file.readlines()

    for line in reversed(lines):

        record = json.loads(line)

        if record.get("trace_id") != trace_id:
            continue

        trace = []

        for step in record.get("steps", []):

            item = {
                "trace_id": trace_id,
                "step": (
                    f"{step['component']}: "
                    f"{step['action']}"
                ),
                "status": step["status"],
            }

            if isinstance(step.get("tool"), str):
                item["tool"] = step["tool"]

            if isinstance(step.get("arguments"), dict):
                item["arguments"] = step["arguments"]

            if step.get("response") is not None:
                item["response"] = step["response"]

            if step.get("duration_ms") is not None:
                item["duration_ms"] = step["duration_ms"]

            trace.append(item)

        return trace

    return []

def to_external_result(result: dict) -> dict:

    status_map = {
        "CONFIRMATION_REQUIRED": "NEEDS_CONFIRMATION",
        "DUPLICATE_REQUEST": "REJECTED",
        "ADAPTER_ERROR": "FAILED",
    }

    status = status_map.get(
        result["status"],
        result["status"],
    )

    errors = []

    for error in result.get("errors", []):

        item = {
            "code": error["code"],
            "message": error["reason"],
            "trace_id": result["trace_id"],
        }

        for field in ("field", "source"):

            if isinstance(error.get(field), str):
                item[field] = error[field]

        errors.append(item)

    if not errors and result.get("error_code"):

        errors.append({
            "code": result["error_code"],
            "message": (
                result.get("reason")
                or result.get("user_message")
                or "Ошибка обработки запроса."
            ),
            "trace_id": result["trace_id"],
        })
    message = result["user_message"]

    if (
            result.get("uses_test_adapter")
            and status == "SUCCESS"
    ):
        message = (
            "Тестовый вызов MCP успешно выполнен. "
            "Использован TEST_ADAPTER. "
            "Реальный расчёт PVTP не выполнялся. "
            "Инженерная оценка: NOT_ASSESSED."
        )

    external = {
        "request_id": result["request_id"],
        "trace_id": result["trace_id"],
        "status": status,
        "message": message,
        "errors": errors,
        "values": [],
        "sources": [],
        "pending_confirmation": None,
        "trace": load_trace(result["trace_id"]),
    }

    validate_result(external)

    return external