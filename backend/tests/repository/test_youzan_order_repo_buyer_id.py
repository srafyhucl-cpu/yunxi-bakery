from __future__ import annotations

from app.models.employee_agent import OrderQueryKind, OrderQueryPlan
from app.models.order import YouzanOrderData
from app.repository.youzan_order_repo import YouzanOrderRepo


async def test_query_orders_filters_by_buyer_id(db) -> None:
    repo = YouzanOrderRepo(db)
    await repo.upsert_order(
        YouzanOrderData(
            order_no="E202607050001",
            buyer_id="buyer_same",
            status="WAIT_SELLER_SEND_GOODS",
            amount_fen=18800,
            product_titles="草莓蛋糕 x 1",
            total_quantity=1,
            created_at="2026-07-05 10:00:00",
            updated_at="2026-07-05 10:00:00",
        )
    )
    await repo.upsert_order(
        YouzanOrderData(
            order_no="E202607050002",
            buyer_id="buyer_same",
            status="WAIT_BUYER_CONFIRM_GOODS",
            amount_fen=26800,
            product_titles="伯牙绝弦 x 1",
            total_quantity=1,
            created_at="2026-07-05 11:00:00",
            updated_at="2026-07-05 11:00:00",
        )
    )
    await repo.upsert_order(
        YouzanOrderData(
            order_no="E202607050003",
            buyer_id="buyer_other",
            status="WAIT_SELLER_SEND_GOODS",
            amount_fen=9900,
            product_titles="椰椰凤梨 x 1",
            total_quantity=1,
            created_at="2026-07-05 12:00:00",
            updated_at="2026-07-05 12:00:00",
        )
    )

    rows = await repo.query_orders(
        OrderQueryPlan(
            kind=OrderQueryKind.LIST,
            buyer_id="buyer_same",
        )
    )

    assert [row["order_no"] for row in rows] == [
        "E202607050002",
        "E202607050001",
    ]


async def test_get_by_order_no_for_identity_requires_matching_owner(db) -> None:
    repo = YouzanOrderRepo(db)
    await repo.upsert_order(
        YouzanOrderData(
            order_no="E202607050001",
            buyer_id="buyer_same",
            status="TRADE_SUCCESS",
            amount_fen=18800,
            product_titles="草莓蛋糕 x 1",
            total_quantity=1,
            outer_user_id="outer_same",
            created_at="2026-07-05 10:00:00",
            updated_at="2026-07-05 10:00:00",
        )
    )

    same_buyer = await repo.get_by_order_no_for_identity(
        "E202607050001",
        buyer_id="buyer_same",
        outer_user_id=None,
    )
    other_buyer = await repo.get_by_order_no_for_identity(
        "E202607050001",
        buyer_id="buyer_other",
        outer_user_id=None,
    )
    same_outer_user = await repo.get_by_order_no_for_identity(
        "E202607050001",
        buyer_id=None,
        outer_user_id="outer_same",
    )
    empty_identity = await repo.get_by_order_no_for_identity(
        "E202607050001",
        buyer_id="",
        outer_user_id=" ",
    )

    assert same_buyer is not None
    assert same_buyer["order_no"] == "E202607050001"
    assert other_buyer is None
    assert same_outer_user is not None
    assert empty_identity is None
