"""客户 graph read-only memory 测试。"""

from types import SimpleNamespace

import pytest

from app.models.customer_profile import CustomerProfile
from app.service.agents.customer.memory import load_customer_memory_block


class _FakeSummaryRepo:
    async def get_active(self, session_id: str) -> object:
        assert session_id == "session-1"
        return SimpleNamespace(summary_text="  需要低糖生日蛋糕  ")


@pytest.mark.asyncio
async def test_load_customer_memory_block_keeps_summary_and_profile() -> None:
    profile = CustomerProfile(
        id="profile-1",
        channel="youzan",
        user_id="buyer-1",
        display_name="林女士",
    )

    memory_block = await load_customer_memory_block(
        summary_repo=_FakeSummaryRepo(),
        session_id="session-1",
        customer_profile=profile,
    )

    assert memory_block.conversation_summary_text == "需要低糖生日蛋糕"
    assert memory_block.customer_profile is profile
    assert memory_block.has_conversation_summary is True
    assert memory_block.has_customer_profile is True


@pytest.mark.asyncio
async def test_load_customer_memory_block_empty_without_sources() -> None:
    memory_block = await load_customer_memory_block(
        summary_repo=None,
        session_id="session-1",
        customer_profile=None,
    )

    assert memory_block.conversation_summary_text == ""
    assert memory_block.customer_profile is None
    assert memory_block.has_conversation_summary is False
    assert memory_block.has_customer_profile is False
