"""店员快捷开单创建服务测试（储值直扣 / 微信分享待付 / 请求幂等）。"""

import json

import aiosqlite
import pytest

from app.repository.staff_quick_order_repo import StaffQuickOrderRequestRepo
from app.service.staff_quick_order import MODE_WECHAT_SHARE_CARD
from tests.helpers.staff_quick_order import (
    PHONE,
    balance_fen,
    build_stack,
    create_payload,
    order_count,
    pay_ledger_count,
    principal,
    seed_member,
    seed_product,
    seed_unbound_member,
)


@pytest.mark.asyncio
async def test_stored_value_direct_creates_paid_order_and_receipt(
    db: aiosqlite.Connection,
) -> None:
    await seed_member(db, balance_fen=20000)
    await seed_product(db)
    service, order_repo, audit_repo = build_stack(db)

    result = await service.create_quick_order(
        principal(),
        create_payload("req-direct-0001"),
    )
    await db.commit()

    assert result["status"] == "pending"
    assert result["paymentStatus"] == "paid"
    assert result["balanceFen"] == 15000
    assert "订单号：" + result["orderId"] in result["receiptText"]
    assert "现烤可颂 x1" in result["receiptText"]
    assert "合计：50.00元" in result["receiptText"]
    assert "支付方式：储值余额" in result["receiptText"]
    assert "余额支付：50.00元" in result["receiptText"]
    assert "剩余余额：150.00元" in result["receiptText"]

    order = await order_repo.get_order(result["orderId"])
    assert order is not None
    assert json.loads(order.payment)["status"] == "paid"
    assert await balance_fen(db) == 15000
    assert await pay_ledger_count(db) == 1

    request_row = await StaffQuickOrderRequestRepo(db).get("req-direct-0001")
    assert request_row is not None
    assert request_row["status"] == "completed"
    assert request_row["order_id"] == result["orderId"]

    logs = await audit_repo.list_audit(principal().id)
    assert logs[0].action == "quick_order_create"
    assert logs[0].target_type == "order"
    assert logs[0].target_id == result["orderId"]
    detail = logs[0].detail_json
    assert "stored_value_direct" in detail
    assert "req-direct-0001" in detail
    assert PHONE not in detail


@pytest.mark.asyncio
async def test_same_request_id_is_idempotent_without_second_deduction(
    db: aiosqlite.Connection,
) -> None:
    await seed_member(db, balance_fen=20000)
    await seed_product(db)
    service, _order_repo, _audit_repo = build_stack(db)

    first = await service.create_quick_order(
        principal(),
        create_payload("req-direct-0002"),
    )
    await db.commit()
    second = await service.create_quick_order(
        principal(),
        create_payload("req-direct-0002"),
    )
    await db.commit()

    assert second["orderId"] == first["orderId"]
    assert second["paymentStatus"] == "paid"
    assert await order_count(db) == 1
    assert await balance_fen(db) == 15000
    assert await pay_ledger_count(db) == 1


@pytest.mark.asyncio
async def test_insufficient_balance_rolls_back_order_and_marks_failed(
    db: aiosqlite.Connection,
) -> None:
    await seed_member(db, balance_fen=3000)
    await seed_product(db)
    service, _order_repo, _audit_repo = build_stack(db)

    with pytest.raises(ValueError, match="储值余额不足"):
        await service.create_quick_order(
            principal(),
            create_payload("req-direct-0003"),
        )
    await db.commit()

    assert await order_count(db) == 0
    assert await balance_fen(db) == 3000
    assert await pay_ledger_count(db) == 0
    request_row = await StaffQuickOrderRequestRepo(db).get("req-direct-0003")
    assert request_row is not None
    assert request_row["status"] == "failed"
    assert request_row["order_id"] == ""
    assert "储值余额不足" in request_row["error"]

    # 失败请求不允许直接重放，必须换新的 requestId 重新发起。
    with pytest.raises(ValueError, match="上次开单失败"):
        await service.create_quick_order(
            principal(),
            create_payload("req-direct-0003"),
        )


@pytest.mark.asyncio
async def test_wechat_share_card_creates_unpaid_order_with_share_path(
    db: aiosqlite.Connection,
) -> None:
    await seed_member(db, balance_fen=20000)
    await seed_product(db)
    service, order_repo, _audit_repo = build_stack(db)

    result = await service.create_quick_order(
        principal(),
        create_payload("req-wechat-0001", mode=MODE_WECHAT_SHARE_CARD),
    )
    await db.commit()

    assert result["status"] == "pending"
    assert result["paymentStatus"] == "unpaid"
    assert result["sharePath"] == f"/pages/order-detail/index?id={result['orderId']}"
    assert "微信分享待付" in result["receiptText"]
    assert "支付状态：待支付" in result["receiptText"]
    assert await order_count(db) == 1
    assert await balance_fen(db) == 20000
    assert await pay_ledger_count(db) == 0

    order = await order_repo.get_order(result["orderId"])
    assert order is not None
    assert json.loads(order.payment)["status"] == "unpaid"
    request_row = await StaffQuickOrderRequestRepo(db).get("req-wechat-0001")
    assert request_row is not None
    assert request_row["status"] == "completed"
    assert request_row["order_id"] == result["orderId"]


@pytest.mark.asyncio
async def test_missing_or_unbound_member_rejected_and_request_failed(
    db: aiosqlite.Connection,
) -> None:
    await seed_product(db)
    service, _order_repo, _audit_repo = build_stack(db)

    with pytest.raises(ValueError, match="未找到该会员"):
        await service.create_quick_order(
            principal(),
            create_payload("req-missing-0001", phone="13900000000"),
        )
    unbound_phone = "13800000032"
    await seed_unbound_member(db, phone=unbound_phone)
    with pytest.raises(ValueError, match="尚未绑定小程序"):
        await service.create_quick_order(
            principal(),
            create_payload("req-unbound-0001", phone=unbound_phone),
        )
    await db.commit()

    assert await order_count(db) == 0
    for request_id in ("req-missing-0001", "req-unbound-0001"):
        request_row = await StaffQuickOrderRequestRepo(db).get(request_id)
        assert request_row is not None
        assert request_row["status"] == "failed"


@pytest.mark.asyncio
async def test_completed_request_replay_ignores_new_mode_and_phone(
    db: aiosqlite.Connection,
) -> None:
    await seed_member(db, balance_fen=20000)
    await seed_product(db)
    service, _order_repo, _audit_repo = build_stack(db)

    first = await service.create_quick_order(
        principal(),
        create_payload("req-replay-0001"),
    )
    await db.commit()
    replay = await service.create_quick_order(
        principal(),
        create_payload(
            "req-replay-0001",
            mode=MODE_WECHAT_SHARE_CARD,
            phone="13900000000",
        ),
    )
    await db.commit()

    assert replay["orderId"] == first["orderId"]
    assert replay["paymentStatus"] == "paid"
    assert "sharePath" not in replay
    assert await order_count(db) == 1
    assert await balance_fen(db) == 15000
    assert await pay_ledger_count(db) == 1


@pytest.mark.asyncio
async def test_complete_conflict_rolls_back_order_and_marks_request_failed(
    db: aiosqlite.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await seed_member(db, balance_fen=20000)
    await seed_product(db)
    service, _order_repo, _audit_repo = build_stack(db)

    async def _stale_complete(
        self: StaffQuickOrderRequestRepo,
        request_id: str,
        order_id: str,
    ) -> bool:
        del self, request_id, order_id
        return False

    monkeypatch.setattr(StaffQuickOrderRequestRepo, "complete", _stale_complete)

    with pytest.raises(ValueError, match="开单请求状态更新冲突"):
        await service.create_quick_order(
            principal(),
            create_payload("req-conflict-0001"),
        )
    await db.commit()

    assert await order_count(db) == 0
    assert await balance_fen(db) == 20000
    assert await pay_ledger_count(db) == 0
    request_row = await StaffQuickOrderRequestRepo(db).get("req-conflict-0001")
    assert request_row is not None
    assert request_row["status"] == "failed"
    assert request_row["order_id"] == ""
    assert "开单请求状态更新冲突" in request_row["error"]


@pytest.mark.asyncio
async def test_non_pickup_fulfillment_is_rejected_before_reserving(
    db: aiosqlite.Connection,
) -> None:
    await seed_member(db, balance_fen=20000)
    await seed_product(db)
    service, _order_repo, _audit_repo = build_stack(db)

    with pytest.raises(ValueError, match="仅支持到店自提"):
        await service.create_quick_order(
            principal(),
            create_payload("req-delivery-0001", fulfillment_method="delivery"),
        )
    await db.commit()

    assert await StaffQuickOrderRequestRepo(db).get("req-delivery-0001") is None
    assert await order_count(db) == 0
    assert await balance_fen(db) == 20000
