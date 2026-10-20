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

1. **审计状态回写**：已回写 **1,605 条**历史 `received` 为 `processed`；当前只剩 **63 条**近期记录（全部早于 14:34，未满 24 小时阈值），未发现业务事件丢失。新 inbox 载荷已带 `audit_id`，回写后未再新增审计积压。
2. **`database is locked` 曾偶发**：积压清理期间约每分钟 1–2 次事务回滚；队列清空、清理完成后最近未见新增。仍需持续观察，确认没有静默丢事件。
3. **积分查询 API 版本已修复**：`app/service/youzan/member_api.py` 已改为 `1.0.0`，请求体改为 `user.account_type=2` + 手机号，响应按 `data.point` 解析；查不到积分时跳过镜像并记 `youzan_points_unavailable`，不再写 0。提交 `0292d8e`，已部署并重启验证。
4. **53 条 POINTS 死信已归档**：未回放，会员积分未变；其中 130****6825 是过期快照（旧 1,891 / 当前 941 / 本地 941），按有赞当前归档。
5. **券/会员卡 API 版本仍为 3.0.0**：未做生产实测，若被网关拒绝会静默返回空数据；需要单独做只读探针。
4. **`/ready` 仍为 503**：因为微信支付配置为空；在未接入微信支付前，这是预期的 degraded，不是进程故障。
5. 旧服务已 disabled；回退需手动 `systemctl stop yunxi-bakery && systemctl start yunxibakebot`，且会丢失切换后新库写入。
6. 切换前 staging 真向量并行启动曾导致服务器 OOM/失联；已由重启恢复，并改为串行切换。后续禁止再并行启动两套真向量服务。

## 六、死信与审计失败清理结果（2026-10-20 15:00）

- 74 条 dead_letter：POINTS 53、SCRM_CUSTOMER_EVENT 21。
- 已回放 **21 条 SCRM_CUSTOMER_EVENT**，worker 处理完成，inbox 只剩 **53 条 POINTS** dead_letter。
- 已把 **12 条历史 audit failed** 标记为 `skipped`（`historical_invalid_payload`），原错误信息保留、无删除。
- POINTS 53 条**已核对后归档，未回放**：
  - 44 个手机号逐个查询有赞当前积分，53/53 confirmed，0 blocked；
  - 33 superseded、14 无本地账户、5 空手机号、1 过期快照（130****6825）；
  - 全部标记 `processed`，`last_error` 写稳定原因码；
  - 归档前后 `member_balance` 1,385 行 / 2,338,480 分、`points_ledger` 4,216 条 / 197,573 分**完全不变**；
  - inbox dead_letter 从 53 降到 **0**。
- 回放工具：`backend/scripts/resolve_youzan_dead_letters.py`，提交 `2214a04`；支持 dry-run、生产路径防呆、单事务、审计-only `--skip-inbox`。
- 积分核对工具：`backend/scripts/reconcile_youzan_points_dead_letters.py`，提交 `af6f485`；直接调用 `youzan.crm.customer.points.get/1.0.0`。**注意**：`app/service/youzan/member_api.py` 的 `POINTS_QUERY_API_VERSION` 仍是错误的 `3.0.0`，会让会员导入的积分锚点写 0，需单独立项修复。

## 七、券/会员卡接口修复（2026-10-20 18:38）

- 生产只读探针确认：旧券列表 API `youzan.ump.coupon.user.coupons` **名称不存在**，任何版本都返回 4005；已改为 `youzan.ump.promocard.buyer.search` / `promocode.buyer.search` 3.0.0，并按 VALID/USED/INVALID 三状态合并去重。
- 券详情参数从 `coupon_group_id` 改为 `id`；会员卡分页从 `page_no/page_size` 改为 `page`，列表字段改为 `items`。
- 券状态映射：`VALID/CARD_TAKE → TAKE`，`USED/CARD_CONSUME → CONSUME`；无法映射的失效券不写入。
- 券模板面额/门槛按分解析，毫秒时间戳按北京时间转换；券级有效期优先于模板有效期。
- 代码提交 `60cd100`，已部署并重启；服务健康。
- 生产 69 条旧券状态已归一：`CARD_TAKE 66 → TAKE`、`CARD_CONSUME 3 → CONSUME`；`coupon_templates` 仍为 0。
- **遗留**：69 条旧券行的 title/value/template/有效期仍为空；需要按当前有赞数据做一次定向回填，否则这些旧券仍不可核销。20 个会员 dry-run 未发现当前券，不能据此证明全量。

## 八、下一步

1. 对券/会员卡 API（当前 3.0.0）做一次性只读探针，确认版本与响应字段，避免静默漏数据。
2. 补写历史审计终态，并核对会员积分/身份与有赞侧一致。
3. 继续观察 `database is locked`，必要时定位长事务与并发审计写入。
4. 配置微信支付/小程序正式参数后，重新检查 `/ready`。
5. 在切换后的生产库上重新跑数据覆盖审计，确认订单/商品/会员/积分与有赞侧一致。
6. 旧库保留为回滚快照；确认稳定后再安排清理。
7. 更新 `PROJECT-STATE` 的 Go/No-Go 结论前，仍需负责人验收。
