"""Запуск агента на одном JSON-запросе из командной строки.

Примеры (из корня репозитория):
    python -m pvt_agent.cli examples/errors/missing_parameter.json
    python -m pvt_agent.cli examples/errors/invalid_unit.json
    python -m pvt_agent.cli examples/errors/out_of_range.json
    python -m pvt_agent.cli examples/errors/missing_parameter.json --adapter unavailable
    python -m pvt_agent.cli tests/scenario_inputs/S10_repeat_request.json   (файл сценария: все шаги)

Журнал пишется в logs/trace_log.jsonl, выполненные запросы — в logs/processed_requests.json
(нужно для проверки повторной отправки). Флаг --reset очищает список выполненных запросов.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .adapter import TestPVTPAdapter
from .agent import ROOT, PVTAgent, load_rules
from .scenarios import run_scenario

LOG = ROOT / "logs" / "trace_log.jsonl"
STORE = ROOT / "logs" / "processed_requests.json"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="PVT-агент: проверка запроса и ответ")
    ap.add_argument("request", help="путь к JSON-файлу запроса")
    ap.add_argument("--adapter", default="ok",
                    choices=["ok", "unavailable", "license_busy", "timeout", "no_solution"],
                    help="режим тестового адаптера (имитация ПО)")
    ap.add_argument("--timeout", type=float, default=None, help="таймаут вызова ПО, с")
    ap.add_argument("--reset", action="store_true", help="очистить список выполненных запросов")
    a = ap.parse_args(argv)

    if a.reset and STORE.exists():
        STORE.unlink()

    data = json.loads(Path(a.request).read_text(encoding="utf-8"))
    if isinstance(data, dict) and "steps" in data:  # файл сценария: свой режим адаптера и несколько шагов
        run = run_scenario(Path(a.request), log_path=LOG)
        for st in run["steps"]:
            print(f"===== {run['scenario_id']} шаг {st['step']} ({'PASS' if st['passed'] else 'FAIL'}) =====")
            print(json.dumps(st["result"].to_dict(), ensure_ascii=False, indent=2))
            print("--- Сообщение пользователю ---\n" + st["result"].user_message)
        return 0 if run["passed"] else 1
    request = data

    rules = load_rules()
    if a.timeout is not None:
        rules["adapter"]["timeout_s"] = a.timeout
    adapter = TestPVTPAdapter(mode=a.adapter, delay_s=(rules["adapter"]["timeout_s"] + 1) if a.adapter == "timeout" else 0)
    agent = PVTAgent(adapter, rules=rules, log_path=LOG, store_path=STORE)

    result = agent.handle(request)
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    print("\n--- Сообщение пользователю ---\n" + result.user_message, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
