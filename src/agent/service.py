"""Обработка текстовых запросов PVT-агента."""

from uuid import uuid4

from src.agent.parser import parse_request
from src.agent.loop import PVTAgent
from src.agent.mcp_adapter import McpPVTPAdapter


class AgentService:

    def __init__(self, test_mode: bool = False):

        self.agent = PVTAgent(
            adapter=McpPVTPAdapter(
                test_mode=test_mode
            )
        )

    def handle_text(self, user_text: str) -> dict:

        request_id = str(uuid4())

        try:
            request = parse_request(
                user_text,
                request_id=request_id,
            )

        except RuntimeError:

            return {
                "request_id": request_id,
                "status": "FAILED",
                "error_code": "LLM_PARSE_FAILED",
                "calc_status": "NOT_RUN",
                "check_status": "NOT_ASSESSED",
                "mcp_tool_called": False,
                "user_message": (
                    "Не удалось обработать текст "
                    "запроса с помощью LLM. "
                    "Расчёт не запускался."
                ),
            }

        return self.agent.handle(request).to_dict()