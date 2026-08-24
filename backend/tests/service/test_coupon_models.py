# tests/service/test_coupon_models.py
"""M4 券模块数据模型与 v024 迁移结构测试。"""

import aiosqlite
import pytest

from app.models.coupon import (
    CouponGrant,
    CouponGrantStatus,
    CouponTemplate,
    CouponTemplateStatus,
    CouponType,
)
from app.models.member import LedgerSource


@pytest.mark.asyncio
async def test_ledger_source_has_local(db: aiosqlite.Connection) -> None:
    """LedgerSource 含 LOCAL 常量。"""
    assert LedgerSource.LOCAL == "local"
    assert LedgerSource.ORDER == "order"


@pytest.mark.asyncio
async def test_coupon_authority_default() -> None:
    """COUPON_AUTHORITY 默认 youzan，可被环境变量覆盖。"""
    from app.config import settings

    assert settings.COUPON_AUTHORITY == "youzan"


@pytest.mark.asyncio
async def test_coupon_template_defaults() -> None:
    """CouponTemplate 默认值符合模板建模。"""
    tpl = CouponTemplate(id="t1", name="满30减5", coupon_type=CouponType.FULL_REDUCTION)
    assert tpl.threshold_fen == 0
    assert tpl.discount_bp == 0
    assert tpl.cap_fen == 0
    assert tpl.status == CouponTemplateStatus.ACTIVE
    assert tpl.source == "youzan"
    assert tpl.scope_json == "{}"


@pytest.mark.asyncio
async def test_coupon_grant_defaults() -> None:
    """CouponGrant 默认渠道与状态。"""
    grant = CouponGrant(
        id="g1", template_id="t1", mobile="13800000000", coupon_code="C001"
    )
    assert grant.channel == "admin"
    assert grant.status == CouponGrantStatus.GRANTED


@pytest.mark.asyncio
async def test_v024_schema_applied(db: aiosqlite.Connection) -> None:
    """v024 后 coupon_inventory 新列与 source 枚举存在，coupon_templates/coupon_grants 建表。"""
    inv_cols = {
        r["name"]
        for r in await db.execute_fetchall("PRAGMA table_info(coupon_inventory)")
    }
    for col in (
        "template_id",
        "valid_from",
        "valid_until",
        "deducted_fen",
        "consumed_at",
        "refunded_at",
    ):
        assert col in inv_cols, f"coupon_inventory 缺列 {col}"
    tpl_cols = {
        r["name"]
        for r in await db.execute_fetchall("PRAGMA table_info(coupon_templates)")
    }
    for col in (
        "id",
        "name",
        "coupon_type",
        "threshold_fen",
        "value_fen",
        "discount_bp",
        "cap_fen",
        "valid_from",
        "valid_until",
        "scope_json",
        "status",
        "source",
    ):
        assert col in tpl_cols, f"coupon_templates 缺列 {col}"
    grant_cols = {
        r["name"] for r in await db.execute_fetchall("PRAGMA table_info(coupon_grants)")
    }
    for col in (
        "id",
        "template_id",
        "mobile",
        "coupon_code",
        "granted_by",
        "channel",
        "audience_json",
        "status",
    ):
        assert col in grant_cols, f"coupon_grants 缺列 {col}"
