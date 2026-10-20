"""会员储值/积分/优惠券账务域 M1 测试。"""

import aiosqlite
import pytest

from app.config import settings
from app.database import db_conn_var
from app.repository.base import DatabaseHandle
from app.repository.customer_master_repo import CustomerMasterRepo
from app.repository.member_balance_repo import MemberBalanceRepo
from app.service.channels.storefront import StorefrontAuthService
from app.service.member_loyalty import MemberLoyaltyImportService
from app.service.youzan.event_member import handle_member_event
from app.service.youzan.event_handler import YouzanEventHandler
from app.service.youzan.member_api import (
    COUPON_CODE_LIST_API_NAME,
    COUPON_GROUP_DETAIL_API_NAME,
    COUPON_LIST_API_NAME,
    MEMBER_CARD_LIST_API_NAME,
    POINTS_QUERY_API_NAME,
)


class FakeMemberClient:
    """模拟有赞会员账务域 API 响应。

    响应形状按 **2026-10-20 生产实测** 固定：买家券接口的 `data` 直接是数组，
    会员卡列表在 `items`，券模板详情是扁平 CouponGroup。
    """

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
            return {"code": 200, "success": True, "data": list(self._coupons)}
        if api_name == COUPON_CODE_LIST_API_NAME:
            return {"code": 200, "success": True, "data": []}
        if api_name == COUPON_GROUP_DETAIL_API_NAME:
            return {"code": 200, "success": True, "data": dict(self._coupon_detail)}
        if api_name == MEMBER_CARD_LIST_API_NAME:
            return {
                "code": 200,
                "success": True,
                "data": {
                    "total": len(self._cards),
                    "page": 1,
                    "page_size": 30,
                    "items": list(self._cards),
                },
            }
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
        coupon_detail={
            "id": 32035241,
            "title": "20元优惠卷",
            "preferential_type": 1,
            "denominations": 2000,
            "condition": 5000,
            "valid_start_time": 1727340981000,
            "valid_end_time": 4102416000000,
        }
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
    assert rows[0]["title"] == "20元优惠卷"
    assert rows[0]["value_fen"] == 2000
    assert rows[0]["source"] == "webhook"
    assert rows[0]["occurred_at"] == "2026-08-12 11:00:00"


@pytest.mark.asyncio
async def test_coupon_event_maps_youzan_card_take_to_local_take(
    db: aiosqlite.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """有赞推送的 CARD_TAKE 必须映射成本地 TAKE。

    本地券引擎只认 TAKE/CONSUME/BACK：上游词表原样落库会让券永远匹配不上
    TAKE 判断（券在「我的券」里看得见却无法核销，等同漏券）。
    2026-10-20 生产实测：有赞推送的状态词表是 CARD_TAKE / CARD_CONSUME。
    """
    monkeypatch.setattr(settings, "YOUZAN_MOCK_MODE", False)
    client = FakeMemberClient(
        coupon_detail={
            "id": 32035241,
            "title": "20元优惠卷",
            "preferential_type": 1,
            "denominations": 2000,
            "condition": 5000,
        }
    )
    await handle_member_event(
        db=db,
        youzan_client=client,
        event_type="COUPON_CUSTOMER_PROMOTION",
        msg_obj={
            "id": "c2",
            "status": "CARD_TAKE",
            "mobile": "13800000000",
            "coupon_group_id": "32035241",
        },
        updated_at_str="2026-08-12 11:05:00",
    )

    rows = await db.execute_fetchall(
        "SELECT status, title, value_fen FROM coupon_inventory WHERE coupon_id = ?",
        ("c2",),
    )
    assert len(rows) == 1
    assert rows[0]["status"] == "TAKE"
    assert rows[0]["value_fen"] == 2000


@pytest.mark.asyncio
async def test_coupon_event_skips_unmappable_status(
    db: aiosqlite.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """无法映射的状态（已失效/已过期）必须跳过，不得退化成可用券。"""
    monkeypatch.setattr(settings, "YOUZAN_MOCK_MODE", False)
    await handle_member_event(
        db=db,
        youzan_client=FakeMemberClient(),
        event_type="COUPON_CUSTOMER_PROMOTION",
        msg_obj={
            "id": "c3",
            "status": "CARD_INVALID",
            "mobile": "13800000000",
            "coupon_group_id": "32035241",
        },
        updated_at_str="2026-08-12 11:06:00",
    )

    rows = await db.execute_fetchall("SELECT coupon_id FROM coupon_inventory")
    assert rows == []


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
async def test_event_handler_resolves_request_context_db(
    db: aiosqlite.Connection,
) -> None:
    """组装根以 db=None 构造时，事件处理器应使用当前上下文连接。"""
    handler = YouzanEventHandler(
        db=None,
        knowledge_retriever=None,
        youzan_client=FakeMemberClient(),
        audit_repo=None,
    )
    token = db_conn_var.set(DatabaseHandle(db))
    try:
        await handler.handle_system_event(
            payload={
                "msg": {
                    "mobile": "13900000001",
                    "name": "上下文会员",
                    "is_member": 1,
                }
            },
            event_type="SCRM_CUSTOMER_EVENT",
            updated_at_str="2026-08-12 13:10:00",
            msg_id="msg-context-1",
        )
    finally:
        db_conn_var.reset(token)

    rows = await db.execute_fetchall(
        "SELECT mobile, display_name, is_member FROM member_balance WHERE mobile = ?",
        ("13900000001",),
    )
    assert len(rows) == 1
    assert rows[0]["display_name"] == "上下文会员"
    assert rows[0]["is_member"] == 1


@pytest.mark.asyncio
async def test_mirror_skips_openid_only_when_empty_mobile_exists(
    db: aiosqlite.Connection,
) -> None:
    """空手机号唯一约束下，openid-only 新账户不得重复插入空 mobile。"""
    await db.execute(
        "INSERT INTO member_balance (mobile, points, stored_value_fen, principal_fen) "
        "VALUES ('', 0, 0, 0)"
    )
    await db.commit()

    result = await MemberBalanceRepo(db).mirror_youzan_points(
        mobile="",
        yz_open_id="openid-without-mobile",
        youzan_total=10,
    )

    assert result == 0
    rows = await db.execute_fetchall("SELECT COUNT(*) AS count FROM member_balance")
    assert rows[0]["count"] == 1


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
async def test_v040_backfill_repairs_bare_balance_and_claim_shows_principal(
    db: aiosqlite.Connection,
) -> None:
    """裸写总额后重跑 v040：本金被补齐、总额不变，认领回显 principalFen。"""
    mobile = "13800000007"
    await db.execute(
        "INSERT INTO member_balance (mobile, stored_value_fen, bonus_fen) "
        "VALUES (?, ?, ?)",
        (mobile, 8000, 0),
    )
    await db.commit()
    before = await db.execute_fetchall(
        "SELECT principal_fen FROM member_balance WHERE mobile = ? LIMIT 1",
        (mobile,),
    )
    assert int(before[0]["principal_fen"]) == 0

    # 模拟升级到 v040：丢弃版本记录后重跑迁移，回填语句应补齐本金
    await db.execute("DELETE FROM _schema_version WHERE version = ?", (40,))
    await db.commit()
    from app.migrations.runner import run_migrations

    assert await run_migrations(db) == 1

    repaired = await db.execute_fetchall(
        "SELECT stored_value_fen, principal_fen, bonus_fen FROM member_balance "
        "WHERE mobile = ? LIMIT 1",
        (mobile,),
    )
    assert (
        int(repaired[0]["stored_value_fen"]),
        int(repaired[0]["principal_fen"]),
        int(repaired[0]["bonus_fen"]),
    ) == (8000, 8000, 0)

    claimed = await StorefrontAuthService(
        customer_repo=CustomerMasterRepo(db),
        member_balance_repo=MemberBalanceRepo(db),
        db=db,
    ).claim_member_by_phone(user_id="wx_legacy_split", phone=mobile)
    assert claimed["storedValueFen"] == 8000
    assert claimed["principalFen"] == 8000
    assert claimed["bonusFen"] == 0

    # 导入路径绝对覆盖总额时同步维护本金结构
    await MemberBalanceRepo(db).upsert_identity(mobile=mobile, stored_value_fen=6000)
    overridden = await db.execute_fetchall(
        "SELECT stored_value_fen, principal_fen, bonus_fen FROM member_balance "
        "WHERE mobile = ? LIMIT 1",
        (mobile,),
    )
    assert (
        int(overridden[0]["stored_value_fen"]),
        int(overridden[0]["principal_fen"]),
        int(overridden[0]["bonus_fen"]),
    ) == (6000, 6000, 0)


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
