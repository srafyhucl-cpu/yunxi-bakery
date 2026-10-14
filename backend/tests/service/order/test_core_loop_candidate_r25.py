"""MiniApp 核心闭环 r25：最后一件库存并发下单。"""

import asyncio
import sqlite3

import pytest

from app.database import close_db, init_db
from app.repository.base import DatabaseHandle
from app.repository.config_repo import ConfigRepo
from app.repository.order_event_repo import OrderEventRepo
from app.repository.order_repo import OrderRepo
from app.repository.session_repo import SessionRepo
from app.repository.youzan_inventory_repo import YouzanInventoryRepo
from app.repository.youzan_repo import YouzanProductRepo
from app.service.order import OrderApplicationService
from tests.helpers.catalog_seed import seed_catalog_product

ITEM_ID = 92501
ITEM_TITLE = "最后一件库存并发蛋糕"
PRICE_FEN = 19_800
USERS = ("last-stock-user-a", "last-stock-user-b")


def _build_order_service(handle: DatabaseHandle) -> OrderApplicationService:
    """为单个数据库连接构建真实订单应用服务。"""
    return OrderApplicationService(
        order_repo=OrderRepo(handle),
        session_repo=SessionRepo(handle),
        product_repo=YouzanProductRepo(handle),
        inventory_repo=YouzanInventoryRepo(handle),
        config_repo=ConfigRepo(handle),
        event_repo=OrderEventRepo(handle),
    )


def _payload(user_id: str) -> dict:
    """构建两个用户各自的自提下单请求。"""
    return {
        "items": [
            {
                "productId": str(ITEM_ID),
                "title": ITEM_TITLE,
                "priceFen": PRICE_FEN,
                "quantity": 1,
            }
        ],
        "receiverName": f"库存用户-{user_id[-1]}",
        "receiverPhone": "18800002501",
        "deliveryType": "pickup",
        "expectTime": "2026-06-18 18:00",
    }


async def _attempt_create(
    service: OrderApplicationService,
    user_id: str,
) -> tuple[str, str]:
    """执行一个独立订单创建请求并归一化可接受失败。"""
    try:
        result = await service.create_order(_payload(user_id), user_id=user_id)
        return "ok", str(result["orderId"])
    except ValueError as exc:
        return "conflict", str(exc)
    except sqlite3.OperationalError as exc:
        if "locked" not in str(exc).lower():
            raise
        return "locked", str(exc)


@pytest.mark.asyncio
async def test_concurrent_last_stock_order_creation_has_single_winner(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """两个请求都读到最后一件库存时，只能创建一笔订单。"""
    database_path = tmp_path / "last-stock-concurrent-order.db"
    connection_a = await init_db(str(database_path))
    connection_b = await init_db(str(database_path))
    handle_a = DatabaseHandle(connection_a)
    handle_b = DatabaseHandle(connection_b)
    try:
        await seed_catalog_product(
            connection_a,
            item_id=ITEM_ID,
            title=ITEM_TITLE,
            price_fen=PRICE_FEN,
            stock=1,
        )
        service_a = _build_order_service(handle_a)
        service_b = _build_order_service(handle_b)

        stock_read_barrier = asyncio.Barrier(2)
        original_get_prices_and_stocks = YouzanProductRepo.get_prices_and_stocks

        async def synchronized_stock_read(
            repo: YouzanProductRepo,
            item_ids: list[str],
        ) -> dict[str, dict]:
            """确保两个请求都在库存仍为 1 时完成首次读取。"""
            result = await original_get_prices_and_stocks(repo, item_ids)
            await asyncio.wait_for(stock_read_barrier.wait(), timeout=5)
            return result

        monkeypatch.setattr(
            YouzanProductRepo,
            "get_prices_and_stocks",
            synchronized_stock_read,
        )

        results = await asyncio.gather(
            _attempt_create(service_a, USERS[0]),
            _attempt_create(service_b, USERS[1]),
        )

        product_rows = await connection_a.execute_fetchall(
            "SELECT stock FROM youzan_products WHERE item_id = ?",
            (ITEM_ID,),
        )
        order_rows = await connection_a.execute_fetchall(
            "SELECT id, user_id, status FROM orders ORDER BY id",
        )
        event_rows = await connection_a.execute_fetchall(
            "SELECT order_id, status FROM order_events ORDER BY id",
        )
        session_rows = await connection_a.execute_fetchall(
            "SELECT user_id FROM sessions ORDER BY user_id",
        )

        assert len(product_rows) == 1
        assert int(product_rows[0]["stock"]) == 0
        assert len(order_rows) == 1
        successful_results = [value for outcome, value in results if outcome == "ok"]
        assert successful_results == [str(order_rows[0]["id"])]
        assert str(order_rows[0]["user_id"]) in USERS
        assert str(order_rows[0]["status"]) == "pending"
        assert len(event_rows) == 1
        assert str(event_rows[0]["order_id"]) == str(order_rows[0]["id"])
        assert str(event_rows[0]["status"]) == "pending"
        assert [str(row["user_id"]) for row in session_rows] == [
            str(order_rows[0]["user_id"])
        ]
    finally:
        await close_db(connection_b)
        await close_db(connection_a)
