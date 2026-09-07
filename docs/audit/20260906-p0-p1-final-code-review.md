# P0/P1 最终代码复核报告（2026-09-06 第二轮）

- task_id: `T-AUDIT-REMEDIATION-20260906`
- trace_id: `20260906-audit-remediation-final`
- owner: `OpenCode`
- status: `active`
- status_label: 进行中（active）
- 基线提交: `220a8fe0dcd1126dfe43e3745667a3f7f58fc262`
- 依据: `docs/audit/20260905-project-comprehensive-audit.md`、
  `docs/audit/20260906-audit-remediation-final-review.md`、
  本轮任务指令（P0-1..P0-6、P1-1..P1-5）

本轮不采信上一轮“通过”结论，对工作区逐项重验，发现新规差距后先写
失败测试再实现。本报告每项分别记录代码验证、模拟运行验证、
真实运行验收、证据、残余风险。

## P0-1 支付/退款通知状态机与原子认领

- 代码验证：通过。`backend/app/service/order/notify_intake.py`
  实现 `claim_notify(event_id, payload, lease_seconds)`：
  只有 `processed` 返回 `duplicate`；`received`、到期 `processing`、
  退避到期 `failed` 可重认领；有效租约内 `processing` 返回忙；
  `dead_letter` 返回 `dead` 不自动认领；`complete_notify`/`fail_notify`
  必须校验 `claim_token=attempt_count` 与租约有效性，陈旧提交拒绝。
  `payment_runtime` 主通知链路改用认领流；业务异常随调用方事务回滚，
  不留半完成 intake。
- 模拟运行验证：通过。13 项新测试
  `backend/tests/service/order/test_p0_final_claim_idempotency_20260906.py`
  中 P0-1 部分 5 项通过（含并发单胜者、陈旧 token、退避到期重认领）。
- 真实运行验收：未验证（无真实微信通知重放）。
- 证据：新测试文件；定向套件全绿。
- 残余风险：`dead_letter` 在支付路径当前不可达（无自动转死信计数），
  依赖微信侧重试耗尽；后续可按 attempt 上限补自动转死信。

## P0-2 退款回调确认语义

- 代码验证：通过。`refund_notification.py` 新增结构化 `kind`
 （`acknowledged`/`retryable`/`rejected_recorded`/`duplicate`，
  旧 `rejected`/`duplicate` 键保留兼容）；API 层
  `refund_result_to_http_status` 对终态一律映射 200 成功确认，
  只有非终态返回 400；`ValueError`（签名无效、系统异常）仍 400 触发重试。
- 模拟运行验证：通过。新测试断言交易号不一致建案且 kind 正确、
  三类终态映射 200；存量退款测试（全额/部分/超额/重复）全过。
- 真实运行验收：未验证（无真实退款回调）。
- 证据：新测试 2 项；`test_refund_notification.py` 全过。
- 残余风险：签名无效报文返回 400 会引起微信重试，重试幂等安全但浪费；
  如微信提供拉黑机制可后续优化。

## P0-3 退款三腿补偿事务

- 代码验证：通过。`apply_refund_notify`/`apply_refund_query`
  新增显式 `async with order_repo.transaction()` 统一 UoW
  （外层应用事务存在时经 savepoint 嵌套，同一连接同一事务）；
  移除 `coupon/payment.py` 快照路径内部 `commit`；
  关键路径仓储（券库存、积分、余额、订单、退款事件、对账）均无内部提交。
  三腿幂等键按订单维度绑定。
- 模拟运行验证：通过。新测试“第二腿失败整体回滚”断言事件与首腿痕迹
  零残留；三腿分别失败/CAS/重复/乱序/并发/累计/超额由存量
  `test_refund_notification.py` 与 `test_coupon_payment.py` 覆盖，全过。
- 真实运行验收：未验证（无真实退款资金）。
- 证据：新测试 1 项；定向套件全绿。
- 残余风险：部分退款腿补偿仍转人工案件（设计如此）；券 `consume` 路径
  savepoint 兼容分支保留观察。

## P0-4 储值/积分幂等主体

- 代码验证：通过。新增 `app/service/idempotency.py`
 （`IdempotencyConflict(ValueError)`、请求指纹、主体/业务/金额三重校验）；
  储值与积分 `credit`/`deduct` 重放返回原流水 `balance_after/total`，
  同键异主/异业/异额抛冲突；迁移 `v033` 增加 `request_fingerprint` 列
  （幂等 runner，历史空指纹仍按明文字段比对兼容）。
- 模拟运行验证：通过。新测试 3 项（跨账户、原结果重放、积分异业/异额）；
  存量 `test_asset_atomic_idempotent.py` 8 项全过（含双连接并发单胜者）。
- 真实运行验收：未验证（无真实资金）。
- 证据：新测试；迁移文件；定向全绿。
- 残余风险：历史流水无指纹，仅明文字段比对；并发占位竞争失败路径抛
  RuntimeError（调用方需重试），语义已在测试中固定。

## P0-5 金额精确合同

- 代码验证：通过。`yuan_to_fen` 新增非负/有限数值拒绝；
  新增 `fen_to_yuan_str` 规范十进制边界适配器并用于订单创建与有赞解析
  的 REAL 传输边界；支付查询金额比较由“小于才异常”改为严格不等即异常；
  金额静态守卫更新为仅放行 `float(fen_to_yuan_str(...))` 规范形态。
- 模拟运行验证：通过。新测试（严格相等少付/多付拒绝、1 分/半分/非法/
  负数/往返）；存量 `test_money_contract.py` 全过。
- 真实运行验收：未验证（无真实支付金额）。
- 证据：新测试 2 项；守卫更新。
- 残余风险：`orders.total_amount` 等 REAL 列仍为传输形态，整数分列迁移
  未执行（计划见 `fen_to_yuan_str` 文档）；展示格式化维持现状。

## P0-6 企微同步租约两段式

- 代码验证：通过。新增 `v031` 租约表与 `WecomKfSyncLeaseRepo`
  （单语句原子占位/接管/释放）；`handle_callback` 改为短事务取租约 →
  事务外拉取与无账本分类 → 短事务校验 token 与基准游标后提交账本、
  收件箱、游标并释放；拉取失败只记失败不推进；分页截断保存延续状态；
  分类器支持 `dry_run`，账本以终态事务内 `commit_ledger_pendings` 为准。
- 模拟运行验证：通过。存量 25 项同步测试全过；新测试 5 项
  （并发互斥、过期接管、失败释放、截断延续、陈旧凭证拒绝）。
- 真实运行验收：未验证（无真实企微回调）。
- 证据：新测试文件 P0-6 部分；迁移 `v031`。
- 残余风险：慢网络下租约可能过期被接管，原持有者提交时回滚重拉，
  消息不丢但延迟；租约时长 300 秒可按运维观测调优。

## P1-1 外发投递合同

- 代码验证：通过。`v032` 增加 `content_hash`；认领时同键异内容抛错；
  文本/卡片统一计算内容哈希；移除卡片直发分支（缺上下文直接拒绝）；
  欢迎语/事件响应新增 `send_event_guarded` 统一入账本；unknown 不重发，
  仅人工重排。
- 模拟运行验证：通过。新测试 3 项（哈希冲突、未知不重发+重排、
  欢迎语入账）；卡片测试已迁移至账本上下文；wecom 全域通过。
- 真实运行验收：未验证（无真实发送；供应商 msgid 是否去重无项目内
  可验证依据，不宣称 exactly-once，本地账本按至少一次+未知态治理）。
- 证据：迁移 `v032`；新测试；更新后的卡片测试。
- 残余风险：同上，exactly-once 不可证；并发首发竞态下败者转 unknown，
  由胜者终态覆盖收敛。

## P1-2 生产身份与配置 fail-closed

- 代码验证：通过。`WECOM_EMPLOYEE_AUTH_REQUIRED` 默认值改为 `True`；
  关闭只能显式配置；readiness 新增 `edge_protection_shared_ready`，
  preflight 与 startup 共用同一判定函数（`is_edge_protection_shared`/
  `assert_edge_protection_ready`），无口径漂移。
- 模拟运行验证：通过。新默认值断言；渠道 readiness 精确字典测试已同步；
  员工鉴权定向测试已补企业 ID 显式配置；preflight 开发配置下 4 项
  预期阻断（`handoff_staff_userid_ready`、`wecom_employee_auth_ready`、
  `mock_payment_disabled`、`wechat_pay_configured`），退出码 1。
- 真实运行验收：未验证（无真实员工身份与接手人）。
- 证据：preflight JSON（`D:/Temp/yunxi-audit-final-20260906/preflight-final.json`）。
- 残余风险：本地 `.env` 未显式关闭鉴权时员工机器人调用将被拒绝，
  属预期 fail-closed，需开发者显式配置（不得提交 `.env`）。

## P1-3 多实例边缘防护

- 代码验证：通过。后端抽象：`sqlite`=显式本地单机，
  `redis`=共享（Lua 原子脚本，按需引入，缺依赖/缺地址即 `ConfigError`）；
  `EDGE_REQUIRE_SHARED=true` 时无共享后端则启动与预检失败；
  `extract_client_ip` 增加非法 IP 回退，默认零信任。
- 模拟运行验证：通过。新测试 6 项（默认本地、缺共享 fail-closed、
  缺地址 fail-closed、伪造头回退、非法 IP 回退）；存量共享存储测试通过。
- 真实运行验收：未验证（无 Redis、无双实例）。
- 证据：新测试文件；`edge_protection_redis_repo.py`（Lua 脚本内联）。
- 残余风险：Redis 依赖未安装、生产共享存储未选型部署；
  多机防护在 Redis 落地前不存在，SQLite 不得用于多机。

## P1-4 凭证、上传、网络与部署

- 代码验证：通过。有赞凭证经唯一 `build_api_url` 构造点、
  异常与日志脱敏（存量隔离测试通过）；上传保留魔数/维度/像素预算校验，
  本轮补临时写入加原子发布；compose 保持回环绑定；部署脚本 trap 与
  自动回滚三路演练通过（退出码 0）。
- 模拟运行验证：通过。上传测试、部署演练、compose 守卫（存量）通过。
- 真实运行验收：未验证（生产回滚未演练）。
- 证据：演练输出（`D:/Temp/yunxi-audit-final-20260906/drill.txt`）；
  凭证扫描（路径+指纹，见下）。
- 残余风险（负责人动作）：`backend/scripts/test_youzan_product_feasibility.py`
 （git 已跟踪）第 9-11 行硬编码真实有赞 došlo `client_id`/`client_secret`/
  `kdt_id` 字面量。未读取真实值。要求：轮换该应用密钥、改脚本走环境变量、
  评估历史泄露面。本地 `backend/.env` 未入库（已忽略），若曾进入共享环境
  同样需要轮换，由负责人确认。

## P1-5 AI 不可信输入隔离

- 代码验证：通过。知识库、会话摘要已有不可信界定；本轮补画像
  `render_customer_profile` 不可信块与工具优先声明；工具侧身份鉴权存量
  回归通过。
- 模拟运行验证：通过。新增画像隔离测试；存量红队静态测试通过。
  真实模型红队：未执行（明确区分记录）。
- 真实运行验收：未验证。
- 证据：新测试 1 项。
- 残余风险：提示词隔离为纵深一层，不能替代工具侧校验与真实模型红队。

## 第二轮复核（复核方 8 项阻断）

复核结论：上一轮整改不能判定为完成。以下 8 项已按“先失败测试后实现”
逐项修复，业务定向测试通过；全量测试未通过（环境前置缺失，见门禁节）。

### P0-1 组合支付预下单失败回滚

- 代码验证：通过。`prepare_combined_payment` 改为先构造剩余支付会话
  再进事务扣款；预下单失败时余额未动、订单仍未支付，可自然重试；
  事务内复验状态，CAS 冲突回滚。
- 模拟运行验证：通过。新测试预下单失败后余额与未支付态不变。
- 真实运行验收：未验证。
- 证据：`test_review2_pay_combined_refund_20260906.py::test_p01_combined_prepay_failure_rolls_back`。
- 残余风险：会话预建后扣款失败会留下孤儿预下单（微信侧过期作废，无资金影响）。

### P0-2 退款金额合同补齐

- 代码验证：通过。Normalizer 统一合同：交易号必填、金额非负正数、
  `refund<=total`、`payer_refund<=payer_total`、`payer_refund<=refund`
 （查询报文无 payer 口径时只校验 total/refund）；Service 层追加
  `total` 与订单总额一致校验，不一致建案确认不入账；交易号恒比较。
- 模拟运行验证：通过。新测试 2 项；存量退款/查询/归一化套件全过。
- 真实运行验收：未验证。
- 证据：同上文件 P0-2 部分。
- 残余风险：协议级拒绝（400）会引起微信重试，幂等安全但浪费。

### P1-1 凭证脚本代码侧修复（轮换仍待负责人）

- 代码验证：通过。探针脚本改从环境变量读取，输出脱敏（无 secret、
  token、client_id、无完整带 token URL），失败非零退出，落盘改系统
  临时目录；新增脚本凭证卫生扫描测试（直接赋值字面量判定，误报经
  重复模式与纯数字规则收敛）。
- 模拟运行验证：通过。扫描测试 2 项通过。
- 真实运行验收：未验证。
- 证据：`test_no_hardcoded_credentials_20260906.py`。
- 残余风险（负责人动作，M-20260906-003 保持 open）：
  旧密钥已随 git 历史与远端扩散，删除代码不能替代轮换；
  须轮换有赞应用密钥并决定历史处理；`check_wecom_employee_agent_callback.py`
  两处占位值经核验为假值（`callback-token`、重复 `1` 的 base64），不 rot。

### P1-2 登录原子占用

- 代码验证：通过。新增 `check_and_record_login_attempt`（SQLite 条件
  更新加插入重试、Redis 单 Lua），登录门禁改单次原子占用；
  成功后清理计数语义不变。
- 模拟运行验证：通过。8 并发精确放行 3 个；存量登录计数语义测试通过。
- 真实运行验收：未验证（无 Redis、无多实例）。
- 证据：`test_review2_edge_outbound_20260906.py::test_p12_concurrent_login_attempts_capped`。
- 残余风险：Redis 路径无真实服务器验证。

### P1-3 代理网段信任

- 代码验证：通过。新增 `TRUSTED_PROXY_NETWORKS` CIDR 配置；
  直连非受信网段一律忽略转发头；受信内按层级取值并校验 IP 合法。
- 模拟运行验证：通过。新测试 2 项；存量转发头测试已同步网段配置。
- 真实运行验收：未验证（生产拓扑未配置）。
- 证据：同上文件 P1-3 部分。
- 残余风险：生产须按拓扑配置网段，否则转发头恒被忽略（fail-closed，
  可能误限流 NAT 后合法用户，需运维确认）。

### P1-4 Redis 存活探测

- 代码验证：通过。裸 RESP 异步 PING（无新依赖，支持 AUTH）；
  启动（REQUIRE_SHARED 时）不可达直接拒绝启动；/ready 在共享模式下
  探测并可降级 503；预检新增可用性检查与恢复计划；中间件共享异常
  返回受控 503。
- 模拟运行验证：通过。本地伪 RESP 服务器可达/不可达两项测试。
- 真实运行验收：未验证（无真实 Redis）。
- 证据：同上文件 P1-4 部分。
- 残余风险：同 P1-2/3。

### P1-5 外发 owner 隔离

- 代码验证：通过。迁移 `v034` 增加 `claim_token`；认领签发唯一凭证；
  终态写入 fencing（`status='sending' AND claim_token`）；
  人工重排轮换凭证；发送租约过期可接管，旧凭证失效；
  重复消费租约有效时退避，不触碰持有者行。
- 模拟运行验证：通过。新测试旧 worker 迟到提交被拒；
  存量外发 8 项已按新语义更新（崩溃退避加接管）全过。
- 真实运行验收：未验证。
- 证据：迁移 `v034`；新旧测试。
- 残余风险：exactly-once 仍不可证（供应商侧无依据）。

### P1-6 失败提交租约一致

- 代码验证：通过。`fail_notify` 与 `complete_notify` 同一租约校验。
- 模拟运行验证：通过。新测试过期租约失败标记被拒。
- 真实运行验收：未验证。
- 证据：同 P0 文件 P1-6 部分。

### 其他修正

1. 查询恢复统一认领状态机：`reconcile_pay/refund_from_query` 改
   `claim_notify_key` 加 token 完成，重复查询直接确认不重放业务。
2. 指纹插入时落库：`save_fingerprint` 已删除，`INSERT` 直接带指纹；
   重放附指纹一致校验；外部镜像无指纹行仍走明文字段合同。
3. 全量表述：本报告与 LOGBOOK 统一口径为“业务定向测试通过；
   全量测试未通过，存在环境前置缺失”，证据索引 E-20260906-011
   结果记为 `partial`。

## 第三轮复核（复核方 P0×1、P1×2、P2×1）

复核结论：上一轮主要问题已进入主链路且有定向覆盖，未发现新的必然
资金重复扣除漏洞；组合支付并发快照、部署失败恢复仍须处理后才可谈上线。

### P0 组合支付并发快照一致性

- 代码验证：通过。`prepare_combined_payment` 在事务内按最新订单重算
  全部金额，会话金额与重算不一致直接回滚并要求重新发起；
  余额上下界同步复验；支付状态 CAS 更新保留为第二道防线。
- 模拟运行验证：通过。新测试模拟会话生成后并发落券 500 分，
  断言回滚（余额不变、无余额快照、券快照保留）；存量组合支付测试全过。
- 真实运行验收：未验证。
- 证据：`test_review3_combined_snapshot_20260906.py`。
- 残余风险：高频并发下用户可能需重试一次；预下单孤儿由微信侧过期。

### P1 部署失败统一恢复

- 代码验证：通过。`deploy_server.sh` 新增阶段状态
 （`CODE_SWITCHED`/`SERVICE_STOPPED_BY_DEPLOY`/`ROLLBACK_IN_PROGRESS`/
  `DEPLOY_SUCCEEDED`）与统一 EXIT trap：切换版本或停止服务后任一失败
  （含显式退出与 set -e 路径）自动恢复上一 commit、重启旧服务并复验；
  回滚不删除数据临时文件；部署合同测试同步新标记断言。
- 模拟运行验证：通过。演练扩展至 8 路（健康失败、重复回滚、正常上线、
  启动失败、临时文件发布前拒绝、依赖安装失败、回滚恢复成功、
  非干净工作区拒绝），退出码 0。
- 真实运行验收：未验证（生产演练待负责人批准）。
- 证据：`D:/Temp/yunxi-audit-final-20260906/drill3.txt`；部署合同测试。
- 残余风险：回滚后复验仍失败时需人工介入（已明确输出指引）。

### P1 凭证轮换（负责人动作，保持 open）

- 代码侧已完成项：环境变量化、脱敏、非零退出、临时目录、扫描测试。
- 未完成：旧密钥轮换、历史与远端检查、CI/部署包/共享目录排查、
  旧凭证失效确认。`M-20260906-003` 关闭前禁止上线。

### P2 全量口径

- 口径（复核方原文）：业务定向测试通过；全量测试未通过，
  失败项属于环境前置或工作区状态问题，待前置条件补齐后重新执行。

## 第四轮复核（复核方 P0×1、P1×2、P2×1）

复核结论：主要问题已进入主链路且有定向覆盖，未发现新的必然资金重复
扣除漏洞；以下收口后仍保持 No-Go，优先序按复核裁决。

### P0 组合支付预下单与订单竞态

- 代码验证：通过。在上一轮（先会话后扣款、事务内重算）基础上追加：
  支付快照整体全等比对（状态/方式/腿任一并发改动即中止）；
  同连接固化（`MemberBalanceService.db_handle` 与订单仓储句柄同一性，
  不一致拒绝扣款）；微信预下单以订单号为幂等键，中止后重发起复用；
  订单 CAS 更新保留为第二道防线。
- 模拟运行验证：通过。新测试 3 项（中止后重发起成功且金额刷新、
  跨连接拒绝扣款、扣款成功但 CAS 失败整体回滚无孤儿流水）；
  存量组合支付测试全过。
- 真实运行验收：未验证。
- 证据：`test_review3_combined_snapshot_20260906.py` 新增 3 项。
- 残余风险：微信预下单成功后事务内中止会留孤儿预支付单
 （微信侧过期作废，无资金影响，重发起按订单号复用）。

### P1 部署恢复加固

- 代码验证：通过。统一 EXIT trap 覆盖显式退出与 set -e 路径；
  发布前工作区保护（跟踪树脏或非白名单未跟踪文件直接拒绝，
  白名单仅 `server.bundle` 与 `.env`）；结构化标记
 （`DEPLOY_STATUS`/`ROLLBACK_STATUS`，回滚失败退出码 3）；
  回滚失败写告警文件并给人工指引；部署合同测试同步新标记断言。
- 模拟运行验证：通过。演练 6 路全过（退出码 0）。
- 真实运行验收：未验证（生产演练待负责人批准）。
- 证据：`D:/Temp/yunxi-audit-final-20260906/drill3.txt`；部署合同测试。
- 残余风险：不可变 release 目录/软链接迁移未执行，记运维后续项；
  当前以发布前干净检查 fail-closed 防止回滚覆盖未提交数据。

### P1 凭证残留排查（轮换仍待负责人）

- 已完成：脚本环境变量化；残留面扫描（D盘两临时目录、报告目录、
  工作流）仅占位命中，无真实值残留；`check_wecom` 两处为占位假值。
- 未完成（负责人动作，M-20260906-003 open，关闭前禁止上线）：
  旧密钥轮换、Git 历史与远端内容审计、CI/部署包排查、旧凭证失效确认。

### P2 全量口径

- 口径（复核方原文）：业务定向测试通过；全量测试未通过，
  失败项属于环境前置或工作区状态问题，待前置条件补齐后重新执行。

## 第五轮：审计复核收口计划执行（本轮）

- trace_id: `20260906-audit-remediation-final`
- parent_run_id: `20260906-audit-remediation-final4`
- run_id: `20260906-audit-remediation-final5`
- owner: `OpenCode`
- status: `active`
- status_label: 进行中（active）
- as_of_commit: `220a8fe0dcd1126dfe43e3745667a3f7f58fc262`
- version: `0.133.0-p2trial.3`

### Task 1 部署按发布前状态恢复

- 代码验证：通过。`restore_service_state` 按 `SERVICE_WAS_ACTIVE`
  分支恢复；回滚未知状态保守重启复验；结构化标记与退出码 3 保留。
- 模拟运行验证：通过。新演练 9（发布前停止保持停止）首轮失败确认
  缺陷，修复后 9 路全过，退出码 0；部署合同测试同步断言。
- 真实运行验收：未验证（生产演练待负责人批准）。
- 证据：`D:/Temp/yunxi-audit-final-20260906/drill5.txt`。
- 残余风险：不可变发布目录迁移记运维后续项。

### Task 2 全量前置补齐

- 根因：回放 fixture 缺失失败实为 CWD 产物——测试用相对路径
  `tests/fixtures/...`，仅当 CWD=backend 时可解析；
  仓库内已提交脱敏 fixture 本身有效（CWD=backend 下 23 项全过，
  隐私断言由检查器强制）。
- 修复：5 个测试文件改用 `Path(__file__)` 定位 fixture，
  断言与阈值零改动；根目录运行 23 项全过。
- 脏工作区测试改独立临时仓库真实 git 验证（暂存不脏、未暂存脏），
  不放宽不断言。
- Windows 编码：回放链路无 subprocess 调用；全量中 gbk 解码警告
  未构成失败，不做推测性修改。
- 证据：Task 5 全量输出。

### Task 3 凭证（负责人动作，保持 open）

- 代码侧：两扫描测试通过；残留面仅占位命中。
- 未完成：旧密钥轮换、历史与远端内容审计、CI/部署包排查、
  旧凭证失效确认。`M-20260906-003` 关闭前禁止上线。

### 状态区分（本轮结论）

- 代码整改：通过（定向全绿）。
- 模拟运行：通过（演练 9 路全过）。
- 全量测试：见 Task 5 单次执行记录。
- 负责人动作：未完成（轮换与真实验收）。
- 真实验收：未验证。
- 上线裁决：正式公开生产上线 No-Go。

## 第六轮：最终上线收口计划执行（本轮）

- trace_id: `20260906-audit-remediation-final`
- parent_run_id: `20260906-audit-remediation-final5`
- run_id: `20260906-audit-remediation-final6`
- owner: `OpenCode`
- status: `active`
- status_label: 进行中（active）
- as_of_commit: `220a8fe0dcd1126dfe43e3745667a3f7f58fc262`
- version: `0.133.0-p2trial.3`

### Task 1 部署三态识别

- 代码验证：通过。`systemctl show --property=ActiveState --value`
  显式解析三态；未知发布前拒绝（未切换、不操作服务）；
  停止/回滚全程复用发布前记录；未知防御性重启复验。
- 模拟运行验证：通过。演练 10 首轮失败确认缺陷，修复后 10 路全过，
  退出码 0；部署合同测试同步断言。
- 真实运行验收：未验证（生产演练待负责人批准）。
- 证据：`D:/Temp/yunxi-audit-final-20260906/drill-final6.txt`。
- 残余风险：不可变发布目录迁移记运维后续项。

### Task 2 skip/xfail/耗时治理

- 4 跳过（`test_local_production_backup.py` 28/61/86/147 行）：
  前三为 C 盘守卫的 Linux 生产路径，Windows 开发机 tmp 必在 C 盘，
  属平台能力限制，不影响生产业务，替代验证为 Linux CI；
  第四为子进程 gbk 解码限制，同类限制。全部允许保留，禁止删除。
- 4 预期失败（发票 `test_admin_invoice_api.py` 1+3）：
  归属 `T-P1-5-INVOICE-FIX`（待负责人确认字段规则），保留 xfail，
  已在状态行与 `M-20260830-004` 标注上线范围限制。
- 耗时事项 `M-20260906-004`（open，中优先级）：本轮 510 秒、
  上轮 697 秒、审计基线 363.6 秒；最耗时为元测试与 LLM 路径；
  方向为慢测分流与分片；复测附 `--durations=30` 对照。
- 全量：2026-09-06 19:13:30 至 19:22:01，约 510 秒，退出码 0；
  1854 项收集，1846 通过、4 跳过、4 预期失败，0 失败 0 错误。
  输出 `D:/Temp/yunxi-audit-final-20260906/full-pytest-closeout.txt`；
  测量运行 `full-pytest-durations.txt` 同结果复核退出码 0。

### Task 3/4 负责人动作

- 凭证轮换、泄露面审计、`M-20260906-003` 关闭：未完成，保持 open。
- 真实验收六项：未批准、未执行。

### 状态区分（本轮结论）

- 代码整改：通过（定向全绿）。
- 模拟运行：通过（演练 10 路全过）。
- 全量测试：通过（退出码 0，skip/xfail 均有说明）。
- 负责人动作：未完成（轮换、真实验收）。
- 真实验收：未验证。
- 上线裁决：正式公开生产上线 No-Go。

## 门禁与全量

- 业务定向测试通过（见 LOGBOOK 本轮条目命令清单，均为退出码 0）。
- `ruff check` 全仓通过；`ruff format --check` 全仓 858 文件通过。
- `mypy`：新增文件零错误；剩余报错为存量文件既有问题
  （cryptography 重载等），未引入新增。
- 小程序 `typecheck` 通过；页面覆盖 15 页 33 接口通过。
- 治理门禁：开发总表 PASS（tasks=34）；中文治理 coverage=1.0；
  证据索引 failed=0；错误账本 29 条；Harness P0 9/9。
- 生产预检 `--json`：31 项中 4 项预期阻断，退出码 1（开发配置，正确行为）。
- 全量 `pytest backend/tests`（第二轮单次执行）：
  命令 `python -B -m pytest backend/tests -q --no-cov -p no:cacheprovider`，
  2026-09-06 14:54:00 至 15:01:05，约 425 秒，退出码 1；
  共收集 1850 项，15 项失败、其余通过，失败集合为同一环境集合。
  原始输出 `D:/Temp/yunxi-audit-final-20260906/full-pytest-final2.txt`
 （PowerShell 重定向为 UTF-16）。
- 全量 `pytest backend/tests`（第五轮收口单次执行）：
  命令 `python -B -m pytest backend/tests -q --no-cov -p no:cacheprovider`，
  2026-09-06 17:47:13 至 17:58:49，约 697 秒，退出码 0；
  共收集 1854 项，0 失败 0 错误，其余通过（含 4 跳过与 4 预期失败标记，
  均为存量平台兼容与发票 xfail 标记）。
  口径更新：业务定向测试通过；全量测试通过（代码层面）。
  真实验收仍未验证，上线裁决仍为 No-Go。
  原始输出 `D:/Temp/yunxi-audit-final-20260906/full-pytest-final5.txt`
 （PowerShell 重定向为 UTF-16）。
- 全量 `pytest backend/tests`（第四轮单次执行）：
  命令 `python -B -m pytest backend/tests -q --no-cov -p no:cacheprovider`，
  2026-09-06 16:06:56 至 16:14:08，约 432 秒，退出码 1；
  共收集 1851 项，15 项失败、其余通过，失败集合与前两轮同一环境集合一致
 （经逐项核对，无本轮相关失败）。
  口径（复核方原文）：业务定向测试通过；全量测试未通过，
  失败项属于环境前置或工作区状态问题，待前置条件补齐后重新执行。
  原始输出 `D:/Temp/yunxi-audit-final-20260906/full-pytest-final4.txt`
 （PowerShell 重定向为 UTF-16）。

## 最终裁决

**正式公开生产上线：No-Go。**

代码整改已按新规逐项验证，但真实支付/退款、真实企微身份与人工接手、
多实例 Redis、凭证轮换、真实模型红队、生产回滚演练均未验证，
须项目负责人批准并实际验收后另行评审。
