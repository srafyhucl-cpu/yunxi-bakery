# Stage 5.2 生产完整升级切换记录

- 切换日期：2026-10-20 13:13:41–13:14:00（Asia/Shanghai）
- 目标：把生产从旧仓库 `yunxibakebot`（0.132.9，schema v26）切换到当前仓库 `yunxi-bakery`（0.133.0，schema v48）
- 方式：停旧服务 → 冻结备份 → 新库副本 → 启动新服务；**未并行运行两套真向量服务**

## 一、切换前备份

| 文件 | 说明 |
|---|---|
| `/opt/apps/backups/20261020-pre-v2/bot.db` | 切换前生产库，integrity_check=ok，schema v26 |
| `/opt/apps/backups/20261020-pre-v2/old-code.tar.gz` | 旧代码、配置、systemd 单元备份 |
| `/opt/apps/backups/20261020-pre-v2/old.env` | 旧环境变量 |
| `/opt/apps/backups/20261020-cutover/bot.db` | 停旧服务后冻结库，schema v26，23,814 条 webhook 审计 |

## 二、切换结果

| 项 | 结果 |
|---|---|
| 新服务 | `yunxi-bakery.service`，active / enabled |
| 旧服务 | `yunxibakebot.service`，stopped / disabled |
| 访问端口 | 7001（Nginx 无需改动） |
| `/health` | 200，版本 `0.133.0-p2trial.3` |
| `/ready` | 503 degraded；唯一业务缺项为 `wechat_pay_configured=false`，其余检查通过 |
| 数据库 schema | **48**（v027–v048 迁移已完成） |
| 新库 | `/opt/apps/yunxi-bakery/backend/data/bot.db` |
| 管理端静态资源 | 已构建并复制到 `backend/web/admin/dist` |
| 向量模型 | `BAAI/bge-small-zh-v1.5` 已加载，item webhook 向量写入成功 |

## 三、切换后数据恢复（快照 13:51:31）

| 项 | 数值 |
|---|---:|
| inbox `processed` | 22,696 |
| inbox `received` | **0（已清空）** |
| inbox `dead_letter` / `failed` | 74 / 0 |
| 有赞审计 processed / received | 21,730 / 1,661 |
| 有赞订单 | 2,596，最后更新 13:50:28 |
| 有赞商品 | 1,076，最后更新 13:50:25 |
| 会员余额行 | 1,376 |
| 会员积分合计 | 2,333,390 |
| 积分流水 | 4,204 条，合计 197,255 |
| 最新 webhook 审计 | 2026-10-20 13:45:48 |

结论：有赞订单、商品、会员/积分已恢复写入；inbox 业务队列已清空。

**审计状态核对**：13:31 后一度看到 51 条审计行停留在 `received`；逐条关联 inbox 后确认它们都有对应的 `youzan_webhook:<msg_id>` 行，最终状态为 `processed`（当前剩余 17 条，全部对应 processed inbox）。**未发现业务事件丢失**；剩余问题只是审计状态回写滞后，需要后续补记。

## 四、本次部署包含的修复

1. `v048_youzan_webhook_member_business_type.sql`：审计表 CHECK 加入 `member`，解决 `yzuser_*` 审计写入失败。
2. `event_handler`：组装根以 `db=None` 构造时，运行时从 `db_conn_var` 解析连接，解决 `'NoneType' object has no attribute 'in_transaction'`。
3. `member_balance_repo.mirror_youzan_points`：空手机号且不存在既有账户时跳过积分镜像，避免 `UNIQUE constraint failed: member_balance.mobile` 反复失败。
4. `yunxi-bakery.service` 增加 `TimeoutStopSec=20`，避免 worker 积压时重启无限等待。

## 五、已知问题（未清零）

1. **审计状态回写滞后**：17 条 `received` 审计行全部有对应 `processed` inbox，未发现业务事件丢失；需要补写审计终态并排查重复回调导致的 received 状态。
2. **`database is locked` 曾偶发**：积压清理期间约每分钟 1–2 次事务回滚；队列清空后最近未见新增。仍需定位长事务/并发审计写入，确认没有静默丢事件。
3. **dead_letter 74 条、webhook failed 12 条**：多数为切换前遗留；需逐条查看后回放或标记。
4. **`/ready` 仍为 503**：因为微信支付配置为空；在未接入微信支付前，这是预期的 degraded，不是进程故障。
5. 旧服务已 disabled；回退需手动 `systemctl stop yunxi-bakery && systemctl start yunxibakebot`，且会丢失切换后新库写入。
6. 切换前 staging 真向量并行启动曾导致服务器 OOM/失联；已由重启恢复，并改为串行切换。后续禁止再并行启动两套真向量服务。

## 六、下一步

1. 补写 17 条滞后审计终态，并核对会员积分/身份与有赞侧一致。
2. 统计并处理 74 条 dead_letter 与 12 条 audit failed。
3. 处理 `database is locked`：定位长事务与并发审计写入，必要时增加重试/缩短事务。
4. 配置微信支付/小程序正式参数后，重新检查 `/ready`。
5. 在切换后的生产库上重新跑数据覆盖审计，确认订单/商品/会员/积分与有赞侧一致。
6. 旧库保留为回滚快照；确认稳定后再安排清理。
7. 更新 `PROJECT-STATE` 的 Go/No-Go 结论前，仍需负责人验收。
