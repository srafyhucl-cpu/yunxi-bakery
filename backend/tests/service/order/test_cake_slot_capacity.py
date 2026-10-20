"""定制蛋糕 2 小时时段容量原子预占/释放集成测试。"""

import json

import aiosqlite
import pytest

from app.repository.cake_slot_repo import CakeSlotRepo
from app.repository.config_repo import ConfigRepo
from app.repository.order_event_repo import OrderEventRepo
from app.repository.order_repo import OrderRepo
from app.repository.session_repo import SessionRepo
from app.repository.youzan_inventory_repo import YouzanInventoryRepo
from app.repository.youzan_repo import YouzanProductRepo
from app.service.order.application import OrderApplicationService
from app.service.order.cake_slots import CakeSlotCapacityService, extract_slot_key
from tests.helpers.catalog_seed import seed_catalog_product

CAKE_PRODUCT_ID = 91001
DAILY_PRODUCT_ID = 91002
USER_ID = "cake-slot-user"
CUSTOMIZATION = {
    "size": "8寸",
    "filling": "草莓",
    "greeting": "生日快乐",
    "accessories": "餐具+蜡烛",
}


def _build_service(
    db: aiosqlite.Connection,
    *,
    max_capacity: int = 5,
) -> tuple[OrderApplicationService, CakeSlotCapacityService, CakeSlotRepo]:
    """构建注入真实时段容量服务的订单应用服务。"""
    slot_repo = CakeSlotRepo(db)
    slot_service = CakeSlotCapacityService(slot_repo, max_capacity=max_capacity)
    service = OrderApplicationService(
        order_repo=OrderRepo(db),
        event_repo=OrderEventRepo(db),
        session_repo=SessionRepo(db),
        product_repo=YouzanProductRepo(db),
        inventory_repo=YouzanInventoryRepo(db),
        config_repo=ConfigRepo(db),
        slot_service=slot_service,
    )
    return service, slot_service, slot_repo


def _cake_payload(
    expect_time: str,
    *,
    product_id: int = CAKE_PRODUCT_ID,
) -> dict:
    return {
        "items": [
            {
                "productId": product_id,
                "quantity": 1,
                "fulfillmentType": "PREORDER_CAKE",
                "customization": dict(CUSTOMIZATION),
            }
        ],
        "receiverName": "张三",
        "receiverPhone": "13800000000",
        "expectTime": expect_time,
    }


async def _count_orders(db: aiosqlite.Connection) -> int:
    rows = await db.execute_fetchall("SELECT COUNT(*) AS total FROM orders")
    return int(rows[0]["total"])


async def _mark_paid(db: aiosqlite.Connection, order_id: str) -> None:
    """把订单支付快照改为已支付，便于进入履约状态。"""
    rows = await db.execute_fetchall(
        "SELECT payment FROM orders WHERE id = ?",
        (order_id,),
    )
    payment = json.loads(str(rows[0]["payment"]))
    payment["status"] = "paid"
    payment["paidAt"] = "2026-06-17 12:10:00"
    await db.execute(
        "UPDATE orders SET payment = ? WHERE id = ?",
        (json.dumps(payment, ensure_ascii=False), order_id),
    )
    await db.commit()


async def _backdate_payment(db: aiosqlite.Connection, order_id: str) -> None:
    """把支付创建时间改到很久以前，触发超时关闭扫描。"""
    rows = await db.execute_fetchall(
        "SELECT payment FROM orders WHERE id = ?",
        (order_id,),
    )
    payment = json.loads(str(rows[0]["payment"]))
    payment["createdAt"] = "2000-01-01 00:00:00"
    await db.execute(
        "UPDATE orders SET payment = ?, created_at = ? WHERE id = ?",
        (json.dumps(payment, ensure_ascii=False), "2000-01-01 00:00:00", order_id),
    )
    await db.commit()


def test_extract_slot_key_groups_by_two_hour_window() -> None:
    """14:00-16:00 窗口内的不同预约时间归入同一时段键。"""
    assert extract_slot_key("2026-10-20 14:00") == "2026-10-20 14:00-16:00"
    assert extract_slot_key("2026-10-20 15:59") == "2026-10-20 14:00-16:00"
    assert extract_slot_key("2026-10-20 16:00") == "2026-10-20 16:00-18:00"

    with pytest.raises(ValueError, match="预约时间"):
        extract_slot_key("2026/10/20 14:00")


@pytest.mark.asyncio
async def test_cake_order_reserves_slot_and_rejects_overflow(
    db: aiosqlite.Connection,
) -> None:
    """蛋糕订单占 1 个名额，同窗口第二单超容量失败且不写订单。"""
    await seed_catalog_product(
        db,
        item_id=CAKE_PRODUCT_ID,
        title="生日定制蛋糕",
        price_fen=19800,
        stock=10,
    )
    service, slot_service, slot_repo = _build_service(db, max_capacity=1)

    created = await service.create_order(
        _cake_payload("2099-06-18 15:30"),
        user_id=USER_ID,
    )

    assert await slot_service.count("2099-06-18 14:00") == 1
    reservation = await slot_repo.get_reservation(created["orderId"])
    assert reservation is not None
    assert reservation["slot_key"] == "2099-06-18 14:00-16:00"
    assert await _count_orders(db) == 1

    with pytest.raises(ValueError, match="该预约时段定制蛋糕已满"):
        await service.create_order(
            _cake_payload("2099-06-18 15:45"),
            user_id=USER_ID,
        )

    assert await slot_service.count("2099-06-18 15:00") == 1
    assert await _count_orders(db) == 1


@pytest.mark.asyncio
async def test_user_cancel_releases_slot(db: aiosqlite.Connection) -> None:
    """用户取消后释放名额，时段可再次接单。"""
    await seed_catalog_product(
        db,
        item_id=CAKE_PRODUCT_ID,
        title="生日定制蛋糕",
        price_fen=19800,
        stock=10,
    )
    service, slot_service, slot_repo = _build_service(db, max_capacity=1)
    created = await service.create_order(
        _cake_payload("2099-06-19 15:00"),
        user_id=USER_ID,
    )

    await service.cancel_user_order(created["orderId"], user_id=USER_ID)

    assert await slot_service.count("2099-06-19 15:00") == 0
    assert await slot_repo.get_reservation(created["orderId"]) is None

    # 名额已归还，同窗口可以再次下单。
    await service.create_order(
        _cake_payload("2099-06-19 15:30"),
        user_id=USER_ID,
    )
    assert await slot_service.count("2099-06-19 15:30") == 1


@pytest.mark.asyncio
async def test_timeout_expiration_releases_slot(db: aiosqlite.Connection) -> None:
    """未支付超时关闭后释放名额。"""
    await seed_catalog_product(
        db,
        item_id=CAKE_PRODUCT_ID,
        title="生日定制蛋糕",
        price_fen=19800,
        stock=10,
    )
    service, slot_service, slot_repo = _build_service(db, max_capacity=1)
    created = await service.create_order(
        _cake_payload("2099-06-20 15:00"),
        user_id=USER_ID,
    )
    await _backdate_payment(db, created["orderId"])

    result = await service.expire_timeout_unpaid_orders()

    assert result["expiredCount"] == 1
    assert await slot_service.count("2099-06-20 15:00") == 0
    assert await slot_repo.get_reservation(created["orderId"]) is None


@pytest.mark.asyncio
async def test_admin_cancel_releases_slot(db: aiosqlite.Connection) -> None:
    """后台取消释放名额。"""
    await seed_catalog_product(
        db,
        item_id=CAKE_PRODUCT_ID,
        title="生日定制蛋糕",
        price_fen=19800,
        stock=10,
    )
    service, slot_service, slot_repo = _build_service(db, max_capacity=1)
    created = await service.create_order(
        _cake_payload("2099-06-21 15:00"),
        user_id=USER_ID,
    )

    await service.update_admin_order_status(created["orderId"], "cancelled")

    assert await slot_service.count("2099-06-21 15:00") == 0
    assert await slot_repo.get_reservation(created["orderId"]) is None


@pytest.mark.asyncio
async def test_done_keeps_slot_reserved(db: aiosqlite.Connection) -> None:
    """订单完成后不释放名额，时段仍保持占用。"""
    await seed_catalog_product(
        db,
        item_id=CAKE_PRODUCT_ID,
        title="生日定制蛋糕",
        price_fen=19800,
        stock=10,
    )
    service, slot_service, slot_repo = _build_service(db, max_capacity=1)
    created = await service.create_order(
        _cake_payload("2099-06-22 15:00"),
        user_id=USER_ID,
    )

    await service.update_admin_order_status(created["orderId"], "confirmed")
    await _mark_paid(db, created["orderId"])
    await service.update_admin_order_status(created["orderId"], "making")
    await service.update_admin_order_status(created["orderId"], "delivering")
    await service.update_admin_order_status(created["orderId"], "done")

    assert await slot_service.count("2099-06-22 15:00") == 1
    assert await slot_repo.get_reservation(created["orderId"]) is not None


@pytest.mark.asyncio
async def test_daily_ready_order_does_not_reserve_slot(
    db: aiosqlite.Connection,
) -> None:
    """日常现烤订单不占用定制蛋糕时段名额。"""
    await seed_catalog_product(
        db,
        item_id=DAILY_PRODUCT_ID,
        title="现烤法棍",
        price_fen=1500,
        stock=10,
    )
    service, slot_service, _slot_repo = _build_service(db, max_capacity=1)

    await service.create_order(
        {
            "items": [
                {
                    "productId": DAILY_PRODUCT_ID,
                    "quantity": 1,
                    "fulfillmentType": "DAILY_READY",
                }
            ],
            "receiverName": "李四",
            "receiverPhone": "13800000001",
            "expectTime": "2099-06-23 15:00",
        },
        user_id=USER_ID,
    )

    assert await slot_service.count("2099-06-23 15:00") == 0
    rows = await db.execute_fetchall("SELECT order_id FROM cake_slot_reservations")
    assert rows == []


@pytest.mark.asyncio
async def test_mixed_order_with_cake_reserves_slot(
    db: aiosqlite.Connection,
) -> None:
    """蛋糕+现烤混合订单仍占用时段名额。"""
    await seed_catalog_product(
        db,
        item_id=CAKE_PRODUCT_ID,
        title="生日定制蛋糕",
        price_fen=19800,
        stock=10,
    )
    await seed_catalog_product(
        db,
        item_id=DAILY_PRODUCT_ID,
        title="现烤法棍",
        price_fen=1500,
        stock=10,
    )
    service, slot_service, slot_repo = _build_service(db, max_capacity=1)

    created = await service.create_order(
        {
            "items": [
                {
                    "productId": CAKE_PRODUCT_ID,
                    "quantity": 1,
                    "fulfillmentType": "PREORDER_CAKE",
                    "customization": dict(CUSTOMIZATION),
                },
                {
                    "productId": DAILY_PRODUCT_ID,
                    "quantity": 1,
                    "fulfillmentType": "DAILY_READY",
                },
            ],
            "receiverName": "王五",
            "receiverPhone": "13800000002",
            "expectTime": "2099-06-24 15:00",
        },
        user_id=USER_ID,
    )

    assert await slot_service.count("2099-06-24 15:00") == 1
    assert await slot_repo.get_reservation(created["orderId"]) is not None
