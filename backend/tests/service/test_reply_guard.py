"""确定性回复校验门测试。"""

from dataclasses import dataclass

import pytest

from app.models.session import Session
from app.service import reply_guard
from app.service.reply_guard import ReplyGuardContext, apply_reply_guard


class _FakeAnalyticsRepo:
    def __init__(self) -> None:
        self.events: list[dict] = []

    async def add_event(self, **kwargs: object) -> None:
        self.events.append(kwargs)


@dataclass
class _GuardFixture:
    analytics_repo: _FakeAnalyticsRepo
    context: ReplyGuardContext


def _build_context(
    product_titles: tuple[str, ...] = (),
    source_text: str = "",
) -> _GuardFixture:
    analytics_repo = _FakeAnalyticsRepo()
    context = ReplyGuardContext(
        analytics_repo=analytics_repo,
        session=Session(id="session-1", channel="youzan", user_id="buyer-1"),
        user_id="buyer-1",
        channel="youzan",
        product_titles=product_titles,
        source_text=source_text,
    )
    return _GuardFixture(analytics_repo=analytics_repo, context=context)


@pytest.mark.asyncio
async def test_apply_reply_guard_disabled_keeps_reply(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _build_context(source_text="")
    monkeypatch.setattr(reply_guard.settings, "ENABLE_REPLY_GUARD", False)

    guarded = await apply_reply_guard("这款48元", fixture.context)

    assert guarded == "这款48元"
    assert fixture.analytics_repo.events == []


@pytest.mark.asyncio
async def test_apply_reply_guard_allows_supported_price(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _build_context(source_text="草莓蛋糕 48元")
    monkeypatch.setattr(reply_guard.settings, "ENABLE_REPLY_GUARD", True)

    guarded = await apply_reply_guard("草莓蛋糕48元~", fixture.context)

    assert guarded == "草莓蛋糕48元~"
    assert fixture.analytics_repo.events == []


@pytest.mark.asyncio
async def test_apply_reply_guard_masks_unsupported_price(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _build_context(source_text="草莓蛋糕")
    monkeypatch.setattr(reply_guard.settings, "ENABLE_REPLY_GUARD", True)

    guarded = await apply_reply_guard("草莓蛋糕88元~", fixture.context)

    assert guarded is not None
    assert "88元" not in guarded
    assert "具体价格请咨询客服确认" in guarded
    assert fixture.analytics_repo.events[0]["event_type"] == "reply_guard_hit"
    assert "price_check" in str(fixture.analytics_repo.events[0]["meta_data"])


@pytest.mark.asyncio
async def test_apply_reply_guard_rewrites_out_of_scope_product(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _build_context(product_titles=("草莓蛋糕",), source_text="草莓蛋糕 48元")
    monkeypatch.setattr(reply_guard.settings, "ENABLE_REPLY_GUARD", True)

    guarded = await apply_reply_guard("推荐《芒果蛋糕》给您~", fixture.context)

    assert guarded == "推荐该商品给您~"
    assert "product_whitelist" in str(fixture.analytics_repo.events[0]["meta_data"])


@pytest.mark.asyncio
async def test_apply_reply_guard_rewrites_delivery_promise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _build_context(source_text="支持配送")
    monkeypatch.setattr(reply_guard.settings, "ENABLE_REPLY_GUARD", True)

    guarded = await apply_reply_guard("明天12点前送达~", fixture.context)

    assert guarded is not None
    assert "明天12点前送达" not in guarded
    assert "具体配送时间以门店实际排期为准" in guarded
    assert "delivery_promise" in str(fixture.analytics_repo.events[0]["meta_data"])


@pytest.mark.asyncio
async def test_apply_reply_guard_appends_food_safety_notice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _build_context(source_text="坚果蛋糕")
    monkeypatch.setattr(reply_guard.settings, "ENABLE_REPLY_GUARD", True)

    guarded = await apply_reply_guard("这款含坚果成分~", fixture.context)

    assert guarded is not None
    assert "AI 不替您判断能否食用" in guarded
    assert "food_safety" in str(fixture.analytics_repo.events[0]["meta_data"])
