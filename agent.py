"""Основная точка входа PVT-агента."""

import json

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from jsonschema import ValidationError

from src.agent.contracts import (
    validate_request,
    validate_result,
    to_internal_request,
    to_external_result,
)

from src.agent.parser import parse_request
from src.agent.loop import PVTAgent, load_rules
from src.agent.mcp_adapter import McpPVTPAdapter


ROOT = Path(__file__).resolve().parent


def failure(
    request_id: str,
    status: str,
    code: str,
    message: str,
) -> dict:

    trace_id = f"trc-{uuid4().hex[:12]}"

    result = {
        "request_id": request_id,
        "trace_id": trace_id,
        "status": status,
        "message": message,
        "errors": [
            {
                "code": code,
                "message": message,
                "trace_id": trace_id,
            }
        ],
        "values": [],
        "sources": [],
        "trace": [
            {
                "trace_id": trace_id,
                "step": "request_processing",
                "status": status,
            }
        ],
    }

    validate_result(result)

    log_path = ROOT / "logs" / "entrypoint_log.jsonl"

    log_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    record = {
        "request_id": request_id,
        "trace_id": trace_id,
        "timestamp": datetime.now(
            timezone.utc
        ).isoformat(),
        "final_status": status,
        "error_code": code,
        "mcp_tool_called": False,
    }

    with log_path.open("a", encoding="utf-8") as file:
        file.write(
            json.dumps(record, ensure_ascii=False) + "\n"
        )

    return result


def run(request, ctx=None) -> dict:

    """Обработка запроса согласно внешней JSON-схеме."""

    request_id = str(uuid4())

    if isinstance(request, dict):

        candidate = request.get("request_id")

        if isinstance(candidate, str) and candidate:
            request_id = candidate

    try:

        validate_request(request)

    except ValidationError:

        return failure(
            request_id,
            "VALIDATION_FAILED",
            "INVALID_REQUEST_SCHEMA",
            "Запрос не соответствует схеме AgentRequest.",
        )

    # Проверка исходного текста до обращения к LLM.
    rules = load_rules()

    user_text = request["user_text"].casefold()

    for pattern in rules["injection_patterns"]:

        if pattern.casefold() in user_text:

            return failure(
                request_id,
                "REJECTED",
                "INJECTED_INSTRUCTION_IGNORED",
                "Обнаружена инструкция об обходе "
                "ограничений агента. "
                "Запрос отклонён, расчёт не запускался.",
            )

    # Тестовый режим включается только явно.
    test_mode = (
        isinstance(ctx, dict)
        and ctx.get("test_mode") is True
    )

    if request.get("confirmation") is not None:

        return failure(
            request_id,
            "REJECTED",
            "WRITE_NOT_SUPPORTED",
            "Изменение модели пока не поддерживается.",
        )

    if "task" in request:

        try:
            internal = to_internal_request(request)

        except NotImplementedError as error:

            return failure(
                request_id,
                "NOT_CONFIGURED",
                "TASK_NOT_SUPPORTED",
                str(error),
            )

        except ValueError as error:

            return failure(
                request_id,
                "REJECTED",
                "INVALID_TASK",
                str(error),
            )

    else:

        try:
            internal = parse_request(
                request["user_text"],
                request_id=request_id,
            )

        except RuntimeError:

            return failure(
                request_id,
                "FAILED",
                "LLM_PARSE_FAILED",
                "LLM не смогла обработать запрос. "
                "Расчёт не запускался.",
            )

    if internal.get("task_type") != "run_experiment":

        return failure(
            request_id,
            "REJECTED",
            "TASK_NOT_SUPPORTED",
            "Запрошенная операция не поддерживается.",
        )

    agent = PVTAgent(
        adapter=McpPVTPAdapter(
            test_mode=test_mode
        ),
        store_path=(
                ROOT / "logs" / (
            "processed_test.json"
            if test_mode
            else "processed_real.json"
        )
        ),
    )

    result = agent.handle(internal).to_dict()

    return to_external_result(result)
