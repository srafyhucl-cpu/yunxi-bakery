# 测试文件：tests/service/test_coupon_template_sync.py
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
    """折扣解析确定性：9折/9.5折/0.9 小数/百分比/0 空值。"""
    from app.service.coupon.template_sync import _parse_discount_bp

    assert _parse_discount_bp(9) == 9000
    assert _parse_discount_bp("9.5") == 9500
    assert _parse_discount_bp(0.9) == 9000
    assert _parse_discount_bp("0") == 0
    assert _parse_discount_bp("") == 0
    # 有赞官方文档口径：折扣字段 88 即「8.8折」（应付 88%），对应 8800/10000。
    # 该形态在本店 21 个券模板中没有实例（preferential_type 无 2），但口径明确，
    # 不按「>=10 视为歧义」处理，否则折扣券会被永久判为不可用。
    assert _parse_discount_bp(88) == 8800
    assert _parse_discount_bp(90) == 9000


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


def _youzan_group_detail() -> dict:
    """有赞 `youzan.ump.coupon.detail.get` 3.0.0 的真实响应（店铺 32035241）。

    2026-10-20 生产实测：响应是**扁平** CouponGroup，`denominations`（面额）与
    `condition`（满额）单位都是分，时间字段是毫秒时间戳。
    """
    return {
        "id": 32035241,
        "kdt_id": 131707202,
        "group_type": 7,
        "title": "20元优惠卷",
        "preferential_type": 1,
        "denominations": 2000,
        "condition": 5000,
        "discount": 0,
        "date_type": 2,
        "fixed_term": 30,
        "valid_start_time": 1727340981000,
        "valid_end_time": 4102416000000,
        "range_type": "all",
    }


def test_parse_youzan_template_from_real_youzan_detail() -> None:
    """真实有赞券详情必须解析出面额/门槛/有效期（分 + 毫秒时间戳）。"""
    tpl = parse_youzan_template(_youzan_group_detail())
    assert tpl.id == "32035241"
    assert tpl.name == "20元优惠卷"
    assert tpl.coupon_type == CouponType.FULL_REDUCTION
    # 面额 20 元 = 2000 分；满额 50 元 = 5000 分
    assert tpl.value_fen == 2000
    assert tpl.threshold_fen == 5000
    # 毫秒时间戳必须换算成日期，不能截断成无意义数字
    assert tpl.valid_from == "2024-09-26"
    assert tpl.valid_until == "2100-01-01"


def test_parse_youzan_template_no_threshold_coupon() -> None:
    """无门槛代金券：有赞 `condition=0` → NO_THRESHOLD。"""
    tpl = parse_youzan_template(
        {
            "id": 30506332,
            "title": "分享好礼代金券",
            "preferential_type": 1,
            "denominations": 100,
            "condition": 0,
        }
    )
    assert tpl.coupon_type == CouponType.NO_THRESHOLD
    assert tpl.value_fen == 100
    assert tpl.threshold_fen == 0


def test_parse_youzan_template_unmappable_types_are_not_discounted() -> None:
    """运费抵扣券/指定商品兑换券无法映射时必须留空，不得按错误金额抵扣。"""
    # preferential_type=5 运费抵扣券：无面额
    shipping = parse_youzan_template(
        {
            "id": 32035320,
            "title": "运费抵扣券",
            "preferential_type": 5,
            "denominations": None,
            "condition": 0,
        }
    )
    assert shipping.coupon_type == ""
    assert shipping.value_fen == 0
    # preferential_type=3 指定商品兑换券：无面额
    exchange = parse_youzan_template(
        {
            "id": 31492272,
            "title": "口味罐子(随机口味）",
            "preferential_type": 3,
            "denominations": 0,
            "condition": 0,
        }
    )
    assert exchange.coupon_type == ""
    assert exchange.value_fen == 0


def test_extract_template_fields_prefers_coupon_level_validity() -> None:
    """券自身有效期优先于模板有效期（防已过期券被当成可用券）。"""
    coupon = {
        "coupon_group_id": "32035241",
        "valid_start_at": 1789574400000,
        "expire_at": 1790179199000,
    }
    fields = extract_template_fields(coupon, _youzan_group_detail())
    assert fields["template_id"] == "32035241"
    # 券级有效期（2026-09-17 ~ 2026-09-23，即「领券当日起 7 天内有效」）
    # 必须覆盖模板的活动有效期（2024-09-26 ~ 2100-01-01）
    assert fields["valid_from"] == "2026-09-17"
    assert fields["valid_until"] == "2026-09-23"
