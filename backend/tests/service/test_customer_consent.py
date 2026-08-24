"""顾客 consent service 测试。"""

import pytest

from app.service.customer_memory import load_customer_profile


class _ProfileRepo:
    def __init__(self, status: str) -> None:
        self.status = status
        self.read_count = 0

    async def get_consent_status(self, channel: str, user_id: str) -> str:
        return self.status

    async def get(self, channel: str, user_id: str):
        self.read_count += 1
        return object()


@pytest.mark.asyncio
async def test_customer_memory_does_not_read_profile_without_grant(monkeypatch) -> None:
    from app.service import customer_memory

    monkeypatch.setattr(customer_memory.settings, "ENABLE_CUSTOMER_MEMORY", True)
    repo = _ProfileRepo("unknown")

    assert await load_customer_profile(repo, "miniapp", "user-1") is None
    assert repo.read_count == 0


@pytest.mark.asyncio
async def test_customer_memory_reads_profile_after_grant(monkeypatch) -> None:
    from app.service import customer_memory

    monkeypatch.setattr(customer_memory.settings, "ENABLE_CUSTOMER_MEMORY", True)
    repo = _ProfileRepo("granted")

    assert await load_customer_profile(repo, "miniapp", "user-1") is not None
    assert repo.read_count == 1
