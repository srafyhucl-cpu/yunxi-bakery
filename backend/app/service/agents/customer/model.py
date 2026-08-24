"""客户机器人 LangChain 模型调用适配。"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, cast
import time

from app.config import settings
from app.logger import setup_logger
from app.service.agents.llm import get_langchain_chat_model
from app.service.agents.observability import get_agent_tracing_config
from app.service.privacy_redaction import redact_external_langchain_messages
from app.service.llm.constants import (
    LLM_FAILURE_REASON_API_ERROR,
    LLM_FAILURE_REASON_KEY,
    LLM_FAILURE_REASON_RESPONSE_PARSE,
)
from app.service.llm.provider import LLMProvider, select_llm_model

logger = setup_logger()


@dataclass(frozen=True)
class CustomerModelRequest:
    """客户模型单次请求上下文。"""

    messages: list[Any]
    tools: list[Any]
    timing: dict | None
    first_llm_started_at: float | None
    has_image: bool
    fallback_reply: str
    failure_alerter: Callable[[str], Awaitable[None]]


@dataclass(frozen=True)
class CustomerModelResult:
    """客户模型单次返回结果。"""

    message: Any | None
    finish_reason: str
    model_name: str = ""
    fallback_reply: str | None = None
    first_llm_started_at: float | None = None


async def request_customer_model_with_tools(
    request: CustomerModelRequest,
) -> CustomerModelResult:
    """通过 LangChain chat model 请求客户回复。"""
    first_llm_started_at = _ensure_started_at(request.first_llm_started_at)
    model_name = select_llm_model(request.has_image) or settings.MIMO_CHAT_MODEL
    try:
        message = await _bound_model(request, model_name).ainvoke(
            redact_external_langchain_messages(request.messages),
            config=_build_runnable_config(request),
        )
    except Exception as exc:
        _record_failure_reason(request.timing, LLM_FAILURE_REASON_API_ERROR)
        logger.error("客户 LangChain 模型调用失败，返回兜底回复: %s", exc)
        await request.failure_alerter("LLMError: customer graph 返回兜底回复")
        return _fallback_result(
            request.fallback_reply, first_llm_started_at, model_name
        )

    _record_latency(request.timing, first_llm_started_at)
    try:
        finish_reason = _finish_reason(message)
    except (AttributeError, TypeError) as exc:
        _record_failure_reason(request.timing, LLM_FAILURE_REASON_RESPONSE_PARSE)
        logger.error("客户 LangChain 模型响应解析失败，返回兜底回复: %s", exc)
        await request.failure_alerter(f"LLM 响应解析失败: {exc}")
        return _fallback_result(
            request.fallback_reply, first_llm_started_at, model_name
        )

    return CustomerModelResult(
        message=message,
        finish_reason=finish_reason,
        model_name=model_name,
        first_llm_started_at=first_llm_started_at,
    )


def _bound_model(request: CustomerModelRequest, model_name: str) -> Any:
    provider: LLMProvider = "mimo" if "mimo" in model_name.lower() else "deepseek"
    return get_langchain_chat_model(provider=provider, model=model_name).bind_tools(
        request.tools
    )


def _build_runnable_config(request: CustomerModelRequest) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        get_agent_tracing_config().to_runnable_config(
            run_name="customer_model_with_tools",
            tags=("customer", "model"),
            metadata={
                "has_image": request.has_image,
                "tool_count": len(request.tools),
            },
        ),
    )


def _finish_reason(message: Any) -> str:
    metadata = getattr(message, "response_metadata", {}) or {}
    finish_reason = metadata.get("finish_reason")
    if finish_reason:
        return str(finish_reason)
    return "tool_calls" if getattr(message, "tool_calls", None) else "stop"


def _ensure_started_at(first_llm_started_at: float | None) -> float:
    if first_llm_started_at is not None:
        return first_llm_started_at
    return time.monotonic()


def _record_latency(timing: dict | None, first_llm_started_at: float) -> None:
    if timing is not None and "llm_ms" not in timing:
        timing["llm_ms"] = round((time.monotonic() - first_llm_started_at) * 1000)


def _record_failure_reason(timing: dict | None, reason: str) -> None:
    if timing is not None:
        timing[LLM_FAILURE_REASON_KEY] = reason


def _fallback_result(
    fallback_reply: str,
    first_llm_started_at: float,
    model_name: str,
) -> CustomerModelResult:
    return CustomerModelResult(
        message=None,
        finish_reason="fallback",
        model_name=model_name,
        fallback_reply=fallback_reply,
        first_llm_started_at=first_llm_started_at,
    )
