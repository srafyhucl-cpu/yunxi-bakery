# Agent Handoff Template

当任务较长、上下文即将重置、需要换 Agent，或准备让另一个 AI 继续执行时，使用本模板生成交接摘要。

## 模板

```markdown
# Agent Handoff

- trace_id:
- updated_at:
- owner:
- current_goal:
- current_status:
- branch_or_worktree:

## 已完成

-

## 当前工作区

- modified_files:
- untracked_files:
- files_intentionally_untouched:
- pre_existing_changes_not_owned:

## 关键决策

-

## API 契约状态

- docs/api-contract.md 是否已更新:
- 后端 YunxiBakeBot 是否需要同步:
- release/manual-acceptance-checklist.md 是否需要同步:

## 已验证

-

## 未验证

-

## 证据位置

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
- docs/api-contract.md
- docs/harness-engineering/README.md
- docs/harness-engineering/core/verification-matrix.md
- docs/harness-engineering/core/evidence-index.md
- docs/release/manual-acceptance-checklist.md
```

## 使用规则

- 不要把“应该没问题”写成已验证。
- 没跑的测试放在“未验证”，并说明原因。
- 如果工作区有非本轮改动，必须标注“不要覆盖”。
- 涉及支付、订单、登录、发布时，必须写清楚测试环境和证据位置。
- 涉及客户群登记时，必须写清楚 `campaignId` 来源、是否已接 Platform 后台汇总、是否做过体验版或真机打开验证。
- 如果只做文档变更，必须写清楚未运行小程序检查的原因。
