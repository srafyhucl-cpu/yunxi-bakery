# 会员储值/积分/优惠券账务域可执行计划书

- 状态：核心主链路及 Platform 第一阶段部署完成；完整闭环仍需工程实现、外部资质与生产验收，拆分至后续工作包（2026-08-14 评审结项 + 深度复核修正）
- trace_id：`20260812-member-loyalty-storedvalue`
- 上线边界：截至 2027-05-31（含）仅开发 / 调试 / 测试；2027-06 只是最早候选上线窗口，必须经项目负责人明确批准后才可开放真实用户
- 来源：迁移前功能补齐盘点（**历史基线**，2026-08-12 前）。当时"我的"页面会员卡数据为静态假数据（`shop_page_config.py` 中 balanceFen=0, points=0, coupons=0），无真实账务域；M2/M3/M4/M5 交付后该现状已改变。
- 前置依赖：微信支付商户号（阻塞，先 mock 跑通）
- 消息推送：✅ 已订阅
- 数据策略：全量导入打底 + Webhook 增量维持（同 openid 预导入模式）

## 目标

目标态：实现会员储值余额、积分、优惠券完整闭环。当前商户号到位后仍需支付/退款工程实现（FP-3）与生产验收，并完成数据导入（FP-1）、正式发布（FP-4）与权威切换（FP-2），并非仅切换一行配置。

## 项目级上线前提

- 截至 **2027 年 5 月 31 日（含）**，小程序不面向真实用户，仅允许开发、调试、自动化测试、体验版验证和授权测试人员操作。
- **2027 年 6 月为最早候选上线窗口**。即使全部工作包完成，也必须由项目负责人明确批准后，才能开放真实用户访问；不得把计划日期视为自动上线日期。
- 截至 **2026 年 8 月 14 日**，项目不具备受控真实微信支付 / 退款及真实有赞券测试条件。未来条件具备后，只允许经单独批准的授权测试账号开展小额、可退款、可对账、可清理的受控真实测试。
- 生产部署、接口探针、真实登录、体验版、审核通过和受控真实测试均属于上线准备证据，不代表已经正式对真实用户运营。

---

## 已订阅事件

| 事件 | msg 核心字段 | 写入目标 |
|------|-------------|---------|
| SCRM_CUSTOMER_EVENT | mobile, name, is_member, status(CREATED/UPDATED) | 客户身份更新 |
| POINTS | amount, total, event_type, yz_open_id, mobile, unique_id | `points_ledger` |
| COUPON_CUSTOMER_PROMOTION | id, status(TAKE/CONSUME/BACK), mobile, coupon_group_id, order_no | `coupon_inventory`（反查券详情补全） |
| SCRM_CUSTOMER_CARD | card_alias, card_no, mobile, yz_open_id, status | 会员卡状态 |

---

## 结项状态（2026-08-14 评审）

| 里程碑 | 状态 | 说明 |
|------|------|------|
| M1 数据底座 | 🟡 第一阶段完成 | 代码、迁移、生产部署完成；生产全量导入与真实店铺 Webhook 契约联调待执行（FP-1） |
| M2 储值余额 | 🟡 第一阶段完成 | mock / 余额支付 / 组合支付 / API 已上线；真实微信支付待商户号（FP-3） |
| M3 积分模块 | 🟡 第一阶段完成 | POINTS_AUTHORITY=youzan 已上线；local 权威第二阶段计划 2027-06（FP-2） |
| M4 优惠券模块 | 🟡 第一阶段完成 | 核心功能已上线（COUPON_AUTHORITY=youzan）；local 切换及真实有赞发券链路未闭环（FP-2 / FP-1）；第二阶段券数据模型以 ADR 0008 为准 |
| M5 小程序前端 | 🟡 开发完成、发布未完成 | 页面与自动化验证完成；真机、体验版、正式审核、真实支付未完成（FP-4） |
| M6 收口部署 | 🟡 部分完成 | Platform 第一阶段部署完成；M3/M4 生产部署证据已归档（E-20260813-001/002），不代表真实业务闭环，业务闭环仍受上述事项约束 |

状态枚举：✅ 已完成 / 🟡 第一阶段完成 / 🔴 外部依赖阻塞 / ⛔ 已取消

## 双阶段裁决（2026-08-14）

> `058567e` 作为 **2027-05-31（含）前开发 / 调试 / 测试阶段规划基线有条件通过**；不代表真实支付验收、真实用户开放或本地权威切换方案已经通过。

- **高风险阻断项（切换前必须解除）**：FP-1 生产导入起止双水位与窗口回放（独立投影重建器，见 FP-1）；FP-2 local 切换模型（券唯一键冲突按 ADR 0008 `coupon_events.transition_key` 唯一模型 + `RESERVED` 预占 / 投影 CAS 解除）。
- **受控真实测试门禁**：授权测试账号、小额、可退款、可对账、可清理，事前获项目负责人批准。
- **正式上线门禁**：全部前置工作包完成 + 项目负责人明确批准，2027-06 不是自动上线日期。


## 里程碑

### M1：数据底座（3 天）🟡 第一阶段完成

| # | 任务 |
|---|------|
| 1.1 | `event_member.py`：解析四种事件 msg，按 type 分发处理 |
| 1.2 | `event_handler.py` 新增路由分支 |
| 1.3 | DB migration：`points_ledger`、`coupon_inventory`、`member_balance` |
| 1.4 | 全量导入 Service：调有赞 API 拉积分/优惠券/会员卡，幂等写入 |
| 1.5 | Webhook 增量写入（POINTS→ledger, COUPON→inventory 反查补全） |
| 1.6 | 本地全量验证 + 生产执行 + LOGBOOK 收口 |

### M2：储值余额（4 天）🟡 第一阶段完成

模型/仓储/充值Service/小程序API/储值支付+组合支付

### M3：积分模块（规则已确认，暂估 4–5 天）🟡 第一阶段完成

**业务规则（已确认）**

- 获得：`1 元实付 = 1 分`；实付现金 = `total_fen - coupon_fen - balance_fen - points_fen`（统一 `compute_remain_fen(total, coupon, balance, points)`）；不足 1 元向下取整，`award_points = cash_fen // 100`。
- 抵扣：`100 分 = 1 元`；单笔最低 `100 分`；最高抵扣 `50% × total_fen`，且 `points_fen <= total_fen - coupon_fen - balance_fen`；可用积分按百位向下取整，`points_used = floor(available / 100) × 100`。
- 发放时点：支付成功即发分；`apply-points` 只写快照，支付成功时才真正扣减抵扣积分。
- 叠加：`remain_fen = total_fen - coupon_fen - balance_fen - points_fen`（统一 `compute_remain_fen(total, coupon, balance, points)`）。
- 有效期：长期有效。
- 退款：支持**全额与部分退款**（B1.6 项目负责人裁决），基准为**净额退款**（B1.7 裁决：券折扣只影响可退商品金额、不生成货币退款操作）。全单退款退回全部 `pointsUsed`、收回全部 `pointsAwarded`；部分退款按 [ADR 0008](../harness-engineering/adr/0008-accounting-core-consistency.md) D1-C 分摊规则——`refund_fen` 在（微信款 / 余额 / 积分）间按实付占比分摊（最大余数法），积分按比例退回 `pointsUsed` / 收回 `pointsAwarded`，收回不足为 manual_review + **持久短缺债务（`refund_shortfall_debt`，债务化模型见 ADR 0008 D1-C，B3.3）**；跨微信退款采用 Saga 最终一致，微信已退本地未补偿进入人工复核。
- 数据主从：配置开关 `points_authority`（默认 `youzan`）两步切换——第一阶段 M3 上线保持 `youzan`（有赞 `total` 继续维护余额）；第二阶段切 `local`（本地 `member_balance.points` 权威，有赞 `POINTS` 事件只写流水/审计）由 FP-2 执行，须满足 2027-06 候选窗口、项目负责人批准、唯一键阻断解除与独立切换窗口门禁，禁止仅修改进程级配置触发。

**M3.1 数据/仓储**

- `v023`：`points_ledger.source` 扩为 `webhook/import/order`；新增 `biz_type`（`order_award/order_redeem/order_refund`）、`biz_id`；`total` 继续表示变动后余额，不新增 `balance_after`。
- `member_balance_repo`：新增 `get_points/credit_points/deduct_points_if_sufficient`（原子条件更新，参照储值同款）。
- `points_ledger_repo`：新增 `list_by_mobile`；`get_by_unique_id` 复用。
- `points_ledger` 模型：`PointsLedgerEntry` 增 `biz_type/biz_id`，`LedgerSource` 增 `ORDER = "order"`。
- `event_member._handle_points_event`：`points_authority=local` 时不再把有赞 `total` 写进 `member_balance.points`，只写 `points_ledger` 作为审计镜像；`youzan` 模式保持现状。

**M3.2 积分 Service**

- `app/service/points/rules.py`：纯函数 `award_points(cash_fen)`、`redeem_units(available, total_fen, balance_fen)`、`refund_reversal`。
- `app/service/points/ledger.py`：credit/deduct + 写流水；幂等键 `points:award:<order_id>`、`points:redeem:<order_id>`、`points:refund:<order_id>`。
- `app/service/points/payment.py`：`apply_points_snapshot`、`award_on_payment`、`refund_points`。
- `__init__.py` 门面 `PointsService`：`get_points/get_ledger/redeem_preview/apply_points/award_on_payment/refund_points`。

**M3.3 支付联动**

- `payment.json` 新增 `pointsFen/pointsUsed/pointsAwarded`。
- `apply-points` 必须把订单写为 `partial`，生成 `pointsFen/pointsUsed/remainFen`，后续微信/mock 按 `remainFen` 收款，不能只放快照。
- `build_combined_payment`、`prepare-payment`、微信通知金额校验统一支持 `couponFen/pointsFen`：`remain_fen = total_fen - coupon_fen - balance_fen - points_fen`（统一 `compute_remain_fen(total, coupon, balance, points)`）。
- 三条支付成功路径（mock、微信通知、储值全额支付）统一调 `award_on_payment`，重复通知幂等。
- 取消/超时/后台取消按支付快照调 `refund_points`。

**M3.4 小程序 API**

- `GET /api/v1/miniapp/points`：余额 + 明细。
- `POST /api/v1/miniapp/orders/{order_id}/points-preview`：试算不落账。
- `POST /api/v1/miniapp/orders/{order_id}/apply-points`：校验并写 partial 快照。
- 新增 `app/api/channels/storefront/points.py`，鉴权沿用 `authenticate_storefront_request` 并在 storefront 装配点注册。

**M3.5 验证/收口**

- 规则纯函数单测、仓储幂等/余额不足单测、三路径发分一次、重复通知幂等、组合金额正确、取消退积分。
- 全套测试 + `ruff` + `check_file_sizes` + `check_project --skip-tests`。
- 本地验证 → 生产部署 → LOGBOOK/项目进度清单收口，按 M1/M2 模式。

> 说明：小程序页面仍归 M5，M3 只交付 API 与账务闭环。

### M4：优惠券模块（4 天）🟡 第一阶段完成

模型/仓储/管理后台/核销引擎/小程序API

### M5：小程序前端（3 天）🟡 开发完成、发布未完成

我的页真实API/充值页/积分明细/优惠券中心/结算页扩展

### M6：收口部署（1 天）🟡 部分完成

---

## 架构约束

- 禁止 `api/` → `repository/` 直调
- 禁止 SQL f-string、`Optional[X]`、`SELECT *`
- 原子条件更新（同订单支付一致性模式）
- POINTS 用 `unique_id` 去重；COUPON 用 `id`+`status`+`mobile` 组合去重（**第一阶段现状，禁止用于新实现**——新券数据模型以 [ADR 0008](../harness-engineering/adr/0008-accounting-core-consistency.md) 的 `coupon_events.transition_key` + `origin_event_id` 为准）
- mock 支付显式开关

---

## M1 执行记录（2026-08-12）

- 1.1 ✅ `event_member.py`：四类事件解析与分发
- 1.2 ✅ `event_handler.py` 新增会员事件路由分支；webhook 审计归类 MEMBER
- 1.3 ✅ v021 迁移：`points_ledger` / `coupon_inventory` / `member_balance`（本地库已应用，schema_version=21）
- 1.4 ✅ 全量导入 Service + `scripts/import_member_loyalty.py`（dry-run/apply/limit/JSON）
- 1.5 ✅ Webhook 增量写入（POINTS→ledger，COUPON→inventory 反查补全）
- 1.6 ✅ 本地验证 + 生产执行完成：部署 v0.111.0（ecffa3b），v021 三表落库（schema_version=21）、/ready database_schema_ready=true、Webhook 会员路由生效；生产全量导入待真实店铺 API 契约验证后执行

### M1 关键决策
### M2 执行记录（2026-08-12）

- 模型/仓储 ✅ v022 迁移新增 `stored_value_recharge`（unpaid/paid/cancelled/expired）+ `balance_ledger`（unique_id 幂等、amount_fen 带符号）；`app/models/stored_value.py`、`app/constants/stored_value.py`（单笔 100~50000 分）
- 充值 Service ✅ `app/service/stored_value/recharge.py`：创建/取消/mock 确认幂等入账（`recharge:<id>` 幂等键）/列表；`member.py` 身份解析（openid→identity_links→primary_phone）+ credit/deduct 原子记账
- 储值支付+组合支付 ✅ `app/service/stored_value/payment.py`：全额余额支付防超扣（原子扣款+条件更新）；组合支付先扣余额置 partial（balanceFen/remainFen）再返回差额 mock/微信会话；取消/超时/后台取消按 `payment.balanceFen` 原路退款（`order_refund:<order_id>` 幂等）（**B3.1 口径修正：唯一账务事实为 `payment_attempt.payment_snapshot_json`，退款按快照资产分摊原路退回，`payment.balanceFen` 仅存于历史基线表述，见 ADR 0008 D1-0**）
- 小程序 API ✅ `recharges.py`（充值/余额端点）+ `orders.py`（pay-with-balance / prepare-combined-payment）；既有 `POST /{order_id}/mock-pay` 支持从 partial 完成支付
- 边界修复 ✅ 消除 `stored_value ↔ order` 循环导入（TYPE_CHECKING + `from __future__ import annotations`）；组合支付差额走微信时按 `remainFen` 校验通知金额；余额全额支付订单不可取消/不退款
- 验证 ✅ 储值域 14 项测试全过；全套 1365 项通过（含 tests/scripts），覆盖率 82.54%；ruff / check_file_sizes / check_project --skip-tests 全绿；本地库 v022 已应用（schema_version=22）
- 待办 ⏳ 真实微信支付（商户号到位后，见 FP-3）：组合支付差额走微信 JSAPI、支付通知与余额原路退款。M5 前端已交付（充值页/余额明细/结算页组合支付入口）。


- POINTS 去重键 `unique_id`；COUPON 去重键 `id+status+mobile`（状态流转写多行，符合生命周期记录语义）
- `member_balance.upsert_identity` 采用「None 不更新、显式 0 覆盖」，防止卡片/身份事件抹掉积分余额
- 会员域 API 名称以常量集中管理（`app/service/youzan/member_api.py`），真实店铺联调前需按实际开通权限验证
- 全量导入只落余额快照、券库存与券模板（`member_balance` / `coupon_inventory` / `coupon_templates`），积分明细流水由 Webhook 增量维护，避免导入快照污染明细

---

## 后续工作包（2026-08-14 结项拆分）

> 核心主链路及 Platform 第一阶段部署已完成。以下工作包为剩余事项，各自独立闭环后，方可整体标记「全部完成」；各工作包执行时须生成独立 trace_id（parent_trace_id 见各文档）。

| 编号 | 工作包 | 状态 | 阻塞 / 时点 | 文档 |
|------|--------|------|------------|------|
| FP-1 | 会员数据正式导入 | 🔴 待执行 | 真实店铺 API 契约 | docs/specs/2026-08-12-member-loyalty-followup-data-import.md |
| FP-2 | 本地权威切换 | 🔴 待执行 | 计划 2027-06（以本小程序替代有赞小程序） | docs/specs/2026-08-12-member-loyalty-followup-local-authority.md |
| FP-3 | 真实微信支付 | 🔴 待执行 | 微信支付商户号 | docs/specs/2026-08-12-member-loyalty-followup-wechat-pay.md |
| FP-4 | 小程序正式发布 | 🔴 待执行 | 真机 / 体验版 / 正式审核 | docs/specs/2026-08-12-member-loyalty-followup-miniapp-release.md |
| FP-5 | 技术债承接 | 🔴 待执行 | 无外部阻塞 | docs/specs/2026-08-12-member-loyalty-followup-techdebt.md |
