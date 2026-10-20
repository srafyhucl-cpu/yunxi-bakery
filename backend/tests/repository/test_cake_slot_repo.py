"""定制蛋糕时段容量预占仓库测试。"""

import asyncio

import aiosqlite
import pytest

from app.repository.cake_slot_repo import CakeSlotRepo

SLOT_KEY = "2026-10-20 14:00-16:00"
OTHER_SLOT_KEY = "2026-10-20 16:00-18:00"


@pytest.mark.asyncio
async def test_concurrent_reserve_only_one_wins_last_slot(
    db: aiosqlite.Connection,
) -> None:
    """容量为 1 时两个并发预占只能成功一个，失败方不留预占记录。"""
    repo = CakeSlotRepo(db)

    results = await asyncio.gather(
        repo.reserve(SLOT_KEY, "order_a", 1),
        repo.reserve(SLOT_KEY, "order_b", 1),
    )

    assert sorted(results) == [False, True]
    assert await repo.count_for_slot(SLOT_KEY) == 1
    reservations = await db.execute_fetchall(
        "SELECT order_id FROM cake_slot_reservations WHERE slot_key = ?",
        (SLOT_KEY,),
    )
    assert len(reservations) == 1


@pytest.mark.asyncio
async def test_reserve_same_order_same_slot_is_idempotent(
    db: aiosqlite.Connection,
) -> None:
    """同一订单重复预占同一时段幂等，不重复计数；换时段则拒绝。"""
    repo = CakeSlotRepo(db)

    assert await repo.reserve(SLOT_KEY, "order_a", 5) is True
    assert await repo.reserve(SLOT_KEY, "order_a", 5) is True
    assert await repo.count_for_slot(SLOT_KEY) == 1

    assert await repo.reserve(OTHER_SLOT_KEY, "order_a", 5) is False
    assert await repo.count_for_slot(OTHER_SLOT_KEY) == 0
    reservation = await repo.get_reservation("order_a")
    assert reservation is not None
    assert reservation["slot_key"] == SLOT_KEY


@pytest.mark.asyncio
async def test_release_is_idempotent_and_never_negative(
    db: aiosqlite.Connection,
) -> None:
    """释放幂等，重复释放不会把计数减成负数。"""
    repo = CakeSlotRepo(db)
    await repo.reserve(SLOT_KEY, "order_a", 5)

    assert await repo.release("order_a") is True
    assert await repo.count_for_slot(SLOT_KEY) == 0
    assert await repo.get_reservation("order_a") is None

    assert await repo.release("order_a") is True
    assert await repo.count_for_slot(SLOT_KEY) == 0


@pytest.mark.asyncio
async def test_different_orders_exceed_capacity(
    db: aiosqlite.Connection,
) -> None:
    """不同订单争抢已满时段时失败方不写入预占。"""
    repo = CakeSlotRepo(db)

    assert await repo.reserve(SLOT_KEY, "order_a", 1) is True
    assert await repo.reserve(SLOT_KEY, "order_b", 1) is False
    assert await repo.count_for_slot(SLOT_KEY) == 1
    assert await repo.get_reservation("order_b") is None
