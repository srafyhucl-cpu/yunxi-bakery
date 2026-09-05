# Traceability Model

> 中文治理属于 Harness P0 控制面：任务、运行、证据和交接的面向人说明使用中文，稳定机器字段保持 ASCII。

本文件定义 YunxiBakery monorepo 的任务级追溯模型；后端代码位于 `backend/`，小程序位于 `miniapp/`，旧仓 `YunxiBakeBot` 仅作冻结历史。目标是让任何一次 Vibe Coding 变更都能回答：为什么改、改了什么、怎么证明、还剩什么风险。

______________________________________________________________________

## Trace ID

推荐格式：

```text
YYYYMMDD-topic
```

示例：

```text
20260611-harness-engineering
20260611-production-readiness
20260609-agent-memory
```

______________________________________________________________________

## 任务追溯字段

| 字段 | 必填 | 说明 |
|---|---|---|
| `trace_id` | 是 | 任务级追踪号 |
| `run_id` | 中大型任务必填 | 一次具体 Agent 执行的唯一标识；同一 `trace_id` 可以有多次运行 |
| `parent_run_id` | 否 | 续跑、重试或换 Agent 时指向上一运行 |
| `task_id` | 是 | 对应 `PROJECT-STATE.md` 的唯一任务 |
| `source` | 是 | 需求、故障、用户请求或生产事件来源 |
| `goal` | 是 | 本轮要达成的结果 |
| `as_of_commit` | 是 | 开始执行时核对的代码快照 |
| `version` | 是 | 开始执行时的 `backend/VERSION` |
| `model_id` | 中大型 Agent 运行必填 | 实际使用的模型或人工执行标识 |
| `tool_policy_hash` | 中大型 Agent 运行必填 | 允许路径、禁止路径、网络和生产开关策略摘要哈希 |
| `input_artifact_hash` | 否 | 输入 fixture、任务包或外部资料的哈希 |
| `output_artifact_hash` | 否 | 关键报告、快照或交付物的哈希 |
| `decision_refs` | 否 | 设计文档、ADR、评估报告、关键讨论 |
| `changed_files` | 是 | 核心改动文件或文档 |
| `verification` | 是 | 执行过的检查命令和结果 |
| `evidence` | 否 | JSON 报告、截图、日志、测试输出、链接 |
| `failure_class` | 否 | 失败归因，如 `scope_drift`、`stale_snapshot`、`policy_violation`、`verification_failure` |
| `latency_ms` | 否 | 运行耗时；长任务或 Agent eval 应记录 |
| `cost` | 否 | 模型、工具或测试成本摘要；未知时写 `unknown` |
| `human_intervention` | 否 | 是否发生人工批准、接管、纠偏或恢复 |
| `replayable` | 是 | 是否能用固定输入、策略和依赖摘要重放到同一决策阶段 |
| `logbook_entry` | 是 | LOGBOOK 对应条目标题 |
| `residual_risks` | 否 | 未解决风险、人工确认项或未验证范围 |

证据索引中的仓库来源使用 `repository_origin`：新证据填写 `monorepo`；冻结旧仓历史
证据保留原始提交并由检查器标记 `legacy:YunxiBakeBot`；无法读取来源时标记为
`external`/`external_unverified`，不得把旧仓证据改写成当前仓证据。

### 错误候选追溯字段（trace: 20260905-harness-evidence-error-loop）

错误候选（`docs/harness-engineering/core/failure-candidate.schema.json`）是运行级失败
事实到正式错误账本之间的候选层，必须绑定任务追溯字段：

| 字段 | 说明 |
|---|---|
| `candidate_id` | 随机生成的候选标识，只用于候选与 review 记录，不得复用为 `ERRORS.md` 条目 ID |
| `fingerprint` | `failure_class + 规范化 summary + 规范化 evidence_files` 的 SHA-256，可重复计算 |
| `status` | `pending → accepted / rejected / deferred`；生成时必须为 `pending` |
| `run_id` / `trace_id` / `task_id` / `as_of_commit` / `version` | 绑定生成时的运行与代码快照 |
| `evidence_files` | 证据相对路径列表，进入 artifact index 哈希校验 |
| `duplicate_of` | 重复候选指向已有候选 ID 或 `ERRORS.md` 条目 |
| `review.operator / reviewed_at / decision / reason` | 人工 review 记录；accept 后写入 `ERRORS.md` 并回填 `- fingerprint:` 行 |

候选生成与 `reject`/`defer` 不得修改根目录 `ERRORS.md`；只有 `accept` 经临时内容校验
后一次性写入新 `M-YYYYMMDD-NNN` 条目，并运行 `check_mistake_ledger.py`。

______________________________________________________________________

## 推荐记录模板

```markdown
### Trace: 20260611-harness-engineering

- source: 用户要求完善 Vibe Coding Harness Engineering
- goal: 建立可追溯、可记忆、防重犯的生产级 Harness 规划与入口文档
- decision_refs:
  - docs/harness-engineering/specs/2026-06-11-vibe-coding-harness-engineering-design.md
  - docs/harness-engineering/adr/0001-traceable-memory-harness.md
- changed_files:
  - docs/harness-engineering/README.md
  - docs/harness-engineering/core/traceability-model.md
  - docs/harness-engineering/core/verification-matrix.md
  - ERRORS.md
  - docs/harness-engineering/core/agent-handoff-template.md
- verification:
  - Test-Path docs/harness-engineering/README.md
  - Select-String -Path docs/harness-engineering/**/*.md -Pattern "占位符"
- evidence:
  - LOGBOOK.md 顶部条目
- residual_risks:
  - P1 脚本化 snapshot 尚未实现
```

当前任务最小模板：

```markdown
- trace_id:
- run_id:
- parent_run_id:
- task_id:
- source:
- goal:
- as_of_commit:
- version:
- model_id:
- tool_policy_hash:
- changed_files:
- verification:
- evidence:
- failure_class:
- latency_ms:
- cost:
- human_intervention:
- replayable:
- logbook_entry:
- residual_risks:
```

## 最小 Episode（运行回放包）

中大型 Agent 任务应将一次运行视为可回放的 episode，而不是只保存最终回答。最小包包含任务输入、计划摘要、关键工具调用、策略摘要、验证命令、人工介入、最终状态和恢复点。

规则：

1. 事件只记录完成任务所需的最小摘要，不保存密钥、客户原文或未经批准的生产数据。
2. 重试必须生成新的 `run_id` 并通过 `parent_run_id` 关联，禁止覆盖失败运行。
3. “通过”至少拆成结果正确、策略合法、证据完整、可回放四个断言。

______________________________________________________________________

## 证据等级

| 等级 | 证据 | 说明 |
|---|---|---|
| L1 | 口头说明 | 只能作为线索，不能作为完成证明 |
| L2 | 文档记录 | 可追溯，但不能证明行为正确 |
| L3 | 命令输出 | 能证明本地某次检查结果 |
| L4 | JSON 报告 | 可归档、可机器读取、可复盘 |
| L5 | CI/生产监控证据 | 最强证据，适合发布和事故复盘 |

结论：生产相关任务尽量达到 L4；普通文档任务至少达到 L2；代码行为变更至少达到 L3。

______________________________________________________________________

## Reports 命名建议

```text
backend/reports/harness/handoff-{timestamp}.md
backend/reports/harness/handoff-{timestamp}.json
backend/reports/preflight-before-{timestamp}.json
backend/reports/preflight-after-{timestamp}.json
backend/reports/smoke-after-{timestamp}.json
backend/reports/migration-dry-run-{timestamp}.json
backend/reports/migration-apply-{timestamp}.json
backend/reports/baseline-seed-before-{timestamp}.json
backend/reports/baseline-seed-after-{timestamp}.json
backend/reports/rebuild-embeddings-after-{timestamp}.json
```

报告文件应拒绝覆盖旧文件。涉及写库或生产状态变更时，必须同时保留 dry-run 和 apply 后验证证据。

生成后的证据文件应登记到 [evidence-index.md](evidence-index.md)。影响长期演进的决策应登记到 [../adr/README.md](../adr/README.md)。

______________________________________________________________________

## 快照命令

长任务、上下文重置或换 Agent 前，运行：

```powershell
  python backend/scripts/harness_snapshot.py --trace-id 20260611-example --goal "说明当前任务" --status in_progress
```

需要归档时运行：

```powershell
  python backend/scripts/harness_snapshot.py --json --output backend/reports/harness/handoff-{timestamp}.json
```
