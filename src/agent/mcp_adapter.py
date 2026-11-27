"""Связь основной логики агента с MCP-сервером."""

from src.agent.adapter import (
    PVTPAdapter,
    SoftwareUnavailableError,
    LicenseBusyError,
    NoSolutionError,
)
from src.agent.tools import McpToolGateway


class McpPVTPAdapter(PVTPAdapter):

    def __init__(self, test_mode: bool = False):
        self.is_test_adapter = test_mode
        self.gateway = McpToolGateway(
            test_mode=test_mode
        )

    def run_experiment(
        self,
        model_id: str,
        args: dict,
    ) -> dict:

        if model_id != "исходная_модель":
            raise ValueError("Модель не разрешена.")

        experiment = args["type"]

        if experiment not in ("PSAT", "CCE", "CVD"):
            raise NotImplementedError(
                f"Эксперимент {experiment} пока "
                "не поддерживается MCP-сервером."
            )

        arguments = {
            "model": {
                "path": "PVT/исходная_модель.xlsx"
            },
            "stream": args["stream"],
            "experiment": experiment,
            "temperature": {
                "value": args["temperature_degC"],
                "unit": "degC",
            },
            "pressures": [
                {
                    "value": pressure,
                    "unit": "BARa",
                }
                for pressure in args.get(
                    "pressure_steps_BARa", []
                )
            ],
        }

        response = self.gateway.call_tool(
            "run_experiment",
            arguments,
        )

        status = response.get("status")
        message = response.get(
            "message",
            str(response.get("errors", status)),
        )

        if status == "SUCCESS":
            return {
                **response["result"],
                "mcp_trace_id": response["trace_id"],
            }

        if status in (
            "SOFTWARE_UNAVAILABLE",
            "NOT_CONFIGURED",
        ):
            raise SoftwareUnavailableError(message)

        if status == "LICENSE_BUSY":
            raise LicenseBusyError(message)

        if status == "NO_SOLUTION":
            raise NoSolutionError(message)

        if status == "TIMEOUT":
            raise TimeoutError(message)

        raise RuntimeError(
            f"MCP: {status}. {message}"
        )

    def apply_changes(
        self,
        model_id: str,
        plan: dict,
    ) -> dict:

        raise NotImplementedError(
            "Изменение модели через MCP "
            "пока не реализовано."
        )