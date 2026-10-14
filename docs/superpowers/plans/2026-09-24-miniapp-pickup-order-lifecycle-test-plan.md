# MiniApp 自提订单核心闭环测试优先 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不改业务实现的前提下，新增后端自提订单完整 API 集成测试和本地 DevTools 页面生命周期测试，确认商品到支付、订单详情、取消和本地存储清理是否真实闭环。

**Architecture:** 后端测试直接通过现有 FastAPI 小程序订单路由和测试数据库验证 API 合约；MiniApp 测试通过 `miniprogram-automator` 连接本地 DevTools，使用真实本地会话和商品调用页面自身方法。前端测试只注入确定性弹窗结果，不替换业务服务层；环境预检失败写 `blocked`，业务断言失败写 `fail`。

**Tech Stack:** Python 3.13、pytest、httpx ASGITransport、aiosqlite、Node.js、miniprogram-automator、微信开发者工具、本地 FastAPI `127.0.0.1:7001`。

## Global Constraints

- 只使用本地后端、测试数据库和合成联系人/商品，不访问生产 API、真实客户数据或真实微信支付。
- 本轮先新增测试；只有测试复现当前业务代码的 P0/P1 行为错误后，才允许修改业务代码。
- 北京闪送、真实微信支付、真机、生产验收不属于本轮实现范围。
- 现有未提交的 `backend/app/repository/knowledge_product_repo.py` 改动保持原样，不纳入本轮测试提交。
- 测试报告写入既有证据目录，失败和环境阻塞必须分别记录。
- 新增或修改 Python 测试时只使用中文注释/文档字符串，遵守参数化 SQL、架构分层和 `X | None` 类型规则。

## 文件边界

- Modify: `backend/tests/api/test_miniapp_order_api.py`，新增一条完整自提订单 API 集成测试。
- Create: `miniapp/scripts/check-devtools-pickup-order-lifecycle.mjs`，新增本地 DevTools 生命周期验证脚本。
- Modify: `miniapp/package.json`，注册 `devtools:pickup-order-lifecycle` 命令。
- Modify: `PROJECT-STATE.md`，更新本任务证据、下一步和当前状态事实。
- Modify: `LOGBOOK.md`，追加本轮测试优先复核条目。
- Modify: `docs/harness-engineering/core/evidence-index.md`，登记命令或报告证据。

---

### Task 1: 新增后端自提订单完整 API 集成测试

**Files:**
- Modify: `backend/tests/api/test_miniapp_order_api.py`，在现有支付与详情测试之后新增 `test_miniapp_pickup_order_lifecycle_creates_prepares_mock_pays_and_reads_detail`
- Test: `backend/tests/api/test_miniapp_order_api.py`

**Interfaces:**
- Consumes: `seed_miniapp_product(db, item_id=82010, title=..., price_fen=19800, stock=2)`、现有 `storefront_auth_headers(user_id)`、现有小程序订单路由。
- Produces: 一条可独立运行的 API 测试，验证创建自提订单、支付准备回退、mock 支付和详情读取的连续结果。

- [ ] **Step 1: 写入失败前的集成测试**

在 `backend/tests/api/test_miniapp_order_api.py` 中加入以下测试。测试使用两个库存单位，避免成功支付后无法继续读取详情；所有时间、联系人和地址均为合成值：

```python
@pytest.mark.asyncio
async def test_miniapp_pickup_order_lifecycle_creates_prepares_mock_pays_and_reads_detail(
    db: aiosqlite.Connection,
    app: FastAPI,
) -> None:
    """自提订单应完成创建、mock 支付准备、支付和详情读取闭环。"""
    await seed_miniapp_product(
        db,
        item_id=82010,
        title="API 自提闭环蛋糕",
        price_fen=19800,
        stock=2,
    )
    headers = storefront_auth_headers("pickup-lifecycle-api-user")
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        create_response = await client.post(
            "/api/v1/miniapp/orders",
            json={
                "items": [
                    {
                        "productId": "82010",
                        "title": "API 自提闭环蛋糕",
                        "priceFen": 1,
                        "quantity": 1,
                    }
                ],
                "receiverName": "自提闭环测试",
                "receiverPhone": "18800000020",
                "deliveryType": "pickup",
                "fulfillmentMethod": "pickup",
                "pickupAddress": "北京市东城区南竹杆胡同2号银河SOHO",
                "expectTime": "2026-06-18 18:00",
            },
            headers=headers,
        )
        assert create_response.status_code == 200
        created = create_response.json()["data"]
        order_id = created["orderId"]
        assert created["status"] == "pending"
        assert created["totalFen"] == 19800

        prepare_response = await client.post(
            f"/api/v1/miniapp/orders/{order_id}/prepare-payment",
            headers=headers,
        )
        assert prepare_response.status_code == 200
        prepared = prepare_response.json()["data"]
        assert prepared["mode"] == "mock"
        assert prepared["paymentMethod"] == "mock"
        assert prepared["paymentStatus"] == "unpaid"
        assert prepared["paymentParams"]["action"] == "mock-pay"

        pay_response = await client.post(
            f"/api/v1/miniapp/orders/{order_id}/mock-pay",
            headers=headers,
        )
        assert pay_response.status_code == 200
        paid = pay_response.json()["data"]
        assert paid["paymentStatus"] == "paid"
        assert paid["paymentMethod"] == "mock"

        detail_response = await client.get(
            f"/api/v1/miniapp/orders/{order_id}",
            headers=headers,
        )

    assert detail_response.status_code == 200
    detail = detail_response.json()["data"]
    assert detail["id"] == order_id
    assert detail["status"] == "pending"
    assert detail["paymentStatus"] == "paid"
    assert detail["paymentMethod"] == "mock"
    assert detail["deliveryType"] == "pickup"
    assert detail["pickupAddress"] == "北京市东城区南竹杆胡同2号银河SOHO"
    assert detail["items"][0]["product_id"] == "82010"
    assert detail["timeline"]
    assert detail["timeline"][0]["status"] == "pending"
```

- [ ] **Step 2: 运行新增测试，确认它能独立执行**

Run:

```powershell
python -m pytest --no-cov tests/api/test_miniapp_order_api.py::test_miniapp_pickup_order_lifecycle_creates_prepares_mock_pays_and_reads_detail -q
```

Expected: `1 passed`。如果失败，先保留完整 traceback，判断是测试假设不符合当前 API 契约，还是现有业务实现确实无法完成闭环；不得先改生产代码掩盖失败。

- [ ] **Step 3: 运行相邻订单 API 定向测试**

Run:

```powershell
python -m pytest --no-cov tests/api/test_miniapp_order_api.py -q
```

Expected: 现有订单 API 测试和新增生命周期测试全部通过。

- [ ] **Step 4: 复核后端是否需要业务修改**

只有新增测试或相邻测试失败，且 traceback 指向当前 API 业务实现时，才在 `backend/app/api/channels/storefront/orders.py`、`backend/app/service/order/` 或对应 repository 中做最小修复。修复后先重跑本测试，再运行相邻 API 测试。没有失败证据时保持业务代码不变。

---

### Task 2: 新增 MiniApp 本地 DevTools 生命周期测试

**Files:**
- Create: `miniapp/scripts/check-devtools-pickup-order-lifecycle.mjs`
- Modify: `miniapp/package.json`，在 `devtools:service-smoke` 附近新增脚本
- Test: `miniapp/scripts/check-devtools-pickup-order-lifecycle.mjs`

**Interfaces:**
- Consumes: `miniprogram-automator.connect({ wsEndpoint })`、`miniProgram.evaluate()`、现有 `pages/cart/index`、`pages/checkout/index`、`pages/order-detail/index` 页面方法、`wx.login`、本地 `/api/v1/miniapp/auth/login`、本地商品接口。
- Produces: `reports/button-runtime/pickup-order-lifecycle-<timestamp>.json` 和 `pickup-order-lifecycle-latest.json`，状态为 `pass`、`fail` 或 `blocked`。

- [ ] **Step 1: 写入 DevTools 测试脚本的预检和报告骨架**

脚本必须：

1. 从 `MINIAPP_AUTOMATOR_WS` 读取 DevTools WebSocket 地址，默认 `ws://127.0.0.1:9420`。
2. 将 API 地址固定为 `http://127.0.0.1:7001`，不读取线上默认地址。
3. 在连接 DevTools 前用 Node `http` 请求 `/health`；连接失败、HTTP 非 2xx、商品不足或登录失败时写 `blocked` 并以退出码 2 结束。
4. 恢复测试前的 `cartItems`、`miniappSession`、`miniappUserId`、`yunxiPendingOrder` 和 `yunxiUseLocalApi` 存储值；恢复逻辑放在 `finally`。

报告结构固定为：

```javascript
const report = {
  traceId: "20260924-miniapp-pickup-order-lifecycle",
  generatedAt: new Date().toISOString(),
  apiBaseUrl: LOCAL_API_BASE_URL,
  wsEndpoint,
  status: "blocked",
  checks: [],
  errors: [],
  result: {},
  notes: [
    "只使用本地后端、合成联系人和本地 DevTools 存储。",
    "不读取生产订单，不执行真实微信支付。",
  ],
};
```

- [ ] **Step 2: 在 DevTools evaluate 中建立真实本地测试会话和商品选择**

在 `miniProgram.evaluate(async function(apiBaseUrl) { ... }, LOCAL_API_BASE_URL)` 内实现：

```javascript
function loginWithWechat() {
  return new Promise(function(resolve, reject) {
    wx.login({
      success(loginResult) {
        if (!loginResult.code) {
          reject(new Error("wx.login 未返回 code"));
          return;
        }
        wx.request({
          url: apiBaseUrl + "/api/v1/miniapp/auth/login",
          method: "POST",
          data: { code: loginResult.code },
          timeout: 10000,
          header: { "content-type": "application/json" },
          success(response) {
            const body = response.data && typeof response.data === "object" ? response.data : {};
            const payload = body.data && typeof body.data === "object" ? body.data : body;
            if (response.statusCode < 200 || response.statusCode >= 300 ||
                typeof payload.accessToken !== "string" || !payload.accessToken ||
                payload.tokenType !== "Bearer") {
              reject(new Error("本地登录接口未返回有效 Bearer 会话"));
              return;
            }
            resolve({
              userId: String(payload.userId || ""),
              openid: String(payload.openid || ""),
              accessToken: payload.accessToken,
              tokenType: "Bearer",
              expiresIn: Number(payload.expiresIn || 0),
              expiresAt: Date.now() + Number(payload.expiresIn || 0) * 1000,
            });
          },
          fail(error) {
            reject(new Error(error.errMsg || "本地登录请求失败"));
          },
        });
      },
      fail(error) {
        reject(new Error(error.errMsg || "wx.login 失败"));
      },
    });
  });
}
```

使用同一个会话请求 `/api/v1/miniapp/products?limit=100`，筛选：

```javascript
const product = products.find(function(item) {
  return item && item.id && item.isActive && item.isPurchasable !== false &&
    Number(item.stock) >= 2 && Number(item.priceFen) > 0;
});
```

找不到商品时抛出带“本地测试商品不足”说明的错误，由外层转换为 `blocked`。

- [ ] **Step 3: 覆盖支付成功路径**

在 evaluate 中：

1. 将选中的商品写入 `cartItems`，数量为 1。
2. `wx.switchTab({ url: "/pages/cart/index" })`，等待购物车页面加载完成。
3. 调用购物车页面 `checkout()`，等待结算页。
4. 读取结算页并通过 `page.setData()` 写入：

```javascript
{
  receiverName: "本地自提闭环",
  receiverPhone: "18800000021",
  deliveryType: "pickup",
  deliveryAddress: "",
  remark: "",
  agreementAccepted: true,
  expectTime: "2099-01-02 18:00",
  isLoggedIn: true,
}
```

5. 将 `wx.showModal` 临时替换为立即回调 `{ confirm: true }` 的确定性替身，调用页面 `submitOrder()`；调用结束后恢复原方法。
6. 等待路由变为 `pages/order-detail/index` 且 `loading=false`。
7. 读取详情数据并记录以下断言：

```javascript
detail.data.order.paymentStatus === "paid"
detail.data.order.paymentMethod === "mock"
detail.data.order.deliveryType === "pickup"
detail.data.order.pickupAddress === "北京市东城区南竹杆胡同2号银河SOHO"
detail.data.order.itemsView.length > 0
wx.getStorageSync("cartItems").length === 0
!wx.getStorageSync("yunxiPendingOrder")
```

若 `submitOrder()` 抛错、页面未跳转、支付状态不为 `paid` 或本地存储未清理，记录 `fail`，保留异常消息和阶段名。

- [ ] **Step 4: 覆盖取消路径**

在同一商品仍剩余至少 1 件库存的前提下：

1. 重新写入购物车并进入结算页。
2. 写入同样的自提表单，但将 `wx.showModal` 替身改为 `{ confirm: false }`。
3. 调用 `submitOrder()`，等待 `pendingOrderId` 非空且 `pendingBarVisible=true`。
4. 调用页面 `cancelPendingOrder()`。
5. 读取待支付存储，调用 `/api/v1/miniapp/orders/{orderId}` 或进入订单详情，断言：

```javascript
cancelledOrder.status === "cancelled"
cancelledOrder.paymentStatus === "unpaid"
!wx.getStorageSync("yunxiPendingOrder")
```

如果测试商品的库存已经被第一笔成功订单消耗到 0，则第二个阶段开始前将结果标为 `blocked`，不把库存前置条件误报为支付缺陷。

- [ ] **Step 5: 输出报告并恢复存储**

脚本成功时退出码 0，业务断言失败时退出码 1，环境阻塞时退出码 2。报告只保留订单 ID 的短显示、商品 ID、状态、断言结果和异常摘要，不保存 accessToken、openid、手机号全文或请求头。恢复存储后再断开 Automator。

- [ ] **Step 6: 注册 npm 命令**

在 `miniapp/package.json` 的 `devtools:service-smoke` 后加入：

```json
"devtools:pickup-order-lifecycle": "node scripts/check-devtools-pickup-order-lifecycle.mjs",
```

保持 JSON 逗号和脚本顺序有效。

- [ ] **Step 7: 运行静态门禁和脚本预检**

Run:

```powershell
npm run typecheck
npm run check:miniapp
npm run devtools:pickup-order-lifecycle
```

Expected: 前两项退出码 0；第三项在本地后端或 DevTools 未启动时退出码 2 并输出 `blocked`，在环境可用时输出完整生命周期报告。

---

### Task 3: 失败归因与治理收口

**Files:**
- Modify: `PROJECT-STATE.md`
- Modify: `LOGBOOK.md`
- Modify: `docs/harness-engineering/core/evidence-index.md`
- Conditional Modify: only the implementation file proven responsible by a failing test

**Interfaces:**
- Consumes: Task 1 的 pytest 退出码和报告、Task 2 的 JSON 报告及退出码、当前 `git status --short --branch`。
- Produces: 可回放的测试结论，明确区分 `pass`、`fail`、`blocked`，并把后续修复或未验证边界写入唯一状态入口。

- [ ] **Step 1: 归类测试结果**

使用以下固定分类：

- `pass`：测试完整执行且所有业务断言通过。
- `fail`：测试完整执行，但订单 API、页面跳转、支付状态、取消状态或本地存储断言失败。
- `blocked`：本地后端未启动、DevTools 未连接、无法登录、没有足够库存商品或测试环境文件锁。

`blocked` 不得写成 `pass`，`fail` 不得通过修改断言或跳过用例隐藏。

- [ ] **Step 2: 只有 `fail` 才定位业务代码**

沿真实调用链确认：页面字段 → `validateOrderForm()` → `validateCartProducts()` → `createOrder()` → `prepareOrderPayment()` → `executePreparedPayment()` → 订单详情读取。只有确认当前业务代码造成确定性 P0/P1 结果，才修改对应文件，并为该失败补最小回归断言。

- [ ] **Step 3: 更新项目状态和证据**

在 `PROJECT-STATE.md` 的 `T-MINIAPP-CORE-LOOP-TEST-01` 行记录测试命令、退出码、报告路径和下一步；在 `LOGBOOK.md` 追加一条包含 `task_id`、`trace_id`、`run_id`、结果、限制和未验证边界的条目；在 `docs/harness-engineering/core/evidence-index.md` 登记本轮命令或报告。不得删除既有证据或覆盖上一份 `*-latest.json` 以外的报告。

- [ ] **Step 4: 最终验证**

Run:

```powershell
python -B backend/scripts/check_project_development_register.py
git diff --check
git status --short --branch
```

Expected: 总表守卫退出码 0；差异无空白错误；工作区事实与 `PROJECT-STATE.md` 一致。提交前必须区分本轮测试文件、现有用户改动、证据文件和任何业务修复，不能把不同来源的改动混入同一提交。
