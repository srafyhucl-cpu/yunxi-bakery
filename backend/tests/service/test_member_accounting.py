"""会员储值/积分/优惠券账务域 M1 测试。"""

import aiosqlite
import pytest

from app.config import settings
from app.service.member_loyalty import MemberLoyaltyImportService
from app.service.youzan.event_member import handle_member_event
from app.service.youzan.event_handler import YouzanEventHandler
from app.service.youzan.member_api import (
    COUPON_GROUP_DETAIL_API_NAME,
    COUPON_LIST_API_NAME,
    MEMBER_CARD_LIST_API_NAME,
    POINTS_QUERY_API_NAME,
)


class FakeMemberClient:
    """模拟有赞会员账务域 API 响应。"""

    def __init__(
        self,
        *,
        points: dict | None = None,
        cards: list[dict] | None = None,
        coupons: list[dict] | None = None,
        coupon_detail: dict | None = None,
    ) -> None:
        self._points = points or {}
        self._cards = cards or []
        self._coupons = coupons or []
        self._coupon_detail = coupon_detail or {}
        self.calls: list[str] = []

    async def call_api(self, api_name: str, version: str, params: dict) -> dict:
        self.calls.append(api_name)
        if api_name == POINTS_QUERY_API_NAME:
            return {"data": self._points}
        if api_name == COUPON_LIST_API_NAME:
            return {"data": {"coupons": self._coupons, "total": len(self._coupons)}}
        if api_name == COUPON_GROUP_DETAIL_API_NAME:
            return {"data": self._coupon_detail}
        if api_name == MEMBER_CARD_LIST_API_NAME:
            return {"data": {"cards": self._cards}}
        return {"data": {}}


async def test_member_accounting_tables_created(db: aiosqlite.Connection) -> None:
    """初始化数据库后应包含三张账务表与关键字段。"""
    for table in ("member_balance", "points_ledger", "coupon_inventory"):
        columns = await _column_names(db, table)
        assert "id" in columns
        assert "mobile" in columns
    balance_columns = await _column_names(db, "member_balance")
    assert {"points", "stored_value_fen", "is_member", "card_no"}.issubset(
        balance_columns
    )
    ledger_columns = await _column_names(db, "points_ledger")
    assert {"unique_id", "amount", "total", "event_type"}.issubset(ledger_columns)
    coupon_columns = await _column_names(db, "coupon_inventory")
    assert {
        "coupon_id",
        "coupon_group_id",
        "status",
        "order_no",
        "title",
        "value_fen",
    }.issubset(coupon_columns)


@pytest.mark.asyncio
async def test_points_event_writes_ledger_and_balance(
    db: aiosqlite.Connection,
) -> None:
    """POINTS 事件应写积分流水并同步余额快照，unique_id 去重。"""
    await handle_member_event(
        db=db,
        youzan_client=FakeMemberClient(),
        event_type="POINTS",
        msg_obj={
            "unique_id": "u1",
            "mobile": "13800000000",
            "yz_open_id": "o1",
            "amount": "10",
            "total": "100",
            "event_type": "INCREASE",
        },
        updated_at_str="2026-08-12 10:00:00",
    )
    await handle_member_event(
        db=db,
        youzan_client=FakeMemberClient(),
        event_type="points",
        msg_obj={
            "unique_id": "u1",
            "mobile": "13800000000",
            "amount": "10",
            "total": "100",
        },
        updated_at_str="2026-08-12 10:01:00",
    )

    ledger_rows = await db.execute_fetchall(
        "SELECT unique_id, amount, total, source FROM points_ledger"
    )
    assert len(ledger_rows) == 1
    assert ledger_rows[0]["unique_id"] == "u1"
    assert ledger_rows[0]["amount"] == 10
    assert ledger_rows[0]["total"] == 100
    assert ledger_rows[0]["source"] == "webhook"

    balance_rows = await db.execute_fetchall(
        "SELECT mobile, points, yz_open_id FROM member_balance"
    )
    assert len(balance_rows) == 1
    assert balance_rows[0]["mobile"] == "13800000000"
    assert balance_rows[0]["points"] == 100
    assert balance_rows[0]["yz_open_id"] == "o1"


@pytest.mark.asyncio
async def test_points_event_without_unique_id_skipped(
    db: aiosqlite.Connection,
) -> None:
    """缺少 unique_id 的积分事件应跳过写入。"""
    await handle_member_event(
        db=db,
        youzan_client=FakeMemberClient(),
        event_type="POINTS",
        msg_obj={"mobile": "13800000000", "amount": "5", "total": "50"},
        updated_at_str="2026-08-12 10:00:00",
    )
    rows = await db.execute_fetchall("SELECT id FROM points_ledger")
    assert len(rows) == 0


@pytest.mark.asyncio
async def test_coupon_event_with_detail_and_dedup(
    db: aiosqlite.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """优惠券事件应反查券详情补全标题面额，并按组合键去重。"""
    monkeypatch.setattr(settings, "YOUZAN_MOCK_MODE", False)
    client = FakeMemberClient(
        coupon_detail={"coupon_group": {"title": "满100减10", "value": 1000}}
    )
    payload = {
        "id": "c1",
        "status": "TAKE",
        "mobile": "13800000000",
        "coupon_group_id": "g1",
        "order_no": "E123",
    }
    for _ in range(2):
        await handle_member_event(
            db=db,
            youzan_client=client,
            event_type="COUPON_CUSTOMER_PROMOTION",
            msg_obj=payload,
            updated_at_str="2026-08-12 11:00:00",
        )

    rows = await db.execute_fetchall(
        "SELECT coupon_id, status, mobile, title, value_fen, source, occurred_at "
        "FROM coupon_inventory"
    )
    assert len(rows) == 1
    assert rows[0]["coupon_id"] == "c1"
    assert rows[0]["status"] == "TAKE"
    assert rows[0]["title"] == "满100减10"
    assert rows[0]["value_fen"] == 1000
    assert rows[0]["source"] == "webhook"
    assert rows[0]["occurred_at"] == "2026-08-12 11:00:00"


@pytest.mark.asyncio
async def test_customer_and_card_events_update_balance(
    db: aiosqlite.Connection,
) -> None:
    """客户身份与会员卡事件应更新 member_balance 快照。"""
    await handle_member_event(
        db=db,
        youzan_client=FakeMemberClient(),
        event_type="SCRM_CUSTOMER_EVENT",
        msg_obj={"mobile": "13800000000", "name": "张三", "is_member": 1},
        updated_at_str="2026-08-12 12:00:00",
    )
    await handle_member_event(
        db=db,
        youzan_client=FakeMemberClient(),
        event_type="SCRM_CUSTOMER_CARD",
        msg_obj={
            "mobile": "13800000000",
            "card_alias": "银卡",
            "card_no": "CARD001",
            "yz_open_id": "o1",
            "status": "ACTIVE",
        },
        updated_at_str="2026-08-12 12:05:00",
    )

    rows = await db.execute_fetchall(
        "SELECT display_name, is_member, card_alias, card_no, card_status, "
        "yz_open_id FROM member_balance"
    )
    assert len(rows) == 1
    assert rows[0]["display_name"] == "张三"
    assert rows[0]["is_member"] == 1
    assert rows[0]["card_alias"] == "银卡"
    assert rows[0]["card_no"] == "CARD001"
    assert rows[0]["card_status"] == "ACTIVE"
    assert rows[0]["yz_open_id"] == "o1"


@pytest.mark.asyncio
async def test_event_handler_routes_member_events(db: aiosqlite.Connection) -> None:
    """事件分发器应把会员事件路由到账务域处理器。"""
    handler = YouzanEventHandler(
        db=db,
        knowledge_retriever=None,
        youzan_client=FakeMemberClient(),
        audit_repo=None,
    )
    await handler.handle_system_event(
        payload={
            "msg": {
                "unique_id": "h1",
                "mobile": "13900000000",
                "amount": "3",
                "total": "30",
            }
        },
        event_type="POINTS",
        updated_at_str="2026-08-12 13:00:00",
        msg_id="msg-h1",
    )
    rows = await db.execute_fetchall(
        "SELECT unique_id FROM points_ledger WHERE unique_id = ?", ("h1",)
    )
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_import_service_dry_run_and_apply(
    db: aiosqlite.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """导入服务应支持干跑与幂等落库。"""
    monkeypatch.setattr(settings, "YOUZAN_MOCK_MODE", False)
    client = FakeMemberClient(
        points={"points": 250},
        cards=[{"card_alias": "金卡", "card_no": "G1", "status": "ACTIVE"}],
        coupons=[
            {
                "coupon_id": "ic1",
                "coupon_group_id": "ig1",
                "status": "TAKE",
                "title": "导入券",
                "value": 500,
            }
        ],
    )
    service = MemberLoyaltyImportService(db, client, tenant_id="yunxi")

    dry_stats = await service.import_one(
        "13800000000", customer_id="cust-1", should_apply=False
    )
    assert dry_stats["points_total"] == 250
    assert dry_stats["cards"] == 1
    assert dry_stats["coupons"] == 1
    assert dry_stats["errors"] == []
    coupon_rows = await db.execute_fetchall("SELECT id FROM coupon_inventory")
    balance_rows = await db.execute_fetchall("SELECT id FROM member_balance")
    assert len(coupon_rows) == 0
    assert len(balance_rows) == 0

    for _ in range(2):
        apply_stats = await service.import_one(
            "13800000000", customer_id="cust-1", should_apply=True
        )
    assert apply_stats["errors"] == []
    coupon_rows = await db.execute_fetchall(
        "SELECT coupon_id, status, mobile, source FROM coupon_inventory"
    )
    assert len(coupon_rows) == 1
    assert coupon_rows[0]["source"] == "import"
    balance_rows = await db.execute_fetchall(
        "SELECT mobile, points, is_member, card_alias FROM member_balance"
    )
    assert len(balance_rows) == 1
    assert balance_rows[0]["points"] == 250
    assert balance_rows[0]["is_member"] == 1
    assert balance_rows[0]["card_alias"] == "金卡"


async def _column_names(db: aiosqlite.Connection, table_name: str) -> set[str]:
    rows = await db.execute_fetchall(
        "SELECT name FROM pragma_table_info(?)", (table_name,)
    )
    return {row["name"] for row in rows}


@pytest.mark.asyncio
async def test_points_event_local_authority_keeps_local_balance(
    db: aiosqlite.Connection, monkeypatch
) -> None:
    """local 权威模式下 POINTS 事件只写流水，不覆盖本地余额。"""
    from app.config import settings

    monkeypatch.setattr(settings, "POINTS_AUTHORITY", "local")
    await handle_member_event(
        db=db,
        youzan_client=FakeMemberClient(),
        event_type="POINTS",
        msg_obj={
            "unique_id": "u-local-1",
            "mobile": "13800000000",
            "amount": "10",
            "total": "999",
            "event_type": "INCREASE",
        },
        updated_at_str="2026-08-13 10:00:00",
    )
    rows = await db.execute_fetchall(
        "SELECT points FROM member_balance WHERE mobile = '13800000000' LIMIT 1"
    )
    assert not rows
