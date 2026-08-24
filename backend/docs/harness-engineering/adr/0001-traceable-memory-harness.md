# ADR 0001：采用 Traceable Memory Harness 作为 Vibe Coding 驾驭框架

- status: accepted
- date: 2026-06-11
- trace_id: 20260611-harness-engineering
- decision_owner: AI (Codex)
- related_docs:
  - docs/harness-engineering/specs/2026-06-11-vibe-coding-harness-engineering-design.md
  - docs/harness-engineering/README.md
  - docs/harness-engineering/core/traceability-model.md
  - docs/harness-engineering/core/mistake-ledger.md
  - docs/harness-engineering/core/verification-matrix.md

______________________________________________________________________

## Context

项目已经具备 `AGENTS.md`、Guard Skill、pre-commit、LOGBOOK、生产预检、冒烟 JSON 留档等基础 Harness，但这些资产原本更像分散的工具箱。

用户目标是让项目达到：

- 处处有追溯。
- 增强跨会话记忆。
- 同一类问题不要重复犯错。
- 适配当前 AI 驾驭和 Vibe Coding 范式。
- 达到大厂生产级可审计水平。

如果继续只依赖聊天提醒或零散文档，后续新 Agent 容易忘记上下文，架构决策也容易反复横跳。

______________________________________________________________________

## Decision

采用 **Traceable Memory Harness** 作为本项目 Vibe Coding 驾驭框架。

核心设计：

- 用 traceability model 串联需求、决策、改动、验证、证据和 LOGBOOK。
- 用 mistake ledger 把可复用教训沉淀为测试、脚本、门禁、skill 或 runbook。
- 用 verification matrix 降低收口验证的随机性。
- 用 harness snapshot 支持上下文重置和换 Agent。
- 用 ADR 固化影响长期演进的关键决策。
- 用 evidence index 管理上线前后的证据包。

______________________________________________________________________

## Alternatives

- 只加强 `AGENTS.md`：成本最低，但仍依赖 AI 自觉，难以证明每次任务是否被正确验证。
- 直接引入多 Agent 平台：自动化程度更高，但当前项目最缺的是追溯和证据闭环，先上平台会增加复杂度。
- 只依赖 pre-commit/CI：能拦截部分代码问题，但不能覆盖决策、交接、复盘和生产证据。

______________________________________________________________________

## Consequences

- 后续中大型任务应优先分配 `trace_id`。
- 关键决策需要补 ADR，而不是只留在聊天里。
- 上线相关动作应保留 JSON 报告，并在 evidence index 中登记。
- 可复用失误要进入 mistake ledger，并尽量补机械防线。
- Harness 文档和脚本本身也需要测试和 LOGBOOK 记录。

______________________________________________________________________

## Verification

- `docs/harness-engineering/README.md` 提供统一入口。
- `scripts/harness_snapshot.py` 能生成当前任务快照。
- `scripts/check_mistake_ledger.py` 能检查防重犯账本结构。
- `docs/harness-engineering/core/evidence-index.md` 能登记证据包。
- 本 ADR 作为首条长期决策记录存在。
