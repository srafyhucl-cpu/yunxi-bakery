"""
YouzanProductRepo / YouzanOrderRepo 数据访问层单元测试。

覆盖：upsert 写入、get 查询、时序防线（旧时间戳不覆写）、软下架。
"""

import aiosqlite
import pytest

from app.models.employee_agent import OrderQueryKind, OrderQueryPlan
from app.models.order import YouzanOrderData
from app.repository.youzan_order_repo import YouzanOrderRepo
from app.repository.youzan_repo import YouzanProductRepo

_TS_OLD = "2026-01-01 00:00:00"
_TS_NEW = "2026-06-01 00:00:00"


@pytest.fixture
def product_repo(db: aiosqlite.Connection) -> YouzanProductRepo:
    return YouzanProductRepo(db)


@pytest.fixture
def order_repo(db: aiosqlite.Connection) -> YouzanOrderRepo:
    return YouzanOrderRepo(db)


# ───────────── YouzanProductRepo ─────────────


async def test_product_get_by_id_returns_none_when_missing(
    product_repo: YouzanProductRepo,
) -> None:
    """不存在的商品 ID 应返回 None。"""
    assert await product_repo.get_by_id(99999) is None


async def test_product_upsert_and_get_by_id(product_repo: YouzanProductRepo) -> None:
    """写入商品后可按 item_id 读回完整数据。"""
    await product_repo.upsert_product(
        item_id=1001,
        title="草莓蛋糕",
        alias="cake-strawberry",
        price_fen=18800,
        stock=10,
        image="https://img/1.jpg",
        is_active=1,
        updated_at=_TS_NEW,
    )
    row = await product_repo.get_by_id(1001)

    assert row is not None
    assert row["title"] == "草莓蛋糕"
    assert row["price_fen"] == 18800
    assert row["alias"] == "cake-strawberry"


async def test_product_get_by_alias(product_repo: YouzanProductRepo) -> None:
    """写入商品后可按 alias 读回。"""
    await product_repo.upsert_product(
        item_id=1002,
        title="芒果蛋糕",
        alias="cake-mango",
        price_fen=22800,
        stock=5,
        image="",
        is_active=1,
        updated_at=_TS_NEW,
    )
    row = await product_repo.get_by_alias("cake-mango")

    assert row is not None
    assert row["item_id"] == 1002


async def test_product_upsert_newer_timestamp_overwrites(
    product_repo: YouzanProductRepo,
) -> None:
    """新时间戳的 upsert 应覆盖旧数据。"""
    await product_repo.upsert_product(
        item_id=1003,
        title="旧名称",
        alias="cake-old",
        price_fen=10000,
        stock=3,
        image="",
        is_active=1,
        updated_at=_TS_OLD,
    )
    await product_repo.upsert_product(
        item_id=1003,
        title="新名称",
        alias="cake-old",
        price_fen=12000,
        stock=3,
        image="",
        is_active=1,
        updated_at=_TS_NEW,
    )
    row = await product_repo.get_by_id(1003)

    assert row is not None
    assert row["title"] == "新名称"
    assert row["price_fen"] == 12000


async def test_product_upsert_older_timestamp_does_not_overwrite(
    product_repo: YouzanProductRepo,
) -> None:
    """旧时间戳的 upsert 不应覆盖新数据（时序防线）。"""
    await product_repo.upsert_product(
        item_id=1004,
        title="当前名称",
        alias="cake-guard",
        price_fen=15000,
        stock=2,
        image="",
        is_active=1,
        updated_at=_TS_NEW,
    )
    await product_repo.upsert_product(
        item_id=1004,
        title="过时推送",
        alias="cake-guard",
        price_fen=9999,
        stock=2,
        image="",
        is_active=1,
        updated_at=_TS_OLD,
    )
    row = await product_repo.get_by_id(1004)

    assert row is not None
    assert row["title"] == "当前名称"
    assert row["price_fen"] == 15000


async def test_product_delete_soft_deactivates(product_repo: YouzanProductRepo) -> None:
    """delete_product 应将 is_active 置 0（软下架），不物理删除。"""
    await product_repo.upsert_product(
        item_id=1005,
        title="待下架",
        alias="cake-delete",
        price_fen=8800,
        stock=1,
        image="",
        is_active=1,
        updated_at=_TS_OLD,
    )
    await product_repo.delete_product(item_id=1005, updated_at=_TS_NEW)

    row = await product_repo.get_by_id(1005)
    assert row is not None
    assert row["is_active"] == 0


# ───────────── YouzanOrderRepo ─────────────


async def test_order_get_by_order_no_returns_none_when_missing(
    order_repo: YouzanOrderRepo,
) -> None:
    """不存在的订单号应返回 None。"""
    assert await order_repo.get_by_order_no("NO_EXIST_999") is None


async def test_order_upsert_and_get(order_repo: YouzanOrderRepo) -> None:
    """写入订单后可按订单号读回完整数据。"""
    await order_repo.upsert_order(
        YouzanOrderData(
            order_no="E202600001",
            buyer_id="buyer_aaa",
            status="TRADE_PAID",
            amount_fen=18800,
            product_titles="草莓蛋糕 x 1",
            total_quantity=1,
            created_at=_TS_NEW,
            updated_at=_TS_NEW,
        )
    )
    row = await order_repo.get_by_order_no("E202600001")

    assert row is not None
    assert row["status"] == "TRADE_PAID"
    assert row["amount_fen"] == 18800
    assert row["buyer_id"] == "buyer_aaa"


async def test_order_upsert_newer_timestamp_overwrites(
    order_repo: YouzanOrderRepo,
) -> None:
    """新时间戳的 upsert 应覆盖旧订单状态。"""
    await order_repo.upsert_order(
        YouzanOrderData(
            order_no="E202600002",
            buyer_id="buyer_bbb",
            status="TRADE_PAID",
            amount_fen=10000,
            product_titles="芒果蛋糕 x 1",
            total_quantity=1,
            created_at=_TS_OLD,
            updated_at=_TS_OLD,
        )
    )
    await order_repo.upsert_order(
        YouzanOrderData(
            order_no="E202600002",
            buyer_id="buyer_bbb",
            status="TRADE_SUCCESS",
            amount_fen=10000,
            logistics_no="SF1234567890",
            logistics_status="已签收",
            product_titles="芒果蛋糕 x 1",
            total_quantity=1,
            created_at=_TS_OLD,
            updated_at=_TS_NEW,
        )
    )
    row = await order_repo.get_by_order_no("E202600002")

    assert row is not None
    assert row["status"] == "TRADE_SUCCESS"
    assert row["logistics_no"] == "SF1234567890"


async def test_order_upsert_older_timestamp_does_not_overwrite(
    order_repo: YouzanOrderRepo,
) -> None:
    """旧时间戳的 upsert 不应覆盖新订单数据（时序防线）。"""
    await order_repo.upsert_order(
        YouzanOrderData(
            order_no="E202600003",
            buyer_id="buyer_ccc",
            status="TRADE_SUCCESS",
            amount_fen=22000,
            logistics_no="YT9999",
            logistics_status="已签收",
            product_titles="提拉米苏 x 2",
            total_quantity=2,
            created_at=_TS_OLD,
            updated_at=_TS_NEW,
        )
    )
    await order_repo.upsert_order(
        YouzanOrderData(
            order_no="E202600003",
            buyer_id="buyer_ccc",
            status="TRADE_PAID",
            amount_fen=22000,
            product_titles="提拉米苏 x 2",
            total_quantity=2,
            created_at=_TS_OLD,
            updated_at=_TS_OLD,
        )
    )
    row = await order_repo.get_by_order_no("E202600003")

    assert row is not None
    assert row["status"] == "TRADE_SUCCESS"
    assert row["logistics_no"] == "YT9999"


async def test_order_search_matches_order_no_and_product_title(
    order_repo: YouzanOrderRepo,
) -> None:
    """订单搜索应覆盖订单号和商品标题。"""
    await order_repo.upsert_order(
        YouzanOrderData(
            order_no="E202600004",
            buyer_id="buyer_ddd",
            status="TRADE_PAID",
            amount_fen=26800,
            product_titles="草莓蛋糕 x 1",
            total_quantity=1,
            created_at=_TS_NEW,
            updated_at=_TS_NEW,
        )
    )
    await order_repo.upsert_order(
        YouzanOrderData(
            order_no="E202600005",
            buyer_id="buyer_eee",
            status="TRADE_PAID",
            amount_fen=19800,
            product_titles="巧克力卷 x 1",
            total_quantity=1,
            created_at=_TS_NEW,
            updated_at=_TS_NEW,
        )
    )

    title_rows = await order_repo.search_orders("草莓", limit=5)
    order_no_rows = await order_repo.search_orders("E202600005", limit=5)

    assert [row["order_no"] for row in title_rows] == ["E202600004"]
    assert [row["order_no"] for row in order_no_rows] == ["E202600005"]


async def test_order_search_matches_buyer_and_delivery_fields(
    order_repo: YouzanOrderRepo,
) -> None:
    """订单搜索应覆盖买家标识和配送字段。"""
    await order_repo.upsert_order(
        YouzanOrderData(
            order_no="E202600006",
            buyer_id="buyer_phone_13812345678",
            status="TRADE_PAID",
            amount_fen=32800,
            product_titles="生日蛋糕 x 1",
            total_quantity=1,
            delivery_city="上海市",
            delivery_district="浦东新区",
            delivery_time="2026-07-03 18:00",
            outer_user_id="outer_customer_001",
            order_items_json='[{"title":"生日蛋糕"}]',
            created_at=_TS_NEW,
            updated_at=_TS_NEW,
        )
    )

    buyer_rows = await order_repo.search_orders("13812345678", limit=5)
    district_rows = await order_repo.search_orders("浦东", limit=5)
    outer_rows = await order_repo.search_orders("outer_customer", limit=5)

    assert [row["order_no"] for row in buyer_rows] == ["E202600006"]
    assert [row["order_no"] for row in district_rows] == ["E202600006"]
    assert [row["order_no"] for row in outer_rows] == ["E202600006"]


async def test_order_search_respects_limit(order_repo: YouzanOrderRepo) -> None:
    """订单搜索应尊重 limit。"""
    for index in range(3):
        await order_repo.upsert_order(
            YouzanOrderData(
                order_no=f"E20260010{index}",
                buyer_id=f"buyer_limit_{index}",
                status="TRADE_PAID",
                amount_fen=10000 + index,
                product_titles="限量蛋糕 x 1",
                total_quantity=1,
                created_at=_TS_NEW,
                updated_at=_TS_NEW,
            )
        )

    rows = await order_repo.search_orders("限量蛋糕", limit=2)

    assert len(rows) == 2


async def test_order_list_recent_orders_returns_latest_first(
    order_repo: YouzanOrderRepo,
) -> None:
    """最近订单应按支付或更新时间倒序返回。"""
    await order_repo.upsert_order(
        YouzanOrderData(
            order_no="E202600007",
            buyer_id="buyer_old",
            status="TRADE_PAID",
            amount_fen=10000,
            product_titles="旧订单 x 1",
            total_quantity=1,
            pay_time=_TS_OLD,
            created_at=_TS_OLD,
            updated_at=_TS_OLD,
        )
    )
    await order_repo.upsert_order(
        YouzanOrderData(
            order_no="E202600008",
            buyer_id="buyer_new",
            status="TRADE_PAID",
            amount_fen=12000,
            product_titles="新订单 x 1",
            total_quantity=1,
            pay_time=_TS_NEW,
            created_at=_TS_NEW,
            updated_at=_TS_NEW,
        )
    )

    rows = await order_repo.list_recent_orders(limit=1)

    assert [row["order_no"] for row in rows] == ["E202600008"]


async def test_order_dynamic_query_filters_date_status_and_keyword(
    order_repo: YouzanOrderRepo,
) -> None:
    """动态查询计划应影响日期、状态和商品关键词。"""
    await order_repo.upsert_order(
        YouzanOrderData(
            order_no="E202607030001",
            buyer_id="buyer_dynamic_001",
            status="WAIT_SELLER_SEND_GOODS",
            amount_fen=26200,
            product_titles="伯牙绝弦 x 1",
            total_quantity=1,
            pay_time="2026-07-03 20:37:23",
            created_at="2026-07-03 20:37:23",
            updated_at="2026-07-03 20:37:23",
        )
    )
    await order_repo.upsert_order(
        YouzanOrderData(
            order_no="E202607020001",
            buyer_id="buyer_dynamic_002",
            status="TRADE_SUCCESS",
            amount_fen=15800,
            product_titles="伯牙绝弦 x 1",
            total_quantity=1,
            pay_time="2026-07-02 12:00:00",
            created_at="2026-07-02 12:00:00",
            updated_at="2026-07-02 12:00:00",
        )
    )

    rows = await order_repo.query_orders(
        OrderQueryPlan(
            kind=OrderQueryKind.LIST,
            date_from="2026-07-03",
            date_to="2026-07-03",
            statuses=("WAIT_SELLER_SEND_GOODS",),
            keyword="伯牙绝弦",
            limit=5,
        )
    )

    assert [row["order_no"] for row in rows] == ["E202607030001"]


async def test_order_dynamic_summary_counts_statuses(
    order_repo: YouzanOrderRepo,
) -> None:
    """动态统计计划应返回总数、金额和状态分布。"""
    await order_repo.upsert_order(
        YouzanOrderData(
            order_no="E202607030002",
            buyer_id="buyer_summary_001",
            status="WAIT_SELLER_SEND_GOODS",
            amount_fen=10000,
            product_titles="草莓蛋糕 x 1",
            total_quantity=1,
            pay_time="2026-07-03 10:00:00",
            created_at="2026-07-03 10:00:00",
            updated_at="2026-07-03 10:00:00",
        )
    )
    await order_repo.upsert_order(
        YouzanOrderData(
            order_no="E202607030003",
            buyer_id="buyer_summary_002",
            status="TRADE_SUCCESS",
            amount_fen=20000,
            product_titles="椰椰凤梨 x 1",
            total_quantity=1,
            pay_time="2026-07-03 11:00:00",
            created_at="2026-07-03 11:00:00",
            updated_at="2026-07-03 11:00:00",
        )
    )

    summary = await order_repo.summarize_orders(
        OrderQueryPlan(
            kind=OrderQueryKind.SUMMARY,
            date_from="2026-07-03",
            date_to="2026-07-03",
        )
    )

    assert summary["total_count"] == 2
    assert summary["total_amount_fen"] == 30000
    assert summary["status_counts"] == {
        "TRADE_SUCCESS": 1,
        "WAIT_SELLER_SEND_GOODS": 1,
    }


async def test_order_dynamic_query_filters_refund_state(
    order_repo: YouzanOrderRepo,
) -> None:
    """退款查询计划应只返回 refund_state 非零订单。"""
    await order_repo.upsert_order(
        YouzanOrderData(
            order_no="E202607030031",
            buyer_id="buyer_refund_001",
            status="TRADE_CLOSED",
            amount_fen=8800,
            product_titles="售后退款蛋糕 x 1",
            total_quantity=1,
            refund_state=1,
            pay_time="2026-07-03 12:00:00",
            created_at="2026-07-03 12:00:00",
            updated_at="2026-07-03 12:00:00",
        )
    )
    await order_repo.upsert_order(
        YouzanOrderData(
            order_no="E202607030032",
            buyer_id="buyer_refund_002",
            status="TRADE_SUCCESS",
            amount_fen=9900,
            product_titles="正常订单蛋糕 x 1",
            total_quantity=1,
            refund_state=0,
            pay_time="2026-07-03 13:00:00",
            created_at="2026-07-03 13:00:00",
            updated_at="2026-07-03 13:00:00",
        )
    )

    rows = await order_repo.query_orders(
        OrderQueryPlan(
            kind=OrderQueryKind.LIST,
            date_from="2026-07-03",
            date_to="2026-07-03",
            needs_refund=True,
        )
    )
    summary = await order_repo.summarize_orders(
        OrderQueryPlan(
            kind=OrderQueryKind.SUMMARY,
            date_from="2026-07-03",
            date_to="2026-07-03",
            needs_refund=True,
        )
    )

    assert [row["order_no"] for row in rows] == ["E202607030031"]
    assert summary["total_count"] == 1
    assert summary["total_amount_fen"] == 8800
    assert summary["status_counts"] == {"TRADE_CLOSED": 1}


async def test_order_dynamic_query_filters_fulfillment_risk(
    order_repo: YouzanOrderRepo,
) -> None:
    """履约风险计划应只返回有约送时间的待履约订单。"""
    await order_repo.upsert_order(
        YouzanOrderData(
            order_no="E202607030041",
            buyer_id="buyer_risk_001",
            status="WAIT_SELLER_SEND_GOODS",
            amount_fen=16800,
            product_titles="快超时蛋糕 x 1",
            total_quantity=1,
            delivery_time="2026-07-03 18:00",
            pay_time="2026-07-03 10:00:00",
            created_at="2026-07-03 10:00:00",
            updated_at="2026-07-03 10:00:00",
        )
    )
    await order_repo.upsert_order(
        YouzanOrderData(
            order_no="E202607030042",
            buyer_id="buyer_risk_002",
            status="WAIT_SELLER_SEND_GOODS",
            amount_fen=9900,
            product_titles="未约送蛋糕 x 1",
            total_quantity=1,
            pay_time="2026-07-03 11:00:00",
            created_at="2026-07-03 11:00:00",
            updated_at="2026-07-03 11:00:00",
        )
    )
    await order_repo.upsert_order(
        YouzanOrderData(
            order_no="E202607030043",
            buyer_id="buyer_risk_003",
            status="TRADE_SUCCESS",
            amount_fen=8800,
            product_titles="已完成蛋糕 x 1",
            total_quantity=1,
            delivery_time="2026-07-03 18:30",
            pay_time="2026-07-03 12:00:00",
            created_at="2026-07-03 12:00:00",
            updated_at="2026-07-03 12:00:00",
        )
    )

    rows = await order_repo.query_orders(
        OrderQueryPlan(
            kind=OrderQueryKind.LIST,
            needs_fulfillment_risk=True,
        )
    )

    assert [row["order_no"] for row in rows] == ["E202607030041"]


async def test_order_dynamic_query_filters_delivery_time_window(
    order_repo: YouzanOrderRepo,
) -> None:
    """配送时间窗计划应只返回白名单时间段内的订单。"""
    await order_repo.upsert_order(
        YouzanOrderData(
            order_no="E202607030051",
            buyer_id="buyer_evening_001",
            status="WAIT_SELLER_SEND_GOODS",
            amount_fen=16800,
            product_titles="晚送蛋糕 x 1",
            total_quantity=1,
            delivery_time="2026-07-03 18:30",
            pay_time="2026-07-03 10:00:00",
            created_at="2026-07-03 10:00:00",
            updated_at="2026-07-03 10:00:00",
        )
    )
    await order_repo.upsert_order(
        YouzanOrderData(
            order_no="E202607030052",
            buyer_id="buyer_evening_002",
            status="WAIT_SELLER_SEND_GOODS",
            amount_fen=9900,
            product_titles="午送蛋糕 x 1",
            total_quantity=1,
            delivery_time="2026-07-03 12:30",
            pay_time="2026-07-03 11:00:00",
            created_at="2026-07-03 11:00:00",
            updated_at="2026-07-03 11:00:00",
        )
    )
    await order_repo.upsert_order(
        YouzanOrderData(
            order_no="E202607030053",
            buyer_id="buyer_evening_003",
            status="TRADE_SUCCESS",
            amount_fen=8800,
            product_titles="已完成蛋糕 x 1",
            total_quantity=1,
            delivery_time="2026-07-03 19:00",
            pay_time="2026-07-03 12:00:00",
            created_at="2026-07-03 12:00:00",
            updated_at="2026-07-03 12:00:00",
        )
    )

    rows = await order_repo.query_orders(
        OrderQueryPlan(
            kind=OrderQueryKind.LIST,
            date_from="2026-07-03",
            date_to="2026-07-03",
            statuses=("WAIT_SELLER_SEND_GOODS",),
            delivery_time_start="18:00",
            delivery_time_end="23:59",
        )
    )

    assert [row["order_no"] for row in rows] == ["E202607030051"]


async def test_order_dynamic_query_filters_delivery_date_field(
    order_repo: YouzanOrderRepo,
) -> None:
    """配送日期口径应按约送日期过滤，而不是下单日期。"""
    await order_repo.upsert_order(
        YouzanOrderData(
            order_no="E202607030061",
            buyer_id="buyer_delivery_001",
            status="WAIT_SELLER_SEND_GOODS",
            amount_fen=16800,
            product_titles="明日约送蛋糕 x 1",
            total_quantity=1,
            delivery_time="2026-07-04 10:30",
            pay_time="2026-07-03 10:00:00",
            created_at="2026-07-03 10:00:00",
            updated_at="2026-07-03 10:00:00",
        )
    )
    await order_repo.upsert_order(
        YouzanOrderData(
            order_no="E202607040061",
            buyer_id="buyer_delivery_002",
            status="WAIT_SELLER_SEND_GOODS",
            amount_fen=9900,
            product_titles="今日约送蛋糕 x 1",
            total_quantity=1,
            delivery_time="2026-07-03 18:30",
            pay_time="2026-07-04 11:00:00",
            created_at="2026-07-04 11:00:00",
            updated_at="2026-07-04 11:00:00",
        )
    )

    rows = await order_repo.query_orders(
        OrderQueryPlan(
            kind=OrderQueryKind.LIST,
            date_from="2026-07-04",
            date_to="2026-07-04",
            date_field="delivery_time",
            statuses=("WAIT_SELLER_SEND_GOODS",),
        )
    )

    assert [row["order_no"] for row in rows] == ["E202607030061"]


async def test_order_dynamic_top_products(order_repo: YouzanOrderRepo) -> None:
    """动态商品聚合应按销量返回排行。"""
    await order_repo.upsert_order(
        YouzanOrderData(
            order_no="E202607030004",
            buyer_id="buyer_top_001",
            status="TRADE_SUCCESS",
            amount_fen=30000,
            product_titles="伯牙绝弦 x 2",
            total_quantity=2,
            pay_time="2026-07-03 12:00:00",
            created_at="2026-07-03 12:00:00",
            updated_at="2026-07-03 12:00:00",
        )
    )
    await order_repo.upsert_order(
        YouzanOrderData(
            order_no="E202607030005",
            buyer_id="buyer_top_002",
            status="TRADE_SUCCESS",
            amount_fen=10000,
            product_titles="椰椰凤梨 x 1",
            total_quantity=1,
            pay_time="2026-07-03 13:00:00",
            created_at="2026-07-03 13:00:00",
            updated_at="2026-07-03 13:00:00",
        )
    )

    rows = await order_repo.list_top_products(
        OrderQueryPlan(
            kind=OrderQueryKind.TOP_PRODUCTS,
            date_from="2026-07-03",
            date_to="2026-07-03",
        )
    )

    assert rows[0]["product_titles"] == "伯牙绝弦 x 2"
    assert rows[0]["total_quantity"] == 2
