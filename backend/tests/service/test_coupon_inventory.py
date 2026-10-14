# 测试文件：tests/service/test_coupon_inventory.py
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
    """最新态非 TAKE 时必须抛错，不得静默返回空结果让调用方当作已核销。

    该契约由 r63 的跨订单双花修复确立：券已被其他订单退回时若静默放行，
    支付路径会把「券未核销」当成「已核销」，使订单按券面抵扣完成支付，
    形成一张券抵扣两单且券退回用户手里的资产双花。
    """
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
    assert rows == []


@pytest.mark.asyncio
async def test_consume_honours_locked_snapshot_after_expiry(
    db: aiosqlite.Connection,
) -> None:
    """跨过有效期后仍按应用时锁定的快照核销，避免已到账支付被回滚。

    有效期与抵扣金额的权威关口在 `apply_coupon_snapshot`（按模板校验
    `is_coupon_available` 并锁定 `couponFen`），核销阶段不再复查：核销是
    支付事务内的最后一步，此时微信资金已到账，若因过期拒绝核销会把整笔
    支付回滚成未支付，形成「已付款但永远不落单」且无法自动收敛的资金
    搁浅。券记为已消耗，不给用户留下可二次使用的抵扣。
    """
    await _seed_take(db)
    service = CouponInventoryService(db)
    result = await service.consume_once(
        "c1",
        "13800000000",
        order_no="o3",
        deducted_fen=500,
        occurred_at="2026-10-01 09:00:00",
    )
    assert result is not None
    assert str(result.status) == CouponStatus.CONSUME
    assert str(result.order_no) == "o3"
    rows = await db.execute_fetchall(
        "SELECT id FROM coupon_inventory WHERE coupon_id = 'c1' AND status = 'CONSUME'"
    )
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_refund_success_and_idempotent(db: aiosqlite.Connection) -> None:
    """已核销后退回并在新周期恢复可持有；重复退回幂等。

    r78（`M-20260926-028`）后本腿写两行：`BACK` 冲正 + 新周期 `TAKE` 恢复
    可持有（退款把整笔权益还给客户，券必须能再次使用）。因此第二次
    `refund_once` 返回 `None` 是**正确**结果而非缺陷：最新态已是新周期 `TAKE`，
    券已在客户手里，本腿无事可做（与 r72「券从未核销时退回静默无操作」同一
    语义）。幂等性由行数不变来锁定，而不是由返回值形状锁定。
    """
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
    assert str(first.status) == CouponStatus.BACK
    second = await service.refund_once(
        "c1", "13800000000", order_no="o1", occurred_at="2026-08-12 09:01:00"
    )
    assert second is None
    rows = await db.execute_fetchall(
        "SELECT status, cycle_no, order_no FROM coupon_inventory "
        "WHERE coupon_id = 'c1' ORDER BY id"
    )
    # 关键断言：冲正行与恢复持有的 TAKE 各只一条，重复调用没有多写。
    assert [dict(row) for row in rows] == [
        {"status": CouponStatus.TAKE, "cycle_no": 0, "order_no": ""},
        {"status": CouponStatus.CONSUME, "cycle_no": 0, "order_no": "o1"},
        {"status": CouponStatus.BACK, "cycle_no": 0, "order_no": "o1"},
        {"status": CouponStatus.TAKE, "cycle_no": 1, "order_no": "o1"},
    ]


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
