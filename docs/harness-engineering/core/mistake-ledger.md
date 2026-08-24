# Mistake Ledger

本文件记录值得系统学习的问题。原则是：同一类错误不能只靠“下次小心”解决，必须沉淀为测试、脚本、规则、门禁、skill 或 runbook。

______________________________________________________________________

## 记录条件

出现以下任一情况，应新增条目：

- 同一问题第二次出现。
- AI 违反项目红线、架构边界或删除安全约束。
- 上线前后发现本可提前检测的问题。
- 修复后没有回归测试保护。
- 用户需要反复提醒同一流程。
- 某个操作依赖聊天上下文，换 Agent 后容易丢失。

### M-20260711-004：消息去重依赖先查后插

- status: verified
- first_seen: 2026-07-11
- severity: high
- symptom: webhook 与聊天流程先查询 `channel_msg_id`，再单独插入消息；数据库没有非空键唯一约束，跨请求或跨进程并发可重复执行消息副作用。
- root_cause: 将去重查询和写入拆成两个操作，并把内存/查询结果当成跨进程一致性保障。
- impact: 同一渠道消息可能重复写入会话、重复触发 AI 或重复发送非文本兜底回复。
- fix: 增加非空渠道消息键唯一索引，使用 `INSERT ... ON CONFLICT DO NOTHING` 原子认领，并接入聊天主流程与有赞非文本旁路。
- new_guardrail: 迁移前历史重复报告脚本；并发、重放、外层事务回滚和旁路发送测试。
- verification: R2-A 定向测试 9 项通过；`data/bot.db` 历史重复组为 0；相关 Ruff check/format 通过。
- linked_trace: `20260711-global-risk-remediation`
- linked_files: `app/migrations/v017_message_channel_id_unique.sql`; `app/repository/message_repo.py`; `app/service/chat.py`; `scripts/check_message_idempotency.py`
- next_time_signal: 任何新的 webhook 或入站旁路必须先调用原子消息 claim；`has_processed()` 只能作为快速观察，不得作为正确性依据。

______________________________________________________________________

### M-20260812-001：feat 提交在 Windows 上被 pre-commit 按 patch 递增版本

- status: guarded
- first_seen: 2026-08-12
- severity: medium
- symptom: 执行 `git commit -m "feat(member): ..."` 时 pre-commit 的 sync_version 钩子把 VERSION 从 0.110.1 递增为 0.110.2（patch），而不是 0.111.0（minor），导致提交被 ruff-format 拦下后版本号已错误变化。
- root_cause: Windows 下 `git commit -m` 触发 pre-commit 时，`sync_version.py` 读取的 `.git/COMMIT_EDITMSG` 仍是上一条提交信息（docs），`determine_bump_type` 按 docs 判定为 patch。
- impact: feat/refactor/perf 提交可能拿到错误版本号并进入发布，污染 VERSION 与进度清单版本注入。
- fix: 重新提交时显式设置 `VERSION_BUMP=minor` 强制 minor 递增，目标 0.111.0 正确落地；提交前核对 `git diff --cached VERSION` 的期望值。
- new_guardrail: 含代码变更的提交前先核对 VERSION 目标；Windows 上 feat 提交显式传 `VERSION_BUMP=minor`，不依赖钩子自动推断提交类型。
- verification: `ecffa3b` 提交后 VERSION=0.111.0；生产部署核对服务器 VERSION 与 `/ready` 版本一致。
- linked_trace: `20260812-member-loyalty-storedvalue`
- linked_files: `scripts/sync_version.py`; `VERSION`; `.pre-commit-config.yaml`
- next_time_signal: 任何含代码变更的提交前先 `git diff --cached VERSION`；feat/perf/refactor 提交使用 `VERSION_BUMP=minor` 强制递增。

### M-20260812-002：提交被门禁拦下后重试导致 VERSION 双次递增

- status: guarded
- first_seen: 2026-08-12
- severity: medium
- symptom: M2 feat 提交第一次被 ruff-format 门禁拦下（pre-commit 已把 VERSION 0.111.0→0.112.0 并暂存），第二次直接重跑 `git commit` 时 sync_version 再次递增为 0.113.0，且第二次提交被 check-project 子脚本（report_langchain_observability_evidence --summary）偶发挂起，提交一直未落地。
- root_cause: sync_version 每次按当前 VERSION 递增；被门禁阻断的提交只是中止，版本递增已生效；重试时未先核对 `git diff --cached VERSION`，导致在同一目标版本上连续两次递增。Windows 下 pre-commit 子进程偶发不退出（无超时脚本），进一步拖垮重试。
- impact: 版本号偏离计划（0.112.0→0.113.0），若直接发布会污染版本语义；重试期间残留 pre-commit 进程占用钩子状态。
- fix: 手工把 VERSION 与进度清单表头改回目标 0.112.0，重新暂存后以 `SKIP_VERSION_BUMP=1` 提交；先清理残留的 git/pre-commit/python 钩子进程再重试。
- new_guardrail: 任何提交被门禁拦下后，重试前必须 `git diff --cached VERSION` 核对期望版本；若版本已被钩子递增且不再需要，用 `SKIP_VERSION_BUMP=1` 防二次递增；提交前确认无残留钩子进程（Get-Process git/pre-commit/python）。
- verification: `e6bc534` 提交后 VERSION=0.112.0；生产部署核对服务器 VERSION 与 `/ready` version=0.112.0 一致。
- linked_trace: `20260812-member-loyalty-storedvalue`
- linked_files: `scripts/sync_version.py`; `VERSION`; `.pre-commit-config.yaml`
- next_time_signal: 提交失败重试前自动核对暂存区 VERSION 目标；`git status` 出现 VERSION 已修改但提交失败时直接触发本条目检查。


### M-20260813-001：服务构造期访问 _db 导致生产启动崩溃

- status: guarded
- first_seen: 2026-08-13
- severity: critical
- symptom: M4 生产部署第一段重启后 yunxibakebot 崩溃循环（status=3/NOTIMPLEMENTED），/health /ready 不可达；journalctl 显示 lifespan `init_services` 装配 `CouponService()` 时构造器访问 `OrderRepo(None)._db` 抛 `RuntimeError: 数据库操作未在 db_session_scope 上下文管理器中执行！`。
- root_cause: `CouponService.__init__` 构造期急切执行 `self._order_repo._db`（为建 CouponInventoryService），而 lifespan 装配期无 db_session_scope；Points/StoredValue 服务均为惰性方法期访问，Coupon 未遵循同模式。本地测试未暴露：`test_init_services_wires_core_services` 用 FakeCouponService 替换真实构造。
- impact: 生产服务中断约 10 分钟（部署失败→回滚 v0.122.1 恢复），期间线上客服/小程序不可用；v024 迁移已在崩溃前落库，回滚代码与 DB 兼容（迁移器只补未应用版本、无降级检测）。
- fix: `CouponService` 券库存服务改惰性属性 `_inventory`，首次方法调用期才 `CouponInventoryService(self._order_repo._db)`；新增裸构造与惰性解析两个回归测试。
- new_guardrail: 无参服务构造不得在 `__init__` 访问 `_db`（必须惰性/方法期解析）；lifespan 装配的每个新服务必须能在无 db_session_scope 下完成构造，并补「裸构造」回归测试，禁止只用 Mock 覆盖装配路径。
- verification: 本地定向 70+ 项全绿；`CouponService()` 裸构造测试通过；重新部署后生产 /health /ready 200、schema_version=24。
- linked_trace: 20260813-coupon-m4-prod-deploy
- linked_files: `app/service/coupon/__init__.py`; `tests/service/test_coupon_payment.py`; `app/lifespan_services.py`
## 条目模板

```markdown
## M-YYYYMMDD-001：问题标题

- status: open | guarded | verified
- first_seen: YYYY-MM-DD
- severity: low | medium | high | critical
- symptom: 外在现象
- root_cause: 根因
- impact: 影响范围
- fix: 本次修复方式
- new_guardrail: 新增防线
- verification: 如何证明防线有效
- linked_trace: 关联 trace_id
- linked_files: 关联文件
- next_time_signal: 下次同类问题如何被自动发现
```

## M-20260712-007：部署停机前未检查后台 session secret

- status: guarded
- first_seen: 2026-07-12
- severity: critical
- symptom: 发布 commit 后直接重启生产，启动安全检查发现 `ADMIN_SESSION_SECRET` 缺失，服务进入 systemd 自动重启，7001 短时不可用。
- root_cause: 部署脚本只在启动后依赖应用发现必需配置，没有在停止现有服务前验证 `.env` 中的非空安全配置。
- impact: 缺失配置会把可用旧版本服务变成不可用状态，必须依靠人工回滚恢复。
- fix: `scripts/deploy_server.sh` 在停止服务前检查 `ADMIN_API_TOKEN` 和 `ADMIN_SESSION_SECRET` 非空；缺失时立即退出并保留现有服务。
- new_guardrail: `tests/scripts/test_deploy_server_contract.py` 固定安全配置预检和“拒绝停止现有服务”合同。
- verification: 部署合同测试、Bash 语法检查和提交前完整质量门禁通过；生产发布后 health/ready 版本门禁通过。
- linked_trace: `20260711-global-risk-remediation`
- linked_files: `scripts/deploy_server.sh`; `tests/scripts/test_deploy_server_contract.py`; `app/main.py`
- next_time_signal: 所有会停止现有服务的部署脚本必须先检查启动必需配置、manifest 和版本；发现缺失时不得进入 stop 阶段。

## M-20260712-008：Callback API 测试夹具未同步服务端授权语义

- status: verified
- first_seen: 2026-07-12
- severity: high
- symptom: 员工 callback 已改为用户、群、企业服务端白名单和 allowed tools 执行前门禁，但两个 API 测试仍发送无 chatid/actor/corp 的 group 消息，Fake Agent 也不接收 allowed_tools，导致全量测试回退到转人工。
- root_cause: 授权收口只同步了专项 callback 探针和 dispatcher 测试，没有把加密 API 回调夹具纳入同一 actor 合同。
- impact: 全量测试失败；若通过关闭授权绕过测试，会掩盖生产 fail-closed 边界和工具权限传递回归。
- fix: API 测试使用明确合成员工、群和企业 ID，配置对应服务端白名单；Fake Agent 对齐 answer 接口并记录 allowed_tools。
- new_guardrail: `test_wecom_intelligent_bot_callback_api.py` 的产品回复和 Agent 路径同时要求授权 actor，Agent 路径断言收到非空 allowed_tools；标准全量 pytest 纳入发布完成审计。
- verification: callback API 与版本同步定向套件 `12 passed`；Ruff 和独立 mypy 通过；全量测试复跑作为最终验证。
- linked_trace: `20260711-global-risk-remediation`
- linked_files: `tests/api/test_wecom_intelligent_bot_callback_api.py`; `app/service/wecom/employee_authorization.py`; `app/service/wecom/intelligent_bot_dispatcher.py`
- next_time_signal: callback actor 或工具授权接口变更时，无完整 user/chat/corp 或未接收 allowed_tools 的 API 夹具必须在全量测试中失败。

## M-20260713-001：静态容器合同未发现不可ready和超大镜像

- status: guarded
- first_seen: 2026-07-13
- severity: critical
- symptom: Docker静态合同通过，但首次真实构建得到14.5GB镜像并把40GB生产根盘推到100%；隔离容器虽health通过，ready因后台dist被dockerignore排除而503。
- root_cause: 合同只搜索Dockerfile中的非root、单worker和digest字符串，没有验证真实构建上下文、最终镜像层、后台产物和PyTorch CPU/CUDA依赖来源。
- impact: 容器发布会因readiness永久失败；构建可耗尽生产磁盘并影响systemd服务日志、数据库和后续发布。
- fix: 已编译后台dist进入镜像，reports排除；PyTorch固定从官方CPU wheel索引构建，runtime只从wheelhouse离线安装；smoke使用隔离tmpfs和独立端口。
- new_guardrail: 容器合同新增CPU torch、离线wheelhouse、reports排除和dist包含断言；真实build必须记录镜像大小并执行ready/version smoke。
- verification: 静态合同测试通过；真实精确HEAD重建、镜像层检查、隔离health/ready和漏洞扫描作为最终验证。
- linked_trace: `20260711-global-risk-remediation`
- linked_files: `Dockerfile`; `.dockerignore`; `tests/scripts/test_container_contract.py`; `docs/harness-engineering/specs/2026-07-13-production-container-verification-design.md`
- next_time_signal: 静态容器合同不能作为R4-C完成证据；没有真实镜像大小、dist文件、ready 200和scanner结果时必须保持未完成。

## M-20260713-002：容器依赖下载中断导致整层重做

- status: guarded
- first_seen: 2026-07-13
- severity: medium
- symptom: 生产机从官方PyPI下载锁定wheel超过一小时，在transformers下载阶段构建会话退出；builder未产出镜像，已完成的约100MB依赖下载随失败层全部丢失。
- root_cause: builder同时使用`pip wheel --no-cache-dir`且没有BuildKit cache mount，网络中断或外层会话结束后无法复用任何已完成HTTP下载。
- impact: 低带宽生产环境的真实镜像验证耗时不可控，重复构建增加发布窗口、带宽和磁盘压力，并放大人工切换第三方镜像的诱因。
- fix: builder两段`pip wheel`共享`/root/.cache/pip` BuildKit cache mount，移除builder的`--no-cache-dir`；runtime继续从wheelhouse离线安装并保持`--no-cache-dir`。
- new_guardrail: 容器合同要求builder存在locked pip cache mount、禁止`pip wheel --no-cache-dir`，并继续断言runtime离线wheelhouse安装。
- verification: 容器合同定向测试与中断后真实重建；最终镜像检查确认cache mount内容不进入runtime层。
- linked_trace: `20260711-global-risk-remediation`
- linked_files: `Dockerfile`; `tests/scripts/test_container_contract.py`; `docs/harness-engineering/specs/2026-07-13-production-container-verification-design.md`
- next_time_signal: 任何远程大依赖构建若没有可跨失败复用的下载缓存，不得在低带宽生产窗口直接执行。

## M-20260713-003：容器向量索引基名指向数据目录

- status: guarded
- first_seen: 2026-07-13
- severity: high
- symptom: 真实容器`/health=200`，但`/ready=503`；唯一失败项是`embedding_index_path_exists=false`，即使隔离volume内已有空索引文件也不生效。
- root_cause: Dockerfile/Compose把`EMBEDDING_INDEX_DIR`设置为`/app/data`，应用把配置值当索引基名并解析为`/app/data.npy/.json`，文件落在volume挂载点之外。
- impact: 容器部署表面启动但永远不可ready，发布门禁会错误失败；若用smoke环境变量临时覆盖，可能掩盖生产默认配置缺陷。
- fix: Dockerfile和Compose统一设置`EMBEDDING_INDEX_DIR=/app/data/embeddings`，空索引预置到volume内的`embeddings.npy/.json`。
- new_guardrail: 容器合同同时断言Dockerfile/Compose的DB和embedding基名；真实smoke不覆盖该环境变量，必须以镜像默认值通过ready。
- verification: 新精确HEAD镜像默认环境变量下隔离`/health`、`/ready`、Docker health和version全部通过。
- linked_trace: `20260711-global-risk-remediation`
- linked_files: `Dockerfile`; `docker-compose.yml`; `tests/scripts/test_container_contract.py`; `docs/harness-engineering/specs/2026-07-13-production-container-verification-design.md`
- next_time_signal: readiness smoke若需要额外覆盖`EMBEDDING_INDEX_DIR`才能通过，必须回到镜像/Compose默认路径修复，不得把覆盖值作为通过证据。

## M-20260713-004：运行时保留安装工具的vendor漏洞

- status: guarded
- first_seen: 2026-07-13
- severity: high
- symptom: 最小 runtime smoke 已通过，但 Trivy 复扫仍发现 `wheel 0.45.1` 与 `jaraco.context 5.3.0` 的可修复HIGH；`pip show`不显示它们，实际来自pip/setuptools vendor目录。
- root_cause: 只卸载顶层wheel/jaraco包，没有移除生产运行不需要的pip和setuptools，因此其vendor代码仍被镜像漏洞扫描器识别。
- impact: 生产镜像保留不必要的安装工具和可被利用的依赖代码，HIGH漏洞门禁无法归零。
- fix: runtime以root完成依赖离线安装后卸载`pip setuptools wheel jaraco.context`，应用运行时不依赖这些工具。
- new_guardrail: 容器合同锁定四项runtime工具卸载；Trivy必须以最终镜像JSON报告证明HIGH/CRITICAL均为0。
- verification: root临时容器验证卸载命令可执行；新精确HEAD需重建、复跑smoke和Trivy。
- linked_trace: `20260711-global-risk-remediation`
- linked_files: `Dockerfile`; `tests/scripts/test_container_contract.py`; `docs/harness-engineering/specs/2026-07-13-production-container-verification-design.md`
- next_time_signal: 仅以`pip show`判断runtime工具是否消失不足；必须结合镜像扫描和vendor路径检查。

## M-20260711-004：消息去重依赖先查后插

- status: verified
- first_seen: 2026-07-11
- severity: high
- symptom: webhook 与聊天流程先查询 `channel_msg_id`，再单独插入消息；数据库没有非空键唯一约束，跨请求或跨进程并发可重复执行消息副作用。
- root_cause: 将去重查询和写入拆成两个操作，并把内存/查询结果当成跨进程一致性保障。
- impact: 同一渠道消息可能重复写入会话、重复触发 AI 或重复发送非文本兜底回复。
- fix: 增加非空渠道消息键唯一索引，使用 `INSERT ... ON CONFLICT DO NOTHING` 原子认领，并接入聊天主流程与有赞非文本旁路。
- new_guardrail: 迁移前历史重复报告脚本；并发、重放、外层事务回滚和旁路发送测试。
- verification: R2-A 定向测试 9 项通过；`data/bot.db` 历史重复组为 0；相关 Ruff check/format 通过。
- linked_trace: `20260711-global-risk-remediation`
- linked_files: `app/migrations/v017_message_channel_id_unique.sql`; `app/repository/message_repo.py`; `app/service/chat.py`; `scripts/check_message_idempotency.py`
- next_time_signal: 任何新的 webhook 或入站旁路必须先调用原子消息 claim；`has_processed()` 只能作为快速观察，不得作为正确性依据。

________________________________________________________________________

## M-20260711-006：隐私检索日志和主体删除范围不完整

- status: guarded
- first_seen: 2026-07-11
- severity: critical
- symptom: 首片 consent 只覆盖画像，检索日志仍会保存原始 query，主体删除没有统一覆盖会话、订单、地址、客户主档和外部订单链。
- root_cause: 把 consent、外发脱敏和数据生命周期当成独立局部功能，没有以数据表覆盖清单建立单一权利链。
- impact: 原始客服 query 可能长期留存，撤回后仍可能从关联表恢复个人数据，无法证明主体删除完整。
- fix: 新增 `PrivacyRepo` 单一数据覆盖仓库、主体导出/删除 service/API、TTL 清理入口；检索日志只保存脱敏 query hash/category；备份保留 30 天且不由应用批量删除。
- new_guardrail: 隐私 API/仓库合同测试、嵌套 LLM payload 脱敏测试、`privacy-data-retention-policy.md` 和 R3-A 证据索引。
- verification: R3-A 定向测试通过；检索日志断言原始 query 为空且 hash 为 64 位；主体删除断言画像、会话、消息、订单、地址和客户主档关联数据清理，consent 保留 revoked。
- linked_trace: `20260711-global-risk-remediation`
- linked_files: `app/repository/privacy_repo.py`; `app/service/privacy_lifecycle.py`; `app/service/privacy_redaction.py`; `app/api/channels/storefront/privacy.py`; `docs/architecture/privacy-data-retention-policy.md`
- next_time_signal: 新增含个人数据的表必须同时进入导出/删除/TTL 覆盖清单和合同测试；任何模型入口必须经过统一脱敏 helper。

________________________________________________________________________

## M-20260711-005：Webhook ACK 依赖进程内队列

- status: guarded
- first_seen: 2026-07-11
- severity: critical
- symptom: 企微队列使用进程内 `asyncio.Queue`，队列满时丢弃消息，worker 取消或进程重启后 ACK 过的消息无法恢复。
- root_cause: 把“已进入内存”误当成“已持久接收”，没有 lease、重试和 dead-letter 状态。
- impact: 入站消息可能在客户无感知的情况下永久丢失，部署或异常恢复期间无法证明业务副作用是否完成。
- fix: 新增 SQLite `inbox_events`，入队先持久化；worker 使用原子 lease claim、有限重试、dead-letter 和实例恢复。
- new_guardrail: ADR 0006、InboxRepo 状态机测试、企微队列持久恢复测试；R2 完成前禁止多 worker 和水平扩容。
- verification: R2-B 首片定向测试 24 项和 `check_project.py --skip-tests` 通过。
- linked_trace: `20260711-global-risk-remediation`
- linked_files: `app/migrations/v018_inbox_events.sql`; `app/repository/inbox_repo.py`; `app/service/wecom/base_queue.py`
- next_time_signal: 新 webhook/队列必须证明“持久化后 ACK”、lease 超时可恢复、失败有界重试和 shutdown drain，不能只测试内存 queue size。

________________________________________________________________________

## M-20260711-001：支付回调只验签不验业务合同

- status: guarded
- first_seen: 2026-07-11
- severity: critical
- symptom: 微信通知完成密码学验签和解密后，原实现直接按 `out_trade_no` 写入 paid，未校验商户、appid、金额、币种和交易号唯一性。
- root_cause: 把第三方协议验签误当成业务支付事实确认，订单 JSON 也没有独立交易号认领约束。
- impact: 伪造或重放通知可能造成错误订单入账、跨订单交易号复用和重复履约。
- fix: 在 service 层补齐微信业务字段校验，并新增交易号账本与条件状态迁移。
- new_guardrail: 支付通知负向测试、唯一交易号 claim 和生产 mock-pay 默认关闭。
- guard: service 层显式校验支付字段；`payment_transactions.transaction_id` 主键绑定订单；repository 原子 claim；支付状态只允许 unpaid -> paid；负向和重复通知测试纳入 R1-A。
- verification: `python -m pytest tests/api/test_miniapp_payment_api.py tests/service/test_order.py -q --no-cov` 与 `python -m pytest tests/ -q --no-cov` 通过。
- linked_trace: `20260711-global-risk-remediation`
- linked_files: `app/service/order/payment_runtime.py`; `app/repository/order_repo.py`; `app/migrations/schema.py`
- next_time_signal: 支付回调合同测试必须覆盖错金额、错商户、空交易号、跨订单交易号和重复通知。

## M-20260711-002：Repository 内部提交切断领域事务

- status: guarded
- first_seen: 2026-07-11
- severity: high
- symptom: 订单创建先扣库存，再由多个 repository 分别 `commit()`，外层 service 无法在事件写入失败时回滚全部写入。
- root_cause: 把 repository 当作独立操作边界，未把订单聚合写入的事务责任放在 service 层。
- impact: 可能产生库存已扣但订单/事件缺失，或支付已标记但支付事件未记录的不一致状态。
- fix: 订单应用服务统一建立 Unit of Work；首批订单域 repository 只执行 SQL，不再自行提交。
- new_guardrail: `scripts/check_order_repository_transactions.py` 接入 `check_project.py`，并补订单创建/支付回调故障注入回滚测试。
- verification: `python -m pytest tests/ -q --no-cov`、`python scripts/check_project.py --skip-tests` 通过。
- linked_trace: `20260711-global-risk-remediation`
- linked_files: `app/repository/base.py`; `app/service/order/application.py`; `scripts/check_order_repository_transactions.py`
- next_time_signal: 订单域新增 repository 写方法时，静态门禁必须阻断内部 `commit()`。

## M-20260711-003：后台长期凭证落入浏览器存储

- status: guarded
- first_seen: 2026-07-11
- severity: high
- symptom: 后台前端把长期 `ADMIN_API_TOKEN` 写入 localStorage，并自动附加 Bearer；后端同时把长期 token 作为 Cookie。
- root_cause: 登录凭证和短时会话没有分层，兼容路径长期保留且没有明确默认关闭开关。
- impact: XSS 或浏览器残留可直接复用长期管理凭证，向量重建等后台入口也缺少统一边界。
- fix: 使用签名短时 HttpOnly/Secure Cookie；默认关闭 legacy Bearer；向量接口统一接入 admin 鉴权。
- new_guardrail: 前端源码无 localStorage token/自动 Bearer；启动/readiness 要求 `ADMIN_SESSION_SECRET`；后台 Origin、会话、ASGI body cap 和静态 auth surface 合同纳入 R1-C。
- verification: 后台鉴权/启动/readiness 测试和 `web/admin` `npm run typecheck` 通过。
- linked_trace: `20260711-global-risk-remediation`
- linked_files: `app/api/admin/root.py`; `web/admin/src/services/http.ts`; `app/api/admin/frontend.py`
- next_time_signal: 新后台 API 必须使用短会话依赖，静态扫描阻断 localStorage 管理凭证。

______________________________________________________________________

## 防线优先级

| 优先级 | 防线 | 说明 |
|---:|---|---|
| 1 | 自动测试 | 最可靠，优先补回归测试 |
| 2 | 静态检查脚本 | 适合架构边界、危险模式、文档同步 |
| 3 | pre-commit/CI | 适合必须阻断的问题 |
| 4 | Guard Skill / AGENTS | 适合操作流程和分层约束 |
| 5 | Runbook / 文档 | 只能作为补充，不能替代机械防线 |

______________________________________________________________________

## 当前条目

## M-20260711-001：生产快照通过删除黑名单推断安全

- status: guarded
- first_seen: 2026-07-11
- severity: critical
- symptom: 旧快照脚本复制完整生产库后只删除若干已知 PII 表，并允许 `--raw` 和评测回退，新增表或遗漏表可能把个人数据带入本地评测库。
- root_cause: 快照边界采用黑名单和原始库兼容路径，没有把允许表、允许列和 schema 漂移定义为正向合同。
- impact: 客户地址、身份、画像、摘要、群登记或原始消息可能进入本地评测库并被误分发。
- fix: 新增白名单导出器，只创建三张允许表的明确列；未知源表、缺列和敏感模式直接失败，失败清理目标文件；移除原始库评测回退。
- new_guardrail: `tests/scripts/test_export_safe_snapshot.py` 覆盖 PII 表、敏感值、未知表、目标表集合和列集合；生产快照脚本不再支持 `--raw`。
- verification: `python -m pytest tests/scripts/test_export_safe_snapshot.py tests/scripts/test_eval_retrieval.py -q --no-cov`; `python -m ruff check scripts/export_safe_snapshot.py tests/scripts/test_export_safe_snapshot.py scripts/eval_retrieval.py tests/scripts/test_eval_retrieval.py`。
- linked_trace: 20260711-global-risk-remediation
- linked_files: `scripts/export_safe_snapshot.py`; `scripts/pull_prod_snapshot.sh`; `scripts/eval_retrieval.py`; `tests/scripts/test_export_safe_snapshot.py`; `tests/scripts/test_eval_retrieval.py`
- next_time_signal: 源 SQLite 出现未登记表或允许列变更时，白名单合同测试和导出器必须非零退出，不得生成评测库。

## M-20260710-001：版本钩子未识别当前进度表头却报告成功

- status: verified
- first_seen: 2026-07-10
- severity: medium
- symptom: 提交钩子把 `VERSION` 从 `0.105.13` 更新为 `0.105.14` 并报告版本同步通过，但 `项目进度与配置清单.md` 顶部仍显示 `0.105.13`。
- root_cause: `scripts/sync_version.py` 只匹配旧版“最后更新: ... — v...”表头；当前“最后更新 ... 当前本地代码版本为 ...”格式无法命中。函数未把零匹配视为失败，也未在修改进度文件后执行 `git add`。
- impact: 提交可在版本来源不一致时成功，后续生产验证、文档查阅和 Agent 续跑可能依据过期版本号。
- fix: 同时支持当前与旧版表头；无法识别时返回失败并回滚 VERSION；成功后自动暂存 VERSION 和项目进度文件。
- new_guardrail: 新增当前格式、旧格式、未知格式和仓库 VERSION/进度一致性 4 项 pytest 回归；pre-commit 继续运行版本同步脚本。
- verification: `python -m pytest tests/scripts/test_sync_version.py -q --tb=short --no-cov`; `python scripts/check_mistake_ledger.py`; amend 后核对 `VERSION` 与项目进度表头均为 `0.105.14`。
- linked_trace: 20260710-version-progress-sync
- linked_files: `scripts/sync_version.py`; `tests/scripts/test_sync_version.py`; `项目进度与配置清单.md`; `.pre-commit-config.yaml`
- next_time_signal: 版本脚本遇到未知表头会以非零状态阻断提交；即使脚本逻辑回退，仓库一致性测试也会直接失败。

______________________________________________________________________

## 机器检查

运行：

```powershell
python scripts/check_mistake_ledger.py
```

检查内容：

- 空账本必须保留“暂无正式条目”标记。
- 正式条目标题必须使用 `M-YYYYMMDD-001：标题` 格式。
- 正式条目必须包含模板里的全部字段。
- `status` 只能是 `open`、`guarded`、`verified`。
- `severity` 只能是 `low`、`medium`、`high`、`critical`。

该检查已接入 `.pre-commit-config.yaml` 的 `check-mistake-ledger` hook。账本一旦出现格式漂移，会在提交前被发现，而不是等到后续 Agent 读取时才踩坑。
