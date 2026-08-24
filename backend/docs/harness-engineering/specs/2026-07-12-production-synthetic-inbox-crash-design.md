# 生产合成 Inbox 崩溃恢复专项设计

## 目标

使用生产 Python 运行时、生产 SQLite 数据库和真实 `InboxRepo` 状态机，验证任务进入 `processing` 后 worker 被强制终止，lease 到期后可由新进程重领，并且最终不丢失、不重复。

## 方案选择

- 不向 `wecom`、`wecom_kf` 或 `youzan_webhook` 写入合成 payload，避免真实 worker 触发外部回复或业务处理。
- 不再次执行“无处理中消息的 systemd 崩溃”，因为它不能证明 lease 重领。
- 使用专用 `remediation_production_harness` 队列。生产服务不消费该队列，两个独立子进程通过真实 `InboxRepo` claim；第一个进程进入 `processing` 后被父进程 kill，第二个进程在 lease 到期后重领并写入 `processed`。

## 安全边界

- 必须显式提供 `--confirm-production-synthetic-inbox-crash`。
- 数据库路径必须是绝对路径，且执行前 `PRAGMA integrity_check` 必须为 `ok`。
- message key 使用 `remediation-prod-inbox-` 随机前缀；发现已有同前缀记录时拒绝执行，不清理未知运行留下的数据。
- JSON payload 只包含合成标记，不包含客户、订单、员工、群或渠道身份。
- 最终只按本次精确 message key 删除一条合成记录，并确认前缀零残留。
- 报告不输出 message key、payload 或数据库内容。

## 验收标准

1. 数据库前后完整性均为 `ok`。
2. 首次 enqueue 成功，重复 enqueue 被拒绝。
3. 第一子进程真实进入 `processing`，随后被强制终止。
4. lease 到期后第二子进程重领成功，`attempt_count=2`。
5. 最终仅有一条 `processed` 终态，pending 为零。
6. 清理后专用前缀记录为零，systemd、health 和 ready 保持正常。
