"""Преобразование естественного языка в запрос агента."""

import json
import time

from src.agent.schemas import ParsedRequest
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from src.agent.llm import ask_llm
from src.agent.prompts import SYSTEM_PROMPT


ROOT = Path(__file__).resolve().parents[2]
LOG_PATH = ROOT / "logs" / "llm_log.jsonl"


def write_llm_log(record: dict) -> None:

    LOG_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with LOG_PATH.open("a", encoding="utf-8") as file:
        file.write(
            json.dumps(record, ensure_ascii=False) + "\n"
        )


def parse_request(
    user_text: str,
    request_id: str | None = None,
) -> dict:

    request_id = request_id or str(uuid4())
    started = time.perf_counter()

    record = {
        "request_id": request_id,
        "component": "llm",
        "action": "parse_request",
        "timestamp": datetime.now(
            timezone.utc
        ).isoformat(),
    }

    try:

        if not isinstance(user_text, str):
            raise ValueError("Ожидается текстовый запрос.")

        if not user_text.strip():
            raise ValueError("Запрос пуст.")

        raw_answer = ask_llm([
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": user_text,
            },
        ])

        # Удаляем Markdown-обёртку, если модель
        # всё-таки её добавила.
        answer = raw_answer.strip()

        if answer.startswith("```"):
            lines = answer.splitlines()

            if lines[-1].strip() == "```":
                answer = "\n".join(lines[1:-1])

        parsed = ParsedRequest.model_validate(
            json.loads(answer)
        ).model_dump()


        # Идентификатор назначает программа, а не LLM.
        request = {
            "request_id": request_id,
            "task_type": parsed.get("task_type"),
            "model_id": parsed.get("model_id"),
            "experiment": parsed.get("experiment"),
        }

        # На текущем этапе разрешены только эксперименты.
        if request["task_type"] != "run_experiment":
            request["task_type"] = "out_of_scope"

        record["status"] = "SUCCESS"
        record["parsed_request"] = request

        return request

    except Exception as error:

        record["status"] = "FAILED"
        record["error_type"] = type(error).__name__

        raise RuntimeError(
            "Не удалось преобразовать запрос в JSON."
        ) from None

    finally:

        record["duration_ms"] = round(
            (time.perf_counter() - started) * 1000,
            2,
        )

        write_llm_log(record)