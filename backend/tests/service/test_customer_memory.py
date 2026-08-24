"""热路径顾客记忆加载测试。"""

import pytest

from app.models.customer_profile import CustomerProfile
from app.service import customer_memory
from app.service.customer_memory import load_customer_profile


class _FakeProfileRepo:
    def __init__(self, profile: CustomerProfile | None = None) -> None:
        self.profile = profile
        self.calls: list[tuple[str, str]] = []

    async def get(self, channel: str, user_id: str) -> CustomerProfile | None:
        self.calls.append((channel, user_id))
        return self.profile


class _BrokenProfileRepo:
    async def get(self, channel: str, user_id: str) -> CustomerProfile | None:
        raise RuntimeError(f"{channel}:{user_id}")


@pytest.mark.asyncio
async def test_load_customer_profile_disabled_skips_repo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = _FakeProfileRepo()
    monkeypatch.setattr(customer_memory.settings, "ENABLE_CUSTOMER_MEMORY", False)

    profile = await load_customer_profile(repo, "youzan", "buyer-1")

    assert profile is None
    assert repo.calls == []


@pytest.mark.asyncio
async def test_load_customer_profile_enabled_returns_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = CustomerProfile(id="p-1", channel="youzan", user_id="buyer-1")
    repo = _FakeProfileRepo(expected)
    monkeypatch.setattr(customer_memory.settings, "ENABLE_CUSTOMER_MEMORY", True)

    profile = await load_customer_profile(repo, "youzan", "buyer-1")

    assert profile is expected
    assert repo.calls == [("youzan", "buyer-1")]


@pytest.mark.asyncio
async def test_load_customer_profile_error_downgrades_to_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(customer_memory.settings, "ENABLE_CUSTOMER_MEMORY", True)

    profile = await load_customer_profile(_BrokenProfileRepo(), "youzan", "buyer-1")

    assert profile is None
