"""Адаптер к расчётному ПО.

PVTPAdapter — интерфейс, который должен реализовать настоящий адаптер к PVTP через OpenServer
(DoSet / DoCmd / DoGet). НАСТОЯЩИЙ адаптер в этом модуле НЕ реализован.

TestPVTPAdapter — тестовый адаптер (имитация, п. 3.6 ТЗ). Воспроизводит недоступность ПО, занятую
лицензию, таймаут и отсутствие решения. Числовых результатов PVT он не выдаёт: результаты
помечены как имитация и не являются расчётом PVTP.
"""

from __future__ import annotations

import time


class SoftwareUnavailableError(Exception):
    """ПО/OpenServer недоступны (не запущены, нет соединения)."""


class LicenseBusyError(Exception):
    """Лицензия PVTP занята."""


class NoSolutionError(Exception):
    """Расчёт выполнен, но решение не найдено (не сошёлся)."""

    def __init__(self, reason: str, settings: dict | None = None):
        super().__init__(reason)
        self.reason = reason
        self.settings = settings or {}


class PVTPAdapter:
    """Интерфейс адаптера. Реализация для OpenServer — задача следующего этапа."""

    is_test_adapter = False

    def run_experiment(self, model_id: str, args: dict) -> dict:
        raise NotImplementedError("Адаптер OpenServer/PVTP ещё не реализован")

    def apply_changes(self, model_id: str, plan: dict) -> dict:
        raise NotImplementedError("Адаптер OpenServer/PVTP ещё не реализован")


class TestPVTPAdapter(PVTPAdapter):
    """Имитация ПО. mode: ok | unavailable | license_busy | timeout | no_solution."""

    is_test_adapter = True
    __test__ = False  # чтобы pytest не принимал класс за набор тестов

    def __init__(self, mode: str = "ok", busy_attempts: int = 10**6, delay_s: float = 0.0):
        if mode not in {"ok", "unavailable", "license_busy", "timeout", "no_solution"}:
            raise ValueError(f"Неизвестный режим тестового адаптера: {mode}")
        self.mode = mode
        self.busy_attempts = busy_attempts  # сколько первых попыток лицензия занята
        self.delay_s = delay_s              # задержка «расчёта» для режима timeout
        self.calls = 0                      # все обращения к ПО (для имитации занятой лицензии)
        self.run_calls = 0                  # сколько раз вызывали расчёт
        self.write_calls = 0                # сколько раз записывали изменения
        self.model_copies: dict[str, dict] = {}

    def _common(self):
        self.calls += 1
        if self.mode == "unavailable":
            raise SoftwareUnavailableError("OpenServer не отвечает: PVTP не запущен или нет соединения (имитация)")
        if self.mode == "license_busy" and self.calls <= self.busy_attempts:
            raise LicenseBusyError("Лицензия PVTP занята другим пользователем (имитация)")
        if self.mode == "timeout":
            time.sleep(self.delay_s)

    def run_experiment(self, model_id: str, args: dict) -> dict:
        self.run_calls += 1
        self._common()
        if self.mode == "no_solution":
            raise NoSolutionError(
                "Расчёт не сошёлся: решение не найдено (имитация)",
                {"experiment": args.get("type"), "stream": args.get("stream"),
                 "temperature_degC": args.get("temperature_degC")},
            )
        return {
            "source": "TEST_ADAPTER",
            "note": "Имитация вызова. Это НЕ расчёт PVTP, числовые свойства не формируются.",
            "experiment": args.get("type"),
            "stream": args.get("stream"),
            "conditions": {k: v for k, v in args.items() if k not in ("type", "stream")},
        }

    def apply_changes(self, model_id: str, plan: dict) -> dict:
        self._common()
        copy_id = f"{model_id}__copy_{plan['plan_id'][:8]}"
        if copy_id in self.model_copies:  # повторная запись того же плана не дублирует изменения
            return {"model_copy_id": copy_id, "applied": 0, "already_applied": True, "source": "TEST_ADAPTER"}
        self.write_calls += 1
        self.model_copies[copy_id] = {"base_model": model_id, "changes": plan["changes"]}
        return {"model_copy_id": copy_id, "applied": len(plan["changes"]), "already_applied": False,
                "source": "TEST_ADAPTER",
                "note": "Изменения записаны в КОПИЮ модели внутри тестового адаптера (имитация)."}
