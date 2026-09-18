# 芸熙烘焙小程序商品优先型 UI/UX 与履约重构实施计划

> **执行状态回填（2026-09-12，run_id: `20260912-miniapp-category-noise-r26`）**：Task 1—Task 7 除两个闪送真实联调门禁外均已执行并留下证据；未勾选项仅为 Task 1 Step 3 与 Task 3 Step 5（未取得闪送开放平台资料与测试权限）。平台侧模型、mock 契约、订单金额快照、前端金额适配、商品优先页面、DevTools 走查与仓库门禁均已落地，证据见 `LOGBOOK.md` r26 条目与 `docs/harness-engineering/core/evidence-index.md` E-20260912-006；真实微信支付/退款、真实闪送报价-建单-回调、生产验收仍未执行；2026-09-12 第二轮视觉走查（run_id: 20260912-miniapp-card-semantics-and-button-visibility-r27，证据 E-20260912-007）修复商品卡可用性文案冲突、按钮被全局重置覆盖不可见与客服页未登录文案，DevTools 15/15 复跑通过。
>
> **全量测试口径**：首轮全量 738.33s/8 failed，收口复跑 745.7s/2 failed；余下 2 项已定位为隔离 Harness 未关闭 SQLite 连接（M-20260912-085）并完成覆盖插桩定向验证，但按测试节奏约束未二次全量复跑，不能写成全量 0 失败。
>
> **r56 视觉收口**：首页履约说明由“预/送/时”文字改为 booking/delivery/hours 线性图标；快捷入口 mock 回退改为 `iconKey`，线上兼容旧 `iconText` 但顾客端不再渲染文字图标；客服未登录空态由“客服”二字改为 support 图标。`check-miniapp.mjs` 新增图标表面一致性和 WXSS 脱敏占位符守卫，`verify-all-15-pages-devtools.cjs` 新增运行态断言；`devtools:verify-all-pages` PASS（15/15 页 + 8/8 未登录态），服务承诺图标 16×16px、客服空态图标 72×72px；核心成交、购买路径、电商状态和触控扫描均 PASS。首轮失败因补丁误写 `[image omitted]` 脱敏占位符，已修正并记录 M-20260914-025；闪送真实联调两项仍为外部阻塞。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不脱离芸熙烘焙单店真实业务的前提下，完成商品优先型 MiniApp 体验重构，并建立北京闪送支付前报价、订单金额快照和配送状态闭环。

**Architecture:** 小程序只负责收集履约输入、展示 Platform 返回的报价与状态、提交订单和展示配送进度。Platform 在现有 `api → service → repository → models` 分层中新增配送领域，通过 `DeliveryProvider` 适配闪送开放平台；有赞继续承担迁移期商品数据来源，但不参与新小程序订单的配送报价、支付或配送单创建。

**Tech Stack:** 微信原生小程序、TypeScript、Python、FastAPI、SQLite、现有 Platform 仓储与测试体系、微信开发者工具。

## Global Constraints

- 首发只实现北京闪送与门店自取；全国配送不进入首发。
- 闪送配送费必须在支付前确定，并与商品金额一并支付。
- 商品价格按自提价格制定，配送费单独计算并由客户承担。
- 小程序不得计算配送费、最终金额、配送范围或闪送签名。
- 有赞只作为迁移期商品/经营数据来源，不作为新订单配送中间层。
- 配送报价失败、过期、超范围或平台不可用时，不得按零元配送费支付。
- 闪送开放平台尚未申请；申请、文档、测试环境和商户能力验证是开发前置门禁。
- 不新增无事实来源的评价、销量、会员权益或配送承诺。
- 不修改其他 Agent 未授权的有效工作区改动；涉及 `PROJECT-STATE.md`、`LOGBOOK.md` 和证据索引时由任务 owner 统一收口。
- 截至 2027 年 5 月 31 日（含），小程序仅用于开发、调试和测试，不向真实用户开放。
- 代码注释使用中文，Python 类型使用 `X | None`，不使用 `Optional[X]` 或 `Union[X, Y]`。

---

## 文件与职责地图

### 需要创建

- `docs/tasks/20260908-miniapp-commerce-ux-redesign.md`：任务元数据、范围、状态和验证入口。
- `backend/app/models/delivery.py`：配送方式、报价、配送订单和状态模型。
- `backend/app/repository/delivery_quote_repo.py`：报价快照与状态持久化。
- `backend/app/repository/delivery_order_repo.py`：配送单与回调事件持久化。
- `backend/app/service/delivery/provider.py`：配送平台内部协议。
- `backend/app/service/delivery/shansong.py`：闪送开放平台适配器。
- `backend/app/service/delivery/application.py`：报价、绑定、创建和状态编排。
- `backend/app/api/channels/storefront/delivery.py`：小程序配送报价接口和回调入口。
- `backend/tests/service/delivery/test_application.py`：配送领域状态与幂等测试。
- `backend/tests/service/delivery/test_shansong.py`：闪送适配器契约测试。
- `backend/tests/api/test_miniapp_delivery_api.py`：报价 API 测试。
- `miniapp/miniprogram/services/delivery.ts`：小程序配送 API 客户端。
- `miniapp/miniprogram/utils/order-summary.ts`：金额明细与配送状态展示适配。
- `miniapp/tests/utils/order-summary.test.ts`：金额展示适配测试。

### 需要修改

- `backend/app/config.py`：增加闪送配置项和未启用默认值，密钥只从配置读取。
- `backend/app/migrations/schema.py`：增加配送报价、配送单和回调事件表。
- `backend/app/service/order/creation.py`：绑定报价、生成金额快照和创建待配送状态。
- `backend/app/service/order/serialization.py`：序列化金额拆分和配送快照。
- `backend/app/service/order/payment.py` 或实际支付编排模块：以 `payableFen` 校验支付金额。
- `backend/app/api/channels/storefront/orders.py`：接受新履约字段并保持旧值兼容。
- `backend/tests/api/test_miniapp_orders_api.py`：增加配送报价绑定和金额边界测试。
- `miniapp/miniprogram/services/orders.ts`：新增履约方式、报价 ID和金额字段。
- `miniapp/miniprogram/pages/home/`：精选商品优先、履约说明和条件化复购。
- `miniapp/miniprogram/pages/products/`：分类、状态和长尾商品展示。
- `miniapp/miniprogram/pages/product-detail/`：朋友圈直达所需的完整商品与履约信息。
- `miniapp/miniprogram/pages/checkout/`：自提/闪送切换、报价状态和金额拆分。
- `miniapp/miniprogram/pages/orders/`：订单金额和状态摘要。
- `miniapp/miniprogram/pages/order-detail/`：制作状态、闪送状态和金额快照。
- `miniapp/miniprogram/pages/address/`：地址选择与重新报价联动。
- `miniapp/miniprogram/app.wxss`、相关页面 WXSS 与共享组件：统一暖白、可可棕、现代电商信息层级。
- `miniapp/docs/api-contract.md`：先写新契约，再修改前端调用。
- `miniapp/docs/page-api-coverage.md`：登记新增配送报价依赖。
- `docs/harness-engineering/core/evidence-index.md`：登记接口、测试和 DevTools 证据。
- `PROJECT-STATE.md`、`LOGBOOK.md`：按 owner 记录任务状态和历史证据。

---

## Task 1: 建立任务登记和闪送申请门禁

**Files:**
- Create: `docs/tasks/20260908-miniapp-commerce-ux-redesign.md`
- Modify: `PROJECT-STATE.md`（由 owner 收口）
- Modify: `LOGBOOK.md`（由 owner 收口）
- Modify: `docs/harness-engineering/core/evidence-index.md`（获得接口资料后登记）

**Interfaces:**
- Produces: `trace_id=20260908-miniapp-commerce-ux-redesign`、首发范围和前置门禁记录。

- [x] **Step 1: 建立任务元数据**

写入 `docs/tasks/20260908-miniapp-commerce-ux-redesign.md`：

```markdown
---
trace_id: 20260908-miniapp-commerce-ux-redesign
parent_trace_id: 20260908-miniapp-display-polish
owner: AI 员工
status: active
status_label: 进行中（active）
as_of_commit: <执行开始时的 git rev-parse HEAD>
version: <执行开始时的 backend/VERSION>
allowed_paths: miniapp/, backend/app/api/channels/storefront/, backend/app/service/order/, backend/app/service/delivery/, backend/app/repository/, backend/app/models/, backend/app/migrations/, backend/tests/, docs/superpowers/, docs/tasks/
forbidden_paths: backend/data/, backend/reports/, .env*, 生产目录
---

目标：完成商品优先型小程序体验与北京闪送支付前报价闭环。
首发：北京闪送、门店自取。
非目标：全国配送不进入首发。
门禁：未取得闪送开放平台资料前，不实现真实平台字段猜测，不宣称报价完成。
```

- [x] **Step 2: 核对并记录工作区基线**

运行：

```powershell
git rev-parse HEAD
git status --short
Get-Content backend/VERSION
python -B backend/scripts/check_project_development_register.py
```

Expected: 记录当前提交、版本和 dirty 文件；开发总表检查通过，或将已存在的失败单独登记，不覆盖既有修改。

- [ ] **Step 3: 完成闪送平台申请信息收集**（阻塞（blocked）：未取得闪送开放平台资料与测试权限，禁止猜测真实平台字段）

由项目负责人取得并归档以下非敏感资料：开发者/商户开通状态、API 文档版本、测试环境、签名规则、回调规范、门店取货地址要求、报价输入字段、报价有效期、取消/退款规则和错误码。密钥只写入本地非版本控制配置，不写入文档或仓库。

- [x] **Step 4: 做前置 Go/No-Go 判断**

当资料齐全且具备测试权限时，记录 `GO` 并进入 Task 2；否则记录 `BLOCKED` 和缺少的具体资料，只完成不依赖平台资料的契约与 mock 设计，不伪造真实联调结果。

---

## Task 2: 固化 Platform 配送领域模型和数据库契约

**Files:**
- Create: `backend/app/models/delivery.py`
- Create: `backend/app/repository/delivery_quote_repo.py`
- Create: `backend/app/repository/delivery_order_repo.py`
- Modify: `backend/app/migrations/schema.py`
- Modify: `backend/app/config.py`
- Test: `backend/tests/service/delivery/test_application.py`

**Interfaces:**
- Produces: `FulfillmentMethod`、`DeliveryQuoteStatus`、`DeliveryOrderStatus`、`DeliveryQuote`、`DeliveryOrder`、报价和配送事件仓储接口。
- Consumes: Task 1 的平台字段映射和项目现有 `BaseRepository`、`ConfigRepo` 模式。

- [x] **Step 1: 写状态和金额契约测试**

测试必须覆盖：`pickup` 不产生配送费；`beijing_delivery` 的 `deliveryFeeFen=None` 不能支付；报价状态只能从 `quoting` 到 `quoted/failed/expired`；配送回调重复事件只处理一次。

示例断言：

```python
assert build_payable_fen(19800, 2600, 1000, 500, 200, 0) == 20700
assert can_pay_quote(DeliveryQuoteStatus.QUOTED, 2600) is True
assert can_pay_quote(DeliveryQuoteStatus.PENDING_CONFIRMATION, None) is False
```

- [x] **Step 2: 运行测试确认失败**

运行：

```powershell
pytest backend/tests/service/delivery/test_application.py -q
```

Expected: FAIL，原因是新模型和函数尚未实现。

- [x] **Step 3: 实现领域模型和 schema**

新增固定枚举和数据类，金额全部使用整数分。新增表至少保存：报价 ID、用户 ID、请求摘要哈希、履约方式、商品金额、配送费、报价总额、状态、过期时间；配送单保存供应商单号、状态、费用和地址快照；回调事件保存外部事件 ID、原始摘要哈希、处理状态和处理时间。不得保存密钥或无必要完整客户原文。

- [x] **Step 4: 实现仓储的参数化读写**

所有 SQL 明确列名并使用 `?` 绑定；增加报价按用户和报价 ID读取、过期更新、配送单按订单读取、事件按外部 ID幂等写入。不得在 service 直接访问 `aiosqlite`。

- [x] **Step 5: 运行定向测试**

运行：

```powershell
pytest backend/tests/service/delivery/test_application.py -q
python -B backend/scripts/check_project.py --skip-tests
```

Expected: 配送模型与仓储测试通过；项目红线扫描通过。

---

## Task 3: 实现闪送 Provider 和 Platform 报价接口

**Files:**
- Create: `backend/app/service/delivery/provider.py`
- Create: `backend/app/service/delivery/shansong.py`
- Create: `backend/app/service/delivery/application.py`
- Create: `backend/app/api/channels/storefront/delivery.py`
- Create: `backend/tests/service/delivery/test_shansong.py`
- Create: `backend/tests/api/test_miniapp_delivery_api.py`
- Modify: `backend/app/config.py`
- Modify: `backend/app/lifespan_services.py`、实际路由注册文件

**Interfaces:**
- Produces: `DeliveryProvider.quote(request) -> DeliveryQuote`、`create_order(request) -> DeliveryOrder`、`cancel_order(provider_order_id, reason) -> DeliveryOrder`；`POST /api/v1/miniapp/delivery/quotes`。
- Consumes: Task 1 的闪送字段映射和 Task 2 的模型、仓储。

- [x] **Step 1: 写 Provider mock 契约测试**

测试固定覆盖：成功报价、地址超范围、平台超时、签名失败、报价过期；平台返回金额以分保存；相同请求不把平台错误暴露为原始异常。

- [x] **Step 2: 运行测试确认失败**

运行：

```powershell
pytest backend/tests/service/delivery/test_shansong.py backend/tests/api/test_miniapp_delivery_api.py -q
```

Expected: FAIL，原因是 Provider、应用服务和路由尚未实现。

- [x] **Step 3: 实现 Provider 协议和 ShansongProvider**

Provider 只接收内部请求模型，不接收 FastAPI payload。签名、鉴权、超时、有限重试和错误映射集中在适配器内；日志只记录订单/报价内部 ID和错误分类，不记录密钥、完整地址或手机号。

- [x] **Step 4: 实现报价应用服务和路由**

路由负责鉴权、输入校验和统一响应；应用服务负责读取实时商品、校验库存、生成请求摘要、调用 Provider、保存报价和返回稳定状态。闪送未启用时返回 `provider_unavailable`，不返回假报价。

- [ ] **Step 5: 实现真实平台受控联调**（阻塞（blocked）：未取得闪送开放平台资料与测试权限，禁止猜测真实平台字段）

仅在 Task 1 取得测试权限后运行近距离、远距离、超范围、不可服务和过期场景。每个场景记录请求摘要、报价状态、费用结果、错误分类和可回放证据，禁止记录密钥和完整地址。

- [x] **Step 6: 运行定向门禁**

运行：

```powershell
pytest backend/tests/service/delivery backend/tests/api/test_miniapp_delivery_api.py -q
python -B backend/scripts/check_project.py --skip-tests
```

Expected: mock 契约、API 和红线检查通过；真实联调未具备条件时明确记录未验证范围。

---

## Task 4: 将报价和金额快照接入订单支付

**Files:**
- Modify: `backend/app/service/order/creation.py`
- Modify: `backend/app/service/order/serialization.py`
- Modify: `backend/app/service/order/payment.py` 或当前支付编排实现文件
- Modify: `backend/app/api/channels/storefront/orders.py`
- Modify: `miniapp/miniprogram/services/orders.ts`
- Test: `backend/tests/api/test_miniapp_orders_api.py`

**Interfaces:**
- Produces: 创建配送订单必须携带 `deliveryQuoteId`；订单响应提供 `goodsTotalFen`、`deliveryFeeFen`、各项抵扣和 `payableFen`。
- Consumes: Task 2 的报价快照和 Task 3 的报价接口。

- [x] **Step 1: 写订单金额和边界测试**

必须覆盖：自提配送费为 0；有效报价进入应付金额；报价过期拒绝；地址/商品/数量与报价不一致拒绝；配送费未确定拒绝支付；重复提交不重复创建报价或配送单。

- [x] **Step 2: 运行订单测试确认失败**

运行：

```powershell
pytest backend/tests/api/test_miniapp_orders_api.py -q
```

Expected: 新增场景 FAIL，现有订单回归保持基线状态。

- [x] **Step 3: 实现订单创建校验和金额快照**

服务端重新读取商品实时价格与库存，校验报价用户、地址、商品签名、数量和过期时间，生成不可变金额快照。旧 `delivery` 输入仅兼容映射到 `beijing_delivery`，新响应同时保留旧 `totalFen` 兼容字段和新明细字段。

- [x] **Step 4: 接入支付金额校验**

所有支付分支以订单持久化的 `payableFen` 为准，禁止以小程序提交的金额作为支付依据。配送报价失败、配送费为 `null` 或快照过期时，支付接口返回稳定业务错误。

- [x] **Step 5: 运行定向测试**

运行：

```powershell
pytest backend/tests/api/test_miniapp_orders_api.py backend/tests/service/order -q
python -B backend/scripts/check_project.py --skip-tests
```

Expected: 订单与支付定向测试通过，现有自提路径无回归。

---

## Task 5: 更新 MiniApp API 契约和配送客户端

**Files:**
- Create: `miniapp/miniprogram/services/delivery.ts`
- Create: `miniapp/miniprogram/utils/order-summary.ts`
- Create: `miniapp/tests/utils/order-summary.test.ts`
- Modify: `miniapp/miniprogram/services/orders.ts`
- Modify: `miniapp/docs/api-contract.md`
- Modify: `miniapp/docs/page-api-coverage.md`

**Interfaces:**
- Produces: `quoteDelivery(payload) -> DeliveryQuote`、`DeliveryQuoteStatus`、`OrderAmountSummary`、`DeliveryStatus`。
- Consumes: Task 3/4 的 Platform 稳定响应。

- [x] **Step 1: 先更新 API 契约文档**

补充报价请求/响应、订单金额明细、状态枚举、报价过期规则、错误码和全国配送首发不开放说明。文档必须明确小程序不本地计算配送费。

- [x] **Step 2: 写金额适配测试**

```typescript
expect(formatOrderAmountSummary({ goodsTotalFen: 19800, deliveryFeeFen: 2600, payableFen: 22400 })).toEqual({
  goodsText: "¥198.00",
  deliveryText: "¥26.00",
  payableText: "¥224.00"
});
```

同时测试 `deliveryFeeFen: null` 显示“待确认”而非“¥0.00”。

- [x] **Step 3: 运行前端测试确认失败**

运行：

```powershell
npm test --prefix miniapp -- --runInBand miniapp/tests/utils/order-summary.test.ts
```

Expected: 新测试 FAIL，适配器尚未实现；若项目测试脚本参数不同，以 `miniapp/package.json` 为准并记录实际命令。

- [x] **Step 4: 实现客户端和类型适配**

客户端只调用 Platform；请求地址变化、商品变化和预约时间变化由页面触发重新报价。所有金额展示通过整数分格式化函数，不在页面内直接除法拼接金额。

- [x] **Step 5: 运行前端门禁**

运行：

```powershell
npm run typecheck --prefix miniapp
npm run check:miniapp --prefix miniapp
npm test --prefix miniapp
```

Expected: TypeScript、MiniApp 静态检查和已有测试通过。

---

## Task 6: 重构商品优先型 MiniApp 页面

**Files:**
- Modify: `miniapp/miniprogram/pages/home/`
- Modify: `miniapp/miniprogram/pages/products/`
- Modify: `miniapp/miniprogram/pages/product-detail/`
- Modify: `miniapp/miniprogram/pages/checkout/`
- Modify: `miniapp/miniprogram/pages/orders/`
- Modify: `miniapp/miniprogram/pages/order-detail/`
- Modify: `miniapp/miniprogram/pages/address/`
- Modify: `miniapp/miniprogram/pages/profile/`
- Modify: `miniapp/miniprogram/app.wxss`
- Modify: 共享组件和对应 WXSS

**Interfaces:**
- Consumes: Task 5 的配送和订单客户端；现有商品、会员、地址、订单服务。
- Produces: 首页精选优先、长尾可查找、详情可直达、结算报价状态、订单金额与配送状态界面。

- [x] **Step 1: 建立页面状态测试/检查清单**

固定走查状态：未登录、登录、加载中、空精选、商品售罄、图片失败、地址未填、报价中、报价成功、报价过期、地址超范围、平台不可用、待支付、已支付、配送异常。

- [x] **Step 2: 重构首页和商品展示**

首页只在有真实数据时展示精选、分类和复购；商品卡统一图片比例、价格、状态和购买动作。长尾商品进入真实分类和搜索，不在首页全量展开。

- [x] **Step 3: 重构详情和朋友圈直达路径**

详情页独立展示商品图、价格、规格、状态、预订规则、履约方式和客服入口；不增加无数据评价、销量和配送承诺。

- [x] **Step 4: 重构结算履约和报价交互**

自提路径不请求报价；北京闪送路径在地址、商品或预约时间变化后重新报价。报价未成功时禁用支付/提交，报价成功后展示金额明细；报价过期提供重新报价；失败状态提供客服兜底。

- [x] **Step 5: 重构订单详情**

区分制作状态和闪送状态，展示不可变金额快照。自提订单隐藏闪送模块，配送异常显示明确客服动作。

- [x] **Step 6: 统一视觉与交互系统**

以暖白、可可棕、少量奶油金为基础，减少旧绿色、渐变、玻璃拟态和无信息装饰；统一按钮、标签、圆角、间距、阴影、骨架、空态、错误和触控尺寸。保持微信原生实现和现有无第三方 UI 约束。

- [x] **Step 7: 运行页面静态门禁**

运行：

```powershell
npm run typecheck --prefix miniapp
npm run check:miniapp --prefix miniapp
npm run audit:buttons --prefix miniapp
npm run audit:button-styles --prefix miniapp
```

Expected: 全部通过；发现未授权旧页面改动时先停下核对，不覆盖其他 Agent 代码。

---

## Task 7: 微信开发者工具走查与证据收口

**Files:**
- Modify: `miniapp/scripts/verify-all-15-pages-devtools.cjs`
- Create: `miniapp/scripts/verify-devtools-registration-policy.cjs`
- Modify: `miniapp/scripts/scan-miniapp-button-touch-targets.mjs`
- Create: `miniapp/scripts/verify-miniapp-commerce-flows.cjs`
- Modify: `miniapp/package.json`
- Modify: `docs/harness-engineering/core/evidence-index.md`
- Modify: `LOGBOOK.md`（由 owner 收口）
- Modify: `PROJECT-STATE.md`（由 owner 收口）

**Interfaces:**
- Consumes: Task 6 的页面和 Task 3/4 的接口；测试环境闪送 mock 或受控账号。
- Produces: 15 页面走查、交易链路和失败状态的可回放证据。

- [x] **Step 1: 扩展 DevTools 走查脚本**

覆盖：首页精选、商品列表、详情直达、购物车、自提结算、闪送报价成功、报价过期、地址超范围、订单详情和控制台 warning/error。脚本不得访问生产真实支付，不得写入真实客户数据。

补充（r32）：`verify-devtools-registration-policy.cjs` 覆盖群内登记页结构、未登录闸门、CTA 可达性、44px 触控目标、时间选择器联动、六步必填校验链、后端错误落页、提交成功态，以及隐私/协议/售后三个政策变体与默认回落；`scan-miniapp-button-touch-targets.mjs` 补充 cart / coupons-login-gate / points-login-gate 注入态，交互控件低于 44px 直接失败。

补充（r33）：`verify-all-15-pages-devtools.cjs` 增加控件交互态断言，充值自定义金额输入框必须达到 44px 且具备可见背景/边框与正确单位对齐；微信原生 `disabled` 按钮必须按实际计算颜色校验，充值、结算和客服发送禁用态文字对比度不得低于 4.5:1。

补充（r34）：受限页面未登录态统一为 `.yunxi-state yunxi-state--page` 整页引导空态（图标 + 标题 + 单行说明 + 去登录，44px 触控），`verify-all-15-pages-devtools.cjs` 新增 `inspectLoginGate()` 与结算页优惠券行断言，确定性未登录态扩到 8 页；结算页零可用券时不再保留下拉箭头、按下反馈与空面板，避免伪交互。

补充（r35）：订单展示按履约方式分叉，后端 `OrderSerializationService` 返回 `pickupAddress` 快照并同步 `OrderSummary` 契约与 API 文档；订单列表区分“到店自提 · 联系人 / 预约取货”与“北京闪送 · 收货人 / 期望配送”，订单详情自提单隐藏闪送费、展示自提门店与快照地址、仅配送单展示配送地址，进度节点按履约方式区分“待取货”与“配送中”。`verify-miniapp-commerce-flows.cjs` 增加配送/自提两种订单详情语义断言，`verify-devtools-commerce-states.cjs` 增加履约信息可读性与已登录空订单引导断言；`check-miniapp.mjs` 新增 `checkOrderFulfillmentPresentation()`（自提单禁渲染闪送费与配送地址）与 `checkTabBarLabels()`（`app.json` 与自定义 tabBar 文案逐项比对）。商品详情首图不再叠加销量角标，销量只在元信息保留一处。上架前仍需与客服确认真实发货时段与截单时间的对外文案口径。

- [x] **Step 2: 运行全页面定向走查**

运行：

```powershell
npm run devtools:verify-all-pages --prefix miniapp
npm run devtools:verify-commerce-flows --prefix miniapp
```

Expected: 页面和流程结果分别记录 PASS/FAIL、失败分类、截图/日志路径和未验证范围。

补充（r36）：结算页三个时间选择器（日期/小时/分钟）在 `loadCheckout()` 时改为由已提交的 `expectTime` 反推索引，`verify-devtools-checkout-delivery-states.cjs` 新增 `expect_time_picker_restore` 断言（种子索引设定 09:00、提交值 19:30，重进页面后必须还原为 19/30，不能回落到默认小时）；`utils/checkout-time.ts` 新增 `parseExpectTime()`/`resolveCheckoutSchedule()` 等纯函数并由 `tests/utils/checkout-time.test.ts` 5 项单测覆盖。`verify-devtools-commerce-states.cjs` 新增已登录优惠券/积分空页断言（整页 `.yunxi-state`、“去选购”、44px 触控），订单页已登录空态继续作为同一空态结构的基准。商品目录移除静态“自提价”chip 与“人气汇聚/匠心手作/麦香现烤/层层甜蜜/生活美学”等无数据依据副标题，`check-miniapp.mjs` 的 `checkCatalogHeadlineAndScheduleConsistency()` 同时禁止这两类展示回归。分类导航仍受有赞分类/商品标签命名空间零交集阻塞（M-20260913-115，open），本轮不伪造静态分类兜底。

补充（r37）：购物车商品信息层级纳入运行态门禁。购物车内商品名改为独占信息列、两行截断，最长 41 字真实商品名不再只剩单行残句；库存/购买提示标签移到价格行并限制最大宽度，`devtools:cart-long-title` 用真实长名称播种 `cartItems`，断言 line-clamp=2、标题区尺寸、标签与数量步进器零重叠，并验证点击商品名可进入完整商品详情；商品图与商品名复用已有 `openProduct` 导航。充值记录空态从裸文本改为 `.yunxi-state.yunxi-state--section`，`verify-all-15-pages-devtools.cjs` 在充值页运行态断言该结构、文案和最小高度，`check-miniapp.mjs` 新增 `checkRechargeRecordsEmptyState()` 防止回退。

补充（r38）：商品数据一致性与底部安全区纳入门禁。`buildProductsCacheKey()` 原先未包含 `limit`，导致首页货架（featured+6）、购物车推荐（featured+4）、商品详情关联（featured+5）共用同一 5 分钟缓存条目，首页推荐条数随访问顺序在 4/5/6 之间漂移；缓存键补上 `limit` 后三个调用点各自独立，`verify-all-15-pages-devtools.cjs` 在首页新增“精选接口条数 vs 货架渲染条数”交叉校验并在计数稳定前轮询，`check-miniapp.mjs` 新增 `checkProductListCacheKeyIncludesLimit()` 静态守卫。商品详情 `.detail-page` 的 `padding-bottom: 220rpx` 改为 `calc(env(safe-area-inset-bottom) + 140rpx)`，与 `100rpx + 安全区` 的固定操作栏同源伸缩；`verify-devtools-product-purchase-path.cjs` 新增 `product-detail-footer-gap`，滚到底后测量最后内容分区与操作栏间隙（<0 遮挡或 >48px 大片空白均失败），`check-miniapp.mjs` 新增 `checkProductDetailFooterSpace()` 守卫。运行态结果：首页“商品数=6；接口=6，渲染=6”，footer gap=14.44px，`devtools:verify-all-pages` 15/15 PASS。

补充（r39）：首页承诺、群内登记履约口径与详情页滚动悬浮栏纳入门禁。首页服务承诺卡说明原先只有 18rpx 且 `white-space: nowrap`，第三项还写成“17:00 前咨询”，现为“当天制作 次日自取或配送 / 运费按地址单独计算 / 当天订单 17:00 截单”，标题 24rpx、说明 22rpx 并允许两行；群内登记页配送选项由“门店配送”改为“北京闪送”，并补充“运费按收货地址实测、由顾客承担，客服确认后告知”；商品详情页悬浮栏新增滚动状态（`navSolid` + `detail-nav--solid`），首屏压在商品大图上保持透明、`scrollTop > 8` 切实底、回顶复透明，修复正文穿透状态栏与返回控件叠字；商品卡购买说明同步升到 22rpx 并允许两行。`check-miniapp.mjs` 新增 `checkHomePromiseCardReadability()`、`checkGroupRegistrationDeliveryCopy()`、`checkProductDetailScrollNav()`、`checkProductCardHintReadability()`；`verify-all-15-pages-devtools.cjs` 新增 `inspectProductDetailScrollNav()` 与轮询助手 `waitForDetailNavState()`；`verify-miniapp-commerce-flows.cjs` 新增真实商品 `product-detail-scroll-nav`。运行态结果：15 页审计 15/15 PASS、`scrolledNavBackground=rgb(255, 255, 255)`、群内登记 `tabText=北京闪送`。

补充（r40）：购物车状态胶囊纳入文案长度门禁。库存充足时胶囊原先复用商品卡长购买提示，被省略号截断成“自提价展示，闪…”；现改为 `getProductAvailabilityLabel()` 只输出“现货/仅余 N 件/暂时售罄/已达库存上限”等短事实，无额外事实时不渲染胶囊，长运费口径保留在底部“商品合计 · 不含闪送费”。`check-miniapp.mjs` 新增 `checkCartTagCopy()`；`verify-devtools-cart-long-title.cjs` 新增 `cart-healthy-stock-tag`（库存充足不得出现长胶囊）与 `cart-low-stock-tag`（低库存必须为“仅余 3 件”且与数量控件零重叠）。运行态结果：`devtools:cart-long-title`、`devtools:verify-commerce-flows`、`devtools:verify-all-pages` 15/15 全部 PASS。

补充（r41）：购物车推荐卡口径统一与首页商品卡可读性纳入门禁。购物车“推荐商品”卡原先自建裸“加入”动作并把加购提示写死为“已加入预订单”，与首页/商品列表的 `getProductActionLabel()`、`getProductAddToastLabel()`、`getProductCardTip()` 分叉（配件商品出现动作与提示矛盾）；现统一改为复用这三个 helper，视图字段 `soldText`→`hintText`、样式类 `.recommend-sold`→`.recommend-hint`（两行 clamp + 最小高度 + 22rpx）。首页商品卡购买说明由 19rpx 提到 22rpx（11px）并限制在卡片宽度内自然换行，与商品列表同口径。门禁方面：`check-miniapp.mjs` 新增 `checkCartRecommendedActionCopy()` 并把 `checkProductCardHintReadability()` 扩展到首页 `.product-tip`；`verify-devtools-cart-long-title.cjs` 新增 `cart-recommend-card-copy`（渲染文案=页面数据、动作只允许“预订/加入购物车/查看”、提示 ≥11px、价格与动作零重叠）；`verify-all-15-pages-devtools.cjs` 新增首页商品卡购买说明量测（字号/溢出/行数）与连接后渲染预检（无法渲染首页即 exit=2）。同轮固化审计环境前置：本地后端 `127.0.0.1:7001` 必须 `/health` 200 且精选接口有数据，DevTools 必须为单一实例（多实例/陈旧端口会伪装成页面缺陷，见 ERRORS M-20260913-128/129）；同一轮还把商品详情悬浮栏断言从“只看 class”改为轮询背景 alpha，避免 0.18s 过渡造成的实底假失败（ERRORS M-20260913-130）。

补充（r42）：结算调度与登记成功态纳入运行态审计一致性。结算审计原先直接注入 `expectTime` 而绕过 `syncExpectTimeSchedule()`，截图中控件 `2026-09-13 18:00` 与预览 `2026-09-15 15:00` 并存；现统一调用页面真实同步方法，并新增 `checkout-schedule-consistency` 同时校验提交值、日期、小时、分钟和预览。登记审计原先在真实后端错误后未清理 Toast，导致成功截图出现“登记已提交/活动批次不存在或已结束”的假冲突；现在成功态截图前清除 Toast、匿名/登录注入都同步完整 `sessionView`，并断言 `successSessionText`、成功标题、说明、四行摘要和双按钮尺寸。成功面板同步改为确认图标、状态说明、四行摘要和等宽双操作按钮，保留原业务行为。运行态结果：`devtools:verify-commerce-flows` PASS、`devtools:registration-policy` PASS、`devtools:verify-all-pages` 15/15 PASS（另 8/8 未登录态 PASS）。

补充（r43）：商品目录搜索与长尾查找纳入运行态门禁。新增 `miniapp/scripts/verify-devtools-product-search.cjs`（npm script `devtools:product-search`），断言页面目录与全量接口一致（310 款且顺序一致）、“曲奇”3 条长尾商品全部命中且都在首屏 12 款之外、搜索栏输入前后高度差 ≤1px、清空按钮唯一且≥44px、无结果空态必须有“查看全部商品”出口、搜索结果可快捷预订并进入对应详情；商品页搜索栏与输入框统一 88rpx，清空按钮保留 88rpx 触控盒、可视圆点收到 52rpx，空态文案改为“换个关键词试试，或先看看全部商品”并新增一键出口，搜索结果新增“共找到 N 款商品 / 按销量排序”。同轮 `verify-all-15-pages-devtools.cjs` 增加锁屏探测与截图跳过：截图属证据而非断言，锁屏时页面断言照跑并把整轮标记为 `BLOCKED`（exit 2），不再把环境缺证据误报成 15 页产品失败。运行态结果：`devtools:product-search` PASS、`scan:button-touch-targets` 46 选择器/13 页 PASS、`devtools:verify-all-pages` 15/15 页面断言 PASS（status=BLOCKED）、`check:miniapp`/`typecheck` PASS；目录 5 款“非卖品仅展示/勿拍”商品仍可预订，待业务确认（M-20260913-137）。

补充（r43.1）：搜索审计证据状态口径修正。`verify-devtools-product-search.cjs` 原先在截图失败时把检查记为 `ok:false`，但顶层仍汇总为 PASS；现改为与 15 页审计一致的 `PASS=0 / FAIL=1 / BLOCKED=2` 三态，锁屏缺截图时输出 `BLOCKED / EXIT=2`，不再把证据缺失伪装成绿灯（M-20260913-140）。只读运行态复测同时确认商品目录规模问题：目录 310 款首屏仅 12 款，手动“查看更多”需 25 次；搜索“蛋糕”命中 310 款并一次渲染 310 张商品卡，检索面板内容高度 36281px（M-20260913-141，open）。接口复测进一步确认 `limit=30` 为 30 条 / 22274 字节 / 暖态中位 81ms，`limit=500` 为 310 条 / 302510 字节 / 暖态中位 228ms。下一轮计划分两阶段：第一阶段在方案确认后做客户端有界渲染与触底加载；第二阶段在上线前另立 API 契约，补服务端分页与关键词搜索，把首屏冷启动下载降到约 22000 字节量级。未获确认前不先改页面行为。

补充（r43.2）：DevTools 审计截图证据统一阻塞口径。锁屏下 `devtools:commerce-states` 以 `fail to capture screenshot` 直接整轮失败，盘点发现 `cart-long-title`、`checkout-delivery-states`、`product-purchase-path`、`registration-policy`、`commerce-flows` 与 `walkthrough:phase-c` 存在同类裸截图调用（M-20260913-142）。新增共享模块 `miniapp/scripts/lib/devtools-audit-status.cjs`，7 个脚本统一为“页面断言继续执行、截图失败只记环境阻塞（BLOCKED）”，退出码为通过（PASS）0 / 断言失败（FAIL）1 / 环境阻塞（BLOCKED）2。锁屏下串行复核：前 6 个脚本共 56 项检查、0 错误，全部 BLOCKED；`walkthrough:phase-c` 15/15 页导航成功、控制台 0 warning / 0 error、15 页截图阻塞；未发现产品断言缺陷。当前缺失的只剩锁屏环境下的当前代码截图，解锁后重跑同一批审计补齐视觉证据。

补充（r43.5）：商品页滚动偏移复位纳入门禁。搜索关键词收窄与商品分类切换后，两个 `scroll-view` 会复用旧滚动位置，导致用户直接落进结果中段；现为搜索面板与分类内容各增加零高度顶部锚点（`products-search-top`/`products-catalog-top`），`applySearch()` 与 `applyActiveCategory()` 在数据变化后重置对应 `scroll-into-view` 锚点，并以 `scroll-with-animation="{{false}}"` 立即生效；`index.wxss` 新增 `.products-scroll-anchor` 零高度样式。`check-miniapp.mjs` 新增静态守卫；`verify-devtools-product-search.cjs` 新增 `search-scroll-reset-on-keyword-change` 与 `catalog-scroll-reset-on-category-switch` 运行态断言，并把长尾样本改为按当前目录动态挑选，避免目录排序变化导致固定关键词落入首屏；审计开头强制重建商品页，清除上一轮分类夹具残留。审计还改为“真实输入/点击优先，DevTools 事件未送达时回退到页面方法”，并在报告 `inputPaths`/`clearPaths` 中显式记录实际路径（M-20260913-147）。运行态结果：搜索结果滚动到 `scrollTop=900` 后收窄关键词回到 `scrollTop=0`；分类列表滚动到 `scrollTop=900` 后切换分类回到 `scrollTop=8`、`catalogScrollAnchor=products-catalog-top`，未保留旧偏移；`devtools:product-search` 18 项检查 PASS。当前后端分类接口返回空数组且全部商品同一 categoryId，分类切换断言使用同数据夹具，真实多分类分区待分类数据可用后复测。
补充（r43.4）：商品目录规模护栏落地（M-20260913-141 第一阶段）。商品页目录由“每批 12 款手动查看更多”改为 `bindscrolltolower` 触底自动加载并保留按钮兜底；搜索结果首屏只渲染 30 款（`SEARCH_RENDER_PAGE_SIZE`），并区分“共找到 N 款商品 / 已展示 M 款 · 按销量排序”，触底或“查看更多搜索结果”按同序递增到尾部；搜索态计数、清空、切分类与重试统一走 `getEmptySearchState()` 复位，避免只清列表而漏掉计数。`check-miniapp.mjs` 新增 `checkCatalogIncrementalLoading()`；`verify-devtools-product-search.cjs` 新增 `search-render-bound`、`search-render-bound-screenshot`、`search-load-more-tail`、`catalog-scroll-load-more` 四项断言。运行态结果：“蛋糕”命中 310 款时首屏 DOM 30 张、计数文案“共找到 310 款商品 / 已展示 30 款 · 按销量排序”，连续 10 次加载后 310/310 渲染且首条排序基准不变；目录触底 12→24 款。`devtools:product-search` 16 项检查 PASS、`devtools:verify-all-pages` 15/15 页 + 8/8 未登录态 PASS、`check:miniapp`/`typecheck`/`test:bakery`/触控扫描/按钮审计均 PASS。第二阶段（服务端分页与关键词搜索）仍待上线前另立契约。
- [x] **Step 3: 完成测试节奏要求的单次收口全量测试**

仅在本轮功能实现和定向测试完成后运行一次全量测试，记录耗时：

```powershell
$start = Get-Date
pytest backend/tests -q
$elapsed = (Get-Date) - $start
Write-Output "backend pytest elapsed=$($elapsed.TotalSeconds)s"
npm test --prefix miniapp
```

若全量失败，转为定向定位；修复后只允许一次有记录的最终复跑。

- [x] **Step 4: 运行仓库门禁**

```powershell
python -B backend/scripts/check_project_development_register.py
python -B backend/scripts/check_chinese_governance.py --summary
python -B backend/scripts/check_evidence_index.py --summary
python -B backend/scripts/check_project.py --skip-tests
```

Expected: 门禁通过或明确记录既有失败、未验证项和阻塞原因。

- [x] **Step 5: 收口任务状态和证据**

更新 `LOGBOOK.md`、`PROJECT-STATE.md` 和 evidence index，明确区分：代码完成、策略合法、证据完整、可回放、闪送真实联调、真实支付/退款验收。没有闪送商户资料或真实受控验收时，不能写成已上线或已完成真实支付闭环。

---

## 执行依赖与阻塞规则

1. Task 1 未取得闪送平台文档和测试权限时，Task 3 的真实联调和 Task 7 的真实闪送场景保持阻塞；可以先完成模型、mock 和前端状态框架。
2. Task 2/3 的金额和报价契约未稳定前，不应大规模修改结算页支付逻辑。
3. Task 4 未通过报价绑定和金额快照测试前，不得把配送费显示为可支付最终金额。
4. Task 6 只在现有工作区改动已核对后执行，不覆盖其他 Agent 的页面调整。
5. 全国配送不作为本计划的隐藏扩展任务；只保留契约扩展位，不阻塞北京闪送和自提首发。
6. 每个 Task 独立定向验证；上线候选阶段才执行一次全量测试并记录耗时。

## 计划自检

- 设计文档的业务事实、首发边界、Platform 分层、闪送 Provider、报价状态、金额快照、订单状态和 DevTools 验收均有对应任务。
- 真实闪送接口字段没有被猜测；计划要求先取得官方资料，再实现适配器。
- 计划不把有赞历史 `post_fee_fen` 作为新订单配送费来源。
- 计划未引入 `TBD`、`TODO` 或“类似 Task N”占位。
- 前后端接口名称、履约值 `pickup`/`beijing_delivery`、报价字段 `deliveryQuoteId`、金额字段 `payableFen` 和状态枚举保持一致。
- 计划明确了现有工作区 dirty 状态、多 Agent 路径边界、测试节奏和上线边界。

## 补充记录（r45）


补充（r45）：群内登记时间基线跨日收口（M-20260914-001，E-20260914-001）。换日后复跑 `devtools:same-day-scheduling` 时发现：页面 `dateStartValue`/`selectedDateValue` 已是 `2026-09-14`，但 `isSameDayRegistration=false`、当天客服确认提示不显示。根因是 `pages/group-registration/index.ts` 的 `data` 默认值在模块求值时只算一次，`onLoad` 只重算 `desiredTime` 与 `selectedDateValue`，日期起点、小时选项与当天标记停留在小程序启动时刻；在 17:00 前启动、17:00 后打开登记页时，选择器仍允许当天日期与已过时段，而群内登记后端只按字符串保存 `desiredTime`、无截单校验。现新增 `REGISTRATION_BUSINESS_HOURS` 与 `buildRegistrationSchedule(expectTime?, now)`，用 `resolveCheckoutSchedule()` 统一产出日期起点/终点、可选小时与选中索引、`desiredTime`、当天标记，`data`/`onLoad`/`onShow` 三处统一按当前北京时间重建，`onShow` 把过期选择抬到最早可预约时间；`check-miniapp.mjs` 新增 `checkRegistrationScheduleRefresh()`，`verify-devtools-same-day-scheduling.cjs` 新增“当天标记=所选日期是否为今天”“日期落在可选区间”“注入过期状态后 onShow 必须重建”三项断言。运行态结果：`devtools:same-day-scheduling` PASS（`promptVisible=true`、`stale-state-repair` 后 `dateStartValue=2026-09-14`、`hourOptions=09..19`），`devtools:verify-all-pages` 15/15 页 + 8/8 未登录态 PASS，`devtools:registration-policy`、`devtools:product-search`（18 项）与前端静态门禁全部 PASS。后续项：群内登记后端补截单服务端校验；结算页持续可见并跨过 17:00 的窄窗口仍依赖后端 `order/schedule.py` 拒绝超时提交。

## 补充记录（r46）

补充（r46）：群内登记服务端履约校验收口（M-20260914-001，E-20260914-002）。`OrderScheduleService` 开放共享的 `validate_expect_time()`，把北京时间、营业时段和当天 17:00 截单规则抽成纯函数；`CustomerGroupOperationsService` 现在要求 `desiredTime` 并复用该 service，`lifespan_services.py` 向订单与客户群登记注入同一实例，`OrderApplicationService` 保留可选注入且默认行为不变。后端定向 65/65、`ruff` 通过；最新代码在本地 `127.0.0.1:7001` 重启，`/health=ok`，DevTools `wx.login` 与订单/地址/聊天真实受保护接口 4/4 PASS，`devtools:same-day-scheduling` PASS；`devtools:registration-policy` 的 11 项页面断言通过，但 Windows 锁屏导致截图证据为环境阻塞（BLOCKED），解锁后需补视觉帧。外部阻塞仍为有赞 IP 白名单、真实闪送联调与生产验收。

## 补充记录（r47）

补充（r47）：结算自提态审计夹具修正与本地运行态复测（M-20260914-002，E-20260914-003）。`verify-devtools-checkout-delivery-states.cjs` 原先把 `expectTime` 写死为历史日期、只调用 `refreshSubmitState()`，且把配送地址和 quoted 配送金额沿用到自提截图，造成选择器显示 `2026-09-14 18:00` 而预览仍为 `2026-09-10 15:00` 的自相矛盾证据。现改为按北京时间生成明天 15:00，注入后统一调用 `syncExpectTimeSchedule()`、`refreshEstimate()`、`refreshSubmitState()`；自提态独立清空地址并注入 `not_applicable`、`免运费`、`¥198.00`，新增四项运行态断言并输出新截图 `final-checkout-pickup-state.png`。本地后端 `127.0.0.1:7001` 健康、后端 65/65、DevTools 真实接口冒烟 4/4、`devtools:same-day-scheduling` PASS、结算页面断言无错误、15/15 页面与 8/8 未登录态断言 PASS；Windows 锁屏使截图证据按环境阻塞（BLOCKED）保留，解锁后仍需补视觉帧。

## 补充记录（r48）

补充（r48）：商品目录服务端分页与搜索收口（M-20260914-003 前端复核、M-20260914-004，E-20260914-004）。商品页原先在进页时用 `limit=500` 拉全量目录再本地过滤，既超过服务端单页上限 100（实际只拿到 100 条），又让搜索、分类和触底加载全部绑定首屏数据。现改为：`services/products.ts` 新增 `fetchProductListing()` 解析 `meta.total/limit/offset/hasMore` 并把 `offset`、`keyword` 纳入缓存键；`pages/products/index.ts` 删除 `FULL_CATALOG_LIMIT` 与 `allProducts` 全量缓存，首屏 12 条、搜索 30 条/页、分类切换重新拉页、触底加载取 `meta.offset + meta.limit`，搜索输入 300ms 防抖并用请求序号丢弃过期响应；`index.wxml`/`index.wxss` 增加搜索中、搜索失败与分类加载骨架态；`check-miniapp.mjs` 改为断言服务端分页契约，并修正页面定义正则未锚定行首导致的 `listProductPage({` 误匹配（M-20260914-004）；DevTools 搜索、购买路径、电商流程审计和触控扫描夹具同步改为读取 `activeProducts`/`catalogTotal`。运行态结果：`devtools:product-search` 19 项 PASS（首屏 12/310、搜索“蛋糕”命中 310 款时首屏只渲染 30 张并按服务端顺序翻页至尾部、关键词与分类切换 scrollTop 自 900 复位、夹具分类清理后真正恢复 12 款），`devtools:verify-commerce-flows`、`devtools:product-purchase-path`、`devtools:verify-all-pages`（15/15 页 + 8/8 未登录态）与 `scan:button-touch-targets`（13 页 46 选择器）PASS。后续项：有赞分类接口因 IP 白名单仍返回空数组，分类导航在生产数据可用前保持单一“全部商品”分区；服务端搜索目前是 SQL LIKE 包含匹配，若命中量继续放大再评估前缀索引或全文检索。

## 补充记录（r49）

补充（r49）：购物车语义、结算底栏金额来源与全页视觉取证收口（M-20260914-005～M-20260914-008，E-20260914-005）。逐张复核上一轮截图后发现三处体验与证据问题：（1）购物车数量为 1 时减号渲染为 `✕`，顾客会把“减量”误读为“立即删除”，现固定渲染 `-`，删除语义仍由数量为 1 的确认弹窗承担；（2）结算固定栏只显示“实付（估算）¥224.00”，看不到金额是否含闪送费，现新增 `footerAmountNote` 次要明细行，区分“已含闪送费 ¥26.00 / 自提价 · 免运费 / 闪送费确认中，暂未计入 / 闪送费未计入，提交前确认”；`check-miniapp.mjs` 新增两条静态守卫，购买路径与结算配送状态审计各新增运行态断言（减号文案与 44px 触控、四种配送态与自提态的底栏说明）。

全页审计原先用 `switchTab` 复用商品页上一轮搜索后的实例、用 `reLaunch('/pages/product-detail/index')` 无参进入详情，因此 `final-products.png` 是搜索态、`final-product-detail.png` 是“商品不存在”空态；详情页的悬浮栏滚动断言也因此一直被空态跳过。现新增 `preparePageState()`：商品页先 `resetSearchState()` 并断言 `searchText` 为空、目录非空，再回顶部（该页滚动区是原生页面滚动，元素无 `scrollTo`，回落 `wx.pageScrollTo`）；详情页从 `/api/v1/miniapp/products` 取真实在售商品 `id` 带参导航，未渲染真实商品直接报错。取证修复后立即暴露悬浮栏背景断言读到 `rgba(0,0,0,0)`：一次性探针确认过渡结束后为 `rgb(255,255,255)`（已清理临时文件），属 0.18s 过渡中间值假失败，故新增 `waitForDetailNavBackground()` 按 alpha 轮询稳定值并补“回顶恢复透明”反向断言。

运行期间本地后端 7001 与 DevTools 自动化端口 9420 先后掉线，用户已两次提醒“先启动后端再测”。为防重犯，审计脚本新增 `probeBackendHealth()` 前置门禁：`/health` 不通过时 `exit 2` 且不覆写上一份报告，必要时用 `MINIAPP_ALLOW_BACKEND_DOWN=1` 显式降级；反向验证指向 `127.0.0.1:7999` 时 `EXIT=2`、报告 `generatedAt`/`status` 与上一份 PASS 完全一致。最终运行态：`devtools:verify-all-pages` 15/15 页 + 8/8 未登录态 PASS（商品页搜索词空、12/310 款；详情页真实商品且悬浮栏滚动实底 `rgba(255,255,255,0.984)`、回顶恢复透明）、`devtools:product-purchase-path`、`devtools:checkout-delivery-states`、`devtools:verify-commerce-flows` 与触控扫描（13 页 46 选择器）均 PASS。后续项：闪送真实平台联调（Task 1 Step 3、Task 3 Step 5）仍因缺少开放平台资料与测试权限保持外部阻塞；详情页取证样本目前按销量取第一个在售商品，后续可固定一款蛋糕类样本以便跨轮对比。

## 补充记录（r50）

补充（r50）：展示型商品只读收敛与下单防线（M-20260913-137 转 guarded，E-20260914-006）。逐页复核上一轮截图时确认：本地 310 款商品里有 5 款标题自述“非卖品仅展示 / 勿拍 / 虚拟价格”（4487996522、4589335101、5552189607、4589414115、5552190749），此前仍带“预订”按钮、可以加入购物车并进入结算。业务侧最终口径（下架、独立“仅展示”分组或标签过滤）仍待客服/店主确认，但“不能下单”不依赖该确认，故本轮先按标题关键词做保守收敛：后端新增 `service/catalog/purchasability.py` 与 `isPurchasable` 读模型，`youzan_repo.get_prices_and_stocks()` 返回 `title` 供校验使用，`service/order/inventory.py` 在库存与价格校验前逐单拦截并抛出 `商品仅供展示，不可下单: <productId>`；小程序 `utils/bakery.ts` 统一输出“仅供展示 / 查看 / 仅用于原料或产品展示，不参与下单”，首页、商品目录、购物车推荐与商品详情四页阻断快捷预订、加购与立即购买，详情页改为只读说明卡 + “返回选购 / 咨询客服”，并隐藏数量步进器与履约卡。

为避免“只隐藏按钮但仍可下单”，新增三层防线：`check-miniapp.mjs` 的 `checkDisplayOnlyProductGuard()` 静态守卫、新增 npm 审计 `devtools:display-only-products`（`verify-devtools-display-only-products.cjs`）覆盖服务端读模型集合、目录卡动作与标签、详情页控件收敛、强制调用 `addToCart`/`buyNow` 后购物车仍为空，并在真实接口层用服务端签发会话直连 `POST /api/v1/miniapp/orders` 复验。运行态结果（重启 7001 后，PID 21892）：翻页拉全 310 款恰好 5 款 `isPurchasable=false`、其余 305 款 `true`；5 款直连下单全部 `400 商品仅供展示，不可下单`；`devtools:display-only-products` PASS 并产出 `display-only-product-detail.png`；后端定向 48/48、前端 `test:bakery` 9/9、`typecheck`、`check:miniapp`、`devtools:verify-all-pages`（15/15 页 + 8/8 未登录态）、`devtools:product-purchase-path`、`devtools:product-search`（19 项）、`devtools:verify-commerce-flows`、`devtools:checkout-delivery-states`、触控扫描（13 页 47 选择器）全部 PASS。后续项：确认有赞侧正式展示分组后，把判定来源从标题关键词换成分组/标签并复跑同一套断言；闪送真实联调（Task 1 Step 3、Task 3 Step 5）仍保持外部阻塞。

## 补充记录（r51）

补充（r51）：非卖品占位价与库存不再当作真实售价展示（M-20260914-012，E-20260914-007）。r50 只在动作层拦住下单，逐张目视复核截图时发现 5 款展示型商品仍显示有赞同步占位价（¥99999.00 / ¥1600.00 / ¥1140.00）与“库存充足”，详情页标题区同显“门店自提价 ¥99999.00”；接口复核确认 `priceFen=9999900/160000/114000`、`stock=99999+`、`soldText=库存充足` 仍原样存在，即读模型没区分“展示占位符”与“可售价”。现新增 `utils/bakery.ts#getProductPriceText()`，非卖品统一输出“非卖品”，首页、商品目录、购物车推荐与详情页搭配推荐全部改走该口径；商品目录非卖品隐藏库存胶囊，首页、目录、购物车推荐价格加 `is-display-only` 样式；详情页 `.detail-meta`（自提价 + 库存文案）改由 `!isDisplayOnly` 条件渲染；购物车推荐（取 12 回填 4）与详情搭配推荐（取 8 回填 4）过滤 `isPurchasable=false` 商品，避免推荐位出现不可下单商品或虚拟价。

门禁同步扩到价格维度：`check-miniapp.mjs` 的 `checkDisplayOnlyProductGuard()` 新增价格函数、三页价格样式类、目录库存胶囊、详情元信息与推荐位过滤断言；`devtools:display-only-products` 新增“搜索卡片渲染文本同时含非卖品与 ¥/库存充足即失败”的价格渲染断言、详情标题区文本断言与搭配推荐断言，并新增 `evidence-display-only-list-after.png` 证据。运行态结果：后端 `127.0.0.1:7001`（PID 21892）健康；`devtools:display-only-products` PASS（4 张展示型商品卡 `priceText=非卖品`、`renderedWithFakePrice=[]`、详情页 `hasDetailMeta=false`、搭配推荐无“非卖品/¥99999”），两张截图目视确认无占位价与“库存充足”；`typecheck`、`test:bakery` 9/9、`check:miniapp`（15 页/15 路由）、`devtools:verify-all-pages`（15/15 页 + 8/8 未登录态）、`devtools:product-search`（19 项）、`devtools:product-purchase-path`、`devtools:verify-commerce-flows`、`devtools:checkout-delivery-states`、`devtools:commerce-states`、触控扫描（13 页 47 选择器）全部 PASS。同时修复 `devtools:product-search` 空态文案偶发读到空数组（改为轮询到非空值再断言，M-20260914-013）与 `backend/scripts/append_logbook.py` 在 monorepo 下写错日志文件的问题（改为写仓库根 `LOGBOOK.md`，M-20260914-014）。后续项：有赞正式展示分组确认后需复核读模型是否应把占位价归零；闪送真实联调（Task 1 Step 3、Task 3 Step 5）仍保持外部阻塞。

## 补充记录（r52）

补充（r52）：商品详情服务入口图标与收货地址可履约性收口（M-20260914-015、M-20260914-016，E-20260914-008）。逐图目视复核发现商品详情底部服务入口用单汉字“询 / 购”冒充图标，与“加入购物车 / 立即购买”挤在同一横排，像未替换的占位稿；已改用与全局 TabBar 一致的标准线性聊天与购物车图标，保留“客服 / 购物车”标签并补 `aria-label`，运行态实测 2 个图标、无文字、19×19px，底栏间距 14.44px。

地址侧发现地址簿里存在只有“北京市东城区”“北京市朝阳区”的记录，而这类地址无法支撑闪送派单。新增 `utils/address.ts`（`isAddressDetailedEnough` / `getAddressDetailText`）定义最小可履约粒度，`utils/address-book.ts` 在保存前拦截，地址页对历史不完整地址标记 `needsDetailHint` 并提示“地址信息不完整，请编辑补充小区、楼栋或门牌号”，不删除也不改写旧数据；后端 `service/customer/address_support.py` 用同一口径拒绝行政区-only 地址，形成前后端一致的防线。重启本地后端（PID 8948，version `0.133.0-p2trial.3`）后实调 `POST /api/v1/miniapp/addresses`：`北京市东城区` 返回 `400 请补充小区、楼栋或门牌号`，完整地址返回 `200`，测试记录与临时 token 已清理。同一轮把商品详情悬浮导航的背景色移出 transition（只保留 `box-shadow`），消除回顶时读到过渡中间值的误判（M-20260914-007 复发口径收口）。

门禁同步：`check-miniapp.mjs` 新增禁止“询 / 购”单汉字回归断言与背景色不得参与 transition 守卫；`verify-devtools-product-purchase-path.cjs` 新增图标数量、无文字、背景图非空与尺寸不小于 18px 的运行态断言；新增 `miniapp/tests/utils/address.test.ts` 与 npm `test:address`，后端新增行政区-only 地址拒绝用例。运行态结果：`typecheck`、`check:miniapp`（15 页 / 15 路由）、`test:bakery` 9/9、`test:address` 2/2、地址定向 pytest 17/17、`devtools:product-purchase-path`、`devtools:verify-all-pages`（15/15 页 + 8/8 未登录态，悬浮栏双向断言通过：滚动态 `rgb(255,255,255)`、回顶 `rgba(0,0,0,0)`）、`devtools:commerce-states`、触控扫描（13 页 47 选择器）均 PASS。后续项：历史行政区-only 地址保留原记录只做提示，需顾客或客服主动补全；地址粒度判断仍是启发式口径，未接入微信地址解析或地图校验；闪送真实联调（Task 1 Step 3、Task 3 Step 5）仍保持外部阻塞。

## 补充记录（r53）

补充（r53）：预约时间控件可识别性与登录引导文案收口（M-20260914-017、M-20260914-018、M-20260914-019，E-20260914-009）。本轮把重点放在逐页目视评审：重跑 15 页审计后逐张查看截图，发现三处已确认的体验缺陷。第一处，结算页与群内登记页的“日期 / 小时 / 分钟”是 picker 控件，但与只读的“期望时间：2026-09-15 15:00”预览渲染成完全相同的方框，页面上没有任何迹象能区分前三项可点击、最后一项不可点击；预约时间是本店预订链路的核心输入，顾客可能直接以默认时间提交或找不到改期入口。现两个页面的三个 picker face 增加 `time-picker__chevron` 下拉指示、文案包进 `time-picker__value` 并保留超长省略，`.time-preview` 去掉背景与边框改为次要文字行。第二处，订单、订单详情、地址、优惠券、积分的登录引导副文案只是在重复标题（“登录后查看订单”配“请先登录后查看订单”），现改为说明登录后可获得的信息：制作/自提/配送进度、金额明细与履约进度、常用地址复用、券面与有效期、积分获取与抵扣记录。第三处，结算金额面板在未使用优惠券与余额时显示“-¥0.00”，与相邻积分抵扣行的“-”不一致，现新增 `utils/money.ts#formatDeductionFen()`，抵扣额 ≤0 统一输出“-”。

门禁同步：`check-miniapp.mjs` 新增 `checkTimePickerAffordance()`（三个 picker 都必须有下拉指示、期望时间预览不得带底色）、`checkDeductionPlaceholder()`（抵扣不得用模板字符串拼接）与 `checkLoginStateHintCopy()`（登录空态副文案不得是“请先登录后……”式重复）；`verify-devtools-checkout-delivery-states.cjs` 新增下拉指示尺寸、预览背景与 `checkout_deduction_placeholder` 数据断言；`verify-devtools-registration-policy.cjs` 新增 `registration_picker_affordance`；新增 `miniapp/tests/utils/money.test.ts` 与 npm `test:money`。运行态结果：`devtools:checkout-delivery-states` PASS（`timeChevrons` 3 个实测 6×6、`timePreviewBackground=rgba(0, 0, 0, 0)`、`estimateCouponFen=0` 时优惠券与余额行均为“-”）、`devtools:registration-policy` PASS（`pickerFaces=3`、`chevrons=3`、预览背景透明）、`devtools:verify-all-pages` PASS（15/15 页 + 8/8 未登录态；中间版本曾因地址登录引导文案 23 字换行报 FAIL，压缩到 17 字后复跑通过）、`devtools:verify-commerce-flows` PASS、`devtools:commerce-states` PASS、`devtools:product-purchase-path` PASS、`typecheck`/`check:miniapp`/`test:money` 3/3/`test:bakery` 9/9/`test:address` 2/2/`test:checkout-time` 5/5/`test:order-summary` 6/6 与触控扫描（13 页 47 选择器）均 PASS。后续项：登录引导副文案受空态单行宽度约束，后续加长会被全页审计拦下；闪送真实联调（Task 1 Step 3、Task 3 Step 5）仍保持外部阻塞。

## 补充记录（r54）

补充（r54）：会员中心入口图标线性化与支付方式顾客口径收口（M-20260914-021、M-20260914-022、M-20260914-023，E-20260914-010）。逐张目视评审截图时发现两处顾客可见问题。第一处，会员中心“我的订单”四个入口用“付/制/送/售”单汉字放在空白方块里充当图标，“特色服务”列表用“电/微/售/协/隐”单汉字放在圆圈里；截图上这些方块几乎等于空白占位，与 r52 已收口的商品详情同类缺陷重复出现。现把数据字段从 `iconText` 改为 `iconKey`，`index.wxml` 按 `iconKey` 渲染装饰图标节点并补 `aria-hidden`，`index.wxss` 定义 9 个内联线性图标（订单入口 wallet/clock/truck/rotate-ccw 40rpx；特色服务 phone/message-circle/shield-check/file-text/lock 48rpx 圆底 + 30rpx 字形）。第二处，订单详情在 mock 支付订单上把开发口径“MVP 模拟支付”直接展示给顾客，现新增 `utils/order-summary.ts#formatPaymentMethodText()`，把 `wechat/balance/combined/mock/未知` 映射为“微信支付/余额支付/组合支付/门店确认/待确认”，并新增 `test:order-summary` 覆盖。

门禁同步：`check-miniapp.mjs` 新增 `checkProfileShortcutIcons()`（禁止 `iconText` 占位、要求按 `iconKey` 渲染、要求 9 个 key 样式与 `aria-hidden`）与支付方式禁用词守卫；`verify-all-15-pages-devtools.cjs#inspectProfileShortcuts()` 从“只数图标元素”改为断言背景图可渲染、图标内无文字、渲染尺寸不小于 16px；`verify-miniapp-commerce-flows.cjs` 与 `scan-miniapp-button-touch-targets.mjs` 的会员中心夹具同步改为 `iconKey`。运行态结果：`devtools:verify-all-pages` PASS（15/15 页 + 8/8 未登录态；订单图标 4 个、服务图标 5 个，均 20×20px 或 24×24px、有背景图且无文字）、`devtools:verify-commerce-flows`/`devtools:product-purchase-path`/`devtools:checkout-delivery-states`/`devtools:registration-policy`/`devtools:commerce-states`/`typecheck`/`check:miniapp`/`test:order-summary` 7/7 与触控扫描（13 页 47 选择器）均 PASS；后端保持 `127.0.0.1:7001` 健康（PID 8948，`0.133.0-p2trial.3`），未重启。过程记录：首轮审计以“订单/服务入口图标缺少可渲染背景图标”FAIL，根因是新写 WXSS 的 data URI 前缀被替换成工具输出里的脱敏占位符（M-20260914-023），修正 9 处后复跑通过。后续项：新增 `iconKey` 必须同时补 WXSS 修饰类；闪送真实联调（Task 1 Step 3、Task 3 Step 5）与真实支付/退款、生产验收仍为外部阻塞。

## 补充记录（r55）

补充（r55）：空态与身份徽标图标线性化（M-20260914-024，E-20260914-011）。继续逐页目视评审时发现前两轮“单汉字冒充图标”的整改只覆盖了入口图标，共用空态与身份徽标仍是重灾区：13 处空态/登录引导在 140rpx 白底圆角方块内渲染单个汉字或标点（址/购/结/券/详/单/订/分/充/芸/!），群内登记与个人中心的身份徽标分别渲染“登/我”。空态是顾客遇到“未登录 / 加载失败 / 暂无数据”时的第一屏，占位式图标会让页面看起来像未完成的半成品。现 `app.wxss` 为 13 个 key 定义内联线性图标（map-pin / shopping-cart / shopping-bag / clipboard-check / ticket / receipt / file-question / package / loader / wifi-off / star / cake / wallet），去掉 `font-size` 文字渲染；13 处页面 WXML 改为按 key 渲染并补 `aria-hidden`；`session-notice` 组件把 `iconText` 换成 `iconKey`（log-in / user-check），个人中心与群内登记调用方同步。

门禁同步：`check-miniapp.mjs` 新增 `checkEmptyStateIcons()`（空态图标不得有文字内容、必须声明 key 修饰类、必须标 `aria-hidden`、key 必须在 app.wxss 有背景图规则、页面不得再向会话提示传 `icon-text`）；`verify-all-15-pages-devtools.cjs` 的登录引导断言从“图标文字非空”改为“背景图非空 + 渲染尺寸 ≥32px + 无文字”，并新增身份徽标断言。运行态结果：`devtools:verify-all-pages` PASS（15/15 页 + 8/8 未登录态；登录引导图标 72×72px、`iconBackground=set`、`iconText` 为空；群内登记徽标 31×31px、无文字）、`devtools:commerce-states`/`devtools:checkout-delivery-states`/`devtools:registration-policy`/`devtools:verify-commerce-flows`/`devtools:product-purchase-path`/`typecheck`/`check:miniapp` 均 PASS，触控扫描首轮 automator 超时中止（未写报告）重试后 PASS（13 页 47 选择器）。后续项：新增空态 icon key 必须同时补 app.wxss 背景图规则；闪送真实联调（Task 1 Step 3、Task 3 Step 5）与真实支付/退款、生产验收仍为外部阻塞。

## 补充记录（r58）

补充（r58）：沉浸式商品详情导航标题对比度收口（M-20260918-001，E-20260918-001）。逐张目视复核 r57 之后的 15 页截图时发现：商品详情首屏标题“商品详情”用深色文字直接压商家上传的商品大图，截图里正落在数字蜡烛包装的高光与金色图案交界处，文字与背景互相干扰；换成深色商品图时同一条标题会与背景同色，顾客读不到当前页身份。根因是 `.detail-nav` 沉浸态把 `page-fixed-safe` 的白色底与应用级标题样式一起透明化，页面唯一可用的底衬 `.page-fixed-safe::after` 又被 `has-custom-title` 显式 `display: none`，标题可读性完全依赖商品图恰好够浅。现为沉浸态标题补半透明白底胶囊（`rgba(255, 255, 255, 0.92)` + 1rpx 边框 + 轻阴影，胶囊中心与返回按钮垂直居中对齐），滚动切实底后由 `.detail-nav--solid` 把底衬还原为透明，避免白底叠白底。

门禁同步：`check-miniapp.mjs#checkProductDetailScrollNav()` 增加三条静态断言（沉浸态底衬不透明度 ≥ 0.8、不得参与过渡、实底态必须移除底衬）；`verify-miniapp-commerce-flows.cjs` 新增 `product-detail-immersive-title-contrast` 运行态断言，把半透明底衬分别叠到纯白与纯黑两个边界上计算对比度并取更差一侧，要求 ≥ 4.5:1，同时校验实底态底衬消失、回顶后恢复。运行态结果：`devtools:verify-commerce-flows` PASS（标题 `rgb(43, 39, 36)` 压 `rgba(255, 255, 255, 0.92)`，最坏情况对比度 12.37:1；实底态 `rgba(0, 0, 0, 0)`；回顶恢复 `rgba(255, 255, 255, 0.92)`），`devtools:verify-all-pages` 页面断言 15/15 页 + 8/8 未登录态、`devtools:product-purchase-path` 全部检查项无失败，两者截图证据因 DevTools `fail to capture screenshot` 记为环境阻塞（BLOCKED）（报告 `blockedReason` 只缺截图）；`typecheck`、`check:miniapp` PASS。后续项：沉浸式文字不得依赖商家图片明暗；闪送真实联调（Task 1 Step 3、Task 3 Step 5）与真实支付/退款、生产验收仍为外部阻塞。

## 补充记录（r59）

补充（r59）：商品目录页头收口与首页审计实例重置（M-20260918-002、M-20260918-003，E-20260918-002）。逐页运行态复核商品 tab 时发现两处展示问题：一是页头左侧的 `.page-fixed-safe__home` 在真机/模拟器渲染为 35×35px 的空白点击区，既无图标也无文字，顾客看不出这里可以返回首页；二是页头标题用 `SHOP_CONFIG.displayName` 渲染“芸熙烘焙（银河SOHO店）”（266px 宽），紧下方固定信息卡的“银河SOHO店”再次出现，同一门店身份连续占两行。商品 tab 是 TabBar 页，首页入口已由自定义 TabBar 承担，因此页头恢复为与购物车/客服/我的一致的默认品牌头，移除 `goHome()`、`storeName` 与 `.page-fixed-safe__home` 死样式，门店名只在固定信息卡出现一次。

门禁同步：`check-miniapp.mjs` 以 `checkNoHeaderHomeControl()` 取代原 `checkFixedSafeHomeAction()`，禁止任何页面重新渲染该隐藏控件；`verify-all-15-pages-devtools.cjs` 新增 `inspectProductsHeader()`，断言隐藏主页控件为 0、固定信息卡门店名非空、页头标题不包含门店名、页头容器高度 ≥20px。审计脚本另修复一处假失败：首页在本地后端不可用时会回落到 `mock-catalog.ts`，而 tab 页 `switchTab` 会复用旧实例，后端恢复后仍拿旧 mock 货架与新鲜接口比较；现审计首页改用 `reLaunch` 重置实例（M-20260918-003）。运行态结果：`devtools:verify-all-pages` PASS（15/15 页 + 8/8 未登录态，截图补齐；商品页 `hiddenHomeControlCount=0`、页头标题为空、固定卡门店“银河SOHO店”、页头 88px；首页“接口=6，渲染=6”）、`devtools:verify-commerce-flows` PASS、`devtools:product-purchase-path` PASS、`typecheck`/`check:miniapp` PASS。后续项：闪送真实联调（Task 1 Step 3、Task 3 Step 5）与真实支付/退款、生产验收仍为外部阻塞。
