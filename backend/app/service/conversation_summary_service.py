"""客户会话短期摘要生成服务。"""

import json
import re
from dataclasses import dataclass
from functools import lru_cache

from app.exceptions import LLMError
from app.logger import setup_logger
from app.models.conversation_summary import ConversationSummaryCreate
from app.models.message import Message, MessageRole
from app.service.agents.llm import get_langchain_chat_model
from app.service.offline.agent_shared import format_dialog
from app.service.offline.json_utils import parse_json_object
from app.service.privacy_redaction import redact_external_text
from app.service.session_manager import estimate_tokens


logger = setup_logger()

SUMMARY_MAX_CHARS = 800
SUMMARY_LLM_MAX_TOKENS = 512
SOURCE_DIALOG_MAX_CHARS = 6000
PHONE_PATTERN = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
LONG_NUMBER_PATTERN = re.compile(r"(?<![A-Za-z0-9])[A-Z]?\d{10,}(?![A-Za-z0-9])")
ADDRESS_PATTERN = re.compile(
    r"[\u4e00-\u9fff]{2,}(?:省|市|区|县)[\u4e00-\u9fff0-9号楼栋单元室路街弄巷-]{6,}"
)

SUMMARY_SYSTEM_PROMPT = (
    "你是芸熙烘焙客户会话短期摘要助手。只输出 JSON 对象："
    '{"customer_goal":"","confirmed_facts":[],"pending_questions":[],'
    '"service_boundaries":[],"handoff_state":"none"}。'
    "只总结当前会话内对后续回复有帮助的短期上下文；"
    "不要保存长期偏好、生日、纪念日、过敏原、电话、地址、完整订单号或完整交易号；"
    "不要把订单、库存、物流、价格当作事实来源；这些必须由工具或知识库重新确认。"
)
SUMMARY_PARSE_ERROR = "会话摘要结果不是有效 JSON"


@lru_cache(maxsize=1)
def _get_summary_prompt_template():
    """延迟构建会话摘要提示模板，避免模块导入阶段加载重依赖。"""
    from langchain_core.prompts import ChatPromptTemplate

    return ChatPromptTemplate.from_messages(
        [
            ("system", "{system_prompt}"),
            ("user", "{user_content}"),
        ]
    )


@dataclass(frozen=True)
class ConversationSummaryGenerationRequest:
    """生成客户会话短期摘要所需输入。"""

    session_id: str
    channel: str
    user_id: str
    messages: list[Message]
    existing_summary_text: str = ""


async def generate_conversation_summary_draft(
    request: ConversationSummaryGenerationRequest,
) -> ConversationSummaryCreate | None:
    """生成可写入 repository 的会话摘要草稿。"""
    summarizable_messages = _summarizable_messages(request.messages)
    if not summarizable_messages:
        return None

    try:
        content = await _invoke_summary_chain(
            summarizable_messages,
            request.existing_summary_text,
        )
    except LLMError as exc:
        logger.warning("会话摘要生成失败 session=%s err=%s", request.session_id, exc)
        return None

    try:
        payload = parse_json_object(content, SUMMARY_PARSE_ERROR)
        summary_text = _render_summary_text(payload)
        state_json = _build_state_json(payload, summarizable_messages)
    except LLMError as exc:
        logger.warning("会话摘要解析失败 session=%s err=%s", request.session_id, exc)
        return None

    if _should_discard_summary(summary_text, state_json):
        logger.warning(
            "会话摘要含敏感信息或超长，已丢弃 session=%s", request.session_id
        )
        return None

    return ConversationSummaryCreate(
        session_id=request.session_id,
        channel=request.channel,
        user_id=request.user_id,
        summary_text=summary_text,
        state_json=state_json,
        source_message_ids_json=json.dumps(
            [message.id for message in summarizable_messages],
            ensure_ascii=False,
        ),
        source_until_message_id=summarizable_messages[-1].id,
        token_estimate=estimate_tokens(summary_text),
    )


async def _invoke_summary_chain(
    messages: list[Message],
    existing_summary_text: str,
) -> str:
    """通过统一 LangChain Runnable 生成会话摘要文本。"""
    model = get_langchain_chat_model(provider="mimo", temperature=0).bind(
        max_tokens=SUMMARY_LLM_MAX_TOKENS
    )
    from langchain_core.output_parsers import StrOutputParser

    chain = _get_summary_prompt_template() | model | StrOutputParser()
    summary_messages = _build_summary_messages(messages, existing_summary_text)
    try:
        return await chain.ainvoke(
            {
                "system_prompt": SUMMARY_SYSTEM_PROMPT,
                "user_content": redact_external_text(summary_messages[1]["content"]),
            }
        )
    except Exception as exc:
        raise LLMError("会话摘要 LLM 调用失败") from exc


def _build_summary_messages(
    messages: list[Message],
    existing_summary_text: str,
) -> list[dict[str, str]]:
    existing_section = (
        f"已有短期摘要：\n{existing_summary_text}\n\n" if existing_summary_text else ""
    )
    dialog = format_dialog(messages)[-SOURCE_DIALOG_MAX_CHARS:]
    return [
        {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": existing_section + "请总结以下客户会话：\n" + dialog,
        },
    ]


def _summarizable_messages(messages: list[Message]) -> list[Message]:
    return [
        message
        for message in messages
        if _role_value(message.role)
        in {MessageRole.USER.value, MessageRole.ASSISTANT.value}
    ]


def _render_summary_text(payload: dict) -> str:
    customer_goal = _string_value(payload.get("customer_goal"))
    confirmed_facts = _string_list(payload.get("confirmed_facts"))
    pending_questions = _string_list(payload.get("pending_questions"))
    service_boundaries = _string_list(payload.get("service_boundaries"))
    handoff_state = _string_value(payload.get("handoff_state")) or "none"

    lines = [
        f"客户目标：{customer_goal}" if customer_goal else "",
        _joined_line("已确认", confirmed_facts),
        _joined_line("待确认", pending_questions),
        _joined_line("服务边界", service_boundaries),
        f"转人工状态：{handoff_state}",
    ]
    return "\n".join(line for line in lines if line).strip()


def _build_state_json(payload: dict, messages: list[Message]) -> str:
    state = {
        "customer_goal": _string_value(payload.get("customer_goal")),
        "confirmed_facts": _string_list(payload.get("confirmed_facts")),
        "pending_questions": _string_list(payload.get("pending_questions")),
        "service_boundaries": _string_list(payload.get("service_boundaries")),
        "handoff_state": _string_value(payload.get("handoff_state")) or "none",
        "source_scope": {
            "from_message_id": messages[0].id,
            "until_message_id": messages[-1].id,
        },
    }
    return json.dumps(state, ensure_ascii=False, separators=(",", ":"))


def _should_discard_summary(summary_text: str, state_json: str) -> bool:
    if not summary_text or len(summary_text) > SUMMARY_MAX_CHARS:
        return True
    observable_text = summary_text + "\n" + state_json
    return bool(
        PHONE_PATTERN.search(observable_text)
        or LONG_NUMBER_PATTERN.search(observable_text)
        or ADDRESS_PATTERN.search(observable_text)
    )


def _string_value(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _joined_line(label: str, values: list[str]) -> str:
    if not values:
        return ""
    return f"{label}：" + "；".join(values)


def _role_value(role: object) -> str:
    return str(getattr(role, "value", role))
