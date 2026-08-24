# 跨入口资产策略矩阵（X1 设计）

- status: proposed
- parent_trace_id: `20260812-member-loyalty-storedvalue`
- 拆分来源：2026-08-14 完整复核（评审问题 3、4）
- 关联 ADR：[0008](../harness-engineering/adr/0008-accounting-core-consistency.md)

## 背景

当前小程序与有赞并存。小程序 storefront API 中充值、余额支付、积分抵扣、券抵扣均**无服务端资产开关**（仅 `ALLOW_MOCK_PAYMENT`、`POINTS_AUTHORITY`、`COUPON_AUTHORITY` 三个开关）；仅隐藏前端入口可被直接 API 调用绕过。旧入口能力**待外部核验**：本仓代码仅能证明 Platform 未封装有赞储值/积分写 API（`member_api.py` 仅查询、`event_member.py` 仅事件镜像），**不能证明旧有赞小程序或后台具备 / 不具备写能力**；以有赞配置、旧小程序能力清单与证据确认后入证据索引。

## 服务端资产策略矩阵（目标）

新增服务端资产策略配置（`app/config.py`），对四类资产写操作独立控制，在**应用服务层与支付成功联动点强制执行**（不依赖前端隐藏）：

| 资产写操作 | 配置开关（默认） | 受控入口 |
|---|---|---|
| 储值充值 / 余额入账 | `ASSET_STORED_VALUE_WRITE`（default `enabled`，上线前按裁决改 `disabled`） | `stored_value/recharge.py` 入账；`orders.py pay-with-balance`、`prepare-combined-payment` |
| 储值余额支付 | `ASSET_STORED_VALUE_PAY`（同上） | `stored_value/payment.py:42/:106` |
| 积分抵扣 / 发放 / 退款 | `ASSET_POINTS_WRITE`（同上） | `points/__init__.py apply_points`；`points/payment.py` 发分/退回 |
| 券应用 / 核销 / 退回 | `ASSET_COUPON_WRITE`（同上） | `coupon/__init__.py apply_coupon`；`coupon/payment.py` 核销/BACK |
| 支付成功联动（置 paid + 发分 + 核销） | 由上述开关组合 + `PAYMENT_COMMIT_ASSET_FLUSH` | `payment_runtime.py:156-157`、`payment_notification.py:137-138`、`stored_value/payment.py:100-101` 三处统一切入 |

- 开关在**应用服务层**与**支付成功联动点**强制执行：`disabled` 时对应写操作拒绝并返回受控错误（非 401 伪装），覆盖直接 API 调用绕过。
- **策略固化时点（B1.7 修正：在首次不可逆承诺前固化，而非支付成功时；B3.1 唯一事实修正）**：在**首次不可逆承诺**（余额预占、券 `RESERVE` 预占、创建微信支付会话——三者任一先发生）时，随 **`payment_attempt.payment_snapshot_json`** 固化 `payment_attempt_id + policy_version + asset_policy_snapshot`（**B3.1：唯一事实在 `payment_attempt`，`order.payment` 仅同步展示缓存，不再承载策略固化事实**）。支付会话已创建或余额 / 券已预占后、开关再关闭，该 `payment_attempt_id` 属于在途业务，**必须按快照完成结算**；不因开关关闭中断已收款订单。
- **授权三分类（B1.7）**：
  - **新业务**：新下单 / 新抵扣 / **新支付尝试**（新的 `payment_attempt_id`，含重试、超时后重新发起）必须按**实时策略**重新授权——任一是 `disabled` 即拒绝，不产生资产副作用。
  - **在途结算**：已固化的 `payment_attempt_id`（余额 / 券预占或微信支付会话已创建）按 `asset_policy_snapshot` 完成，不因实时开关关闭而中断。
  - **系统补偿**：退款 / 对账补偿按 `asset_policy_snapshot` 原路补偿，不禁用。
- **重试 / 超时 / 重新发起归属（B1.7）**：同一 `payment_attempt_id` 的重试沿用原快照；超时作废或重新发起生成**新 `payment_attempt_id`**，按新业务实时策略重新授权。
- **三类操作状态转换（明确）**：

  | 操作 | 读取 | 行为 |
  |---|---|---|
  | 新下单 / 新抵扣 / 新支付尝试（apply-points / apply-coupon / 充值 / 下单 / 重试重新发起） | 实时策略 | `disabled` 即拒绝（无副作用） |
  | 支付通知 / 在途结算（mock / 微信通知 / 储值全额，同一 `payment_attempt_id`） | `asset_policy_snapshot` | 按快照完成，不因实时开关关闭而中断 |
  | 退款 / 对账补偿 | `asset_policy_snapshot` | 不禁用，按快照原路补偿 |

- 资产策略**写入 `payment_attempt.payment_snapshot_json`**（**B3.1：`order.payment` 仅保存引用与展示缓存，不再承载策略快照事实**；快照内 `payment_attempt_id + policy_version + asset_policy_snapshot`），区分三态：`拒绝新业务` / `完成在途结算` / `退款对账补偿`。**不能用单一布尔开关阻断退款与对账补偿**。
- **持久 `payment_attempt` 表（B1.8 + B1.9 + B2.0 + B3）**：`payment.json` 可被覆盖，不能承载不可变支付尝试事实。新增 `payment_attempt` 表（v025+ 迁移），每行一次支付尝试，字段：`payment_attempt_id`（主键）、**`subject_type + subject_id`（`order` / `recharge` 等聚合类型与实例 ID）**、`provider`（`wechat` / `balance` / `mock`）、**`merchant_order_no`（微信 `out_trade_no`；仅 `provider=wechat` 强制 `UNIQUE NOT NULL` 且不可复用）**、`amount_fen`、**`payment_snapshot_json`（完整不可变支付快照——各资产分摊 / 券周期 / 币种 / 策略版本与快照 / 金额；**B2.0：写入后不可修改，任何变更只能新增新尝试**）**、**`snapshot_hash`（B2.0：规范化快照哈希——对 `payment_snapshot_json` 做规范化序列化后取 sha256，供一致性核验）**、`status`、**`provider_transaction_id`（微信 transaction_id，异步回填；B2.0：`UNIQUE(provider, provider_transaction_id)` 防跨尝试串单）**、**`active_command_type / lease_token / lease_until / state_version / prepay_started_at`（B3.3：支付命令租约字段，`prepay_requested` 崩溃恢复 / 超时转移，见 ADR 0008 D1-A）**、`created_at / updated_at`。**（B3.2 删除独立 `policy_version` / `asset_policy_snapshot` 列：策略固化事实（`payment_attempt_id + policy_version + asset_policy_snapshot`）唯一存于 `payment_snapshot_json` 内，不再双存；如需列投影由快照 JSON 派生并做一致性校验）**。
- **资金腿与预占持久化（B3 + B3.1 账户绑定）**：新增 **`payment_attempt_leg`**（每腿金额与 `payment_snapshot_json` 分摊一致，`UNIQUE(payment_attempt_id, asset_type)`，状态 `reserved / consumed / released`）与 **`account_hold`**（余额 / 积分持久预占，`hold_key UNIQUE`、**`member_balance_id`（B3.1 不可变账户主键，绑定具体余额 / 积分账户行，`hold_key` 含账户维度，如 `hold:<payment_attempt_id>:<asset_type>:<member_balance_id>`，杜绝跨账户串占）**、`asset_type`、`status active / consumed / released / expired`、`expires_at`）。**可用余额公式（唯一口径，按账户行计算）**：`available_balance_fen = member_balance.stored_value_fen - SUM(account_hold.amount_fen WHERE account_hold.member_balance_id = member_balance.id AND asset_type='balance' AND status='active')`，积分同构。首次不可逆承诺点**必须先持久化预占再进入微信等待 / 结算**；微信等待期间（`prepay_*`）余额 / 积分不得被其他尝试重复预占；**仅 `failed / expired / cancelled` 终态允许释放，`settling` 与等待期禁止释放**（防微信已扣款而本地已释放）；**`cancelled`（B3.1 关单成功终态）允许释放；`manual_review`（B3.1 处置态）期间保持占用，裁决后才释放 / 消费**。券预占沿用 `coupon_current_state RESERVED`，不重复建 hold。
- **`order.payment` 降级为引用 / 展示缓存（B3，评审问题 1）**：`order.payment`（payment.json）不再承载账务裁决事实，仅保留 `payment_attempt_id` 引用与展示快照；结算、分摊、预占、退款额度初始化、回调校验一律以 `payment_attempt.payment_snapshot_json` 为唯一账务事实；不一致时以快照为准并提示对账。**订单 / 充值 / 余额 / mock 必须经统一支付应用服务入口进入 `payment_attempt → payment_attempt_leg + account_hold → ledger_operation → accounting_outbox` 模型**（B3），禁止各路径自行拼接账务写入。
- **支付尝试状态机（B2.0 完整定义 + B3 补调度 + B3.1 补状态）**：`draft → prepay_requested → prepay_unknown / prepay_ready → settling → succeeded / failed / expired / cancelled`（含 **`manual_review`** 处置态）——创建为 `draft`；发起微信预下单写 `prepay_requested`（**B3.3：带命令租约 `active_command_type / lease_token / lease_until / state_version / prepay_started_at`，请求发出后崩溃由调度租约接管、CAS 转 `prepay_unknown` 后再查询 / 关单**）；预下单响应未知 `prepay_unknown`（**B3 + B3.1 固定映射：由独立调度任务按退避经 outbox 发起 `wechat_order_query` 并 CAS 推进，与关单互斥、lease_token 防陈旧回写——查询 `SUCCESS` → `settling`；`NOTPAY` → 先关单确认再 `cancelled / expired` 终态释放；`CLOSED / REVOKED / PAYERROR` → 终态释放；未知 → 保持占用退避查询至上限转 `manual_review`；`prepay_unknown` 不产生 `prepay_ready`（prepay_id 丢失不可恢复），支付会话禁止写回不可变快照；**用户侧重试由调度先推进原尝试至确认终态（查询-关单路径）或 `manual_review`（保持占用），终态确认后才允许新建尝试（B3.2）**）、就绪 `prepay_ready`（**仅已持久化可用会话**）；回调 / 余额扣款开始结算置 `settling`；**仅 `succeeded` 对同一交易号回调幂等 ACK；`settling` 必须可恢复（进程重启后按快照继续）且不能提前确认成功**；`failed / expired / cancelled` 为终态永久失效；**`manual_review`（B3.1）为人工处置态——未解除前禁止同主体创建新支付尝试，holds 保持占用**。
- **结算分派（B1.9）**：订单（微信差额 / 余额 / mock）、充值（微信 / mock 确认）按 `subject_type` 分派到对应结算路径，均以 `payment_attempt` 状态机推进并**与账务写入同一 UoW** 结算；充值真实回调按 `subject_type=recharge + merchant_order_no` 归属，避免真实回调无归属。
- **唯一活跃尝试（B1.9 + B3.1 补 `manual_review`）**：每个 `(subject_type, subject_id)` 至多一个活跃尝试——新尝试以条件更新创建（`WHERE 不存在 status ∈ {draft, prepay_requested, prepay_unknown, prepay_ready, settling, manual_review} 的同主体尝试`——**`manual_review` 未解除前禁止同主体创建新支付尝试，B3.1**），冲突即拒绝；**重复通知仅对 `succeeded` 同交易号幂等 ACK**（不重复结算）；**冲突或过期尝试进入对账**，不静默覆盖。**（B3.2 支付状态命令表）旧尝试确认终态（`failed / expired / cancelled`）前不得新建尝试；`prepay_*` 仅关单成功后释放；仅 `succeeded` 才能创建退款聚合**（完整命令表见 ADR 0008 D1-A）。
- **回调结算校验（B1.8 + B2.0 + B3）**：微信支付通知回调**先按 `out_trade_no`（= `merchant_order_no`）查 `payment_attempt`**；**固定校验清单（B3）**：① 验签上下文（`Wechatpay-Signature` RSA-SHA256、`Wechatpay-Timestamp`、`Wechatpay-Nonce`、`Wechatpay-Serial` 按证书序列号取平台证书验签）；② `mchid`；③ `appid`；④ 交易成功状态 `trade_state=SUCCESS`；⑤ 金额 `amount.total` 与币种 `currency=CNY`（**B3.3：微信 v3 通知 resource 币种字段统一为 `amount.currency`，v2 旧称币种字段不再使用**）；⑥ 商户单号；⑦ 交易号 `transaction_id`。**只校验微信实际提供的字段，其中金额 `amount.total`、币种 `currency=CNY`、商户单号 `out_trade_no` 必须与不可变快照微信腿（`payment_snapshot_json` 中 `asset_type='wechat'` 的 `amount_fen`）一致（B3.2：快照微信腿是回调校验的唯一本地参照，不依赖 `order.payment` / 可变列）**；**先持久化到 `payment_provider_event`（唯一 `event_key` 幂等）再处理，处理成功后才返回 ACK，失败返回 5xx 由微信重试（B3，禁止先 ACK 后持久化）**；校验通过后置 `settling` 并按该尝试快照内的 `asset_policy_snapshot` 结算；尝试不存在、已终态、交易号已绑定其他尝试（`UNIQUE(provider, provider_transaction_id)` 冲突）或任一校验不匹配 → 拒绝结算并进入对账。
- **尝试失效（B1.8）**：超时或替代尝试发起后，原尝试置 `failed / expired` 终态**永久失效**；**禁止复用 `merchant_order_no`（`out_trade_no`）**——新尝试必须生成新的商户单号，杜绝迟到支付通知按新快照结算旧尝试。
- **资金腿原子合同（B2.0）**：余额扣减、积分扣减 / 发放、券核销、流水写入与 `accounting_outbox` 投递占位在同一 UoW 内，以 **`ledger_operation`（`operation_key UNIQUE` 幂等占位）** 先行落位，随后执行余额 / 积分变更与流水，全部成功才提交；`operation_key` 覆盖重复通知 / 重试，禁止"先改余额后写流水"或"先查后改"的非原子模式（见 ADR 0008 D1-A）。
- 开发 / 测试 / mock 阶段保持 `enabled`；进入受控真实测试或正式上线前，由项目负责人裁决逐项切换并留证。

## 积分门禁（B1.6 已裁决：关闭 Platform 积分写操作）

`POINTS_AUTHORITY=youzan` 下，Webhook 用有赞总积分覆盖本地余额，而小程序订单直接在本地扣分/发分/退款，且无有赞积分写接口——新旧入口并存会产生积分双花与延迟事件覆盖。正式开放前必须定稿防双花方案。

**裁决（项目负责人，B1.6）**：采用**关闭 Platform 积分写操作**——正式开放前 `ASSET_POINTS_WRITE=disabled`，小程序积分抵扣 / 发放 / 退款关闭，仅只读展示。无需有赞侧协调，风险最低；后续如需开放积分写，须重新走 FP-4B2 门禁裁决。

- 否决项：有赞幂等写入 + outbox/回查补偿（依赖真实有赞积分写接口与对账能力，实现最重）；关闭旧入口积分能力（需有赞运营协调停用，外部依赖不确定）。
- Webhook 镜像不视为同步方案（有覆盖延迟，不能保证一致）。

## 券双端门禁（B1.6 已裁决：关闭旧入口券能力 + 正式版关闭券抵扣）

**裁决（项目负责人，B1.6）**：**关闭旧入口券能力**（与有赞运营协调停用有赞券核销 / 发放入口）+ **正式版关闭券抵扣**（`ASSET_COUPON_WRITE=disabled`；真实券测试前做跨端双花检查，通过后再开放）。券数据模型以 ADR 0008 为唯一来源。

## 验收（实施阶段）

- 服务端资产开关生效：每个受控写操作在 `disabled` 时被拒绝（含直接 API 调用绕过测试）；支付快照三态（拒绝新业务 / 完成在途结算 / 退款对账补偿）测试通过，退款与补偿不被开关阻断。
- **承诺点固化测试（B1.7）**：余额预占 / 券 `RESERVE` / 微信支付会话任一创建后开关关闭，`payment_attempt_id` 按快照完成结算；同一 `payment_attempt_id` 重试沿用快照；超时重新发起生成新 `payment_attempt_id` 且按实时策略重新授权。
- **payment_attempt 校验（B1.8 + B2.0 + B3 + B3.1）**：`subject_type + subject_id` 主体模型，`provider=wechat` 时 `out_trade_no` 一对一不可复用（复用被唯一键拒绝）；完整状态机 `draft → prepay_requested → prepay_unknown/prepay_ready → settling → succeeded/failed/expired/cancelled` 测试通过（含 `settling` 重启恢复、仅 `succeeded` 同交易号幂等 ACK、**`cancelled` 关单成功终态、`manual_review` 未解除前同主体新尝试被拒**）；`UNIQUE(provider, provider_transaction_id)` 防串单；回调只校验微信实际字段（金额 / 币种 / 商户单号 / 交易号）；快照写入后不可修改；`ledger_operation` 幂等占位 + 余额变更 + 流水 + outbox 同一 UoW（无"先改后写"非原子模式）；充值 / 订单 / 余额 / mock 结算分派与同一 UoW 行为有测试；**（B3）`payment_attempt_leg` / `account_hold` 持久预占与可用余额公式（微信等待期间并发预占被拒、结算成功消费与 ledger 同 UoW、`settling` 与等待期禁止释放）、`order.payment` 与不可变快照不一致以快照为准、统一支付应用服务入口覆盖订单 / 充值 / 余额 / mock、`payment_provider_event` 先持久化再 ACK 与验签 / mchid / appid / trade_state 固定校验**。
- 支付成功联动点统一读取开关 / 快照：**新业务禁写不产生资产副作用；在途结算与退款补偿按 `asset_policy_snapshot` 完成，不因实时开关关闭而中断**（覆盖"支付通知到达前关闭开关"场景）。
- **（B3.1）账户绑定 / 租约 / 映射验收**：`account_hold` 绑定 `member_balance_id`（可用额按账户行计算、跨账户不串占）；`payment_provider_event` 租约 CAS（仅 `processed` 后重复通知 200，落库后崩溃重领不丢不重）；`prepay_unknown` 固定映射（已支付→`settling` / 未支付先关单再终态释放 / 未知保持占用退避至 `manual_review`；不产生 `prepay_ready`；支付会话不写回不可变快照）；唯一事实 D1-0 逐端点迁移核对与"历史待处理为 0"证据。
- **FP-4B2 门禁（B1.6 补强，不能以"矩阵文档存在"代替验收）**：正式开放前必须归档——
  1. 已选积分策略证据：`ASSET_POINTS_WRITE=disabled` 的配置与 `disabled` 时写操作拒绝的运行证据；
  2. 已选券策略证据：有赞侧停用旧入口券能力的确认 + `ASSET_COUPON_WRITE=disabled` 的配置与拒绝证据；
  3. 旧有赞小程序无储值 / 积分 / 券写能力的**外部核验证据**（旧小程序能力清单 / 有赞后台配置确认），并登记证据索引；
  4. **FP-2 不可逆边界审批项（B1.7）**：本地首次写入后仅 roll-forward 不回写有赞的风险列为正式放行的显式审批项。
