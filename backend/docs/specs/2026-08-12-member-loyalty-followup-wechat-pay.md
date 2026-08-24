# 后续工作包 FP-3：真实微信支付（工程实现 + 生产验收两阶段）

- status: pending
- parent_trace_id: `20260812-member-loyalty-storedvalue`
- 执行时须生成独立 trace_id（如 `2026MMDD-member-loyalty-wechat-pay`），不得复用父计划 trace
- 所属计划：[2026-08-12-member-loyalty-storedvalue-plan.md](./2026-08-12-member-loyalty-storedvalue-plan.md)（M2 储值余额 / M3 积分 / M4 优惠券支付链路）
- 阻塞依赖：微信支付商户号（阶段二）
- 当前条件：截至 2026-08-14，尚不具备受控真实微信支付 / 退款测试条件
- 拆分来源：2026-08-14 M1–M6 完整评审（方案 B 分阶段结项）；2026-08-14 深度复核修正

## 背景

组合支付结构（`remain_fen = total_fen - coupon_fen - balance_fen - points_fen`，统一 `compute_remain_fen(total, coupon, balance, points)`）已上线，但真实微信支付受商户号阻塞。**这不是"商户号到位即可验证"**——当前还缺少真实支付所需的资金状态机与若干工程能力（见下）。

## 当前实现事实（复核修正）

- 订单支付：已有 `mock-pay`、`prepare_payment`、`handle_wechat_payment_notify`（JSAPI 预下单 + 支付通知）。
- 微信适配器（`app/service/integrations/wechat_pay.py`）：`create_jsapi_prepay`、通知验签与解密；**没有微信关单、退款、退款查询**。
- 充值 API（`app/api/channels/storefront/recharges.py`）：仅 `POST /{recharge_id}/mock-pay` 与 `/{recharge_id}/cancel`，**没有充值真实支付回调、充值微信关单、退款、退款查询**。
- 余额全额支付订单当前**不可退款**（主计划 M2 明确约束）。
- 跨微信款 / 余额 / 积分 / 券的补偿顺序、退款失败恢复未实现。

因此 FP-3 拆为两个阶段：**阶段一 工程实现**（无需商户号即可开发与本地验证）与 **阶段二 真实商户生产验收**。

## 阶段一：支付 / 退款工程实现

1. 储值充值支付状态机：`unpaid → paying → paid / cancelled / expired`，新增真实支付回调落地（现仅 mock 确认）；充值尝试纳入 `payment_attempt`（`subject_type=recharge`，`provider=wechat` 时 `merchant_order_no` 唯一），回调按主体 + 商户单号归属，避免真实回调无归属。
2. 交易号 / 退款号持久化：微信 `transaction_id`、商户单号（`out_trade_no`）、退款单号落库，幂等键覆盖重复通知 / 重复退款请求；`payment_attempt.payment_snapshot_json` 持久化不可变快照（各资产分摊 / 券周期 / 币种 / 策略版本 / 金额）。**（B3.3：币种字段统一为微信 v3 通知 resource `amount.currency`、校验值固定 `CNY`（v2 旧称币种字段不再使用）；支付 / 退款通知与订单 / 退款查询四类 ProviderEventNormalizer 契约、事件键、快照比对与负向测试以 ADR 0008 D1-A 为唯一源；交易号缺失时事件键稳定性与碰撞合同见 ADR 0008）**。
3. 微信关单：超时未支付调用微信关单，状态收敛，防重复支付。
4. 微信退款与退款查询 + 持久退款聚合：退款聚合状态集 `requested / processing / succeeded / failed / manual_review`；退款单号幂等（`refund:<refund_no>`）；异步退款结果通知落状态；查询补偿（对账任务拉取微信退款结果）；进程重启后从未完成状态恢复；每日对账状态报告。第一次真实支付前必须落地（阶段一第 10 条门禁）。
5. 余额全额支付退款：按 **ADR 0008 D1-C 既定政策**（支持全额与部分退款、净额口径、`payment_refund_quota` 逐腿额度、差分分摊）落地退款能力，解除"余额全额支付订单不可退款"约束；**不再保留"或按产品决策保留"待选项**（政策已定稿，见 ADR 0008）。
6. 跨资金补偿顺序：明确退款时微信款 → 积分（退回 pointsUsed / 收回 pointsAwarded）→ 余额 → 券（核销回退）的补偿顺序与回退链路。
7. **券 BACK 退款接入**：`COUPON_CUSTOMER_PROMOTION` 的 `BACK` 状态接入核销 / 退回链路（承接 M4 评审遗留 #2 退款未接 BACK）。
8. 幂等与失败恢复：重复通知幂等、退款失败进入重试队列、进程重启后可恢复未完成退款。
9. 本地验证：全套测试 + `ruff` + `check_project --skip-tests` 门禁通过。
10. **第一次真实支付前硬门禁**：按 **ADR 0008 D1-C 既定政策**（全额 + 部分净额退款、差分分摊、逐腿额度）落地 `refund_aggregate + refund_operation`（原支付快照、各资产分摊、每步幂等键、重试与人工复核、微信已退本地未补偿的恢复策略）；项目负责人**仅裁决参数**（退款时限、审批阈值、金额上限等，默认时限 72h）；评审通过后方可进入阶段二受控测试。

## 阶段二：真实商户生产验收

1. 真实 JSAPI 支付：充值 / 组合支付差额走微信 JSAPI，验证统一下单、调起支付、支付成功回调。
2. 支付通知回调幂等：重复通知不重复入账、不重复发分 / 核销。
3. 金额校验：微信通知金额与 `remain_fen`（= `compute_remain_fen(total, coupon, balance, points)`，含券/余额/积分抵扣）严格一致，防篡改。
4. 取消与退款：取消 / 超时 / 后台取消按 **`payment_attempt.payment_snapshot_json` 资产分摊**原路退款（**B3.1：`order.payment` 仅展示缓存，余额腿按快照 `balance_fen` 原路退回——删除 `payment.balanceFen` 旧退款口径**）；余额全额支付退款走余额原路退回。
5. 边界值验证：`amountFen=50000` 恰好等于上限的边界行为（60000 超限 400 已有证据）。
6. 生产端到端证据归档：微信登录 → 下单 → 支付 → 回调 → 账务入账 → 退款 / 关单，证据索引 / LOGBOOK 收口（独立 trace_id）。
7. **唯一事实与迁移（B3.1）**：真实支付验收前按 [ADR 0008 D1-0](../harness-engineering/adr/0008-accounting-core-consistency.md) 完成**逐端点迁移核对**（旧写路径禁用 / 转发）与**历史未完成处置**（未完成订单 / 充值单回填 `payment_attempt` 或 `manual_review`），**"历史待处理为 0"**（无未归属回调 / 未处置 `prepay_unknown` / 未查询退款 / 未决 `manual_review`）作为阶段二放行证据之一。

## 验收标准

- 阶段一：资金状态机、关单、退款、退款查询、跨资金补偿顺序均有测试覆盖并通过；退款失败可恢复。
- 阶段二：充值、组合支付、回调幂等、金额校验、取消、退款全链路有生产端到端证据。
- 无重复入账、无金额不一致、无退款丢失。
- 证据索引与 LOGBOOK 记录 trace_id 关联完整。

## 边界

- 阶段一不依赖商户号，先行完成；阶段二依赖商户号与微信支付相关资质。
- 涉及真实资金，阶段二前需小额受控测试并确认异常恢复路径（不可逆前中止、不可逆后 roll-forward 补偿）。
- 2027-05-31（含）前不面向真实用户。未来条件具备后，阶段二只允许授权测试账号在项目负责人事前批准下开展小额真实支付 / 退款测试，并完成全额退款、账务对账、测试数据标记与证据归档。
- 受控真实测试通过仅代表上线准备完成，不代表已经获准开放真实用户。
