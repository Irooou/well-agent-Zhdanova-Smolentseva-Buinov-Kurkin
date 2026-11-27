"""Проверка входа ДО вызова MCP-инструмента и ПО.

Порядок для величин (п. 3.4 ТЗ): наличие -> тип -> конечность -> единица -> пересчёт в °C/BARa
-> физический предел -> рабочий диапазон. Собираются ВСЕ ошибки; значения не подставляются.
"""

from __future__ import annotations

import math

from .result import ErrorCode, ErrorItem
from .units import UnitConversionNotConfirmed, to_BARa, to_degC, unit_kind


def _is_number(v) -> bool:
    # bool — подкласс int, но числом давления/температуры не является
    return isinstance(v, (int, float)) and not isinstance(v, bool)


class Validator:
    def __init__(self, rules: dict):
        self.rules = rules
        self.errors: list[ErrorItem] = []

    def _err(self, code, field, reason, received=None, expected=None, source="запрос пользователя"):
        self.errors.append(ErrorItem(code, field, reason, received, expected, source))

    # ------------------------------------------------------------------ общие поля
    def validate(self, req) -> tuple[list[ErrorItem], dict | None]:
        self.errors = []
        if not isinstance(req, dict):
            self._err(ErrorCode.INVALID_VALUE, None, "Запрос должен быть JSON-объектом.", type(req).__name__,
                      "объект {...}")
            return self.errors, None

        for name in self.rules["common_required"]:
            if req.get(name) in (None, ""):
                self._err(ErrorCode.MISSING_REQUIRED_FIELD, name,
                          f"Не указан обязательный параметр «{name}».", None, "непустое значение")

        task = req.get("task_type")
        if task not in (None, "") and task not in self.rules["task_types"]:
            self._err(ErrorCode.INVALID_VALUE, "task_type", f"Неизвестный тип задачи «{task}».", task,
                      " | ".join(self.rules["task_types"]), "схема запроса")

        model = req.get("model_id")
        if model not in (None, "") and model not in self.rules["allowed_model_ids"]:
            self._err(ErrorCode.INVALID_VALUE, "model_id",
                      f"Модель «{model}» недоступна агенту (преподавательская адаптированная модель "
                      "алгоритму не выдаётся, п. 1.1 ТЗ).", model, " | ".join(self.rules["allowed_model_ids"]),
                      "конфигурация проекта")

        norm = None
        if task == "run_experiment":
            norm = self._validate_experiment(req.get("experiment"))
        elif task == "apply_model_changes":
            norm = self._validate_changes(req.get("changes"))
        return self.errors, (None if self.errors else norm)

    # ------------------------------------------------------------------ эксперимент
    def _validate_experiment(self, exp) -> dict | None:
        if not isinstance(exp, dict):
            self._err(ErrorCode.MISSING_REQUIRED_FIELD, "experiment",
                      "Не указан блок эксперимента (тип, поток, параметры).", exp,
                      '{"type": ..., "stream": ..., "parameters": {...}}')
            return None
        norm: dict = {}
        etype = exp.get("type")
        exps = self.rules["experiments"]
        if etype in (None, ""):
            self._err(ErrorCode.MISSING_REQUIRED_FIELD, "experiment.type", "Не указан тип эксперимента.",
                      None, " | ".join(exps))
        elif etype not in exps:
            self._err(ErrorCode.INVALID_VALUE, "experiment.type", f"Эксперимент «{etype}» не поддерживается.",
                      etype, " | ".join(exps), "п. 2 ТЗ (PVT.PSAT/CCE/CVD/SEP)")
        if exp.get("stream") in (None, ""):
            self._err(ErrorCode.MISSING_REQUIRED_FIELD, "experiment.stream", "Не указан поток (stream) PVTP.",
                      None, "имя потока")
        if etype not in exps:
            return None
        norm.update(type=etype, stream=exp.get("stream"))

        params = exp.get("parameters")
        if not isinstance(params, dict):
            self._err(ErrorCode.MISSING_REQUIRED_FIELD, "experiment.parameters",
                      "Не указаны параметры эксперимента.", params, "объект параметров")
            return None

        base = "experiment.parameters"
        for name in exps[etype]["required"]:
            if params.get(name) is None:
                self._err(ErrorCode.MISSING_REQUIRED_FIELD, f"{base}.{name}",
                          f"Для эксперимента {etype} обязателен параметр «{name}»; значение не подставляется.",
                          None, self._expected_text(name))

        if "temperature" in exps[etype]["required"] and params.get("temperature") is not None:
            norm["temperature_degC"] = self._quantity(f"{base}.temperature", params["temperature"], "temperature")

        if "pressure_steps" in exps[etype]["required"] and params.get("pressure_steps") is not None:
            steps = params["pressure_steps"]
            if not isinstance(steps, list) or not steps:
                self._err(ErrorCode.INVALID_VALUE, f"{base}.pressure_steps", "Нужен непустой список давлений.",
                          steps, self._expected_text("pressure_steps"))
            elif len(steps) > self.rules["max_pressure_steps"]:
                self._err(ErrorCode.OUT_OF_RANGE, f"{base}.pressure_steps",
                          f"Слишком много ступеней: {len(steps)}.", len(steps),
                          f"не более {self.rules['max_pressure_steps']}", "конфигурация проекта")
            else:  # порядок ступеней сохраняется (PVT-04): не сортируем
                norm["pressure_steps_BARa"] = [
                    self._quantity(f"{base}.pressure_steps[{i}]", p, "pressure") for i, p in enumerate(steps)
                ]

        if etype == "SEP" and params.get("stages") is not None:
            stages = params["stages"]
            if not isinstance(stages, list) or not stages:
                self._err(ErrorCode.INVALID_VALUE, f"{base}.stages", "Нужен непустой список ступеней сепарации.",
                          stages, self._expected_text("stages"))
            else:  # порядок ступеней SEP не меняется (п. 1.4 ТЗ)
                norm["stages"] = []
                for i, st in enumerate(stages):
                    st = st if isinstance(st, dict) else {}
                    norm["stages"].append({
                        "pressure_BARa": self._quantity(f"{base}.stages[{i}].pressure", st.get("pressure"), "pressure"),
                        "temperature_degC": self._quantity(f"{base}.stages[{i}].temperature",
                                                           st.get("temperature"), "temperature"),
                    })
        return norm

    @staticmethod
    def _expected_text(name: str) -> str:
        return {
            "temperature": '{"value": <число>, "unit": "degC|degF|K"}',
            "pressure_steps": '[{"value": <число>, "unit": "BARa|psia|..."}, ...]',
            "stages": '[{"pressure": {...}, "temperature": {...}}, ...]',
        }.get(name, "значение")

    # ------------------------------------------------------------------ величина со значением и единицей
    def _allowed_units(self, kind: str) -> str:
        u = self.rules["units"]
        return ", ".join(u["temperature"] if kind == "temperature" else u["pressure_absolute"] + u["pressure_gauge"])

    def _quantity(self, path: str, q, kind: str) -> float | None:
        if q is None:
            self._err(ErrorCode.MISSING_REQUIRED_FIELD, path, "Величина не указана.", None,
                      '{"value": <число>, "unit": <единица>}')
            return None
        if not isinstance(q, dict):
            self._err(ErrorCode.INVALID_VALUE, path, "Величина должна быть объектом со значением и единицей.", q,
                      '{"value": <число>, "unit": <единица>}', "схема запроса")
            return None

        ok = True
        if q.get("value") is None:
            self._err(ErrorCode.MISSING_REQUIRED_FIELD, f"{path}.value", "Не указано значение.", None, "число")
            ok = False
        if q.get("unit") in (None, ""):
            self._err(ErrorCode.UNIT_MISSING, f"{path}.unit",
                      "Не указана единица; угадывать её по величине числа нельзя (п. 3.4 ТЗ).", None,
                      self._allowed_units(kind))
            ok = False
        if not ok:
            return None

        value, unit = q["value"], q["unit"]
        value_ok = True
        if not _is_number(value):
            self._err(ErrorCode.INVALID_VALUE, f"{path}.value",
                      f"Ожидается число, получено {type(value).__name__}. Строки не преобразуются неявно.",
                      value, "число")
            value_ok = False
        elif not math.isfinite(value):
            self._err(ErrorCode.INVALID_VALUE, f"{path}.value", "NaN/бесконечность недопустимы.", str(value),
                      "конечное число")
            value_ok = False

        if not self._unit_ok(f"{path}.unit", unit, kind) or not value_ok:
            return None

        try:
            if kind == "temperature":
                canon = to_degC(float(value), unit)
            else:
                atm = self.rules["atmospheric_pressure"]
                canon = to_BARa(float(value), unit, atm["value"] if atm.get("status") == "CONFIRMED" else None)
        except UnitConversionNotConfirmed as e:
            self._err(ErrorCode.UNIT_CONVERSION_NOT_CONFIRMED, f"{path}.unit",
                      f"{e}. Избыточное давление не переводится в абсолютное без подтверждения (п. 3.4 ТЗ).",
                      unit, "абсолютное давление (BARa, psia) или подтверждённое атмосферное давление",
                      "config/agent_rules.json: atmospheric_pressure.status = NOT_CONFIRMED")
            return None
        return self._limits(path, float(value), unit, canon, kind)

    def _unit_ok(self, path: str, unit, kind: str) -> bool:
        if not isinstance(unit, str):
            self._err(ErrorCode.UNIT_INVALID, path, "Единица должна быть строкой.", unit, self._allowed_units(kind))
            return False
        amb = self.rules["ambiguous_units"]
        if unit in amb:
            self._err(ErrorCode.UNIT_AMBIGUOUS, path, f"Единица «{unit}» неоднозначна: {amb[unit]}.", unit,
                      self._allowed_units(kind))
            return False
        k = unit_kind(unit)
        if k is None:
            self._err(ErrorCode.UNIT_INVALID, path, f"Неизвестная единица «{unit}».", unit, self._allowed_units(kind))
            return False
        dim = "temperature" if k == "temperature" else "pressure"
        if dim != kind:
            ru = {"temperature": "температуры", "pressure": "давления"}
            self._err(ErrorCode.UNIT_INVALID, path,
                      f"«{unit}» — единица {ru[dim]}, а поле ожидает величину {ru[kind]} (не та размерность).",
                      unit, self._allowed_units(kind))
            return False
        return True

    def _limits(self, path, value, unit, canon, kind) -> float | None:
        sym = "°C" if kind == "temperature" else "BARa"
        shown = f"{value} {unit}" if unit in ("degC", "°C", "BARa", "bara") else f"{value} {unit} (= {canon:.3f} {sym})"
        lim, rng = self.rules["physical_limits"], self.rules["working_ranges"]
        src = f"{rng['source']}; статус {rng['status']}"
        if kind == "temperature":
            phys, r, phys_txt = lim["temperature_degC_min_exclusive"], rng["temperature_degC"], "выше абсолютного нуля"
        else:
            phys, r, phys_txt = lim["pressure_BARa_min_exclusive"], rng["pressure_BARa"], "абсолютное давление > 0"
        if canon <= phys:
            self._err(ErrorCode.INVALID_VALUE, f"{path}.value", f"{shown}: физически невозможно ({phys_txt}).",
                      value, f"> {phys} {sym}", "физический предел")
            return None
        if not (r["min"] <= canon <= r["max"]):
            self._err(ErrorCode.OUT_OF_RANGE, f"{path}.value",
                      f"{shown} вне допустимого диапазона [{r['min']}; {r['max']}] {sym}.",
                      value, f"[{r['min']}; {r['max']}] {sym}", src)
            return None
        return canon

    # ------------------------------------------------------------------ изменения модели
    def _validate_changes(self, changes) -> dict | None:
        cfg = self.rules["model_changes"]
        n = cfg["component_count"]
        if not isinstance(changes, list) or not changes:
            self._err(ErrorCode.MISSING_REQUIRED_FIELD, "changes", "Не указан список изменений модели.", changes,
                      "непустой список изменений")
            return None
        norm, seen = [], set()
        for k, ch in enumerate(changes):
            p = f"changes[{k}]"
            if not isinstance(ch, dict):
                self._err(ErrorCode.INVALID_VALUE, p, "Изменение должно быть объектом.", ch, "объект")
                continue
            par = ch.get("parameter")
            if par not in cfg["allowed_parameters"]:
                self._err(ErrorCode.INVALID_VALUE, f"{p}.parameter",
                          f"Параметр «{par}» не входит в разрешённый список.", par,
                          " | ".join(cfg["allowed_parameters"]), "список разрешённых параметров (PVT-06)")
                continue
            idx_fields = ["i", "j"] if par == "BIC" else ["component_index"]
            idx_ok = True
            for f in idx_fields:
                v = ch.get(f)
                if v is None:
                    self._err(ErrorCode.MISSING_REQUIRED_FIELD, f"{p}.{f}", f"Не указан индекс «{f}».", None,
                              f"целое 0..{n - 1}")
                    idx_ok = False
                elif not isinstance(v, int) or isinstance(v, bool) or not 0 <= v < n:
                    self._err(ErrorCode.OUT_OF_RANGE, f"{p}.{f}", f"Индекс компонента вне 0..{n - 1} (PVT-02).",
                              v, f"целое 0..{n - 1}")
                    idx_ok = False
            if idx_ok and par == "BIC" and ch["i"] == ch["j"]:
                self._err(ErrorCode.INVALID_VALUE, p, "BIC задаётся для пары разных компонентов.",
                          [ch["i"], ch["j"]], "i != j")
                idx_ok = False
            nv = ch.get("new_value")
            if nv is None:
                self._err(ErrorCode.MISSING_REQUIRED_FIELD, f"{p}.new_value", "Не указано новое значение.", None,
                          "число")
                continue
            if not _is_number(nv) or not math.isfinite(nv):
                self._err(ErrorCode.INVALID_VALUE, f"{p}.new_value", "Новое значение должно быть конечным числом.",
                          nv if _is_number(nv) else repr(nv), "число")
                continue
            if not idx_ok:
                continue
            key = (par, tuple(sorted((ch["i"], ch["j"])))) if par == "BIC" else (par, ch["component_index"])
            if key in seen:
                self._err(ErrorCode.INVALID_VALUE, p, "Повторное изменение того же параметра в одном запросе "
                          "(конфликтующая пара, PVT-02).", list(key[1]) if par == "BIC" else key[1], "уникальные пары")
                continue
            seen.add(key)
            item = {"parameter": par, "new_value": float(nv)}
            item.update({f: ch[f] for f in idx_fields})
            norm.append(item)
        return {"changes": norm}
