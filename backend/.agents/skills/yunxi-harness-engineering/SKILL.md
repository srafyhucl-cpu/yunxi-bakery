---
name: 芸熙Harness工程守卫
version: 1.0.0
description: "【较大任务、跨文件变更、上线收口、复盘或发现重复错误时调用】芸熙烘焙 AI 客服 Harness Engineering 守卫。用于把需求、决策、改动、验证、证据、LOGBOOK、mistake ledger 和交接快照串成可追溯闭环；当用户提到 harness、追溯、记忆、防重犯、复盘、证据、交接、生产级治理、文档统一管理、Skill 是否过时时必须调用。"
---

# 芸熙 Harness Engineering 守卫

本 Skill 是项目级 AI 驾驭入口。它不替代 `AGENTS.md`、Guard Skill、pre-commit 或测试，而是负责把它们组织成一条可追溯链路。

统一父入口：

```text
docs/harness-engineering/README.md
```

## 触发场景

只要命中以下任一情况，就先使用本 Skill：

- 用户提到 Harness、Vibe Coding、追溯、记忆、防重犯、复盘、证据、交接、Skill 过时、文档散乱。
- 任务预计修改超过 2 个文件，或需要跨文档、脚本、测试、配置同步。
- 任务涉及生产同步、上线前后验证、报告留档、恢复计划、冒烟或预检。
- 发生返工、误解、误操作、重复 bug、遗漏验证、上下文丢失。
- 需要判断“这次经验应该沉淀到哪里”：测试、脚本、pre-commit、AGENTS、Skill、runbook、ADR 或 mistake ledger。

## 启动顺序

1. 读取 `AGENTS.md`，确认本轮还需要哪些 Guard Skill。
2. 读取 `LOGBOOK.md` 最新条目，避免重复踩坑。
3. 读取 `docs/harness-engineering/README.md`，只按场景继续打开子文档。
4. 为中大型任务分配 `trace_id`，格式参考 `docs/harness-engineering/core/traceability-model.md`。
5. 按 `docs/harness-engineering/core/verification-matrix.md` 选择最低验证和加强验证。

## 记忆落点决策

不要把经验只留在聊天里。按下面优先级沉淀：

| 情况 | 首选落点 |
|---|---|
| 可被机器检查的格式或规则 | 测试、脚本、pre-commit |
| 操作流程或 Agent 启动约束 | `AGENTS.md` 或项目 Skill |
| 某类错误已发生且值得防重犯 | `docs/harness-engineering/core/mistake-ledger.md` |
| 长期架构取舍 | `docs/harness-engineering/adr/` |
| 上线、迁移、冒烟、交接证据 | `reports/harness/` + `core/evidence-index.md` |
| 上下文要换人或续跑 | `scripts/harness_snapshot.py` + `core/agent-handoff-template.md` |

## 防重犯闭环

当发现一次值得记住的错误时，不要只修当次问题。至少补一类防线：

1. 新增或更新测试。
2. 新增或更新检查脚本。
3. 接入 pre-commit 或 CI。
4. 更新 AGENTS 或项目 Skill。
5. 更新 runbook、ADR 或验证矩阵。

然后运行：

```powershell
python scripts/check_mistake_ledger.py
```

## 证据留档

长任务、上下文切换或上线收口时运行：

```powershell
python scripts/harness_snapshot.py --trace-id <trace_id> --goal "<任务目标>" --status in_progress
```

需要归档时：

```powershell
python scripts/harness_snapshot.py --trace-id <trace_id> --goal "<任务目标>" --status completed --output reports/harness/handoff-{timestamp}.md
```

归档后在 `docs/harness-engineering/core/evidence-index.md` 登记报告路径、命令、结果、关联 LOGBOOK 和敏感数据状态。

## Skill 维护规则

- 项目规则优先写入 `.agents/skills/`，不要污染全局 Skill。
- 全局 Skill 只保留通用能力，例如 `brainstorming`、`skill-creator`、`using-superpowers`。
- 如果某个项目 Skill 的路径、阈值、文件清单或流程入口变了，必须同步 `docs/AGENTS/skill-reference.md`。
- 如果 Skill 中的约束来自一次错误或返工，把来源写入 `mistake-ledger` 或 LOGBOOK，避免规则变成无根命令。

## 收口清单

- [ ] 本轮是否有 `trace_id`，或明确说明为什么不需要。
- [ ] 相关验证是否按 verification matrix 执行。
- [ ] 证据文件是否已归档或说明无需归档。
- [ ] LOGBOOK 和项目进度清单是否同步。
- [ ] 如果出现错误，是否进入 mistake ledger 并补了机械防线。
- [ ] 如果更新了 Skill，是否同步 `docs/AGENTS/skill-reference.md`。
