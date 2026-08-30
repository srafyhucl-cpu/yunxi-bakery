# 文档归档区（docs/archive）

> 建立日期：2026-08-29
> trace_id：`20260829-cleanup-deprecated-directions`
> 性质：**归档不是删除**。全部文件通过 `git mv` 单路径移动，历史可随时通过 `git log --follow` 追溯。

本目录收纳已被后续决策取代或执行完毕的历史方向文档。**归档文档不再是任何当前工作的执行依据**；当前状态、范围与遗留事项的唯一入口是根目录 [PROJECT-STATE.md](../../PROJECT-STATE.md) 与 [待办优先级清单_20260829.md](../待办优先级清单_20260829.md)。

## 归档分组与原因

| 分组 | 文件 | 归档原因 |
|---|---|---|
| `p0-monorepo-20260817/` | EXECUTION-GUIDE.md、EXECUTION-REPORT.md、VERIFICATION-CHECKLIST.md、ARCHITECTURE-REVIEW-20260817.md | P0 Monorepo 整合（2026-08-17）的一次性执行指南、执行报告、验收清单与架构评审。整合已完成（commit `1c2a3ea`），仅作历史记录。 |
| `v1-scope-retracted/` | AI-EMPLOYEE-INSTRUCTIONS.md、MVP-DEVELOPMENT-GUIDE.md | 基于 v1.0「三大功能 MVP」框架编写；该范围定义已被计划书附录D v1.2（2026-08-24）**正式撤回**——小程序端/会员/积分/储值/券为有赞替代核心，不可砍且已全部建成于基线。P0.5 资产迁移与 P1 承接验证技术工作已完成（2026-08-25），阶段关闭仍以 `PROJECT-STATE.md` 的负责人确认状态为准；Week 2+ 任务清单已被 PROJECT-STATE 与任务指令体系取代。 |
| `two-repo-era/` | two-repo-rollout-plan.md、platform-miniapp-api-contract-v1.md、miniapp-phase1-execution-checklist.md、miniapp-ai-handoff-plan.md、AI对话页面原型设计说明.md | 双仓（YunxiBakeBot + YunxiBakeMiniApp）协作方向已被 2026-08-17 Monorepo 整合取代。现行 API 契约以 [miniapp/docs/api-contract.md](../../miniapp/docs/api-contract.md) 为准。原型设计说明引用的 `web/admin/src/pages/ai-dialog/prototype.html` 不存在于本仓（管理后台前端未纳入 monorepo）。 |
| `langchain-legacy-plans/` | langchain-ecosystem-ai-layer-takeover-plan.md、langchain-langgraph-migration-plan.md、langchain-ai-layer-next-execution-plan.md、langchain-ai-layer-next-enhancement-execution-plan.md | LangChain / LangGraph 接管 AI 应用层的分阶段执行计划（阶段 1-9）已落地完毕，后续 next 执行计划属于已完成方向的历史包袱。检索增强后续以 PROJECT-STATE 口径为准：**BM25 关键词检索落地，向量路径战略禁用**。 |

## 明确保留在原位的相关文档（为何不归档）

| 文件 | 位置 | 保留原因 |
|---|---|---|
| `langchain-ai-layer-production-enhancement-plan.md` | `docs/architecture/` | 仍被 `backend/scripts/check_langchain_ai_layer_production_plan.py:17` 及其测试 `backend/tests/scripts/test_check_langchain_ai_layer_production_plan.py` 引用；移动会破坏全量回归。已加废弃横幅：向量路径战略禁用，计划不再作为执行依据。 |
| `langchain-ai-layer-portfolio.md` | `docs/architecture/` | 被 `backend/scripts/build_langchain_portfolio_evidence_packet.py:23` 引用；作品集方向未被任何正式决策撤回。 |
| `github-reference-benchmark-and-implementation-plan.md`、`global-risk-remediation-and-framework-convergence-plan.md` | `docs/architecture/` | 已执行完毕的历史计划，保留原位供追溯，导航中标注为历史。 |
| `项目重构与推进计划书.md`（仓库根） | 根目录 | v1.0 计划书及附录C/D（v1.2 范围修正与缺陷复盘）是里程碑重新基线化（待办⑫）的基础材料，且附录D 是 v1.2 撤回条款的原始载体。 |

## 相关待决事项（登记，不在本轮处理）

- `backend/docs/` 是旧仓文档树的完整镜像副本（与根 `docs/` 大量重复，内容停在 monorepo 整合时点）。处置（合并/删除/标注）需要项目负责人明确指示；按文件操作红线不做批量删除。
- 旧仓 `D:\Project\YunxiBakeBot`（🔒 冻结，只读，永不删）与过期副本 `D:\Project\YunxiBakeMiniApp` 的处置见待办优先级清单⑪。
