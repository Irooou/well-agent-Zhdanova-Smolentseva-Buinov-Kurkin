"""Прогон сценариев из tests/scenario_inputs/*.json: ожидаемый результат vs фактический."""

from __future__ import annotations

import json
from pathlib import Path

from .adapter import TestPVTPAdapter
from .agent import ROOT, PVTAgent, load_rules

SCENARIO_DIR = ROOT / "tests" / "scenario_inputs"


def load_scenario(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def make_agent(adapter_cfg: dict, log_path=None) -> tuple[PVTAgent, TestPVTPAdapter]:
    rules = load_rules()
    if "timeout_s" in adapter_cfg:
        rules["adapter"]["timeout_s"] = adapter_cfg["timeout_s"]
    if "license_delay_s" in adapter_cfg:
        rules["adapter"]["license_retry"]["delay_s"] = adapter_cfg["license_delay_s"]
    adapter = TestPVTPAdapter(mode=adapter_cfg.get("mode", "ok"), delay_s=adapter_cfg.get("delay_s", 0.0))
    return PVTAgent(adapter, rules=rules, log_path=log_path), adapter


def _actual(result, adapter, key):
    d = result.to_dict()
    if key == "adapter_write_calls":
        return adapter.write_calls
    if key == "adapter_run_calls":
        return adapter.run_calls
    if key == "warning_code":
        codes = [w["code"] for w in d["warnings"]]
        return codes[0] if codes else None
    return d.get(key)


def run_scenario(path: Path, log_path=None) -> dict:
    sc = load_scenario(path)
    agent, adapter = make_agent(sc["adapter"], log_path)
    steps_out, last_plan_id = [], None
    for i, step in enumerate(sc["steps"], 1):
        if "request_file" in step:
            request = json.loads((ROOT / step["request_file"]).read_text(encoding="utf-8"))
        else:
            request = json.loads(json.dumps(step["request"]))
        # подставляем plan_id из предыдущего шага, если в файле стоит заглушка
        conf = request.get("confirmation")
        if isinstance(conf, dict) and str(conf.get("plan_id", "")).startswith("<") and last_plan_id:
            conf["plan_id"] = last_plan_id

        result = agent.handle(request)
        if result.change_plan:
            last_plan_id = result.change_plan["plan_id"]

        checks = []
        for key, exp in step["expected"].items():
            act = _actual(result, adapter, key)
            checks.append({"key": key, "expected": exp, "actual": act, "ok": act == exp})
        steps_out.append({"step": i, "request_id": request.get("request_id"), "result": result,
                          "checks": checks, "passed": all(c["ok"] for c in checks)})
    return {"scenario_id": sc["scenario_id"], "name": sc["name"], "file": Path(path).name,
            "uses_test_adapter": sc["uses_test_adapter"], "steps": steps_out,
            "passed": all(s["passed"] for s in steps_out)}


def all_scenarios() -> list[Path]:
    return sorted(SCENARIO_DIR.glob("S*.json"))
