# Agent Handoff Template

当任务较长、上下文即将重置、需要换 Agent，或准备让另一个 AI 继续执行时，使用本模板生成交接摘要。

______________________________________________________________________

## 模板

```markdown
# Agent Handoff

- trace_id:
- updated_at:
- owner:
- current_goal:
- current_status:

## 已完成

- 

## 当前工作区

- modified_files:
- untracked_files:
- files_intentionally_untouched:

## 关键决策

- 

## 已验证

- 

## 未验证

- 

## 风险

- 

## 下一步

1. 
2. 
3. 

## 参考入口

- AGENTS.md
- LOGBOOK.md
- docs/harness-engineering/README.md
- docs/harness-engineering/core/verification-matrix.md
```

______________________________________________________________________

## 使用规则

- 不要把“我感觉应该没问题”写成已验证。
- 没跑的测试放在“未验证”，并说明原因。
- 如果工作区有非本轮改动，必须标注“不要覆盖”。
- 涉及生产或数据库写入时，必须写清楚 dry-run 和 apply 状态。

______________________________________________________________________

## 自动生成

可用脚本生成当前工作区交接快照：

```powershell
python scripts/harness_snapshot.py --trace-id 20260611-example --goal "说明当前任务" --status in_progress
```

需要机器可读归档时：

```powershell
python scripts/harness_snapshot.py --json --output reports/harness/handoff-{timestamp}.json
```
