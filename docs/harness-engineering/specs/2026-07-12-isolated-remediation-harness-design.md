# 隔离本地整改 Harness 设计

> trace_id: `20260711-global-risk-remediation`
> 约束来源: ADR 0005、ADR 0006、全局风险整改与框架收敛计划

## 目标

提供一个可重复执行、完全隔离的本地整改入口，使用生产同构的认证、API、服务、仓库、SQLite schema 和 inbox lease 语义验证两条风险链：

1. 合成主体通过真实 Bearer JWT 调用主体导出和删除 API，关联数据被清理且 consent 保留 `revoked`。
2. 合成 inbox 消息由独立子进程认领；父进程终止子进程后，新连接在 lease 到期时重领，并证明最终只进入一次成功终态。

## 边界

- 不访问生产服务、生产数据库、微信登录接口或外部 LLM。
- 不使用 legacy 用户头作为认证捷径；运行时生成隔离 JWT secret。
- 合成数据使用固定前缀，不包含真实手机号、地址、订单号或客户标识。
- `--work-dir` 必须显式提供；SQLite、WAL 和 SHM 文件结束后逐个删除。
- 报告只输出检查名称、布尔结果和失败原因，不输出导出正文或消息 payload。
- 本 Harness 是生产同构的隔离验证，不替代真实生产账号和真实生产消息专项。

## 数据流

主体删除链：

```text
生成隔离 JWT -> FastAPI privacy router -> PrivacyLifecycleService
-> PrivacyRepo -> 完整 SQLite schema -> 删除断言 / revoked 断言
```

消息崩溃链：

```text
InboxRepo.enqueue -> 子进程 claim(processing) -> 父进程 kill
-> lease 到期 -> 新连接 claim(attempt=2) -> mark_processed
-> duplicate enqueue 被拒绝 -> pending=0
```

## 验收

- CLI 返回 0，JSON 报告 `status=passed`、`failed=0`。
- 主体导出和删除均为 HTTP 200，所有合成关联记录归零，consent 为 `revoked`。
- 子进程确实被终止，消息由新连接重领且 `attempt_count=2`，最终仅一条 `processed` 记录。
- 工作目录不存在遗留 `.db`、`.db-wal` 或 `.db-shm` 文件。

## 职责评审

主脚本同时编排主体删除和消息崩溃两条场景，但它们共享临时数据库生命周期、无敏感报告合同和“子进程重新调用同一 CLI”的 worker 协议。当前保持一个脚本可避免跨模块传递数据库所有权和隐藏 worker 参数；场景内部已经拆为独立函数。后续只有新增第三类风险链或任一场景形成独立复用入口时，才按稳定职责拆模块。
