"""Агент: проверка запроса -> (подтверждение записи) -> вызов MCP-инструмента -> ответ + журнал.

Обрабатываемые ситуации (ТЗ на неделю, участник №4, задача 1):
  1 пропуск параметра      2 неверная единица     3 выход за диапазон     4 неоднозначность
  5 ПО недоступно          6 лицензия занята      7 таймаут               8 нет решения
  9 нет подтверждения записи                      10 повтор запроса       11 внедрённая инструкция

Вызов MCP-инструмента выполняется через MCP-клиент
и отдельный MCP-сервер по протоколу stdio.
Расчётное ПО подключается через адаптер.
В текущей версии используется TEST_ADAPTER.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
import time
import uuid
from pathlib import Path

from .adapter import LicenseBusyError, NoSolutionError, PVTPAdapter, SoftwareUnavailableError
from .result import (CLARIFIABLE, AgentResult, CalcStatus, ErrorCode, ErrorItem, Status)
from .validation import Validator

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RULES = ROOT / "config" / "agent_rules.json"


def load_rules(path: Path | str = DEFAULT_RULES) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _hash(obj) -> str:
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def _run_with_timeout(fn, timeout_s: float):
    """Запускает fn в фоновом потоке. Возвращает ('ok', value) | ('error', exc) | ('timeout', None).
    Зависший поток принудительно не убивается: отмена — только через поддерживаемый API ПО (п. 3.5 ТЗ)."""
    box: dict = {}

    def target():
        try:
            box["value"] = fn()
        except BaseException as e:  # noqa: BLE001 — передаём любую ошибку адаптера наверх
            box["error"] = e

    t = threading.Thread(target=target, daemon=True)
    t.start()
    t.join(timeout_s)
    if t.is_alive():
        return "timeout", None
    if "error" in box:
        return "error", box["error"]
    return "ok", box.get("value")


class Trace:
    """Журнал действий по trace_id: компонент, действие, инструмент, аргументы, ответ, статус, время."""

    def __init__(self, request_id):
        self.trace_id = f"trc-{uuid.uuid4().hex[:12]}"
        self.request_id = request_id
        self.steps: list[dict] = []
        self.started = time.time()

    def add(self, component, action, status, tool=None, arguments=None, response=None, duration_ms=None):
        self.steps.append({
            "step": len(self.steps) + 1, "component": component, "action": action, "tool": tool,
            "arguments": arguments, "response": response, "status": status,
            "duration_ms": None if duration_ms is None else round(duration_ms, 2),
        })

    def to_dict(self, final_status: str) -> dict:
        return {
            "request_id": self.request_id, "trace_id": self.trace_id,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(self.started)),
            "final_status": final_status, "total_ms": round((time.time() - self.started) * 1000, 2),
            "steps": self.steps,
        }


class PVTAgent:
    def __init__(self, adapter: PVTPAdapter, rules: dict | None = None, log_path: Path | str | None = None,
                 store_path: Path | str | None = None, sleep=time.sleep):
        self.adapter = adapter
        self.rules = rules or load_rules()
        self.log_path = (
            Path(log_path)
            if log_path is not None
            else ROOT / "logs" / "trace_log.jsonl"
        )
        self.store_path = Path(store_path) if store_path else None
        self.sleep = sleep  # можно подменить в тестах, чтобы не ждать паузу между повторами
        self.processed: dict[str, dict] = {}
        if self.store_path and self.store_path.exists():
            self.processed = json.loads(self.store_path.read_text(encoding="utf-8"))

    # ================================================================== главная точка входа
    def handle(self, request) -> AgentResult:
        req_id = request.get("request_id") if isinstance(request, dict) else None
        trace = Trace(req_id)
        res = AgentResult(request_id=req_id, trace_id=trace.trace_id, status=Status.REJECTED,
                          calc_status=CalcStatus.NOT_RUN,
                          uses_test_adapter=getattr(self.adapter, "is_test_adapter", False))
        trace.add("agent", "получен запрос", "OK", arguments=request if isinstance(request, dict) else repr(request))

        try:
            self._process(request, res, trace)
        finally:
            trace.add("agent", "сформирован ответ", res.status.value,
                      response={"error_code": res.error_code.value if res.error_code else None,
                                "mcp_tool_called": res.mcp_tool_called})
            self._write_log(trace.to_dict(res.status.value))
        return res

    def _process(self, request, res: AgentResult, trace: Trace) -> None:
        # ---- 10. повтор запроса
        if isinstance(request, dict) and request.get("request_id"):
            prev = self.processed.get(request["request_id"])
            if prev is not None:
                self._duplicate(request, prev, res, trace)
                return

        # ---- 11. посторонние инструкции в исходном документе
        if isinstance(request, dict):
            res.warnings = self._scan_injection(request.get("source_document"))
            if res.warnings:
                trace.add("security", "найдены инструкции в документе — считаются содержимым, полномочия не "
                          "меняются", "WARNING", response=[w.received for w in res.warnings])

        # ---- 1–4. проверка входа
        errors, norm = Validator(self.rules).validate(request)
        if errors:
            res.set_errors(errors)
            res.status = (Status.NEEDS_CLARIFICATION if all(e.code in CLARIFIABLE for e in errors)
                          else Status.REJECTED)
            res.user_message = self._msg_input_errors(errors, res.status)
            trace.add("validator", "проверка входа", "FAILED",
                      response=[{"code": e.code.value, "field": e.field} for e in errors])
            return
        trace.add("validator", "проверка входа", "OK", response=norm)

        if request["task_type"] == "run_experiment":
            self._run_experiment(request, norm, res, trace)
        else:
            self._apply_changes(request, norm, res, trace)

        if res.status == Status.SUCCESS:
            self._remember(request, res)

    # ================================================================== сценарии
    def _run_experiment(self, request, norm, res, trace):
        self._call_tool(
            "run_experiment",
            {"model_id": request["model_id"], **norm},
            lambda: self.adapter.run_experiment(
                request["model_id"], norm
            ),
            res,
            trace,
        )

        if res.status == Status.SUCCESS:
            if res.uses_test_adapter:
                res.calc_status = CalcStatus.NOT_RUN
                res.user_message = (
                    f"Тестовый вызов эксперимента {norm['type']} "
                    f"успешно выполнен (поток {norm['stream']}). "
                    "Использован TEST_ADAPTER. "
                    "Реальный расчёт PVTP не выполнялся. "
                    "Инженерная оценка: NOT_ASSESSED."
                )
            else:
                res.user_message = (
                    f"Эксперимент {norm['type']} выполнен "
                    f"(поток {norm['stream']}). "
                    "Инженерная оценка точности не выполнялась: "
                    "допуск не утверждён (NOT_ASSESSED)."
                )

    def _apply_changes(self, request, norm, res, trace):
        # ---- 9. запись в модель — только после подтверждения конкретного плана
        plan = {"plan_id": _hash({"model_id": request["model_id"], "changes": norm["changes"]})[:16],
                "model_id": request["model_id"], "target": "копия модели (исходный файл не изменяется)",
                "changes": norm["changes"]}
        res.change_plan = plan
        conf = request.get("confirmation")
        trace.add("agent", "сформирован план изменений", "OK", response=plan)

        if conf is None:
            res.status = Status.CONFIRMATION_REQUIRED
            res.set_errors([ErrorItem(ErrorCode.CONFIRMATION_REQUIRED, "confirmation",
                                      "Операция требует записи в модель; подтверждение не получено.",
                                      None, f'{{"plan_id": "{plan["plan_id"]}", "confirmed": true}}')])
            lines = [f"- {c['parameter']} " + (f"[{c['i']},{c['j']}]" if c["parameter"] == "BIC"
                                                 else f"[{c['component_index']}]") + f" -> {c['new_value']}"
                     for c in plan["changes"]]
            res.user_message = ("Запись НЕ выполнена. План изменений (будут применены к копии модели):\n"
                                + "\n".join(lines)
                                + f"\nДля применения отправьте тот же запрос с полем "
                                  f'"confirmation": {{"plan_id": "{plan["plan_id"]}", "confirmed": true}}.')
            return
        if not isinstance(conf, dict) or conf.get("confirmed") is not True:
            res.status = Status.REJECTED
            res.set_errors([ErrorItem(ErrorCode.CONFIRMATION_DECLINED, "confirmation.confirmed",
                                      "Пользователь не подтвердил запись (confirmed != true).",
                                      conf, "true")])
            res.user_message = "Запись в модель отменена: подтверждение не дано. Модель не изменялась."
            return
        if conf.get("plan_id") != plan["plan_id"]:
            res.status = Status.REJECTED
            res.set_errors([ErrorItem(ErrorCode.CONFIRMATION_MISMATCH, "confirmation.plan_id",
                                      "Подтверждён другой план изменений (plan_id не совпадает с текущим).",
                                      conf.get("plan_id"), plan["plan_id"])])
            res.user_message = ("Запись отменена: подтверждение относится к другому плану. "
                                f"Проверьте изменения и подтвердите plan_id {plan['plan_id']}.")
            return

        self._call_tool("apply_model_changes", plan,
                        lambda: self.adapter.apply_changes(request["model_id"], plan), res, trace)
        if res.status == Status.SUCCESS:
            res.user_message = (f"Изменения ({len(plan['changes'])}) применены к копии модели "
                                f"{res.results.get('model_copy_id')}. Исходная модель не изменялась.")
            if res.uses_test_adapter:
                res.user_message += " Внимание: использован ТЕСТОВЫЙ адаптер (имитация записи)."

    def _call_tool(self, tool, args, fn, res: AgentResult, trace: Trace) -> None:
        """Вызов MCP-инструмента с ограниченным повтором при занятой лицензии и таймаутом."""
        retry = self.rules["adapter"]["license_retry"]
        timeout_s = float(self.rules["adapter"]["timeout_s"])
        res.mcp_tool_called, res.mcp_tool = True, tool

        while True:
            res.attempts += 1
            t0 = time.perf_counter()
            kind, value = _run_with_timeout(fn, timeout_s)
            ms = (time.perf_counter() - t0) * 1000

            if kind == "ok":
                trace.add("mcp", f"вызов инструмента (попытка {res.attempts})", "SUCCESS", tool, args, value, ms)
                res.status, res.calc_status, res.results = Status.SUCCESS, CalcStatus.SUCCESS, value
                return

            if kind == "timeout":  # 7
                trace.add("mcp", f"вызов инструмента (попытка {res.attempts})", "TIMEOUT", tool, args, None, ms)
                self._fail(res, Status.TIMEOUT, CalcStatus.FAILED, ErrorCode.TIMEOUT,
                           f"Нет ответа ПО за {timeout_s} с. Состояние задачи зафиксировано в журнале; "
                           "принудительная отмена не выполнялась (только через поддерживаемый API).",
                           "Расчёт не завершился за отведённое время. Результатов нет. Повторите позже "
                           "или увеличьте таймаут по согласованию.")
                return

            err = value
            if isinstance(err, LicenseBusyError):  # 6
                trace.add("mcp", f"вызов инструмента (попытка {res.attempts})", "LICENSE_BUSY", tool, args,
                          str(err), ms)
                if res.attempts < retry["max_attempts"]:
                    self.sleep(retry["delay_s"])
                    continue
                self._fail(res, Status.LICENSE_BUSY, CalcStatus.NOT_RUN, ErrorCode.LICENSE_BUSY,
                           f"Лицензия занята; выполнено попыток: {res.attempts} из {retry['max_attempts']}.",
                           "Лицензия PVTP занята. Расчёт не выполнен, повторите запрос позже.")
                return
            if isinstance(err, SoftwareUnavailableError):  # 5
                trace.add("mcp", "вызов инструмента", "SOFTWARE_UNAVAILABLE", tool, args, str(err), ms)
                self._fail(res, Status.SOFTWARE_UNAVAILABLE, CalcStatus.NOT_RUN, ErrorCode.SOFTWARE_UNAVAILABLE,
                           str(err), "Расчётное ПО недоступно. Расчёт не выполнен, результатов нет.")
                return
            if isinstance(err, NoSolutionError):  # 8
                trace.add("mcp", "вызов инструмента", "NO_SOLUTION", tool, args,
                          {"reason": err.reason, "settings": err.settings}, ms)
                self._fail(res, Status.NO_SOLUTION, CalcStatus.FAILED, ErrorCode.NO_SOLUTION, err.reason,
                           "Решение не найдено. Причина и настройки сохранены в журнале; "
                           "числовых результатов нет.", received=err.settings)
                return
            trace.add("mcp", "вызов инструмента", "ADAPTER_ERROR", tool, args, repr(err), ms)
            self._fail(res, Status.ADAPTER_ERROR, CalcStatus.FAILED, ErrorCode.ADAPTER_ERROR,
                       f"{type(err).__name__}: {err}", "Ошибка адаптера ПО. Расчёт не выполнен.")
            return

    @staticmethod
    def _fail(res, status, calc, code, reason, msg, received=None):
        res.status, res.calc_status, res.results = status, calc, None
        res.set_errors([ErrorItem(code, None, reason, received)])
        res.user_message = msg

    # ================================================================== повтор запроса
    def _duplicate(self, request, prev, res, trace):
        if prev["hash"] == _hash(request):
            res.status = Status.DUPLICATE_REQUEST
            res.set_errors([ErrorItem(ErrorCode.DUPLICATE_REQUEST, "request_id",
                                      f"Запрос уже выполнен (trace_id {prev['trace_id']}); повторно не выполняется.",
                                      request["request_id"])])
            res.results = {"original_trace_id": prev["trace_id"], "original_status": prev["status"],
                           "original_results": prev["results"]}
            res.user_message = ("Этот запрос уже был выполнен. Повторный расчёт/запись не выполнялись, "
                                "возвращён сохранённый результат.")
            trace.add("agent", "повтор запроса — возвращён сохранённый результат", "DUPLICATE")
        else:
            res.status = Status.REJECTED
            res.set_errors([ErrorItem(ErrorCode.REQUEST_ID_CONFLICT, "request_id",
                                      "request_id уже использован для другого запроса с другим содержимым.",
                                      request["request_id"], "новый уникальный request_id")])
            res.user_message = "Запрос отклонён: такой request_id уже занят другим запросом. Задайте новый."
            trace.add("agent", "конфликт request_id", "REJECTED")

    def _remember(self, request, res):
        self.processed[request["request_id"]] = {"hash": _hash(request), "trace_id": res.trace_id,
                                                 "status": res.status.value, "results": res.results}
        if self.store_path:
            self.store_path.parent.mkdir(parents=True, exist_ok=True)
            self.store_path.write_text(json.dumps(self.processed, ensure_ascii=False, indent=2), encoding="utf-8")

    # ================================================================== внедрённые инструкции
    def _scan_injection(self, doc) -> list[ErrorItem]:
        if doc is None:
            return []
        text = doc.get("text", "") if isinstance(doc, dict) else str(doc)
        name = doc.get("name", "source_document") if isinstance(doc, dict) else "source_document"
        found = []
        for sentence in re.split(r"(?<=[.!?\n])\s*", text):
            low = sentence.lower()
            if any(p in low for p in self.rules["injection_patterns"]):
                found.append(ErrorItem(ErrorCode.INJECTED_INSTRUCTION_IGNORED, "source_document.text",
                                       f"В документе «{name}» найдена инструкция агенту. Она считается содержимым "
                                       "источника и не выполняется; полномочия агента не меняются.",
                                       sentence.strip()))
        return found

    # ================================================================== сообщения
    @staticmethod
    def _msg_input_errors(errors, status) -> str:
        head = ("Нужно уточнение — расчёт не запускался." if status == Status.NEEDS_CLARIFICATION
                else "Запрос отклонён — расчёт не запускался.")
        lines = [head]
        for i, e in enumerate(errors, 1):
            exp = f" Ожидается: {e.expected}." if e.expected else ""
            lines.append(f"{i}) [{e.code.value}] {e.field}: {e.reason}{exp}")
        lines.append("Значения не подставлялись автоматически; MCP-инструмент и ПО не вызывались.")
        return "\n".join(lines)

    def _write_log(self, entry: dict) -> None:
        if not self.log_path:
            return
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")  # кириллица без \\u-кодов
