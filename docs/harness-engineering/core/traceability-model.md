# Traceability Model

本文件定义 Bakery Commerce Platform 当前 `Platform` 主仓的任务级追溯模型；对应代码仓路径仍为 `YunxiBakeBot`。目标是让任何一次 Vibe Coding 变更都能回答：为什么改、改了什么、怎么证明、还剩什么风险。

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
| `source` | 是 | 需求、故障、用户请求或生产事件来源 |
| `goal` | 是 | 本轮要达成的结果 |
| `decision_refs` | 否 | 设计文档、ADR、评估报告、关键讨论 |
| `changed_files` | 是 | 核心改动文件或文档 |
| `verification` | 是 | 执行过的检查命令和结果 |
| `evidence` | 否 | JSON 报告、截图、日志、测试输出、链接 |
| `logbook_entry` | 是 | LOGBOOK 对应条目标题 |
| `residual_risks` | 否 | 未解决风险、人工确认项或未验证范围 |

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
  - docs/harness-engineering/core/mistake-ledger.md
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
- source:
- goal:
- changed_files:
- verification:
- evidence:
- logbook_entry:
- residual_risks:
```

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
reports/harness/handoff-{timestamp}.md
reports/harness/handoff-{timestamp}.json
reports/preflight-before-{timestamp}.json
reports/preflight-after-{timestamp}.json
reports/smoke-after-{timestamp}.json
reports/migration-dry-run-{timestamp}.json
reports/migration-apply-{timestamp}.json
reports/baseline-seed-before-{timestamp}.json
reports/baseline-seed-after-{timestamp}.json
reports/rebuild-embeddings-after-{timestamp}.json
```

报告文件应拒绝覆盖旧文件。涉及写库或生产状态变更时，必须同时保留 dry-run 和 apply 后验证证据。

生成后的证据文件应登记到 [evidence-index.md](evidence-index.md)。影响长期演进的决策应登记到 [../adr/README.md](../adr/README.md)。

______________________________________________________________________

## 快照命令

长任务、上下文重置或换 Agent 前，运行：

```powershell
python scripts/harness_snapshot.py --trace-id 20260611-example --goal "说明当前任务" --status in_progress
```

需要归档时运行：

```powershell
python scripts/harness_snapshot.py --json --output reports/harness/handoff-{timestamp}.json
```
