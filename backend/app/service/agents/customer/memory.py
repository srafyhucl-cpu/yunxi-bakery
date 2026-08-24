"""客户机器人 read-only memory 适配器。"""

from dataclasses import dataclass

from app.models.customer_profile import CustomerProfile
from app.service.conversation_summary_memory import (
    ConversationSummaryReader,
    load_active_conversation_summary_text,
)


@dataclass(frozen=True)
class CustomerMemoryBlock:
    """客户 graph 当前轮可读记忆输入。"""

    conversation_summary_text: str = ""
    customer_profile: CustomerProfile | None = None

    @property
    def has_conversation_summary(self) -> bool:
        return bool(self.conversation_summary_text.strip())

    @property
    def has_customer_profile(self) -> bool:
        return self.customer_profile is not None


async def load_customer_memory_block(
    *,
    summary_repo: ConversationSummaryReader | None,
    session_id: str,
    customer_profile: CustomerProfile | None,
) -> CustomerMemoryBlock:
    """加载客户 graph 本轮只读 memory block。"""
    conversation_summary_text = await load_active_conversation_summary_text(
        summary_repo,
        session_id,
    )
    return CustomerMemoryBlock(
        conversation_summary_text=conversation_summary_text,
        customer_profile=customer_profile,
    )
