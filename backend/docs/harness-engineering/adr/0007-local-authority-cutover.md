# ADR 0007：会员账务本地权威切换（2027-06 最早候选窗口）

- status: accepted
- date: 2026-08-14
- trace_id: `20260812-member-loyalty-storedvalue`
- decision_owner: project owner
- related_docs:
  - `docs/specs/2026-08-12-member-loyalty-storedvalue-plan.md`
  - `docs/specs/2026-08-12-member-loyalty-followup-local-authority.md`
  - `docs/specs/2026-08-12-member-loyalty-followup-data-import.md`
  - `docs/specs/2026-08-12-member-loyalty-followup-wechat-pay.md`
  - `docs/specs/2026-08-12-member-loyalty-followup-miniapp-release.md`

## Context

会员账务域当前处于第一阶段，数据权威与用户入口需分别表述：

| 资产域 | 当前数据权威 | 目标数据权威 |
|---|---|---|
| 储值余额（`member_balance.stored_value_fen`） | **Platform 本地账本**（v022 起由 `stored_value_recharge` / `balance_ledger` 本地维护） | Platform 本地账务域 |
| 积分余额（`member_balance.points`） | 有赞 `total`（`POINTS_AUTHORITY=youzan`） | Platform 本地账务域（`POINTS_AUTHORITY=local`） |
| 优惠券（`coupon_inventory`） | 有赞镜像 + 本地核销引擎（`COUPON_AUTHORITY=youzan`） | Platform 本地账务域（`COUPON_AUTHORITY=local`） |
| 会员身份（`member_balance` / `customer_identity_links`） | Platform 本地投影（openid 预导入） | Platform 本地投影（**一致性核对，非切换**） |

**Platform 本地账务域是数据权威，小程序是唯一用户入口**。业务目标是**以本小程序替代有赞小程序**作为用户入口，切换完成后关停有赞小程序。切换涉及真实资金与券资产，且 `POINTS_AUTHORITY` / `COUPON_AUTHORITY` 为进程级配置，`coupon_inventory` 在 `local` 权威下只识别 `order/local` 来源，现有 `import` / `webhook` 券行会被过滤，需专门的迁移与围栏策略，不能仅做配置翻转。

项目发布边界已经明确：截至 **2027 年 5 月 31 日（含）**，小程序只用于开发、调试和测试，不向真实用户开放。**2027 年 6 月只是最早候选上线窗口，不构成自动上线或自动切换授权**；正式开放必须由项目负责人明确批准。

## Decision

保留"切换本地权威"为既定决策，**2027-06 作为最早候选执行窗口**，并在批准切换完成后关停有赞小程序：

- 无项目负责人明确批准，不得开放真实用户，也不得因到达 2027-06 自动执行切换。
- 截至 2026-08-14，尚不具备受控真实微信支付 / 退款与真实有赞券测试条件。未来条件具备后，只允许授权测试账号开展经事前批准的小额、可退款、可对账、可清理测试。
- 积分与优惠券**分别切换**，各自完成数据对账、观察与演练，禁止一次性切换全部聚合。切换语义（B1.9 起）：**不可逆前可中止**（未发生本地首次写入前可中止切换）、**不可逆后仅 roll-forward 补偿**（本地首次写入后不回写有赞，差异以本地快照为权威追加修正，见 FP-2 C 节），不再表述为"回滚"。
- 切换前置（硬依赖）：FP-1（会员数据正式导入）、FP-3（真实微信支付，含退款 / 关单能力）、FP-4（小程序正式发布并稳定回验）全部完成。
- 优惠券切换前必须完成：有效券基线迁移（`import` / `webhook` 来源有效券行迁移到 `local` 语义）、切换水位线、写入围栏、影子读对账与稳定观察期。
- 执行前书面确认并演练 RPO / RTO；本地首次写入为**不可逆边界**——写入后仅 roll-forward 补偿（不回写有赞），该风险列为正式放行的显式审批项（FP-4B2 Go/No-Go 清单）。
- 有赞小程序下线仅在该工作包与 FP-4 完成后执行，并与有赞运营协调在途用户。

## Alternatives

- 维持 `youzan` 权威：与"以本小程序替代有赞小程序"目标冲突，否决。
- 立即切换：前置（数据导入、真实支付、正式发布）未完成，且券来源过滤 / 围栏未就绪，风险不可接受，否决。
- 放弃切换、长期双权威：会造成余额 / 券分裂与双写风险，否决。

## Consequences

- Platform 本地账务域成为储值、积分、券、身份的唯一数据权威，小程序作为唯一用户入口；有赞小程序下线。
- 2027-05-31（含）前维持开发测试属性；完成工程和外部验收不自动改变该属性。
- 切换前需要完成数据导入、真实支付、正式发布与券迁移 / 围栏 / 对账能力，工程量前置明确。
- 切换窗口存在资金与券资产风险，RPO / RTO 演练与 roll-forward 补偿演练是硬约束。
- 长期避免双写分裂，但需维护与有赞的数据交接 / 停止写入流程（不可逆前中止、不可逆后仅 roll-forward）。

## Verification

- 逐聚合对账通过（积分与券分别），影子读观察期无差异漂移。
- 有效券基线迁移后，已有有效券在 `local` 下可查询、可核销。
- 切换水位线、写入围栏、roll-forward 补偿与 RPO / RTO 演练记录齐全。
- 有赞下线后，Platform 本地账务域成为唯一数据权威，小程序作为唯一用户入口，无业务中断。
- 项目负责人对真实用户开放作出明确批准，并记录批准日期、版本、范围和残余风险。
