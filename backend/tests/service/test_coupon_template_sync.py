# tests/service/test_coupon_template_sync.py
"""券模板仓储与有赞模板同步解析测试。"""

import aiosqlite
import pytest

from app.models.coupon import CouponGrant, CouponTemplate, CouponType
from app.repository.coupon_grant_repo import CouponGrantRepo
from app.repository.coupon_template_repo import CouponTemplateRepo
from app.service.coupon.template_sync import (
    extract_template_fields,
    parse_youzan_template,
)


def _detail() -> dict:
    return {
        "coupon_group_id": "cg_001",
        "title": "满30减5",
        "coupon_type": "FULL_REDUCTION",
        "threshold": "30",
        "value": "5",
        "discount": "0",
        "valid_start_time": "2026-08-01 00:00:00",
        "valid_end_time": "2026-09-30 23:59:59",
    }


@pytest.mark.asyncio
async def test_parse_youzan_template_full_reduction(db: aiosqlite.Connection) -> None:
    """满减券详情解析为模板字段。"""
    tpl = parse_youzan_template(_detail())
    assert tpl.id == "cg_001"
    assert tpl.coupon_type == CouponType.FULL_REDUCTION
    assert tpl.threshold_fen == 3000
    assert tpl.value_fen == 500
    assert tpl.valid_from == "2026-08-01"
    assert tpl.valid_until == "2026-09-30"


@pytest.mark.asyncio
async def test_parse_youzan_template_empty_detail(db: aiosqlite.Connection) -> None:
    """详情为空返回默认模板，不抛异常。"""
    tpl = parse_youzan_template({})
    assert tpl.id == ""
    assert tpl.coupon_type == ""


@pytest.mark.asyncio
async def test_template_repo_upsert_and_list(db: aiosqlite.Connection) -> None:
    """模板 upsert 幂等，list_active 生效。"""
    repo = CouponTemplateRepo(db)
    await repo.upsert_from_youzan(
        CouponTemplate(
            id="cg_001", name="满30减5", coupon_type=CouponType.FULL_REDUCTION
        )
    )
    await repo.upsert_from_youzan(
        CouponTemplate(
            id="cg_001", name="满30减5改", coupon_type=CouponType.FULL_REDUCTION
        )
    )
    rows = await repo.list_active()
    assert len(rows) == 1
    assert rows[0]["name"] == "满30减5改"


@pytest.mark.asyncio
async def test_extract_template_fields(db: aiosqlite.Connection) -> None:
    """从客户券行与详情提取回填字段。"""
    coupon = {"coupon_group_id": "cg_001", "status": "TAKE"}
    fields = extract_template_fields(coupon, _detail())
    assert fields["template_id"] == "cg_001"
    assert fields["valid_from"] == "2026-08-01"
    assert fields["valid_until"] == "2026-09-30"


def test_parse_discount_bp_semantics() -> None:
    """折扣解析确定性：9折/9.5折/0.9 小数/0 空值。"""
    from app.service.coupon.template_sync import _parse_discount_bp

    assert _parse_discount_bp(9) == 9000
    assert _parse_discount_bp("9.5") == 9500
    assert _parse_discount_bp(0.9) == 9000
    assert _parse_discount_bp("0") == 0
    assert _parse_discount_bp("") == 0
    assert _parse_discount_bp(90) == 0  # >=10 视为歧义输入，不猜测


@pytest.mark.asyncio
async def test_parse_youzan_template_discount(db: aiosqlite.Connection) -> None:
    """折扣券详情解析为 discount_bp 与 cap_fen。"""
    tpl = parse_youzan_template(
        {**_detail(), "coupon_type": "DISCOUNT", "discount": "9", "cap": "3"}
    )
    assert tpl.coupon_type == CouponType.DISCOUNT
    assert tpl.discount_bp == 9000
    assert tpl.cap_fen == 300


@pytest.mark.asyncio
async def test_coupon_grant_repo_insert(db: aiosqlite.Connection) -> None:
    """发券记录写入与按手机号查询。"""
    repo = CouponGrantRepo(db)
    await repo.insert(
        CouponGrant(
            id="g1", template_id="cg_001", mobile="13800000000", coupon_code="C001"
        )
    )
    rows = await repo.list_by_mobile("13800000000")
    assert len(rows) == 1
    assert rows[0]["coupon_code"] == "C001"
