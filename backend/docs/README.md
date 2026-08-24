# 文档导航

本目录同时包含当前设计文档、历史方案、评估报告和 Harness 证据入口。为避免把历史材料误读成当前架构，请优先按下面顺序阅读。

## 当前权威口径

除非你是在回顾历史决策，否则当前实施、迁移和双仓协作都应从本节进入；下方“历史方案”和“业务与技术背景”只用于参考，不作为执行起点。

当前代码事实（2026-07-12，`VERSION=0.107.12`）：

- `docs/architecture/global-risk-remediation-and-framework-convergence-plan.md`
  - 当前全局风险整改唯一主计划；先处理订单伪造、快照 PII、认证支付、事务、消息可靠性和发布恢复，再恢复 LangChain E1-E6 扩大灰度。
- `docs/architecture/privacy-data-retention-policy.md`
  - R3-A 主体导出/删除、consent 撤回、检索日志哈希、数据库 TTL 和备份保留策略。
- `docs/harness-engineering/adr/0005-framework-first-single-path.md`
  - 固化“通用能力框架优先、AI 应用层 LangChain / LangGraph 单路径、业务领域层保持可审计”的长期约束。
- `docs/harness-engineering/adr/0006-sqlite-inbox-outbox-exception.md`
  - 固化单机阶段 SQLite 持久 inbox 的窄例外、恢复边界和后续退出条件。

- `app/lifespan_routes.py` 是路由装配入口；对外仍暴露 `/api/v1/miniapp/*`、`/api/v1/admin/*`、`/api/v1/wecom/*`、`/api/v1/webhook/*` 等稳定路径。
- `app/api/channels/storefront/` 是消费者前台渠道的 canonical API 目录，继续承接 MiniApp 兼容路径。
- `app/api/admin/` 和 `app/api/integrations/` 是当前后台与第三方集成真实 Router 所在目录；根层 `admin_*.py`、`miniapp_*.py`、`webhook.py`、`wecom.py` 只保留兼容入口。
- `app/lifespan_services.py` 是服务装配入口；当前 canonical 服务包括 `catalog_service`、`order_service`、`customer_address_service`、`customer_group_service`、`storefront_conversation_service`、`employee_agent_service` 等。
- `app/service/order/`、`app/service/catalog/`、`app/service/customer/`、`app/service/conversation/`、`app/service/ops/` 已承接主要业务逻辑，`app/service/miniapp_*.py` 作为兼容 facade 使用。
- 统一质量门禁入口为 `python scripts/check_project.py --skip-tests`；发布前预检入口为 `python scripts/preflight_production.py --json`。
- AI 应用层已引入 LangChain / LangGraph：客户机器人使用 LangGraph 编排和 LangChain tool/model adapter；员工助手使用 LangGraph 执行流、LangChain structured planner fallback 和确定性 finalizer；业务领域层仍保持 `api -> service -> repository -> models`。

- `README.md`
  - 产品命名、仓角色、启动方式和总入口说明。
- `docs/architecture/project-boundaries.md`
  - 当前 `Platform` / `Storefront MiniApp` 边界与 canonical 领域职责。
- `docs/architecture/platform-miniapp-api-contract-v1.md`
  - 当前双仓对接的 API 契约基线，明确 MiniApp 应消费哪些公开接口以及背后 canonical 归属域。
- `docs/architecture/platform-domain-migration-inventory.md`
  - 当前 `Platform` 内部从历史 `miniapp_*` 命名继续迁到 canonical 领域的盘点、风险分级和建议执行批次。
- `docs/architecture/customer-group-operations-phase1.md`
  - 当前客户群运营一期说明，覆盖客户群触达、小程序结构化登记、后台汇总和微信客服单聊承接的最小闭环。
- `docs/architecture/github-reference-benchmark-and-implementation-plan.md`
  - GitHub 参考项目借鉴、客户机器人 / 员工助手双线边界、LangChain / LangGraph 取舍和分阶段实施计划。
- `docs/architecture/bot-capability-matrix.md`
  - 客户机器人和员工助手的能力目录，覆盖入口、底层 service、回复策略、验证入口和当前缺口。
- `docs/architecture/langchain-ecosystem-ai-layer-takeover-plan.md`
  - LangChain / LangGraph 接管 AI 应用层的分阶段执行计划和阶段 1-9 落地记录。
- `docs/architecture/langchain-ai-layer-portfolio.md`
  - 面向作品集和求职展示的 LangChain 生态化工程说明，覆盖边界、关键代码、133 项双机器人 eval、RAG 矩阵、事实敏感客服治理和回滚策略。
- `docs/architecture/customer-session-summary-design.md`
  - 客户机器人会话摘要设计，明确短期摘要、长期画像、触发阈值、独立数据层、异步生成和热路径读取边界。
- `docs/architecture/customer-memory-governance-plan.md`
  - 客户长期记忆治理计划，明确 `customer_profiles` 证据、置信度、撤销、过期和会话摘要隔离边界。
- `docs/architecture/customer-observability-contract.md`
  - 客户机器人可观测合约，明确知识命中、无资料兜底、转人工、工具成功、上下文压力等指标和隐私边界。
- `docs/architecture/miniapp-page-api-coverage-contract.md`
  - MiniApp 页面 API 覆盖合约，明确各前台页面依赖的 Platform API、待补会员/营销 API 和前端不得持有的业务真相。
- `docs/architecture/knowledge-governance-migration-plan.md`
  - 知识库治理兼容迁移计划，明确 audience、有效期、审核状态、默认值、过滤边界和静态验收入口。
- `scripts/check_github_reference_implementation_plan.py`
  - GitHub 参考实施计划静态验收入口，防止计划边界被误改成全量 LangChain / LangGraph 迁移。
- `scripts/check_customer_rag_golden_cases.py`
  - 客户机器人首批 RAG golden cases 的结构验收入口，覆盖商品咨询、配送、退款售后和转人工。
- `scripts/eval_retrieval.py --fixture tests/fixtures/customer_rag_golden_cases.json`
  - 客户机器人 golden cases 的离线检索评估入口，输出整体和分组 Recall@K / MRR。
- `scripts/report_retrieval_eval_matrix.py --db data/bot.db --fixture tests/fixtures/customer_rag_golden_cases.json --k 5`
  - RAG Advanced 多模式评测矩阵，比较 vector、hybrid、planned-hybrid 和 planned-hybrid+rerank。
- `scripts/report_agent_eval.py --latest`
  - 双机器人统一离线 Agent Eval 报告，聚合客户 RAG golden cases、员工 planner 探针和能力合约。
- `docs/architecture/customer-master-v1.md`
  - 当前客户主档 v1 设计基线，明确主档、身份链接、来源快照三层结构，以及有赞迁移审计落点。
- `docs/architecture/customer-master-v1-schema-draft.md`
  - 当前客户主档 v1 四表 schema 草案，明确 `customer_master / customer_identity_links / customer_source_snapshots / customer_merge_reviews` 的字段、索引、唯一约束和 `pending_review` 闭环。
- `docs/architecture/youzan-customer-migration-audit-checklist.md`
  - 当前有赞客户迁移审计清单，明确输入、标准化规则、风险分级、输出表头和分流规则。
- `docs/architecture/youzan-customer-formal-import-runbook.md`
  - 当前有赞客户正式迁移执行 runbook，明确审计、dry-run、apply、报告留档和重跑语义。
- `scripts/verify_youzan_customer_import.py`
  - 当前有赞客户迁移后核对脚本，按批次核对快照、主档、身份与复核汇总，可选对比正式导入报告。
- `docs/architecture/youzan-customer-import-handoff-and-rollback-runbook.md`
  - 当前有赞客户迁移交接与回滚 runbook，明确异常中止、交接证据、同批次重跑和恢复优先级。
- `scripts/import_youzan_customers.py`
  - 当前有赞客户正式迁移入口；默认 dry-run，显式 `--apply` 才写库。
- `项目进度与配置清单.md`
  - 当前进度、生产同步检查和阶段记录。
- `docs/api-spec.md`
  - 高层接口总览；真实契约仍以运行中的 OpenAPI 为准。

## 历史方案

- `docs/architecture/two-repo-rollout-plan.md`
  - 双仓推进节奏的历史路线图，只用于回顾过渡思路。
- `docs/architecture/miniapp-phase1-execution-checklist.md`
  - `Storefront MiniApp` 第一阶段边界对齐清单，只保留历史过渡记录。
- `docs/architecture/miniapp-ai-handoff-plan.md`
  - 发给 `MiniApp` 仓 AI 的过渡阶段执行说明，只作为历史参考。

## 业务与技术背景

- `docs/design/`
  - 保存业务方案、工作流、技术架构和升级设计。
  - 这些文档大多保留了早期阶段表达；如与当前代码边界冲突，以 `docs/architecture/project-boundaries.md` 为准。

## Harness 与证据

- `docs/harness-engineering/README.md`
  - Harness Engineering 总入口。
- `docs/harness-engineering/adr/0002-platform-storefront-boundaries-and-instance-naming.md`
  - 固化逻辑总项目、双仓边界和 `Yunxi` 实例名定位的长期决策。
- `docs/harness-engineering/adr/0003-langchain-ai-layer-boundary.md`
  - 固化 LangChain 生态接管 AI 应用层、但不接管业务领域层和数据库事实层的长期边界。
- `docs/harness-engineering/adr/0005-framework-first-single-path.md`
  - 固化框架优先决策顺序、禁止长期框架/自研双轨，以及迁移兼容路径的退出条件。
- `docs/harness-engineering/adr/0006-sqlite-inbox-outbox-exception.md`
  - 固化单机阶段 SQLite 持久 inbox 的窄例外、恢复边界和后续退出条件。
- `docs/harness-engineering/core/evidence-index.md`
  - 历史证据索引，只做追溯，不作为当前架构口径来源。
- `docs/harness-engineering/specs/2026-07-12-isolated-remediation-harness-design.md`
  - 生产同构、数据隔离的主体删除和消息进程崩溃恢复 Harness 设计。
- `docs/harness-engineering/specs/2026-07-12-local-production-backup-job-design.md`
  - 无生产独立磁盘时，由 Windows 主机主动拉取并在 D 盘加密保留生产快照的设计。
- `docs/harness-engineering/specs/2026-07-12-production-privacy-outbound-audit-design.md`
  - 聚合模型入口、结构化脱敏、trace 过滤和生产关闭态的隐私出站审计设计。
- `docs/harness-engineering/specs/2026-07-12-r3b-security-outbound-audit-design.md`
  - 统一远程图片下载和员工 Agent 工具授权的 R3-B 安全出站审计设计。
- `docs/harness-engineering/specs/2026-07-12-production-synthetic-subject-deletion-design.md`
  - 使用生产真实 JWT、loopback API 和随机合成主体验证隐私导出删除闭环，不触碰真实客户。
- `docs/harness-engineering/specs/2026-07-12-production-synthetic-inbox-crash-design.md`
  - 使用生产真实 `InboxRepo`、专用合成队列和独立子进程验证 processing 崩溃后的 lease 重领，不触发外部发送。
- `docs/harness-engineering/specs/2026-07-13-production-container-verification-design.md`
  - 使用隔离端口和 tmpfs 完成生产 Docker build、非 root/单 worker smoke、镜像资源审计和漏洞扫描。

## 历史评估与报告

- `docs/评估报告.md`
- `docs/HarnessEngineering评估报告_20260604.md`
- `docs/VibeCoding可持续性评估报告_20260604.md`

这些文档反映的是各自时间点的判断，适合回顾，不应直接当作当前设计结论。
