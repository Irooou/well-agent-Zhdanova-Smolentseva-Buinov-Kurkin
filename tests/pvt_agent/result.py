"""Формат ответа агента (AgentResult) и коды ошибок.

Поля ответа при ошибке (задача 4 участника №4):
  request_id, trace_id      — идентификаторы запроса и журнала
  status                    — итог обработки запроса (см. Status)
  calc_status               — выполнило ли ПО операцию: SUCCESS / NOT_RUN / FAILED (п. 3.5 ТЗ)
  check_status              — инженерная оценка: OK / OUT_OF_TOLERANCE / NOT_ASSESSED (п. 3.5 ТЗ)
  error_code, field, reason — главная ошибка: код, проблемное поле, причина отказа
  errors                    — список всех найденных ошибок
  user_message              — сообщение пользователю
  mcp_tool_called, mcp_tool — был ли вызван MCP-инструмент и какой
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from dataclasses import field as dc_field
from enum import Enum


class Status(str, Enum):
    SUCCESS = "SUCCESS"                             # операция выполнена
    NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"     # пропуск/неоднозначность — нужен ответ пользователя
    REJECTED = "REJECTED"                           # вход некорректен или операция запрещена
    CONFIRMATION_REQUIRED = "CONFIRMATION_REQUIRED" # запись в модель ждёт подтверждения
    SOFTWARE_UNAVAILABLE = "SOFTWARE_UNAVAILABLE"
    LICENSE_BUSY = "LICENSE_BUSY"
    TIMEOUT = "TIMEOUT"
    NO_SOLUTION = "NO_SOLUTION"
    DUPLICATE_REQUEST = "DUPLICATE_REQUEST"         # повтор уже выполненного запроса
    ADAPTER_ERROR = "ADAPTER_ERROR"                 # непредвиденная ошибка адаптера


class CalcStatus(str, Enum):
    SUCCESS = "SUCCESS"
    NOT_RUN = "NOT_RUN"
    FAILED = "FAILED"


class CheckStatus(str, Enum):
    OK = "OK"
    OUT_OF_TOLERANCE = "OUT_OF_TOLERANCE"
    NOT_ASSESSED = "NOT_ASSESSED"   # допуск не утверждён — «в допуске» не утверждаем (п. 3.4 ТЗ)


class ErrorCode(str, Enum):
    MISSING_REQUIRED_FIELD = "MISSING_REQUIRED_FIELD"
    UNIT_MISSING = "UNIT_MISSING"
    UNIT_INVALID = "UNIT_INVALID"
    UNIT_AMBIGUOUS = "UNIT_AMBIGUOUS"
    UNIT_CONVERSION_NOT_CONFIRMED = "UNIT_CONVERSION_NOT_CONFIRMED"
    INVALID_VALUE = "INVALID_VALUE"
    OUT_OF_RANGE = "OUT_OF_RANGE"
    SOFTWARE_UNAVAILABLE = "SOFTWARE_UNAVAILABLE"
    LICENSE_BUSY = "LICENSE_BUSY"
    TIMEOUT = "TIMEOUT"
    NO_SOLUTION = "NO_SOLUTION"
    CONFIRMATION_REQUIRED = "CONFIRMATION_REQUIRED"
    CONFIRMATION_DECLINED = "CONFIRMATION_DECLINED"
    CONFIRMATION_MISMATCH = "CONFIRMATION_MISMATCH"
    DUPLICATE_REQUEST = "DUPLICATE_REQUEST"
    REQUEST_ID_CONFLICT = "REQUEST_ID_CONFLICT"
    INJECTED_INSTRUCTION_IGNORED = "INJECTED_INSTRUCTION_IGNORED"
    ADAPTER_ERROR = "ADAPTER_ERROR"


# Ошибки входа, которые устраняются уточнением пользователя (а не «запрос неверен»)
CLARIFIABLE = {
    ErrorCode.MISSING_REQUIRED_FIELD,
    ErrorCode.UNIT_MISSING,
    ErrorCode.UNIT_AMBIGUOUS,
    ErrorCode.UNIT_CONVERSION_NOT_CONFIRMED,
}


@dataclass
class ErrorItem:
    code: ErrorCode
    field: str | None
    reason: str
    received: object = None
    expected: str | None = None
    source: str | None = None


@dataclass
class AgentResult:
    request_id: str | None
    trace_id: str
    status: Status
    calc_status: CalcStatus
    check_status: CheckStatus = CheckStatus.NOT_ASSESSED
    error_code: ErrorCode | None = None
    field: str | None = None
    reason: str | None = None
    errors: list[ErrorItem] = dc_field(default_factory=list)
    warnings: list[ErrorItem] = dc_field(default_factory=list)
    user_message: str = ""
    mcp_tool_called: bool = False
    mcp_tool: str | None = None
    attempts: int = 0
    change_plan: dict | None = None
    results: dict | None = None
    uses_test_adapter: bool = False

    def set_errors(self, errors: list[ErrorItem]) -> None:
        self.errors = errors
        if errors:
            self.error_code, self.field, self.reason = errors[0].code, errors[0].field, errors[0].reason

    def to_dict(self) -> dict:
        def conv(o):
            if isinstance(o, Enum):
                return o.value
            if isinstance(o, dict):
                return {k: conv(v) for k, v in o.items()}
            if isinstance(o, (list, tuple)):
                return [conv(v) for v in o]
            return o
        return conv(asdict(self))
