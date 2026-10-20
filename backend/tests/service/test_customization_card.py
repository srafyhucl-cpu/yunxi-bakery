"""定制蛋糕结构化需求卡服务测试。"""

from datetime import datetime, timedelta

import aiosqlite
import pytest

from app.service.customization_card import (
    DEFAULT_SWEETNESS,
    REMARK_MAX_LENGTH,
    CustomizationCardService,
)
from app.service.order.fulfillment_dual_track import BEIJING_TIME_ZONE

FIXED_NOW = datetime(2026, 6, 17, 12, 0, tzinfo=BEIJING_TIME_ZONE)


def _service() -> CustomizationCardService:
    """构造使用固定时钟的需求卡服务。"""
    return CustomizationCardService(now_provider=lambda: FIXED_NOW)


def _payload(**overrides: str) -> dict:
    """构造一份完整的需求卡入参。"""
    payload = {
        "size": "8寸",
        "filling": "芒果慕斯",
        "greeting": "生日快乐",
        "accessories": "蜡烛、餐具",
    }
    payload.update(overrides)
    return payload


async def _count_orders(db: aiosqlite.Connection) -> int:
    """统计订单表行数，用于验证需求卡不产生交易副作用。"""
    rows = await db.execute_fetchall("SELECT COUNT(*) FROM orders")
    return int(rows[0][0])


@pytest.mark.parametrize(
    ("field", "message"),
    [
        ("size", "尺寸规格"),
        ("filling", "夹心口味"),
        ("greeting", "祝福语"),
        ("accessories", "配件"),
    ],
)
def test_build_card_rejects_missing_required_field(
    field: str,
    message: str,
) -> None:
    """四要素缺一不可，缺失时抛出中文错误。"""
    payload = _payload()
    payload.pop(field)

    with pytest.raises(ValueError) as exc_info:
        _service().build_card(payload)

    assert message in str(exc_info.value)


def test_build_card_defaults_sweetness_to_store_default() -> None:
    """未填甜度时按门店默认 8 分甜处理。"""
    card = _service().build_card(_payload())

    assert card["sweetness"] == DEFAULT_SWEETNESS


def test_build_card_normalizes_sweetness_alias() -> None:
    """口语甜度写法归一到门店标准表述。"""
    card = _service().build_card(_payload(sweetness="5分"))

    assert card["sweetness"] == "5分甜"


def test_build_card_accepts_expect_time_beyond_four_hours() -> None:
    """晚于四小时的预约时间可以通过校验。"""
    expect_time = (FIXED_NOW + timedelta(hours=5)).strftime("%Y-%m-%d %H:%M")

    card = _service().build_card(_payload(expectTime=expect_time))

    assert card["expectTime"] == expect_time


def test_build_card_rejects_expect_time_within_four_hours() -> None:
    """不足四小时的预约时间必须拒绝，与双轨下单规则保持一致。"""
    expect_time = (FIXED_NOW + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M")

    with pytest.raises(ValueError) as exc_info:
        _service().build_card(_payload(expectTime=expect_time))

    assert "提前" in str(exc_info.value)


def test_build_card_rejects_invalid_expect_time_format() -> None:
    """预约时间格式非法时直接拒绝。"""
    with pytest.raises(ValueError) as exc_info:
        _service().build_card(_payload(expectTime="2026/06/18 10:00"))

    assert "预约时间格式无效" in str(exc_info.value)


def test_build_card_rejects_remark_over_length_limit() -> None:
    """备注超过长度上限时直接拒绝。"""
    with pytest.raises(ValueError) as exc_info:
        _service().build_card(_payload(remark="备" * (REMARK_MAX_LENGTH + 1)))

    assert "备注不能超过" in str(exc_info.value)


def test_build_card_summary_contains_all_core_fields() -> None:
    """摘要要覆盖尺寸、夹心、甜度、祝福语、配件、预约时间与备注。"""
    card = _service().build_card(
        _payload(
            sweetness="3分甜",
            expectTime="2026-06-18 10:00",
            remark="不要草莓装饰",
        )
    )

    summary = card["summary"]
    assert "尺寸：8寸" in summary
    assert "夹心：芒果慕斯" in summary
    assert "甜度：3分甜" in summary
    assert "祝福语：生日快乐" in summary
    assert "配件：蜡烛、餐具" in summary
    assert "预约时间：2026-06-18 10:00" in summary
    assert "备注：不要草莓装饰" in summary


async def test_build_card_does_not_write_database(db: aiosqlite.Connection) -> None:
    """需求卡只做文本化，不落库也不建单。"""
    before = await _count_orders(db)

    _service().build_card(_payload(expectTime="2026-06-18 10:00"))

    assert before == 0
    assert await _count_orders(db) == 0


def test_build_card_summary_marks_unset_fields_as_pending() -> None:
    """未确定的预约时间与备注要显式占位，避免店员误认为已确认。"""
    card = _service().build_card(_payload())

    assert "预约时间：待确认" in card["summary"]
    assert "备注：无" in card["summary"]
