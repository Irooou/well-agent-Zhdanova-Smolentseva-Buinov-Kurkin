"""Прогон всех 11 сценариев ошибок одной командой.

    python run_all_scenarios.py

Что делает:
  * выполняет сценарии из tests/scenario_inputs/;
  * сохраняет ответы агента на 3 примера в examples/errors/responses/;
  * записывает таблицу «ожидаемо / фактически / PASS-FAIL» в tests/scenario_results.md;
  * пишет журнал вызовов в logs/trace_log.jsonl.
Код выхода 0 — все сценарии пройдены, 1 — есть провалы.
"""

from __future__ import annotations

import json
import sys
import time

from pvt_agent.agent import ROOT
from pvt_agent.scenarios import all_scenarios, run_scenario

LOG = ROOT / "logs" / "trace_log.jsonl"
RESP_DIR = ROOT / "examples" / "errors" / "responses"
REPORT = ROOT / "tests" / "scenario_results.md"
EXAMPLE_RESPONSES = {"S01": "missing_parameter_response.json",
                     "S02": "invalid_unit_response.json",
                     "S03": "out_of_range_response.json"}


def fmt(v):
    return "—" if v is None else str(v).replace("|", "\\|")


def main() -> int:
    RESP_DIR.mkdir(parents=True, exist_ok=True)
    runs = [run_scenario(p, log_path=LOG) for p in all_scenarios()]

    for r in runs:
        if r["scenario_id"] in EXAMPLE_RESPONSES:
            d = r["steps"][0]["result"].to_dict()
            d["trace_id"] = "trc-пример"  # trace_id случайный; в файле-примере заменён на постоянный
            (RESP_DIR / EXAMPLE_RESPONSES[r["scenario_id"]]).write_text(
                json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# Результаты прогона сценариев ошибок",
        "",
        f"Сформировано командой `python run_all_scenarios.py` ({time.strftime('%Y-%m-%d %H:%M')}).",
        "Колонка «Адаптер»: **тестовый** — ситуация воспроизведена имитацией ПО (п. 3.6 ТЗ), "
        "реальный PVTP не вызывался; **не нужен** — отказ происходит до вызова ПО.",
        "",
        "| ID | Проверка | Шаг | request_id | Ожидаемо | Фактически | Адаптер | Итог |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in runs:
        for s in r["steps"]:
            exp = "; ".join(f"{c['key']}={fmt(c['expected'])}" for c in s["checks"])
            act = "; ".join(f"{c['key']}={fmt(c['actual'])}" for c in s["checks"])
            lines.append(f"| {r['scenario_id']} | {r['name']} | {s['step']} | {s['request_id']} | {exp} | {act} | "
                         f"{'тестовый' if r['uses_test_adapter'] else 'не нужен'} | "
                         f"{'PASS' if s['passed'] else '**FAIL**'} |")
    passed = sum(r["passed"] for r in runs)
    lines += ["", f"**Итого: пройдено {passed} из {len(runs)} сценариев.**", ""]
    REPORT.write_text("\n".join(lines), encoding="utf-8")

    for r in runs:
        mark = "PASS" if r["passed"] else "FAIL"
        print(f"[{mark}] {r['scenario_id']} {r['name']}")
        for s in r["steps"]:
            res = s["result"]
            print(f"       шаг {s['step']}: status={res.status.value}  error_code="
                  f"{res.error_code.value if res.error_code else '—'}  mcp_tool_called={res.mcp_tool_called}")
    print(f"\nИтого: {passed} из {len(runs)}. Таблица: {REPORT.relative_to(ROOT)}")
    return 0 if passed == len(runs) else 1


if __name__ == "__main__":
    sys.exit(main())
