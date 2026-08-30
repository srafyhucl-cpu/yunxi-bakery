# 文档导航

本目录包含当前设计文档、历史方案、评估报告和 Harness 证据入口。为避免把历史材料误读成当前架构，请按下面顺序阅读。

> 本导航已于 2026-08-29（trace `20260829-cleanup-deprecated-directions`）从双仓时代口径（2026-07-12，VERSION=0.107.12）重写为 Monorepo 口径。已废弃方向与已执行完毕的一次性文档移入 [archive/](archive/)，归档原因见 [archive/README.md](archive/README.md)。

## 当前权威口径

除非你在回顾历史决策，否则从本节进入；其余各节只用于参考，不作为执行起点。

- **[../PROJECT-STATE.md](../PROJECT-STATE.md)** — 唯一状态入口：定位、时间线（P0 ✅ → P0.5 ✅ → P1 技术完成、阶段关闭待负责人确认 → ▶ P2 试运行准备 → P3）、资产地图、v1.2/v1.3/v1.4 范围修正与遗留事项。**迷路先看这里，不要翻历史文档。**
- **[待办优先级清单_20260829.md](待办优先级清单_20260829.md)** — 当前待办 P0/P1/P2/P3 与依赖关系。
- **[../AGENTS.md](../AGENTS.md)** — AI Agent 工作规范（含小程序规范与项目级红线）。
- **[AGENTS/multi-agent-coordination.md](AGENTS/multi-agent-coordination.md)** — 多 Agent 权威源、状态快照、并行边界和清理规则。
- **[../miniapp/docs/api-contract.md](../miniapp/docs/api-contract.md)** — 现行前后端 API 契约（Monorepo 单一契约源；双仓时代契约已归档）。
- **[api-spec.md](api-spec.md)** — 高层接口总览（自带历史横幅；真实接口以运行中的 FastAPI OpenAPI 为准）。
- **[../项目进度与配置清单.md](../项目进度与配置清单.md)** — 版本、生产同步检查和阶段记录。

### 代码现状（Monorepo）

- 后端在 `backend/app/`；`lifespan_routes.py` 是路由装配入口，对外暴露 `/api/v1/miniapp/*`、`/api/v1/admin/*`、`/api/v1/wecom/*`、`/api/v1/webhook/*` 等稳定路径。
- `backend/app/api/channels/storefront/` 是消费者前台渠道 canonical API 目录；`backend/app/api/admin/` 与 `backend/app/api/integrations/` 是后台与第三方集成的真实 Router 所在目录；根层 `admin_*.py`、`miniapp_*.py`、`webhook.py`、`wecom.py` 只保留兼容入口。
- 统一质量门禁入口：`python backend/scripts/check_project.py --skip-tests`。
- 统一协作约束入口：[../docs/AGENTS/multi-agent-coordination.md](AGENTS/multi-agent-coordination.md)；动态状态只以 [../PROJECT-STATE.md](../PROJECT-STATE.md) 为准。
- AI 应用层使用 LangChain / LangGraph 编排；业务领域层保持 `api -> service -> repository -> models`；检索为 BM25 关键词路径（向量路径战略禁用）。

### architecture/ 活跃文档

- [project-boundaries.md](architecture/project-boundaries.md) — Platform / Storefront MiniApp 边界与 canonical 领域职责。
- [miniapp-page-api-coverage-contract.md](architecture/miniapp-page-api-coverage-contract.md) — MiniApp 页面 API 覆盖合约。
- [platform-domain-migration-inventory.md](architecture/platform-domain-migration-inventory.md) — 从历史 `miniapp_*` 命名收口到 canonical 领域的盘点。
- [bot-capability-matrix.md](architecture/bot-capability-matrix.md) — 客户机器人与员工助手能力目录。
- [customer-group-operations-phase1.md](architecture/customer-group-operations-phase1.md) — 客户群运营一期说明（范围：继续推迟，非当前活跃工作）。
- [privacy-data-retention-policy.md](architecture/privacy-data-retention-policy.md) — 主体导出/删除、consent、检索日志哈希、备份保留策略。
- [knowledge-governance-migration-plan.md](architecture/knowledge-governance-migration-plan.md) — 知识库治理兼容迁移计划（迁移已随 P0.5 完成，作执行口径参考）。
- 客户主档与有赞迁移：[customer-master-v1.md](architecture/customer-master-v1.md)、[customer-master-v1-schema-draft.md](architecture/customer-master-v1-schema-draft.md)、[youzan-customer-migration-audit-checklist.md](architecture/youzan-customer-migration-audit-checklist.md)、[youzan-customer-formal-import-runbook.md](architecture/youzan-customer-formal-import-runbook.md)、[youzan-customer-import-handoff-and-rollback-runbook.md](architecture/youzan-customer-import-handoff-and-rollback-runbook.md)、[youzan-openapi-customer-openid-access-runbook.md](architecture/youzan-openapi-customer-openid-access-runbook.md)（正式导入已于 2026-08-11 执行，runbook 保留作重跑与回滚口径）。
- 客户机器人记忆与可观测：[customer-session-summary-design.md](architecture/customer-session-summary-design.md)、[customer-memory-governance-plan.md](architecture/customer-memory-governance-plan.md)、[customer-observability-contract.md](architecture/customer-observability-contract.md)。
- 企微员工助手：`wecom-employee-agent-*.md` 5 篇（承接验证已通过，作能力与运行口径参考）。
- 历史保留（已执行完毕、未归档因仍被脚本引用或作战略追溯）：[langchain-ai-layer-production-enhancement-plan.md](architecture/langchain-ai-layer-production-enhancement-plan.md)（**已加废弃横幅：向量路径战略禁用**，被 `backend/scripts/check_langchain_ai_layer_production_plan.py` 引用）、[langchain-ai-layer-portfolio.md](architecture/langchain-ai-layer-portfolio.md)（被 `backend/scripts/build_langchain_portfolio_evidence_packet.py` 引用）、[github-reference-benchmark-and-implementation-plan.md](architecture/github-reference-benchmark-and-implementation-plan.md)、[global-risk-remediation-and-framework-convergence-plan.md](architecture/global-risk-remediation-and-framework-convergence-plan.md)。

### 检索 / RAG 评估入口（backend/scripts/）

- `python backend/scripts/check_customer_rag_golden_cases.py` — golden cases 结构验收。
- `python backend/scripts/eval_retrieval.py --fixture backend/tests/fixtures/customer_rag_golden_cases.json` — 离线检索评估（Recall@K / MRR）。
- `python backend/scripts/report_retrieval_eval_matrix.py --db backend/data/bot.db --fixture backend/tests/fixtures/customer_rag_golden_cases.json --k 5` — 多模式评测矩阵。
- `python backend/scripts/report_agent_eval.py --latest` — 双机器人统一离线 Agent Eval 报告。

## 已归档方向（docs/archive/）

归档原因与逐文件说明见 [archive/README.md](archive/README.md)（trace `20260829-cleanup-deprecated-directions`）：

- `archive/p0-monorepo-20260817/` — P0 Monorepo 整合执行指南 / 执行报告 / 验收清单 / 架构评审（已执行完毕）。
- `archive/v1-scope-retracted/` — v1.0「三大功能 MVP」范围文档（已被附录D v1.2 撤回：小程序/会员/积分/储值/券不可砍）。
- `archive/two-repo-era/` — 双仓协作方向文档（已被 Monorepo 整合取代；现行契约见 `miniapp/docs/api-contract.md`）。
- `archive/langchain-legacy-plans/` — LangChain 接管与 next 执行计划（已落地完毕；向量增强路径战略禁用）。

## 业务与技术背景

- [design/](design/)
  - 保存业务方案、工作流、技术架构和升级设计。
  - 这些文档大多保留了早期阶段表达；如与当前代码边界冲突，以 [architecture/project-boundaries.md](architecture/project-boundaries.md) 与 `PROJECT-STATE.md` 为准。

## Harness 与证据

- [harness-engineering/README.md](harness-engineering/README.md)
  - Harness Engineering 总入口（脚本统一位于 `backend/scripts/`）。
- [harness-engineering/adr/0002-platform-storefront-boundaries-and-instance-naming.md](harness-engineering/adr/0002-platform-storefront-boundaries-and-instance-naming.md)
  - 固化逻辑总项目、双仓边界和 `Yunxi` 实例名定位的长期决策（边界已在 Monorepo 整合后落地为同仓目录边界）。
- [harness-engineering/adr/0003-langchain-ai-layer-boundary.md](harness-engineering/adr/0003-langchain-ai-layer-boundary.md)
  - 固化 LangChain 生态接管 AI 应用层、但不接管业务领域层和数据库事实层的长期边界。
- [harness-engineering/adr/0005-framework-first-single-path.md](harness-engineering/adr/0005-framework-first-single-path.md)
  - 固化框架优先决策顺序、禁止长期框架/自研双轨，以及迁移兼容路径的退出条件。
- [harness-engineering/adr/0006-sqlite-inbox-outbox-exception.md](harness-engineering/adr/0006-sqlite-inbox-outbox-exception.md)
  - 固化单机阶段 SQLite 持久 inbox 的窄例外、恢复边界和后续退出条件。
- [harness-engineering/core/evidence-index.md](harness-engineering/core/evidence-index.md)
  - 历史证据索引，只做追溯，不作为当前架构口径来源。
- [harness-engineering/core/agent-handoff-template.md](harness-engineering/core/agent-handoff-template.md) 与 [AGENT-HANDOFF-20260829.md](AGENT-HANDOFF-20260829.md)
  - 交接模板与最新结构化交接文档。

## 历史评估与报告

- [评估报告.md](评估报告.md)
- [HarnessEngineering评估报告_20260604.md](HarnessEngineering评估报告_20260604.md)
- [VibeCoding可持续性评估报告_20260604.md](VibeCoding可持续性评估报告_20260604.md)

这些文档反映的是各自时间点的判断，适合回顾，不应直接当作当前设计结论。
