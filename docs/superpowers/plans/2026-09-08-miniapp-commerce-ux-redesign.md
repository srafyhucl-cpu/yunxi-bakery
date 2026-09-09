# 芸熙烘焙小程序商品优先型 UI/UX 与履约重构实施计划

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

- [ ] **Step 1: 建立任务元数据**

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

- [ ] **Step 2: 核对并记录工作区基线**

运行：

```powershell
git rev-parse HEAD
git status --short
Get-Content backend/VERSION
python -B backend/scripts/check_project_development_register.py
```

Expected: 记录当前提交、版本和 dirty 文件；开发总表检查通过，或将已存在的失败单独登记，不覆盖既有修改。

- [ ] **Step 3: 完成闪送平台申请信息收集**

由项目负责人取得并归档以下非敏感资料：开发者/商户开通状态、API 文档版本、测试环境、签名规则、回调规范、门店取货地址要求、报价输入字段、报价有效期、取消/退款规则和错误码。密钥只写入本地非版本控制配置，不写入文档或仓库。

- [ ] **Step 4: 做前置 Go/No-Go 判断**

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

- [ ] **Step 1: 写状态和金额契约测试**

测试必须覆盖：`pickup` 不产生配送费；`beijing_delivery` 的 `deliveryFeeFen=None` 不能支付；报价状态只能从 `quoting` 到 `quoted/failed/expired`；配送回调重复事件只处理一次。

示例断言：

```python
assert build_payable_fen(19800, 2600, 1000, 500, 200, 0) == 20700
assert can_pay_quote(DeliveryQuoteStatus.QUOTED, 2600) is True
assert can_pay_quote(DeliveryQuoteStatus.PENDING_CONFIRMATION, None) is False
```

- [ ] **Step 2: 运行测试确认失败**

运行：

```powershell
pytest backend/tests/service/delivery/test_application.py -q
```

Expected: FAIL，原因是新模型和函数尚未实现。

- [ ] **Step 3: 实现领域模型和 schema**

新增固定枚举和数据类，金额全部使用整数分。新增表至少保存：报价 ID、用户 ID、请求摘要哈希、履约方式、商品金额、配送费、报价总额、状态、过期时间；配送单保存供应商单号、状态、费用和地址快照；回调事件保存外部事件 ID、原始摘要哈希、处理状态和处理时间。不得保存密钥或无必要完整客户原文。

- [ ] **Step 4: 实现仓储的参数化读写**

所有 SQL 明确列名并使用 `?` 绑定；增加报价按用户和报价 ID读取、过期更新、配送单按订单读取、事件按外部 ID幂等写入。不得在 service 直接访问 `aiosqlite`。

- [ ] **Step 5: 运行定向测试**

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

- [ ] **Step 1: 写 Provider mock 契约测试**

测试固定覆盖：成功报价、地址超范围、平台超时、签名失败、报价过期；平台返回金额以分保存；相同请求不把平台错误暴露为原始异常。

- [ ] **Step 2: 运行测试确认失败**

运行：

```powershell
pytest backend/tests/service/delivery/test_shansong.py backend/tests/api/test_miniapp_delivery_api.py -q
```

Expected: FAIL，原因是 Provider、应用服务和路由尚未实现。

- [ ] **Step 3: 实现 Provider 协议和 ShansongProvider**

Provider 只接收内部请求模型，不接收 FastAPI payload。签名、鉴权、超时、有限重试和错误映射集中在适配器内；日志只记录订单/报价内部 ID和错误分类，不记录密钥、完整地址或手机号。

- [ ] **Step 4: 实现报价应用服务和路由**

路由负责鉴权、输入校验和统一响应；应用服务负责读取实时商品、校验库存、生成请求摘要、调用 Provider、保存报价和返回稳定状态。闪送未启用时返回 `provider_unavailable`，不返回假报价。

- [ ] **Step 5: 实现真实平台受控联调**

仅在 Task 1 取得测试权限后运行近距离、远距离、超范围、不可服务和过期场景。每个场景记录请求摘要、报价状态、费用结果、错误分类和可回放证据，禁止记录密钥和完整地址。

- [ ] **Step 6: 运行定向门禁**

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

- [ ] **Step 1: 写订单金额和边界测试**

必须覆盖：自提配送费为 0；有效报价进入应付金额；报价过期拒绝；地址/商品/数量与报价不一致拒绝；配送费未确定拒绝支付；重复提交不重复创建报价或配送单。

- [ ] **Step 2: 运行订单测试确认失败**

运行：

```powershell
pytest backend/tests/api/test_miniapp_orders_api.py -q
```

Expected: 新增场景 FAIL，现有订单回归保持基线状态。

- [ ] **Step 3: 实现订单创建校验和金额快照**

服务端重新读取商品实时价格与库存，校验报价用户、地址、商品签名、数量和过期时间，生成不可变金额快照。旧 `delivery` 输入仅兼容映射到 `beijing_delivery`，新响应同时保留旧 `totalFen` 兼容字段和新明细字段。

- [ ] **Step 4: 接入支付金额校验**

所有支付分支以订单持久化的 `payableFen` 为准，禁止以小程序提交的金额作为支付依据。配送报价失败、配送费为 `null` 或快照过期时，支付接口返回稳定业务错误。

- [ ] **Step 5: 运行定向测试**

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

- [ ] **Step 1: 先更新 API 契约文档**

补充报价请求/响应、订单金额明细、状态枚举、报价过期规则、错误码和全国配送首发不开放说明。文档必须明确小程序不本地计算配送费。

- [ ] **Step 2: 写金额适配测试**

```typescript
expect(formatOrderAmountSummary({ goodsTotalFen: 19800, deliveryFeeFen: 2600, payableFen: 22400 })).toEqual({
  goodsText: "¥198.00",
  deliveryText: "¥26.00",
  payableText: "¥224.00"
});
```

同时测试 `deliveryFeeFen: null` 显示“待确认”而非“¥0.00”。

- [ ] **Step 3: 运行前端测试确认失败**

运行：

```powershell
npm test --prefix miniapp -- --runInBand miniapp/tests/utils/order-summary.test.ts
```

Expected: 新测试 FAIL，适配器尚未实现；若项目测试脚本参数不同，以 `miniapp/package.json` 为准并记录实际命令。

- [ ] **Step 4: 实现客户端和类型适配**

客户端只调用 Platform；请求地址变化、商品变化和预约时间变化由页面触发重新报价。所有金额展示通过整数分格式化函数，不在页面内直接除法拼接金额。

- [ ] **Step 5: 运行前端门禁**

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

- [ ] **Step 1: 建立页面状态测试/检查清单**

固定走查状态：未登录、登录、加载中、空精选、商品售罄、图片失败、地址未填、报价中、报价成功、报价过期、地址超范围、平台不可用、待支付、已支付、配送异常。

- [ ] **Step 2: 重构首页和商品展示**

首页只在有真实数据时展示精选、分类和复购；商品卡统一图片比例、价格、状态和购买动作。长尾商品进入真实分类和搜索，不在首页全量展开。

- [ ] **Step 3: 重构详情和朋友圈直达路径**

详情页独立展示商品图、价格、规格、状态、预订规则、履约方式和客服入口；不增加无数据评价、销量和配送承诺。

- [ ] **Step 4: 重构结算履约和报价交互**

自提路径不请求报价；北京闪送路径在地址、商品或预约时间变化后重新报价。报价未成功时禁用支付/提交，报价成功后展示金额明细；报价过期提供重新报价；失败状态提供客服兜底。

- [ ] **Step 5: 重构订单详情**

区分制作状态和闪送状态，展示不可变金额快照。自提订单隐藏闪送模块，配送异常显示明确客服动作。

- [ ] **Step 6: 统一视觉与交互系统**

以暖白、可可棕、少量奶油金为基础，减少旧绿色、渐变、玻璃拟态和无信息装饰；统一按钮、标签、圆角、间距、阴影、骨架、空态、错误和触控尺寸。保持微信原生实现和现有无第三方 UI 约束。

- [ ] **Step 7: 运行页面静态门禁**

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
- Create: `miniapp/scripts/verify-miniapp-commerce-flows.cjs`
- Modify: `miniapp/package.json`
- Modify: `docs/harness-engineering/core/evidence-index.md`
- Modify: `LOGBOOK.md`（由 owner 收口）
- Modify: `PROJECT-STATE.md`（由 owner 收口）

**Interfaces:**
- Consumes: Task 6 的页面和 Task 3/4 的接口；测试环境闪送 mock 或受控账号。
- Produces: 15 页面走查、交易链路和失败状态的可回放证据。

- [ ] **Step 1: 扩展 DevTools 走查脚本**

覆盖：首页精选、商品列表、详情直达、购物车、自提结算、闪送报价成功、报价过期、地址超范围、订单详情和控制台 warning/error。脚本不得访问生产真实支付，不得写入真实客户数据。

- [ ] **Step 2: 运行全页面定向走查**

运行：

```powershell
npm run devtools:verify-all-pages --prefix miniapp
npm run devtools:verify-commerce-flows --prefix miniapp
```

Expected: 页面和流程结果分别记录 PASS/FAIL、失败分类、截图/日志路径和未验证范围。

- [ ] **Step 3: 完成测试节奏要求的单次收口全量测试**

仅在本轮功能实现和定向测试完成后运行一次全量测试，记录耗时：

```powershell
$start = Get-Date
pytest backend/tests -q
$elapsed = (Get-Date) - $start
Write-Output "backend pytest elapsed=$($elapsed.TotalSeconds)s"
npm test --prefix miniapp
```

若全量失败，转为定向定位；修复后只允许一次有记录的最终复跑。

- [ ] **Step 4: 运行仓库门禁**

```powershell
python -B backend/scripts/check_project_development_register.py
python -B backend/scripts/check_chinese_governance.py --summary
python -B backend/scripts/check_evidence_index.py --summary
python -B backend/scripts/check_project.py --skip-tests
```

Expected: 门禁通过或明确记录既有失败、未验证项和阻塞原因。

- [ ] **Step 5: 收口任务状态和证据**

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
