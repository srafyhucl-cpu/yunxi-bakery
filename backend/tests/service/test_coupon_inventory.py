# tests/service/test_coupon_inventory.py
"""券库存账本测试：最新态、核销、退回、并发幂等。"""

import aiosqlite
import pytest

from app.models.member import CouponInventoryEntry, CouponStatus, LedgerSource
from app.repository.coupon_inventory_repo import CouponInventoryRepo
from app.service.coupon.inventory import CouponInventoryService


async def _seed_take(
    db: aiosqlite.Connection, coupon_id: str = "c1", mobile: str = "13800000000"
) -> None:
    repo = CouponInventoryRepo(db)
    await repo.insert(
        CouponInventoryEntry(
            coupon_id=coupon_id,
            status=CouponStatus.TAKE,
            mobile=mobile,
            coupon_group_id="cg_001",
            title="满30减5",
            value_fen=500,
            source=LedgerSource.IMPORT,
            occurred_at="2026-08-01 09:00:00",
            template_id="cg_001",
            valid_from="2026-08-01",
            valid_until="2026-09-30",
        )
    )


@pytest.mark.asyncio
async def test_insert_persists_template_fields(db: aiosqlite.Connection) -> None:
    """insert 必须落库 6 个新列（模板回填/过期校验/展示依赖）。"""
    await _seed_take(db)
    rows = await db.execute_fetchall(
        "SELECT template_id, valid_from, valid_until FROM coupon_inventory "
        "WHERE coupon_id = 'c1' AND mobile = '13800000000'"
    )
    assert rows
    assert rows[0]["template_id"] == "cg_001"
    assert rows[0]["valid_from"] == "2026-08-01"
    assert rows[0]["valid_until"] == "2026-09-30"


@pytest.mark.asyncio
async def test_get_latest_state_youzan(db: aiosqlite.Connection) -> None:
    """youzan 模式最新态优先 order 行。"""
    await _seed_take(db)
    repo = CouponInventoryRepo(db)
    await repo.insert(
        CouponInventoryEntry(
            coupon_id="c1",
            status=CouponStatus.CONSUME,
            mobile="13800000000",
            coupon_group_id="cg_001",
            order_no="o1",
            source=LedgerSource.ORDER,
            occurred_at="2026-08-10 09:00:00",
            template_id="cg_001",
        )
    )
    await repo.insert(
        CouponInventoryEntry(
            coupon_id="c1",
            status=CouponStatus.BACK,
            mobile="13800000000",
            coupon_group_id="cg_001",
            order_no="o1",
            source=LedgerSource.WEBHOOK,
            occurred_at="2026-08-11 09:00:00",
            template_id="cg_001",
        )
    )
    state = await repo.get_latest_state("c1", "13800000000", authority="youzan")
    assert state is not None
    assert state["status"] == CouponStatus.CONSUME


@pytest.mark.asyncio
async def test_consume_success_and_idempotent(db: aiosqlite.Connection) -> None:
    """核销成功；重复核销幂等返回同一结果不重复插行。"""
    await _seed_take(db)
    service = CouponInventoryService(db)
    first = await service.consume_once(
        "c1",
        "13800000000",
        order_no="o1",
        deducted_fen=500,
        occurred_at="2026-08-10 09:00:00",
    )
    assert first is not None
    second = await service.consume_once(
        "c1",
        "13800000000",
        order_no="o1",
        deducted_fen=500,
        occurred_at="2026-08-10 09:01:00",
    )
    assert second is not None
    rows = await db.execute_fetchall(
        "SELECT id FROM coupon_inventory WHERE coupon_id = 'c1' AND status = 'CONSUME'"
    )
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_consume_rejected_cross_order(db: aiosqlite.Connection) -> None:
    """同券被两订单应用时，第二订单核销抛错（防跨订单双花）。"""
    await _seed_take(db)
    service = CouponInventoryService(db)
    await service.consume_once(
        "c1",
        "13800000000",
        order_no="o1",
        deducted_fen=500,
        occurred_at="2026-08-10 09:00:00",
    )
    with pytest.raises(ValueError):
        await service.consume_once(
            "c1",
            "13800000000",
            order_no="o2",
            deducted_fen=500,
            occurred_at="2026-08-10 10:00:00",
        )
    rows = await db.execute_fetchall(
        "SELECT id FROM coupon_inventory WHERE coupon_id = 'c1' AND status = 'CONSUME'"
    )
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_consume_rejected_when_not_take(db: aiosqlite.Connection) -> None:
    """最新态非 TAKE 时拒绝核销。"""
    await _seed_take(db)
    repo = CouponInventoryRepo(db)
    await repo.insert(
        CouponInventoryEntry(
            coupon_id="c1",
            status=CouponStatus.BACK,
            mobile="13800000000",
            coupon_group_id="cg_001",
            order_no="o_other",
            source=LedgerSource.ORDER,
            occurred_at="2026-08-05 09:00:00",
            template_id="cg_001",
        )
    )
    service = CouponInventoryService(db)
    result = await service.consume_once(
        "c1",
        "13800000000",
        order_no="o2",
        deducted_fen=500,
        occurred_at="2026-08-10 10:00:00",
    )
    assert result is None


@pytest.mark.asyncio
async def test_consume_rejected_when_expired(db: aiosqlite.Connection) -> None:
    """券已过期时拒绝核销。"""
    await _seed_take(db)
    service = CouponInventoryService(db)
    result = await service.consume_once(
        "c1",
        "13800000000",
        order_no="o3",
        deducted_fen=500,
        occurred_at="2026-10-01 09:00:00",
    )
    assert result is None


@pytest.mark.asyncio
async def test_refund_success_and_idempotent(db: aiosqlite.Connection) -> None:
    """已核销后退回；重复退回幂等。"""
    await _seed_take(db)
    service = CouponInventoryService(db)
    await service.consume_once(
        "c1",
        "13800000000",
        order_no="o1",
        deducted_fen=500,
        occurred_at="2026-08-10 09:00:00",
    )
    first = await service.refund_once(
        "c1", "13800000000", order_no="o1", occurred_at="2026-08-12 09:00:00"
    )
    assert first is not None
    second = await service.refund_once(
        "c1", "13800000000", order_no="o1", occurred_at="2026-08-12 09:01:00"
    )
    assert second is not None
    rows = await db.execute_fetchall(
        "SELECT id FROM coupon_inventory WHERE coupon_id = 'c1' AND status = 'BACK'"
    )
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_list_by_mobile_aggregates_latest(db: aiosqlite.Connection) -> None:
    """我的券列表按最新态聚合，不返回历史行。"""
    await _seed_take(db)
    repo = CouponInventoryRepo(db)
    await repo.insert(
        CouponInventoryEntry(
            coupon_id="c1",
            status=CouponStatus.CONSUME,
            mobile="13800000000",
            coupon_group_id="cg_001",
            order_no="o1",
            source=LedgerSource.ORDER,
            occurred_at="2026-08-10 09:00:00",
            template_id="cg_001",
        )
    )
    rows = await repo.list_by_mobile("13800000000", authority="youzan")
    assert len(rows) == 1
    assert rows[0]["status"] == CouponStatus.CONSUME
