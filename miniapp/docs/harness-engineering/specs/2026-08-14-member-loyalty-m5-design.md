# M5 会员资产前端设计

- 状态：待批准（v2，按用户复审 4 点跟进修订：#1 支付开关与后端 ALLOW_MOCK_PAYMENT 对齐、#2 积分明细 biz_type 映射、#3 券中心 tab 规则微调、#4 thresholdFen 批量取模板）
- trace_id：`20260814-member-loyalty-m5`
- 来源：计划书 `docs/specs/2026-08-12-member-loyalty-storedvalue-plan.md`（M5 小程序前端）；brainstorming 问答（Q1-Q8）与用户 4 项修订
- 仓：`YunxiBakeMiniApp`（前端主体）+ `YunxiBakeBot`（1 个后端字段补充）
- 前置：M2 储值闭环（`/recharges`、`/balance`）、M3 积分闭环（`/points`、points-preview/apply-points）、M4 优惠券闭环（`/coupons`、coupon-preview/apply-coupon）、订单支付链路（pay-with-balance / prepare-combined-payment / prepare-payment / mock-pay）

## 目标

在既有微信原生小程序（TypeScript）上交付会员资产前端闭环：我的页资产真实化、积分明细、优惠券中心、充值页、结算页优惠与余额抵扣扩展。后端 API 全部复用 M2-M4 交付，仅补 1 个字段（`thresholdFen`）。

## 范围与边界

**范围内**

- 我的页：余额/积分/可用券数三项接真实 API，并作为三个入口。
- 积分明细独立页（`GET /api/v1/miniapp/points` 的 ledger，最多 50 条倒序，不分页）。
- 优惠券中心（我的券，tab：可用/已用/已过期）。
- 充值页（档位配置 + 自定义金额 + 充值记录 + mock 支付确认 + 赠送角标口子）。
- 结算页扩展（券选择 + 积分开关 + 余额自动抵扣 + 4 分支支付决策）。
- `docs/api-contract.md` 契约更新（profile 契约改真实 API + 新页面契约）。
- `YunxiBakeBot`：`get_my_coupons` 响应补 `thresholdFen`（跨仓小任务，第一批第一步）。

**范围外（本期不做）**

- 领券中心/客户自领券 API（本地发券靠有赞/管理后台，无客户自领契约）。
- 真实微信支付（商户号未到位；develop/trial 走 mock，release 走余额-only 过渡）。
- 积分明细分页（现有 ledger 上限 50 条）。
- 会员权益卡（无后端数据源，我的页移除该项）。
- 券的「去使用」跳转（本期只展示）。
- 后端充值赠送入账（`bonusFen` 仅前端角标占位，实际到账以服务端 `amountFen` 为准）。

## 已确认决策

1. 支付：商户号未到位，本期 mock 闭环；生产 release 由配置开关控制入口。
2. 余额：默认自动抵扣、可手动关闭；余额足够→余额支付，不足→差额 mock/微信。
3. 结算：一步式——提交时才建单并按序 apply，弹窗确认精确实付金额。
4. 券中心：我的券 tab，无领券。
5. 积分明细：独立页，现有 ledger 不分页。
6. 我的页：三项真实化，权益卡移除，等级/副标题/有效期保留 page-config 装修文案。
7. 充值：档位配置数组含 `bonusFen` 口子，后端本期不动。
8. 批次：一个计划内两批（第一批展示类，第二批交易类）。
9. 【修订·高】release 支付过渡策略：微信/mock 路径 release 下后端会拒绝，由同源开关控制入口。
10. 【修订·高】apply 时序约束：弹窗确认前不改订单；取消后复用订单或取消订单；积分一旦应用不可撤销。
11. 【修订·中】4 分支支付决策表（含 remain==0 与余额不足降级）。
12. 【修订·中】充值入口 develop/trial 可见；`bonusFen` 仅展示占位。

## 支付能力开关（核心约束）

> v2 修订 #1：开关语义与后端 `ALLOW_MOCK_PAYMENT`（生产默认 False）对齐。关键区分是**后端环境**而非前端环境：trial/develop 若连**生产 API**，mock 支付/充值确认会被生产后端 400 拒绝。因此交易类能力由 `IS_USING_LOCAL_API`（本地后端）控制；展示类不受限。

新增 `miniprogram/services/payment-gate.ts`：

```ts
// 本地后端（mock 支付可用）：IS_USING_LOCAL_API 为 true 时 API_BASE_URL 指向 127.0.0.1:7001
export const IS_LOCAL_BACKEND = IS_USING_LOCAL_API;
// 充值 mock 确认依赖本地后端
export const RECHARGE_READY = IS_LOCAL_BACKEND;
// 在线支付路径（prepare-payment / 组合差额会话，需 mock 或微信）依赖本地后端
export const ONLINE_PAYMENT_READY = IS_LOCAL_BACKEND;
```

- 展示类（我的页资产、积分明细、券中心）：不限环境，任何环境可联调。
- 余额支付（`pay-with-balance`）：**不限环境**（真实后端能力，不依赖 mock/微信）。
- 在线支付路径（`prepare-payment` / `prepare-combined-payment` 差额）：仅 `IS_LOCAL_BACKEND` 可用；trial/develop 连生产 API 时同样不可用，前端禁用差额按钮并提示「在线支付即将上线，请到店支付或联系客服」。
- 充值入口：仅 `RECHARGE_READY`（`IS_LOCAL_BACKEND`）显示；release 隐藏入口。
- 商户号到位后的翻开关清单（写入计划收口任务）：放开 release 在线支付（真实微信 JSAPI）→ 放开充值入口真实微信支付；届时 `payment-gate.ts` 改为按后端能力接口判断。
- 联调约束（v2 修订 #1）：交易类流程（充值 mock-pay、结算 mock-pay）必须 `IS_USING_LOCAL_API=1` 连本地后端；连生产 API 的 trial/develop 只做展示类联调。

## 页面设计

### 1. 我的页（修改 `pages/profile/index`）

- 资产三项接真实 API，并行加载（`Promise.all`），单项失败降级 `--` 不阻塞页面：
  - 余额：`GET /api/v1/miniapp/balance` → balanceFen。
  - 积分：`GET /api/v1/miniapp/points` → pointsBalance。
  - 可用券数：`GET /api/v1/miniapp/coupons` → 过滤 `status=TAKE` 且未过期。
- 401 行为：走既有会话刷新流程（`http.ts` 的 retryOnUnauthorized），刷新失败提示登录。
- 每项可点击：余额→充值页（`RECHARGE_READY` 才显示入口）、积分→积分明细、券→券中心。
- 移除权益卡项；等级/副标题/有效期保留 page-config 装修文案（装修配置不是数据）。
- `docs/api-contract.md`：profile 的 `memberSummary` 契约改为「资产数字必须来自真实 API，装修文案可来自 page-config」。

### 2. 积分明细（新增 `pages/points/index`）

- 顶部：当前积分余额。
- 列表：`GET /points` → ledger（倒序），行内展示时间 / ±变动 / 变动后余额 / 来源说明。
- 来源映射（v2 修订 #2，按 `biz_type` 优先级）：`order_award`→订单奖励、`order_redeem`→订单抵扣、`order_refund`→退款退回；无订单 biz_type 时按 `source` 兜底：`webhook`→有赞同步、`import`→导入、`order`→订单消费。
- 空态 / 加载态 / 错误态文案。

### 3. 优惠券中心（新增 `pages/coupons/index`）

- tab（v2 修订 #3）：可用（`status=TAKE` 且 `validFrom <= today <= validUntil`）/ 已用（`CONSUME`）/ 已退回（`BACK`，展示文案「已退回」而非「已用」，避免误以为可复用）/ 已过期（`TAKE` 且 `validUntil < today`，前端派生）。
- 卡片：券名、面额 `valueFen`、门槛 `thresholdFen`（依赖后端补充）、有效期 `validFrom~validUntil`。
- 已用券：附 `deductedFen`（抵扣金额）与 `orderNo`（订单号）。
- 不做领券、不做「去使用」跳转。

### 4. 充值页（新增 `pages/recharge/index`）

- 顶部：当前余额 + 充值记录列表（`GET /api/v1/miniapp/recharges`）。
- 档位：`RECHARGE_TIERS` 配置数组 `[{ amountFen, bonusFen }]`；`bonusFen` 默认 0，全 0 时隐藏「送」角标；`bonusFen` 仅展示占位，实际到账金额以服务端 `amountFen` 为准（后端无赠送契约）。
- 自定义输入：1~500 元（前端校验，后端 MIN/MAX_RECHARGE_FEN 兜底）。
- 提交：`POST /recharges` 建单 → 确认弹窗（充值金额 + 到账金额）→ `POST /{recharge_id}/mock-pay` 确认 → 成功刷新余额与记录。
- 入口开关：`RECHARGE_READY`（我的页余额入口按开关显示）。

### 5. 结算页扩展（修改 `pages/checkout/index`）

- 优惠区（表单下方）：
  - 优惠券：「可用 x 张」→ 选择面板选一张（列表来自 `GET /coupons` 过滤可用）；选中后显示「已减 ¥xx」（估算，最终以服务端为准）。
  - 积分：开关，显示「可用 xx 积分」，不估算金额（避免比例漂移）。
  - 余额抵扣：默认开，显示「余额抵扣 ¥xx / 可用 ¥xx」，可手动关闭。
- 金额区：商品合计 / 优惠小计（券+积分）/ 余额抵扣 / 实付（估算）。
- **提交时序（修订·高）**：
  1. 校验表单 + 购物车商品有效性。
  2. 无 pending 订单 → `POST /orders` 建单；有 pending 未支付订单 → 复用该订单。
  3. 按序 apply：选券 → `POST apply-coupon`；开积分 → `POST apply-points`（弹窗确认前不改订单）。
  4. 按 4 分支决策表调支付预览。
  5. 弹确认窗：展示服务端返回的精确 `remainFen` + 优惠明细 → 确认 → 执行支付（develop/trial mock；release 仅余额路径）。
  6. 取消弹窗：订单保留 partial 快照（积分不可撤销，依赖后端订单超时清理）；提供「继续支付 / 取消订单」；取消订单调 `POST /orders/{id}/cancel`，清空 pending。
- **4 分支决策表（修订·中）**：

| 条件 | 动作 |
|---|---|
| `remain_fen == 0`（券+积分全额抵扣） | 确认窗显示「无需支付」→ `pay-with-balance`（0 金额置 paid，后端支持） |
| `balance >= remain`（余额充足） | `pay-with-balance` |
| `0 < balance < remain`（余额部分抵扣） | `prepare-combined-payment` → 差额支付（develop/trial mock；release 提示在线支付暂不可用） |
| `balance == 0`（无余额或用户关闭余额） | `prepare-payment` → 全额支付（模式开关同上） |
| `pay-with-balance` 报「储值余额不足」 | 降级提示：转组合支付或引导充值，不落账 |

- pending 订单：storage 保存 orderId（与购物车快照绑定），重新进入结算页时提示「继续支付上次订单」。

## 后端小任务（YunxiBakeBot 仓）

- `get_my_coupons` 响应补 `thresholdFen`（读取券模板门槛）。
- 位置：`app/service/coupon/__init__.py`；测试：`tests/api/test_miniapp_coupons_api.py`。
- 实现要点（v2 修订 #4）：`CouponTemplateRepo` 新增 `list_by_ids(ids)` 批量查询；`get_my_coupons` 收集 `template_id` 去重后**一次查询**建映射，禁止逐张 `get()` 造成 N+1（券列表上限 100 张）；模板缺失时 `thresholdFen` fallback 0。
- 跨仓收口：同一 trace_id `20260814-member-loyalty-m5`，YunxiBakeBot LOGBOOK 与 miniapp LOGBOOK 都挂该 trace_id。

## 契约与文档更新

- `docs/api-contract.md`：profile `memberSummary` 契约改真实 API；新增充值/积分明细/券中心/结算扩展契约条目。
- `check-page-api-coverage` 脚本同步（新增 3 个页面）。
- 发布验收清单 `docs/release/manual-acceptance-checklist.md` 同步（mock 支付、release 过渡行为）。

## 批次与验证

- 第一批（展示类）：`thresholdFen` 后端小任务 → 新增 services → 我的页 → 积分明细 → 券中心。
- 第二批（交易类）：充值页 → 结算扩展。
- 每批验证：`tsc --noEmit`、`npm run check:miniapp`、本地起 Platform（mock 模式）devtools 联调、收口（trace_id + LOGBOOK + evidence-index）。
- 联调账号：需有绑定手机号的真实登录态（券/积分/余额均为 mobile 维度）；无手机号时显示「绑定手机号后可查看资产」提示。

## 风险与决策记录

- apply 后取消：积分不可撤销，依赖后端订单超时清理 + 明确的取消订单路径（风险已由修订 10 闭环）。
- release 过渡：余额-only 支付，差额提示到店支付/客服（修订 9）。
- `bonusFen` 后端无契约：仅前端占位，联调时不得误以为后端会加赠（修订 12）。
- `thresholdFen` 依赖后端小任务：放在第一批第一步，避免券中心联调返工。
- 前置事项：miniapp 仓现存未提交改动（DevTools CLI 修复，trace 20260807-post-p0-production-closure）与 M5 无关，动工前先确认归属。
- 联调环境（v2 修订 #1）：交易类 mock 流程必须连本地后端（`IS_USING_LOCAL_API=1`）；trial/develop 连生产 API 时交易按钮禁用并提示，只可联调展示类。
