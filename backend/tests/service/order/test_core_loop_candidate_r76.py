"""MiniApp 核心闭环 r76：主体删除漏掉客户主档层的复现。

r75 修好了 `payment_transactions` / `delivery_orders` 两张硬外键子表，本轮把
视线移到删除链路的**客户主档层**（`customer_master` / `customer_identity_links`
/ `customer_source_snapshots`）。

候选一（真实缺陷）：`PrivacyRepo._customer_ids` 与 `_delete_customer_records`
第 1 步都用裸 `identity_value = user_id` 匹配，但生产链路里
`StorefrontAuthService.login` 下发的前台 user_id 是 `wx_{openid}`
（`auth.py`），而身份链接存的是**裸 openid**
（`CustomerMasterService.build_miniapp_openid_identity` 直接透传 openid，
`MemberBalanceService.resolve_mobile` 读之前也先 `extract_openid` 剥前缀）。
于是 `_customer_ids` 对每个真实小程序用户都返回空列表，删除照样返回
`status=revoked`，三张客户主档表却整行留存。

候选二（真实缺陷，且修好候选一后立刻变成 P1）：`_delete_customer_records`
第 1 步先删 `customer_identity_links`，第 2、3 步才删
`customer_source_snapshots` / `customer_merge_reviews`。两张子表都声明了
`REFERENCES customer_identity_links(id)` 且建库 `PRAGMA foreign_keys = ON`、
`on_delete=NO ACTION`，所以只要快照引用了将被删的链接，删除事务就会抛
`FOREIGN KEY constraint failed` 并整体回滚。当前因候选一使第 1 步匹配不到
任何行而不可触发；**一旦修好候选一，这条路径对每个真实用户立刻生效**，
因此两者必须同批修复。

三个用例都只通过真实业务动作造数（`CustomerMasterService` 工厂 +
`CustomerMasterRepo` 写入 + `OrderRepo.create_order`），不手工 UPDATE 终态。
"""

import json

import aiosqlite
import pytest

from app.database import close_db, init_db
from app.models.customer_master import (
    CustomerMasterCreate,
    CustomerSourceSnapshotCreate,
)
from app.models.order import Order, OrderStatus
from app.repository.base import DatabaseHandle
from app.repository.customer_master_repo import CustomerMasterRepo
from app.repository.order_repo import OrderRepo
from app.repository.privacy_repo import PrivacyRepo
from app.service.customer.master import CustomerMasterService
from app.service.order.payment_state import now_text
from app.service.privacy_lifecycle import PrivacyLifecycleService

MOBILE = "13800003078"
OPENID = "core_loop_r76_001"
USER_ID = f"wx_{OPENID}"
ORDER_ID = "order_core_loop_r76_001"
ORDER_AMOUNT_FEN = 10_000


async def _seed_customer_master_by_factory(
    connection: aiosqlite.Connection,
    *,
    tenant_id: str = "yunxi",
    openid: str = OPENID,
    with_snapshot: bool = True,
) -> tuple[CustomerMasterRepo, str, str]:
    """用真实工厂造出「客户主档 + 身份链接（+ 来源快照）」。

    身份链接走 `CustomerMasterService.build_miniapp_openid_identity`，与生产
    保持同一条构造路径：链接里存的是裸 openid，不带 `wx_` 前缀。
    """
    repo = CustomerMasterRepo(DatabaseHandle(connection))
    master = await repo.create_master(
        CustomerMasterCreate(
            tenant_id=tenant_id,
            primary_phone=MOBILE,
            phone_verified=1,
            display_name="核心闭环会员",
            first_source="miniapp",
            has_miniapp_identity=1,
        )
    )
    link = await repo.create_identity_link(
        CustomerMasterService.build_miniapp_openid_identity(
            customer_id=master.id,
            tenant_id=tenant_id,
            openid=openid,
            source_system="miniapp",
        )
    )
    if with_snapshot:
        await repo.create_source_snapshot(
            CustomerSourceSnapshotCreate(
                tenant_id=tenant_id,
                customer_id=master.id,
                identity_link_id=link.id,
                source_system="miniapp",
                source_record_id=f"miniapp-customer-{openid}",
                source_batch_id=f"batch-r76-{openid}",
                snapshot_json=json.dumps({"openid": openid}, ensure_ascii=False),
                normalized_json=json.dumps({"openid": openid}, ensure_ascii=False),
                field_hash="r76-field-hash",
                captured_at=now_text(),
            )
        )
    return repo, master.id, link.id


async def _seed_order_for_subject(connection: aiosqlite.Connection) -> None:
    """写入会员余额、会话与一笔未支付订单。"""
    await connection.execute(
        "INSERT INTO member_balance (mobile, points, stored_value_fen) VALUES (?, 0, 0)",
        (MOBILE,),
    )
    await connection.execute(
        "INSERT INTO sessions (id, channel, user_id, status) "
        "VALUES (?, 'miniapp', ?, 'active')",
        (f"session_{ORDER_ID}", USER_ID),
    )
    await OrderRepo(DatabaseHandle(connection)).create_order(
        Order(
            id=ORDER_ID,
            session_id=f"session_{ORDER_ID}",
            channel="miniapp",
            user_id=USER_ID,
            products="[]",
            total_amount=ORDER_AMOUNT_FEN / 100,
            delivery="{}",
            payment=json.dumps(
                {"status": "unpaid", "method": "", "balanceFen": 0},
                ensure_ascii=False,
            ),
            status=OrderStatus.PENDING,
            remark="",
            created_at=now_text(),
            updated_at=now_text(),
        )
    )
    await connection.commit()


async def _customer_layer_counts(
    connection: aiosqlite.Connection,
) -> tuple[int, int, int]:
    """返回 (customer_master, customer_identity_links, customer_source_snapshots) 行数。"""
    counts: list[int] = []
    for table in (
        "customer_master",
        "customer_identity_links",
        "customer_source_snapshots",
    ):
        rows = await connection.execute_fetchall(f"SELECT COUNT(*) AS c FROM {table}")
        counts.append(int(rows[0]["c"]))
    return counts[0], counts[1], counts[2]


@pytest.mark.asyncio
async def test_real_miniapp_erasure_must_clear_customer_master_layer(tmp_path) -> None:
    """真实小程序用户删除主体后，客户主档层不得整行留存。

    怀疑：`_customer_ids` 用裸 `identity_value = user_id` 匹配，但生产 user_id
    是 `wx_{openid}`、身份链接存裸 openid，因此匹配恒为空，删除返回 revoked
    却把 `customer_master` / `customer_identity_links` /
    `customer_source_snapshots` 全部留下。
    验证：用真实工厂造出与生产同构的数据（链接存裸 openid），再以
    `wx_{openid}` 调用 `delete_subject`。
    """
    connection = await init_db(str(tmp_path / "customer-layer-r76.db"))
    handle = DatabaseHandle(connection)
    try:
        await _seed_customer_master_by_factory(connection, with_snapshot=False)
        await _seed_order_for_subject(connection)
        assert await _customer_layer_counts(connection) == (1, 1, 0)

        await PrivacyLifecycleService(PrivacyRepo(handle)).delete_subject(USER_ID)

        # 防空洞断言：订单确实被删了，说明删除事务真的执行并提交了，
        # 下面的客户层残留不是「整笔请求失败」造成的假象。
        assert await OrderRepo(handle).get_order(ORDER_ID) is None
        assert await _customer_layer_counts(connection) == (0, 0, 0)
    finally:
        await close_db(connection)


@pytest.mark.asyncio
async def test_export_must_include_customer_layer_for_real_miniapp_subject(
    tmp_path,
) -> None:
    """主体导出必须覆盖真实小程序用户的客户主档层。

    怀疑：与候选一同源。`export_subject` 的 `customer_master` 段按
    `_customer_ids` 的结果取行，`customer_ids` 为空时该段恒为空数组，
    顾客的导出件里看不到自己的客户主档与身份链接。
    """
    connection = await init_db(str(tmp_path / "export-customer-layer-r76.db"))
    handle = DatabaseHandle(connection)
    try:
        await _seed_customer_master_by_factory(connection, with_snapshot=False)

        exported = await PrivacyLifecycleService(PrivacyRepo(handle)).export_subject(
            USER_ID
        )
        records = exported["records"]
        assert records["customer_master"]
        assert records["customer_identity_links"]
    finally:
        await close_db(connection)


@pytest.mark.asyncio
async def test_erasure_must_clear_snapshot_children_before_identity_links(
    tmp_path,
) -> None:
    """快照引用身份链接时，删除必须先清子表再清链接。

    怀疑：`_delete_customer_records` 先删 `customer_identity_links`，而
    `customer_source_snapshots.identity_link_id` 声明
    `REFERENCES customer_identity_links(id)`（NO ACTION）且
    `PRAGMA foreign_keys = ON`，删除会在第 1 步抛外键错误并整体回滚。
    验证：让第 1 步的匹配条件真实命中（链接 identity_value 等于 user_id），
    并用真实写入接口造出引用该链接的快照。
    """
    connection = await init_db(str(tmp_path / "fk-order-r76.db"))
    handle = DatabaseHandle(connection)
    try:
        _, master_id, link_id = await _seed_customer_master_by_factory(
            connection, openid=USER_ID, with_snapshot=True
        )
        # 快照必须真的挂在链接上，否则第 1 步删链接不会触发外键检查。
        assert master_id and link_id
        assert await _customer_layer_counts(connection) == (1, 1, 1)

        await PrivacyLifecycleService(PrivacyRepo(handle)).delete_subject(USER_ID)

        assert await _customer_layer_counts(connection) == (0, 0, 0)
    finally:
        await close_db(connection)
