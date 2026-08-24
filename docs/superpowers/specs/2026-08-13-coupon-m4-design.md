# M4 优惠券模块设计

- 状态：**归档资料，禁止执行（2026-08-15 B3.3 标注）**——本设计与实施计划不再作为任何券实现 / 退款实现的依据，仅保留作历史追溯；**第一阶段历史实现（已交付，2026-08-14 B1.6 复核标注）**；后续券数据模型以 [ADR 0008](../../harness-engineering/adr/0008-accounting-core-consistency.md) 的 `coupon_events.transition_key` + `origin_event_id` + `coupon_current_state` 投影（`RESERVED` 预占 / 投影 CAS）为唯一来源（**B3.3：券写入语义唯一源 = ADR 0008 D1-B；退款口径唯一源 = ADR 0008 D1-C（全额 + 部分净额退款、差分分摊、`refund_shortfall_debt` 持久短缺债务）**），本设计中的 `(coupon_id, status, mobile)` 唯一键与来源权重规则**禁止用于新实现**。
- trace_id：`20260813-coupon-m4`
- 来源：计划书 `docs/specs/2026-08-12-member-loyalty-storedvalue-plan.md`（M4 优惠券模块）；brainstorming 与用户确认；v2 按用户 5 点修订 + 2 项补充修订
- 前置：M1 数据底座（`coupon_inventory` 生命周期记录 + 全量导入 + COUPON 事件增量）、M2 储值闭环、M3 积分闭环

## 目标

在 M1 优惠券库存底座之上，交付优惠券模块闭环：券模板统一建模、本地核销引擎（订单结算抵扣）、支付/退款联动、小程序券 API、管理后台模板管理与查询。数据主从 `COUPON_AUTHORITY` 默认 `youzan`（有赞发券，本地镜像 + 本地核销），预留 `local` 模式与后续运营能力（定向发券、数据看板）演进。

## 范围与边界

**范围内**
- 券类型：满减券（满 X 减 Y）、无门槛代金券、折扣券（含优惠上限）。
- 结算抵扣核销：选券 → 写支付快照 → 支付成功核销 → 退款退回。
- 抵扣叠加：`remain_fen = total_fen - coupon_fen - balance_fen - points_fen`（唯一公式，全部支付路径复用）。
- 小程序 API：我的券列表、结算选券预览、应用券。
- 管理后台：券模板 CRUD/启停、发券记录/核销记录/库存查询、local 模式发券。
- 数据主从开关 `COUPON_AUTHORITY`（youzan/local），与 `POINTS_AUTHORITY` 同构。
- **M3 同步修改**：`redeem_units`/发分公式/快照合并纳入本里程碑（见"支付联动"）。

**范围外（本期不做）**
- 商家扫码/到店核销（用户已确认无此场景）。
- 商品维度可用性校验：券模板保留适用商品/分类字段（`scope_json`），有赞同步时填充，但 M4 结算校验只做金额维度。
- 定向发券、数据看板（向 C 演进，本期只预留字段与扩展位）。
- 部分退款（沿用全单退款语义，与 M3 一致）。**（B3.3 归档标注：此为本阶段历史范围；退款政策以 ADR 0008 D1-C 定稿为准——支持全额与部分退款、净额口径、差分分摊，本行不构成对 D1-C 的修改）**

## 业务规则

### 券实例状态模型（v2 修订 1：保持 M1 生命周期多行语义）

`coupon_inventory` 保持 M1 的**生命周期多行**模型（唯一索引 `coupon_id + status + mobile`，状态流转写多行，符合生命周期记录语义）。**禁止** `UPDATE ... SET status='CONSUME'` 单行当前态写法。

> **B1.6 + B1.7 复核标注（B3.3 归档修正）**：以上是第一阶段历史实现。第二阶段券数据模型以 ADR 0008 为唯一来源：事件表 `coupon_events`（`transition_key` 不含来源的逻辑键 + `origin_event_id` 外部事件幂等 + `ingest_source` 摄取来源）+ 当前态投影 `coupon_current_state`（`RESERVED` 预占 + 投影版本 CAS，防止双订单并发预占同一券）；旧唯一键 `(coupon_id, status, mobile)` 标为"第一阶段现状，禁止用于新实现"。来源权重排序（`SOURCE_PRIORITY`）随旧模型一并停用；新模型事件新旧判定按事件版本合同（`event_version` / `ordering_kind` / `payload_hash`），**禁止以 `(occurred_at, id)` 承担因果**（仅作同源展示序；原"新模型按 `(occurred_at, id)` 单调排序"表述已删除，B3.3）。

- 核销 = 在**事务内**先读取该券最新状态行，校验最新态为 `TAKE` 且未过期，再**插入**一条 `source='order'` 的 `CONSUME` 行。
- 最新态判定（v3 修订：来源优先级 + 时间）：`get_latest_state` 先按**来源权重**排序，再按时间排序：
  - `youzan` 模式：`order/local` 权重高于 `webhook/import`，同权重内按 `(occurred_at, created_at, id)` 降序取首行。有赞 `BACK` 审计行时间再晚也不得覆盖本地 `CONSUME`/`TAKE`（order/local 行）。
  - `local` 模式：只查询 `order/local` 来源行判定可用/核销，`webhook/import` 审计行完全不参与。
- 来源权重常量集中定义（如 `SOURCE_PRIORITY = {"order": 2, "local": 2, "webhook": 1, "import": 1}`），禁止散落魔法值。
- 并发防重：核销事务以 `BEGIN IMMEDIATE` 串行化（SQLite 写串行），"读最新态 → 插入"原子完成；service 层幂等键 `coupon:consume:<order_id>` 二次兜底；唯一索引 `(coupon_id, status, mobile)` 保证同券同状态只有一行（**第一阶段现状，第二阶段以 ADR 0008 `coupon_events.transition_key` + 投影 CAS / `RESERVED` 预占为准**）。
- 去重键语义不变：`(coupon_id, status, mobile)` 组合去重（第一阶段现状，禁止用于新实现）。

### 券类型与抵扣计算（`rules.py` 纯函数）

| 类型 | 可用条件 | 抵扣金额 |
|---|---|---|
| FULL_REDUCTION 满减 | `total_fen >= threshold_fen` | `min(value_fen, total_fen)` |
| NO_THRESHOLD 无门槛 | 无门槛 | `min(value_fen, total_fen)` |
| DISCOUNT 折扣 | 无门槛 | `min(total_fen * (10000 - discount_bp) // 10000, cap_fen or 无穷, total_fen)`，至少 1 分 |

- 券自身有效期（`valid_from/valid_until`）内且最新态为 `TAKE` 才可用；过期券不参与可用列表。
- 抵扣不能超过订单应付，且与储值、积分叠加后 `remain_fen >= 0`。

### 叠加约束（v2 修订 3：M3 同步修改）

- 应用券（apply-coupon）与应用积分（apply-points）**顺序不敏感**：两次写入统一合并进同一支付快照，任何一方都读取对方已写入的字段参与校验，**不得互相覆盖**。
- 唯一剩余应付公式：`remain_fen = max(0, total_fen - coupon_fen - balance_fen - points_fen)`。
- 积分抵扣上限（M3 规则同步收窄）：`points_fen <= 50% * total_fen`，且 `points_fen <= total_fen - coupon_fen - balance_fen`。
- M3 同步改动：
  - `app/service/points/rules.py:redeem_units(available_points, total_fen, balance_fen, coupon_fen=0)`：`cap_fen = max(0, total_fen - balance_fen - coupon_fen)`。
  - `app/service/points/payment.py` 发分公式：`cash_fen = max(0, total_fen - coupon_fen - balance_fen - points_fen)`（原 `total - balance - points` 再减券）。
  - `build_points_payment` 与 `build_combined_payment` 统一合并快照：同一 `payment.json` 内共存 `couponFen/couponId/pointsFen/pointsUsed/balanceFen/remainFen`。

### 幂等与并发

- 幂等键：`coupon:consume:<order_id>`、`coupon:refund:<order_id>`（与积分 `points:*` 幂等键同构）。
- 核销并发：`BEGIN IMMEDIATE` 事务内"读最新态=TAKE → 插入 CONSUME 行"，唯一索引兜底；重复支付/重复通知只核销一次。
- 取消语义（v2 补充 2）：**apply-coupon 后未支付就取消/超时，只清支付快照**（`couponFen/couponId` 归零），**不写 `BACK` 行**；`BACK` 只发生在已支付后的全单退款。

### 数据主从与事件优先级（v2 修订 5：写死）

> 风险等级（2026-08-14 双阶段裁决）：**开发阶段中风险**——正式小程序尚未开放、无真实用户，券双端核销不一致不直接影响真实用户；**真实券测试与正式上线前为硬门禁**——开放券抵扣前必须解决双端同步、停用有赞入口或关闭本地券抵扣，任一未满足不得开放券抵扣。

- `COUPON_AUTHORITY=youzan`：**本地核销引擎是当前态权威**。有赞 `COUPON_CUSTOMER_PROMOTION` 事件只按去重键**补缺失**的生命周期行（`source='webhook'`），**不得覆盖/降级本地状态**：
  - 本地核销已写 `order` 来源 CONSUME 行后，有赞 CONSUME 事件去重键 `(coupon_id, CONSUME, mobile)` 命中 → 跳过。
  - 有赞 BACK 事件：本地最新态为 CONSUME 时，插入 `webhook` 来源 BACK 行仅作审计；本地最新态为 TAKE 时按去重键插入（有赞侧退回）。
  - 有赞 TAKE 事件：去重键未命中则插入（首次领取）。
- `COUPON_AUTHORITY=local`：有赞券事件**只审计**（写 `webhook` 行或日志，不参与本地可用券/核销判定）；本地发券（`coupon_grants` + `source='local'` 行）与本地核销引擎为唯一权威。
- 调有赞核销 API 封装为可选调用、默认 mock 短路（真实店铺 API 契约验证后再启用，沿用 M1 待办）。

## 数据模型（v024 迁移，参考 v023 重建模式）

### 重建 `coupon_inventory`（v2 修订 1+2）

SQLite 重建表以扩展 CHECK 与列（沿用 `points_ledger_new` → DROP → RENAME 模式，数据全量搬迁）：

新增列：`template_id`、`valid_from`、`valid_until`、`deducted_fen`（核销抵扣金额）、`consumed_at`、`refunded_at`。

`source` 枚举扩展：`CHECK(source IN ('webhook', 'import', 'local', 'order'))`；`app/models/member.py` 的 `LedgerSource` 已有 `WEBHOOK/IMPORT/ORDER`（v023 已加 `ORDER`），本期**新增 `LOCAL = "local"`**。核销/退回行统一用 `LedgerSource.ORDER` 常量、本地发券行用 `LedgerSource.LOCAL`，**禁止魔法字符串**。

保留：唯一索引 `idx_coupon_inventory_dedup ON (coupon_id, status, mobile)`、`idx_coupon_inventory_mobile ON (mobile)`；新增 `idx_coupon_inventory_order ON (order_no)`、`idx_coupon_inventory_latest ON (coupon_id, mobile, occurred_at)`。

### 新增 `coupon_templates`（券模板）

| 字段 | 说明 |
|---|---|
| `id` | 主键（youzan 用 coupon_group_id，local 用 uuid） |
| `name` | 券名称 |
| `coupon_type` | FULL_REDUCTION / NO_THRESHOLD / DISCOUNT |
| `threshold_fen` | 满减门槛（无门槛=0） |
| `value_fen` | 面额（折扣券=0） |
| `discount_bp` | 折扣万分比（如 9000=9 折；非折扣券=0） |
| `cap_fen` | 折扣优惠上限（0=不限） |
| `valid_from` / `valid_until` | 模板有效期 |
| `scope_json` | 适用商品/分类（预留，默认 `{}` 全场，暂不参与结算校验） |
| `status` | active / disabled |
| `source` | youzan / local |
| `created_at` / `updated_at` | 时间戳 |

### 新增 `coupon_grants`（发券记录，local 模式）

| 字段 | 说明 |
|---|---|
| `id` | 主键 |
| `template_id` | 关联模板 |
| `customer_id` / `mobile` | 领券人 |
| `coupon_code` | 券码（local 发券生成） |
| `granted_by` | 操作人（admin 账号或 system） |
| `channel` | 发券渠道（预留：admin/batch/auto） |
| `audience_json` | 人群/标签（预留 C 定向发券） |
| `status` | granted / revoked |
| `created_at` | 时间戳 |

### 模板字段回填（v2 补充 1）

- 全量导入（`member_loyalty.py`）与 Webhook 反查（`member_api.get_coupon_group_detail`）统一解析券详情：`coupon_type/threshold_fen/value_fen/discount_bp/cap_fen/valid_from/valid_until/name/scope_json` → **upsert `coupon_templates`**（youzan 来源）→ 写 `coupon_inventory` 时回填 `template_id/valid_from/valid_until`，避免新列长期为空。
- 抽取公共解析函数（如 `app/service/coupon/template_sync.py`），导入与事件两处复用。

## 分层设计

```
api/ → service/coupon/ → repository/ → models/
```

- `app/models/coupon.py`：`CouponTemplate`、`CouponGrant`（`CouponInventoryEntry` 留在 `member.py` 扩展字段）。
- `app/repository/coupon_template_repo.py`：模板 CRUD、`upsert_from_youzan`、`list_active`。
- `app/repository/coupon_inventory_repo.py` 扩展：`list_by_mobile`（含状态/有效期筛选）、`get_latest_state`（按来源权重+时间取最新态，youzan/local 两套口径）、`consume`（事务内读最新态+插入）、`refund`（插入 BACK 行）、`list_by_order`。
- `app/repository/coupon_grant_repo.py`：`insert`、`list_by_mobile`、`revoke`。
- `app/service/coupon/rules.py`：纯函数（可用性、抵扣计算、叠加校验、最新态判断）。
- `app/service/coupon/inventory.py`：券账本（核销/退回，幂等键，事务边界）。
- `app/service/coupon/payment.py`：`build_coupon_payment` 快照合并、`consume_on_payment`、`refund_coupon`、`clear_coupon_snapshot`（未支付取消只清快照）。
- `app/service/coupon/grants.py`：local 发券/回收。
- `app/service/coupon/__init__.py`：`CouponService` 门面（`get_my_coupons` / `redeem_preview` / `apply_coupon` / `clear_applied`）。
- `app/service/order/payment_state.py`：新增统一 `compute_remain_fen(total, coupon, balance, points)` 纯函数，快照合并逻辑改造。

## 支付联动（v2 修订 3+4：唯一金额公式，M3 同步改）

- **唯一剩余应付公式**：`remain_fen = compute_remain_fen(total_fen, coupon_fen, balance_fen, points_fen)`，定义在 `payment_state.py`，以下全部复用：
  - mock 支付建单金额：`remain_fen`。
  - 微信 JSAPI 建单金额：`remain_fen`（原 `order.total_amount`，见 `payment_runtime.py`）。
  - 微信通知金额校验 `expected_fen`：`remain_fen`（原 `total_amount`，见 `payment_notification.py`）。
  - 储值全额余额支付（`stored_value/payment.py`）：按 `remain_fen` 扣减（原 `total_fen`）。
  - `prepare_combined_payment`：`remain_fen = total - coupon - balance - points`（原 `total - balance`）。
- 结算选券 `build_coupon_payment`：写快照 `couponFen/couponId`（与 points 快照合并，顺序不敏感）。
- 三条支付成功路径（mock、微信通知、储值全额）统一调 `consume_on_payment`：按快照核销券；非会员/无券订单自动跳过。
- 取消/超时/后台取消：**未支付**只清快照（不写 BACK）；**已支付全单退款**调 `refund_coupon` 写 BACK（幂等键防重）。
- M3 同步：`redeem_units` 加 `coupon_fen` 参数、发分公式减券、快照合并（见"叠加约束"）。

## 小程序 API（3 端点，prefix `/api/v1/miniapp`）

| 端点 | 说明 |
|---|---|
| `GET /coupons` | 我的券列表（按状态/有效期筛选，最新态口径） |
| `POST /orders/{order_id}/coupon-preview` | 结算选券预览（可用券 + 每张可减金额 + 与积分/储值叠加校验结果） |
| `POST /orders/{order_id}/apply-coupon` | 应用券（合并写快照，支付成功才核销） |

鉴权沿用 `authenticate_storefront_request` + `x-miniapp-user-id`，错误语义与积分 API 一致（ValueError → 400）。

## 管理后台

- `app/api/admin/coupons.py`：
  - 券模板：列表 / 新建 / 编辑 / 启停（`coupon_authority=local` 时后台创建模板并发券）。
  - 查询：发券记录、核销记录、券库存明细（按状态/模板/手机号筛选）。
  - `local` 发券：按手机号发放指定模板券，生成 `coupon_code` 写 `coupon_grants` 并落 `coupon_inventory`（`source='local'`）。
- `web/admin/src/pages/coupons/`：`CouponsPage.vue`（模板管理 + 记录查询 + local 发券入口），沿用现有 admin 页面模式（API service + Element Plus）。

## 演进预留（向 C 转）

- 模板表已含 `scope_json`、渠道/人群字段（`coupon_grants.channel/audience_json`），定向发券可直接扩展发券表单与 API 参数。
- 核销记录含 `deducted_fen/consumed_at/order_no`，数据看板可直接聚合（领券数/核销数/核销率/优惠金额）。

## 测试验收

1. `rules.py`：三类券可用性（门槛/有效期/上限）与抵扣金额边界（含超应付、折扣取整、上限封顶）。
2. 状态模型：核销=插入 CONSUME 行且最新态校验；同券并发核销只有一个成功（BEGIN IMMEDIATE + 唯一索引 + 幂等键）。
3. 最新态来源优先级：有赞 BACK 审计行时间晚于本地 CONSUME 时不降级；local 模式审计行不参与判定。
3. 叠加约束：券+储值+积分不超应付；`redeem_units` 加 `coupon_fen` 后积分上限正确收窄；发分公式减券后 `cash_fen` 正确。
4. 快照合并：apply-coupon 与 apply-points 顺序不敏感，最终快照字段共存不互相覆盖。
5. 唯一金额公式：mock/微信/储值三条路径与微信通知金额校验全部按 `remain_fen`（含券/储值/积分组合场景）。
6. 支付联动：三条成功路径核销券；未支付取消只清快照不写 BACK；已支付全单退款写 BACK；非会员无券订单跳过。
7. 事件优先级：youzan 模式下本地核销后事件不降级/不冲突（去重键命中跳过）；local 模式事件只审计。
8. 模板回填：导入与 Webhook 均 upsert 模板并回填 `template_id/valid_from/valid_until`。
9. 小程序 API：列表/预览/应用三端点鉴权与错误语义；lifespan 装配契约测试同步更新。
10. 管理后台：模板 CRUD/启停、发券记录、核销记录、local 发券。
11. 全套回归：新增测试 + `tests/` 全套 + `check_project --skip-tests` + `check_file_sizes` + `ruff check` + `ruff format --check` + 门禁全绿。

## 收口

- 本地验证全绿后按 M6 模式生产部署：第一阶段 `COUPON_AUTHORITY=youzan` 已上线（v0.131.2，见 LOGBOOK / E-20260813-002）；第二段切 `local` 由 FP-2 执行，须满足 2027-06 候选窗口、项目负责人批准、唯一键阻断解除与独立切换窗口门禁，禁止仅修改进程级配置触发。
- LOGBOOK / 项目进度清单 / 执行计划（writing-plans）收口，证据归档按 harness 规范。
