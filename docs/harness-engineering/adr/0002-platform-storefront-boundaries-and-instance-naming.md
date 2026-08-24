# ADR 0002：采用逻辑总项目 + 双仓边界，并将 Yunxi 降级为实例名

- status: accepted
- date: 2026-06-20
- trace_id: 20260620-platform-storefront-boundaries-and-naming
- decision_owner: AI (Codex)
- related_docs:
  - README.md
  - docs/README.md
  - docs/architecture/project-boundaries.md
  - docs/architecture/platform-miniapp-api-contract-v1.md
  - docs/architecture/customer-master-v1.md
  - docs/architecture/customer-master-v1-schema-draft.md

______________________________________________________________________

## Context

项目最初围绕 `YunxiBakeBot` 与 `YunxiBakeMiniApp` 两个代码仓推进，但随着客户迁移、企微接入、CRM 规划和小程序边界收口逐步展开，出现了三个长期风险：

- 仓库路径名、产品名、渠道角色名和客户实例名混在一起，后续很容易越用越乱。
- `MiniApp` 相关命名曾一度承载平台真相，容易让人误判前后台职责。
- 如果继续把历史过渡材料当成当前实施蓝图，后续新 Agent 或新成员会不断重复边界讨论。

同时，当前阶段还不适合立即做第三个总仓、monorepo 或仓库 slug 重命名，因为这会把精力从客户迁移、平台收口和生产能力建设上转走。

______________________________________________________________________

## Decision

采用以下长期决策：

1. 以 `Bakery Commerce Platform` 作为通用产品级逻辑总项目名。
2. 当前不新建第三个代码仓，也不立即改成 monorepo。
3. 将当前 `YunxiBakeBot` 明确定义为 `Platform` 主仓。
4. 将当前 `YunxiBakeMiniApp` 明确定义为 `Storefront MiniApp` 渠道仓。
5. 将 `Yunxi` 明确定义为首个真实落地实例、配置集合、迁移来源和样板客户名，而不是产品名。
6. `Platform` 承担客户、商品、订单、会话、运营配置和第三方集成真相；`Storefront MiniApp` 只承担消费者前台页面、交互和渠道接入。
7. 第一阶段继续保留现有仓库 slug、外部 API 路径和数据库 schema 稳定，通过文档、canonical 领域命名和兼容 facade 完成边界收口。

______________________________________________________________________

## Alternatives

- 立即新建第三个总仓或 monorepo：统一感最强，但会显著增加迁移、CI、权限、部署和协作成本，不适合当前以客户迁移和平台收口为主的阶段。
- 继续沿用 `Yunxi` 作为产品级命名：短期改动最少，但会把“实例名”和“平台能力名”持续混在一起，不利于后续 SaaS 化、多租户或复制到其他商家。
- 保持现状不定边界：看似灵活，但会继续让 `MiniApp`、后台、迁移脚本和历史方案彼此串味，维护成本会越来越高。

______________________________________________________________________

## Consequences

- 后续新文档、新接口说明和新协作口径默认使用 `Bakery Commerce Platform`、`Platform`、`Storefront MiniApp`。
- `YunxiBakeBot` / `YunxiBakeMiniApp` 只保留为仓库路径名、历史材料引用或兼容层上下文。
- `Yunxi` 只出现在实例配置、迁移来源、样板客户或运营环境命名中。
- 当前实施入口需要持续把历史方案和当前权威口径分流，避免历史路线图重新变成执行起点。
- 如果未来需要仓库改名、monorepo 或多前台渠道扩展，应基于本 ADR 再新增后续 ADR，而不是直接覆盖本决策。

______________________________________________________________________

## Verification

- `README.md` 已明确 `Platform` / `Storefront MiniApp` 是角色名，不等于仓库名。
- `docs/architecture/project-boundaries.md` 已明确双仓职责、canonical 领域和命名约束。
- `docs/architecture/platform-miniapp-api-contract-v1.md` 已明确双仓 API 契约以 `Platform` 为真相源。
- `docs/README.md` 已把当前权威入口、历史方案和背景材料分层。
- 本 ADR 作为长期决策记录存在，并可被后续文档直接引用。
