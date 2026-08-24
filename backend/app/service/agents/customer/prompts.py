"""客户机器人 Prompt 组件。"""

from app.models.customer_profile import CustomerProfile
from app.models.knowledge import KnowledgeEntry
from app.service.llm.prompt import build_system_prompt

SESSION_SUMMARY_SECTION_TITLE = "【本会话早期摘要】"


def build_customer_system_prompt(
    knowledge_entries: list[KnowledgeEntry],
    customer_profile: CustomerProfile | None = None,
    conversation_summary_text: str = "",
) -> str:
    """构造客户机器人 system prompt。"""
    return append_conversation_summary(
        build_system_prompt(knowledge_entries, customer_profile),
        conversation_summary_text,
    )


def build_customer_context_messages(
    system_prompt: str, history: list[dict]
) -> list[dict]:
    """构造客户机器人上下文消息。"""
    return [{"role": "system", "content": system_prompt}, *history]


def extract_product_titles(entries: list[KnowledgeEntry]) -> tuple[str, ...]:
    """提取本轮 RAG 命中的商品标题。"""
    return tuple(entry.title for entry in entries if entry.category == "product")


def build_guard_source_text(entries: list[KnowledgeEntry]) -> str:
    """构造回复事实保护输入。"""
    return "\n".join(f"{entry.title}\n{entry.content}" for entry in entries)


def append_conversation_summary(system_prompt: str, summary_text: str) -> str:
    """把会话短期摘要追加到 system prompt。"""
    summary = summary_text.strip()
    if not summary:
        return system_prompt
    return (
        f"{system_prompt}\n\n{SESSION_SUMMARY_SECTION_TITLE}\n"
        f"{summary}\n"
        "以上摘要只用于理解本会话早期上下文；订单、库存、配送、价格仍以工具和知识库为准。"
    )
