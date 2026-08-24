# ADR 0006：单机阶段 SQLite 持久 Inbox 例外

- status: accepted
- date: 2026-07-11
- trace_id: 20260711-global-risk-remediation
- decision_owner: project owner / AI (Codex)
- related_docs:
  - `docs/architecture/global-risk-remediation-and-framework-convergence-plan.md`
  - `docs/harness-engineering/adr/0005-framework-first-single-path.md`

## Context

R2-B 要求 webhook 先持久化再 ACK，并支持 lease、重试、dead-letter 和重启恢复。当前生产约束仍是单机 SQLite，尚未批准 Redis 或独立 worker 基础设施；继续使用进程内 `asyncio.Queue` 会在队列满、进程退出或服务重启时丢失入站消息。

## Decision

在单 worker、单机 SQLite 阶段，采用 `inbox_events` 作为持久入站任务账本，属于 ADR 0005 所允许的窄基础设施例外：

- 入队先写数据库，数据库成功后才向渠道返回成功；重复 `message_key` 幂等接受。
- worker 使用数据库 lease 原子 claim，处理成功写 `processed`，失败按上限重试，最终进入 `dead_letter`。
- lease 到期任务可由新 worker 重领；停止时持久 worker 等待当前任务和可认领任务 drain 后退出。
- 该表只承载持久业务事件，不演变为第二套通用消息框架；未来引入成熟持久任务框架时，删除本 adapter、迁移未完成任务并保留状态核对报告。
- 在 R2 完成前继续禁止多 worker 和水平扩容。

## Alternatives

- Dramatiq/Redis：长期能力更完整，但当前需要新的生产基础设施、运维和数据边界，不作为本列车的即时依赖。
- 继续使用内存队列：改动最小，但无法证明 ACK 后消息可恢复，拒绝。

## Consequences

- 企微两条队列获得可恢复的入队、lease、有限重试和 dead-letter 状态。
- SQLite 写入和 worker drain 增加运行时开销；单 worker 和数据库容量监控仍是硬约束。
- 有赞 webhook 路由闭包尚需接入同一持久 dispatch；R2 完成前本 ADR 不宣称所有渠道已收口。

## Verification

- `InboxRepo` 测试证明重复入队、lease 重领、失败上限和 processed 终态。
- 企微队列测试证明实例重启可恢复消息，重复渠道推送不产生第二条 inbox 记录。
- R2 完成前必须补有赞持久 dispatch、并发 100 次、shutdown drain 和发送失败恢复测试。
