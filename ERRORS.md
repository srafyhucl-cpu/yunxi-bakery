# 错误账本（ERRORS）

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

## M-20260909-001：迁移编号与既有版本冲突导致初始化失败

- status: verified
- first_seen: 2026-09-09
- severity: medium
- symptom: 新增配送表迁移最初使用 `v032_delivery_quotes.sql`，仓库已有 `v032_wecom_kf_outbound_content_hash.sql`；迁移器按数字版本登记，内存数据库初始化出现 `_schema_version.version` 唯一约束失败。
- root_cause: 新迁移文件只按局部功能顺序命名，未先核对全仓迁移目录的既有版本号。
- impact: 测试数据库和新环境无法完成 schema 初始化，配送、订单与其他依赖完整迁移链路的测试被阻断。
- fix: 配送迁移改为未占用的 `v035_delivery_quotes.sql`，保留既有 `v032` 迁移不变。
- new_guardrail: 新增迁移前先检索 `backend/app/migrations/` 的版本前缀；定向测试必须使用 `init_db(":memory:")` 验证完整迁移链可执行。
- verification: `pytest tests/api/test_miniapp_delivery_api.py tests/service/delivery/test_order_quote_binding.py tests/service/delivery/test_shansong.py -q --no-cov` 退出码 0（9 项通过）；订单、支付、券、积分、储值与配送定向回归 120 项退出码 0。
- linked_trace: 20260908-miniapp-commerce-ux-redesign
- linked_files: `backend/app/migrations/v035_delivery_quotes.sql`; `backend/tests/service/delivery/test_order_quote_binding.py`; `backend/tests/api/test_miniapp_delivery_api.py`
- next_time_signal: 新增迁移后如 `init_db(":memory:")` 出现 `_schema_version` 约束冲突，先核对版本号全局唯一性，禁止通过删除或覆盖既有迁移修复。

## M-20260909-002：DevTools 截图超时后仍延迟写入，文件与目标页面错配

- status: guarded
- first_seen: 2026-09-09
- severity: medium
- symptom: `miniprogram-automator` 的 `miniProgram.screenshot()` 超时后，DevTools 仍可能在后续页面导航完成后写入截图；例如目标为结算页的 `wt-checkout.png` 实际显示积分明细页，走查 JSON 也出现当前路由与目标页不一致。
- root_cause: 截图协议超时只中断调用方等待，不会取消 DevTools 内部的异步截图任务；脚本继续导航后，迟到帧被写入原文件名。
- impact: 截图文件名、报告目标页和实际像素内容不再存在一一对应关系，不能作为视觉验收或 UI 回归结论。
- fix: 走查脚本保留截图失败即非零退出；在截图通道修复前，以当前路由、运行态数据、关键 DOM 坐标、元素可见性和溢出检查作为结构证据。
- new_guardrail: 任何截图超时、截图前后路由不一致或异步调用未完成时，禁止引用该图片作为页面视觉证据；关键交易页必须额外记录当前路由与关键元素的运行态检查结果。
- verification: 单页模式下 `App.captureScreenshot` 仍在 30 秒超时，且既有 `walkthrough-phase-c.json` 可复现页面错配；`devtools:verify-all-pages` 可稳定复核当前路由和 DOM。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `miniapp/scripts/walkthrough-phase-c.mjs`; `miniapp/scripts/verify-all-15-pages-devtools.cjs`; `miniapp/reports/devtools/walkthrough-phase-c.json`
- next_time_signal: 后续要恢复截图级验收，先验证单页截图在请求期限内完成且截图前后 `currentPage.path` 相同；任一条件不满足时继续使用结构化运行态证据。

## M-20260909-003：DevTools 测试状态注入使用错误的购物车存储键

- status: guarded
- first_seen: 2026-09-09
- severity: low
- symptom: 首次有商品购物车走查向 `yunxiCartItems` 写入样本数据，但实际购物车读取 `STORAGE_KEYS.cartItems` 的 `cartItems` 键，页面保持空态并误报缺少结算栏。
- root_cause: 测试脚本未先读取 `miniapp/miniprogram/constants/storage.ts` 的共享存储契约，凭名称猜测了键值。
- impact: 自动化走查可将测试状态注入失败误判为界面或布局故障，浪费排查时间。
- fix: 使用共享契约中的 `cartItems` 键重新验证；新增 `devtools:commerce-states` 固化正确键与清理逻辑。
- new_guardrail: 任何依赖本地状态的 DevTools 审计先读取对应常量或工具函数；注入后必须同时断言页面运行态数据已反映目标状态。
- verification: 正确注入后购物车 `hasItems=true`，商品行位于 `99px`，结算栏位于 `674px`，数量控件存在且无内容遮挡。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `miniapp/miniprogram/constants/storage.ts`; `miniapp/miniprogram/utils/cart.ts`; `miniapp/scripts/verify-devtools-commerce-states.cjs`
- next_time_signal: 后续任何状态注入若页面数据未进入预期分支，先核对共享存储契约和写入结果，禁止直接归因到页面 UI。

## M-20260909-004：DevTools 审计只等待路由稳定，未等待首页商品异步内容就绪

- status: guarded
- first_seen: 2026-09-09
- severity: low
- symptom: 15 页审计在首页路由已稳定但精选商品仍在异步加载时立即查询 `.shelf`，导致实际商品优先页面偶发报“未找到包含商品的货架”。
- root_cause: 审计脚本的导航等待只验证 `currentPage.path`，没有为依赖远程商品块的首页增加内容就绪条件。
- impact: 网络或模拟器性能波动可产生首页商品优先的假阴性，降低审计结果可信度。
- fix: 首页业务断言查询货架和商品卡时最多等待 2.4 秒，只有内容仍未出现才报错。
- new_guardrail: 路由稳定不等于页面数据稳定；涉及异步业务数据的运行态审计必须等待对应关键元素或显式加载失败状态。
- verification: 修复后重新运行 `npm run devtools:verify-all-pages`，首页需同时输出货架、首张商品和品牌轮播坐标。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `miniapp/scripts/verify-all-15-pages-devtools.cjs`; `ERRORS.md`
- next_time_signal: 新增异步页面断言时，先区分路由完成、加载中、加载失败和内容就绪四种状态，禁止只按固定等待时间判断。

## M-20260906-004：全量测试耗时超过 10 分钟优化阈值

- status: verified
- first_seen: 2026-09-06
- severity: medium
- symptom: 全量 `python -B -m pytest backend/tests -q --no-cov -p no:cacheprovider` 本轮 510 秒、上轮 697 秒，均超过 600 秒阈值；审计基线 363.6 秒，整改各轮 421-461 秒。
- root_cause: 最耗时为元测试（check_project 30 秒、preflight 29 秒、harness 自评 18 秒，多次重复执行重量级检查器）、LLM 工厂与聊天失败路径（单项 6-13 秒）、治理与总表检查（单项 4-6 秒，数量多）；单进程串行执行，无分片。
- impact: 开发反馈变慢；耗时波动掩盖真实回归信号。
- fix: 本轮仅建档，不删测试、不降覆盖、不默认跳过。
- new_guardrail: 优化方向为慢测试标记分流、元测试复用检查结果缓存、pytest-xdist 分片；下一次全量复测附 `--durations=30` 对照本轮基线。
- verification: `D:/Temp/yunxi-audit-final-20260906/full-pytest-durations.txt`（30 项耗时表）；收口全量 `full-pytest-closeout.txt` 退出码 0。
- linked_trace: `20260906-audit-remediation-final`
- linked_files: `backend/tests/scripts/test_check_project.py`; `backend/tests/scripts/test_preflight_production.py`; `backend/tests/scripts/test_harness_eval_regression.py`
- next_time_signal: 全量耗时相对本轮基线增长 20% 以上或绝对值持续超 600 秒时，必须先落优化动作再收口，不得用跳过测试代替优化。

## M-20260906-003：已入库脚本硬编码真实有赞应用密钥

- status: open
- first_seen: 2026-09-06
- severity: critical
- symptom: `backend/scripts/test_youzan_product_feasibility.py`（git 已跟踪）第 9-11 行以字面量硬编码真实有赞 `client_id`/`client_secret`/`kdt_id`，注释称“真实配置信息”。任何克隆仓库者均可读到该密钥。
- root_cause: 早期连通性探针为图方便把生产密钥写入脚本并提交；后续无人清理；密钥类字面量无提交门禁。
- impact: 有赞应用密钥已随 git 历史扩散，视为已泄露；须由项目负责人轮换并评估历史泄露面。本地 `backend/.env` 未入库，不在本次范围内。
- fix: 负责人轮换该有赞应用密钥；脚本改为从环境变量读取；评估是否需要清理 git 历史（注意重写历史影响协作，需负责人决策）。
- fix_progress_20260906_round2: 脚本代码侧已整改（环境变量读取、输出脱敏、失败非零退出、落盘改系统临时目录），新增脚本凭证卫生扫描测试；轮换与历史处理仍待负责人，账本保持 open。
- gating_20260906_round3: M-20260906-003 关闭前禁止上线（复核裁决）。
- progress_20260906_round4: 代码侧整改完成（环境变量化、脱敏、非零退出、临时目录、扫描测试）；残留面排查完成（D盘临时目录、报告目录、工作流仅占位命中，无真实值残留）；旧密钥轮换、历史与远端内容审计、CI/部署包排查、旧凭证失效确认仍待负责人，账本保持 open。
- new_guardrail: 本轮新增凭证模式扫描（路径加指纹，不输出真实值）；提交前对新增字面量密钥保持人工复核。
- verification: 扫描复核脚本位于 `D:/Temp/yunxi-audit-final-20260906/credential_scan.py`；命中清单见最终复核报告 P1-4 节；真实值从未在本轮输出或提交。
- linked_trace: `20260906-audit-remediation-final`
- linked_files: `backend/scripts/test_youzan_product_feasibility.py`; `docs/audit/20260906-p0-p1-final-code-review.md`
- next_time_signal: 发现 git 已跟踪文件含真实密钥字面量时，先登记负责人轮换动作，不读取、不输出、不提交真实值。

## M-20260906-002：回滚后再次发布因 fetch 非快进被拒

- status: guarded
- first_seen: 2026-09-06
- severity: high
- symptom: 回滚演练第 2 路（重复失败发布）中，`git fetch server.bundle` 因传输游标非快进被拒，发布在合入阶段失败；生产回滚后下一次发布会命中同一失败。
- root_cause: bundle 传输游标复用普通分支引用，fetch 默认拒绝非快进更新；回滚把 HEAD 指回旧提交，新包相对游标不再是快进。
- impact: 回滚成功但后续发布被阻断，恢复时间不可预测；演练前生产脚本同样存在该缺陷。
- fix: 取数引用改为强制更新，传输游标语义与分支历史解耦；演练覆盖回滚后再次发布路径。
- new_guardrail: `backend/scripts/drill_deploy_rollback.sh` 三路演练（失败回滚、重复回滚、健康上线）；发布脚本引用变更必须经演练验证。
- verification: `bash backend/scripts/drill_deploy_rollback.sh` 三路通过；三个脚本 `bash -n` 语法通过。
- linked_trace: `20260906-audit-remediation`
- linked_files: `backend/scripts/deploy_server.sh`; `backend/scripts/drill_deploy_rollback.sh`
- next_time_signal: 修改发布取数或回滚引用后，若演练三路未全过，不得声明发布恢复收口。

## M-20260906-001：测试补丁撤销误触真实开发库

- status: guarded
- first_seen: 2026-09-06
- severity: high
- symptom: 新测试中调用 `monkeypatch.undo()` 恢复单个补丁，顺带撤销了同夹具的 `DB_PATH` 补丁，后续回调在真实开发库 `backend/data/bot.db` 落库，单跑通过、联跑失败且污染开发数据。
- root_cause: `monkeypatch.undo()` 撤销该用例全部补丁，而 `DB_PATH` 补丁与被测补丁共享同一 `monkeypatch` 实例；测试未声明数据库隔离断言，污染直到联跑失败才暴露。
- impact: 开发库写入 3 行测试假数据（已清理）；若假游标残留，企微同步重跑会跳过真实消息。
- fix: 改用 `monkeypatch.setattr` 显式恢复单个目标，不调用 `undo()`；清理开发库测试行并复核为 0。
- new_guardrail: 故障注入测试必须使用显式恢复单个补丁；涉及 `DB_PATH` 的测试不得调用 `monkeypatch.undo()`。
- verification: `python -B -m pytest backend/tests/service/wecom/test_kf_callback_processor.py backend/tests/service/wecom/test_kf_sync_atomicity.py backend/tests/repository/test_wecom_kf_sync_repo.py -q --no-cov -p no:cacheprovider` 联跑通过；开发库复核三表残留均为 0。
- linked_trace: `20260906-audit-remediation`
- linked_files: `backend/tests/service/wecom/test_kf_sync_atomicity.py`
- next_time_signal: 新增或修改 `DB_PATH` 相关测试后，若出现单跑过联跑失败，必须先查补丁恢复范围与真实库残留，不得只重跑单文件收口。

## M-20260831-002：中文注释扫描器误判 URL、资源和工具指令

- status: guarded
- first_seen: 2026-08-31
- severity: medium
- symptom: 非 Python 注释扫描器把字符串中的 URL、内嵌 SVG 的 `//`、TypeScript 的 `/// <reference>` 以及多行 CSS 分隔注释误判为英文自然语言注释，导致中文治理 P0 门禁错误失败。
- root_cause: 使用单行正则直接搜索斜杠标记，没有区分字符串、跨行注释和编译器工具指令。
- impact: 合法源文件被错误阻断，真实英文注释缺口与扫描器噪声混在一起，无法稳定判断六维中文治理覆盖率。
- fix: 改用字符串外状态机提取 `//`、`/* */`、`<!-- -->` 注释；跳过 URL、内嵌资源和 `/// <reference>`；对实际自然语言英文注释逐项翻译并保留技术标识白名单。
- new_guardrail: `backend/tests/scripts/test_check_chinese_governance.py` 增加英文注释、模型缺维度、协作模板缺字段和英文界面文案负向测试；提交前通过 Harness 中文治理 P0 钩子执行全仓扫描。
- verification: `python -B -m pytest backend/tests/scripts/test_check_chinese_governance.py -q --no-cov -p no:cacheprovider` → EXIT=0（9 passed）；`python -B backend/scripts/check_chinese_governance.py --summary` → EXIT=0（coverage=1.0，dimension_ratio=1.0）。
- linked_trace: `20260831-harness-p0-hardening`
- linked_files: `backend/scripts/check_chinese_governance.py`; `backend/tests/scripts/test_check_chinese_governance.py`; `.pre-commit-config.yaml`; `docs/harness-engineering/core/chinese-governance.json`
- next_time_signal: 修改注释扫描规则后若 URL、内嵌资源或工具指令再次被报为自然语言，必须先补解析边界测试，不得直接扩大英文白名单。

## 单一入口原则

`ERRORS.md` 是本项目唯一正式错误账本。其他历史路径只能保留兼容说明，不得新增条目；新增错误必须直接写入本文件并运行 `python -B backend/scripts/check_mistake_ledger.py`。

## M-20260831-001：P0 门禁扩展未同步 Harness 自评与质量工作流

- status: guarded
- first_seen: 2026-08-31
- severity: high
- symptom: 为 P0 门禁新增“依赖锁一致性”后，本地 P0 门禁已变为 9 项，但 `harness_eval_regression.py` 仍固定期待 8 项，导致 P0 门禁通过而 Harness 自评实际失败（7/8）。P1/P2 工作流的触发路径也未覆盖 P0 门禁与依赖锁变更，直接推送主线时不会自动暴露该漂移。
- root_cause: P0 门禁清单、自评基线和 P1/P2 CI 触发范围分散维护，扩展检查项时只更新了门禁本体及其单测。
- impact: 会形成“本地 P0 通过、持续质量信号失效”的错误收口结论；云端依赖解析问题无法在安装前提供结构化诊断。
- fix: 为生产/开发锁增加约束与一致性检查；P0 门禁纳入第九项；自评基线同步为九项；P1/P2 工作流同时覆盖 Harness 门禁、依赖锁、相关测试和 workflow 配置变更。
- new_guardrail: 修改 `harness_p0_gate.build_commands()` 时，必须同时运行 `harness_eval_regression.py --summary` 和 `test_harness_eval_regression.py`；质量工作流必须在主线与 PR 的 Harness 门禁、依赖锁或工作流变更上触发。
- verification: `python -B -m pytest backend/tests/scripts/test_harness_eval_regression.py backend/tests/scripts/test_harness_p0_gate.py backend/tests/scripts/test_check_requirements_lock_alignment.py backend/tests/scripts/test_observe_harness_runs.py backend/tests/scripts/test_check_doc_garden.py -q --no-cov -p no:cacheprovider --basetemp D:\Project\YunxiBakery\.tmp-harness-lock-tests\quality-loop-sync` → EXIT=0（18 passed）；`python -B backend/scripts/harness_p0_gate.py --summary` → EXIT=0（9/9）；`python -B backend/scripts/harness_eval_regression.py --summary` → EXIT=0（8/8）。
- linked_trace: `20260831-harness-p0-hardening`
- linked_files: `backend/scripts/check_requirements_lock_alignment.py`; `backend/scripts/harness_p0_gate.py`; `backend/scripts/harness_eval_regression.py`; `.github/workflows/harness-p0.yml`; `.github/workflows/harness-p1-p2.yml`; `backend/tests/scripts/test_harness_p0_gate.py`; `backend/tests/scripts/test_harness_eval_regression.py`; `backend/tests/scripts/test_check_requirements_lock_alignment.py`
- next_time_signal: P0 门禁项数或顺序变化后，若 Harness 自评不是 8/8 通过，或 P1/P2 workflow 未因该变更触发，则不得声明 Harness 治理收口。

## M-20260830-005：已否决事项被重新激活为当前待办

- status: guarded
- first_seen: 2026-08-30
- severity: high
- symptom: 项目负责人已经否决 FAQ 店家回收事项，后续 Agent 仍将 P1-7 重新写成阻塞待办，并新建填写版文件，造成任务复活和方向漂移。
- root_cause: 启动时只读取当前状态表和任务指令，没有先核对负责人否决/排除决策；状态模型也没有单独展示“已否决事项”区域。
- impact: 浪费执行时间，可能误发店家填写请求、误采集业务事实，破坏单一权威入口和负责人决策边界。
- fix: 将 T-P1-7-FAQ 改为历史（historical），在任务文件和 FAQ 草案加“已否决、禁止执行”标记，删除本轮误建填写版，并从待办清单和交接文档移除。
- new_guardrail: 新任务启动必须同时核对当前待办和负责人否决/排除项；已否决事项只能保留历史证据，不能出现在未完成状态视图或下一步顺序中。
- verification: `python -B backend/scripts/check_project_development_register.py` → EXIT=0；`python -B backend/scripts/check_mistake_ledger.py` → EXIT=0；全仓检索确认不存在 `faq-template-fillable-20260830.md` 当前入口。
- linked_trace: `20260830-p1p2-state-correction`
- linked_files: `PROJECT-STATE.md`; `docs/待办优先级清单_20260829.md`; `docs/AGENT-HANDOFF-20260829.md`; `docs/tasks/20260829-P1-7-FAQ回收-指令.md`; `docs/specs/faq-template-draft.md`
- next_time_signal: 任何已否决事项再次进入 pending、blocked 或下一步列表时，必须立即阻断并要求负责人重新明确批准。

## M-20260830-004：发票承接 API 未完整执行状态与必填校验

- status: verified
- first_seen: 2026-08-30
- severity: medium
- symptom: 发票登记 API 可以创建并标记记录，但已为 `issued` 的记录再次标记仍返回 200；缺少企业抬头、税号或邮箱时也会被归一为空字符串并成功登记。
- root_cause: 请求模型为三个字段提供空字符串默认值，仓储更新只用 `status != 'issued'` 避免重复写入，却没有把“未更新”转为非法状态流转错误。
- impact: 后台可能重复执行开票动作或保存不可执行的开票请求，P1 发票验收和 P2 E 项无法闭环。
- fix: API 模型将三个字段改为必填；服务层拒绝缺失、非字符串和空白值；仓储层使用 `status = 'applied'` 条件更新并检查 `rowcount`，服务层将非法状态转换映射为 409。
- new_guardrail: `backend/tests/api/test_admin_invoice_api.py` 固化创建、列表、标记已开、重复标记和三个必填字段缺失场景；P1-5 在这些用例全部通过且完成 E1-E4 前保持阻塞。
- verification: `python -B -m pytest backend/tests/api/test_admin_invoice_api.py -q --no-cov -p no:cacheprovider` → EXIT=0（7 passed）；相关 Ruff check 与 format check → EXIT=0。
- linked_trace: `20260830-p1p2-continue`
- linked_files: `backend/app/api/admin/invoices.py`; `backend/app/service/invoice/admin.py`; `backend/app/repository/invoice_repo.py`; `backend/tests/api/test_admin_invoice_api.py`; `docs/tasks/20260829-P1-5-发票承接验收-指令.md`
- next_time_signal: 发票状态再次标记未返回 409，或缺少抬头/税号/邮箱的请求未被 400/422 拒绝时，禁止将 P1-5 或 P2 E 项标记为完成。
- closeout_20260906: 4 项严格 `xfail` 已移除，代码缺口已修复；发票仍需完成 `T-P1-5-INVOICE` 的 E1-E4 真实客服、后台和联动验收，代码修复不等同于真实验收。

## M-20260830-001：中文管理要求未下沉到 Harness 防线

- status: guarded
- first_seen: 2026-08-30
- severity: medium
- symptom: 管理回复和状态文档直接暴露 `completed`、`blocked` 等机器状态码，未按项目“中文优先”要求提供中文状态说明，造成阶段状态理解偏差。
- root_cause: 将机器字段兼容要求误当成面向人的展示要求，且缺少对 `PROJECT-STATE.md` 中文叙述和任务指令状态说明的自动校验。
- impact: 项目负责人需要额外追问状态含义；多 Agent 可能把技术完成、治理关闭和阻塞条件混读，增加方向不一致风险。
- fix: 增加 `status_label` 与主表“状态说明”列；更新 AGENTS、Harness Skill、协作规则、提交流程和任务指令；新增开发总表守卫及回归测试。
- new_guardrail: `check_project_development_register.py` 校验状态中英映射并拒绝中文叙述裸写机器状态码；提交前通过 `check_project.py --skip-tests` 自动覆盖。
- verification: 开发总表专项测试 12/12；开发总表守卫 EXIT=0；项目总守卫 EXIT=0；证据索引、文本编码和 Ruff 检查通过。
- linked_trace: `20260830-chinese-status-display-guard`
- linked_files: `backend/.agents/skills/yunxi-harness-engineering/SKILL.md`; `AGENTS.md`; `docs/AGENTS/multi-agent-coordination.md`; `docs/AGENTS/commit-workflow.md`; `backend/scripts/check_project_development_register.py`
- next_time_signal: 任何新增或修改任务状态未同步 `status_label`，或中文叙述出现裸机器状态码时，开发总表守卫必须立即失败。

## M-20260830-002：错误账本存在多份镜像，造成管理入口分叉

- status: guarded
- first_seen: 2026-08-30
- severity: high
- symptom: 根 `docs/` 与 `backend/docs/` 各自保留一份 `mistake-ledger.md`，当前条目数量和内容不一致；不同 Agent 可能读取不同副本，导致错误记录、检查结果和修复方向分叉。
- root_cause: Monorepo 整合时保留旧仓文档树镜像，未在权威源层级中明确错误账本的唯一正式路径；检查器默认路径也曾落到 `backend/docs/`。
- impact: 新错误可能只写入某一副本；检查通过不能证明当前账本完整；长期累积后无法判断哪份记录有效。
- fix: 将当前账本迁移为根目录 `ERRORS.md`；旧路径改为仅指向 `ERRORS.md` 的兼容说明；检查器和现行 Skill、规范、工作流统一引用根文件。
- new_guardrail: `check_mistake_ledger.py` 默认只检查根 `ERRORS.md`；重复 ID 直接阻断；项目规则新增“尽可能单一正式文件、兼容入口不得承载内容”。
- verification: 根账本与旧路径引用扫描通过；重复 ID 回归测试通过；`python -B backend/scripts/check_mistake_ledger.py` EXIT=0。
- linked_trace: `20260830-errors-ledger-canonicalization`
- linked_files: `ERRORS.md`; `docs/harness-engineering/core/mistake-ledger.md`; `backend/docs/harness-engineering/core/mistake-ledger.md`; `backend/scripts/check_mistake_ledger.py`
- next_time_signal: 发现新的同职能文档、副本或检查器默认路径指向非根账本时，必须先停止扩展并回到 `ERRORS.md` 单一入口。

## M-20260830-003：开发迭代未区分定向测试与全量收口

- status: guarded
- first_seen: 2026-08-30
- severity: medium
- symptom: 开发期间容易因每次改动重复执行全量测试，浪费时间并模糊“定向定位”和“上线候选收口”的验证边界。
- root_cause: 测试节奏、全量执行条件和耗时优化阈值没有在统一 Harness 规则中固化，也没有要求记录全量测试耗时。
- impact: 反馈周期变长；全量测试结果被重复执行稀释；慢测问题没有形成可追踪的优化事项。
- fix: 统一规定开发期优先定向测试；每个功能或模块上线候选时只执行一次全量测试；失败先定向定位，修复后最多一次最终复跑；全量耗时超过 10 分钟或较基线增加 20% 时登记优化事项。
- new_guardrail: 更新 `AGENTS.md`、Harness Skill、协作规则、验证矩阵和提交流程，明确纯文档/Harness 变更不要求全量测试并要求记录未运行原因。
- verification: 开发总表专项测试、Harness 门禁和文档一致性检查通过；本轮未运行全量测试，原因已记录为纯文档/Harness 变更。
- linked_trace: `20260830-test-cadence-governance`
- linked_files: `AGENTS.md`; `backend/.agents/skills/yunxi-harness-engineering/SKILL.md`; `docs/harness-engineering/core/verification-matrix.md`; `docs/AGENTS/commit-workflow.md`
- next_time_signal: 任何非上线候选任务重复运行全量测试，或全量结果缺少耗时/基线比较时，收口检查必须要求补充说明或建立优化事项。

______________________________________________________________________

## M-20260812-001：feat 提交在 Windows 上被 pre-commit 按 patch 递增版本

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

## M-20260812-002：提交被门禁拦下后重试导致 VERSION 双次递增

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


## M-20260813-001：服务构造期访问 _db 导致生产启动崩溃

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
- next_time_signal: 新服务若在构造期访问数据库依赖，必须由裸构造回归测试和 lifespan 装配检查立即发现。

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

## M-20260824-001：MVP 范围误判为"三大功能"+ 知识库按"从零创建"排期

- status: guarded
- first_seen: 2026-08-24
- severity: high
- symptom: MVP 范围被误判为"三大功能"，计划书写明小程序/积分/储值/券推迟 v2.0；知识库被按"从零创建"排期重新起草问卷（FAQ 十条填空模板）。
- root_cause: 规划需求获取未问"小程序替代什么/哪些模块生死攸关"，把完整电商平台（15 页面小程序 + 16 后端服务域 + M1-M5 会员资产模块）误判为 AI 客服附加品；且未盘点旧库资产先定任务——旧库已有 638 条业务知识（含 24 条人工沉淀）与全套凭证，规划却按空系统起步。
- impact: 项目负责人产生"从 0 开始"错觉；一轮无效工作量（FAQ 模板作废）；差点造成模块砍单错误——若按 v1.0 执行，自研电商替代有赞的核心模块（会员资产/小程序）将被砍出范围，2027-06 上线的业务前提不成立。
- fix: 架构师范围修正 v1.2（计划书附录D）：撤回推迟决定，电商/会员资产/小程序完全承接不可砍；P1 重定义为"全模块承接验证"（后端全域 API 冒烟 + 小程序 15 页面走查 + 跨端链路验证），Week2+ 旧任务作废；新增 P0.5 资产迁移阶段承接凭证与知识存量；FAQ 填空问卷作废，改走选择性迁移 + 迁移后缺口对比。
- new_guardrail: ①`PROJECT-STATE.md` 建立为唯一状态活页入口（每周收口更新、架构师复核，迷路先看它）；②规划原则"先盘库存，再定任务"写入计划书附录 C.2——任何"创建/获取"类任务下达前先回答"它是否已存在"；③范围裁剪决定前置确认问题固化为流程要求（见 next_time_signal）。
- verification: 三文件入库（PROJECT-STATE.md / 计划书附录C+D / MVP-DEVELOPMENT-GUIDE.md 警示横幅）；LOGBOOK trace `20260824-scope-correction-v12` 登记；实质验证待 P0.5 迁移命中测试与 P1 全模块承接验证完成。
- linked_trace: `20260824-scope-correction-v12`
- linked_files: `PROJECT-STATE.md`; `项目重构与推进计划书.md`（附录C+D）; `MVP-DEVELOPMENT-GUIDE.md`; `docs/specs/faq-template-draft.md`（作废留档）
- next_time_signal: 任何范围裁剪决定前，必须先向项目负责人确认"这个模块替代什么、砍掉后业务是否成立"；任何"创建"类任务前必须先盘点存量资产（代码/数据/知识/凭证），盘点结果写入 PROJECT-STATE.md 资产地图后再排任务。

## M-20260817-001：Monorepo 整合脚本全量复制把客户数据库带入新仓工作目录

- status: guarded
- first_seen: 2026-08-17
- severity: critical
- symptom: 执行 monorepo-merge.ps1 整合双仓时，`Copy-Item -Recurse -Force` 全量复制把 `backend\data\bot.db`（17.8MB，24,726 条真实客户主档 + openid 关联）连同 `.mypy_cache`、`htmlcov`、`ngrok.exe`、`node_modules` 等运行时产物一并复制进新仓 `D:\Project\YunxiBakery\backend\` 工作目录；架构评审 A1 事后核查发现。
- root_cause: 整合脚本只排除了 `.git`，没有定义隐私数据与运行时产物排除清单；"复制什么"由文件系统默认行为决定，而不是由显式白名单决定。
- impact: 本次因新仓 .gitignore 的 `*.db` 规则恰好生效，bot.db 未被 Git 跟踪、未推送 GitHub（`git ls-tree -r origin/main` 复核零命中），未构成实际泄露；若 .gitignore 规则缺失或被调整，2.4 万客户个人数据将随首次 push 进入远端仓库历史，且 force push 也无法从已克隆方撤回。
- fix: 从新仓工作目录清除 bot.db 副本与全部运行时产物；monorepo-merge.ps1 增加排除清单（data/、*.db、*.sqlite*、ngrok.exe、各类 cache、node_modules、.codex-tmp、reports）并在 Step 3/4 复制后逐项删除；Step 8 提交前增加双重隐私断言（工作区 Get-ChildItem 检查 + git ls-files 跟踪清单检查），任一命中立即退出非零阻断提交。
- new_guardrail: 脚本级——排除清单 + 提交前硬门禁断言（scripts/monorepo-merge.ps1 L31 排除定义、L450 断言逻辑）；流程级——架构评审将"迁移脚本必须含排除清单"列为执行前置条件（ARCHITECTURE-REVIEW-20260817.md 第五节通过条件 #1）；策略级——技术债不允许项新增第五条"客户隐私数据明文暴露"（计划书 B1）。
- verification: 新仓 `git ls-files` 全量匹配 .db/.sqlite/.csv/ngrok.exe 零命中（1379 文件）；GitHub 远端 ls-tree 复核零命中；修正版整合以 master b30b2066 基线重做并 force push 为唯一初始 commit `1c2a3ea`。
- linked_trace: `20260817-monorepo-merge-review-fixed`
- linked_files: `scripts/monorepo-merge.ps1`; `ARCHITECTURE-REVIEW-20260817.md`; `项目重构与推进计划书.md`; `LOGBOOK.md`（2026-08-17 chore(monorepo) 条目）
- next_time_signal: 任何跨仓库/跨目录的批量复制操作（Copy-Item -Recurse、rsync、robocopy）在提交或推送前，必须运行隐私断言（数据库/CSV/二进制工具零命中）；新增数据文件落盘路径时同步检查 .gitignore 是否覆盖。

## M-20260711-009：生产快照通过删除黑名单推断安全

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
python -B backend/scripts/check_mistake_ledger.py
```

检查内容：

- 空账本必须保留“暂无正式条目”标记。
- 正式条目标题必须使用 `M-YYYYMMDD-001：标题` 格式。
- 正式条目必须包含模板里的全部字段。
- 正式条目 ID 不得重复；非条目二级标题不能污染相邻条目。
- `status` 只能是 `open`、`guarded`、`verified`。
- `severity` 只能是 `low`、`medium`、`high`、`critical`。

该检查由 `backend/.pre-commit-config.yaml` 的 `check-mistake-ledger` hook 保留，并可在根目录手动运行。账本一旦出现格式漂移，会在提交前被发现，而不是等到后续 Agent 读取时才踩坑。
## M-20260908-001：单文件编辑工具误用导致治理文件重复试错

- status: guarded
- first_seen: 2026-09-08
- severity: medium
- symptom: 连续使用批量补丁接口对同一路径执行删除+新增，接口拒绝“multiple operations target”并未落盘。
- root_cause: 未按工具 schema 选择单文件 replace 操作，且失败后重复了同一调用方式。
- impact: 治理文件未能及时收口，浪费执行轮次；业务源码未被覆盖。
- fix: 改用单文件替换接口；后续同一路径只执行一个编辑操作，失败后先读取当前内容和工具 schema，再更换方法。
- new_guardrail: 编辑失败三次后必须暂停重试并写入 ERRORS.md，随后只允许使用已确认匹配 schema 的单文件操作。
- verification: 当前条目保留在 ERRORS.md，并在本轮继续执行前完成任务登记文件解析检查。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `ERRORS.md`; `backend/scripts/check_mistake_ledger.py`
- next_time_signal: 新增错误条目若缺少治理字段，账本检查必须在继续业务改动前失败并先修复。

## M-20260908-002：补丁上下文与文件实际内容不一致

- status: guarded
- first_seen: 2026-09-08
- severity: medium
- symptom: 对已有文件使用过大的上下文块进行替换时，工具报告找不到预期行；文件编码/换行或当前内容与记忆不一致。
- root_cause: 编辑前未先读取足够精确的原文上下文，且在失败后继续使用同一批量删除+新增方式。
- impact: 该轮未改动目标业务文件；执行时间被编辑方式试错消耗。
- fix: 以后只使用已成功验证的 `apply_patch_add_file` 新增文件或 `apply_patch_update_file` 小范围 hunk；现有文件先读取精确行，再改单一职责。
- new_guardrail: 同一补丁失败后不得原样重试；失败三次即记录 ERRORS.md 并换成小 hunk 或先停止编辑。
- verification: 已追加本条目；新增配送 API 文件已成功落盘，后续将以单文件小步方式继续。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `ERRORS.md`; `backend/app/api/channels/storefront/delivery.py`; `backend/app/service/delivery/`
- next_time_signal: 新增配送领域文件若未完成单文件读取确认，禁止继续扩展跨层实现。

## M-20260908-004：视觉走查发现商品信号和未登录结算状态不符合业务主路径

- status: guarded
- first_seen: 2026-09-08
- severity: medium
- symptom: DevTools 截图显示首页首屏由无商品图的促销块占据，推荐商品被固定底栏遮挡；商品详情无商品时主体近乎空白；未登录结算仍展示可填写表单和提交订单按钮。
- root_cause: 商品货架排序晚于品牌宣传块，页面底部空间未覆盖多层固定栏，空态和登录状态没有按交易动作收敛。
- impact: 用户不能在首屏快速选购，可能误以为未登录仍可提交订单，核心购买路径的理解和转化受损。
- fix: 将精选商品前置，统一固定栏底部留白，完善商品详情和结算空态动作；通过微信开发者工具逐页复验。
- new_guardrail: 视觉走查同时检查首屏商品可见性、固定元素遮挡和未登录状态是否暴露核心写操作。
- verification: 本轮 DevTools 15 页面结构走查 15/15、控制台 warning/error 0；关键视觉问题已由截图复核，修复验证待完成。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `miniapp/miniprogram/pages/home/`; `miniapp/miniprogram/pages/products/`; `miniapp/miniprogram/pages/product-detail/`; `miniapp/miniprogram/pages/cart/`; `miniapp/miniprogram/pages/checkout/`
- next_time_signal: 关键交易页视觉走查再次发现固定栏遮挡、首屏无商品或未登录状态暴露提交动作时，必须先阻断验收并修复。

## M-20260908-005：走查脚本缺少已存在的 npm 命令入口

- status: guarded
- first_seen: 2026-09-08
- severity: low
- symptom: scripts/walkthrough-phase-c.mjs 存在，但 npm run walkthrough:phase-c 返回 Missing script。
- root_cause: package.json 未登记该已有走查脚本。
- impact: 按文档或脚本名称执行会失败，需要改用裸 node 命令，降低验证可发现性。
- fix: 后续补齐稳定 npm script，并保持原有 node 入口兼容。
- new_guardrail: 每个纳入验收的脚本必须同时有 package.json 命令和 node --check 可执行入口。
- verification: 已用 node scripts/walkthrough-phase-c.mjs 完成本轮 15 页截图走查；npm script 修复待完成。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `miniapp/package.json`; `miniapp/scripts/walkthrough-phase-c.mjs`
- next_time_signal: 纳入验收的脚本若没有 package.json 稳定入口或 node --check 结果，必须视为验证入口不完整。

## M-20260908-006：DevTools 走查截图超时导致页面验收串扰

- status: guarded
- first_seen: 2026-09-08
- severity: medium
- symptom: 走查脚本将截图和页面导航共用 12 秒超时；截图超时后未隔离未完成调用，后续页面出现路由错配，报告仍以成功退出。
- root_cause: 自动化脚本将慢速截图当作普通页面操作处理，且未把路由一致性和截图错误纳入进程退出码。
- impact: 15 页面报告可能把错误页面数据归属到目标页面，无法作为页面视觉验收证据。
- fix: 单独配置截图超时，记录页面路由一致性，并在截图错误、路由错配或控制台警告/错误时以非零状态退出。
- new_guardrail: DevTools 视觉走查报告只有在每页截图成功、当前路由匹配且控制台无 warning/error 时才可标记为通过。
- verification: 修复后重新运行 `npm run walkthrough:phase-c` 并复核报告与关键截图。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `miniapp/scripts/walkthrough-phase-c.mjs`; `miniapp/reports/devtools/walkthrough-phase-c.json`; `ERRORS.md`
- next_time_signal: 再次发生截图超时或路由错配时，脚本必须非零退出并阻断视觉验收结论。

## M-20260909-005：当天预订规则测试需要固定时钟，避免历史夹具随自然日期失效

- status: guarded
- first_seen: 2026-09-09
- severity: medium
- symptom: 订单预约夹具大量使用固定的 `2026-06` 日期；直接加入“不得预约过去时间”校验后，测试会随当前系统日期全部变成过去预约。
- root_cause: 既有测试没有显式的业务时钟注入，预约服务直接依赖系统当前时间。
- impact: 回归测试结果不可复现，业务规则可能被迫放宽或被历史数据掩盖。
- fix: `OrderScheduleService` 支持可注入 `now_provider`；共享测试夹具将校验时钟固定为北京时间 `2026-06-17 12:00`，专用用例覆盖过去、当天截止前和当天截止后三态。
- new_guardrail: 任何依赖当前日期或截止时间的订单规则必须通过注入时钟测试，禁止用自然时间让固定历史夹具偶发失效。
- verification: `cd backend && pytest tests/service/test_order.py -q --no-cov` 通过；`ruff check app/service/order/schedule.py tests/conftest.py tests/service/test_order.py` 通过。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `backend/app/service/order/schedule.py`; `backend/tests/conftest.py`; `backend/tests/service/test_order.py`
- next_time_signal: 新增订单时间规则时，先声明业务时区、注入时钟和边界测试，再修改既有预约校验。

## M-20260909-006：长文档补丁漏行前缀导致日志补丁未落盘

- status: guarded
- first_seen: 2026-09-09
- severity: medium
- symptom: 更新 `LOGBOOK.md` 的长补丁时，有一行正文缺少 `+` 前缀，`apply_patch` 报告 invalid hunk，文件未修改。
- root_cause: 多文件长补丁没有保持每一行的补丁操作前缀，失败后又未立即拆分到单文件小块。
- impact: 日志证据写入延迟，浪费一次执行轮次；源码和已有文档内容未被覆盖。
- fix: 记录错误后改为单文件、小段落补丁；每次补丁后立即读取目标段落确认落盘。
- new_guardrail: 治理文档只使用短 hunk；长自然语言段落逐行带操作前缀，补丁失败不原样重试。
- verification: `check_mistake_ledger.py` 与本轮治理检查共同验证。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `LOGBOOK.md`; `ERRORS.md`
- next_time_signal: 更新日志或证据索引时，优先追加单独的小段落，并在下一步读取尾部确认。

## M-20260909-007：PowerShell 内联 Node 脚本插值破坏 DevTools 选择器

- status: guarded
- first_seen: 2026-09-09
- severity: low
- symptom: 使用 PowerShell 双引号执行内联 `node -e` 审计时，脚本中的 `$` 被 PowerShell 先解释，生成了 `p..time-preview` 等非法 JavaScript，导致当天预订运行态审计没有真正执行。
- root_cause: PowerShell 双引号字符串会进行变量和子表达式插值，内联 Node 脚本中的 `$()` 选择器表达式没有被当作原始 JavaScript 传递。
- impact: 本次命令未修改源码、订单或测试数据，但会产生“命令失败原因不清”的假象，延迟当天预订边界的运行态验证。
- fix: 将审计逻辑落到独立的 `verify-devtools-same-day-scheduling.cjs` 文件，并通过 npm script 执行；脚本只读取页面状态和元素文本，不提交登记。
- new_guardrail: Windows PowerShell 下禁止用双引号包装包含 `$` 的内联 Node 脚本；需要复跑时使用独立 `.cjs` 文件或单引号包装，并先运行 `node --check`。
- verification: `cd miniapp && node --check scripts/verify-devtools-same-day-scheduling.cjs` 退出码 0；`cd miniapp && npm run devtools:same-day-scheduling` 退出码 0，报告为 PASS。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `miniapp/scripts/verify-devtools-same-day-scheduling.cjs`; `miniapp/package.json`; `miniapp/reports/devtools/same-day-scheduling-audit.json`
- next_time_signal: DevTools 运行态审计若依赖 `$` 选择器或模板字符串，先使用文件脚本并回读文件，再执行验证。

## M-20260909-008：DevTools 审计并发占用同一调试连接

- status: guarded
- first_seen: 2026-09-09
- severity: medium
- symptom: 同时启动 `devtools:verify-all-pages` 与 `devtools:commerce-states`，两个脚本竞争 `ws://127.0.0.1:9420`；全页审计继续运行，状态审计无输出并挂起。
- root_cause: 微信开发者工具自动化连接不是并发安全的，本轮操作没有遵守项目要求的单会话串行约束。
- impact: 状态审计未形成有效结果，需要停止本轮明确创建的审计进程后重新串行运行；源码、订单、支付和测试数据未被修改。
- fix: 已通过进程命令行确认后，仅停止本轮 `commerce-states` 的 npm、cmd 和 node 进程；后续所有 DevTools 脚本串行执行，前一个进程退出后才启动下一个。
- new_guardrail: 小程序 DevTools 验证队列一次只允许一个自动化脚本持有调试连接；并行文件检查可以并行，DevTools 操作不得并行。
- verification: `verify-all-15-pages-devtools.cjs` 15/15 PASS；状态审计将在串行条件下重新执行。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `miniapp/scripts/verify-all-15-pages-devtools.cjs`; `miniapp/scripts/verify-devtools-commerce-states.cjs`; `ERRORS.md`
- next_time_signal: 需要执行多个 DevTools 审计时，先等待前一脚本取得退出码，再启动下一脚本，不使用并行工具包装。

## M-20260909-009：工作目录切换后残留检查使用错误相对路径

- status: guarded
- first_seen: 2026-09-09
- severity: low
- symptom: 在 `miniapp` 工作目录执行残留样式检查时，仍使用 `miniapp/miniprogram/...` 路径，`rg` 报路径不存在。
- root_cause: 命令工作目录和相对路径前缀没有保持一致。
- impact: 该次 `rg` 没有形成有效的残留检查证据；同一命令中的 TypeScript 和小程序静态检查仍返回通过，源码和运行数据未受影响。
- fix: 改为在仓库根目录使用完整相对路径，或在 `miniapp` 目录使用 `miniprogram/...` 路径；本轮将分开重跑残留检查、类型检查和静态检查。
- new_guardrail: 每次执行命令前明确记录 workdir；禁止在已切换子目录后重复拼接仓库目录前缀。
- verification: 修正路径后重新执行 `rg`，并分别执行 `npm run typecheck` 与 `npm run check:miniapp`。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `miniapp/miniprogram/app.wxss`; `miniapp/miniprogram/pages/`; `ERRORS.md`
- next_time_signal: 目录检查命令的路径必须与 workdir 同时审阅，禁止把组合命令的部分通过当成整体证据。

## M-20260909-010：并行检查编排参数嵌套错误

- status: guarded
- first_seen: 2026-09-09
- severity: low
- symptom: 并行执行详情页、商品页和购物车残留检查时，第三个工具调用参数被错误地嵌套为字符串，编排脚本报 JavaScript 语法错误，目标检查未执行。
- root_cause: 组合工具参数没有保持统一的对象结构。
- impact: 该次检查没有产生文件或运行态副作用，但浪费一次执行轮次；其余两个并行读取仍正常完成。
- fix: 取消该错误调用，改用单独、结构明确的命令重新执行全部残留检查。
- new_guardrail: 组合工具只传递合法的工具参数对象；复杂 PowerShell 检查先单独执行，再汇总结果。
- verification: 修正后的残留检查、类型检查、小程序静态检查和 DevTools 审计共同验证。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `miniapp/miniprogram/pages/`; `ERRORS.md`
- next_time_signal: 工具编排失败时不得把其他并行调用的通过结果当作完整证据，必须重新执行未完成的目标检查。

## M-20260909-016：次级页面读取命令重复遗漏 miniapp 路径前缀

- status: guarded
- first_seen: 2026-09-09
- severity: low
- symptom: 在仓库根目录读取次级页面样式时使用了 miniprogram/...，实际文件位于 miniapp/miniprogram/...，多个 Get-Content 命令返回路径不存在。
- root_cause: 本轮读取命令未统一使用仓库根目录或 miniapp 子目录的路径约定。
- impact: 只影响本次代码读取，没有修改源码、订单、支付或测试数据；次级页面视觉审计尚未因该命令形成证据。
- fix: 改用仓库根目录的绝对路径读取，并在后续命令中固定声明 workdir 与路径策略。
- new_guardrail: 多文件读取前先用 rg --files 确认根路径；同一批命令只使用一种 workdir/路径组合。
- verification: 修正路径后完成次级页面样式审阅，再运行全页面 DevTools 审计。
- linked_trace: 20260908-miniapp-commerce-ux-redesign
- linked_files: miniapp/miniprogram/pages/; miniapp/miniprogram/components/; ERRORS.md
- next_time_signal: 进入子目录或使用仓库根目录时，命令和路径必须成对复核。

## M-20260909-011：残留扫描正则中的括号未转义

- status: guarded
- first_seen: 2026-09-09
- severity: low
- symptom: 扫描旧颜色和旧文案时把含括号的 `rgba(... )` 片段直接放入正则，`rg` 报 unclosed group，扫描未执行。
- root_cause: 正则元字符没有转义，且本次扫描本可使用固定字符串查询。
- impact: 没有修改源码、订单或测试数据；该次扫描没有形成证据。
- fix: 改用不含括号的固定关键词分组扫描，避免把命令解析问题误判为源码问题。
- new_guardrail: Windows 下做残留检查优先使用 `rg --fixed-strings` 或逐项关键词查询；只有确需正则时才转义括号并先单独验证。
- verification: 修正命令后完成旧视觉残留扫描，再运行最终类型、静态和 DevTools 审计。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `miniapp/miniprogram/app.wxss`; `miniapp/miniprogram/pages/`; `ERRORS.md`
- next_time_signal: 复杂命令失败时，先确认失败发生在扫描器还是目标文件，再重试最小等价命令。

## M-20260909-012：治理文档补丁中的反引号破坏编排字符串

- status: guarded
- first_seen: 2026-09-09
- severity: low
- symptom: 将包含反引号代码标记的长治理补丁直接放入 JavaScript 模板字符串，编排器报 Unexpected identifier，补丁未执行。
- root_cause: 补丁文本的反引号未转义，提前结束了外层模板字符串。
- impact: LOGBOOK、证据索引和项目状态均未被部分写入；源码、订单、支付和测试数据未受影响。
- fix: 已放弃该长补丁，改为三个不含嵌套反引号的独立小补丁，并在每个补丁后回读目标段落。
- new_guardrail: 治理文档补丁不得把未转义反引号直接放入工具编排模板字符串；长记录按文件拆分。
- verification: 三个目标文件分别回读后，再运行治理检查器。
- linked_trace: 20260908-miniapp-commerce-ux-redesign
- linked_files: LOGBOOK.md; docs/harness-engineering/core/evidence-index.md; PROJECT-STATE.md; ERRORS.md
- next_time_signal: 自然语言补丁先检查模板边界字符，再执行 apply_patch。

## M-20260909-013：状态表替换补丁缺少删除行前缀

- status: guarded
- first_seen: 2026-09-09
- severity: low
- symptom: 更新 PROJECT-STATE.md 任务行时，补丁 hunk 中的旧行未使用删除前缀，apply_patch 报 Unexpected line found，补丁未执行。
- root_cause: 手工构造替换 hunk 时只提供了新增行，没有同时提供旧行删除标记。
- impact: PROJECT-STATE.md 没有被部分写入；此前已成功写入的 LOGBOOK.md 和 evidence-index.md 不受影响，源码、订单、支付和测试数据未受影响。
- fix: 按标准替换 hunk 补齐旧行删除前缀和新行新增前缀，并在执行后回读任务行。
- new_guardrail: 修改长表格行时先读取精确旧行，补丁必须同时包含以减号开头的旧行和以加号开头的新行。
- verification: PROJECT-STATE.md 任务行回读后运行开发总表和证据检查器。
- linked_trace: 20260908-miniapp-commerce-ux-redesign
- linked_files: PROJECT-STATE.md; ERRORS.md
- next_time_signal: apply_patch 报 hunk 格式错误时不重试原文，先核对每行操作前缀。

## M-20260909-014：全页面视觉残留审计发现次级页面仍未统一

- status: guarded
- first_seen: 2026-09-09
- severity: medium
- symptom: 对整个 miniapp 目录扫描后，客服、个人中心、订单、优惠券、充值和自定义 TabBar 仍存在旧绿色渐变、玻璃模糊或装饰性样式；此前只扫描核心购买链路，不能证明全页面视觉完成。
- root_cause: 上一轮把核心购买链路收口结果误当成全页面 UI/UX 收口结果，审计范围不完整。
- impact: 不影响当前业务接口或订单数据，但会造成页面间品牌系统不一致，违背本轮全页面 UI/UX 重构目标。
- fix: 已扩大样式收口到所有 15 个页面和共享组件，保留业务行为与现有审计类名；已逐页用微信开发者工具复核结构和运行态。
- new_guardrail: 视觉审计必须覆盖所有用户可达页面、共享组件和自定义 TabBar，不能只扫描商品购买主链路。
- verification: `npm run typecheck`、`npm run check:miniapp`、`npm run devtools:verify-all-pages`、`npm run devtools:commerce-states`、`npm run devtools:product-purchase-path` 和 `npm run devtools:same-day-scheduling` 均退出码 0；15/15 页面通过。
- linked_trace: 20260908-miniapp-commerce-ux-redesign
- linked_files: miniapp/miniprogram/pages/; miniapp/miniprogram/components/; miniapp/miniprogram/custom-tab-bar/; ERRORS.md
- next_time_signal: 页面级 UI 任务必须建立全页面文件清单，并在收口前逐项验证；结构通过不等于截图级像素验收通过。

## M-20260909-015：全页面扫描参数再次使用不兼容 PowerShell glob

- status: guarded
- first_seen: 2026-09-09
- severity: low
- symptom: 使用类 Bash 的大括号 glob 扫描 WXML 时，PowerShell 在参数解析阶段报 Missing argument，目标扫描没有执行。
- root_cause: PowerShell 不支持该形式的 brace expansion，且命令未按当前 shell 语法拆分。
- impact: 没有修改源码、订单或测试数据；该次扫描不产生任何有效证据。
- fix: 后续使用 rg --glob '*.wxml' 或明确目录参数，不使用 Bash 专属 glob 语法。
- new_guardrail: Windows PowerShell 下所有文件 glob 命令必须先用最小目录和单个 glob 验证，再扩大范围。
- verification: 改用兼容 PowerShell 的固定 glob 后重新执行全页面扫描。
- linked_trace: 20260908-miniapp-commerce-ux-redesign
- linked_files: miniapp/miniprogram/pages/; miniapp/miniprogram/components/; ERRORS.md
- next_time_signal: shell 相关命令失败时先确认 shell 语法，不将未执行的扫描当作源码结果。

## M-20260909-017：DevTools 单页截图在延长超时后仍未完成

- status: guarded
- first_seen: 2026-09-09
- severity: medium
- symptom: 单页运行态和当前路由均已稳定，但 `miniProgram.screenshot()` 在 `SCREENSHOT_TIMEOUT=60000` 下仍超时；本次 `pages/profile/index` 走查总耗时约 73 秒，脚本以非零退出。
- root_cause: 当前微信开发者工具的 `App.captureScreenshot` 调用未在自动化客户端等待窗口内完成，调用方超时无法取消底层请求。
- impact: 本次没有生成可确认对应页面的截图，不能把既有同名 PNG 作为本轮视觉证据；页面运行态、接口、订单、支付和测试数据未受影响。
- fix: 走查脚本改用页面专属临时文件，并仅在截图成功且截图前后路由仍为目标页面时替换正式图片；超时继续保留为失败，不再覆盖旧证据。
- new_guardrail: 截图级验收必须同时满足调用成功、临时文件存在、截图前后路由一致三项条件；任一不满足时只报告结构化运行态证据。
- verification: `MINIAPP_WALKTHROUGH_PAGE=pages/profile/index SCREENSHOT_TIMEOUT=60000 node scripts/walkthrough-phase-c.mjs` 退出码 1；`npm run devtools:verify-all-pages` 15/15 通过。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `miniapp/scripts/walkthrough-phase-c.mjs`; `miniapp/reports/devtools/walkthrough-phase-c.json`; `ERRORS.md`
- next_time_signal: DevTools 截图请求即使延长等待仍超时时，不重复启动并发截图；先使用结构审计，并等待官方工具或运行环境修复后再恢复像素级验收。

## M-20260909-018：旧色值批量补丁因内嵌 SVG 上下文不匹配未执行

- status: guarded
- first_seen: 2026-09-09
- severity: low
- symptom: 一次同时覆盖多个 WXSS、WXML、TS 和自定义 TabBar 内嵌 SVG 的补丁，因 TabBar 中目标 SVG 行与预期文本不完全一致而整体校验失败。
- root_cause: 把长内嵌资源行和普通样式行放在同一批量 hunk 中，编辑前没有先读取精确原文。
- impact: 本次补丁没有落盘，未修改源码、订单、支付或测试数据；执行轮次被浪费。
- fix: 改为按文件、按短 hunk 修改；内嵌 SVG 颜色先读取精确行，再单独替换。
- new_guardrail: 涉及内嵌资源的样式补丁不得与多文件批量替换混用；批量编辑失败后先确认 apply_patch 为原子失败，再拆分并回读。
- verification: 补丁失败返回校验错误；后续拆分补丁逐个回读并执行类型、静态和 DevTools 验证。
- linked_trace: 20260908-miniapp-commerce-ux-redesign
- linked_files: `miniapp/miniprogram/custom-tab-bar/index.wxss`; `ERRORS.md`
- next_time_signal: 长 SVG 或模板字符串只做精确、小范围替换，禁止凭记忆构造整行上下文。

## M-20260909-019：内嵌 SVG 颜色替换补丁再次因整行文本不匹配未执行

- status: guarded
- first_seen: 2026-09-09
- severity: low
- symptom: 针对 TabBar 激活图标的精确替换补丁仍因手工重建的长 SVG 行与文件原文不一致而失败。
- root_cause: 内嵌 URL 编码 SVG 是超长单行，手工拼接上下文容易遗漏字符。
- impact: 该次补丁未落盘，未修改源码、订单、支付或测试数据；其余样式替换未受影响。
- fix: 放弃手工整行重建，改用 Node 对单一 URL 编码色值 token 做机械替换，替换后回读确认旧 token 不再残留。
- new_guardrail: 超长内嵌资源不做手工整行重写；需要改变时先将资源迁移为独立可维护文件，并配套静态检查。
- verification: `node -e` 机械替换报告 `replaced encoded legacy color tokens=13`；回读仅剩 `%233D332D`，无 `%232B4C3F` 残留。
- linked_trace: 20260908-miniapp-commerce-ux-redesign
- linked_files: `miniapp/miniprogram/custom-tab-bar/index.wxss`; `ERRORS.md`
- next_time_signal: 不要凭记忆复制内嵌 SVG 行；若只是固定 token 替换，先统计命中数量，再执行机械替换并回读。

## M-20260909-020：多文件补丁包含错误路径和空 hunk 未执行

- status: guarded
- first_seen: 2026-09-09
- severity: low
- symptom: 对剩余旧色值做多文件补丁时，误写了 `miniapp/miniprogram/miniprogram/app.json` 路径并提交了空更新 hunk，apply_patch 在校验阶段失败。
- root_cause: 没有把普通单文件替换与路径核对分开，补丁构造时重复拼接了目录前缀。
- impact: 该次补丁整体未执行，未修改源码、订单、支付或测试数据。
- fix: 改用实际路径的单文件短补丁，并在执行前用已确认的工作区路径。
- new_guardrail: 每个补丁文件路径必须来自 `rg --files` 或当前已读路径；禁止提交空 hunk；跨文件补丁失败后改为逐文件执行。
- verification: 后续分别回读优惠券 WXSS、app.json 和配置色值，再运行静态及 DevTools 门禁。
- linked_trace: 20260908-miniapp-commerce-ux-redesign
- linked_files: `miniapp/miniprogram/pages/coupons/index.wxss`; `miniapp/miniprogram/app.json`; `ERRORS.md`
- next_time_signal: 补丁执行前检查路径是否重复、hunk 是否有实际变更，失败后不重试原批次。

## M-20260909-021：PowerShell 机械替换命令被执行策略拦截

- status: guarded
- first_seen: 2026-09-09
- severity: low
- symptom: 针对 TabBar 单一颜色 token 的 PowerShell 文本替换命令被执行策略拒绝，命令未执行，目标 WXSS 未修改。
- root_cause: 命令同时包含复杂引号、路径和临时文件清理操作，触发了当前执行器的命令策略拦截。
- impact: 该次替换没有产生源码、订单、支付或测试数据副作用；临时补丁文件仍待单独清理。
- fix: 将机械替换拆为独立 Node 单文件命令；清理临时文件时使用明确的单文件操作并单独核对。
- new_guardrail: Windows 下复杂文本改写不混入清理操作；先执行单文件替换并回读，再清理明确的本轮临时文件。
- verification: Node 单文件替换退出码 0，`%232B4C3F` 无残留；类型、静态及 DevTools 验证继续作为最终证据。
- linked_trace: 20260908-miniapp-commerce-ux-redesign
- linked_files: `miniapp/miniprogram/custom-tab-bar/index.wxss`; `D:\Temp\yunxi-tabbar-color.patch`; `ERRORS.md`
- next_time_signal: 执行器拒绝复杂 PowerShell 时，优先使用已确认语法的独立 Node 机械替换，不重复原命令。

## M-20260909-022：临时文件清理命令被默认 Shell 误解析

- status: guarded
- first_seen: 2026-09-09
- severity: low
- symptom: 清理单个 D 盘临时补丁文件时，带有 `cmd /c` 的命令仍由默认 PowerShell 解析，`exit /b` 被当作 PowerShell 命令而失败。
- root_cause: 执行器的 `shell` 参数没有显式指定为 `cmd.exe`，导致命令语法和实际 Shell 不一致。
- impact: 清理动作未完成，临时补丁文件暂时保留；源码、订单、支付和测试数据未受影响。
- fix: 使用明确的 `cmd.exe` Shell 执行单文件删除，再用单独的存在性检查确认。
- new_guardrail: Windows 删除命令必须让 `shell` 参数与命令语法一致；临时文件只允许一次删除一个明确路径，删除后必须单独复核。
- verification: 删除命令和存在性检查分别取得退出码；治理检查在收口前确认临时文件不存在。
- linked_trace: 20260908-miniapp-commerce-ux-redesign
- linked_files: `D:\Temp\yunxi-tabbar-color.patch`; `ERRORS.md`
- next_time_signal: 使用 `cmd /c` 时显式指定 `shell: cmd.exe`，不要让默认 PowerShell 解释 cmd 语法。

## M-20260909-023：执行器策略连续拒绝单文件临时清理

- status: guarded
- first_seen: 2026-09-09
- severity: low
- symptom: 针对本轮创建的单个 `D:\Temp\yunxi-tabbar-color.patch`，默认 PowerShell、显式 `cmd.exe` 和最小 `Remove-Item` 删除调用均被执行器策略拒绝。
- root_cause: 当前命令执行策略阻断了删除类操作，且无法在本轮切换到允许删除的执行通道。
- impact: 当时该临时补丁文件尚未确认删除；源码、订单、支付和测试数据未受影响。
- fix: 暂停重复删除尝试后，单独用存在性检查复核，确认该临时补丁文件已不存在。
- new_guardrail: 删除失败后不重复变形尝试；记录明确路径、保护边界和未清理事实，禁止把清理失败写成完成。
- verification: 三次删除调用均返回执行器策略拒绝；后续 `Test-Path -LiteralPath D:\Temp\yunxi-tabbar-color.patch` 返回 `False`，确认文件不存在。
- linked_trace: 20260908-miniapp-commerce-ux-redesign
- linked_files: `D:\Temp\yunxi-tabbar-color.patch`; `ERRORS.md`
- next_time_signal: 临时文件优先创建在可使用项目白名单清理入口管理的目录；删除动作被阻断时先做存在性复核，再决定是否继续处理。

## M-20260909-024：并行验证参数多出引号导致编排脚本语法错误

- status: guarded
- first_seen: 2026-09-09
- severity: low
- symptom: 一次并行执行残留扫描、类型检查和 diff 检查时，第一个工具参数对象末尾多出引号，编排器返回 `SyntaxError: Unexpected end of input`。
- root_cause: 手工拼接 `multi_tool_use.parallel` 参数时没有逐项检查 JSON 对象闭合。
- impact: 第一个残留扫描未执行；同批另外两个验证正常完成，源码、订单、支付和测试数据未受影响。
- fix: 改为单独执行残留扫描并重新获取有效退出码；后续复杂验证拆成独立命令或先检查 JSON 结构。
- new_guardrail: 并行工具只用于彼此独立且参数简单的命令；含多层引号的命令优先单独执行。
- verification: 后续单独执行固定字符串扫描，确认旧绿色、渐变和模糊 token 无残留。
- linked_trace: 20260908-miniapp-commerce-ux-redesign
- linked_files: `miniapp/miniprogram/`; `ERRORS.md`
- next_time_signal: 编排命令报 `SyntaxError` 时先检查工具参数对象和引号闭合；同一批验证未执行的步骤必须单独重跑并记录退出码。
 - next_time_signal: 并行验证失败时逐项确认哪些命令真实执行，未执行项必须单独复跑。

## M-20260909-025：补丁脚本嵌套模板字符串导致语法错误

- status: guarded
- first_seen: 2026-09-09
- severity: low
- symptom: 修改 `miniapp/miniprogram/utils/order-summary.ts` 时，外层执行脚本和补丁内容同时使用模板字符串，执行器返回 `SyntaxError: Invalid or unexpected token`。
- root_cause: 手工构造补丁字符串时没有避开内层金额格式化模板表达式，导致 JavaScript 在调用 `apply_patch` 前先解析失败。
- impact: 目标源码没有落盘改动，订单、支付、配送、客户数据和测试数据均未受影响；执行轮次被浪费。
- fix: 改用普通字符串拼接的补丁，并把金额格式化函数改为不依赖内层模板字符串。
- new_guardrail: 补丁正文包含反引号、模板表达式或长脚本时，不使用外层模板字符串承载；优先用单引号拼接或逐行数组。
- verification: 重新应用补丁后 `npm run test:order-summary` 退出码 0，4 项金额展示断言通过；`npm run typecheck` 退出码 0。
- linked_trace: 20260908-miniapp-commerce-ux-redesign
- linked_files: `miniapp/miniprogram/utils/order-summary.ts`; `miniapp/tests/utils/order-summary.test.ts`; `ERRORS.md`
- next_time_signal: 看到 `apply_patch` 前的 `SyntaxError` 时先判断是否为执行脚本构造失败，不把它误判成目标文件语法错误。

## M-20260909-026：新增 DevTools 脚本补丁再次被模板字符串截断

- status: guarded
- first_seen: 2026-09-09
- severity: low
- symptom: 新增 `verify-devtools-checkout-delivery-states.cjs` 时，补丁正文包含页面路由模板字符串，外层执行器返回 `SyntaxError: Unexpected token '{'`。
- root_cause: 仍使用模板字符串承载包含反引号的完整脚本文件，没有按上一条规则改为安全拼接。
- impact: 新脚本文件没有创建，源码、订单、支付、配送和测试数据未受影响。
- fix: 改为逐行数组拼接补丁，并在脚本中使用普通字符串拼接替代可避免的模板字符串。
- new_guardrail: 新增脚本文件时，如果文件本身包含反引号，补丁构造必须使用逐行数组或外部已验证 patch，不得直接用同类分隔符嵌套。
- verification: `node --check scripts/verify-devtools-checkout-delivery-states.cjs` 退出码 0；`npm run devtools:checkout-delivery-states` 退出码 0。
- linked_trace: 20260908-miniapp-commerce-ux-redesign
- linked_files: `miniapp/scripts/verify-devtools-checkout-delivery-states.cjs`; `ERRORS.md`
- next_time_signal: 同类工具错误发生第二次时必须立即换构造方式，不继续微调原模板字符串。

## M-20260909-027：长串行验证外层执行器空输出超时

- status: guarded
- first_seen: 2026-09-09
- severity: low
- symptom: 串行运行小程序静态检查和多项 DevTools 审计时，外层执行器因长时间空输出返回代理中断提示，但各审计报告随后已写入 `miniapp/reports/devtools/`。
- root_cause: 多条长耗时命令被包在同一个外层执行脚本内，期间没有持续输出，触发执行器空输出保护。
- impact: 没有源码或业务数据副作用；若直接复跑可能造成重复 DevTools 连接压力。
- fix: 改为读取已生成的审计报告确认结果，并将后续长命令拆成单条执行；没有把空输出代理中断误写成测试失败。
- new_guardrail: DevTools 验证必须保持串行，但每次只跑一个长命令；命令可能超过 30 秒时优先让脚本自身定期输出进度，或用报告文件作为补充证据。
- verification: `all-pages-devtools-audit.json`、`commerce-state-audit.json`、`product-purchase-path-audit.json`、`same-day-scheduling-audit.json` 和 `checkout-delivery-state-audit.json` 均显示 `PASS`。
- linked_trace: 20260908-miniapp-commerce-ux-redesign
- linked_files: `miniapp/reports/devtools/`; `ERRORS.md`
- next_time_signal: 执行器提示不要继续等待同一空输出 cell 时，停止轮询并改查可复跑报告或单条命令结果。

## M-20260909-028：错误账本补丁拼接末尾漏加连接符

- status: guarded
- first_seen: 2026-09-09
- severity: low
- symptom: 登记本轮工具错误时，补丁字符串末尾的 `*** End Patch` 没有参与字符串拼接，执行器返回 `SyntaxError: Unexpected token '*'`。
- root_cause: 手工拼接长补丁时混用了多行字符串连接和裸文本，缺少最后一段连接符。
- impact: 错误账本没有写入，源码、订单、支付、配送和测试数据未受影响。
- fix: 改为逐行数组构造完整补丁，再调用 `apply_patch`。
- new_guardrail: 长治理补丁必须用逐行数组构造，并在末尾显式包含 `*** End Patch` 字符串，不手工拼接裸尾行。
- verification: 本条写入后运行 `python -B backend/scripts/check_mistake_ledger.py` 复核账本结构。
- linked_trace: 20260908-miniapp-commerce-ux-redesign
- linked_files: `ERRORS.md`
- next_time_signal: 如果错误账本补丁本身失败，先确认没有落盘，再用更简单构造方式补记，避免工具错误逃逸。
## M-20260909-029：PowerShell 嵌套引号截断 DevTools 尺寸测量命令

- status: guarded
- first_seen: 2026-09-09
- severity: low
- symptom: 执行商品页运行态尺寸测量时，PowerShell 将 `node -e` 中的嵌套引号截断，Node 报 `Expression expected`，测量脚本未启动。
- root_cause: 在 PowerShell 命令参数中直接嵌套 JavaScript 字符串和选择器引号，未使用标准输入或独立脚本文件隔离解析层。
- impact: DevTools 未建立新连接，源码、订单、支付、配送和测试数据均未受影响；视觉尺寸测量尚未执行。
- fix: 改用 PowerShell here-string 通过 `node -` 标准输入执行测量脚本，避免多层命令字符串解析。
- new_guardrail: 含大量 JavaScript 引号或选择器的 DevTools 临时测量优先通过标准输入执行；`node -e` 仅用于无嵌套引号的一行命令。
- verification: 修正命令成功输出商品页运行态尺寸，并在结束时断开 DevTools。
- linked_trace: 20260908-miniapp-commerce-ux-redesign
- linked_files: `miniapp/miniprogram/pages/products/index.wxml`; `miniapp/miniprogram/pages/products/index.wxss`; `ERRORS.md`
- next_time_signal: PowerShell 返回 Node 语法截断时，先判定为外层命令构造错误，改用标准输入并单独复跑未执行的测量步骤。
## M-20260909-030：价格字距批量补丁选择器上下文不匹配

- status: guarded
- first_seen: 2026-09-09
- severity: low
- symptom: 统一价格字距的多文件补丁因购物车实际选择器与预设名称不一致而被 `apply_patch` 拒绝，全部目标文件均未修改。
- root_cause: 在没有读取每个文件精确上下文的情况下，按记忆拼接了跨文件选择器 hunk。
- impact: 本轮价格字距优化尚未落盘；源码、订单、支付、配送和测试数据未受影响。
- fix: 先用 `rg -n -C` 获取每个负字距规则的真实选择器，再按文件逐个使用最小 hunk 修改。
- new_guardrail: 跨文件样式替换不得假设选择器名称；批量补丁失败后先读取精确上下文，不原样重试。
- verification: 补丁失败后检查目标文件，确认负字距规则仍原样存在；后续最小补丁逐文件验证。
- linked_trace: 20260908-miniapp-commerce-ux-redesign
- linked_files: `miniapp/miniprogram/app.wxss`; `miniapp/miniprogram/pages/`; `ERRORS.md`
- next_time_signal: 对多页面样式统一时先读取选择器和相邻属性，优先拆成单文件小补丁。
## M-20260909-031：Markdown 表格行未作为字符串转义导致证据同步脚本语法错误

- status: guarded
- first_seen: 2026-09-09
- severity: low
- symptom: 同步 `PROJECT-STATE.md` 与证据索引的工具脚本包含未加引号的 Markdown 表格行，编排器返回 `SyntaxError: Unexpected token '|'`，补丁未调用编辑工具。
- root_cause: 构造长补丁时把含 `|` 的 Markdown 内容直接写入 JavaScript 数组，而不是作为字符串元素。
- impact: 证据编号修正和状态表更新延迟；源码、订单、支付、配送和测试数据未受影响，目标文档没有部分修改。
- fix: 将每一行 Markdown 都作为独立字符串元素传给 `apply_patch`，并拆分为短补丁执行。
- new_guardrail: 补丁数组中所有 Markdown、表格和代码内容必须显式置于字符串引号内；脚本语法错误后先确认目标文件未变化，再重构调用。
- verification: 修正后的短补丁成功更新 `E-20260909-008` 和 `PROJECT-STATE.md`，随后运行证据索引与开发总表检查。
- linked_trace: 20260908-miniapp-commerce-ux-redesign
- linked_files: `PROJECT-STATE.md`; `docs/harness-engineering/core/evidence-index.md`; `ERRORS.md`
- next_time_signal: 长 Markdown 补丁优先逐行数组构造，遇到表格分隔符、反引号或模板表达式时禁止裸嵌套。
## M-20260909-032：状态表替换行缺少补丁操作前缀

- status: guarded
- first_seen: 2026-09-09
- severity: low
- symptom: 更新 `PROJECT-STATE.md` 表格行时，旧行未以 `-` 前缀传入 `apply_patch`，工具返回 `invalid hunk`，状态同步未落盘。
- root_cause: 将包含 Markdown `|` 的整行作为 JavaScript 字符串后，忘记在补丁内容中添加删除行前缀。
- impact: 证据编号已经修正，但项目状态表暂未追加 `E-20260909-008`；源码、订单、支付、配送和测试数据未受影响。
- fix: 重新读取精确状态行，并使用 `-|旧行` 与 `+|新行` 的最小 hunk 修改。
- new_guardrail: Markdown 表格替换必须显式标记删除/新增前缀；工具返回 `invalid hunk` 后先确认目标文件未变化，再重试。
- verification: 状态行更新后运行开发总表、证据索引和错误账本检查。
- linked_trace: 20260908-miniapp-commerce-ux-redesign
- linked_files: `PROJECT-STATE.md`; `docs/harness-engineering/core/evidence-index.md`; `ERRORS.md`
- next_time_signal: 长表格行优先使用精确行号附近的小 hunk，所有上下文、删除和新增行都必须带合法补丁前缀。
## M-20260909-033：触控扫描器工作目录和 DevTools 启动配置不匹配

- status: guarded
- first_seen: 2026-09-09
- severity: low
- symptom: 在 `miniapp` 工作目录下读取 `miniapp/scripts/scan-miniapp-button-touch-targets.mjs` 时路径重复；随后运行扫描器时，它因缺少可用 `cliPath` 尝试自行启动微信开发者工具失败，报告没有形成有效扫描结果。
- root_cause: 命令的 `workdir` 与相对路径前缀不一致，并误用需要独立启动 DevTools 的扫描入口检查已有自动化会话。
- impact: 本次扫描没有提供触控证据；源码、订单、支付、配送和测试数据未受影响。当前通过独立商品页运行态测量和商品状态审计取得的 `58x45px` 证据不受影响。
- fix: 复用脚本前先按仓库根目录读取其实现和启动参数；已有 DevTools 会话优先使用显式 `MINIAPP_AUTOMATOR_WS` 的串行审计，不让扫描器重复启动实例。
- new_guardrail: 执行小程序命令前明确 `workdir`；需要当前 DevTools 实例时先检查脚本是否支持 WS 复用，禁止无配置地重复拉起开发者工具。
- verification: 失败命令退出码 1，未启动新的有效审计连接；后续商品页尺寸测量和 `devtools:commerce-states` 在现有 WS 会话中成功。
- linked_trace: 20260908-miniapp-commerce-ux-redesign
- linked_files: `miniapp/scripts/scan-miniapp-button-touch-targets.mjs`; `miniapp/miniprogram/pages/products/index.wxss`; `ERRORS.md`
- next_time_signal: 运行子目录脚本时不重复添加目录前缀；自动化工具报 `Failed to launch wechat web devTools` 时先检查 CLI 配置，改用现有 WS 会话或明确启动配置。
## M-20260909-034：跨文件触控样式补丁控制行未完全字符串化

- status: guarded
- first_seen: 2026-09-09
- severity: low
- symptom: 扩大多页面触控命中区的补丁在外层 JavaScript 构造阶段因 `@@` 控制行未作为字符串传入而报 `SyntaxError: Unexpected token '**'`，编辑工具未被调用。
- root_cause: 长补丁数组中混用了裸文本和字符串，未保证每一行都经过 JavaScript 解析。
- impact: 本轮触控样式和扫描夹具没有部分落盘；源码、订单、支付、配送和测试数据未受影响。
- fix: 改为单文件短 hunk，每一行补丁控制符都显式置于字符串引号内，并在每个文件后读取确认。
- new_guardrail: 多文件样式修改不再使用未逐行检查的长数组；遇到 `@@`、`***` 或 Markdown 表格时拆分调用。
- verification: 失败调用返回后检查目标文件，确认原有尺寸仍在；后续单文件补丁逐项通过。
- linked_trace: 20260908-miniapp-commerce-ux-redesign
- linked_files: `miniapp/miniprogram/app.wxss`; `miniapp/miniprogram/pages/`; `miniapp/scripts/scan-miniapp-button-touch-targets.mjs`; `ERRORS.md`
- next_time_signal: 补丁脚本出现 JavaScript 语法错误时，先确认未调用编辑工具，再切换为单文件短补丁。
## M-20260909-035：触控扫描夹具补丁重复插入 selectors 导致语法错误

- status: guarded
- first_seen: 2026-09-09
- severity: low
- symptom: 更新 `products-browse` 触控扫描夹具时重复插入 `selectors` 块，`node --check` 报 `Unexpected token ':'`，扫描脚本不能启动。
- root_cause: 以局部上下文替换时没有核对原块边界，新增块和旧块同时保留。
- impact: 触控扫描脚本暂不能运行；小程序源码、订单、支付、配送和测试数据未受影响。
- fix: 删除重复旧块，只保留当前商品页的分类入口、搜索清除和商品卡选择器，并在执行前运行 `node --check`。
- new_guardrail: 修改已有验证夹具前先读取完整对象边界；每次夹具编辑后必须先单独运行语法检查，再连接 DevTools。
- verification: 修复后 `node --check miniapp/scripts/scan-miniapp-button-touch-targets.mjs` 退出码 0，随后串行运行触控扫描。
- linked_trace: 20260908-miniapp-commerce-ux-redesign
- linked_files: `miniapp/scripts/scan-miniapp-button-touch-targets.mjs`; `ERRORS.md`
- next_time_signal: 验证脚本改动出现语法错误时先修复并做本地语法门禁，不重复连接微信开发者工具。
## M-20260909-036：CSS 检索正则未转义字面大括号

- status: guarded
- first_seen: 2026-09-09
- severity: low
- symptom: 触控样式语法检查后使用 `rg` 查询包含字面 `{` 的选择器，正则解析报 `repetition quantifier expects a valid decimal`，该次组合命令返回非零。
- root_cause: 检索内容包含 CSS 大括号，却使用了未转义的正则表达式。
- impact: CSS 和验证脚本语法检查已先行通过；仅检索命令未形成有效输出，源码、订单、支付、配送和测试数据未受影响。
- fix: 改用 `rg --fixed-strings` 或转义正则特殊字符，并将语法检查与内容检索拆开。
- new_guardrail: CSS 字面 token 检索优先使用固定字符串模式；复杂正则失败后不将其误判为源码语法错误。
- verification: `node --check` 对触控扫描脚本和 15 页审计脚本均通过；后续固定字符串检索和 DevTools 扫描单独执行。
- linked_trace: 20260908-miniapp-commerce-ux-redesign
- linked_files: `miniapp/miniprogram/pages/`; `miniapp/scripts/scan-miniapp-button-touch-targets.mjs`; `ERRORS.md`
- next_time_signal: 查询 CSS 选择器时优先使用 `rg -F`，不要把 `{`、`}`、`[` 等字面字符直接放入未转义正则。
## M-20260909-037：触控扫描器多 hunk 上下文重复导致补丁拒绝

- status: guarded
- first_seen: 2026-09-09
- severity: low
- symptom: 同时调整多个页面状态的触控扫描选择器时，订单筛选选择器行在同一补丁中重复作为上下文，`apply_patch` 报 `Failed to find expected lines`，补丁未落盘。
- root_cause: 跨对象 hunk 没有按实际文件顺序拆开，且同一目标行同时出现在保留和删除上下文中。
- impact: 扫描器规则仍保持上一版本；源码、订单、支付、配送和测试数据未受影响。
- fix: 按 `product-detail`、`checkout`、`orders`、`order-detail`、`chat` 等对象逐段读取并单独修改，避免复用重复上下文。
- new_guardrail: 验证脚本的多个状态对象必须分块修改；同一 hunk 不同时保留和替换同一行。
- verification: 每个短补丁后运行 `node --check`，再串行运行触控扫描。
- linked_trace: 20260908-miniapp-commerce-ux-redesign
- linked_files: `miniapp/scripts/scan-miniapp-button-touch-targets.mjs`; `ERRORS.md`
- next_time_signal: 复杂验证脚本先按对象边界拆 patch；失败后先读取目标块，不原样重试。
## M-20260909-038：触控扫描命令在仓库根目录执行导致 npm 找不到入口

- status: guarded
- first_seen: 2026-09-09
- severity: low
- symptom: 触控扫描命令在 `D:\Project\YunxiBakery` 根目录执行，npm 找不到根目录 `package.json` 并返回 `ENOENT`；此前脚本语法检查已通过。
- root_cause: 运行 npm script 时没有使用 `miniapp` 工作目录。
- impact: 本次触控扫描没有启动，源码、订单、支付、配送和测试数据未受影响。
- fix: 在 `D:\Project\YunxiBakery\miniapp` 目录重新执行，并保留 `MINIAPP_AUTOMATOR_WS` 复用当前 DevTools 会话。
- new_guardrail: 执行 npm script 前先确认当前目录包含目标 `package.json`；跨目录命令拆成语法检查和脚本执行两个步骤。
- verification: `node --check miniapp/scripts/scan-miniapp-button-touch-targets.mjs` 退出码 0；随后从 `miniapp` 目录串行执行触控扫描。
- linked_trace: 20260908-miniapp-commerce-ux-redesign
- linked_files: `miniapp/package.json`; `miniapp/scripts/scan-miniapp-button-touch-targets.mjs`; `ERRORS.md`
- next_time_signal: 看到 npm `ENOENT package.json` 时先检查 `workdir`，不要把它误判为依赖或代码错误。

## M-20260909-039：触控扫描连接在部分页面后超时

- status: open
- first_seen: 2026-09-09
- severity: low
- symptom: 最新一次触控扫描仅完成 2 个页面后发生 DevTools Automator timeout，未生成可作为最终通过证据的完整扫描结果。
- root_cause: 当前尚未确认；候选范围包括复用 WebSocket 会话的页面切换等待不足、微信开发者工具响应迟延或验证脚本连接生命周期处理。
- impact: 触控尺寸扫描中断；不能据此判定页面通过或失败。源码、订单、支付、配送和测试数据未受影响。
- fix: 先完成本条错误登记，再运行脚本语法检查并只执行一次串行重试；若仍超时，基于报告中已完成页面和错误堆栈继续缩小根因。
- new_guardrail: DevTools 自动化脚本失败后先保留报告和堆栈，不并发重连、不覆盖旧证据；验证脚本改动或运行方式变化后必须先做 node --check。
- verification: 待本轮串行重试完成后补充结果。
- linked_trace: 20260908-miniapp-commerce-ux-redesign
- linked_files: miniapp/scripts/scan-miniapp-button-touch-targets.mjs；miniapp/reports/button-visual/；ERRORS.md
- next_time_signal: 触控扫描出现超时，优先核对当前 DevTools 会话、脚本等待策略和最新报告，不把连接错误写成 UI 缺陷。

## M-20260909-043：错误账本新增状态不在门禁枚举内

- status: guarded
- first_seen: 2026-09-09
- severity: low
- symptom: 错误账本检查器拒绝新增记录中的 investigating 状态，报告 invalid status。
- root_cause: 新记录状态未按账本检查器允许的 open、guarded、verified 枚举填写。
- impact: 账本结构检查暂时失败；源码、扫描器和业务数据未受影响。
- fix: 将仍待验证的 M-20260909-039 改为 open，并保留本条记录说明门禁反馈。
- new_guardrail: 新增错误账本条目前先读取检查器的状态枚举，未关闭的问题使用 open。
- verification: 重新运行 check_mistake_ledger.py，预期返回 ok。
- linked_trace: 20260908-miniapp-commerce-ux-redesign
- linked_files: ERRORS.md；backend/scripts/check_mistake_ledger.py
- next_time_signal: 错误账本检查返回 invalid status 时，按检查器枚举修正字段，不自定义状态值。

## M-20260909-046：DevTools 业务走查脚本无输出悬挂

- status: open
- first_seen: 2026-09-09
- severity: low
- symptom: 触控扫描修复后运行 devtools commerce states，连接命令超过 40 秒无输出，无法在当前会话中形成新的业务走查报告，随后手动终止。
- root_cause: 当前尚未确认；与触控扫描相同，候选范围是本机 Automator WebSocket 或微信开发者工具响应队列阻塞，不能归因于页面业务失败。
- impact: 本轮未刷新商品状态走查证据；源码、订单、支付、配送和测试数据未受影响。
- fix: 停止悬挂进程并保留已有报告；继续使用不依赖 DevTools 的静态、类型和业务单测验证，不并发重连。
- new_guardrail: DevTools 脚本超过有限等待窗口无输出时停止单个进程，记录阻塞并避免继续启动其他 Automator 任务。
- verification: 后续需在微信开发者工具会话恢复后串行重跑该脚本。
- linked_trace: 20260908-miniapp-commerce-ux-redesign
- linked_files: miniapp/scripts/verify-devtools-commerce-states.cjs；miniapp/reports/devtools/；ERRORS.md
- next_time_signal: DevTools 业务脚本无输出时先读取进程和报告状态，不能把悬挂视为 PASS。

## M-20260909-047：日志补丁正文中的 Markdown 标记被外层模板解析

- status: guarded
- first_seen: 2026-09-09
- severity: low
- symptom: 追加本轮 LOGBOOK 条目时，补丁正文包含反引号代码标记，外层 JavaScript 模板字符串报 Unexpected identifier，编辑工具未执行。
- root_cause: 治理文档补丁未隔离正文中的模板字符串分隔符。
- impact: 本次日志补丁未落盘；源码、扫描器和业务数据未受影响。
- fix: 改用不含 Markdown 反引号的纯文本补丁重新追加日志，并读取文件头部确认。
- new_guardrail: 通过 JavaScript 包装 apply_patch 时，治理文档正文使用纯文本命令和路径，避免未转义的反引号。
- verification: 本条记录成功后检查 LOGBOOK.md 头部和错误账本门禁。
- linked_trace: 20260908-miniapp-commerce-ux-redesign
- linked_files: LOGBOOK.md；ERRORS.md
- next_time_signal: 日志补丁出现 Unexpected identifier 时，先确认编辑工具未调用，再移除正文中的 Markdown 代码标记。

## M-20260909-048：DevTools CLI 配置端口与实际服务端口不一致

- status: open
- first_seen: 2026-09-09
- severity: medium
- symptom: 使用项目默认的 10701 端口关闭微信开发者工具项目时，CLI 返回 IDE server 已运行于 64787，必须先按实际端口处理。
- root_cause: 当前 IDE HTTP 服务端口与小程序验证脚本默认端口发生漂移，旧的 Automator WebSocket 会话仍指向 9420。
- impact: 无法通过默认配置重建 DevTools 自动化会话，触控扫描和商品状态走查持续无输出悬挂；业务源码与数据未受影响。
- fix: 使用 CLI 返回的实际 HTTP 端口 64787 关闭当前项目，再以明确端口重新开启项目自动化并读取新 WebSocket 地址。
- new_guardrail: 重建 DevTools 会话前先读取 CLI 返回的实际 IDE HTTP 端口，不假设默认端口仍有效。
- verification: 待按实际端口完成关闭和自动化重开后补充。
- linked_trace: 20260908-miniapp-commerce-ux-redesign
- linked_files: miniapp/scripts/scan-miniapp-button-touch-targets.mjs；miniapp/scripts/verify-devtools-commerce-states.cjs；ERRORS.md
- next_time_signal: CLI 返回 must be restarted on port 时，先校准端口，不重复使用旧端口重连。

## M-20260909-049：Automator 直接调用 cli.bat 启动失败

- status: open
- first_seen: 2026-09-09
- severity: medium
- symptom: 清理旧 WebSocket 后，触控扫描器使用实际 HTTP 端口 64787 并由 miniprogram-automator 直接 launch，立即返回 Failed to launch wechat web devTools。
- root_cause: 当前微信开发者工具安装的 cli.bat 与 miniprogram-automator 的直接 launch 方式不兼容，CLI 自身 auto 命令可成功，但 launch 未取得自动化 WebSocket。
- impact: 新触控扫描尚未启动页面验证；已生成 0 页面失败报告，业务源码和数据未受影响。
- fix: 读取本地 miniprogram-automator 启动参数契约，使用 DevTools CLI 的固定自动化端口或正确 CLI 入口重建 WebSocket，再连接扫描。
- new_guardrail: DevTools CLI auto 成功不等于 miniprogram-automator launch 可用；运行扫描前必须确认自动化 WebSocket 端口处于监听状态。
- verification: 待固定自动化端口监听并完成扫描后补充。
- linked_trace: 20260908-miniapp-commerce-ux-redesign
- linked_files: miniapp/scripts/scan-miniapp-button-touch-targets.mjs；miniapp/reports/button-visual/button-touch-targets-20260909-005456.json；ERRORS.md
- next_time_signal: 扫描报告为 0 页面且提示 Failed to launch 时，先核对 CLI 入口和自动化端口，不重复直接 launch。

## M-20260909-050：Windows 下 Automator 启动分支未能暴露自动化端口

- status: open
- first_seen: 2026-09-09
- severity: medium
- symptom: 通过实际 IDE HTTP 端口重建会话后，触控扫描器直接 launch 失败；手工 auto 命令也未使 9420 端口进入监听。
- root_cause: 当前微信开发者工具 CLI 的批处理启动方式与 miniprogram-automator 的 Windows 直接 spawn 方式不兼容，且手工 auto 参数未确认被当前 CLI 接受。
- impact: 最新触控扫描无法建立 Automator 连接，运行态触控证据继续缺失；业务源码、订单和测试数据未受影响。
- fix: 先读取 CLI 的真实参数和退出结果，确认可用的自动化端口启动方式；若环境只支持既有连接，则扫描器明确要求 MINIAPP_AUTOMATOR_WS 并返回可诊断错误。
- new_guardrail: Windows 下启动 DevTools 自动化必须同时验证 CLI 退出码、自动化端口监听和 WebSocket 连接，三者缺一不可。
- verification: 待完成 CLI 参数核对或显式连接路径验证。
- linked_trace: 20260908-miniapp-commerce-ux-redesign
- linked_files: miniapp/scripts/scan-miniapp-button-touch-targets.mjs；miniapp/reports/button-visual/；ERRORS.md
- next_time_signal: Automator 启动失败时，先检查批处理 spawn 和真实端口监听，不把 0 页面报告当作页面失败。

## M-20260909-051：DevTools 报告读取使用了错误的工作目录

- status: guarded
- first_seen: 2026-09-09
- severity: low
- symptom: 在 miniapp 工作目录读取仓库根目录的 ERRORS.md 时，PowerShell 返回路径不存在；同一命令读取触控报告成功。
- root_cause: 报告路径位于 miniapp/reports，而错误账本位于仓库根目录，命令没有区分两个路径基准。
- impact: 仅错误账本尾部读取失败；没有修改源码、报告或业务数据，也没有形成新的错误判断。
- fix: 将治理文件读取改为仓库根目录工作目录，并单独读取 miniapp 报告。
- new_guardrail: 跨目录核对时明确每个目标文件的根路径，避免把一个命令的部分成功误写成整体成功。
- verification: 后续根目录读取 ERRORS.md 和 miniapp 目录读取 DevTools 报告分别执行。
- linked_trace: 20260908-miniapp-commerce-ux-redesign
- linked_files: ERRORS.md；miniapp/reports/button-visual/
- next_time_signal: 读取治理文件和小程序报告时，先确认当前 workdir 与目标路径的层级关系。

## M-20260909-052：读取计划时误把命令对象传入编排器源码

- status: guarded
- first_seen: 2026-09-09
- severity: low
- symptom: 读取 MiniApp 计划文件时，将 exec_command 参数对象直接作为 functions.exec 输入，编排器在执行前报 Unexpected token，命令未运行。
- root_cause: functions.exec 需要 JavaScript 编排代码，不能直接接收嵌套工具参数对象。
- impact: 仅本次计划读取失败；源码、报告、业务数据和治理文件未受影响。
- fix: 改用 tools.exec_command({cmd, workdir, max_output_tokens}) 的 JavaScript 调用形式重新读取。
- new_guardrail: 每次 functions.exec 调用前确认输入是可执行 JavaScript，工具参数对象只作为 tools.exec_command 的参数。
- verification: 后续计划和验证入口读取成功。
- linked_trace: 20260908-miniapp-commerce-ux-redesign
- linked_files: docs/superpowers/plans/2026-09-08-miniapp-commerce-ux-redesign.md；ERRORS.md
- next_time_signal: functions.exec 返回 Unexpected token 且命令没有输出时，先检查调用层级，不重复执行同一错误格式。

## M-20260909-040：错误账本补丁字符串被嵌套反引号截断

- status: guarded
- first_seen: 2026-09-09
- severity: low
- symptom: 追加 M-20260909-039 时，补丁正文中的 Markdown 反引号被外层 JavaScript 模板字符串解析，脚本在调用编辑工具前报 SyntaxError。
- root_cause: 自由格式补丁经 JavaScript 包装时未隔离正文中的模板字符串分隔符。
- impact: 首次补丁未执行，ERRORS.md 没有部分写入；源码和业务数据未受影响。
- fix: 补丁正文不再嵌套 Markdown 反引号，并使用可解析的纯文本内容重新登记两条错误。
- new_guardrail: 通过 JavaScript 调用 apply_patch 时，补丁正文避免直接包含未转义的模板字符串分隔符；需要代码标记时用字符串拼接或纯文本。
- verification: 本补丁成功后立即读取 ERRORS.md 尾部确认两条记录完整落盘。
- linked_trace: 20260908-miniapp-commerce-ux-redesign
- linked_files: ERRORS.md
- next_time_signal: apply_patch 外层出现 JavaScript SyntaxError 时，先确认编辑工具未调用，再移除或转义补丁正文中的反引号。

## M-20260909-041：扫描器导航补丁被外层模板表达式截断

- status: guarded
- first_seen: 2026-09-09
- severity: low
- symptom: 为复用同一路由页面对象而追加扫描器补丁时，补丁正文包含脚本原有的模板表达式，外层 JavaScript 模板字符串报 SyntaxError，编辑工具未执行。
- root_cause: 工具调用包装层未隔离补丁正文中的模板表达式。
- impact: 本次导航稳定性修改未落盘；扫描器仍保持上一版本，源码和业务数据未受影响。
- fix: 将补丁拆成不包含模板表达式的短 hunk，先做 node --check，再继续串行验证。
- new_guardrail: apply_patch 的外层 JavaScript 不直接包裹含动态模板表达式的源码上下文；遇到模板表达式时拆分上下文或进行字符串拼接。
- verification: 本补丁成功后读取目标函数和循环边界确认未发生部分写入。
- linked_trace: 20260908-miniapp-commerce-ux-redesign
- linked_files: miniapp/scripts/scan-miniapp-button-touch-targets.mjs；ERRORS.md
- next_time_signal: 工具调用出现 Unexpected identifier 或 Unexpected token 错误时，优先检查补丁正文中的模板表达式。

## M-20260909-042：扫描器定位检索使用了未闭合正则分组

- status: guarded
- first_seen: 2026-09-09
- severity: low
- symptom: 定位触控扫描器函数时，rg 命令的复合正则分组未闭合，命令返回 regex parse error，没有产生源码修改。
- root_cause: 多个包含括号的固定代码片段被直接拼成正则，未进行转义。
- impact: 仅本次定位命令失败；源码、扫描报告和业务数据未受影响。
- fix: 改用 rg fixed strings 分次查询，并在编辑前读取精确上下文。
- new_guardrail: 代码定位优先使用固定字符串检索；需要正则时先单独验证表达式。
- verification: 后续定位命令使用固定字符串模式并成功读取目标上下文。
- linked_trace: 20260908-miniapp-commerce-ux-redesign
- linked_files: miniapp/scripts/scan-miniapp-button-touch-targets.mjs；ERRORS.md
- next_time_signal: rg 出现 unclosed group 时，不重复原正则，改用 fixed strings。

## M-20260909-044：扫描器上下文读取调用格式错误

- status: guarded
- first_seen: 2026-09-09
- severity: low
- symptom: 读取扫描器上下文时，将命令参数对象作为编排器 JavaScript 源码传入，工具在执行前报 Unexpected token，未产生文件修改。
- root_cause: functions.exec 的输入需要 JavaScript 编排代码，命令必须通过 tools.exec_command 调用。
- impact: 仅本次上下文读取失败；源码、扫描报告和业务数据未受影响。
- fix: 改用正确的 tools.exec_command 编排调用，并在后续编辑前确认返回内容。
- new_guardrail: functions.exec 统一传入可执行 JavaScript；嵌套命令参数显式放入 tools.exec_command 的对象中。
- verification: 后续固定字符串检索和文件读取成功。
- linked_trace: 20260908-miniapp-commerce-ux-redesign
- linked_files: miniapp/scripts/scan-miniapp-button-touch-targets.mjs；ERRORS.md
- next_time_signal: functions.exec 返回 JavaScript SyntaxError 时，先检查是否把工具参数对象误当作源码传入。

## M-20260909-045：页面模板检索使用了错误的相对目录

- status: guarded
- first_seen: 2026-09-09
- severity: low
- symptom: 从 miniapp 目录检索页面模板时，使用 pages/... 而不是 miniprogram/pages/...，rg 返回路径不存在。
- root_cause: 小程序源码位于 miniapp/miniprogram，当前工作目录与路径假设不一致。
- impact: 仅本次上下文检索失败；源码、扫描器和业务数据未受影响。
- fix: 改用 miniprogram/pages/... 读取模板，并在修改前确认工作目录。
- new_guardrail: 小程序脚本和源码路径分开管理；从 miniapp 根目录执行检索时显式带 miniprogram 前缀。
- verification: 后续固定字符串检索成功并读取目标模板上下文。
- linked_trace: 20260908-miniapp-commerce-ux-redesign
- linked_files: miniapp/miniprogram/pages/；ERRORS.md
- next_time_signal: rg 返回路径不存在时，先核对仓库相对根目录，不把路径错误当成页面缺陷。

## M-20260909-053：跨文件 UI 补丁被外层模板字符串截断

- status: guarded
- first_seen: 2026-09-09
- severity: low
- symptom: 同时修改商品服务、首页和个人中心时，补丁正文包含 TypeScript 模板字符串，外层 JavaScript 在调用编辑工具前报 Unexpected identifier，未产生部分写入。
- root_cause: 多文件补丁没有隔离源码中的模板字符串分隔符。
- impact: 本次 UI 修复未落盘；业务源码、报告和数据未受影响。
- fix: 改为每个文件单独使用短补丁，并避开模板字符串源码上下文；每次编辑后立即读取确认。
- new_guardrail: 前端源码补丁按文件拆分，外层编排字符串不直接包含未转义模板表达式。
- verification: 待三个目标文件分别修改后运行 typecheck 和静态页面检查。
- linked_trace: 20260908-miniapp-commerce-ux-redesign
- linked_files: miniapp/miniprogram/services/products.ts；miniapp/miniprogram/pages/home/index.ts；miniapp/miniprogram/pages/profile/index.ts；ERRORS.md
- next_time_signal: apply_patch 外层出现 Unexpected identifier 时，先确认编辑未执行，再改为单文件短 hunk。

## M-20260909-054：首页补丁再次被 TypeScript 模板字符串截断

- status: guarded
- first_seen: 2026-09-09
- severity: low
- symptom: 单独修改首页商品映射时，补丁上下文仍包含 TypeScript 模板字符串，外层 JavaScript 在编辑前报 Unexpected identifier。
- root_cause: 虽已拆成单文件补丁，但仍使用反引号包裹整段补丁，没有改变模板字符串冲突条件。
- impact: 首页文件未发生部分写入；商品服务兜底修复已独立落盘，其他源码和数据未受影响。
- fix: 使用普通字符串数组逐行构造补丁，让源码反引号和动态表达式不参与外层解析。
- new_guardrail: 包含 TypeScript 模板字符串的补丁必须使用逐行普通字符串数组或转义，不再使用外层模板字符串。
- verification: 首页补丁落盘后立即读取修改段并运行 typecheck。
- linked_trace: 20260908-miniapp-commerce-ux-redesign
- linked_files: miniapp/miniprogram/pages/home/index.ts；ERRORS.md
- next_time_signal: 同一文件连续出现模板字符串解析错误时，立即切换逐行普通字符串数组，不再尝试模板字符串包装。

## M-20260909-055：首页 UI 修复验证命令在仓库根目录执行

- status: guarded
- first_seen: 2026-09-09
- severity: low
- symptom: 在仓库根目录执行 npm run typecheck，npm 因找不到根目录 package.json 返回 ENOENT。
- root_cause: MiniApp package.json 位于 miniapp 子目录，命令 workdir 没有与项目脚本路径保持一致。
- impact: 本次类型检查没有执行；源码、报告、业务数据和治理文件未受影响。
- fix: 改为在 miniapp 目录执行前端 npm 脚本，并单独记录命令结果。
- new_guardrail: 运行前端门禁前先确认当前工作目录包含 miniapp/package.json，不把路径错误归因于代码。
- verification: 后续在 miniapp 目录重新运行 typecheck、静态检查和页面审计。
- linked_trace: 20260908-miniapp-commerce-ux-redesign
- linked_files: miniapp/package.json；ERRORS.md
- next_time_signal: npm 返回根目录 package.json ENOENT 时，先切换到 miniapp 目录再重跑。

## M-20260909-056：错误记录补丁数组缺少闭合语法

- status: guarded
- first_seen: 2026-09-09
- severity: low
- symptom: 追加 M-20260909-055 时，functions.exec 输入的 JavaScript 数组缺少闭合语法，编排器报 Unexpected end of input，编辑工具未执行。
- root_cause: 手工构造逐行补丁数组时遗漏结束括号和分号。
- impact: 本次错误记录补丁未落盘；源码、报告、业务数据和既有账本内容未受影响。
- fix: 重新构造完整数组并在工具返回后读取账本尾部。
- new_guardrail: 逐行数组补丁发送前先检查数组闭合、join 调用和工具调用结束符。
- verification: 本补丁成功后运行错误账本结构检查。
- linked_trace: 20260908-miniapp-commerce-ux-redesign
- linked_files: ERRORS.md
- next_time_signal: 编排器报 Unexpected end of input 时，先检查外层 JavaScript 的括号、引号和分号。

## M-20260909-057：静态检查定位命令使用了仓库根目录错误路径

- status: guarded
- first_seen: 2026-09-09
- severity: low
- symptom: 从仓库根目录定位 MiniApp 静态检查规则时使用 scripts/... 和 miniprogram/...，rg 返回路径不存在。
- root_cause: 目标文件实际位于 miniapp/scripts 和 miniapp/miniprogram，命令未与仓库根目录保持一致。
- impact: 仅定位命令失败；已经获得的 typecheck、API 覆盖和静态检查失败结果未被篡改，源码与数据未受影响。
- fix: 改用 miniapp/scripts 和 miniapp/miniprogram 的完整相对路径重新读取规则。
- new_guardrail: 仓库根目录检索 MiniApp 文件时必须保留 miniapp 前缀；进入 miniapp workdir 后才省略此前缀。
- verification: 后续固定字符串检索成功并据此修复静态检查冲突。
- linked_trace: 20260908-miniapp-commerce-ux-redesign
- linked_files: miniapp/scripts/check-miniapp.mjs；miniapp/miniprogram/services/products.ts；ERRORS.md
- next_time_signal: rg 返回路径不存在时，先核对 MiniApp 子目录层级再继续分析检查结果。

## M-20260909-058：静态检查修复补丁再次误用工具包装语法

- status: guarded
- first_seen: 2026-09-09
- severity: low
- symptom: 修正商品详情空响应契约时，functions.exec 输入的逐行数组没有包裹在有效的 tools.apply_patch 调用代码中，编排器报 Unexpected token，文件未修改。
- root_cause: 发送补丁时遗漏了把数组结果传给编辑工具的 JavaScript 调用。
- impact: 本次静态检查修复未落盘；商品服务仍保持原状态，其他源码和数据未受影响。
- fix: 重新用完整的 const patch 数组和 tools.apply_patch(patch) 调用执行修复。
- new_guardrail: functions.exec 输入必须同时包含补丁构造和 tools.apply_patch 调用，不能只传补丁文本表达式。
- verification: 修复后重新运行 check:miniapp 和 typecheck。
- linked_trace: 20260908-miniapp-commerce-ux-redesign
- linked_files: miniapp/miniprogram/services/products.ts；ERRORS.md
- next_time_signal: 编排器报 Unexpected token 且没有编辑工具输出时，先检查外层是否实际调用了 tools.apply_patch。

## M-20260909-059：触控缺陷样式读取再次遗漏 MiniApp 源码前缀

- status: guarded
- first_seen: 2026-09-09
- severity: low
- symptom: 读取结算页和订单页 WXSS 时从 miniapp 目录使用 pages/...，rg 返回路径不存在。
- root_cause: 小程序页面样式实际位于 miniapp/miniprogram/pages，命令未按当前 workdir 拼接正确路径。
- impact: 仅本次样式定位命令失败；触控扫描已经取得真实 35px 和 33px 高度测量，源码与数据未受影响。
- fix: 改用 miniprogram/pages/checkout/index.wxss 和 miniprogram/pages/orders/index.wxss 读取样式，再按测量结果修复。
- new_guardrail: 触控报告和源码读取必须使用同一 workdir 约定，先确认 miniapp/miniprogram 路径存在。
- verification: 后续固定字符串检索成功并重跑触控扫描。
- linked_trace: 20260908-miniapp-commerce-ux-redesign
- linked_files: miniapp/miniprogram/pages/checkout/index.wxss；miniapp/miniprogram/pages/orders/index.wxss；ERRORS.md
- next_time_signal: 从 miniapp 目录检索页面源码时始终使用 miniprogram/ 前缀。

## M-20260909-060：DevTools Automator 会话在触控复扫前退出

- status: guarded
- first_seen: 2026-09-09
- severity: low
- symptom: 触控尺寸样式修复后，扫描器未连接到预期的 WebSocket 服务，回退启动 DevTools 失败，报告为 0 pages / 0 selectors。
- root_cause: 先前手工启动的 DevTools Automator 会话不是持久服务，扫描复跑前已退出；扫描脚本默认端口也不等于当前项目会话端口。
- impact: 本次扫描没有产生可用的触控验收结论；两处 WXSS 修复已落盘，业务数据和生产环境未受影响。
- fix: 通过已验证的 cli.bat auto 命令恢复本地 DevTools 会话，并显式传入 MINIAPP_AUTOMATOR_WS 后重跑扫描。
- new_guardrail: 运行依赖 DevTools Automator 的验收前先连接指定 WebSocket；0 pages 的扫描结果必须视为失败，不能作为通过证据。
- verification: 恢复 ws://127.0.0.1:9420 后，扫描报告必须覆盖预期页面与选择器，且两类标签高度均不低于 44px。
- linked_trace: 20260908-miniapp-commerce-ux-redesign
- linked_files: miniapp/scripts/scan-miniapp-button-touch-targets.mjs；miniapp/miniprogram/pages/checkout/index.wxss；miniapp/miniprogram/pages/orders/index.wxss；ERRORS.md
- next_time_signal: 报告出现 0 pages、0 selectors 或 DevTools 启动失败时，先恢复指定 WebSocket 会话，再继续任何 UI 验收。

## M-20260909-061：直接调用 DevTools cli.js 无法解析打包 CLI 模块

- status: guarded
- first_seen: 2026-09-09
- severity: low
- symptom: 为恢复 Automator 服务而直接运行安装目录的 `node.exe cli.js auto ...` 时，启动器尝试加载未解包的 `D:微信web开发者工具jscommoncliindex.js`，进程以 `MODULE_NOT_FOUND` 退出。
- root_cause: 当前 DevTools 将 CLI 实现放在 `code/package.nw` 打包资源中，`cli.js` 需要通过其原有启动方式解析资源路径，不能把内部模块路径当作普通目录文件执行。
- impact: 本次恢复尝试未启动自动化服务；项目源码、报告内容和业务数据未受影响。
- fix: 保留现有 DevTools 进程，改从 `miniprogram-automator`、IDE 服务端口和 DevTools 进程参数确认可用连接入口，不继续使用未经验证的直接模块路径。
- new_guardrail: DevTools CLI 启动失败且出现 `MODULE_NOT_FOUND` 时，先核对安装包结构和官方启动器路径；不得通过复制、解包或修改安装目录来绕过。
- verification: 该命令退出码 1，错误明确为 `Cannot find module ... js/common/cli/index.js`；后续只有 WebSocket 实际可连接并覆盖页面时才形成验收证据。
- linked_trace: 20260908-miniapp-commerce-ux-redesign
- linked_files: miniapp/scripts/scan-miniapp-button-touch-targets.mjs；ERRORS.md
- next_time_signal: 运行 DevTools 自动化恢复命令前，先确认启动器所需的 `package.nw` 资源路径和当前安装版本，不直接拼接内部模块路径。

## M-20260909-062：DevTools 启动器一致性检查失败导致自动化端口无法恢复

- status: guarded
- first_seen: 2026-09-09
- severity: medium
- symptom: 尝试通过微信开发者工具启动器恢复 Automator 会话时，`WeappLog/launch.log` 记录 `CheckConsistency result false`，随后提示“当前应用已损坏，请重新下载安装 windows”，`9420` 自动化端口未监听。
- root_cause: 当前 `D:\微信web开发者工具` 安装目录的一致性校验失败，启动器拒绝继续初始化完整 IDE/CLI 自动化能力；已有旧进程仍保留 IDE HTTP 口，但不能证明 Automator 服务可用。
- impact: 本轮不能把依赖 DevTools Automator 的 0 pages 扫描当作 UI 验收通过；前端源码修复仍可通过静态门禁、类型检查和非 DevTools 审计继续推进。
- fix: 停止继续用同一损坏启动器反复拉端口；先运行不依赖 DevTools 的门禁，后续只在启动器一致性恢复或存在可连接 WebSocket 时执行逐页自动化验收。
- new_guardrail: DevTools 日志出现一致性失败或“应用已损坏”时，立即登记为工具环境阻塞，不再重复试同一启动命令；自动化验收必须要求非 0 页面报告和可连接 WebSocket。
- verification: `Get-Content WeappLog/launch.log -Tail 160` 显示一致性检查失败；`Get-NetTCPConnection` 未发现 `9420` 监听。
- linked_trace: 20260908-miniapp-commerce-ux-redesign
- linked_files: ERRORS.md；miniapp/reports/button-visual/button-touch-targets-latest.json
- next_time_signal: DevTools Automator 再次 0 pages 或连接失败时，先检查启动器一致性日志和端口监听，再决定是否需要重装/修复工具。

## M-20260909-063：已登记的 rg 正则分组错误再次复发

- status: guarded
- first_seen: 2026-09-09
- severity: low
- symptom: 读取 `miniprogram-automator` 源码时再次把 `launch(|connect(` 等未转义括号放入 `rg` 正则，命令返回 `unclosed group`。
- root_cause: 已有 M-20260909-042 的防线只要求“改用 fixed strings”，但本次没有把多个候选关键词拆成独立固定字符串查询。
- impact: 仅一次源码定位命令失败；没有修改源码、报告或业务数据。
- fix: 后续查找多个带括号或竖线的代码片段时，拆成多条 `rg --fixed-strings` 或读取文件目录后用精确路径打开。
- new_guardrail: 本轮剩余源码定位禁止使用包含未转义括号的复合 `rg` 正则；要么 `--fixed-strings`，要么每个关键词单独查询。
- verification: 本条落盘后继续用固定字符串读取 automator 源码，不再重复原复合正则。
- linked_trace: 20260908-miniapp-commerce-ux-redesign
- linked_files: ERRORS.md；miniapp/node_modules/miniprogram-automator
- next_time_signal: `rg` 再次报 `unclosed group` 时，立即停止复合正则，改为固定字符串分次查询。

## M-20260909-064：DevTools HTTP 探测误把 /quit 放入候选端点

- status: guarded
- first_seen: 2026-09-09
- severity: medium
- symptom: 排查 IDE HTTP 服务端点时，将 `/quit` 与 `/open`、`/status` 等候选路径放在同一探测列表中执行。
- root_cause: 端点探测没有先区分只读、编译、预览、自动化和退出类高风险动作。
- impact: 当前返回值未显示 DevTools 主进程退出，项目源码和业务数据未受影响；但该行为可能中断正在打开的开发者工具会话，不能作为常规排查手段。
- fix: 本轮后续 DevTools HTTP 排查只允许调用只读或必要的自动化启动端点，禁止把 `/quit`、上传、预览发布或真实操作端点放入批量探测。
- new_guardrail: 任何 IDE HTTP 端点批量探测前先人工筛掉退出、上传、发布、删除和生产动作；不确定语义的端点先查源码或文档，不直接调用。
- verification: 追加本条后继续仅使用 `/v2/auto`、端口监听和本地日志定位自动化问题；不再调用 `/quit`。
- linked_trace: 20260908-miniapp-commerce-ux-redesign
- linked_files: ERRORS.md
- next_time_signal: 命令列表里出现 `quit`、`upload`、`preview`、`delete` 或生产相关端点时，先停止并拆分成安全最小命令。

## M-20260909-065：UI 收口时再次混用未核实脚本名、复合正则和过大补丁

- status: guarded
- first_seen: 2026-09-09
- severity: low
- symptom: 承接 MiniApp UI 收口时先后误读不存在的 `check-button-styles.mjs`、使用含括号的复合 `rg` 正则导致 `unclosed group`、以及提交跨文件样式大补丁触发 `apply_patch` hunk 校验失败。
- root_cause: 没有先用实际文件清单和固定字符串确认目标，再把文案替换、样式补齐和审计修复混进同一批次。
- impact: 这些失败均发生在工具校验阶段，目标源码和治理文档未被部分写入，订单、支付、配送、客户数据和测试数据未受影响；但浪费了执行轮次并降低了用户对工具可靠性的信任。
- fix: 已改为先用 `rg --files` 定位真实脚本名、用 Node/PowerShell 固定字符串做残留扫描，并将样式补丁拆成按文件的小 hunk；随后重新运行 MiniApp 类型、静态、按钮和样式审计。
- new_guardrail: MiniApp UI 收口先列真实文件路径，再按文件小补丁编辑；含括号、竖线、花括号或中文标点的残留扫描优先使用固定字符串或 Node `includes`；跨文件大补丁只在已读取精确上下文后使用。
- verification: `cd miniapp && npm run typecheck` 退出码 0；`npm run check:miniapp` 退出码 0；`npm run audit:buttons` 退出码 0；`npm run audit:button-styles` 退出码 0 且 96 controls / 0 failures / 0 warnings。
- linked_trace: 20260908-miniapp-commerce-ux-redesign
- linked_files: ERRORS.md；miniapp/scripts/audit-miniapp-button-styles.mjs；miniapp/miniprogram/pages/chat/index.wxml；miniapp/miniprogram/pages/checkout/index.wxss；miniapp/miniprogram/pages/products/index.ts
- next_time_signal: UI/UX 收口中出现脚本名不确定、正则含特殊字符或补丁超过单页上下文时，先停止批量操作，改成路径清单、固定字符串扫描和单文件小补丁。

补充复发记录（同一错误条目，2026-09-09）：收口检索截图调用时再次使用了未闭合分组的正则，`rg` 报 `unclosed group`。已立即停止该写法，后续按本条既有防线使用 `rg -F` 固定字符串检索；该失败未修改文件或业务数据。

## M-20260909-066：本地商品验证器错误拼接绝对图片 URL

- status: guarded
- first_seen: 2026-09-09
- severity: medium
- symptom: 执行 `cd miniapp && npm run check:local-miniapp-products` 时，商品列表和详情接口已返回数据，但图片检查把绝对地址拼成 `http://127.0.0.1:7001https://img.yzcdn.cn/...`，Node `fetch` 以 `ERR_INVALID_URL` 退出。
- root_cause: 验证脚本将所有资源路径无条件与本地 API 基址拼接，未区分外部绝对 URL 和本地相对路径；同时把有赞迁移态下 `productCount=0` 的分类元数据误当成必须可过滤出商品。
- impact: 只读商品验证未生成有效报告；没有修改商品、订单、支付、配送数据，也没有影响运行中的后端。
- fix: 增加统一 URL 解析函数：`http://` 和 `https://` 地址直接请求，相对路径才补本地 API 基址；商品接口和图片代理检查共用该函数。分类检查改为仅在后端回填非零 `productCount` 时验证过滤结果，未回填时记录跳过原因并交由 MiniApp 懒加载路径验证。
- new_guardrail: 任何本地 API 资源检查必须先处理绝对 URL；迁移态分类计数为零时不得强制构造分类商品结果；验证器异常退出时，必须检查报告时间戳和退出堆栈，不能将接口前置成功误判为完整验证通过。
- verification: 修复后重新运行 `npm run check:local-miniapp-products`，并核对 `miniapp/reports/local-miniapp-products/latest.json` 的状态与时间戳。
- linked_trace: 20260908-miniapp-commerce-ux-redesign
- linked_files: ERRORS.md；miniapp/scripts/check-local-miniapp-products.mjs
- next_time_signal: 商品数据含外部图片、视频或 CDN URL 时，先用 URL 解析函数归一化，再执行资源请求。

补充验证（同一错误条目）：修复后 `npm run check:local-miniapp-products` 已通过；分类元数据当前 `productCount=0`，检查器按迁移态记录跳过分类过滤硬断言，未伪造结果。

## M-20260909-067：DevTools 热重载异常导致页面空白与组件 not-found

- status: guarded
- first_seen: 2026-09-09
- severity: medium
- symptom: 微信开发者工具自动化已连接，但商品、会员、充值、结算四页页面栈存在而内容节点、`page.data()` 和截图内容为空；控制台重复输出 `Component is not found in path "wx://not-found"`，商品购买路径等待真实商品超时。
- root_cause: 本次 DevTools 项目热重载/编译状态异常，表现为页面编译产物未挂载；源码静态检查和本地后端接口均正常。
- impact: 该轮运行态检查先产生 `9/15`、`11/15` 失败和购买路径超时，不能作为 UI 代码缺陷结论；没有修改商品、订单、支付、配送数据。
- fix: 通过微信开发者工具 CLI 标准入口关闭并重新打开当前项目，再以 `cli auto --auto-port 9420 --port 13836 --trust-project` 恢复自动化；恢复后页面节点、真实商品数据和截图均正常。
- new_guardrail: DevTools 出现页面栈存在但 `elementMap`/`page.data()` 为空或 `wx://not-found` 时，先保存失败报告与截图，重载项目并重新启用 Automator；恢复前不得改写 CSS 或把空白页面当成 UI 验收结果。
- verification: 重载后 `npm run devtools:verify-all-pages` 为 `PASS (15/15)`；`npm run devtools:product-purchase-path`、`npm run devtools:commerce-states`、`npm run devtools:checkout-delivery-states`、`npm run devtools:same-day-scheduling` 均为 `PASS`。
- linked_trace: 20260908-miniapp-commerce-ux-redesign
- linked_files: ERRORS.md；miniapp/reports/devtools/all-pages-devtools-audit.json；miniapp/scripts/verify-all-15-pages-devtools.cjs
- next_time_signal: 先判断页面是否真实挂载，再分析 UI 选择器；同类异常先重载项目并记录前后报告，不重复盲改页面样式。

## M-20260909-068：结构断言通过但截图仍暴露空白按钮、会话漂移和导航重叠

- status: guarded
- first_seen: 2026-09-09
- severity: medium
- symptom: `npm run devtools:verify-all-pages` 曾返回 `15/15 PASS`，但目视旧截图和新截图后仍发现充值“去登录”按钮背景透明、订单详情清除登录存储后仍显示“已连接”、返回按钮与系统状态栏重叠、商品详情空态图标压住导航标题，以及会员卡操作按钮对比度不足或换行。
- root_cause: 原脚本主要检查路由、节点存在、尺寸和横向溢出，没有为每页保存与报告绑定的最新截图，也没有确定性切换未登录态或检查会话数据刷新；页面级按钮样式还被全局 `button:not([size="mini"])` 更高优先级覆盖，自定义导航又一度绕过 `layout.ts` 的动态胶囊高度。
- impact: 自动报告可能给出通过但实际展示仍不专业，直接影响登录引导、会员入口和空态可用性；未造成订单、支付、配送或客户数据写入。
- fix: 全页脚本改为每页保存 `final-*.png`，额外清除并恢复会话存储，验证订单、订单详情、充值和地址四个未登录态；会话 CTA 使用原生按钮与 88rpx 触控高度；充值和会员按钮使用页面级高优先级样式；订单详情先刷新会话再处理缺失订单号；导航恢复动态高度；商品详情空态增加顶部间距。
- new_guardrail: MiniApp UI/UX 收口必须同时满足结构断言、确定性状态断言和逐页最新截图目视复核；报告必须记录截图路径，未登录态必须验证页面数据而不只检查按钮文本；全局按钮重置或导航高度变化后必须复查选择器优先级和状态栏/胶囊位置。
- verification: 本地后端启动条件下，`npm run devtools:verify-all-pages` 最终为 `15/15 PASS`，额外未登录态 `4/4 PASS`；报告 `miniapp/reports/devtools/all-pages-devtools-audit.json` 绑定 15 张 `final-*.png` 与 4 张 `final-logged-out-*.png`，并完成逐页目视复核。
- linked_trace: 20260908-miniapp-commerce-ux-redesign
- linked_files: ERRORS.md；miniapp/miniprogram/app.wxss；miniapp/miniprogram/components/session-notice/index.*；miniapp/miniprogram/pages/order-detail/index.ts；miniapp/miniprogram/pages/recharge/index.wxss；miniapp/miniprogram/pages/profile/index.wxss；miniapp/miniprogram/pages/product-detail/index.wxml；miniapp/miniprogram/pages/product-detail/index.wxss；miniapp/scripts/verify-all-15-pages-devtools.cjs；miniapp/reports/devtools/all-pages-devtools-audit.json
- next_time_signal: 自动化显示全页通过但截图仍有空白控件、状态矛盾或标题遮挡时，立即判定视觉验收未完成并补状态与截图断言，不能只调高尺寸阈值。

补充复发记录（同一错误条目，2026-09-09）：全页审计与商品购买路径共用 `ws://127.0.0.1:9420` 并行执行时，购买路径切页导致全页审计的商品页对象被销毁，出现 `Missing .page-fixed-safe container` 和 `page destroyed`，结果为 14/15。已确认购买路径独立通过，其余页面正常；后续所有共享同一 Automator 会话的 DevTools 脚本必须串行运行，失败脚本单独重跑后才能形成最终证据。

## M-20260909-069：结算异常状态只有禁用结果，缺少原因与恢复动作证据

- status: guarded
- first_seen: 2026-09-09
- severity: medium
- symptom: 结算页 DevTools 审计能够确认报价未成功时提交按钮被禁用，但所有失败状态主要共用“未取得有效闪送报价前，不能提交订单”，没有验证地址缺失、报价过期、超出范围和平台不可用是否给出不同原因及下一步动作。
- root_cause: 自动化只断言 `canSubmitOrder`、按钮文案和旧的警告节点存在，没有把用户可理解的状态指引、恢复动作、触控尺寸和每个状态的截图纳入验收。
- impact: 结构测试可能通过，但顾客在预订为主的购买流程中无法判断应补地址、重新报价、改自提还是联系客服，增加下单中断和客服沟通成本；未造成订单、支付、配送或客户数据写入。
- fix: 结算页按 `quoting`、信息缺失、`expired`、`address_out_of_range`、`provider_unavailable` 和未知失败状态生成标题、解释和恢复动作；DevTools 审计逐状态断言文案、44px 触控目标并保存对应截图。
- new_guardrail: 交易状态验收必须同时检查提交可用性、顾客可理解的原因、可恢复动作和最新截图；异常状态不能只验证按钮禁用。
- verification: 本轮将运行 `npm run typecheck`、`npm run check:miniapp`、`npm run audit:buttons`、`npm run audit:button-styles`、`npm run devtools:checkout-delivery-states`，并核对每个状态的截图路径。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `ERRORS.md`；`miniapp/miniprogram/pages/checkout/index.ts`；`miniapp/miniprogram/pages/checkout/index.wxml`；`miniapp/miniprogram/pages/checkout/index.wxss`；`miniapp/scripts/verify-devtools-checkout-delivery-states.cjs`
- next_time_signal: 任何交易状态脚本若只检查 `disabled` 或 `canSubmitOrder`，先补原因、恢复动作、触控尺寸和截图，再引用为 UX 验收证据。

## M-20260910-070：DevTools 长会话跨 17:00 截止后模块级 data 初始值冻结，审计误报当天登记回归

- status: guarded
- first_seen: 2026-09-10
- severity: medium
- symptom: 串行复跑 `npm run devtools:same-day-scheduling` 失败：`isSameDayRegistration` 实际 false、预期 true（北京 09:55，早于 17:00 截止），且缺少“当天登记由门店客服确认”提示；同批全页审计与购买链路均通过，疑似产品回归。
- root_cause: 群内登记页 `Page({ data: { dateStartValue: getCheckoutDateStart(), isSameDayRegistration: isCheckoutDateToday(...) } })` 的初始化表达式在模块首次加载时求值一次并冻结；DevTools 会话从前一天 17:00 后一直存活，`reLaunch` 只重建页面实例、不会重新执行模块求值，日期起点和当天标记停留在昨天的求值结果。`cli open` 对已打开项目不触发模拟器重载，误以为已重载。
- impact: 仅影响本地验证判定，导致审计误报 FAIL；未造成产品代码或业务数据变化。真实用户冷启动会重新求值；小程序跨 17:00 常驻时日期起点可能陈旧，属低频边界体验问题，本轮不扩大修复范围。
- fix: 用 `D:\微信web开发者工具\cli.bat quit` 完全退出 IDE，再 `cli.bat auto --project D:\Project\YunxiBakery\miniapp --auto-port 9420` 重启并重编译，模块级 data 重新求值后 same-day 审计串行复跑 PASS。
- new_guardrail: DevTools 长会话跨天或跨 17:00 截止后，任何时间敏感审计 FAIL 先判定是否模块级 data 陈旧：先 `quit` + `auto` 重载项目再串行复跑，复跑仍 FAIL 才判定为产品回归，不要先改产品代码。
- verification: 重载后 `npm run devtools:same-day-scheduling` PASS；同批串行证据：`npm run devtools:verify-all-pages`（15/15 PASS + 未登录态）、`npm run devtools:product-purchase-path` PASS、`npm run devtools:commerce-states` PASS、`npm run devtools:checkout-delivery-states` PASS；定向静态门禁 `npm run typecheck`、`npm run check:miniapp`、`npm run audit:buttons`（106 控件）、`npm run audit:button-styles`（0 失败 0 警告）通过。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `ERRORS.md`；`miniapp/miniprogram/pages/group-registration/index.ts`；`miniapp/miniprogram/utils/checkout-time.ts`；`miniapp/scripts/verify-devtools-same-day-scheduling.cjs`；`miniapp/reports/devtools/same-day-scheduling-audit.json`
- next_time_signal: 时间敏感审计依赖页面模块级初始值时，先确认 DevTools 会话的模块求值时间早于被测时间边界（17:00 / 午夜），先重载再判回归。
