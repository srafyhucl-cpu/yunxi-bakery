# M5 会员资产前端实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 交付 M5 会员资产前端闭环：我的页资产真实化、积分明细、优惠券中心、充值页、结算页优惠与余额抵扣扩展，全部消费 M2-M4 已交付的小程序 API。

**Architecture:** 双仓协作。Task 1 在 `YunxiBakeBot`（Platform）为 `get_my_coupons` 补 `thresholdFen`（批量取模板避免 N+1）；Task 2-10 在 `YunxiBakeMiniApp`：新增纯函数工具（`node --test` TDD）、4 个服务模块 + 支付开关门面、3 个新页面（积分明细/券中心/充值页）、2 个页面扩展（我的页真实化/结算页优惠与余额抵扣）。支付路径区分「展示类（不限环境）/ 余额支付（不限环境）/ 在线支付与充值（仅本地后端 mock）」三档。

**Tech Stack:** 微信原生小程序 + TypeScript（tsc 严格模式）、Node 22+ 内置 `node --test`（原生 TS type stripping，已验证 v22.23.1）、Python 3.11 + FastAPI + pytest（Platform 侧）、Ruff。

## Global Constraints

- trace_id：`20260814-member-loyalty-m5`；跨仓收口——YunxiBakeBot 与 YunxiBakeMiniApp 两个 LOGBOOK 均挂该 trace_id。
- 双仓：Task 1 在 `D:\Project\YunxiBakeBot`，其余任务在 `D:\Project\YunxiBakeMiniApp`。
- 测试：纯逻辑用 `node --test`（Node ≥22.18 原生支持 `.ts`；测试文件 import 必须带 `.ts` 扩展名）；页面/服务验证用 `tsc --noEmit` + `npm run check:miniapp` + devtools 联调。不引入第三方依赖（不装 jest/vitest）。
- `tsconfig.json` include 仅 `miniprogram/**/*.ts`，`tests/` 下的测试文件不影响 typecheck；且位于 `miniprogram/` 之外，微信开发者工具不会编译进包。
- 编码：业务请求放 `miniprogram/services/`，纯逻辑放 `miniprogram/utils/`；注释与用户可见文案一律中文；不写英文注释。
- 支付开关语义（spec v2）：展示类（资产/积分明细/券中心）不限环境；余额支付 `pay-with-balance` 不限环境；在线支付路径与充值入口仅 `IS_LOCAL_BACKEND`（`IS_USING_LOCAL_API`）。
- 联调：交易类 mock 流程必须 `IS_USING_LOCAL_API=1`（storage key `yunxiUseLocalApi`）连本地后端 `127.0.0.1:7001`；连生产 API 的 trial/develop 只做展示类联调。
- 提交：YunxiBakeBot 中间提交用 `SKIP_LOGBOOK_CHECK=1`（LOGBOOK 收口统一在 Task 10）；miniapp 仓每任务提交，只 add 本任务文件，禁止混入 20260807 trace 的未提交改动。
- Platform 侧 pytest 必须 `--basetemp=D:\Temp\<name> --no-cov`（pytest.ini 全局 addopts 含 `--cov --cov-fail-under=70`）。
- Platform 编码红线：SQL `?` 参数化（IN 子句仅动态占位符数量，值仍绑定）、禁 `SELECT *`、禁 `Optional/Union`、禁英文注释、ruff 通过。
- 前置：miniapp 仓现存未提交改动（DevTools CLI 修复，trace 20260807-post-p0-production-closure）与 M5 无关，任何提交不得 `git add .`。

---

## Phase 1：展示类

### Task 1: Platform — `get_my_coupons` 补 `thresholdFen`（跨仓小任务）

**Files:**
- Modify: `app/repository/coupon_template_repo.py`（新增 `list_by_ids` 批量查询，避免 N+1）
- Modify: `app/service/coupon/__init__.py:53-74`（`get_my_coupons` 输出 `thresholdFen`）
- Test: `tests/api/test_miniapp_coupons_api.py`（追加用例）

**Interfaces:**
- Consumes: `CouponTemplateRepo.list_by_ids(ids: list[str]) -> list[dict]`（本任务新增；`CouponTemplate`/`CouponInventoryEntry`/`CouponType`/`CouponStatus`/`LedgerSource` 常量已存在）
- Produces: `GET /api/v1/miniapp/coupons` 的 coupons 每项新增 `thresholdFen: int`；模板缺失时 fallback `0`

- [ ] **Step 1: 写失败测试**（追加到 `tests/api/test_miniapp_coupons_api.py` 末尾）

以下是追加内容：

```python
import httpx

from app.models.coupon import CouponTemplate, CouponType
from app.models.member import CouponInventoryEntry, CouponStatus, LedgerSource
from tests.helpers.storefront_auth import storefront_auth_headers


async def _seed_member_with_coupon(db: aiosqlite.Connection) -> None:
    """写入测试会员 + 券模板 + TAKE 券行。"""
    await db.execute(
        "INSERT INTO customer_master (id, tenant_id, status, primary_phone, "
        "phone_verified, display_name, identity_confidence, has_miniapp_identity) "
        "VALUES (?, 'yunxi', 'active', ?, 1, '券API测试会员', 'high', 1)",
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
    await CouponTemplateRepo(db).upsert_from_youzan(
        CouponTemplate(
            id="cg_001",
            name="满30减5",
            coupon_type=CouponType.FULL_REDUCTION,
            threshold_fen=3000,
            value_fen=500,
            valid_from="2026-08-01",
            valid_until="2026-12-31",
        )
    )
    await CouponInventoryRepo(db).insert(
        CouponInventoryEntry(
            coupon_id="c1",
            status=CouponStatus.TAKE,
            mobile=MOBILE,
            coupon_group_id="cg_001",
            title="满30减5",
            value_fen=500,
            source=LedgerSource.IMPORT,
            occurred_at="2026-08-01 09:00:00",
            template_id="cg_001",
            valid_from="2026-08-01",
            valid_until="2026-12-31",
        )
    )
    await db.commit()


@pytest.mark.asyncio
async def test_get_coupons_includes_threshold_fen(
    db: aiosqlite.Connection,
    app: FastAPI,
) -> None:
    """已识别会员查询券列表返回模板门槛 thresholdFen。"""
    await _seed_member_with_coupon(db)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.get(
            "/api/v1/miniapp/coupons",
            headers=storefront_auth_headers(USER_ID),
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == 0
    coupons = payload["data"]["coupons"]
    assert coupons[0]["couponId"] == "c1"
    assert coupons[0]["thresholdFen"] == 3000


@pytest.mark.asyncio
async def test_get_coupons_threshold_fallback_zero(
    db: aiosqlite.Connection,
    app: FastAPI,
) -> None:
    """券行有 template_id 但模板缺失时 thresholdFen 返回 0（不抛异常）。"""
    await _seed_member_with_coupon(db)
    await db.execute("DELETE FROM coupon_templates WHERE id = 'cg_001'")
    await db.commit()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.get(
            "/api/v1/miniapp/coupons",
            headers=storefront_auth_headers(USER_ID),
        )

    assert response.status_code == 200
    coupons = response.json()["data"]["coupons"]
    assert coupons[0]["thresholdFen"] == 0
```

注意：`app` fixture 需参照 `tests/api/test_miniapp_points_api.py` 的 `app` fixture 写法补到本文件（现有文件只有 `client` fixture 用 TestClient；新增用例用 httpx.ASGITransport）：

```python
@pytest.fixture
def app(db: aiosqlite.Connection) -> FastAPI:
    return _build_app(db)
```

- [ ] **Step 2: 运行测试确认失败**

```powershell
cd D:\Project\YunxiBakeBot
PYTHONUTF8=1 python -m pytest tests/api/test_miniapp_coupons_api.py -q --no-cov --basetemp=D:\Temp\m5_t1
```

Expected: FAIL——`thresholdFen` 缺失（`get_my_coupons` 尚未输出该字段）。

- [ ] **Step 3: 实现 `list_by_ids`**（追加到 `app/repository/coupon_template_repo.py`，`list_active` 之后）

```python
    async def list_by_ids(self, ids: list[str]) -> list[dict]:
        """按模板 ID 批量读取（避免逐张查询 N+1）。"""
        if not ids:
            return []
        placeholders = ", ".join("?" for _ in ids)
        return await self._db.execute_fetchall(
            "SELECT " + self._COLS + " FROM coupon_templates WHERE id IN (" + placeholders + ")",
            tuple(ids),
        )
```

- [ ] **Step 4: 实现 `get_my_coupons` 输出 `thresholdFen`**（改写 `app/service/coupon/__init__.py:53-74`）

```python
    async def get_my_coupons(self, user_id: str) -> dict:
        """我的券列表（最新态 + 模板信息）。"""
        mobile = await self.resolve_mobile(user_id)
        rows = await self._inventory_repo.list_by_mobile(
            mobile, authority=settings.COUPON_AUTHORITY
        )
        template_ids = sorted(
            {str(row.get("template_id", "") or "") for row in rows if row.get("template_id")}
        )
        templates = await self._template_repo.list_by_ids(template_ids)
        template_map = {str(t["id"]): t for t in templates}
        coupons = []
        for row in rows:
            template = template_map.get(str(row.get("template_id", "") or ""), {})
            coupons.append(
                {
                    "couponId": row["coupon_id"],
                    "templateId": row.get("template_id", ""),
                    "title": row.get("title", ""),
                    "status": row.get("status", ""),
                    "valueFen": row.get("value_fen", 0),
                    "thresholdFen": int(template.get("threshold_fen", 0) or 0),
                    "deductedFen": row.get("deducted_fen", 0),
                    "validFrom": row.get("valid_from", ""),
                    "validUntil": row.get("valid_until", ""),
                    "orderNo": row.get("order_no", ""),
                }
            )
        return {"mobile": mobile, "coupons": coupons}
```

- [ ] **Step 5: 运行测试确认通过**

```powershell
cd D:\Project\YunxiBakeBot
PYTHONUTF8=1 python -m pytest tests/api/test_miniapp_coupons_api.py -q --no-cov --basetemp=D:\Temp\m5_t1
```

Expected: 4 passed（原 2 项 + 新增 2 项）。

- [ ] **Step 6: 门禁 + 提交**

```powershell
cd D:\Project\YunxiBakeBot
ruff check app/service/coupon/__init__.py app/repository/coupon_template_repo.py tests/api/test_miniapp_coupons_api.py
git add app/service/coupon/__init__.py app/repository/coupon_template_repo.py tests/api/test_miniapp_coupons_api.py
$env:SKIP_LOGBOOK_CHECK=1; git commit -m "feat(coupon): get_my_coupons 补 thresholdFen（批量取模板避免 N+1）"
```

提交前缀为 `feat`，按 commit-workflow 规则 feat → minor：VERSION 0.131.2 → 0.132.0。

### Task 1b: Platform — 修正 `MAX_RECHARGE_FEN` 笔误（用户确认 A：上限为 500 元）

**Files:**
- Modify: `app/constants/stored_value.py:5`（`5_000_00` → `50_000`）
- Modify: `tests/service/test_stored_value.py`（充值边界用例：原 `500_001` 断言改 `50_001`，并补 `50_000` 边界接受）

**Interfaces:**
- Consumes: 无
- Produces: 单笔充值上限恢复 500 元（`50_000` 分），与 M2 记录、小程序端 `MIN/MAX_RECHARGE_FEN`（Task 2）三方对齐

- [ ] **Step 1: 改写失败测试**（`tests/service/test_stored_value.py` 的 `test_create_recharge_validation` 用例，原约 196-202 行）

```python
    with pytest.raises(ValueError, match="充值金额不能低于"):
        await stored_value_service.create_recharge(USER_ID, 50)
    with pytest.raises(ValueError, match="充值金额不能超过"):
        await stored_value_service.create_recharge(USER_ID, 50_001)
    accepted = await stored_value_service.create_recharge(USER_ID, 50_000)
    assert accepted["status"] == "unpaid"
```

- [ ] **Step 2: 运行测试确认失败**

```powershell
cd D:\Project\YunxiBakeBot
PYTHONUTF8=1 python -m pytest tests/service/test_stored_value.py -q --no-cov --basetemp=D:\Temp\m5_t1b
```

Expected: FAIL——`create_recharge(USER_ID, 50_001)` 当前不抛错（上限仍是 500000）。

- [ ] **Step 3: 修正常量**

`app/constants/stored_value.py:5`：`MAX_RECHARGE_FEN = 5_000_00` → `MAX_RECHARGE_FEN = 50_000`

- [ ] **Step 4: 运行确认通过 + 门禁 + 提交**

```powershell
cd D:\Project\YunxiBakeBot
PYTHONUTF8=1 python -m pytest tests/service/test_stored_value.py -q --no-cov --basetemp=D:\Temp\m5_t1b
ruff check app/constants/stored_value.py tests/service/test_stored_value.py
git add app/constants/stored_value.py tests/service/test_stored_value.py
$env:SKIP_LOGBOOK_CHECK=1; git commit -m "fix(stored_value): MAX_RECHARGE_FEN 笔误修正 5000元→500元（50_000 分）"
```

VERSION：0.132.0 → 0.132.1（fix → patch）。

### Task 2: miniapp — 纯函数工具 `member-assets.ts` + `node --test` TDD

**Files:**
- Create: `miniprogram/utils/member-assets.ts`
- Create: `tests/utils/member-assets.test.ts`
- Modify: `package.json`（新增 `test:member-assets` script）

**Interfaces:**
- Produces（供 Task 4/5/6/9 使用）：
  - `classifyCouponStatus(coupon: MemberCoupon, now?: Date): CouponView`
  - `mapPointsSourceLabel(item: PointsLedgerItem): string`
  - `buildPaymentBranch(params: {remainFen: number; balanceFen: number; balanceEnabled: boolean}): "free"|"balance"|"combined"|"online"`
  - `isValidRechargeAmount(amountFen: number): boolean`、`MIN_RECHARGE_FEN`、`MAX_RECHARGE_FEN`
- 本模块为纯函数、零 import（保证 Node 直接加载）。

- [ ] **Step 1: 写失败测试**（Create `tests/utils/member-assets.test.ts`）

```ts
import { test } from "node:test";
import assert from "node:assert/strict";
import {
  classifyCouponStatus,
  mapPointsSourceLabel,
  buildPaymentBranch,
  isValidRechargeAmount,
  MIN_RECHARGE_FEN,
  MAX_RECHARGE_FEN,
  type MemberCoupon,
} from "../../miniprogram/utils/member-assets.ts";

const NOW = new Date("2026-08-14T12:00:00+08:00");

function coupon(overrides: Partial<MemberCoupon>): MemberCoupon {
  return {
    couponId: "c1",
    templateId: "cg_001",
    title: "满30减5",
    status: "TAKE",
    valueFen: 500,
    thresholdFen: 3000,
    deductedFen: 0,
    validFrom: "2026-08-01",
    validUntil: "2026-12-31",
    orderNo: "",
    ...overrides,
  };
}

test("可用券：TAKE 且生效期内", () => {
  const view = classifyCouponStatus(coupon({}), NOW);
  assert.equal(view.tab, "available");
  assert.equal(view.note, "未使用");
});

test("已用券：CONSUME", () => {
  const view = classifyCouponStatus(coupon({ status: "CONSUME" }), NOW);
  assert.equal(view.tab, "used");
  assert.equal(view.note, "已使用");
});

test("已退回券：BACK 文案为已退回", () => {
  const view = classifyCouponStatus(coupon({ status: "BACK" }), NOW);
  assert.equal(view.tab, "refunded");
  assert.equal(view.note, "已退回");
});

test("已过期券：TAKE 且 validUntil 早于今天", () => {
  const view = classifyCouponStatus(coupon({ validUntil: "2026-08-01" }), NOW);
  assert.equal(view.tab, "expired");
  assert.equal(view.note, "已过期");
});

test("未生效券：TAKE 且 validFrom 晚于今天归入已过期组、角标未生效", () => {
  const view = classifyCouponStatus(coupon({ validFrom: "2026-09-01" }), NOW);
  assert.equal(view.tab, "expired");
  assert.equal(view.note, "未生效");
});

test("来源映射按 biz_type 优先级", () => {
  assert.equal(mapPointsSourceLabel({ amount: 100, total: 100, event_type: "order_award", source: "order", biz_type: "order_award" }), "订单奖励");
  assert.equal(mapPointsSourceLabel({ amount: -100, total: 0, event_type: "order_redeem", source: "order", biz_type: "order_redeem" }), "订单抵扣");
  assert.equal(mapPointsSourceLabel({ amount: 100, total: 100, event_type: "order_refund", source: "order", biz_type: "order_refund" }), "退款退回");
  assert.equal(mapPointsSourceLabel({ amount: 50, total: 150, event_type: "", source: "webhook", biz_type: "" }), "有赞同步");
  assert.equal(mapPointsSourceLabel({ amount: 50, total: 200, event_type: "", source: "import", biz_type: "" }), "导入");
});

test("支付分支：remain==0 走 free", () => {
  assert.equal(buildPaymentBranch({ remainFen: 0, balanceFen: 0, balanceEnabled: true }), "free");
});

test("支付分支：余额充足走 balance", () => {
  assert.equal(buildPaymentBranch({ remainFen: 3000, balanceFen: 5000, balanceEnabled: true }), "balance");
});

test("支付分支：余额部分抵扣走 combined", () => {
  assert.equal(buildPaymentBranch({ remainFen: 3000, balanceFen: 1000, balanceEnabled: true }), "combined");
});

test("支付分支：无余额或关闭余额走 online", () => {
  assert.equal(buildPaymentBranch({ remainFen: 3000, balanceFen: 0, balanceEnabled: true }), "online");
  assert.equal(buildPaymentBranch({ remainFen: 3000, balanceFen: 5000, balanceEnabled: false }), "online");
});

test("充值金额边界校验", () => {
  assert.equal(MIN_RECHARGE_FEN, 100);
  assert.equal(MAX_RECHARGE_FEN, 50000);
  assert.equal(isValidRechargeAmount(100), true);
  assert.equal(isValidRechargeAmount(50000), true);
  assert.equal(isValidRechargeAmount(99), false);
  assert.equal(isValidRechargeAmount(50001), false);
  assert.equal(isValidRechargeAmount(0), false);
});
```

- [ ] **Step 2: 运行确认失败**

```powershell
cd D:\Project\YunxiBakeMiniApp
node --test tests/utils/member-assets.test.ts
```

Expected: FAIL——`Cannot find module`（`member-assets.ts` 不存在）。

- [ ] **Step 3: 实现 `miniprogram/utils/member-assets.ts`**

```ts
/** 会员资产纯函数工具：券分类 / 积分来源文案 / 支付分支 / 充值金额校验。 */

export const MIN_RECHARGE_FEN = 100;
export const MAX_RECHARGE_FEN = 50000;

export interface MemberCoupon {
  couponId: string;
  templateId: string;
  title: string;
  status: string;
  valueFen: number;
  thresholdFen: number;
  deductedFen: number;
  validFrom: string;
  validUntil: string;
  orderNo: string;
}

export type CouponTab = "available" | "used" | "refunded" | "expired";

export interface CouponView {
  tab: CouponTab;
  note: string;
}

export interface PointsLedgerItem {
  amount: number;
  total: number;
  event_type: string;
  source: string;
  biz_type: string;
  occurred_at: string;
}

export type PaymentBranch = "free" | "balance" | "combined" | "online";

function dateString(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export function classifyCouponStatus(coupon: MemberCoupon, now: Date = new Date()): CouponView {
  const today = dateString(now);
  if (coupon.status === "CONSUME") {
    return { tab: "used", note: "已使用" };
  }
  if (coupon.status === "BACK") {
    return { tab: "refunded", note: "已退回" };
  }
  if (coupon.status === "TAKE") {
    if (coupon.validUntil && coupon.validUntil < today) {
      return { tab: "expired", note: "已过期" };
    }
    if (coupon.validFrom && coupon.validFrom > today) {
      return { tab: "expired", note: "未生效" };
    }
    return { tab: "available", note: "未使用" };
  }
  return { tab: "expired", note: "已过期" };
}

export function mapPointsSourceLabel(item: PointsLedgerItem): string {
  const biz = item.biz_type || item.event_type || "";
  if (biz === "order_award") {
    return "订单奖励";
  }
  if (biz === "order_redeem") {
    return "订单抵扣";
  }
  if (biz === "order_refund") {
    return "退款退回";
  }
  const source = item.source || "";
  if (source === "webhook") {
    return "有赞同步";
  }
  if (source === "import") {
    return "导入";
  }
  if (source === "order") {
    return "订单消费";
  }
  return "积分变动";
}

export function buildPaymentBranch(params: {
  remainFen: number;
  balanceFen: number;
  balanceEnabled: boolean;
}): PaymentBranch {
  const { remainFen, balanceFen, balanceEnabled } = params;
  if (remainFen <= 0) {
    return "free";
  }
  if (balanceEnabled && balanceFen >= remainFen) {
    return "balance";
  }
  if (balanceEnabled && balanceFen > 0) {
    return "combined";
  }
  return "online";
}

export function isValidRechargeAmount(amountFen: number): boolean {
  return (
    Number.isInteger(amountFen) &&
    amountFen >= MIN_RECHARGE_FEN &&
    amountFen <= MAX_RECHARGE_FEN
  );
}
```

- [ ] **Step 4: 运行确认通过**

```powershell
cd D:\Project\YunxiBakeMiniApp
node --test tests/utils/member-assets.test.ts
```

Expected: 11 pass / 0 fail。

- [ ] **Step 5: package.json 增加测试脚本 + 提交**

package.json `scripts` 增加：

```json
"test:member-assets": "node --test tests/utils/member-assets.test.ts"
```

```powershell
cd D:\Project\YunxiBakeMiniApp
npx tsc --noEmit
git add miniprogram/utils/member-assets.ts tests/utils/member-assets.test.ts package.json
git commit -m "feat(m5): 会员资产纯函数工具（券分类/积分来源/支付分支/充值校验）+ node:test"
```
### Task 3: miniapp — 服务模块（balance/points/coupons/recharges/payment-gate）

**Files:**
- Create: `miniprogram/services/balance.ts`
- Create: `miniprogram/services/points.ts`
- Create: `miniprogram/services/coupons.ts`
- Create: `miniprogram/services/recharges.ts`
- Create: `miniprogram/services/payment-gate.ts`
- Modify: `miniprogram/services/orders.ts`（追加 `payWithBalance` / `prepareCombinedPayment`）
- Modify: `miniprogram/utils/order-payment.ts`（追加 `executePreparedPayment`，`payOrderById` 复用）

**Interfaces:**
- Consumes: `request`（`services/http.ts`）、`IS_USING_LOCAL_API`（`services/config.ts`）、`MemberCoupon`/`PointsLedgerItem`（`utils/member-assets.ts`）
- Produces:
  - `getBalance(): Promise<BalanceSummary>`、`getPoints(): Promise<PointsSummary>`、`getMyCoupons(): Promise<MyCouponsData>`
  - `couponPreview(orderId)` / `applyCoupon(orderId, couponId)` / `pointsPreview(orderId)` / `applyPoints(orderId)`
  - `createRecharge(amountFen)` / `mockPayRecharge(rechargeId)` / `cancelRecharge(rechargeId)` / `listRecharges()`
  - `IS_LOCAL_BACKEND` / `RECHARGE_READY` / `ONLINE_PAYMENT_READY`
  - `payWithBalance(orderId)` / `prepareCombinedPayment(orderId, balanceFen)`（orders.ts）
  - `executePreparedPayment(payment: PreparedPayment): Promise<OrderSummary>`（order-payment.ts）

- [ ] **Step 1: 创建 `services/balance.ts`**

```ts
import { request } from "./http";

export interface BalanceSummary {
  balanceFen: number;
  mobile: string;
}

interface WrappedApiResponse<TData> {
  code: number;
  data: TData;
}

export async function getBalance(): Promise<BalanceSummary> {
  const response = await request<WrappedApiResponse<BalanceSummary> | BalanceSummary>({
    path: "/api/v1/miniapp/balance"
  });
  if (response && typeof response === "object" && "data" in response) {
    return (response as WrappedApiResponse<BalanceSummary>).data;
  }
  return response as BalanceSummary;
}
```

- [ ] **Step 2: 创建 `services/points.ts`**

```ts
import { request } from "./http";
import type { PointsLedgerItem } from "../utils/member-assets";

export interface PointsSummary {
  pointsBalance: number;
  mobile: string;
  ledger: PointsLedgerItem[];
}

export interface PointsPreview {
  orderId: string;
  totalFen: number;
  balanceFen: number;
  pointsFen: number;
  pointsUsed: number;
  remainFen: number;
}

export interface PointsApplied extends PointsPreview {}

interface WrappedApiResponse<TData> {
  code: number;
  data: TData;
}

function unwrap<TData>(response: WrappedApiResponse<TData> | TData): TData {
  if (response && typeof response === "object" && "data" in response) {
    return (response as WrappedApiResponse<TData>).data;
  }
  return response as TData;
}

export async function getPoints(): Promise<PointsSummary> {
  const response = await request<WrappedApiResponse<PointsSummary> | PointsSummary>({
    path: "/api/v1/miniapp/points"
  });
  return unwrap(response);
}

export async function pointsPreview(orderId: string): Promise<PointsPreview> {
  const response = await request<
    WrappedApiResponse<PointsPreview> | PointsPreview,
    Record<string, never>
  >({
    method: "POST",
    path: `/api/v1/miniapp/orders/${orderId}/points-preview`
  });
  return unwrap(response);
}

export async function applyPoints(orderId: string): Promise<PointsApplied> {
  const response = await request<
    WrappedApiResponse<PointsApplied> | PointsApplied,
    Record<string, never>
  >({
    method: "POST",
    path: `/api/v1/miniapp/orders/${orderId}/apply-points`
  });
  return unwrap(response);
}
```

- [ ] **Step 3: 创建 `services/coupons.ts`**

```ts
import { request } from "./http";
import type { MemberCoupon } from "../utils/member-assets";

export interface MyCouponsData {
  mobile: string;
  coupons: MemberCoupon[];
}

export interface CouponPreview {
  orderId: string;
  totalFen: number;
  balanceFen: number;
  pointsFen: number;
  available: Array<{
    couponId: string;
    title: string;
    valueFen: number;
    thresholdFen: number;
    validUntil: string;
    discountFen: number;
    message?: string;
  }>;
  remainFen: number;
}

export interface CouponApplied {
  orderId: string;
  couponId: string;
  couponFen: number;
  totalFen: number;
  balanceFen: number;
  pointsFen: number;
  remainFen: number;
}

interface WrappedApiResponse<TData> {
  code: number;
  data: TData;
}

function unwrap<TData>(response: WrappedApiResponse<TData> | TData): TData {
  if (response && typeof response === "object" && "data" in response) {
    return (response as WrappedApiResponse<TData>).data;
  }
  return response as TData;
}

export async function getMyCoupons(): Promise<MyCouponsData> {
  const response = await request<WrappedApiResponse<MyCouponsData> | MyCouponsData>({
    path: "/api/v1/miniapp/coupons"
  });
  return unwrap(response);
}

export async function couponPreview(orderId: string): Promise<CouponPreview> {
  const response = await request<
    WrappedApiResponse<CouponPreview> | CouponPreview,
    Record<string, never>
  >({
    method: "POST",
    path: `/api/v1/miniapp/orders/${orderId}/coupon-preview`
  });
  return unwrap(response);
}

export async function applyCoupon(orderId: string, couponId: string): Promise<CouponApplied> {
  const response = await request<
    WrappedApiResponse<CouponApplied> | CouponApplied,
    { couponId: string }
  >({
    method: "POST",
    path: `/api/v1/miniapp/orders/${orderId}/apply-coupon`,
    data: { couponId }
  });
  return unwrap(response);
}
```

- [ ] **Step 4: 创建 `services/recharges.ts`**

```ts
import { request } from "./http";

export interface RechargeRecord {
  rechargeId: string;
  amountFen: number;
  status: string;
  paymentMethod: string;
  paidAt: string;
  createdAt: string;
}

interface WrappedApiResponse<TData> {
  code: number;
  data: TData;
}

function unwrap<TData>(response: WrappedApiResponse<TData> | TData): TData {
  if (response && typeof response === "object" && "data" in response) {
    return (response as WrappedApiResponse<TData>).data;
  }
  return response as TData;
}

export async function createRecharge(amountFen: number): Promise<RechargeRecord> {
  const response = await request<
    WrappedApiResponse<RechargeRecord> | RechargeRecord,
    { amountFen: number }
  >({
    method: "POST",
    path: "/api/v1/miniapp/recharges",
    data: { amountFen }
  });
  return unwrap(response);
}

export async function mockPayRecharge(rechargeId: string): Promise<RechargeRecord> {
  const response = await request<
    WrappedApiResponse<RechargeRecord> | RechargeRecord,
    Record<string, never>
  >({
    method: "POST",
    path: `/api/v1/miniapp/recharges/${rechargeId}/mock-pay`
  });
  return unwrap(response);
}

export async function cancelRecharge(rechargeId: string): Promise<RechargeRecord> {
  const response = await request<
    WrappedApiResponse<RechargeRecord> | RechargeRecord,
    Record<string, never>
  >({
    method: "POST",
    path: `/api/v1/miniapp/recharges/${rechargeId}/cancel`
  });
  return unwrap(response);
}

export async function listRecharges(): Promise<RechargeRecord[]> {
  const response = await request<
    WrappedApiResponse<RechargeRecord[]> | RechargeRecord[]
  >({
    path: "/api/v1/miniapp/recharges"
  });
  return unwrap(response);
}
```

- [ ] **Step 5: 创建 `services/payment-gate.ts`**

```ts
import { IS_USING_LOCAL_API } from "./config";

/** 本地后端（mock 支付可用）：IS_USING_LOCAL_API 为 true 时 API_BASE_URL 指向 127.0.0.1:7001。 */
export const IS_LOCAL_BACKEND = IS_USING_LOCAL_API;
/** 充值 mock 确认依赖本地后端。 */
export const RECHARGE_READY = IS_LOCAL_BACKEND;
/** 在线支付路径（prepare-payment / 组合差额会话，需 mock 或微信）依赖本地后端。 */
export const ONLINE_PAYMENT_READY = IS_LOCAL_BACKEND;
```

- [ ] **Step 6: `services/orders.ts` 追加两个方法**

追加到 `prepareOrderPayment` 之后：

```ts
export async function payWithBalance(orderId: string): Promise<OrderSummary> {
  const response = await request<
    WrappedApiResponse<OrderSummary> | OrderSummary,
    Record<string, never>
  >({
    method: "POST",
    path: `/api/v1/miniapp/orders/${orderId}/pay-with-balance`
  });
  return unwrapResponse(response);
}

export async function prepareCombinedPayment(
  orderId: string,
  balanceFen: number
): Promise<PreparedPayment> {
  const response = await request<
    WrappedApiResponse<PreparedPayment> | PreparedPayment,
    { balanceFen: number }
  >({
    method: "POST",
    path: `/api/v1/miniapp/orders/${orderId}/prepare-combined-payment`,
    data: { balanceFen }
  });
  return unwrapResponse(response);
}
```

- [ ] **Step 7: `utils/order-payment.ts` 追加 `executePreparedPayment` 并让 `payOrderById` 复用**

```ts
export async function executePreparedPayment(
  payment: PreparedPayment
): Promise<OrderSummary> {
  if (payment.mode === "wechat") {
    if (!isWechatPaymentParams(payment.paymentParams)) {
      throw new Error("微信支付参数不完整");
    }
    await requestWechatPayment(payment.paymentParams);
    return getOrder(payment.orderId);
  }
  if (payment.mode !== "mock") {
    throw new Error(`未知支付模式: ${payment.mode}`);
  }
  return mockPayOrder(payment.orderId);
}

export async function payOrderById(orderId: string, reloadOrder: () => Promise<OrderSummary>): Promise<OrderSummary> {
  const payment = await prepareOrderPayment(orderId);
  const paidOrder = await executePreparedPayment(payment);
  return reloadOrder ? reloadOrder() : paidOrder;
}
```

注意：`order-payment.ts` 需新增 `getOrder` import（`import { getOrder, mockPayOrder, prepareOrderPayment, ... } from "../services/orders"`），并保留 `reloadOrder` 语义（支付后重新拉取订单状态，兼容既有调用方）。

- [ ] **Step 8: 验证 + 提交**

```powershell
cd D:\Project\YunxiBakeMiniApp
npx tsc --noEmit
node --test tests/utils/member-assets.test.ts
git add miniprogram/services/balance.ts miniprogram/services/points.ts miniprogram/services/coupons.ts miniprogram/services/recharges.ts miniprogram/services/payment-gate.ts miniprogram/services/orders.ts miniprogram/utils/order-payment.ts
git commit -m "feat(m5): 会员资产服务模块（balance/points/coupons/recharges/payment-gate）+ 订单支付扩展"
```

Expected: `tsc --noEmit` 0 error；node:test 11 pass。

### Task 4: miniapp — 我的页资产真实化

**Files:**
- Modify: `miniprogram/pages/profile/index.ts`
- Modify: `miniprogram/pages/profile/index.wxml`
- Modify: `miniprogram/pages/profile/index.wxss`
- Modify: `miniprogram/constants/routes.ts`（预注册 `points`/`coupons`/`recharge` 三个常量，值见 Task 5 Step 1）

**Interfaces:**
- Consumes: `getBalance`（services/balance）、`getPoints`（services/points）、`getMyCoupons`（services/coupons）、`classifyCouponStatus`（utils/member-assets）、`RECHARGE_READY`（services/payment-gate）
- Produces: 资产三项真实数字 + 三个可点击入口；移除权益卡项

- [ ] **Step 1: 改写 `index.ts`**

在现有 `loadProfile` 的 `setData` 基础上，把静态 `memberProps` 的三项资产替换为真实 API。新增方法 `loadMemberAssets`，`loadProfile` 内并行调用：

```ts
async loadMemberAssets() {
  try {
    const [balance, points, couponsData] = await Promise.all([
      getBalance(),
      getPoints(),
      getMyCoupons()
    ]);
    const availableCoupons = (couponsData.coupons || []).filter(
      (coupon) => classifyCouponStatus(coupon).tab === "available"
    );
    this.setData({
      assetBalanceFen: balance.balanceFen,
      assetPoints: points.pointsBalance,
      assetCouponCount: availableCoupons.length,
      assetsLoaded: true
    });
  } catch (error) {
    // 单项整体失败降级：保持 "--" 占位，不阻塞页面（401 由 http 层会话刷新兜底）
    this.setData({ assetsLoaded: true });
  }
}
```

`data` 新增字段并初始化：

```ts
data: {
  // ...既有字段
  assetBalanceFen: 0 as number | null,
  assetPoints: 0 as number | null,
  assetCouponCount: 0 as number | null,
  assetsLoaded: false
}
```

`loadProfile` 中 `this.setData({ memberProps, ... })` 之前调用 `void this.loadMemberAssets()`（放在 `setData({ loading: true })` 之后）。`refreshSession` 成功后调用 `this.setData({ assetsLoaded: false }); await this.loadMemberAssets();`。

- [ ] **Step 2: 改写 `index.wxml` 资产区**

把「芸熙资产」网格改为真实数据 + 可点击：

```xml
<view wx:if="{{sessionView.loggedIn}}" class="metrics-panel glass-panel fade-in">
  <view class="metrics-header">
    <text class="metrics-title">芸熙资产</text>
  </view>
  <view class="metrics-grid">
    <view class="metric-col" bindtap="openRecharge">
      <text class="metric-val">{{assetsLoaded ? (assetBalanceFen != null ? balanceText : '--') : '--'}}</text>
      <text class="metric-lbl">账户余额</text>
      <text wx:if="{{rechargeReady}}" class="metric-entry">去充值 ›</text>
    </view>
    <view class="metric-col" bindtap="openPoints">
      <text class="metric-val">{{assetsLoaded ? (assetPoints != null ? assetPoints : '--') : '--'}}</text>
      <text class="metric-lbl">累积积分</text>
      <text class="metric-entry">明细 ›</text>
    </view>
    <view class="metric-col" bindtap="openCoupons">
      <text class="metric-val">{{assetsLoaded ? (assetCouponCount != null ? assetCouponCount : '--') : '--'}}<text class="metric-unit">张</text></text>
      <text class="metric-lbl">可用优惠券</text>
      <text class="metric-entry">查看 ›</text>
    </view>
  </view>
</view>
```

移除原「权益卡」列。`balanceText` 由 `formatFen(assetBalanceFen)` 派生（`loadMemberAssets` 内 `this.setData({ balanceText: formatFen(balance.balanceFen) })`）。

新增跳转方法：

```ts
openRecharge() {
  if (!RECHARGE_READY) {
    wx.showToast({ title: "充值功能即将上线", icon: "none" });
    return;
  }
  wx.navigateTo({ url: ROUTES.recharge });
},
openPoints() {
  wx.navigateTo({ url: ROUTES.points });
},
openCoupons() {
  wx.navigateTo({ url: ROUTES.coupons });
}
```

`data` 增加 `rechargeReady: RECHARGE_READY`。

- [ ] **Step 3: 改写 `index.wxss`**（追加样式）

```css
.metric-entry {
  margin-top: 4rpx;
  font-size: 22rpx;
  color: #6c9a63;
}
```

- [ ] **Step 4: 验证 + 提交**

```powershell
cd D:\Project\YunxiBakeMiniApp
npx tsc --noEmit
git add miniprogram/pages/profile/index.ts miniprogram/pages/profile/index.wxml miniprogram/pages/profile/index.wxss miniprogram/constants/routes.ts
git commit -m "feat(m5): 我的页资产三项真实 API（余额/积分/可用券）+ 可点击入口，移除权益卡"
```

注意：`tsc` 只校验常量存在性，不校验页面文件是否已创建；`ROUTES.points/coupons/recharge` 在本任务即注册，页面文件在 Task 5/6/8 创建。

### Task 5: miniapp — 积分明细页

**Files:**
- Create: `miniprogram/pages/points/index.ts` / `index.wxml` / `index.wxss` / `index.json`
- Modify: `miniprogram/app.json`（pages 追加）
- Modify: `miniprogram/constants/routes.ts`（追加 `points`）

**Interfaces:**
- Consumes: `getPoints`（services/points）、`mapPointsSourceLabel`（utils/member-assets）、`formatFen`（utils/money）、`getMiniappLayoutMetrics`（utils/layout）、`goBackOrHome`（utils/navigation）
- Produces: 独立积分明细页 `pages/points/index`（含自定义导航头）

- [ ] **Step 1: routes.ts 追加常量**

```ts
points: "/pages/points/index",
coupons: "/pages/coupons/index",
recharge: "/pages/recharge/index"
```

- [ ] **Step 2: app.json pages 数组追加**

```json
"pages/points/index",
"pages/coupons/index",
"pages/recharge/index"
```

- [ ] **Step 3: 创建 `pages/points/index.json`**

```json
{
  "navigationBarTitleText": "积分明细",
  "usingComponents": {}
}
```

- [ ] **Step 4: 创建 `pages/points/index.ts`**

```ts
import { getPoints } from "../../services/points";
import { mapPointsSourceLabel, type PointsLedgerItem } from "../../utils/member-assets";
import { getErrorMessage } from "../../services/http";
import { getMiniappLayoutMetrics } from "../../utils/layout";
import { isMiniappLoggedIn, buildMiniappSessionView } from "../../utils/session";
import { getMiniappSession } from "../../services/auth";
import { goBackOrHome } from "../../utils/navigation";

interface PointsRow {
  amount: number;
  total: number;
  label: string;
  occurredAt: string;
  displayTime: string;
}

function formatTime(value: string): string {
  const raw = value || "";
  return raw.replace("T", " ").slice(0, 16);
}

function toRow(item: PointsLedgerItem): PointsRow {
  return {
    amount: Number(item.amount || 0),
    total: Number(item.total || 0),
    label: mapPointsSourceLabel(item),
    occurredAt: item.occurred_at || "",
    displayTime: formatTime(item.occurred_at)
  };
}

Page({
  data: {
    pointsBalance: 0 as number | null,
    rows: [] as PointsRow[],
    loading: true,
    loadFailed: false,
    loggedIn: false,
    layoutStyle: getMiniappLayoutMetrics().pageShellStyle
  },
  onShow() {
    void this.loadPoints();
  },
  async loadPoints() {
    const session = getMiniappSession();
    if (!isMiniappLoggedIn(session)) {
      this.setData({ loggedIn: false, loading: false });
      return;
    }
    this.setData({ loggedIn: true, loading: true, loadFailed: false });
    try {
      const points = await getPoints();
      this.setData({
        pointsBalance: points.pointsBalance,
        rows: (points.ledger || []).map(toRow),
        loading: false
      });
    } catch (error) {
      this.setData({ loading: false, loadFailed: true });
      wx.showToast({ title: getErrorMessage(error, "积分明细加载失败"), icon: "none" });
    }
  },
  goLogin() {
    wx.switchTab({ url: "/pages/profile/index" });
  },
  goBack() {
    goBackOrHome();
  }
});
```

- [ ] **Step 5: 创建 `pages/points/index.wxml`**

```xml
<view class="page-shell" style="{{layoutStyle}}">
  <view class="page-fixed-safe has-custom-title">
    <button class="page-nav-back" bindtap="goBack" aria-label="返回">
      <text class="page-nav-back__icon">‹</text>
    </button>
    <view class="page-fixed-safe__title">积分明细</view>
  </view>
  <view class="page-pinned page-pinned--empty"></view>
  <scroll-view class="page-scroll" scroll-y enhanced show-scrollbar="{{false}}">
    <view class="page points-page">
      <view wx:if="{{!loggedIn}}" class="empty-panel glass-panel">
        <text class="empty-title">请先登录</text>
        <button class="primary-btn" bindtap="goLogin">去登录</button>
      </view>
      <block wx:else>
        <view class="balance-panel glass-panel fade-in">
          <text class="balance-label">当前积分</text>
          <text class="balance-value">{{pointsBalance != null ? pointsBalance : '--'}}</text>
        </view>
        <view wx:if="{{loading}}" class="empty-panel glass-panel">
          <text class="empty-title">加载中...</text>
        </view>
        <view wx:elif="{{loadFailed}}" class="empty-panel glass-panel">
          <text class="empty-title">加载失败，请稍后重试</text>
        </view>
        <view wx:elif="{{rows.length === 0}}" class="empty-panel glass-panel">
          <text class="empty-title">暂无积分记录</text>
          <text class="empty-subtitle">下单消费可获得积分奖励</text>
        </view>
        <view wx:else class="ledger-list">
          <view wx:for="{{rows}}" wx:key="index" class="ledger-row">
            <view class="ledger-main">
              <text class="ledger-label">{{item.label}}</text>
              <text class="ledger-time">{{item.displayTime}}</text>
            </view>
            <view class="ledger-amount {{item.amount >= 0 ? 'positive' : 'negative'}}">
              {{item.amount >= 0 ? '+' : ''}}{{item.amount}}
            </view>
            <view class="ledger-total">余额 {{item.total}}</view>
          </view>
        </view>
      </block>
    </view>
  </scroll-view>
</view>
```

- [ ] **Step 6: 创建 `pages/points/index.wxss`**（沿用 profile 页 glass-panel 体系）

```css
.points-page {
  padding: 24rpx;
}
.balance-panel {
  padding: 40rpx 32rpx;
  margin-bottom: 24rpx;
  display: flex;
  flex-direction: column;
  align-items: center;
}
.balance-label {
  font-size: 26rpx;
  color: #756d66;
}
.balance-value {
  margin-top: 12rpx;
  font-size: 64rpx;
  font-weight: 700;
  color: #2d2a26;
}
.ledger-list {
  display: flex;
  flex-direction: column;
}
.ledger-row {
  display: flex;
  align-items: center;
  padding: 24rpx 8rpx;
  border-bottom: 1rpx solid #efeae4;
}
.ledger-main {
  flex: 1;
  display: flex;
  flex-direction: column;
}
.ledger-label {
  font-size: 30rpx;
  color: #2d2a26;
}
.ledger-time {
  margin-top: 6rpx;
  font-size: 22rpx;
  color: #a29a90;
}
.ledger-amount {
  font-size: 30rpx;
  font-weight: 600;
}
.ledger-amount.positive {
  color: #6c9a63;
}
.ledger-amount.negative {
  color: #c25b4e;
}
.ledger-total {
  margin-left: 20rpx;
  font-size: 22rpx;
  color: #a29a90;
}
.empty-panel {
  padding: 80rpx 32rpx;
  align-items: center;
  display: flex;
  flex-direction: column;
}
.empty-title {
  font-size: 30rpx;
  color: #756d66;
}
.empty-subtitle {
  margin-top: 12rpx;
  font-size: 24rpx;
  color: #a29a90;
}
```

- [ ] **Step 7: 验证 + 提交**

```powershell
cd D:\Project\YunxiBakeMiniApp
npx tsc --noEmit
git add miniprogram/pages/points miniprogram/app.json miniprogram/constants/routes.ts
git commit -m "feat(m5): 积分明细页（余额 + ledger 流水 + 来源文案）"
```

### Task 6: miniapp — 优惠券中心页

**Files:**
- Create: `miniprogram/pages/coupons/index.ts` / `index.wxml` / `index.wxss` / `index.json`
- Modify: `miniprogram/app.json`（pages 已在 Task 5 追加）

**Interfaces:**
- Consumes: `getMyCoupons`（services/coupons）、`classifyCouponStatus`/`MemberCoupon`（utils/member-assets）、`formatFen`（utils/money）、`getMiniappLayoutMetrics`（utils/layout）、`goBackOrHome`（utils/navigation）
- Produces: 独立券中心页 `pages/coupons/index`（tab：可用/已用/已退回/已过期，含自定义导航头）

- [ ] **Step 1: 创建 `pages/coupons/index.json`**

```json
{
  "navigationBarTitleText": "我的优惠券",
  "usingComponents": {}
}
```

- [ ] **Step 2: 创建 `pages/coupons/index.ts`**

```ts
import { getMyCoupons } from "../../services/coupons";
import {
  classifyCouponStatus,
  type CouponTab,
  type MemberCoupon
} from "../../utils/member-assets";
import { formatFen } from "../../utils/money";
import { getErrorMessage } from "../../services/http";
import { getMiniappLayoutMetrics } from "../../utils/layout";
import { isMiniappLoggedIn } from "../../utils/session";
import { getMiniappSession } from "../../services/auth";
import { goBackOrHome } from "../../utils/navigation";

const TABS: Array<{ key: CouponTab; title: string }> = [
  { key: "available", title: "可用" },
  { key: "used", title: "已用" },
  { key: "refunded", title: "已退回" },
  { key: "expired", title: "已过期" }
];

interface CouponCard {
  couponId: string;
  title: string;
  valueFen: number;
  thresholdFen: number;
  validText: string;
  note: string;
  orderNo: string;
  deductedFen: number;
  deductedText: string;
}

function toCard(coupon: MemberCoupon): CouponCard {
  const view = classifyCouponStatus(coupon);
  const validText = coupon.validFrom
    ? `${coupon.validFrom} ~ ${coupon.validUntil || "长期"}`
    : coupon.validUntil || "";
  return {
    couponId: coupon.couponId,
    title: coupon.title || "优惠券",
    valueFen: coupon.valueFen,
    thresholdFen: coupon.thresholdFen,
    validText,
    note: view.note,
    orderNo: coupon.orderNo,
    deductedFen: coupon.deductedFen,
    deductedText: formatFen(coupon.deductedFen)
  };
}

Page({
  data: {
    tabs: TABS,
    activeTab: "available" as CouponTab,
    groups: {} as Record<CouponTab, CouponCard[]>,
    loading: true,
    loadFailed: false,
    loggedIn: false,
    layoutStyle: getMiniappLayoutMetrics().pageShellStyle
  },
  onShow() {
    void this.loadCoupons();
  },
  switchTab(event: WechatMiniprogram.TouchEvent) {
    const key = event.currentTarget.dataset.tab as CouponTab;
    this.setData({ activeTab: key });
  },
  async loadCoupons() {
    const session = getMiniappSession();
    if (!isMiniappLoggedIn(session)) {
      this.setData({ loggedIn: false, loading: false });
      return;
    }
    this.setData({ loggedIn: true, loading: true, loadFailed: false });
    try {
      const data = await getMyCoupons();
      const groups: Record<CouponTab, CouponCard[]> = {
        available: [],
        used: [],
        refunded: [],
        expired: []
      };
      (data.coupons || []).forEach((coupon) => {
        const tab = classifyCouponStatus(coupon).tab;
        groups[tab].push(toCard(coupon));
      });
      this.setData({ groups, loading: false });
    } catch (error) {
      this.setData({ loading: false, loadFailed: true });
      wx.showToast({ title: getErrorMessage(error, "优惠券加载失败"), icon: "none" });
    }
  },
  goLogin() {
    wx.switchTab({ url: "/pages/profile/index" });
  },
  goBack() {
    goBackOrHome();
  }
});
```

- [ ] **Step 3: 创建 `pages/coupons/index.wxml`**

```xml
<view class="page-shell" style="{{layoutStyle}}">
  <view class="page-fixed-safe has-custom-title">
    <button class="page-nav-back" bindtap="goBack" aria-label="返回">
      <text class="page-nav-back__icon">‹</text>
    </button>
    <view class="page-fixed-safe__title">我的优惠券</view>
  </view>
  <view class="page-pinned page-pinned--empty"></view>
  <scroll-view class="page-scroll" scroll-y enhanced show-scrollbar="{{false}}">
    <view class="page coupons-page">
      <view wx:if="{{!loggedIn}}" class="empty-panel glass-panel">
        <text class="empty-title">请先登录</text>
        <text class="empty-subtitle">登录后查看您的优惠券</text>
        <button class="primary-btn" bindtap="goLogin">去登录</button>
      </view>
      <block wx:else>
        <view class="coupon-tabs">
          <view
            wx:for="{{tabs}}"
            wx:key="key"
            class="coupon-tab {{activeTab === item.key ? 'active' : ''}}"
            data-tab="{{item.key}}"
            bindtap="switchTab"
          >
            <text>{{item.title}}</text>
            <text class="coupon-tab-count">{{groups[item.key].length}}</text>
          </view>
        </view>
        <view wx:if="{{loading}}" class="empty-panel glass-panel">
          <text class="empty-title">加载中...</text>
        </view>
        <view wx:elif="{{loadFailed}}" class="empty-panel glass-panel">
          <text class="empty-title">加载失败，请稍后重试</text>
        </view>
        <view wx:elif="{{groups[activeTab].length === 0}}" class="empty-panel glass-panel">
          <text class="empty-title">暂无{{activeTab === 'available' ? '可用' : '相关'}}优惠券</text>
        </view>
        <view wx:else class="coupon-list">
          <view wx:for="{{groups[activeTab]}}" wx:key="couponId" class="coupon-card">
            <view class="coupon-value">
              <text class="coupon-value-num">{{item.valueFen / 100}}</text>
              <text class="coupon-value-unit">元</text>
            </view>
            <view class="coupon-info">
              <text class="coupon-title">{{item.title}}</text>
              <text wx:if="{{item.thresholdFen > 0}}" class="coupon-threshold">满{{item.thresholdFen / 100}}元可用</text>
              <text wx:else class="coupon-threshold">无门槛</text>
              <text class="coupon-valid">{{item.validText}}</text>
              <text wx:if="{{item.note === '已使用' && item.orderNo}}" class="coupon-order">订单号 {{item.orderNo}}</text>
              <text wx:if="{{item.note === '已使用' && item.deductedFen > 0}}" class="coupon-order">已抵扣 {{item.deductedText}}</text>
            </view>
            <view class="coupon-note">{{item.note}}</view>
          </view>
        </view>
      </block>
    </view>
  </scroll-view>
</view>
```

- [ ] **Step 4: 创建 `pages/coupons/index.wxss`**（沿用 glass-panel 体系）

```css
.coupons-page {
  padding: 24rpx;
}
.coupon-tabs {
  display: flex;
  gap: 16rpx;
  margin-bottom: 24rpx;
}
.coupon-tab {
  flex: 1;
  padding: 16rpx 0;
  text-align: center;
  font-size: 28rpx;
  color: #756d66;
  background: #f5f1ea;
  border-radius: 12rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8rpx;
}
.coupon-tab.active {
  color: #ffffff;
  background: #6c9a63;
}
.coupon-tab-count {
  font-size: 22rpx;
  opacity: 0.85;
}
.coupon-list {
  display: flex;
  flex-direction: column;
  gap: 20rpx;
}
.coupon-card {
  display: flex;
  align-items: stretch;
  background: #ffffff;
  border-radius: 16rpx;
  overflow: hidden;
  border: 1rpx solid #efeae4;
}
.coupon-value {
  width: 180rpx;
  display: flex;
  align-items: baseline;
  justify-content: center;
  padding: 28rpx 0;
  background: linear-gradient(135deg, #f6e6c8, #f2d9a8);
  color: #8a5a1e;
}
.coupon-value-num {
  font-size: 48rpx;
  font-weight: 700;
}
.coupon-value-unit {
  font-size: 24rpx;
}
.coupon-info {
  flex: 1;
  padding: 20rpx 24rpx;
  display: flex;
  flex-direction: column;
  gap: 6rpx;
}
.coupon-title {
  font-size: 30rpx;
  font-weight: 600;
  color: #2d2a26;
}
.coupon-threshold,
.coupon-valid,
.coupon-order {
  font-size: 22rpx;
  color: #a29a90;
}
.coupon-note {
  writing-mode: vertical-rl;
  padding: 20rpx 12rpx;
  font-size: 22rpx;
  color: #c25b4e;
  background: #faf7f2;
  display: flex;
  align-items: center;
}
.empty-panel {
  padding: 80rpx 32rpx;
  align-items: center;
  display: flex;
  flex-direction: column;
}
.empty-title {
  font-size: 30rpx;
  color: #756d66;
}
.empty-subtitle {
  margin-top: 12rpx;
  font-size: 24rpx;
  color: #a29a90;
}
```

- [ ] **Step 5: 验证 + 提交**

```powershell
cd D:\Project\YunxiBakeMiniApp
npx tsc --noEmit
node --test tests/utils/member-assets.test.ts
git add miniprogram/pages/coupons
git commit -m "feat(m5): 优惠券中心页（可用/已用/已退回/已过期 tab）"
```
### Task 7: miniapp — API 契约与页面覆盖同步 + Phase 1 收口

**Files:**
- Modify: `docs/api-contract.md`（profile 契约改真实 API + 新增 3 页面契约）
- Modify: `docs/page-api-coverage.md`（新增 3 页面覆盖行）
- Modify: `scripts/check-page-api-coverage.mjs`（`requiredPages` 追加 3 页面）
- Modify: `LOGBOOK.md`、`docs/harness-engineering/core/evidence-index.md`（Phase 1 收口，trace_id）

**Interfaces:**
- Consumes: 已完成页面（Task 4/5/6）与 API 路径
- Produces: 契约文档与覆盖检查通过

- [ ] **Step 1: 更新 `docs/api-contract.md`**

将「小程序『我的』页必须从 `memberSummary` 读取余额、积分、权益卡、优惠券、会员卡副标题和有效期文案」一节改为：

```markdown
### 会员资产（M5 修订）

- 我的页资产数字（余额/积分/可用券数）必须来自真实 API，不得从 `memberSummary` 装修配置读取：
  - 余额：`GET /api/v1/miniapp/balance` → `balanceFen`
  - 积分：`GET /api/v1/miniapp/points` → `pointsBalance`（含 `ledger` 明细，上限 50 条倒序）
  - 可用券数：`GET /api/v1/miniapp/coupons` → `coupons`，按 `status=TAKE` 且 `validFrom <= today <= validUntil` 计数
- `memberSummary` 装修配置只负责等级文案、会员卡副标题、有效期文案等展示字段；权益卡数量无数据源，不展示。
- 券中心：`GET /api/v1/miniapp/coupons`，tab 可用/已用/已退回/已过期由前端按 `status` + 有效期派生。
- 充值：`POST /api/v1/miniapp/recharges`（amountFen，100~50000）、`POST /api/v1/miniapp/recharges/{recharge_id}/mock-pay`、`POST /api/v1/miniapp/recharges/{recharge_id}/cancel`、`GET /api/v1/miniapp/recharges`。
- 结算扩展：`POST /api/v1/miniapp/orders/{order_id}/coupon-preview`、`POST /api/v1/miniapp/orders/{order_id}/apply-coupon`、`POST /api/v1/miniapp/orders/{order_id}/points-preview`、`POST /api/v1/miniapp/orders/{order_id}/apply-points`、`POST /api/v1/miniapp/orders/{order_id}/pay-with-balance`、`POST /api/v1/miniapp/orders/{order_id}/prepare-combined-payment`、`POST /api/v1/miniapp/orders/{order_id}/prepare-payment`、`POST /api/v1/miniapp/orders/{order_id}/mock-pay`。
- 支付能力边界：在线支付（mock/微信）仅本地后端可用（`IS_USING_LOCAL_API`）；生产 release 仅余额支付可用。
```

- [ ] **Step 2: 更新 `scripts/check-page-api-coverage.mjs`**

`requiredPages` 数组追加三项：

```js
"pages/points/index",
"pages/coupons/index",
"pages/recharge/index",
```

`requiredCoverageTerms` 追加：

```js
"GET /api/v1/miniapp/balance",
"GET /api/v1/miniapp/points",
"GET /api/v1/miniapp/coupons",
"GET /api/v1/miniapp/recharges",
"POST /api/v1/miniapp/recharges",
"POST /api/v1/miniapp/orders/{orderId}/apply-coupon",
"POST /api/v1/miniapp/orders/{orderId}/apply-points",
"POST /api/v1/miniapp/orders/{orderId}/pay-with-balance",
"POST /api/v1/miniapp/orders/{orderId}/prepare-combined-payment",
```

- [ ] **Step 3: 更新 `docs/page-api-coverage.md`**

覆盖表追加三行：

```markdown
| `pages/points/index` | 积分余额与明细 | `GET /api/v1/miniapp/points` | 已有 API 契约 |
| `pages/coupons/index` | 我的优惠券（tab 分组） | `GET /api/v1/miniapp/coupons` | 已有 API 契约 |
| `pages/recharge/index` | 充值（档位/自定义/mock 确认/记录） | `POST /api/v1/miniapp/recharges`、`POST /api/v1/miniapp/recharges/{recharge_id}/mock-pay`、`GET /api/v1/miniapp/recharges` | 已有 API 契约；入口受 `RECHARGE_READY` 控制 |
```

- [ ] **Step 4: 运行覆盖检查**

```powershell
cd D:\Project\YunxiBakeMiniApp
npm run check:page-api-coverage
npm run check:miniapp
```

Expected: 两脚本 pass。若 `check:miniapp` 检查 profile 装修字段与真实 API 冲突，同步调整其断言（以本计划契约为准）。

- [ ] **Step 5: Phase 1 收口——LOGBOOK + evidence-index**

`LOGBOOK.md` 顶部追加（trace_id `20260814-member-loyalty-m5`，Phase 1）：

```markdown
## 2026-08-14 - M5 Phase 1：展示类页面交付（我的页真实化/积分明细/券中心）

- trace_id: 20260814-member-loyalty-m5
- 变更: 我的页资产三项接真实 API；新增积分明细页与优惠券中心页；Platform `get_my_coupons` 补 thresholdFen（跨仓小任务）。
- 验证: `tsc --noEmit` 0 error；`node --test tests/utils/member-assets.test.ts` 11 pass；`npm run check:page-api-coverage` / `check:miniapp` pass；Platform `tests/api/test_miniapp_coupons_api.py` 4 passed。
- 待办: Phase 2 充值页 + 结算页扩展；交易类联调需 IS_USING_LOCAL_API=1 连本地后端。
```

`docs/harness-engineering/core/evidence-index.md` 登记上述命令输出证据。

- [ ] **Step 6: 提交**

```powershell
cd D:\Project\YunxiBakeMiniApp
git add docs/api-contract.md docs/page-api-coverage.md scripts/check-page-api-coverage.mjs LOGBOOK.md docs/harness-engineering/core/evidence-index.md
git commit -m "docs(m5): API 契约与页面覆盖同步 + Phase 1 收口（trace 20260814-member-loyalty-m5）"
```

Phase 1 结束。进入 Phase 2 前，先本地起 Platform（mock 模式）在微信开发者工具联调展示类三页（我的页/积分明细/券中心），确认资产数字与真实数据一致。

---

## Phase 2：交易类

### Task 8: miniapp — 充值页

**Files:**
- Create: `miniprogram/utils/recharge-config.ts`（档位配置，含 bonusFen 口子）
- Create: `miniprogram/pages/recharge/index.ts` / `index.wxml` / `index.wxss` / `index.json`
- Modify: `miniprogram/app.json`（pages 已在 Task 5 追加）

**Interfaces:**
- Consumes: `getBalance`、`createRecharge`/`mockPayRecharge`/`cancelRecharge`/`listRecharges`、`isValidRechargeAmount`/`MIN_RECHARGE_FEN`/`MAX_RECHARGE_FEN`、`RECHARGE_READY`、`formatFen`、`goBackOrHome`（utils/navigation）
- Produces: 充值页（档位 + 自定义 + 确认弹窗 + mock 支付 + 记录列表，含自定义导航头）

- [ ] **Step 1: 创建 `miniprogram/utils/recharge-config.ts`**

```ts
/** 充值档位配置：档位与赠送金额确定后只改本文件。bonusFen 仅展示占位，实际到账以服务端 amountFen 为准。 */
export interface RechargeTier {
  amountFen: number;
  bonusFen: number;
}

export const RECHARGE_TIERS: RechargeTier[] = [
  { amountFen: 10000, bonusFen: 0 },
  { amountFen: 20000, bonusFen: 0 },
  { amountFen: 30000, bonusFen: 0 },
  { amountFen: 50000, bonusFen: 0 }
];
// 档位任何一项不得超出 MAX_RECHARGE_FEN（50000 分 = 500 元）；档位/赠送确定后只改本文件。

export function hasRechargeBonus(): boolean {
  return RECHARGE_TIERS.some((tier) => tier.bonusFen > 0);
}
```

- [ ] **Step 2: 创建 `pages/recharge/index.json`**

```json
{
  "navigationBarTitleText": "余额充值",
  "usingComponents": {}
}
```

- [ ] **Step 3: 创建 `pages/recharge/index.ts`**

```ts
import { getBalance } from "../../services/balance";
import {
  createRecharge,
  mockPayRecharge,
  cancelRecharge,
  listRecharges,
  type RechargeRecord
} from "../../services/recharges";
import { RECHARGE_READY } from "../../services/payment-gate";
import {
  isValidRechargeAmount,
  MIN_RECHARGE_FEN,
  MAX_RECHARGE_FEN
} from "../../utils/member-assets";
import { RECHARGE_TIERS, hasRechargeBonus, type RechargeTier } from "../../utils/recharge-config";
import { formatFen } from "../../utils/money";
import { getErrorMessage } from "../../services/http";
import { getMiniappLayoutMetrics } from "../../utils/layout";
import { isMiniappLoggedIn } from "../../utils/session";
import { getMiniappSession } from "../../services/auth";
import { goBackOrHome } from "../../utils/navigation";

const STATUS_TEXT: Record<string, string> = {
  unpaid: "待支付",
  paid: "已到账",
  cancelled: "已取消",
  expired: "已过期"
};

Page({
  data: {
    ready: RECHARGE_READY,
    tiers: RECHARGE_TIERS as RechargeTier[],
    showBonus: hasRechargeBonus(),
    selectedTierFen: 10000,
    customFen: "",
    balanceFen: 0 as number | null,
    balanceText: "",
    statusTextMap: STATUS_TEXT,
    records: [] as RechargeRecord[],
    loading: true,
    submitting: false,
    loggedIn: false,
    layoutStyle: getMiniappLayoutMetrics().pageShellStyle
  },
  onShow() {
    void this.loadPage();
  },
  async loadPage() {
    const session = getMiniappSession();
    if (!isMiniappLoggedIn(session)) {
      this.setData({ loggedIn: false, loading: false });
      return;
    }
    this.setData({ loggedIn: true, loading: true });
    try {
      const [balance, records] = await Promise.all([getBalance(), listRecharges()]);
      this.setData({ balanceFen: balance.balanceFen, records, loading: false });
    } catch (error) {
      this.setData({ loading: false });
      wx.showToast({ title: getErrorMessage(error, "充值信息加载失败"), icon: "none" });
    }
  },
  selectTier(event: WechatMiniprogram.TouchEvent) {
    const amountFen = Number(event.currentTarget.dataset.fen);
    this.setData({ selectedTierFen: amountFen, customFen: "" });
  },
  onCustomInput(event: WechatMiniprogram.Input) {
    this.setData({ customFen: event.detail.value });
  },
  getAmountFen(): number {
    if (this.data.customFen) {
      const yuan = Number(this.data.customFen);
      return Math.round(yuan * 100);
    }
    return this.data.selectedTierFen;
  },
  async submitRecharge() {
    if (this.data.submitting) {
      return;
    }
    if (!RECHARGE_READY) {
      wx.showToast({ title: "充值功能即将上线", icon: "none" });
      return;
    }
    const amountFen = this.getAmountFen();
    if (!isValidRechargeAmount(amountFen)) {
      wx.showToast({
        title: `充值金额需在 ${MIN_RECHARGE_FEN / 100}~${MAX_RECHARGE_FEN / 100} 元之间`,
        icon: "none"
      });
      return;
    }
    this.setData({ submitting: true });
    try {
      const recharge = await createRecharge(amountFen);
      const confirmed = await new Promise<boolean>((resolve) => {
        wx.showModal({
          title: "确认充值",
          content: `充值金额 ${formatFen(recharge.amountFen)}，确认支付？`,
          confirmText: "确认支付",
          cancelText: "取消",
          success: (res) => resolve(Boolean(res.confirm)),
          fail: () => resolve(false)
        });
      });
      if (!confirmed) {
        this.setData({ submitting: false });
        return;
      }
      await mockPayRecharge(recharge.rechargeId);
      wx.showToast({ title: "充值成功", icon: "success" });
      await this.loadPage();
    } catch (error) {
      wx.showToast({ title: getErrorMessage(error, "充值失败，请稍后重试"), icon: "none" });
    } finally {
      this.setData({ submitting: false });
    }
  },
  cancelRecord(event: WechatMiniprogram.TouchEvent) {
    const rechargeId = event.currentTarget.dataset.id as string;
    wx.showModal({
      title: "取消充值",
      content: "确定取消这笔未支付充值？",
      success: async (res) => {
        if (!res.confirm) {
          return;
        }
        try {
          await cancelRecharge(rechargeId);
          await this.loadPage();
        } catch (error) {
          wx.showToast({ title: getErrorMessage(error, "取消失败"), icon: "none" });
        }
      }
    });
  },
  goBack() {
    goBackOrHome();
  }
});
```

- [ ] **Step 4: 创建 `pages/recharge/index.wxml`**

```xml
<view class="page-shell" style="{{layoutStyle}}">
  <view class="page-fixed-safe has-custom-title">
    <button class="page-nav-back" bindtap="goBack" aria-label="返回">
      <text class="page-nav-back__icon">‹</text>
    </button>
    <view class="page-fixed-safe__title">余额充值</view>
  </view>
  <view class="page-pinned page-pinned--empty"></view>
  <scroll-view class="page-scroll" scroll-y enhanced show-scrollbar="{{false}}">
    <view class="page recharge-page">
      <view wx:if="{{!loggedIn}}" class="empty-panel glass-panel">
        <text class="empty-title">请先登录</text>
        <text class="empty-subtitle">登录后使用余额充值</text>
      </view>
      <block wx:elif="{{!ready}}">
        <view class="empty-panel glass-panel">
          <text class="empty-title">充值功能即将上线</text>
          <text class="empty-subtitle">微信支付接入后开放</text>
        </view>
      </block>
      <block wx:else>
        <view class="balance-panel glass-panel fade-in">
          <text class="balance-label">当前余额</text>
          <text class="balance-value">{{balanceFen != null ? balanceText : '--'}}</text>
        </view>
        <view class="tier-panel glass-panel">
          <view class="section-title">选择充值金额</view>
          <view class="tier-grid">
            <view
              wx:for="{{tiers}}"
              wx:key="amountFen"
              class="tier-cell {{selectedTierFen === item.amountFen && !customFen ? 'active' : ''}}"
              data-fen="{{item.amountFen}}"
              bindtap="selectTier"
            >
              <text class="tier-amount">{{item.amountFen / 100}}元</text>
              <text wx:if="{{showBonus && item.bonusFen > 0}}" class="tier-bonus">送{{item.bonusFen / 100}}元</text>
            </view>
          </view>
          <view class="custom-row">
            <text class="custom-label">自定义金额</text>
            <input
              class="custom-input"
              type="digit"
              placeholder="1~500"
              value="{{customFen}}"
              bindinput="onCustomInput"
            />
            <text class="custom-unit">元</text>
          </view>
          <button class="primary-btn" loading="{{submitting}}" disabled="{{submitting}}" bindtap="submitRecharge">
            确认充值
          </button>
          <text wx:if="{{showBonus}}" class="bonus-note">充值赠送以活动规则为准，实际到账金额以支付确认页为准</text>
        </view>
        <view class="records-panel glass-panel">
          <view class="section-title">充值记录</view>
          <view wx:if="{{records.length === 0}}" class="records-empty">暂无充值记录</view>
          <view wx:for="{{records}}" wx:key="rechargeId" class="record-row">
            <view class="record-main">
              <text class="record-amount">{{item.amountFen / 100}}元</text>
              <text class="record-time">{{item.createdAt}}</text>
            </view>
            <view class="record-status">{{statusTextMap[item.status] || item.status}}</view>
            <text
              wx:if="{{item.status === 'unpaid'}}"
              class="record-cancel"
              data-id="{{item.rechargeId}}"
              bindtap="cancelRecord"
            >取消</text>
          </view>
        </view>
      </block>
    </view>
  </scroll-view>
</view>
```

`loadPage` 成功后派生文本字段：`this.setData({ balanceText: formatFen(balance.balanceFen) })`。

- [ ] **Step 5: 创建 `pages/recharge/index.wxss`**（沿用 glass-panel 体系）

```css
.recharge-page {
  padding: 24rpx;
  display: flex;
  flex-direction: column;
  gap: 24rpx;
}
.balance-panel {
  padding: 40rpx 32rpx;
  display: flex;
  flex-direction: column;
  align-items: center;
}
.balance-label {
  font-size: 26rpx;
  color: #756d66;
}
.balance-value {
  margin-top: 12rpx;
  font-size: 64rpx;
  font-weight: 700;
  color: #2d2a26;
}
.tier-panel,
.records-panel {
  padding: 28rpx 24rpx;
}
.section-title {
  font-size: 30rpx;
  font-weight: 600;
  color: #2d2a26;
  margin-bottom: 20rpx;
}
.tier-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16rpx;
}
.tier-cell {
  padding: 24rpx 0;
  text-align: center;
  border-radius: 12rpx;
  border: 2rpx solid #e5ddd2;
  background: #ffffff;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6rpx;
}
.tier-cell.active {
  border-color: #6c9a63;
  background: #f0f7ee;
}
.tier-amount {
  font-size: 34rpx;
  font-weight: 700;
  color: #2d2a26;
}
.tier-bonus {
  font-size: 22rpx;
  color: #c25b4e;
}
.custom-row {
  display: flex;
  align-items: center;
  gap: 16rpx;
  margin-top: 24rpx;
}
.custom-label {
  font-size: 28rpx;
  color: #2d2a26;
}
.custom-input {
  flex: 1;
  border-bottom: 2rpx solid #e5ddd2;
  padding: 12rpx 8rpx;
  font-size: 30rpx;
}
.custom-unit {
  font-size: 26rpx;
  color: #756d66;
}
.bonus-note {
  margin-top: 16rpx;
  font-size: 22rpx;
  color: #a29a90;
}
.records-empty {
  padding: 40rpx 0;
  text-align: center;
  color: #a29a90;
  font-size: 26rpx;
}
.record-row {
  display: flex;
  align-items: center;
  padding: 20rpx 0;
  border-bottom: 1rpx solid #f0ece6;
}
.record-main {
  flex: 1;
  display: flex;
  flex-direction: column;
}
.record-amount {
  font-size: 30rpx;
  font-weight: 600;
  color: #2d2a26;
}
.record-time {
  margin-top: 4rpx;
  font-size: 22rpx;
  color: #a29a90;
}
.record-status {
  font-size: 26rpx;
  color: #756d66;
}
.record-cancel {
  margin-left: 24rpx;
  font-size: 24rpx;
  color: #c25b4e;
}
.empty-panel {
  padding: 80rpx 32rpx;
  align-items: center;
  display: flex;
  flex-direction: column;
}
.empty-title {
  font-size: 30rpx;
  color: #756d66;
}
.empty-subtitle {
  margin-top: 12rpx;
  font-size: 24rpx;
  color: #a29a90;
}
```

- [ ] **Step 6: 验证 + 提交**

```powershell
cd D:\Project\YunxiBakeMiniApp
npx tsc --noEmit
git add miniprogram/utils/recharge-config.ts miniprogram/pages/recharge
git commit -m "feat(m5): 充值页（档位配置含 bonus 口子/自定义金额/mock 确认/记录列表）"
```

### Task 9: miniapp — 结算页扩展（券 + 积分 + 余额 + 4 分支支付）

**Files:**
- Modify: `miniprogram/pages/checkout/index.ts`
- Modify: `miniprogram/pages/checkout/index.wxml`
- Modify: `miniprogram/pages/checkout/index.wxss`

**Interfaces:**
- Consumes: `getMyCoupons`/`applyCoupon`、`getPoints`/`applyPoints`、`getBalance`、`payWithBalance`/`prepareCombinedPayment`/`prepareOrderPayment`（orders.ts）、`executePreparedPayment`（order-payment.ts）、`buildPaymentBranch`/`classifyCouponStatus`/`MemberCoupon`/`PaymentBranch`、`ONLINE_PAYMENT_READY`/`IS_LOCAL_BACKEND`
- Produces: 结算页优惠区 + 余额抵扣开关 + 确认弹窗 + 4 分支支付 + pending 订单复用/取消

- [ ] **Step 1: `index.ts` 数据与工具方法**

data 新增字段：

```ts
data: {
  // ...既有字段
  availableCoupons: [] as Array<MemberCoupon & { disabled: boolean }>,
  selectedCouponId: "",
  pointsEnabled: false,
  pointsBalance: 0,
  balanceEnabled: true,
  balanceFen: 0,
  goodsFen: 0,
  estimateCouponFen: 0,
  estimateRemainFen: 0,
  goodsFenText: "¥0.00",
  estimateCouponFenText: "-¥0.00",
  estimateRemainFenText: "¥0.00",
  balanceDeductText: "-¥0.00",
  pendingOrderId: "",
  pendingBarVisible: false,
  showCouponPanel: false,
  orderLocked: false
}
```

新增纯逻辑方法（放在 `validateOrderForm` 之前）：

```ts
buildCouponList(coupons: MemberCoupon[], goodsFen: number) {
  return coupons
    .filter((coupon) => classifyCouponStatus(coupon).tab === "available")
    .map((coupon) => ({
      ...coupon,
      disabled: coupon.thresholdFen > 0 && goodsFen < coupon.thresholdFen
    }));
},

savePendingOrder(orderId: string) {
  const signature = getCartItems()
    .map((item) => `${item.productId}:${item.quantity}`)
    .join(",");
  wx.setStorageSync("yunxiPendingOrder", {
    orderId,
    signature,
    couponId: this.data.selectedCouponId,
    pointsEnabled: this.data.pointsEnabled
  });
},

readPendingOrder(): { orderId: string; signature: string; couponId: string; pointsEnabled: boolean } | null {
  return wx.getStorageSync("yunxiPendingOrder") || null;
},

clearPendingOrder() {
  wx.removeStorageSync("yunxiPendingOrder");
}
```

`loadCheckout` 末尾追加资产与 pending 加载：

```ts
// 资产区数据（余额/积分/可用券）用于展示与抵扣估算
const [balance, points, couponsData] = await Promise.all([
  getBalance().catch(() => null),
  getPoints().catch(() => null),
  getMyCoupons().catch(() => null)
]);
const goodsFen = getCartItems().reduce((sum, item) => sum + item.priceFen * item.quantity, 0);
const availableCoupons = couponsData
  ? this.buildCouponList(couponsData.coupons || [], goodsFen)
  : [];
const pending = this.readPendingOrder();
const pendingBarVisible =
  Boolean(pending) &&
  pending.signature === getCartItems().map((item) => `${item.productId}:${item.quantity}`).join(",");
this.setData({
  goodsFen,
  balanceFen: balance ? balance.balanceFen : 0,
  pointsBalance: points ? points.pointsBalance : 0,
  availableCoupons,
  pendingOrderId: pending ? pending.orderId : "",
  pendingBarVisible,
  selectedCouponId: pending ? pending.couponId : "",
  pointsEnabled: pending ? pending.pointsEnabled : false
});
this.refreshEstimate();
```

`refreshEstimate`（估算金额区，最终以提交后确认为准）：

```ts
refreshEstimate() {
  const goodsFen = this.data.goodsFen;
  const selected = this.data.availableCoupons.find(
    (coupon) => coupon.couponId === this.data.selectedCouponId
  );
  const couponFen = selected && !selected.disabled ? selected.valueFen : 0;
  const balanceFen = this.data.balanceEnabled ? this.data.balanceFen : 0;
  const remainFen = Math.max(0, goodsFen - couponFen - balanceFen);
  this.setData({
    estimateCouponFen: couponFen,
    estimateRemainFen: remainFen,
    goodsFenText: formatFen(goodsFen),
    estimateCouponFenText: `-${formatFen(couponFen)}`,
    estimateRemainFenText: formatFen(remainFen),
    balanceDeductText: `-${formatFen(Math.min(balanceFen, goodsFen))}`
  });
}
```

data 需补 `estimateRemainFen: 0`。优惠区事件方法：

```ts
toggleCouponPanel() {
  this.setData({ showCouponPanel: !this.data.showCouponPanel });
},
selectCoupon(event: WechatMiniprogram.TouchEvent) {
  const couponId = event.currentTarget.dataset.id as string;
  const coupon = this.data.availableCoupons.find((item) => item.couponId === couponId);
  if (coupon && coupon.disabled) {
    return;
  }
  // 订单已生成（快照已写）：已应用券不可退选（后端无撤销端点），允许换选（apply 覆盖写）
  if (this.data.orderLocked && this.data.selectedCouponId === couponId) {
    wx.showToast({ title: "已应用优惠券，如需取消请取消订单", icon: "none" });
    return;
  }
  this.setData({
    selectedCouponId: this.data.selectedCouponId === couponId ? "" : couponId,
    showCouponPanel: false
  });
  this.refreshEstimate();
},
onPointsSwitch(event: WechatMiniprogram.SwitchChange) {
  if (this.data.orderLocked) {
    this.setData({ pointsEnabled: true });
    wx.showToast({ title: "积分已应用，如需取消请取消订单", icon: "none" });
    return;
  }
  this.setData({ pointsEnabled: Boolean(event.detail.value) });
  this.refreshEstimate();
},
togglePointsRow() {
  if (this.data.orderLocked) {
    wx.showToast({ title: "积分已应用，如需取消请取消订单", icon: "none" });
    return;
  }
  this.setData({ pointsEnabled: !this.data.pointsEnabled });
  this.refreshEstimate();
},
onBalanceSwitch(event: WechatMiniprogram.SwitchChange) {
  this.setData({ balanceEnabled: Boolean(event.detail.value) });
  this.refreshEstimate();
},
toggleBalanceRow() {
  this.setData({ balanceEnabled: !this.data.balanceEnabled });
  this.refreshEstimate();
}
```

- [ ] **Step 2: 重写 `submitOrder` 为 4 分支流程**

```ts
async submitOrder() {
  if (this.data.submitting) {
    return;
  }
  if (!isMiniappLoggedIn(getMiniappSession())) {
    this.showValidationError("请先登录后提交订单");
    return;
  }
  const cartItems = getCartItems();
  if (!cartItems.length) {
    this.showValidationError("购物车为空，请先选择商品");
    return;
  }
  if (!this.validateOrderForm()) {
    return;
  }
  this.setData({ errorMessage: "", submitting: true });
  try {
    const cartStillValid = await this.validateCartProducts(cartItems);
    if (!cartStillValid) {
      return;
    }
    let orderId = this.data.pendingOrderId;
    if (!orderId) {
      const order = await createOrder({
        items: cartItems.map((item) => ({
          productId: item.productId,
          quantity: item.quantity,
          title: item.title,
          priceFen: item.priceFen
        })),
        receiverName: this.data.receiverName,
        receiverPhone: this.data.receiverPhone,
        deliveryType: this.data.deliveryType,
        deliveryAddress: getOrderDeliveryAddress(this.data.deliveryType, this.data.deliveryAddress),
        expectTime: this.data.expectTime,
        remark: buildOrderRemark(this.data.deliveryType, this.data.remark, this.data.deliveryAddress)
      });
      orderId = order.orderId;
      this.savePendingOrder(orderId);
      this.setData({ pendingOrderId: orderId, orderLocked: true });
    }
    // 按序 apply（弹窗确认前不改订单金额展示，只写后端快照）
    let couponFen = 0;
    if (this.data.selectedCouponId) {
      const applied = await applyCoupon(orderId, this.data.selectedCouponId);
      couponFen = applied.couponFen || 0;
    }
    let pointsFen = 0;
    if (this.data.pointsEnabled) {
      const applied = await applyPoints(orderId);
      pointsFen = applied.pointsFen || 0;
    }
    const totalFen = this.data.goodsFen;
    const remainFen = Math.max(0, totalFen - couponFen - pointsFen);
    const balance = await getBalance();
    const branch = buildPaymentBranch({
      remainFen,
      balanceFen: this.data.balanceEnabled ? balance.balanceFen : 0,
      balanceEnabled: this.data.balanceEnabled
    });
    await this.confirmAndPay(orderId, { totalFen, couponFen, pointsFen, remainFen, branch, balanceFen: balance.balanceFen });
  } catch (error) {
    const message = getErrorMessage(error, "提交失败，请稍后重试");
    this.setData({ errorMessage: message });
    wx.showToast({ title: message, icon: "none" });
  } finally {
    this.setData({ submitting: false });
  }
},

async confirmAndPay(
  orderId: string,
  summary: {
    totalFen: number;
    couponFen: number;
    pointsFen: number;
    remainFen: number;
    branch: PaymentBranch;
    balanceFen: number;
  }
): Promise<void> {
  const { totalFen, couponFen, pointsFen, remainFen, branch, balanceFen } = summary;
  let content = "";
  if (branch === "free") {
    content = "本单已由优惠全额抵扣，无需支付";
  } else if (branch === "balance") {
    content = `实付 ${formatFen(remainFen)}（余额支付）`;
  } else if (branch === "combined") {
    const onlineFen = Math.max(0, remainFen - balanceFen);
    content = `剩余应付 ${formatFen(remainFen)}\n余额抵扣 ${formatFen(balanceFen)}\n在线支付 ${formatFen(onlineFen)}`;
  } else {
    content = `实付 ${formatFen(remainFen)}（在线支付）`;
  }
  if (couponFen > 0) {
    content += `\n优惠券 -${formatFen(couponFen)}`;
  }
  if (pointsFen > 0) {
    content += `\n积分 -${formatFen(pointsFen)}`;
  }
  const confirmed = await new Promise<boolean>((resolve) => {
    wx.showModal({
      title: "确认支付",
      content,
      confirmText: branch === "free" ? "确认完成" : "确认支付",
      cancelText: "稍后支付",
      success: (res) => resolve(Boolean(res.confirm)),
      fail: () => resolve(false)
    });
  });
  if (!confirmed) {
    wx.showToast({ title: "订单已保留，可继续支付或取消订单", icon: "none" });
    return;
  }
  if (branch === "free") {
    await payWithBalance(orderId);
  } else if (branch === "balance") {
    await payWithBalance(orderId);
  } else if (branch === "combined") {
    if (!ONLINE_PAYMENT_READY) {
      wx.showToast({ title: "在线支付即将上线，请到店支付或联系客服", icon: "none" });
      return;
    }
    const payment = await prepareCombinedPayment(orderId, balanceFen);
    await executePreparedPayment(payment);
  } else {
    if (!ONLINE_PAYMENT_READY) {
      wx.showToast({ title: "在线支付即将上线，请到店支付或联系客服", icon: "none" });
      return;
    }
    const payment = await prepareOrderPayment(orderId);
    await executePreparedPayment(payment);
  }
  this.clearPendingOrder();
  clearCartItems();
  wx.showToast({ title: "支付成功", icon: "success" });
  wx.redirectTo({ url: `${ROUTES.orderDetail}?id=${orderId}` });
}
```

新增 pending 条操作：

```ts
async resumePendingOrder() {
  const pending = this.readPendingOrder();
  if (!pending) {
    return;
  }
  this.setData({
    pendingOrderId: pending.orderId,
    selectedCouponId: pending.couponId,
    pointsEnabled: pending.pointsEnabled,
    pendingBarVisible: false,
    orderLocked: true
  });
  wx.showToast({ title: "已恢复待支付订单，积分与已选券已锁定，请确认支付", icon: "none" });
},
async cancelPendingOrder() {
  const pending = this.readPendingOrder();
  if (!pending) {
    return;
  }
  try {
    await cancelOrder(pending.orderId);
    this.clearPendingOrder();
    this.setData({ pendingOrderId: "", pendingBarVisible: false, orderLocked: false });
    wx.showToast({ title: "订单已取消", icon: "success" });
  } catch (error) {
    wx.showToast({ title: getErrorMessage(error, "取消失败"), icon: "none" });
  }
}
```

- [ ] **Step 3: `index.wxml` 优惠区与金额区**

在表单（`agree`/提交按钮）之前插入优惠区：

```xml
<view class="benefit-panel glass-panel">
  <view class="benefit-row" bindtap="toggleCouponPanel">
    <text class="benefit-label">优惠券</text>
    <text class="benefit-value">
      {{selectedCouponId ? '已选 1 张' : (availableCoupons.length ? availableCoupons.length + ' 张可用' : '暂无可用')}}
    </text>
    <text class="benefit-arrow">{{showCouponPanel ? '▲' : '▼'}}</text>
  </view>
  <view wx:if="{{showCouponPanel}}" class="coupon-panel">
    <view
      wx:for="{{availableCoupons}}"
      wx:key="couponId"
      class="coupon-option {{item.disabled ? 'disabled' : ''}} {{selectedCouponId === item.couponId ? 'selected' : ''}}"
      data-id="{{item.couponId}}"
      bindtap="selectCoupon"
    >
      <text class="coupon-option-value">-{{item.valueFen / 100}}元</text>
      <text class="coupon-option-title">{{item.title}}（{{item.thresholdFen > 0 ? '满' + item.thresholdFen / 100 + '元可用' : '无门槛'}}）</text>
      <text wx:if="{{orderLocked && selectedCouponId === item.couponId}}" class="coupon-applied">已应用</text>
    </view>
    <view wx:if="{{availableCoupons.length === 0}}" class="coupon-empty">暂无可用优惠券</view>
  </view>
  <view class="benefit-row" bindtap="togglePointsRow">
    <text class="benefit-label">积分抵扣</text>
    <switch checked="{{pointsEnabled}}" disabled="{{orderLocked}}" color="#6c9a63" bindchange="onPointsSwitch" />
    <text class="benefit-value">{{orderLocked ? '积分已应用' : '可用 ' + pointsBalance + ' 积分'}}</text>
  </view>
  <text wx:if="{{orderLocked}}" class="benefit-note">积分已应用，取消请先取消订单</text>
  <view class="benefit-row" bindtap="toggleBalanceRow">
    <text class="benefit-label">余额抵扣</text>
    <switch checked="{{balanceEnabled}}" color="#6c9a63" bindchange="onBalanceSwitch" />
    <text class="benefit-value">可用 {{balanceFen / 100}} 元</text>
  </view>
</view>

<view class="amount-panel glass-panel">
  <view class="amount-row"><text>商品金额</text><text>{{goodsFenText}}</text></view>
  <view class="amount-row"><text>优惠券</text><text>{{estimateCouponFenText}}</text></view>
  <view class="amount-row"><text>积分抵扣</text><text>{{pointsEnabled ? '提交后计算' : '-'}}</text></view>
  <view class="amount-row"><text>余额抵扣</text><text>{{balanceEnabled ? balanceDeductText : '-'}}</text></view>
  <view class="amount-row amount-total"><text>实付（估算）</text><text>{{estimateRemainFenText}}</text></view>
  <text class="amount-note">最终金额以支付确认页为准</text>
</view>

<view wx:if="{{pendingBarVisible}}" class="pending-bar">
  <text>您有一笔待支付订单</text>
  <view class="pending-actions">
    <text class="pending-action" bindtap="resumePendingOrder">继续支付</text>
    <text class="pending-action danger" bindtap="cancelPendingOrder">取消订单</text>
  </view>
</view>
```

- [ ] **Step 4: `index.wxss` 追加**

```css
.benefit-panel,
.amount-panel {
  margin-top: 24rpx;
  padding: 8rpx 24rpx;
}
.benefit-row {
  display: flex;
  align-items: center;
  padding: 24rpx 0;
  border-bottom: 1rpx solid #f0ece6;
  gap: 16rpx;
}
.benefit-label {
  font-size: 28rpx;
  color: #2d2a26;
}
.benefit-value {
  flex: 1;
  text-align: right;
  font-size: 26rpx;
  color: #756d66;
}
.benefit-arrow {
  font-size: 22rpx;
  color: #a29a90;
}
.coupon-panel {
  padding: 8rpx 0 16rpx;
}
.coupon-option {
  display: flex;
  align-items: center;
  gap: 16rpx;
  padding: 18rpx 12rpx;
  border-radius: 12rpx;
  border: 2rpx solid #efeae4;
  margin-top: 12rpx;
}
.coupon-option.selected {
  border-color: #6c9a63;
  background: #f0f7ee;
}
.coupon-option.disabled {
  opacity: 0.45;
}
.coupon-option-value {
  font-size: 30rpx;
  font-weight: 700;
  color: #c25b4e;
}
.coupon-applied {
  margin-left: auto;
  font-size: 22rpx;
  color: #6c9a63;
}
.benefit-note {
  display: block;
  padding: 8rpx 0 16rpx;
  font-size: 22rpx;
  color: #a29a90;
}
.coupon-option-title {
  font-size: 24rpx;
  color: #756d66;
}
.coupon-empty {
  padding: 20rpx 0;
  font-size: 24rpx;
  color: #a29a90;
}
.amount-row {
  display: flex;
  justify-content: space-between;
  padding: 16rpx 0;
  font-size: 26rpx;
  color: #756d66;
}
.amount-row.amount-total {
  font-size: 30rpx;
  font-weight: 700;
  color: #2d2a26;
  border-top: 1rpx solid #f0ece6;
  margin-top: 8rpx;
}
.amount-note {
  display: block;
  padding-bottom: 16rpx;
  font-size: 22rpx;
  color: #a29a90;
}
.pending-bar {
  margin-top: 24rpx;
  padding: 20rpx 24rpx;
  border-radius: 12rpx;
  background: #fdf3e3;
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 26rpx;
  color: #8a5a1e;
}
.pending-actions {
  display: flex;
  gap: 24rpx;
}
.pending-action {
  color: #6c9a63;
  font-weight: 600;
}
.pending-action.danger {
  color: #c25b4e;
}
```

说明：WXML 不支持函数调用，金额区已全部使用 `refreshEstimate` 预计算文本字段（`goodsFenText/estimateCouponFenText/balanceDeductText/estimateRemainFenText`），`selectCoupon`/`togglePointsRow`/`toggleBalanceRow`/`onPointsSwitch`/`onBalanceSwitch` 中均需调用 `this.refreshEstimate()` 同步刷新。

- [ ] **Step 5: 验证 + 提交**

```powershell
cd D:\Project\YunxiBakeMiniApp
npx tsc --noEmit
node --test tests/utils/member-assets.test.ts
git add miniprogram/pages/checkout/index.ts miniprogram/pages/checkout/index.wxml miniprogram/pages/checkout/index.wxss
git commit -m "feat(m5): 结算页优惠与余额抵扣扩展（券/积分/余额 + 4 分支支付 + pending 订单）"
```

### Task 10: 发布验收清单 + 双仓收口

**Files:**
- Modify: `docs/release/manual-acceptance-checklist.md`（miniapp 仓）
- Modify: `LOGBOOK.md`、`docs/harness-engineering/core/evidence-index.md`（miniapp 仓，Phase 2 收口）
- Modify: `LOGBOOK.md`（YunxiBakeBot 仓，Task 1 收口条目）
- Modify: `项目进度与配置清单.md`（YunxiBakeBot 仓，M5 进度）

**Interfaces:**
- Consumes: Phase 1 + Phase 2 全部交付
- Produces: 双仓收口闭环

- [ ] **Step 1: 更新发布验收清单（miniapp）**

`docs/release/manual-acceptance-checklist.md` 追加 M5 条目：

```markdown
### M5 会员资产前端（2026-08-14）

- [ ] 展示类（任意环境）：我的页余额/积分/可用券与后端一致；积分明细列表与来源文案正确；券中心四个 tab 分组正确。
- [ ] 交易类（必须 IS_USING_LOCAL_API=1 连本地后端）：充值建单→确认→mock 到账→余额刷新；结算页选券/开积分/余额抵扣→提交→确认弹窗金额与后端一致→支付成功跳订单详情。
- [ ] release 过渡：充值入口隐藏；结算差额按钮提示「在线支付即将上线」；余额支付可用。
- [ ] 真实微信支付（商户号到位后）：翻开关 `payment-gate.ts`，差额/充值走真实 JSAPI 验收。
```

- [ ] **Step 2: Phase 2 收口（miniapp LOGBOOK + evidence-index）**

```markdown
## 2026-08-14 - M5 Phase 2：交易类页面交付（充值页/结算页扩展）

- trace_id: 20260814-member-loyalty-m5
- 变更: 充值页（档位配置 + mock 确认 + 记录）；结算页优惠与余额抵扣扩展（券/积分/余额 + 4 分支支付 + pending 订单复用/取消）。
- 验证: `tsc --noEmit` 0 error；node:test 11 pass；本地后端（mock）devtools 联调充值/结算全流程；release 过渡行为人工核验。
- 待办: 商户号到位后接真实微信支付（翻开关清单）；M5 真机验收。
```

- [ ] **Step 3: Platform 仓收口（Task 1 对应 LOGBOOK + 进度清单）**

`D:\Project\YunxiBakeBot\LOGBOOK.md` 顶部追加（trace_id `20260814-member-loyalty-m5`）：

```markdown
## [2026-08-14] - feat(coupon): get_my_coupons 补 thresholdFen（M5 跨仓小任务）

- 操作人: AI (Codex)
- trace_id: 20260814-member-loyalty-m5
- 变更: CouponTemplateRepo 新增 list_by_ids 批量查询；get_my_coupons 输出 thresholdFen（模板缺失 fallback 0），供小程序券中心展示门槛。
- 验证: tests/api/test_miniapp_coupons_api.py 4 passed；ruff check 通过。
- 版本: 0.132.0（feat → minor 递增）
```

同步更新 `项目进度与配置清单.md`：M5 状态「小程序前端（我的页/积分明细/券中心/充值页/结算扩展）已交付，双仓闭环」。

- [ ] **Step 4: 双仓推送 + 最终核验**

```powershell
cd D:\Project\YunxiBakeMiniApp
npm run check:miniapp
npm run check:page-api-coverage
npx tsc --noEmit
node --test tests/utils/member-assets.test.ts
git push origin HEAD
```

```powershell
cd D:\Project\YunxiBakeBot
PYTHONUTF8=1 python -m pytest tests/api/test_miniapp_coupons_api.py -q --no-cov --basetemp=D:\Temp\m5_t1
ruff check app/service/coupon/__init__.py app/repository/coupon_template_repo.py tests/api/test_miniapp_coupons_api.py
git push origin master
git push server master
```

Expected: 所有检查 pass；双仓远端同步。
