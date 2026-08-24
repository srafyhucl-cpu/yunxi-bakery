"""客户机器人 LangGraph 辅助函数。"""

from collections.abc import Awaitable, Callable
import json

from app.service.agents.customer.constants import (
    LLM_FAILURE_REASON_TOOL_ROUND_LIMIT,
    TRANSFER_TOOL_DEFAULT_REASON,
    TRANSFER_TOOL_ERROR_MESSAGE,
    TRANSFER_TOOL_SUCCESS_MESSAGE,
)
from app.service.agents.customer.tool_messages import ToolExecutionContext
from app.service.agents.messages import message_content, message_role
from app.service.llm.constants import LLM_FAILURE_REASON_KEY
from app.service.chat_transfer import HumanTransferContext, request_human_transfer


def build_transfer_handler(
    tool_context: ToolExecutionContext,
) -> Callable[[str], Awaitable[str]]:
    """构造 LangChain 转人工工具处理器。"""

    async def transfer_handler(reason: str) -> str:
        transfer_created = await request_human_transfer(
            HumanTransferContext(
                session=tool_context.session,
                user_id=tool_context.session.user_id,
                reason=reason or TRANSFER_TOOL_DEFAULT_REASON,
                history_text=tool_context.history_text,
                transfer_mgr=tool_context.transfer_mgr,
                session_repo=tool_context.session_repo,
            )
        )
        if transfer_created:
            return json.dumps(
                {
                    "status": "success",
                    "message": TRANSFER_TOOL_SUCCESS_MESSAGE,
                },
                ensure_ascii=False,
            )
        return json.dumps(
            {"status": "error", "message": TRANSFER_TOOL_ERROR_MESSAGE},
            ensure_ascii=False,
        )

    return transfer_handler


def record_tool_rounds(timing: dict | None, tool_round: int) -> None:
    """记录客户机器人工具轮次。"""
    if timing is not None:
        timing["tool_rounds"] = tool_round


def record_tool_round_limit(timing: dict | None) -> None:
    """记录客户机器人工具轮次超限。"""
    if timing is not None:
        timing[LLM_FAILURE_REASON_KEY] = LLM_FAILURE_REASON_TOOL_ROUND_LIMIT


def extend_guard_source_with_tool_outputs(
    timing: dict | None,
    messages: list[object],
) -> None:
    """把工具输出追加到回复 guard 的事实输入。"""
    if timing is None:
        return
    tool_outputs = [
        str(message_content(message))
        for message in messages
        if message_role(message) == "tool"
    ]
    if tool_outputs:
        existing = str(timing.get("guard_source_text") or "")
        timing["guard_source_text"] = "\n".join([existing, *tool_outputs]).strip()
