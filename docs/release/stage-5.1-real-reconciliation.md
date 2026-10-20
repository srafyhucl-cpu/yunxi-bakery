# Stage 5.1 真实有赞客户导出对账报告

- 日期：2026-10-20
- 数据源：`D:\Project\YunxiBakeBot\docs\有赞导出\客户数据_0002000408539943.csv`（只读）
- 源文件 sha256：`3e23cc224466dbcd…`（完整值见临时报告）
- 执行方式：本地 staging 库，生产库零写入
- 口径：储值余额暂全部按本金入账，`bonus_fen=0`；后续再按有赞明细补齐本金/赠送金

## 一、源数据规模

| 项 | 数值 |
|---|---:|
| 客户总行数 | 24,726 |
| 有效手机号 | 13,550 |
| 空手机号 | 10,932（余额全 0） |
| 非法手机号 | 244（余额全 0） |
| 重复手机号 | 0 |
| 非零储值账户 | **491** |
| 储值总额 | **40,213,332 分 = 402,133.32 元** |
| 有效手机号积分账户 | **8,547** |
| 有效手机号积分总额 | **6,016,981 分** |
| 全表积分（含无有效手机号） | 6,019,949 分 |
| 积分未导入（无有效手机号） | 33 户 / 2,968 分 |

## 二、staging 导入结果

- staging 库：系统临时目录 `stage5/youzan_staging.db`（未进仓库）
- 储值批次：`applied`，491/491 行
  - applied total：40,213,332 分
  - `principal_variance_fen=0`
  - `bonus_variance_fen=0`
  - `variance_fen=0`
- 积分镜像：8,547/8,547，无失败
- 独立交叉核对：
  - `member_balance` 8,576 行
  - `bonus_fen != 0`：0 行
  - `principal_fen + bonus_fen != stored_value_fen`：0 行
  - `points != youzan_points_base`：0 行
  - `balance_ledger` 491 条，合计 40,213,332 分，全部 `source=import`
  - 重复幂等键：0
- 二次 apply：复用同一批次，未重复加款
- 回滚演练（staging 副本）：余额/流水恢复，客户主档保留；**积分镜像不会随余额批次回滚**

## 三、逐会员对账

| 项 | 源 | staging | 差异 |
|---|---:|---:|---:|
| 非零余额账户 | 491 | 491 | 0 |
| 余额总额（分） | 40,213,332 | 40,213,332 | 0 |
| 逐会员差异 | — | — | 0 |
| 积分账户 | 8,547 | 8,547 | 0 |
| 积分总额 | 6,016,981 | 6,016,981 | 0 |
| 多余账户 / 失败手机号 | — | — | 0 / 0 |

**结论：491 个非零账户全部一致，不是抽样结论；随机 30 户抽验也全部一致。**

## 四、异常与未导入项

1. **空号 10,932 + 非法号 244**：不导入，余额均为 0；其中 33 户带 2,968 积分，因无有效手机号无法建档，需业务补手机号或按 openid 另行处理。
2. **订单未导入**：本轮只对储值/积分。订单文件 10,048 单；买家手机号有 2 个不在客户文件（各 3 单），不建会员、不分配余额；客户日后通过手机号认领时按 0 余额/0 积分建档。
3. **收货人手机号**：491 个不在客户文件，属于配送联系人，不能当会员导入。
4. **生产库现状**：`customer_master` 24,726；`member_balance` 62 行、储值合计 0、积分 168,102；`youzan_orders` 1,565；`balance_ledger` 0；生产库尚未执行 v039/v040 迁移（缺 `principal_fen/bonus_fen` 列）。
5. **生产重叠账户**：生产已有 62 行 `member_balance`，真实 apply 前必须先列冲突并逐条处置，不能直接覆盖。
6. **本金/赠送金**：本轮全额按本金，退款/赠送金语义与有赞不同；后续需补有赞储值明细后重分类。

## 五、生产切换前必须做

1. 冻结导出快照，记录 sha256 与导出时间；
2. 备份生产 `bot.db`（含 WAL/SHM），记录行数；
3. 在生产库**副本**上跑 `--apply` / `--verify`，要求 0 差异；
4. 列出生产已有 62 行账户冲突清单，逐条处置；
5. 生产窗口内执行迁移 + 导入，使用同一份归一化 CSV；
6. 生产 `--verify` 必须 0 差异，并人工抽验储值支付/积分抵扣/退回；
7. 余额回滚用导入批次 `rollback`；积分回滚需按导入前快照手工还原；
8. 负责人批准后才能切换权威/开放真实用户。

## 六、复现命令

```powershell
python backend/scripts/reconcile_youzan_customer_export.py `
  --source "D:\Project\YunxiBakeBot\docs\有赞导出\客户数据_0002000408539943.csv"

python backend/scripts/reconcile_youzan_customer_export.py `
  --source "D:\Project\YunxiBakeBot\docs\有赞导出\客户数据_0002000408539943.csv" `
  --apply --staging-db "$env:TEMP\stage5\youzan_staging.db"

python backend/scripts/reconcile_youzan_customer_export.py `
  --source "D:\Project\YunxiBakeBot\docs\有赞导出\客户数据_0002000408539943.csv" `
  --verify --staging-db "$env:TEMP\stage5\youzan_staging.db"
```

报告与 staging 库均落在系统临时目录，不提交真实 CSV、完整手机号或 staging 数据库。
