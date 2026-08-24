# 有赞客户正式迁移执行 Runbook

## 文档目的

这份 runbook 用来把当前已经落地的两条脚本链路，收成一条可重复执行的正式迁移路径：

- 审计入口：`scripts/audit_youzan_customer_migration.py`
- 正式入口：`scripts/import_youzan_customers.py`

它不再讨论 `customer master v1` 为什么这么设计，而是回答更务实的问题：

1. 迁移前先跑什么
2. 正式迁移命令怎么组织
3. 报告文件怎么留
4. `source_batch_id` 应该怎么约定
5. 同批次重跑、跨批次补跑分别会发生什么
6. 哪些情况下不应该直接执行 `--apply`

## 适用范围

- 当前仓：`Bakery Commerce Platform (Platform 仓)`
- 当前实例：`Yunxi`
- 当前来源系统：有赞客户 CSV + 有赞订单 CSV
- 当前目标：把有赞客户安全写入 `customer master v1`

## 前置条件

执行正式迁移前，至少确认下面几件事：

1. 客户 CSV 与订单 CSV 路径已经确认。
2. 目标数据库路径已经确认。
3. `customer master v1` 四表已经存在，或明确允许本次创建数据库文件。
4. 审计结果已经看过，确认 `auto_merge / new_master / pending_review` 分流稳定。
5. 已经决定本次迁移使用的固定 `source_batch_id`。

如果上面任何一项不明确，先不要执行 `--apply`。

## 两条脚本的职责分工

### 审计入口

命令：

```powershell
python scripts/audit_youzan_customer_migration.py
```

用途：

- 判断这批有赞客户是否适合进入正式迁移。
- 输出汇总、问题表、分流表和风险样本。
- 用于人工复核、字段对齐和规则确认。

### 正式入口

命令：

```powershell
python scripts/import_youzan_customers.py
```

用途：

- 读取同一批客户 / 订单 CSV。
- 复用当前审计规则生成 planned bucket summary。
- 显式 `--apply` 时将结果写入 `customer master v1`。
- 输出正式迁移报告，便于留档和补跑。

## `source_batch_id` 约定

建议不要使用脚本自动生成的默认值，正式迁移时统一显式传入。

推荐格式：

```text
youzan-customer-YYYYMMDD-<scope>
```

示例：

- `youzan-customer-20260620-full`
- `youzan-customer-20260620-vip-only`
- `youzan-customer-20260620-retry-batch-a`

约束建议：

1. 同一次正式迁移的 dry-run 和 apply 使用同一个 `source_batch_id`。
2. 如果只是同批次重跑，不要改 `source_batch_id`。
3. 如果是补新范围或新来源批次，再换新的 `source_batch_id`。

## 报告文件命名建议

建议统一写到 `reports/`，并带上 `{timestamp}` 展开：

```text
reports/youzan-customer-audit-{timestamp}.json
reports/youzan-customer-metrics-{timestamp}.csv
reports/youzan-customer-issues-{timestamp}.csv
reports/youzan-customer-buckets-{timestamp}.csv
reports/youzan-customer-import-dry-run-{timestamp}.json
reports/youzan-customer-import-apply-{timestamp}.json
```

这样做的目的：

- 不覆盖历史报告
- 方便对比 dry-run / apply
- 方便后续把证据登记到 Harness 索引

## 标准执行顺序

### 第一步：跑审计

```powershell
python scripts/audit_youzan_customer_migration.py `
  --customer-csv "docs\有赞导出\客户数据_0002000408539943.csv" `
  --orders-csv "docs\有赞导出\订单数据.csv" `
  --json `
  --output "reports\youzan-customer-audit-{timestamp}.json" `
  --metrics-output "reports\youzan-customer-metrics-{timestamp}.csv" `
  --issues-output "reports\youzan-customer-issues-{timestamp}.csv" `
  --buckets-output "reports\youzan-customer-buckets-{timestamp}.csv"
```

至少确认：

1. `pending_review_customer_count` 是否符合预期。
2. `invalid_phone_count` 是否可接受。
3. `new_master_customer_count` 是否与本次目标一致。
4. 风险样本是否需要先人工处理。

### 第二步：跑正式入口 dry-run

```powershell
python scripts/import_youzan_customers.py `
  --customer-csv "docs\有赞导出\客户数据_0002000408539943.csv" `
  --orders-csv "docs\有赞导出\订单数据.csv" `
  --db-path "data\bot.db" `
  --tenant-id "yunxi" `
  --source-batch-id "youzan-customer-20260620-full" `
  --json `
  --output "reports\youzan-customer-import-dry-run-{timestamp}.json"
```

这一步不会写库，重点看：

- `apply_ready`
- `refused_missing_database`
- `refused_unreadable_database`
- `schema_ready_before`
- `planned_total_records`
- `planned_bucket_summary`

如果这里结果不对，先停，不要继续 `--apply`。

### 第三步：显式执行 apply

```powershell
python scripts/import_youzan_customers.py `
  --customer-csv "docs\有赞导出\客户数据_0002000408539943.csv" `
  --orders-csv "docs\有赞导出\订单数据.csv" `
  --db-path "data\bot.db" `
  --tenant-id "yunxi" `
  --source-batch-id "youzan-customer-20260620-full" `
  --apply `
  --json `
  --output "reports\youzan-customer-import-apply-{timestamp}.json"
```

只有在“明确知道目标数据库本来就不存在，并且本次就是要新建它”时，才追加：

```powershell
--allow-create
```

生产已有库场景不要默认带这个参数。

### 第四步：核对 apply 报告

至少核对下面字段：

- `applied`
- `applied_total_records`
- `applied_bucket_summary`
- `actions_summary`
- `schema_ready_after`

如果报告里出现异常值，先保留证据，不要马上换新批次重跑。

## 幂等与补跑语义

### 同一 `source_batch_id` 重跑

当前行为：

- 已处理过的同批次记录会返回 `skip_existing_batch_row`
- 不会重复创建主档、快照或复核单

适用场景：

- apply 中途中断后确认是否已落库
- 同批次报告需要补留档
- 想确认脚本是否具备最低重跑安全

### 跨批次补跑

当前行为：

- 会复用既有 `youzan_customer(source_record_id)` 来源身份
- 已有手机号归并链路会继续复用
- `pending_review` 会复用既有复核记录并追加证据快照

适用场景：

- 新一批 CSV 补数
- 同一来源重新导出但归属新批次
- 后续按范围拆批迁移

## 什么时候不要直接执行 `--apply`

出现下面任一情况时，先停在审计或 dry-run：

1. `refused_unreadable_database=True`
2. `pending_review` 样本超出当前团队可处理范围
3. 手机号标准化结果明显异常
4. 目标 `db-path` 还没确认
5. 本来是已有生产库，却只能靠 `--allow-create` 才能继续

## 迁移后的最小验证

推荐至少保留下面三类证据：

1. 审计报告
2. 正式入口 dry-run 报告
3. 正式入口 apply 报告

建议再补一份批次级核对报告：

```powershell
python scripts/verify_youzan_customer_import.py `
  --db-path "data\bot.db" `
  --tenant-id "yunxi" `
  --source-batch-id "youzan-customer-20260620-full" `
  --import-report "reports\youzan-customer-import-apply-20260620-120000.json" `
  --json `
  --output "reports\youzan-customer-import-verify-{timestamp}.json"
```

这一步会核对：

- 当前批次实际快照数
- 当前批次命中的主档数
- 来源身份数
- 手机号身份数
- 关联复核单数
- 批次分流汇总
- 与 apply 报告中的 total / bucket summary 是否一致

如果本次迁移接近生产同步，还建议追加：

```powershell
python scripts/preflight_production.py --json --output reports/preflight-after-{timestamp}.json
python scripts/smoke_test.py --json --output reports/smoke-after-{timestamp}.json
```

## 当前已验证的关键行为

当前仓内已经有测试覆盖：

- dry-run 不写库
- 显式 `--apply` 才写库
- `--output` 必须配合 `--json`
- 同批次重跑返回 `skip_existing_batch_row`
- 跨批次复用来源身份与复核记录
- 迁移后可按 `source_batch_id` 自动核对批次汇总，并可选对比 import report

对应测试入口：

- `tests/scripts/test_import_youzan_customers.py`
- `tests/scripts/test_audit_youzan_customer_migration.py`
- `tests/scripts/test_verify_youzan_customer_import.py`
- `tests/service/test_customer_import_service.py`

## 关联文档

- [Customer Master v1](./customer-master-v1.md)
- [有赞客户迁移审计清单](./youzan-customer-migration-audit-checklist.md)
- [项目进度与配置清单](../../项目进度与配置清单.md)
