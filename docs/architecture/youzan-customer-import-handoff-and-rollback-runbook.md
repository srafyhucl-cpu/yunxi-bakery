# 有赞客户迁移交接与回滚 Runbook

## 文档目的

这份 runbook 只解决一件事：当有赞客户正式迁移已经开始、或者已经完成 `--apply` 之后，现场应该怎么停、怎么判、怎么交接、怎么恢复。

它不替代正式迁移 runbook，也不提供“一键回滚脚本”。它更像一份事故处理和交接说明，回答下面这些问题：

1. 出现异常时先停在哪里
2. 哪些情况可以继续同批次重跑
3. 哪些情况必须换 `source_batch_id`
4. 哪些情况只能走备份恢复或人工补偿
5. 交接给下一位人时要带哪些证据

## 适用范围

- 当前 `Platform` 代码仓路径：`YunxiBakeBot`
- 当前实例：`Yunxi`
- 当前主档：`customer master v1`
- 当前正式迁移入口：`scripts/import_youzan_customers.py`
- 当前后验核对入口：`scripts/verify_youzan_customer_import.py`

## 和正式迁移 runbook 的关系

这份文档只覆盖“出事之后怎么处理”，不重复正式迁移步骤。

- `docs/architecture/youzan-customer-formal-import-runbook.md`
  - 负责标准执行顺序：审计、dry-run、apply、verify
- 本文档
  - 负责异常中止、交接、回滚判断和证据留档

如果还没开始 `--apply`，优先回到正式迁移 runbook。

## 先停在哪里

出现以下任一情况时，先停，不要继续往下补跑：

1. `verify` 报告与 `apply` 报告的 `total` 或 `bucket summary` 不一致
2. `apply` 过程中中断，无法确认已经写入了多少批次
3. 目标数据库路径不确定
4. 发现本次 `source_batch_id` 用错了
5. 发现本次导入文件并不是预期来源文件
6. `--allow-create` 被误加到了一个本该已有数据的目标库上

第一动作不是删数据，而是保留证据。

## 先保留什么证据

最少保留下面四类信息：

1. 迁移命令行
2. `apply` / `verify` 报告文件
3. 目标数据库路径
4. 当前工作区状态和 `LOGBOOK` 最新条目

建议直接生成交接快照：

```powershell
python scripts/harness_snapshot.py --trace-id 20260620-customer-import-handoff --goal "有赞客户迁移交接与回滚" --status in_progress
```

如果需要留档：

```powershell
python scripts/harness_snapshot.py --trace-id 20260620-customer-import-handoff --goal "有赞客户迁移交接与回滚" --status completed --output reports/harness/handoff-{timestamp}.md
```

## 能继续重跑的情况

下面这些情况，通常可以先用同一个 `source_batch_id` 继续跑，不要急着换批次：

1. `apply` 中途断掉，但确认还是同一批文件
2. `verify` 报告还没生成完整，但 `apply` 已经结束
3. 只是报告文件丢了，需要补留档
4. 同一批次只是想重新确认幂等性

处理方式：

1. 先跑 `dry-run`
2. 再跑 `verify`
3. 必要时重复同一 `source_batch_id` 的 `apply`

因为当前导入链路已经做了批次级幂等控制，同批次重复执行不应该重复写入同一批来源行。

## 必须换批次的情况

下面这些情况，不建议继续沿用旧的 `source_batch_id`：

1. 这次实际导入的来源范围已经变了
2. 这次使用的是另一份 CSV
3. 这次是补充一个新的来源子集
4. 这次需要和原批次做并行对比

推荐做法是保留原批次证据，新批次重新命名，避免把两次执行混成一次历史。

## 不能直接回滚的情况

当前仓内没有一键物理回滚工具时，下面这些情况不要尝试手工删表或批量删行：

1. 已经写入正式目标库，而且数据关系已经开始被其他流程消费
2. 无法确认哪些 `customer_master`、`identity_link`、`snapshot`、`review` 是本次批次写入的
3. 迁移动作已经和后续人工操作混在一起

这类场景应该走三选一：

1. 数据库备份恢复
2. 只读保留现状，改走补偿批次
3. 人工复核后分批修正

## 恢复优先级

### 场景 A：只是脚本或报告问题

优先级：

1. 重新跑 `dry-run`
2. 重新跑 `verify`
3. 补留档

不需要动数据库。

### 场景 B：同批次 apply 中断

优先级：

1. 保留中断现场证据
2. 用同一 `source_batch_id` 重新跑 `dry-run`
3. 重新跑 `apply`
4. 再跑 `verify`

### 场景 C：写入了错误目标库

优先级：

1. 立即停止继续操作
2. 记录错误数据库路径和命令
3. 先找数据库备份或隔离副本
4. 再决定是恢复、补偿还是人工清理

### 场景 D：结果写对了，但业务口径不对

优先级：

1. 不回滚物理数据
2. 保留当前结果
3. 用新批次补一版修正导入
4. 把旧批次标记为历史错误批次

## 交接包清单

把下面内容一起交给下一位接手人：

- 迁移目的
- 当前批次 `source_batch_id`
- 客户 CSV 和订单 CSV 文件路径
- `db-path`
- `apply` 报告
- `verify` 报告
- 是否曾经使用 `--allow-create`
- 当前是否已经写入正式目标库
- 当前最担心的风险点

## 什么时候需要升级处理

如果出现以下任一情况，别继续猜，直接升级给人工确认：

1. 你不确定这批数据有没有被重复写入
2. 你不确定目标数据库是不是正式库
3. 你不确定当前应该保留哪个批次为主
4. 你不确定是否应该恢复备份而不是继续补跑

## 与现有文档的分工

- [有赞客户正式迁移执行 Runbook](./youzan-customer-formal-import-runbook.md)
  - 标准迁移步骤
- [有赞客户迁移审计清单](./youzan-customer-migration-audit-checklist.md)
  - 迁移前审计和字段口径
- [Customer Master v1](./customer-master-v1.md)
  - 主档设计基线
- [项目进度与配置清单](../../项目进度与配置清单.md)
  - 当前状态和阶段记录
- [Agent Handoff Template](../harness-engineering/core/agent-handoff-template.md)
  - 交接摘要结构

## 结论

正式迁移完成后，优先级顺序是：

1. 先停住
2. 先保留证据
3. 先跑 verify
4. 再决定同批次重跑、换批次补跑，还是备份恢复

当前仓内不承诺一键回滚，只承诺有清晰的停机、交接和恢复判断路径。
