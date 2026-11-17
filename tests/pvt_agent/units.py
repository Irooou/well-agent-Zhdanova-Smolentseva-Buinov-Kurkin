"""Преобразование единиц к каноническим: температура -> degC, давление -> BARa.

Правила из ТЗ (п. 1.2, 3.4, PVT-03):
  * °F/°C и psig/BARa должны различаться явно;
  * шкалу давления (абсолютная/избыточная) нельзя угадывать по величине числа;
  * пересчёт избыточного давления в абсолютное требует ПОДТВЕРЖДЁННОГО атмосферного давления.
"""

from __future__ import annotations

PSI_TO_BAR = 0.0689475729  # 1 psi = 0.0689475729 bar (точное определение через фунт-силу)

# Синонимы -> каноническое обозначение
_TEMPERATURE_ALIASES = {
    "degC": "degC", "°C": "degC",
    "degF": "degF", "°F": "degF",
    "K": "K",
}
_PRESSURE_ABS_ALIASES = {
    "BARa": "BARa", "bara": "BARa",
    "psia": "psia",
    "MPa_abs": "MPa_abs",
    "kPa_abs": "kPa_abs",
}
_PRESSURE_GAUGE_ALIASES = {
    "psig": "psig",
    "barg": "barg", "BARg": "barg",
}


class UnitConversionNotConfirmed(Exception):
    """Пересчёт невозможен без подтверждённого параметра (например, атмосферного давления)."""


def unit_kind(unit: str) -> str | None:
    """Возвращает 'temperature', 'pressure_absolute', 'pressure_gauge' или None."""
    if unit in _TEMPERATURE_ALIASES:
        return "temperature"
    if unit in _PRESSURE_ABS_ALIASES:
        return "pressure_absolute"
    if unit in _PRESSURE_GAUGE_ALIASES:
        return "pressure_gauge"
    return None


def to_degC(value: float, unit: str) -> float:
    u = _TEMPERATURE_ALIASES[unit]
    if u == "degC":
        return value
    if u == "degF":
        return (value - 32.0) * 5.0 / 9.0
    if u == "K":
        return value - 273.15
    raise KeyError(unit)


def to_BARa(value: float, unit: str, atmospheric_BARa: float | None) -> float:
    if unit in _PRESSURE_ABS_ALIASES:
        u = _PRESSURE_ABS_ALIASES[unit]
        if u == "BARa":
            return value
        if u == "psia":
            return value * PSI_TO_BAR
        if u == "MPa_abs":
            return value * 10.0
        if u == "kPa_abs":
            return value / 100.0
    if unit in _PRESSURE_GAUGE_ALIASES:
        if atmospheric_BARa is None:
            raise UnitConversionNotConfirmed(
                f"Пересчёт {unit} -> BARa требует подтверждённого атмосферного давления"
            )
        u = _PRESSURE_GAUGE_ALIASES[unit]
        gauge_bar = value * PSI_TO_BAR if u == "psig" else value
        return gauge_bar + atmospheric_BARa
    raise KeyError(unit)
