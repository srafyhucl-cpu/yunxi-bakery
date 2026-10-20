# Stage 5.1 生产数据覆盖与有赞写入审计

- 审计日期：2026-10-20 11:20（Asia/Shanghai）
- 方式：只读 SSH + `sqlite3 -readonly`；未写生产库、未重启服务
- 范围：有赞 webhook、inbox 队列、会员/储值/积分、商品、订单、AI 会话、知识库、券/充值
- 结论：**有赞 webhook 接收正常，但业务处理自 2026-08-15 后停摆；生产业务数据不完整，不能视为当前经营数据。**

## 一、接口写入状态

| 项 | 实测 |
|---|---:|
| Webhook 审计总量 | 23,727 |
| 最新 webhook 接收 | 2026-10-20 11:20:41 |
| 审计状态 | processed 14,137 / received 8,911 / duplicate 657 / failed 12 / processing 10 |
| 有赞 inbox 队列 | received **16,627** / processed 5,821 / failed 50 / dead_letter 69 / processing 2 |
| 有赞队列最后 processed | **2026-08-15 05:25:41** |
| 有赞队列最后 received | 2026-10-20 03:20:41 |
| 生产服务版本 | `0.132.9`，启动于 2026-09-06 |
| 生产 schema | `_schema_version=26` |
| 当前仓库 | `0.133.0-p2trial.3`，迁移到 v048 |
| 数据库锁日志 | 2026-10-19 以来 **15,108 次** `database is locked` |
| 审计约束错误 | `CHECK constraint failed: business_type IN ('trade','item','chat','unknown')`，会员事件 `yzuser_*` 写入失败 |

判断：

- “接收”链路正常：有赞仍在推送，webhook 审计有当前时间记录。
- “处理/写业务”链路不正常：inbox 队列 16,627 条 `received`，attempt_count 为 0，worker 没有消费。
- 部分 webhook 连审计都写不进去：会员事件被旧 CHECK 约束拒绝；已由 `v048` 修复（尚未部署生产）。

## 二、业务数据覆盖

| 业务点 | 生产现状 | 判断 |
|---|---|---|
| 客户主档 | `customer_master` 24,726；创建/更新停在 **2026-08-11** | 有历史存量，8 月后新客户未写入 |
| 会员余额 | `member_balance` 62 行；储值 **0**；积分 168,102；最后更新 **2026-08-14** | 储值基本未迁；积分不完整 |
| 有赞订单 | `youzan_orders` 1,565；最后更新 **2026-09-05** | 新订单未写入 |
| 自研订单 | `orders` 5 单；最后 **2026-08-26** | 几乎没有真实成交 |
| 有赞商品 | 931 个，328 个在售；最后更新 **2026-09-05** | 库存/销量事件未落库 |
| 积分流水 | `points_ledger` 78 条，合计 2,945；最后 **2026-08-14** | 积分流水几乎为空 |
| 储值流水 | `stored_value_recharge` 0；`balance_ledger` 0 | 储值闭环未启用 |
| 券 | `coupon_templates` 0 / `coupon_inventory` 0 / `coupon_grants` 0 | 未启用 |
| AI 会话 | 33 个会话、202 条消息；最后 **2026-10-14** | 有少量使用，不足以证明生产流量 |
| 知识库 | 801 条，356 条启用；FAQ 18 / 政策 3 / 售后 3 | 基础内容有，30 条新 FAQ 未部署 |
| 新功能表 | 无每日库存、蛋糕时段、打印作业、店员账号、快捷开单等表 | v040–v047 未部署 |

## 三、缺失清单

1. 2026-08-15 之后的有赞订单、商品库存/销量、会员/积分事件仍在 inbox 中，未落业务表。
2. 储值余额与积分没有完成真实迁移；生产储值合计为 0。
3. 2026-08-12 之后的新客户/会员更新缺失。
4. 生产 schema 落后 22 个版本；打印、每日库存、时段、店员、快捷开单等业务点没有表结构。
5. 生产版本 `0.132.9` 缺少本轮已交付的修复和功能；不能把 staging 结果直接当作生产结果。

## 四、根因

1. **inbox worker 停止消费**：最后 processed 为 2026-08-15；16,627 条 received，attempt_count 为 0。
2. **SQLite 写锁**：近两日 15,108 次 `database is locked`，webhook 审计/入队失败。
3. **会员事件约束缺失**：旧 CHECK 不允许 `business_type='member'`。
4. **生产版本/schema 落后**：`0.132.9` / v26，当前代码 `0.133.0` / v48。

## 五、恢复步骤（需负责人批准维护窗口）

1. 冻结有赞 webhook 业务写入，记录当前 `_schema_version`、行数、WAL/SHM 大小。
2. 备份生产 `bot.db`（含 WAL/SHM），并做 `PRAGMA integrity_check`。
3. 在副本上演练 v027–v048 迁移；确认审计表 23,727 行不丢、`member` 可写。
4. 部署当前代码，启动 webhook worker；观察 `database is locked` 是否消失。
5. 按幂等键回放 16,627 条 inbox backlog；订单/商品/会员分别抽验。
6. 重新执行本审计；要求有赞队列 received 清零或可解释，业务表时间推进到当天。
7. 数据恢复后再做真实储值/积分迁移；旧 CSV 只能作为历史基线，不能作为当前生产快照。

## 六、当前不建议做的事

- 不要把 `stage-5.1` 的导入脚本直接指向生产。
- 不要用 2026-06-19 的旧 CSV 覆盖生产当前数据。
- 不要在未备份/未冻结窗口时重启或执行迁移。
- 不要把当前生产数据当作完整经营数据做对账结论。

## 七、已交付的代码修复

- `backend/app/migrations/v048_youzan_webhook_member_business_type.sql`：重建审计表 CHECK，加入 `member`。
- `backend/app/migrations/schema.py`：新库同步允许 `member`。
- `backend/tests/migrations/test_youzan_webhook_member_business_type.py`：旧库迁移、新库建表、非法值拒绝、索引重建测试。
- 提交：`1258808 fix(webhook): allow member business type in audit`
