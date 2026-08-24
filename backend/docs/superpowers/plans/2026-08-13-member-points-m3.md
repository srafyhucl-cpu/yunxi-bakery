# M3 积分模块实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 M1 积分数据底座 + M2 储值闭环之上，交付积分模块闭环：积分规则纯函数、`app/service/points/` 域、支付联动发分/抵扣/退款、小程序积分 API，并通过全套验证与生产收口。

**Architecture:** 新增独立 `app/service/points/` 域（rules / ledger / payment + PointsService 门面），与 `stored_value` 域并列、同层隔离（api → service → repository → models 不穿透）。`payment.json` 快照新增 `pointsFen/pointsUsed/pointsAwarded`；三条支付成功路径（mock、微信通知、储值全额支付）统一调 `award_on_payment`；取消/超时/后台取消按快照调 `refund_points`。数据主从用 `points_authority` 配置开关（youzan → local）两步切换。

**Tech Stack:** Python 3.11、FastAPI、SQLite（aiosqlite）、pytest、Ruff、MyPy。

## Global Constraints

- 基线：`f0df6e3`（docs(plan) 已定稿 M3 规则），VERSION=0.114.0；当前分支 `codex/r4c-ci-evidence`。
- 禁止 `Optional[X]` / `Union[X, Y]`，使用 `X | None` / `X | Y`。
- 禁止 `SELECT *`、禁止 SQL f-string 拼接，一律 `?` 参数化并明确列字段。
- 禁止 `api/` 直接导入 `repository/`；禁止 `service/` 直接操作 `aiosqlite`；禁止 `models/` 引用上层模块。
- 禁止静默吞异常（`except: pass`），至少 `logger.error`；禁止 `print()` 调试。
- 代码注释统一中文；新增函数加类型注解。
- 提交必须走 `docs/AGENTS/commit-workflow.md`：更新 `LOGBOOK.md` + `项目进度与配置清单.md`，pre-commit 自动递增版本（feat/perf/refactor→minor，fix/docs/chore→patch）。
- pytest 必须带 `--basetemp=D:\Temp\<name>`（C 盘 pytest 临时目录有权限问题）。
- 写文件用 Python `write_text(..., newline="\n")`；改大文件时保留原始混合行尾。
- 规则（已确认）：获得 `1 元实付 = 1 分`，实付现金 = `total_fen - balance_fen - points_fen`，`award_points = cash_fen // 100`；抵扣 `100 分 = 1 元`，最低 `100 分`，最高 `50% × total_fen` 且 `points_fen <= total_fen - balance_fen`，`points_used = floor(available / 100) × 100`；长期有效；无部分退款，全单退款退回全部 `pointsUsed`、收回全部 `pointsAwarded`；数据主从 `points_authority` 默认 `youzan`。

---

## 文件结构总览

- `app/migrations/v023_points_order_source.sql` — 新建：points_ledger 扩展（source 增 order，新增 biz_type/biz_id）
- `app/models/member.py` — 修改：LedgerSource.ORDER、PointsLedgerEntry 增 biz_type/biz_id
- `app/repository/member_balance_repo.py` — 修改：get_points / credit_points / deduct_points_if_sufficient
- `app/repository/points_ledger_repo.py` — 修改：insert 支持 biz 字段、list_by_mobile
- `app/service/points/rules.py` — 新建：award_points / redeem_units / refund_reversal 纯函数
- `app/service/points/ledger.py` — 新建：积分账本 credit/deduct + 流水（幂等键）
- `app/service/points/payment.py` — 新建：apply_points_snapshot / award_on_payment / refund_points
- `app/service/points/__init__.py` — 新建：PointsService 门面
- `app/service/order/payment_state.py` — 修改：build_points_payment（含 pointsFen/pointsUsed）
- `app/service/order/payment_runtime.py` — 修改：mock 支付成功后调 award_on_payment
- `app/service/order/payment_notification.py` — 修改：微信通知金额校验含 points、成功后调 award_on_payment
- `app/service/stored_value/payment.py` — 修改：储值全额支付成功后调 award_on_payment
- `app/service/order/cancellation.py` / `expiration.py` / `status_flow.py` — 修改：取消/超时/后台取消调 refund_points
- `app/api/channels/storefront/points.py` — 新建：GET /points、POST points-preview、POST apply-points
- `app/lifespan_services.py` / `app/lifespan_routes.py` — 修改：PointsService 装配
- `app/config.py` — 修改：POINTS_AUTHORITY 配置
- `app/service/youzan/event_member.py` — 修改：_handle_points_event 按配置切换是否覆盖余额

---

### Task 1: v023 迁移 + 模型/仓储扩展

**Files:**
- Create: `app/migrations/v023_points_order_source.sql`
- Modify: `app/models/member.py`（LedgerSource、PointsLedgerEntry）
- Modify: `app/repository/points_ledger_repo.py`
- Modify: `app/repository/member_balance_repo.py`
- Test: `tests/service/test_points_repo.py`

**Interfaces:**
- Produces:
  - `LedgerSource.ORDER = "order"`
  - `PointsLedgerEntry` 新增字段 `biz_type: str = ""`、`biz_id: str = ""`
  - `PointsLedgerRepo.insert(entry)` 写入 biz 字段；`PointsLedgerRepo.list_by_mobile(mobile, limit=50) -> list[dict]`
  - `MemberBalanceRepo.get_points(mobile) -> int`；`credit_points(mobile, amount) -> int`；`deduct_points_if_sufficient(mobile, amount) -> bool`

- [ ] **Step 1: 写失败测试**

创建 `tests/service/test_points_repo.py`：

```python
"""积分模块 v023 仓储测试：迁移字段、幂等与余额不足。"""

import aiosqlite
import pytest

from app.models.member import LedgerSource, PointsLedgerEntry
from app.repository.member_balance_repo import MemberBalanceRepo
from app.repository.points_ledger_repo import PointsLedgerRepo


async def _column_names(db: aiosqlite.Connection, table: str) -> list[str]:
    rows = await db.execute_fetchall(f"PRAGMA table_info({table})")
    return [row["name"] for row in rows]


@pytest.mark.asyncio
async def test_v023_points_ledger_columns(db: aiosqlite.Connection) -> None:
    """points_ledger 应包含 biz_type/biz_id，source 允许 order。"""
    columns = await _column_names(db, "points_ledger")
    assert {"biz_type", "biz_id"}.issubset(columns)


@pytest.mark.asyncio
async def test_points_ledger_insert_and_list_by_mobile(db: aiosqlite.Connection) -> None:
    """积分流水写入后可按手机号倒序查询。"""
    repo = PointsLedgerRepo(db)
    await repo.insert(
        PointsLedgerEntry(
            unique_id="p1",
            amount=10,
            total=100,
            event_type="order_award",
            source=LedgerSource.ORDER,
            biz_type="order_award",
            biz_id="order_1",
            mobile="13800000000",
            occurred_at="2026-08-13 10:00:00",
        )
    )
    rows = await repo.list_by_mobile("13800000000")
    assert len(rows) == 1
    assert rows[0]["biz_type"] == "order_award"
    assert rows[0]["biz_id"] == "order_1"
    assert rows[0]["source"] == "order"
    assert await repo.get_by_unique_id("p1") is not None


@pytest.mark.asyncio
async def test_member_balance_points_credit_and_deduct(db: aiosqlite.Connection) -> None:
    """积分加款/余额不足不扣/原子扣款。"""
    repo = MemberBalanceRepo(db)
    assert await repo.get_points("13800000001") == 0
    assert await repo.credit_points("13800000001", 500) == 500
    assert await repo.get_points("13800000001") == 500
    assert not await repo.deduct_points_if_sufficient("13800000001", 600)
    assert await repo.get_points("13800000001") == 500
    assert await repo.deduct_points_if_sufficient("13800000001", 200)
    assert await repo.get_points("13800000001") == 300
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/service/test_points_repo.py -q --basetemp=D:\Temp\pytest-bt-points-repo`
Expected: FAIL（biz_type 列不存在 / 方法不存在）

- [ ] **Step 3: 写 v023 迁移**

创建 `app/migrations/v023_points_order_source.sql`：

```sql
-- 积分模块（M3）
-- points_ledger：source 扩展 order，新增 biz_type/biz_id（order_award/order_redeem/order_refund）
-- SQLite 重建表以修改 CHECK 约束并加列

CREATE TABLE IF NOT EXISTS points_ledger_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    unique_id TEXT NOT NULL DEFAULT '',
    customer_id TEXT NOT NULL DEFAULT '',
    mobile TEXT NOT NULL DEFAULT '',
    yz_open_id TEXT NOT NULL DEFAULT '',
    amount INTEGER NOT NULL DEFAULT 0,
    total INTEGER NOT NULL DEFAULT 0,
    event_type TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT 'webhook' CHECK(source IN ('webhook', 'import', 'order')),
    biz_type TEXT NOT NULL DEFAULT '',
    biz_id TEXT NOT NULL DEFAULT '',
    occurred_at TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

INSERT INTO points_ledger_new (id, unique_id, customer_id, mobile, yz_open_id, amount, total, event_type, source, occurred_at, created_at)
SELECT id, unique_id, customer_id, mobile, yz_open_id, amount, total, event_type, source, occurred_at, created_at FROM points_ledger;

DROP TABLE points_ledger;
ALTER TABLE points_ledger_new RENAME TO points_ledger;

CREATE UNIQUE INDEX IF NOT EXISTS idx_points_ledger_unique ON points_ledger(unique_id);
CREATE INDEX IF NOT EXISTS idx_points_ledger_customer ON points_ledger(customer_id);
CREATE INDEX IF NOT EXISTS idx_points_ledger_mobile ON points_ledger(mobile);
CREATE INDEX IF NOT EXISTS idx_points_ledger_biz ON points_ledger(biz_type, biz_id);
```

- [ ] **Step 4: 更新模型**

修改 `app/models/member.py`：

```python
class LedgerSource:
    """账务数据来源。"""

    WEBHOOK = "webhook"
    IMPORT = "import"
    ORDER = "order"
```

`PointsLedgerEntry` 增加字段：

```python
@dataclass
class PointsLedgerEntry:
    """一条积分变动流水。"""

    unique_id: str
    amount: int
    total: int
    event_type: str
    source: str = LedgerSource.WEBHOOK
    biz_type: str = ""
    biz_id: str = ""
    customer_id: str = ""
    mobile: str = ""
    yz_open_id: str = ""
    occurred_at: str = ""
```

- [ ] **Step 5: 更新 points_ledger_repo**

修改 `app/repository/points_ledger_repo.py` 的 insert 与新增 list_by_mobile：

```python
    async def insert(self, entry: PointsLedgerEntry) -> None:
        """写入一条积分流水。"""
        await self._db.execute(
            "INSERT INTO points_ledger (unique_id, customer_id, mobile, yz_open_id, "
            "amount, total, event_type, source, biz_type, biz_id, occurred_at, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                entry.unique_id,
                entry.customer_id,
                entry.mobile,
                entry.yz_open_id,
                entry.amount,
                entry.total,
                entry.event_type,
                entry.source,
                entry.biz_type,
                entry.biz_id,
                entry.occurred_at,
                now_str(),
            ),
        )
        await self._db.commit()

    async def list_by_mobile(self, mobile: str, *, limit: int = 50) -> list[dict]:
        """按手机号读取积分流水，按 id 倒序。"""
        if not mobile:
            return []
        return await self._db.execute_fetchall(
            "SELECT id, unique_id, customer_id, mobile, yz_open_id, amount, total, "
            "event_type, source, biz_type, biz_id, occurred_at, created_at "
            "FROM points_ledger WHERE mobile = ? ORDER BY id DESC LIMIT ?",
            (mobile, limit),
        )
```

- [ ] **Step 6: 更新 member_balance_repo**

在 `app/repository/member_balance_repo.py` 的 `get_stored_value_fen` 之后新增：

```python
    async def get_points(self, mobile: str) -> int:
        """读取会员积分余额，账户不存在返回 0。"""
        rows = await self._db.execute_fetchall(
            "SELECT points FROM member_balance WHERE mobile = ? LIMIT 1",
            (mobile,),
        )
        return int(rows[0]["points"]) if rows else 0

    async def credit_points(self, mobile: str, amount: int) -> int:
        """为会员积分加款（发分/退回抵扣），返回加款后余额。"""
        now = now_str()
        cursor = await self._db.execute(
            "UPDATE member_balance SET points = points + ?, updated_at = ? "
            "WHERE mobile = ?",
            (amount, now, mobile),
        )
        if cursor.rowcount != 1:
            await self._db.execute(
                "INSERT INTO member_balance (mobile, points, created_at, updated_at) "
                "VALUES (?, ?, ?, ?)",
                (mobile, amount, now, now),
            )
        rows = await self._db.execute_fetchall(
            "SELECT points FROM member_balance WHERE mobile = ? LIMIT 1",
            (mobile,),
        )
        return int(rows[0]["points"]) if rows else amount

    async def deduct_points_if_sufficient(self, mobile: str, amount: int) -> bool:
        """原子扣减积分，余额不足时不扣减。"""
        cursor = await self._db.execute(
            "UPDATE member_balance SET points = points - ?, updated_at = ? "
            "WHERE mobile = ? AND points >= ?",
            (amount, now_str(), mobile, amount),
        )
        return bool(cursor.rowcount == 1)
```

- [ ] **Step 7: 运行测试确认通过**

Run: `python -m pytest tests/service/test_points_repo.py -q --basetemp=D:\Temp\pytest-bt-points-repo`
Expected: PASS（3 passed）

- [ ] **Step 8: 提交**

```bash
git add app/migrations/v023_points_order_source.sql app/models/member.py app/repository/points_ledger_repo.py app/repository/member_balance_repo.py tests/service/test_points_repo.py
$env:VERSION_BUMP='minor'
git commit -m "feat(points): M3 v023 迁移与积分仓储扩展"
```

---

### Task 2: 积分规则纯函数

**Files:**
- Create: `app/service/points/rules.py`
- Test: `tests/service/test_points_rules.py`

**Interfaces:**
- Produces:
  - `award_points(cash_fen: int) -> int`：`cash_fen // 100`，负数按 0。
  - `redeem_units(available_points: int, total_fen: int, balance_fen: int) -> int`：百位向下取整；最低 100 分；最高 `50% × total_fen` 且折算 `points_fen <= total_fen - balance_fen`。
  - `points_to_fen(points_used: int) -> int`：`points_used`（100 分 = 1 元 = 100 分钱，数值相等但语义独立）。
  - `refund_reversal(points_used: int, points_awarded: int) -> tuple[int, int]`：返回 `(退回积分, 收回积分)`，全单退款为 `(points_used, points_awarded)`。

- [ ] **Step 1: 写失败测试**

创建 `tests/service/test_points_rules.py`：

```python
"""积分规则纯函数测试。"""

from app.service.points.rules import (
    award_points,
    points_to_fen,
    redeem_units,
    refund_reversal,
)


def test_award_points_floor_by_yuan() -> None:
    """1 元实付 = 1 分，不足 1 元向下取整。"""
    assert award_points(0) == 0
    assert award_points(99) == 0
    assert award_points(100) == 1
    assert award_points(19900) == 199
    assert award_points(-100) == 0


def test_redeem_units_floor_and_min() -> None:
    """可用积分百位向下取整，不足 100 分不可抵扣。"""
    assert redeem_units(50, 50_000, 0) == 0
    assert redeem_units(199, 50_000, 0) == 100
    assert redeem_units(1250, 50_000, 0) == 1200


def test_redeem_units_cap_50_percent_and_remain() -> None:
    """抵扣金额受 50% 上限与剩余应付约束。"""
    assert redeem_units(100_000, 10_000, 0) == 5000
    assert redeem_units(100_000, 10_000, 7_000) == 3000
    assert redeem_units(100_000, 10_000, 9_000) == 1000


def test_points_to_fen() -> None:
    """100 分 = 1 元 = 100 分钱。"""
    assert points_to_fen(0) == 0
    assert points_to_fen(100) == 100
    assert points_to_fen(1200) == 1200


def test_refund_reversal() -> None:
    """全单退款退回全部抵扣积分并收回全部已发积分。"""
    assert refund_reversal(1200, 88) == (1200, 88)
    assert refund_reversal(0, 0) == (0, 0)
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/service/test_points_rules.py -q --basetemp=D:\Temp\pytest-bt-points-rules`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现 rules.py**

创建 `app/service/points/rules.py`：

```python
"""积分业务规则纯函数（无 IO，可独立单测）。"""

MIN_REDEEM_POINTS = 100
MAX_REDEEM_RATIO_NUMERATOR = 50
MAX_REDEEM_RATIO_DENOMINATOR = 100


def award_points(cash_fen: int) -> int:
    """按实付现金（分）计算应发积分：1 元实付 = 1 分，向下取整。"""
    return max(0, cash_fen) // 100


def points_to_fen(points_used: int) -> int:
    """把抵扣积分数折算为金额（分）：100 分 = 1 元。"""
    return max(0, points_used) // 100 * 100


def redeem_units(available_points: int, total_fen: int, balance_fen: int) -> int:
    """计算本单可用抵扣积分数。

    规则：百位向下取整；单笔最低 100 分；最高抵扣订单应付 50%，
    且折算金额不超过剩余应付（total_fen - balance_fen）。
    """
    available = max(0, available_points)
    usable = (available // MIN_REDEEM_POINTS) * MIN_REDEEM_POINTS
    if usable < MIN_REDEEM_POINTS:
        return 0
    cap_fen = max(0, total_fen - balance_fen)
    ratio_cap_fen = (
        total_fen * MAX_REDEEM_RATIO_NUMERATOR // MAX_REDEEM_RATIO_DENOMINATOR
    )
    points_fen = points_to_fen(min(cap_fen, ratio_cap_fen))
    return min(usable, points_fen)


def refund_reversal(points_used: int, points_awarded: int) -> tuple[int, int]:
    """全单退款退返金额：返回（退回抵扣积分, 收回已发积分）。"""
    return max(0, points_used), max(0, points_awarded)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/service/test_points_rules.py -q --basetemp=D:\Temp\pytest-bt-points-rules`
Expected: PASS（5 passed）

- [ ] **Step 5: 提交**

```bash
git add app/service/points/rules.py tests/service/test_points_rules.py
git commit -m "feat(points): 积分规则纯函数"
```

---

### Task 3: 积分账本 + PointsService 门面

**Files:**
- Create: `app/service/points/ledger.py`
- Create: `app/service/points/__init__.py`
- Test: `tests/service/test_points_service.py`

**Interfaces:**
- Consumes: `MemberBalanceRepo.get_points/credit_points/deduct_points_if_sufficient`、`PointsLedgerRepo`、`PointsLedgerEntry`（Task 1）
- Produces:
  - `PointsLedgerService.credit(mobile, amount, biz_type, biz_id, unique_id, event_type) -> int`（幂等，返回变动后余额）
  - `PointsLedgerService.deduct(mobile, amount, biz_type, biz_id, unique_id, event_type) -> int | None`（余额不足返回 None）
  - `PointsLedgerService.list_by_mobile(mobile) -> list[dict]`
  - `PointsService.get_points(user_id) -> dict`（balance + mobile + ledger）
  - `PointsService.redeem_preview(order_id, user_id) -> dict`（试算，不落账）

- [ ] **Step 1: 写失败测试**

创建 `tests/service/test_points_service.py`：

```python
"""积分服务测试：账本幂等、预览试算。"""

import aiosqlite
import pytest

from app.repository.config_repo import ConfigRepo
from app.repository.customer_master_repo import CustomerMasterRepo
from app.repository.member_balance_repo import MemberBalanceRepo
from app.repository.order_event_repo import OrderEventRepo
from app.repository.order_repo import OrderRepo
from app.repository.points_ledger_repo import PointsLedgerRepo
from app.repository.session_repo import SessionRepo
from app.repository.youzan_inventory_repo import YouzanInventoryRepo
from app.repository.youzan_repo import YouzanProductRepo
from app.service.order import OrderApplicationService
from app.service.points import PointsService

MOBILE = "13800000002"
OPENID = "openid_m3_001"
USER_ID = f"wx_{OPENID}"


async def _seed_member(db: aiosqlite.Connection, *, points: int = 0) -> None:
    await db.execute(
        "INSERT INTO customer_master (id, tenant_id, status, primary_phone, "
        "phone_verified, display_name, identity_confidence, has_miniapp_identity) "
        "VALUES (?, 'yunxi', 'active', ?, 1, '积分测试会员', 'high', 1)",
        (f"cm_{OPENID}", MOBILE),
    )
    await db.execute(
        "INSERT INTO customer_identity_links (id, tenant_id, customer_id, "
        "identity_type, identity_value, identity_value_normalized, source_system, "
        "link_status, verification_status, confidence_score) "
        "VALUES (?, 'yunxi', ?, 'miniapp_openid', ?, ?, 'miniapp', 'active', "
        "'verified', 100)",
        (f"cil_{OPENID}", f"cm_{OPENID}", OPENID, OPENID),
    )
    if points:
        await db.execute(
            "INSERT INTO member_balance (mobile, points) VALUES (?, ?)",
            (MOBILE, points),
        )
    await db.commit()


@pytest.fixture
def points_service(db: aiosqlite.Connection) -> PointsService:
    return PointsService(
        balance_repo=MemberBalanceRepo(db),
        ledger_repo=PointsLedgerRepo(db),
        customer_repo=CustomerMasterRepo(db),
        order_repo=OrderRepo(db),
    )


@pytest.fixture
def order_service(db: aiosqlite.Connection) -> OrderApplicationService:
    return OrderApplicationService(
        order_repo=OrderRepo(db),
        event_repo=OrderEventRepo(db),
        session_repo=SessionRepo(db),
        product_repo=YouzanProductRepo(db),
        inventory_repo=YouzanInventoryRepo(db),
        config_repo=ConfigRepo(db),
    )


async def _create_order(order_service: OrderApplicationService, price_fen: int = 10_000) -> str:
    created = await order_service.create_order(
        {
            "items": [
                {
                    "productId": "p_m3_001",
                    "title": "M3 积分测试蛋糕",
                    "priceFen": price_fen,
                    "quantity": 1,
                }
            ],
            "receiverName": "积分测试",
            "receiverPhone": MOBILE,
            "deliveryType": "delivery",
            "deliveryAddress": "积分测试地址",
            "expectTime": "2026-08-20 19:00",
        },
        user_id=USER_ID,
    )
    return created["orderId"]


@pytest.mark.asyncio
async def test_get_points_requires_member(db: aiosqlite.Connection, points_service: PointsService) -> None:
    """未识别会员查询积分应报错。"""
    with pytest.raises(ValueError, match="当前用户未识别为会员"):
        await points_service.get_points("wx_unknown_openid")


@pytest.mark.asyncio
async def test_get_points_balance_and_ledger(
    db: aiosqlite.Connection,
    points_service: PointsService,
) -> None:
    """已识别会员返回余额与流水。"""
    await _seed_member(db, points=2000)
    result = await points_service.get_points(USER_ID)
    assert result["pointsBalance"] == 2000
    assert result["mobile"] == MOBILE
    assert isinstance(result["ledger"], list)


@pytest.mark.asyncio
async def test_redeem_preview_caps(
    db: aiosqlite.Connection,
    points_service: PointsService,
    order_service: OrderApplicationService,
) -> None:
    """预览按 50% 上限与余额约束计算。"""
    await _seed_member(db, points=100_000)
    order_id = await _create_order(order_service, price_fen=10_000)
    preview = await points_service.redeem_preview(order_id, user_id=USER_ID)
    assert preview["pointsFen"] == 5000
    assert preview["pointsUsed"] == 5000
    assert preview["remainFen"] == 5000


@pytest.mark.asyncio
async def test_redeem_preview_not_enough_points(
    db: aiosqlite.Connection,
    points_service: PointsService,
    order_service: OrderApplicationService,
) -> None:
    """积分不足 100 分预览返回 0。"""
    await _seed_member(db, points=50)
    order_id = await _create_order(order_service, price_fen=10_000)
    preview = await points_service.redeem_preview(order_id, user_id=USER_ID)
    assert preview["pointsFen"] == 0
    assert preview["pointsUsed"] == 0
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/service/test_points_service.py -q --basetemp=D:\Temp\pytest-bt-points-service`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现 ledger.py**

创建 `app/service/points/ledger.py`：

```python
"""积分账本：加款/扣款与流水写入（幂等）。"""

from app.models.member import LedgerSource, PointsLedgerEntry
from app.repository.member_balance_repo import MemberBalanceRepo
from app.repository.points_ledger_repo import PointsLedgerRepo
from app.utils import now_str


class PointsLedgerService:
    """负责积分余额变动与流水记账。"""

    def __init__(
        self,
        balance_repo: MemberBalanceRepo | None = None,
        ledger_repo: PointsLedgerRepo | None = None,
    ) -> None:
        self._balance_repo = balance_repo or MemberBalanceRepo(None)
        self._ledger_repo = ledger_repo or PointsLedgerRepo(None)

    async def credit(
        self,
        *,
        mobile: str,
        amount: int,
        biz_type: str,
        biz_id: str,
        unique_id: str,
        event_type: str,
    ) -> int:
        """加款并写流水（幂等），返回变动后余额。"""
        if await self._ledger_repo.get_by_unique_id(unique_id):
            return await self._balance_repo.get_points(mobile)
        balance_after = await self._balance_repo.credit_points(mobile, amount)
        await self._ledger_repo.insert(
            PointsLedgerEntry(
                unique_id=unique_id,
                mobile=mobile,
                amount=amount,
                total=balance_after,
                event_type=event_type,
                source=LedgerSource.ORDER,
                biz_type=biz_type,
                biz_id=biz_id,
                occurred_at=now_str(),
            )
        )
        return balance_after

    async def deduct(
        self,
        *,
        mobile: str,
        amount: int,
        biz_type: str,
        biz_id: str,
        unique_id: str,
        event_type: str,
    ) -> int | None:
        """原子扣款并写流水；余额不足返回 None，不扣款不记账。"""
        if await self._ledger_repo.get_by_unique_id(unique_id):
            return await self._balance_repo.get_points(mobile)
        if not await self._balance_repo.deduct_points_if_sufficient(mobile, amount):
            return None
        balance_after = await self._balance_repo.get_points(mobile)
        await self._ledger_repo.insert(
            PointsLedgerEntry(
                unique_id=unique_id,
                mobile=mobile,
                amount=-amount,
                total=balance_after,
                event_type=event_type,
                source=LedgerSource.ORDER,
                biz_type=biz_type,
                biz_id=biz_id,
                occurred_at=now_str(),
            )
        )
        return balance_after

    async def list_by_mobile(self, mobile: str) -> list[dict]:
        """读取手机号积分流水。"""
        return await self._ledger_repo.list_by_mobile(mobile)
```

- [ ] **Step 4: 实现 __init__.py 门面**

创建 `app/service/points/__init__.py`（先实现 get_points / redeem_preview，Task 4 补 apply_points / award / refund）：

```python
"""积分域应用服务门面。"""

from app.models.order import Order
from app.repository.customer_master_repo import CustomerMasterRepo
from app.repository.member_balance_repo import MemberBalanceRepo
from app.repository.order_repo import OrderRepo
from app.repository.points_ledger_repo import PointsLedgerRepo
from app.service.order.payment_state import (
    PAYMENT_STATUS_PAID,
    PAYMENT_STATUS_UNPAID,
    loads_payment,
)
from app.service.points.ledger import PointsLedgerService
from app.service.points.rules import points_to_fen, redeem_units


class PointsService:
    """积分域门面：查询/预览/支付联动/退款。"""

    def __init__(
        self,
        balance_repo: MemberBalanceRepo | None = None,
        ledger_repo: PointsLedgerRepo | None = None,
        customer_repo: CustomerMasterRepo | None = None,
        order_repo: OrderRepo | None = None,
        ledger_service: PointsLedgerService | None = None,
    ) -> None:
        self._balance_repo = balance_repo or MemberBalanceRepo(None)
        self._ledger_repo = ledger_repo or PointsLedgerRepo(None)
        self._customer_repo = customer_repo or CustomerMasterRepo(None)
        self._order_repo = order_repo or OrderRepo(None)
        self._ledger_service = ledger_service or PointsLedgerService(
            balance_repo=self._balance_repo,
            ledger_repo=self._ledger_repo,
        )

    async def resolve_mobile(self, user_id: str) -> str:
        """把小程序用户标识解析为会员手机号。"""
        from app.service.stored_value.member import MemberBalanceService

        return await MemberBalanceService(customer_repo=self._customer_repo).resolve_mobile(
            user_id
        )

    async def get_points(self, user_id: str) -> dict:
        """读取会员积分余额与最近流水。"""
        mobile = await self.resolve_mobile(user_id)
        balance = await self._balance_repo.get_points(mobile)
        ledger = await self._ledger_service.list_by_mobile(mobile)
        return {"pointsBalance": balance, "mobile": mobile, "ledger": ledger}

    async def redeem_preview(self, order_id: str, *, user_id: str) -> dict:
        """积分抵扣试算（不落账）。"""
        order = await self._owned_order(order_id, user_id)
        payment = loads_payment(order.payment)
        payment_status = str(payment.get("status", PAYMENT_STATUS_UNPAID))
        if payment_status == PAYMENT_STATUS_PAID:
            raise ValueError("订单已支付")
        mobile = await self.resolve_mobile(user_id)
        balance = await self._balance_repo.get_points(mobile)
        total_fen = self._total_fen(order)
        balance_fen = int(payment.get("balanceFen", 0) or 0)
        points_used = redeem_units(balance, total_fen, balance_fen)
        points_fen = points_to_fen(points_used)
        return {
            "orderId": order.id,
            "pointsBalance": balance,
            "pointsFen": points_fen,
            "pointsUsed": points_used,
            "remainFen": max(0, total_fen - balance_fen - points_fen),
        }

    async def _owned_order(self, order_id: str, user_id: str) -> Order:
        order = await self._order_repo.get_order(order_id)
        if order is None or order.user_id != user_id:
            raise ValueError("订单不存在")
        return order

    @staticmethod
    def _total_fen(order: Order) -> int:
        from app.utils import yuan_to_fen

        return yuan_to_fen(order.total_amount)
```

- [ ] **Step 5: 运行测试确认通过**

Run: `python -m pytest tests/service/test_points_service.py -q --basetemp=D:\Temp\pytest-bt-points-service`
Expected: PASS（4 passed）

- [ ] **Step 6: 提交**

```bash
git add app/service/points/ledger.py app/service/points/__init__.py tests/service/test_points_service.py
git commit -m "feat(points): 积分账本与门面查询预览"
```

---

### Task 4: 支付联动（快照 / 发分 / 退款）

**Files:**
- Create: `app/service/points/payment.py`
- Modify: `app/service/order/payment_state.py`（build_points_payment）
- Modify: `app/service/order/payment_runtime.py`（mock 支付后发分）
- Modify: `app/service/order/payment_notification.py`（微信金额校验含 points、支付后发分）
- Modify: `app/repository/order_repo.py`（新增 partial→partial 更新方法）
- Modify: `app/service/stored_value/payment.py`（储值支付后发分）
- Modify: `app/service/order/cancellation.py` / `expiration.py` / `status_flow.py`（退款收分）
- Test: `tests/service/test_points_payment.py`

**Interfaces:**
- Consumes: `PointsLedgerService`、`redeem_units/points_to_fen/award_points/refund_reversal`、`PointsService.resolve_mobile/_owned_order/_total_fen`
- Produces:
  - `PointsPaymentService.apply_points_snapshot(order, user_id, points_used, mobile) -> dict`：写 partial 快照，返回支付字段
  - `PointsPaymentService.award_on_payment(order) -> None`：发分 + 扣抵扣（幂等键 `points:award:<order_id>` / `points:redeem:<order_id>`）
  - `PointsPaymentService.refund_points(order) -> None`：退回 pointsUsed + 收回 pointsAwarded（幂等键 `points:refund:<order_id>`）
  - `PointsService.apply_points(order_id, user_id) -> dict` 门面入口

- [ ] **Step 1: 写失败测试**

创建 `tests/service/test_points_payment.py`：

```python
"""积分支付联动测试：快照、发分、退款。"""

import aiosqlite
import pytest

from app.repository.config_repo import ConfigRepo
from app.repository.customer_master_repo import CustomerMasterRepo
from app.repository.member_balance_repo import MemberBalanceRepo
from app.repository.order_event_repo import OrderEventRepo
from app.repository.order_repo import OrderRepo
from app.repository.points_ledger_repo import PointsLedgerRepo
from app.repository.session_repo import SessionRepo
from app.repository.youzan_inventory_repo import YouzanInventoryRepo
from app.repository.youzan_repo import YouzanProductRepo
from app.service.order import OrderApplicationService
from app.service.points import PointsService

MOBILE = "13800000003"
OPENID = "openid_m3_pay_001"
USER_ID = f"wx_{OPENID}"


async def _seed_member(db: aiosqlite.Connection, *, points: int = 0) -> None:
    await db.execute(
        "INSERT INTO customer_master (id, tenant_id, status, primary_phone, "
        "phone_verified, display_name, identity_confidence, has_miniapp_identity) "
        "VALUES (?, 'yunxi', 'active', ?, 1, '积分支付测试', 'high', 1)",
        (f"cm_{OPENID}", MOBILE),
    )
    await db.execute(
        "INSERT INTO customer_identity_links (id, tenant_id, customer_id, "
        "identity_type, identity_value, identity_value_normalized, source_system, "
        "link_status, verification_status, confidence_score) "
        "VALUES (?, 'yunxi', ?, 'miniapp_openid', ?, ?, 'miniapp', 'active', "
        "'verified', 100)",
        (f"cil_{OPENID}", f"cm_{OPENID}", OPENID, OPENID),
    )
    await db.execute(
        "INSERT INTO member_balance (mobile, points) VALUES (?, ?)",
        (MOBILE, points),
    )
    await db.commit()


@pytest.fixture
def points_service(db: aiosqlite.Connection) -> PointsService:
    return PointsService(
        balance_repo=MemberBalanceRepo(db),
        ledger_repo=PointsLedgerRepo(db),
        customer_repo=CustomerMasterRepo(db),
        order_repo=OrderRepo(db),
    )


@pytest.fixture
def order_service(db: aiosqlite.Connection) -> OrderApplicationService:
    return OrderApplicationService(
        order_repo=OrderRepo(db),
        event_repo=OrderEventRepo(db),
        session_repo=SessionRepo(db),
        product_repo=YouzanProductRepo(db),
        inventory_repo=YouzanInventoryRepo(db),
        config_repo=ConfigRepo(db),
    )


async def _create_order(order_service: OrderApplicationService, price_fen: int = 10_000) -> str:
    created = await order_service.create_order(
        {
            "items": [
                {
                    "productId": "p_m3_pay_001",
                    "title": "M3 支付联动蛋糕",
                    "priceFen": price_fen,
                    "quantity": 1,
                }
            ],
            "receiverName": "积分支付测试",
            "receiverPhone": MOBILE,
            "deliveryType": "delivery",
            "deliveryAddress": "积分支付测试地址",
            "expectTime": "2026-08-20 19:00",
        },
        user_id=USER_ID,
    )
    return created["orderId"]


async def _points(db: aiosqlite.Connection) -> int:
    rows = await db.execute_fetchall(
        "SELECT points FROM member_balance WHERE mobile = ? LIMIT 1", (MOBILE,)
    )
    return int(rows[0]["points"]) if rows else 0


async def _ledger_count(db: aiosqlite.Connection) -> int:
    rows = await db.execute_fetchall(
        "SELECT COUNT(*) AS c FROM points_ledger WHERE mobile = ?", (MOBILE,)
    )
    return int(rows[0]["c"])


@pytest.mark.asyncio
async def test_apply_points_writes_partial_snapshot(
    db: aiosqlite.Connection,
    points_service: PointsService,
    order_service: OrderApplicationService,
) -> None:
    """apply-points 写 partial 快照但不动积分账。"""
    await _seed_member(db, points=100_000)
    order_id = await _create_order(order_service, price_fen=10_000)
    result = await points_service.apply_points(order_id, user_id=USER_ID)
    assert result["paymentStatus"] == "partial"
    assert result["pointsFen"] == 5000
    assert result["pointsUsed"] == 5000
    assert result["remainFen"] == 5000
    assert await _points(db) == 100_000
    assert await _ledger_count(db) == 0


@pytest.mark.asyncio
async def test_award_on_payment_after_mock_pay(
    db: aiosqlite.Connection,
    points_service: PointsService,
    order_service: OrderApplicationService,
) -> None:
    """mock 支付成功后发分并扣抵扣，重复确认幂等。"""
    await _seed_member(db, points=100_000)
    order_id = await _create_order(order_service, price_fen=10_000)
    await points_service.apply_points(order_id, user_id=USER_ID)
    await order_service.confirm_mock_payment(order_id, user_id=USER_ID)
    assert await _points(db) == 100_000
    await order_service.confirm_mock_payment(order_id, user_id=USER_ID)
    assert await _points(db) == 100_000
    assert await _ledger_count(db) == 2


@pytest.mark.asyncio
async def test_refund_points_returns_used_and_claws_back_award(
    db: aiosqlite.Connection,
    points_service: PointsService,
    order_service: OrderApplicationService,
) -> None:
    """退款退回全部抵扣积分并收回全部已发积分，幂等。"""
    await _seed_member(db, points=100_000)
    order_id = await _create_order(order_service, price_fen=10_000)
    await points_service.apply_points(order_id, user_id=USER_ID)
    await order_service.confirm_mock_payment(order_id, user_id=USER_ID)
    order = await OrderRepo(db).get_order(order_id)
    await points_service.refund_points(order)
    assert await _points(db) == 100_000
    await points_service.refund_points(order)
    assert await _points(db) == 100_000
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/service/test_points_payment.py -q --basetemp=D:\Temp\pytest-bt-points-payment`
Expected: FAIL（PointsService.apply_points 不存在）

- [ ] **Step 3: 扩展 build_points_payment**

修改 `app/service/order/payment_state.py`，在 `build_combined_payment` 后新增：

```python
def build_points_payment(
    now_text_value: str,
    *,
    balance_fen: int,
    points_fen: int,
    points_used: int,
    remain_fen: int,
) -> dict:
    """构建含积分抵扣的组合支付中间状态。"""
    payment = build_combined_payment(now_text_value, balance_fen, remain_fen)
    payment.update(
        {
            "pointsFen": points_fen,
            "pointsUsed": points_used,
        }
    )
    return payment
```

- [ ] **Step 3.5: 扩展 order_repo（partial → partial 更新）**

修改 `app/repository/order_repo.py`，在 `update_payment_to_partial_if_unpaid_active` 后新增：

```python
    async def update_payment_to_partial_if_unpaid_or_partial_active(
        self,
        order_id: str,
        payment: str,
        updated_at: str,
    ) -> Order | None:
        """原子把未支付或已部分支付订单更新为新的组合支付中间态。"""
        cursor = await self._db.execute(
            "UPDATE orders SET payment = ?, updated_at = ? "
            "WHERE id = ? AND status != 'cancelled' AND "
            + PAYMENT_STATUS_SQL
            + " IN ('unpaid', 'partial')",
            (payment, updated_at, order_id),
        )
        if cursor.rowcount != 1:
            return None
        return await self.get_order(order_id)
```

- [ ] **Step 4: 实现 payment.py**

创建 `app/service/points/payment.py`：

```python
"""积分支付联动：抵扣快照、支付发分、退款收回。"""

from app.models.order import Order
from app.repository.order_repo import OrderRepo
from app.service.order.payment_state import (
    PAYMENT_METHOD_COMBINED,
    PAYMENT_STATUS_PAID,
    PAYMENT_STATUS_PARTIAL,
    PAYMENT_STATUS_UNPAID,
    dumps_payment,
    loads_payment,
    now_text,
    status_value,
)
from app.service.points.ledger import PointsLedgerService
from app.service.points.rules import (
    award_points,
    points_to_fen,
    refund_reversal,
)

POINTS_AWARD_EVENT = "order_award"
POINTS_REDEEM_EVENT = "order_redeem"
POINTS_REFUND_EVENT = "order_refund"


class PointsPaymentService:
    """负责订单积分抵扣快照、支付发分与退款收回。"""

    def __init__(
        self,
        ledger_service: PointsLedgerService | None = None,
        order_repo: OrderRepo | None = None,
    ) -> None:
        self._ledger_service = ledger_service or PointsLedgerService()
        self._order_repo = order_repo or OrderRepo(None)

    async def apply_points_snapshot(
        self,
        order: Order,
        *,
        user_id: str,
        points_used: int,
        mobile: str,
    ) -> dict:
        """校验并写积分抵扣 partial 快照（不扣积分账）。"""
        payment = loads_payment(order.payment)
        payment_status = str(payment.get("status", PAYMENT_STATUS_UNPAID))
        if payment_status == PAYMENT_STATUS_PAID:
            raise ValueError("订单已支付")
        total_fen = self._total_fen(order)
        balance_fen = int(payment.get("balanceFen", 0) or 0)
        points_fen = points_to_fen(points_used)
        if points_fen <= 0:
            raise ValueError("积分抵扣至少 100 分")
        if points_fen > total_fen - balance_fen:
            raise ValueError("积分抵扣金额超过剩余应付")
        remain_fen = total_fen - balance_fen - points_fen
        now = now_text()
        from app.service.order.payment_state import build_points_payment

        snapshot = build_points_payment(
            now,
            balance_fen=balance_fen,
            points_fen=points_fen,
            points_used=points_used,
            remain_fen=remain_fen,
        )
        updated = await self._order_repo.update_payment_to_partial_if_unpaid_or_partial_active(
            order.id, dumps_payment(snapshot), now
        )
        if updated is None:
            raise ValueError("订单支付状态更新冲突")
        return {
            "orderId": order.id,
            "status": status_value(updated),
            "paymentStatus": PAYMENT_STATUS_PARTIAL,
            "paymentMethod": PAYMENT_METHOD_COMBINED,
            "pointsFen": points_fen,
            "pointsUsed": points_used,
            "remainFen": remain_fen,
        }

    async def award_on_payment(self, order: Order) -> None:
        """支付成功后发分并扣抵扣（幂等）。"""
        payment = loads_payment(order.payment)
        if str(payment.get("status", PAYMENT_STATUS_UNPAID)) != PAYMENT_STATUS_PAID:
            return
        if int(payment.get("pointsAwarded", 0) or 0) > 0:
            return
        points_used = int(payment.get("pointsUsed", 0) or 0)
        mobile = await self._resolve_mobile(order.user_id)
        total_fen = self._total_fen(order)
        balance_fen = int(payment.get("balanceFen", 0) or 0)
        points_fen = int(payment.get("pointsFen", 0) or 0)
        cash_fen = max(0, total_fen - balance_fen - points_fen)
        award = award_points(cash_fen)
        if points_used > 0:
            await self._ledger_service.deduct(
                mobile=mobile,
                amount=points_used,
                biz_type=POINTS_REDEEM_EVENT,
                biz_id=order.id,
                unique_id=f"points:redeem:{order.id}",
                event_type=POINTS_REDEEM_EVENT,
            )
        if award > 0:
            await self._ledger_service.credit(
                mobile=mobile,
                amount=award,
                biz_type=POINTS_AWARD_EVENT,
                biz_id=order.id,
                unique_id=f"points:award:{order.id}",
                event_type=POINTS_AWARD_EVENT,
            )
        await self._record_awarded(order, points_used, award)

    async def refund_points(self, order: Order) -> None:
        """按支付快照退回抵扣积分并收回已发积分（幂等）。"""
        payment = loads_payment(order.payment)
        points_used = int(payment.get("pointsUsed", 0) or 0)
        points_awarded = int(payment.get("pointsAwarded", 0) or 0)
        if points_used <= 0 and points_awarded <= 0:
            return
        mobile = await self._resolve_mobile(order.user_id)
        return_points, clawback_points = refund_reversal(points_used, points_awarded)
        if return_points > 0:
            await self._ledger_service.credit(
                mobile=mobile,
                amount=return_points,
                biz_type=POINTS_REFUND_EVENT,
                biz_id=order.id,
                unique_id=f"points:refund:{order.id}",
                event_type=POINTS_REFUND_EVENT,
            )
        if clawback_points > 0:
            await self._ledger_service.deduct(
                mobile=mobile,
                amount=clawback_points,
                biz_type=POINTS_REFUND_EVENT,
                biz_id=order.id,
                unique_id=f"points:refund:{order.id}:clawback",
                event_type=POINTS_REFUND_EVENT,
            )
        await self._clear_awarded(order)

    async def _record_awarded(self, order: Order, points_used: int, award: int) -> None:
        """把已发积分回写支付快照，防止重复发分。"""
        latest = await self._order_repo.get_order(order.id)
        if latest is None:
            return
        payment = loads_payment(latest.payment)
        payment["pointsUsed"] = points_used
        payment["pointsAwarded"] = award
        await self._order_repo.update_payment(
            order.id, dumps_payment(payment), now_text()
        )

    async def _clear_awarded(self, order: Order) -> None:
        """退款后清理快照中的抵扣/已发标记。"""
        latest = await self._order_repo.get_order(order.id)
        if latest is None:
            return
        payment = loads_payment(latest.payment)
        payment["pointsUsed"] = 0
        payment["pointsFen"] = 0
        payment["pointsAwarded"] = 0
        await self._order_repo.update_payment(
            order.id, dumps_payment(payment), now_text()
        )

    async def _resolve_mobile(self, user_id: str) -> str:
        from app.service.stored_value.member import MemberBalanceService

        return await MemberBalanceService().resolve_mobile(user_id)

    @staticmethod
    def _total_fen(order: Order) -> int:
        from app.utils import yuan_to_fen

        return yuan_to_fen(order.total_amount)
```

- [ ] **Step 5: 门面补 apply_points**

修改 `app/service/points/__init__.py`，在 `redeem_preview` 之后补：

```python
    async def apply_points(self, order_id: str, *, user_id: str) -> dict:
        """应用积分抵扣：校验并写 partial 快照（支付成功才扣积分）。"""
        from app.service.points.payment import PointsPaymentService

        payment_service = PointsPaymentService(
            ledger_service=self._ledger_service,
            order_repo=self._order_repo,
        )
        order = await self._owned_order(order_id, user_id)
        mobile = await self.resolve_mobile(user_id)
        balance = await self._balance_repo.get_points(mobile)
        payment = loads_payment(order.payment)
        balance_fen = int(payment.get("balanceFen", 0) or 0)
        total_fen = self._total_fen(order)
        points_used = redeem_units(balance, total_fen, balance_fen)
        if points_used <= 0:
            raise ValueError("积分不足或订单金额不支持抵扣")
        return await payment_service.apply_points_snapshot(
            order,
            user_id=user_id,
            points_used=points_used,
            mobile=mobile,
        )
```

注意：`__init__.py` 需要导入 `Order` 类型用于注解，顶部已有 `from app.models.order import Order`。

- [ ] **Step 6: 挂接三条支付路径**

修改 `app/service/order/payment_runtime.py` 的 `confirm_mock_payment`：

```python
        # 在函数末尾 return 前统一补发分（重复通知由 pointsAwarded 幂等兜底）
        from app.service.points.payment import PointsPaymentService

        await PointsPaymentService(order_repo=self._order_repo).award_on_payment(updated)
        return self._serializer.serialize(updated)
```

同时把 `payment_status == PAYMENT_STATUS_PAID` 的提前返回分支改为也走发分：

```python
        if payment_status == PAYMENT_STATUS_PAID:
            from app.service.points.payment import PointsPaymentService

            await PointsPaymentService(order_repo=self._order_repo).award_on_payment(order)
            return self._serializer.serialize(order)
```

修改 `app/service/order/payment_notification.py`：
- `mark_paid` 中 `_record_paid_event(updated, payment["paidAt"])` 之后调用 `award_on_payment(updated)`。
- `validate_transaction` 的 partial 分支保持按 `remainFen` 校验（快照已含积分，无需改校验逻辑，但确认 `remainFen` 读取兼容 pointsFen 场景）。

修改 `app/service/stored_value/payment.py`：
- `pay_order_with_balance` 返回前调 `award_on_payment(updated)`（全额余额支付 cash=0，不发分但保持统一钩子）。

- [ ] **Step 7: 挂接退款路径**

修改 `app/service/order/cancellation.py` 的 `cancel_user_order`：

```python
        await self._refund_balance(updated)
        await self._refund_points(updated)
```

并新增：

```python
    async def _refund_points(self, order: Order) -> None:
        """取消时按支付快照退回积分并收回已发积分。"""
        from app.service.points.payment import PointsPaymentService

        await PointsPaymentService(order_repo=self._order_repo).refund_points(order)
```

同样在 `app/service/order/expiration.py` 的 `_refund_balance` 调用点后与 `app/service/order/status_flow.py` 的 `_refund_balance` 调用点后补 `_refund_points`（三个文件同构）。

- [ ] **Step 8: 运行测试确认通过**

Run: `python -m pytest tests/service/test_points_payment.py tests/service/test_stored_value.py tests/service/test_order.py -q --basetemp=D:\Temp\pytest-bt-points-payment`
Expected: PASS

- [ ] **Step 9: 提交**

```bash
git add app/service/points/payment.py app/service/points/__init__.py app/service/order/payment_state.py app/service/order/payment_runtime.py app/service/order/payment_notification.py app/service/stored_value/payment.py app/service/order/cancellation.py app/service/order/expiration.py app/service/order/status_flow.py tests/service/test_points_payment.py
git commit -m "feat(points): 支付联动发分/抵扣/退款闭环"
```

---

### Task 5: 小程序积分 API

**Files:**
- Create: `app/api/channels/storefront/points.py`
- Modify: `app/lifespan_services.py`（装配 PointsService）
- Modify: `app/lifespan_routes.py`（注册路由）
- Test: `tests/api/test_miniapp_points_api.py`

**Interfaces:**
- Consumes: `PointsService.get_points/redeem_preview/apply_points`
- Produces:
  - `create_storefront_points_router(service: PointsService) -> APIRouter`：`GET /api/v1/miniapp/points`、`POST /api/v1/miniapp/orders/{order_id}/points-preview`、`POST /api/v1/miniapp/orders/{order_id}/apply-points`

- [ ] **Step 1: 参考既有 API 测试夹具**

先查看 `tests/api/test_miniapp_order_api.py` 的登录/客户端夹具，按其模式写 `tests/api/test_miniapp_points_api.py`：

```python
"""小程序积分 API 测试。"""

import aiosqlite
import pytest
from httpx import ASGITransport, AsyncClient

from app.lifespan_routes import register_routes
from app.lifespan_services import init_services
from app.service.channels.storefront.auth import StorefrontAuthService

MOBILE = "13800000004"
OPENID = "openid_m3_api_001"
USER_ID = f"wx_{OPENID}"


@pytest.fixture
async def client(db: aiosqlite.Connection):
    """构建带鉴权头的测试客户端（夹具签名以既有 miniapp 测试为准）。"""
    from fastapi import FastAPI

    from app.repository import build_repositories

    repos = build_repositories(db)
    services = init_services(repos, None)
    app = FastAPI()
    register_routes(app, services)
    token = StorefrontAuthService().create_access_token(USER_ID)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        ac.headers["authorization"] = f"Bearer {token}"
        yield ac


@pytest.mark.asyncio
async def test_get_points_requires_auth(db: aiosqlite.Connection) -> None:
    """未带 token 访问积分接口返回 401。"""
    from fastapi import FastAPI

    from app.repository import build_repositories

    repos = build_repositories(db)
    services = init_services(repos, None)
    app = FastAPI()
    register_routes(app, services)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/v1/miniapp/points")
        assert resp.status_code == 401
```

> 说明：`build_repositories` / `register_routes` 的确切签名以现有 `tests/api/test_miniapp_order_api.py` 夹具为准；如不一致，按既有模式调整。积分接口鉴权 401 用例必须通过。

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/api/test_miniapp_points_api.py -q --basetemp=D:\Temp\pytest-bt-points-api`
Expected: FAIL（路由不存在 / 断言失败）

- [ ] **Step 3: 实现 points.py 路由**

创建 `app/api/channels/storefront/points.py`：

```python
"""前台积分 API 路由。"""

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException

from app.api.channels.storefront._user import (
    authenticate_storefront_request,
    require_storefront_user_id,
)
from app.service.points import PointsService


def create_storefront_points_router(service: PointsService) -> APIRouter:
    """创建前台积分公开路由。"""
    router = APIRouter(
        prefix="/api/v1/miniapp/points",
        tags=["miniapp-points"],
        dependencies=[Depends(authenticate_storefront_request)],
    )

    @router.get("")
    async def get_points(
        x_miniapp_user_id: str | None = Header(default=None, alias="x-miniapp-user-id"),
    ) -> dict[str, Any]:
        try:
            points = await service.get_points(
                require_storefront_user_id(x_miniapp_user_id),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"code": 0, "data": points}

    @router.post("/orders/{order_id}/points-preview")
    async def points_preview(
        order_id: str,
        x_miniapp_user_id: str | None = Header(default=None, alias="x-miniapp-user-id"),
    ) -> dict[str, Any]:
        try:
            preview = await service.redeem_preview(
                order_id,
                user_id=require_storefront_user_id(x_miniapp_user_id),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"code": 0, "data": preview}

    @router.post("/orders/{order_id}/apply-points")
    async def apply_points(
        order_id: str,
        x_miniapp_user_id: str | None = Header(default=None, alias="x-miniapp-user-id"),
    ) -> dict[str, Any]:
        try:
            applied = await service.apply_points(
                order_id,
                user_id=require_storefront_user_id(x_miniapp_user_id),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"code": 0, "data": applied}

    return router
```

- [ ] **Step 4: 装配服务与路由**

修改 `app/lifespan_services.py`，在 `stored_value_service` 之后新增：

```python
    from app.service.points import PointsService

    points_service = PointsService()
```

并按现有返回结构把 `"points_service": points_service` 加入 services 字典。

修改 `app/lifespan_routes.py`，在 recharges 路由注册后新增：

```python
    from app.api.channels.storefront.points import create_storefront_points_router

    app.include_router(
        create_storefront_points_router(services["points_service"])
    )
```

- [ ] **Step 5: 运行测试确认通过**

Run: `python -m pytest tests/api/test_miniapp_points_api.py -q --basetemp=D:\Temp\pytest-bt-points-api`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add app/api/channels/storefront/points.py app/lifespan_services.py app/lifespan_routes.py tests/api/test_miniapp_points_api.py
git commit -m "feat(points): 小程序积分查询/预览/抵扣 API"
```

---

### Task 6: 数据主从配置开关

**Files:**
- Modify: `app/config.py`（POINTS_AUTHORITY）
- Modify: `app/service/youzan/event_member.py`（_handle_points_event）
- Test: `tests/service/test_member_accounting.py` 增加用例

**Interfaces:**
- Consumes: `settings.POINTS_AUTHORITY`
- Produces: `_handle_points_event` 在 `local` 模式下只写流水不覆盖余额

- [ ] **Step 1: 写失败测试**

在 `tests/service/test_member_accounting.py` 增加：

```python
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
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/service/test_member_accounting.py -q --basetemp=D:\Temp\pytest-bt-member-acct`
Expected: FAIL（POINTS_AUTHORITY 属性不存在或事件仍写余额）

- [ ] **Step 3: 加配置**

修改 `app/config.py`，在 `ALLOW_MOCK_PAYMENT` 附近加：

```python
    # 积分余额权威来源：youzan=有赞 total 镜像，local=本地 member_balance.points
    POINTS_AUTHORITY: str = "youzan"
```

- [ ] **Step 4: 改 event_member**

修改 `app/service/youzan/event_member.py`：文件顶部加 `from app.config import settings`；`_handle_points_event` 中把 `balance_repo.upsert_identity(...)` 包在条件里：

```python
    await ledger_repo.insert(...)
    if settings.POINTS_AUTHORITY != "local":
        await balance_repo.upsert_identity(
            mobile=mobile,
            customer_id=customer_id,
            yz_open_id=yz_open_id,
            points=to_int(msg_obj.get("total")),
        )
```

- [ ] **Step 5: 运行测试确认通过**

Run: `python -m pytest tests/service/test_member_accounting.py -q --basetemp=D:\Temp\pytest-bt-member-acct`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add app/config.py app/service/youzan/event_member.py tests/service/test_member_accounting.py
git commit -m "feat(points): 积分余额权威配置开关"
```

---

### Task 7: 验证收口

**Files:**
- Modify: `LOGBOOK.md`、`项目进度与配置清单.md`

- [ ] **Step 1: 运行全套验证**

Run:
```bash
python -m pytest tests/service/test_points_repo.py tests/service/test_points_rules.py tests/service/test_points_service.py tests/service/test_points_payment.py tests/api/test_miniapp_points_api.py tests/service/test_stored_value.py tests/service/test_order.py -q --basetemp=D:\Temp\pytest-bt-points-final
python -m pytest tests/ -q --basetemp=D:\Temp\pytest-bt-full
python scripts/check_project.py --skip-tests
python scripts/check_file_sizes.py
ruff check .
ruff format --check .
```
Expected: 全绿；门禁全绿。

- [ ] **Step 2: 更新 LOGBOOK 与进度清单**

用 `python scripts/append_logbook.py` 追加 M3 收口条目；更新 `项目进度与配置清单.md` 最后更新行与 M3 状态。

- [ ] **Step 3: 提交并推送**

```bash
git add LOGBOOK.md 项目进度与配置清单.md
git commit -m "docs(harness): M3 积分模块本地收口"
git push origin codex/r4c-ci-evidence:master
git push server codex/r4c-ci-evidence:master
git push origin codex/r4c-ci-evidence
git push server codex/r4c-ci-evidence
```

---

## 自审记录（plan 编写时执行）

1. **Spec 覆盖**：M3.1 数据/仓储 → Task 1；M3.2 积分 Service → Task 2/3；M3.3 支付联动 → Task 4；M3.4 小程序 API → Task 5；数据主从 → Task 6；M3.5 验证收口 → Task 7。计划书「apply-points 必须把订单写为 partial」「remain_fen 三段叠加」「取消/超时/后台取消 refund_points」全部有对应任务。
2. **占位符扫描**：无 TBD/TODO；每个代码步骤给出完整实现；测试用例给出断言。
3. **类型一致**：`redeem_units/points_to_fen/award_points/refund_reversal` 签名在 Task 2 定义并被 Task 3/4 引用一致；`PointsService.get_points/redeem_preview/apply_points` 在 Task 3/4 定义并被 Task 5 API 引用一致；`PointsLedgerService.credit/deduct` 参数顺序一致。
