"""MiniApp 核心闭环 r70：有赞积分事件缺失 total 时把会员积分余额清零。

复核对象：`app/service/youzan/event_member.py` 的 `_handle_points_event`。

怀疑：该函数用有赞 `total` 覆盖 `member_balance.points` 这一权威投影，
但只对 `unique_id` 做了缺失校验，对 `total` **完全没有校验**。而
`member_helpers.to_int` 对 `None` / 空串 / 非数值一律返回 `0`，于是
`upsert_identity(points=0)` 中的 `points = CASE WHEN ? IS NOT NULL THEN ? ELSE
points END` 会因为 `0 is not None` 成立而把余额**写成 0**。

即：一条 `total` 缺失、为空或非数值的 `POINTS` 事件，就能把会员的全部积分
余额清零。流水侧同样写成 `total=0`，看起来是一条合法的「有赞权威余额为 0」
声明，按流水对账看不出这是畸形输入导致的写坏。

这与 r69 不同：r69 是「有赞 total 覆盖本地发分」，属语义冲突；
本条是**缺失输入未校验**导致的错误写入，不需要切换权威即可单点修复。
（r79 已一并修复 r69：外部镜像改走 `mirror_youzan_points` 锚点口径，
`upsert_identity` 的 `points` 绝对覆盖参数已从签名中移除。）

本文件用真实有赞会员域 webhook 入口验证：`total` 缺失 / 空串 / 非数值三种
畸形输入都不得改写本地积分余额投影。
"""

import aiosqlite
import pytest

from app.config import settings
from app.database import close_db, init_db
from app.repository.member_balance_repo import MemberBalanceRepo
from app.service.youzan.event_member import handle_member_event

MOBILE = "13800003070"
OPENID = "points_total_guard_r70_001"
INITIAL_POINTS = 500


async def _seed_member(connection: aiosqlite.Connection) -> None:
    """写入会员身份链与有赞镜像的积分余额行。"""
    await connection.execute(
        "INSERT INTO customer_master (id, tenant_id, status, primary_phone, "
        "phone_verified, display_name, identity_confidence, has_miniapp_identity) "
        "VALUES (?, 'yunxi', 'active', ?, 1, 'total 校验会员', 'high', 1)",
        ("cm_points_total_r70_001", MOBILE),
    )
    await connection.execute(
        "INSERT INTO customer_identity_links (id, tenant_id, customer_id, "
        "identity_type, identity_value, identity_value_normalized, source_system, "
        "link_status, verification_status, confidence_score) "
        "VALUES (?, 'yunxi', ?, 'miniapp_openid', ?, ?, 'miniapp', 'active', "
        "'verified', 100)",
        ("cil_points_total_r70_001", "cm_points_total_r70_001", OPENID, OPENID),
    )
    # r79：走真实导入入口写入外部锚点，使「余额来自有赞权威总额、本地净额为 0」
    # 被如实表达；直接 INSERT 会让 `youzan_points_base` 停在默认 0。
    await MemberBalanceRepo(connection).mirror_youzan_points(
        mobile=MOBILE,
        youzan_total=INITIAL_POINTS,
    )
    await connection.commit()


async def _deliver_points_event(
    connection: aiosqlite.Connection,
    *,
    unique_id: str,
    occurred_at: str,
    total_present: bool = True,
    total_value: object = "",
) -> None:
    """用真实有赞会员域 webhook 入口投递一条 POINTS 事件。

    `total_present=False` 时完全省略 `total` 字段，用于模拟畸形 / 字段变体 payload。
    """
    msg: dict = {
        "unique_id": unique_id,
        "mobile": MOBILE,
        "yz_open_id": f"yz_{OPENID}",
        "amount": 50,
        "event_type": "points",
    }
    if total_present:
        msg["total"] = total_value
    await handle_member_event(connection, None, "POINTS", msg, occurred_at)
    await connection.commit()


async def _read_points(connection: aiosqlite.Connection) -> int:
    """读取本地积分余额投影。"""
    rows = await connection.execute_fetchall(
        "SELECT points FROM member_balance WHERE mobile = ?", (MOBILE,)
    )
    return int(rows[0]["points"]) if rows else 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("label", "total_present", "total_value"),
    [
        ("total 字段缺失", False, ""),
        ("total 为空串", True, ""),
        ("total 为 null", True, None),
        ("total 为非数值", True, "not-a-number"),
    ],
)
async def test_malformed_youzan_points_event_must_not_zero_out_balance(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    label: str,
    total_present: bool,
    total_value: object,
) -> None:
    """`total` 不可用的有赞积分事件不得把会员积分余额清零。

    这是权威余额投影的写坏：`to_int` 把不可用输入一律折叠成 `0`，而
    `upsert_identity` 的 `CASE WHEN ? IS NOT NULL` 对 `0` 成立，于是畸形 payload
    直接落成「余额 0」。修复后应保留原余额并把该事件当作不可信输入跳过覆盖。
    """
    database_path = tmp_path / f"points-total-guard-r70-{label}.db"
    connection = await init_db(str(database_path))
    try:
        monkeypatch.setattr(settings, "POINTS_AUTHORITY", "youzan")
        monkeypatch.setattr(settings, "YOUZAN_MOCK_MODE", True)
        await _seed_member(connection)
        assert await _read_points(connection) == INITIAL_POINTS

        await _deliver_points_event(
            connection,
            unique_id=f"yz:points:r70:{label}",
            occurred_at="2026-09-26 16:00:00",
            total_present=total_present,
            total_value=total_value,
        )

        # 契约：不可信的 total 不得改写本地权威余额投影。
        assert await _read_points(connection) == INITIAL_POINTS
    finally:
        await close_db(connection)


@pytest.mark.asyncio
async def test_valid_youzan_points_event_still_applies_external_total(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """合法 `total` 仍必须被应用到余额投影（钉桩对照）。

    修复不能靠「一律不应用」实现——那会把有赞权威镜像整个关掉，用户在有赞
    侧真实积分变动就再也不同步进小程序。

    r79：语义从「绝对覆盖余额」改为「移动外部锚点并按偏移量重算余额」。
    本夹具本地净额为 0，因此两种口径结果相同（640），断言保持不变。
    """
    database_path = tmp_path / "points-total-guard-r70-valid.db"
    connection = await init_db(str(database_path))
    try:
        monkeypatch.setattr(settings, "POINTS_AUTHORITY", "youzan")
        monkeypatch.setattr(settings, "YOUZAN_MOCK_MODE", True)
        await _seed_member(connection)

        await _deliver_points_event(
            connection,
            unique_id="yz:points:r70:valid",
            occurred_at="2026-09-26 16:05:00",
            total_present=True,
            total_value=640,
        )

        assert await _read_points(connection) == 640
    finally:
        await close_db(connection)
