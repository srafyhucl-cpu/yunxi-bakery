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

补充复发记录（同一错误条目，2026-09-12）：改写 D 盘临时探针脚本时，把“删除同一路径 + 新增同一路径”放进同一批补丁，`apply_patch` 连续以 `multiple operations target ...` 拒绝；重复提交同一形态的调用只会重复失败，不会部分写入。已停止该写法，改为直接扩展现有结算页审计脚本增加布局断言，并用 Node/PowerShell 固定字符串核验目标。后续遇到同类拒绝，立即改用单文件替换或复用既有脚本承载断言。

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

补充复发记录（同一错误条目，2026-09-12）：首页修复后再次出现“自动化通过但截图不合格”——`npm run devtools:verify-all-pages` 为 15/15 PASS，但 `final-home.png` 显示“今日鲜制”“今日推荐”“按需预订，新鲜制作”三层货架文案挤在同一行。原因是 `shelf-head__eyebrow/title/subtitle` 使用行内 `text` 且未声明 `display: block`，父容器也未约束副本宽度。已改为块级堆叠并新增货架标题层级与“查看更多”入口重叠断言，复跑后标题层级为 98px / 113.3px / 135.5px 且仍为 15/15 PASS。

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

## M-20260912-071：依赖原生默认样式的移动端表单在窄屏出现异常高度、换行与字段失去标签

- status: guarded
- first_seen: 2026-09-12
- severity: medium
- symptom: 逐页目视复核发现：结算页与群内登记页备注 `textarea` 实际高度约 150px，远超设计的 180rpx；两个页面三列时间栅格把“日期：2026-09-12”挤成两行；结算页协议文案在 flex 换行后出现“我已阅读并同意 …… 和 / 《用户协议》 《隐私政策》”的错位排版；群内登记页数量输入预填 “1” 后 placeholder “数量” 不再显示，字段含义丢失。
- root_cause: 页面只声明 `min-height` 而未覆盖微信 `textarea` 的默认高度；时间栅格用三等分 `flex: 1` 承载较长的日期文本；协议行把整句拆成多个 flex item 且链接触控高度参与换行；数量输入依赖 placeholder 充当标签，预填值后必然失去说明。这些问题均不触发结构断言，只能靠真实尺寸测量与截图发现。
- impact: 顾客在预订结算和群内登记时看到异常空白的备注框、断行日期和含义不明的“1”输入框，降低表单可信度并增加填错与来回沟通成本；未造成订单、支付、配送或客户数据写入。
- fix: 备注 `textarea` 显式声明 `height: 180rpx`；日期选择器新增 `time-grid__date` 类并独占整行（`flex: 1 0 100%`，同时用 `.time-grid picker.time-grid__date` 提高优先级避免被 `.time-grid picker` 覆盖），小时与分钟并排一行；协议区改为“说明行 + 链接行”两段结构，链接保持 44px 触控目标；数量输入改为带常驻“数量”标签的行内字段。
- new_guardrail: 表单类页面必须同时满足结构断言、布局尺寸断言和逐页截图目视复核。备注框高度、日期选择器是否独占整行与是否换行、协议行高度、协议链接触控尺寸已写入 `verify-devtools-checkout-delivery-states.cjs` 断言；数值输入不得只靠 placeholder 说明含义。
- verification: `npm run devtools:checkout-delivery-states` PASS（备注框 93px、日期选择器 341/341 独占整行、协议行 80px、协议链接 72x45）；`npm run devtools:verify-all-pages` 15/15 PASS 并附 4 个未登录态；`npm run typecheck`、`npm run check:miniapp`、`npm run audit:buttons`（106 控件）、`npm run audit:button-styles`（0 失败 0 警告）通过；逐页截图目视复核通过。
- linked_trace: 20260908-miniapp-commerce-ux-redesign
- linked_files: ERRORS.md；miniapp/miniprogram/pages/checkout/index.wxml；miniapp/miniprogram/pages/checkout/index.wxss；miniapp/miniprogram/pages/group-registration/index.wxml；miniapp/miniprogram/pages/group-registration/index.wxss；miniapp/miniprogram/pages/address/index.wxss；miniapp/scripts/verify-devtools-checkout-delivery-states.cjs；miniapp/scripts/verify-all-15-pages-devtools.cjs
- next_time_signal: 页面一旦使用原生 `textarea`、三等分时间栅格或 placeholder 充当标签，必须先量取真实尺寸并查看截图，不能以结构断言通过作为验收结论。

## M-20260912-072：Monorepo 迁移后 secrets 守卫仍读 backend 旧镜像，受控记录需双写

- status: guarded
- first_seen: 2026-09-12
- severity: medium
- symptom: 提交 MiniApp 视觉收口时 `detect-secrets-hook` 阻断，命中 `docs/harness-engineering/core/evidence-index.md` 的 3 条历史误报（企微消息 ID 与 `check-secret-hygiene` 脚本名）；按受控流程把 3 条并入 `backend/.secrets.baseline` 并在根目录 `docs/harness-engineering/core/secrets-baseline-changes.md` 登记后，`verify_secrets_baseline.py` 仍报“未找到与本次 HEAD→index 哈希对匹配的受控记录”。
- root_cause: `backend/scripts/verify_secrets_baseline.py` 的 `ROOT_DIR` 为 `backend/`，而 `_git_show` 又把 `:0:/docs/...` 改写成 `:0:./docs/...`（相对 cwd），于是受控记录实际读取 `backend/docs/harness-engineering/core/secrets-baseline-changes.md` 这份迁移前旧镜像；同一守卫的 staged 校验用 `:/` 前缀却读仓库根同名文件，一份守卫同时读两份文件。
- impact: 守卫不会放行真实密钥（仍会阻断），但合法的误报白名单流程在根文档登记后仍被误判，并要求同一记录双写；本次通过两份记录同步解除阻断，未绕过硬编码密钥门禁，未修改业务代码或数据。
- fix: 受控更新 `backend/.secrets.baseline`，为 `docs\harness-engineering\core\evidence-index.md` 增加 3 条 allowlist（登记 old/new 哈希、命令、版本、trace_id、approved_by），并将同一记录同步到 `backend/docs/...` 旧镜像，使 `verify_secrets_baseline.py` 通过。
- new_guardrail: `.secrets.baseline` 受控更新后必须同时跑 `python -B backend/scripts/verify_secrets_baseline.py` 与 `detect-secrets-hook --baseline backend/.secrets.baseline <changed file>` 复核；守卫路径统一前，受控记录需在 `docs/` 与 `backend/docs/` 两份登记，且禁止用 `--no-verify` 绕过。
- verification: `python -B backend/scripts/verify_secrets_baseline.py` 输出 `[secrets-baseline] OK：.secrets.baseline 状态一致且符合受控流程`、退出码 0；`detect-secrets-hook --baseline backend/.secrets.baseline docs/harness-engineering/core/evidence-index.md` 退出码 0；两份记录文件均为 33 行且 `Compare-Object` 无差异。
- linked_trace: 20260908-miniapp-commerce-ux-redesign
- linked_files: ERRORS.md；backend/.secrets.baseline；docs/harness-engineering/core/secrets-baseline-changes.md；backend/docs/harness-engineering/core/secrets-baseline-changes.md；backend/scripts/verify_secrets_baseline.py；docs/harness-engineering/core/evidence-index.md
- next_time_signal: 若再次出现“根文档已登记但守卫仍报未匹配”，先检查是否遗漏 `backend/docs/.../secrets-baseline-changes.md`；中期应让守卫只读仓库根 canonical 文档、旧镜像改为指针，不得用跳过钩子代替修复。

## M-20260912-073：首页图片缺少加载失败降级，同类能力没有横向对齐

- status: guarded
- first_seen: 2026-09-12
- severity: medium
- symptom: 购物车、商品列表、商品详情早在历史整改中已有 `imageFailed` + `binderror` + `.yunxi-image-fallback`，但首页商品卡与品牌轮播只判断“图片地址是否为空”，`<image>` 没有 `binderror`；本地默认品牌轮播的占位元素还保留 `image-placeholder skeleton-shimmer` 两个已无任何 WXSS 定义的类名。
- root_cause: 图片降级按页面各自实现，没有全局静态门禁；历史清理删除 `.skeleton-shimmer` 样式时只回收了 CSS，未回收仍引用它的骨架元素。
- impact: 首页是“商品优先”重构后的首屏，一旦有赞迁移 CDN 图失效或弱网加载失败，首页会出现破图/空白且没有任何占位反馈，直接影响下单信任；默认空图轮播依赖父容器底色，缺少可独立成立的降级样式。
- fix: 首页补齐 `imageFailed` 状态与 `onHomeProductImageError` / `onHeroImageError` 回调，WXML 改为“图片存在且未失败”才渲染 `<image>`，并补 `binderror` 与占位分支；`.home-hero__fallback` 增加品牌底色，删除失效类名。
- new_guardrail: `miniapp/scripts/check-miniapp.mjs` 新增 `checkImageErrorFallback`：逐页扫描 `<image>`，缺少 `binderror` 即以“页面:行号”失败；`verify-all-15-pages-devtools.cjs` 首页新增降级探针（临时置不可达图片地址，断言 `imageFailed`、占位渲染与货架高度稳定）。
- verification: 变异验证——临时移除 `pages/cart/index.wxml` 的图片 `binderror` 后 `npm run check:miniapp` 退出码 1 并精确报出 `pages/cart/index.wxml:17`，恢复后退出码 0；`npm run devtools:verify-all-pages` 15/15 PASS，首页探针记录商品图占位 0→1、货架高度 929px→929px、轮播占位 128px。
- linked_trace: 20260908-miniapp-commerce-ux-redesign
- linked_files: ERRORS.md；miniapp/miniprogram/pages/home/index.ts；miniapp/miniprogram/pages/home/index.wxml；miniapp/miniprogram/pages/home/index.wxss；miniapp/scripts/check-miniapp.mjs；miniapp/scripts/verify-all-15-pages-devtools.cjs
- next_time_signal: 新增任何 `<image>` 前先确认 `check:miniapp` 的 binderror 门禁；DevTools 沙箱不会为不可达域名触发真实 `binderror`，运行态断言必须保留“直接调用回调”兜底并在结论中写明触发方式，不得把直接调用写成真实事件。

## M-20260912-074：版本表头契约与 backend 旧镜像漂移，sync_version 测试长期失败

- status: guarded
- first_seen: 2026-09-12
- severity: medium
- symptom: `python -m pytest backend/tests/scripts/test_sync_version.py -q --no-cov` 在本轮开始时的干净工作区即失败：断言 `当前本地代码版本为 \`0.133.0-p2trial.3\`` 未出现在 `backend/项目进度与配置清单.md` 前 5 行；根目录同名文件同样只剩下“当前本地代码版本以 `backend/VERSION` 为准”的宽松表述。
- root_cause: 进度清单表头被改成指向版本文件的宽松描述，但测试契约仍要求字面版本号；Monorepo 迁移后 `backend/项目进度与配置清单.md` 成为停在 2026-09-09 的旧镜像，后续每轮只更新根副本，两份副本的漂移没有被任何门禁发现。
- impact: 版本一致性测试长期为红，任何全量回归都会被这一项拖红，真实回归信号被噪声掩盖；旧镜像还停留在 2026-09-09，无法作为项目进度权威源。
- fix: 根目录与 `backend/` 两份 `项目进度与配置清单.md` 表头恢复为包含字面版本号的“当前本地代码版本为 \`0.133.0-p2trial.3\`”。
- new_guardrail: 每轮收口先跑 `python -m pytest backend/tests/scripts/test_sync_version.py -q --no-cov`；改动 VERSION 或进度表头时两份副本必须同步，否则视为未收口。
- verification: 修复前 `python -m pytest backend/tests/scripts/test_sync_version.py -q --no-cov` 退出码 1（`test_repository_progress_header_matches_version_file` 断言失败）；修复后同一命令 4 项全过、退出码 0。
- linked_trace: 20260908-miniapp-commerce-ux-redesign
- linked_files: ERRORS.md；项目进度与配置清单.md；backend/项目进度与配置清单.md；backend/tests/scripts/test_sync_version.py
- next_time_signal: 若全量回归出现 `test_repository_progress_header_matches_version_file` 失败，先看两份进度清单第 3 行是否被改回宽松描述；中期应把 `backend/项目进度与配置清单.md` 收敛为指向根 canonical 文件的指针，而不是继续双写。

## M-20260912-075：表单字段只靠 placeholder 说明含义，常驻标签修复未横向覆盖

- status: guarded
- first_seen: 2026-09-12
- severity: medium
- symptom: 群内登记数量字段在 M-20260912-071 中改为常驻标签后，结算页和地址页的联系人、手机号、地址、备注，以及群内登记其余字段仍只靠 placeholder 表达含义；用户一旦输入内容，字段说明即消失，完成核对时只能靠字段顺序猜测。
- root_cause: 上一轮只修复了截图中暴露的数量输入，没有按表单控件类型横向盘点；静态门禁也只覆盖图片降级，没有把“输入控件必须有常驻标签”纳入检查。
- impact: 顾客填写姓名、手机号、闪送地址和生日牌/忌口备注时更容易把内容填错位置，增加客服核对与来回沟通成本；未造成订单、支付、配送或客户数据写入。
- fix: 全局新增 `.form-field` / `.form-field__label`，结算、地址和群内登记三个页面的全部输入控件统一改为常驻标签加控件；数量字段保留行内标签；输入控件最小高度统一为 88rpx，运行时保持 45px 或 93px 触控高度。
- new_guardrail: `check-miniapp.mjs` 新增 `checkFormFieldLabels`，对结算、地址、群内登记逐页比较 input/textarea 数量与常驻标签数量；`verify-all-15-pages-devtools.cjs` 新增运行态检查，校验标签非空、与控件不重叠、控件高度不低于 44px，并自动处理空购物车与地址空态样本。
- verification: 变异验证——临时移除地址页“联系人”标签后 `npm run check:miniapp` 退出码 1，精确报 `pages/address/index.wxml 有 3 个输入控件但只有 2 个常驻字段标签`，恢复后退出码 0；`npm run devtools:verify-all-pages` 最终 15/15 PASS，地址页控件为 333x45、333x45、333x93px，结算页为 341x45、341x45、341x45、341x93px，群内登记为 333x45、333x45、333x45、273x45、333x93px，标签均无重叠。
- linked_trace: 20260908-miniapp-commerce-ux-redesign
- linked_files: ERRORS.md；miniapp/miniprogram/app.wxss；miniapp/miniprogram/pages/checkout/index.wxml；miniapp/miniprogram/pages/checkout/index.wxss；miniapp/miniprogram/pages/address/index.wxml；miniapp/miniprogram/pages/address/index.wxss；miniapp/miniprogram/pages/group-registration/index.wxml；miniapp/miniprogram/pages/group-registration/index.wxss；miniapp/scripts/check-miniapp.mjs；miniapp/scripts/verify-all-15-pages-devtools.cjs
- next_time_signal: 表单页面新增 input/textarea 时，必须同时补常驻标签并跑静态与 DevTools 断言；placeholder 只能作为输入示例，不能作为字段名称。

## M-20260912-076：DevTools 布尔属性断言把空字符串误判为未禁用

- status: guarded
- first_seen: 2026-09-12
- severity: low
- symptom: 结算页零余额/零积分状态审计确认页面数据已为 `false`、WXML 也已渲染 `disabled`，但首次运行仍报“积分/余额抵扣开关未禁用”；报告记录 `pointsDisabled` 与 `balanceDisabled` 均为空字符串。
- root_cause: `miniprogram-automator` 对存在的布尔属性返回空字符串表示真值，而不是返回 `"true"`；测试脚本错误要求布尔属性必须等于 `true` 或 `"true"`。
- impact: 真实正确的界面会被审计误报为失败，若直接相信首轮结果会制造无效修复和重复试错。
- fix: 运行态断言改为“属性不存在（`null`）才视为未禁用”；同时保留页面数据、开关状态和零资产说明文案三重校验。
- new_guardrail: DevTools 布尔属性只按存在性判断，不按字符串值比较；首次出现属性断言失败时必须先记录 `attribute()` 原始值再修改页面。
- verification: 修正断言后 `npm run devtools:commerce-states` PASS；报告记录 `pointsEnabled=false`、`balanceEnabled=false`、`pointsDisabled=""`、`balanceDisabled=""`，并保留零资产截图。
- linked_trace: 20260908-miniapp-commerce-ux-redesign
- linked_files: ERRORS.md；miniapp/scripts/verify-devtools-commerce-states.cjs；miniapp/reports/devtools/commerce-state-audit.json
- next_time_signal: 新增 DevTools 断言涉及 `disabled`、`checked`、`hidden` 等布尔属性时，先读取并记录原始 `attribute()` 返回值，禁止凭浏览器 DOM 习惯假设为 `"true"`。

## M-20260912-077：商品目录用更新时间冒充人气，营销徽标由前端本地推断

- status: guarded
- first_seen: 2026-09-12
- severity: medium
- symptom: 顾客端商品页“全部商品”和分类列表实际按 `updated_at DESC` 排列，最近被后台编辑过的商品排在数百个 SKU 的最前面；商品卡上的 `招牌`、`热卖`、`新品`、`限量` 由页面按列表位置和标签关键字本地推断，没有销量或后台配置来源。
- root_cause: 目录接口早期只暴露 `categoryId` / `ids` / `featured` 过滤，没有排序参数，页面只能拿到更新时间序；为了让卡片“看起来丰富”，`toProductView` 又用 `isFirst` 和标签关键字生成徽标，缺少数据契约与门禁。
- impact: 顾客进店先看到的是最近改过的商品而不是真实畅销品，畅销品被压在长列表后面；把没有依据的商品标成“招牌/热卖”属于误导商品信息，会损害经营 12 年门店的可信度。未造成订单、支付或库存写入错误。
- fix: 目录服务与仓储新增 `sort=popular`，按 `youzan_products.sold_num`（同 `item_no` 合并销量）降序，未知值回退更新时间序且不拼接原始字符串；商品页首次加载与分类懒加载固定传 `sort=popular`；删除 `getBadgeKind` / `getBadgeText` 推断，徽标只保留可核对来源的 `现货`（商品标签）、`暂时售罄`、`已下架`，无依据时 `wx:if` 不渲染。
- new_guardrail: `backend/tests/service/test_catalog.py` 新增更新时间序与销量序相反的样例，`backend/tests/api/test_miniapp_catalog_api.py` 覆盖 `?sort=popular`；`verify-devtools-commerce-states.cjs` 断言商品目录徽标只允许 `现货`、`暂时售罄`、`已下架`，并校验活动商品 `已售 N` 数字降序。
- verification: `python -B -m pytest backend/tests/service/test_catalog.py backend/tests/api/test_miniapp_catalog_api.py -q --no-cov` 14 passed；真实库查询 `youzan_products` 按 `sold_num` 降序前八为 934/542/340/319/287/270/243/237，与 `GET /api/v1/miniapp/products?sort=popular` 返回顺序一致；`npm run typecheck`、`npm run check:miniapp`（15 页 15 路由）、`npm run check:page-api-coverage`（15 页 34 术语 9 边界）、`npm run audit:buttons`（106 控件）、`npm run audit:button-styles`（0 失败 0 警告）通过；`npm run devtools:commerce-states` PASS，报告 `catalog-badges-and-popularity` 记录 `badgeTexts=[]`、`soldNumbers=[934,542,340,319,287,270,243,237,236,227,218,191]`、`salesOrderedDescending=true`；`npm run devtools:product-purchase-path`、`npm run devtools:verify-all-pages`（15/15）、`npm run devtools:checkout-delivery-states` 均 PASS。
- linked_trace: 20260908-miniapp-commerce-ux-redesign
- linked_files: ERRORS.md；backend/app/service/catalog/application.py；backend/app/api/channels/storefront/catalog.py；backend/app/repository/youzan_repo.py；backend/tests/service/test_catalog.py；backend/tests/api/test_miniapp_catalog_api.py；miniapp/miniprogram/pages/products/index.ts；miniapp/miniprogram/pages/products/index.wxml；miniapp/miniprogram/services/products.ts；miniapp/miniprogram/app.wxss；miniapp/scripts/verify-devtools-commerce-states.cjs；miniapp/docs/api-contract.md
- next_time_signal: 新增目录排序或商品卡徽标时，先确认数据源字段是否真实存在；排序参数必须经服务层白名单映射，禁止把用户字符串拼进 SQL，也禁止用位置、标签关键字或页面文案推断营销标签。

## M-20260912-078：生产域名证书过期，阻断生产 API 与真机线上验收

- status: open
- first_seen: 2026-09-12
- severity: medium
- symptom: `npm run check:production-miniapp-api` 对 `https://yunxifood.cn` 的首页装修、商品、分类、店铺设置和登录配置全部失败；报告统一记录 `cause=certificate has expired`，并非接口路由或本地代码错误。同一阻断还会让 `devtools:product-buy-now`、`devtools:cart-checkout-real-product`、`devtools:service-smoke` 在开发者工具里退化成 `timeout waiting for automator response`（13s 事后报错），容易被误判成页面或自动化缺陷。
- root_cause: `yunxifood.cn` 的 Let's Encrypt 证书有效期为 `2026-06-05 01:41:59 GMT` 至 `2026-09-03 01:41:58 GMT`，截至 2026-09-12 已过期且未完成续期部署。
- impact: 生产 API、真机线上联调和依赖 HTTPS 的生产验收均不可执行；本地后端与 DevTools 通过不能替代生产可访问性证据。
- fix: 由运维续期并部署 `yunxifood.cn` 证书，部署后重新运行生产 API 检查并保存新报告；代码侧不通过关闭证书校验绕过。
- new_guardrail: 每次真机或生产验收前先运行 `npm run check:production-miniapp-api`；证书错误单独判定为基础设施阻断，不伪装成功能验收通过。真实链路脚本统一接入 `miniapp/scripts/lib/real-api-preflight.mjs`：连接开发者工具前先用 `node:https` 探测 `/health`，证书/域名/网络失败时 2 秒内以退出码 2 输出明确原因且不覆盖上一份报告，地址可用 `MINIAPP_REAL_API_BASE_URL` 覆盖。
- verification: `npm run check:production-miniapp-api` 退出码 1；五个端点均返回 `certificate has expired`；报告：`miniapp/reports/production-api-check/production-miniapp-api-20260912-121849.json`。2026-09-13 复跑 `check:production-domain` 与 `check:production-miniapp-api` 仍为 fail；三个真实链路脚本加入预检后实测 1.9–2.3s 退出码 2 并输出 `TLS 证书已过期…（CERT_HAS_EXPIRED）`，预检对 `http://127.0.0.1:7001/health` 返回 200 正常放行（证书 `NotAfter=2026-09-03 09:41:58`，截至复跑已过期 9.6 天）。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `miniapp/scripts/check-production-miniapp-api.mjs`; `miniapp/scripts/lib/real-api-preflight.mjs`; `miniapp/scripts/check-devtools-product-buy-now.mjs`; `miniapp/scripts/check-devtools-cart-checkout-real-product.mjs`; `miniapp/scripts/check-devtools-service-smoke.mjs`; `miniapp/reports/production-api-check/production-miniapp-api-20260912-121849.json`
- next_time_signal: 生产检查若统一显示 `fetch failed`，先核对 `cause` 与证书有效期；在续期完成前，不得把本地 DevTools PASS 写成生产或真机线上已验证。

## M-20260912-079：分类表与商品 tag 命名空间错配，商品页出现空分类导航

- status: guarded
- first_seen: 2026-09-12
- severity: medium
- symptom: 真实 `GET /api/v1/miniapp/product-categories` 返回 34 个分类且 `productCount` 全为 0；点击 `youzan-classification-40606522` 返回 0 商品。旧序列化又把 tag 命中项统一伪装成 `classification` 前缀，导致列表 ID 与商品 `tag_ids_json` 的过滤路径不一致。
- root_cause: 真实库 310 条在售商品的 `classification_ids_json` 全为空，实际只有 7 个 tag；分类表中的 34 个 ID 来自另一套 classification 数据且与 tag ID 无交集。旧实现信任缓存 `product_count`，并把 tag 结果输出成 classification 命名空间。
- impact: 顾客看到大量空分类，点开无商品；分类导航不可信，商品发现路径被破坏。未造成订单、支付、库存或客户数据写入。
- fix: `list_public_categories()` 用 `json_each` 按当前在售商品现场统计 tag/classification 命中；公开接口只返回真实计数大于 0 的分类；序列化保留 `youzan-tag-` 与 `youzan-classification-` 各自命名空间；无有效映射时返回空数组，前端退化为“全部商品”并优先展示真实销量序。
- new_guardrail: 分类列表必须现场统计在售商品；分类 ID 必须保留数据源真实命名空间；新增测试覆盖“空分类不输出”和“tag 分类可筛选”。
- verification: 定向测试 `backend/tests/service/test_catalog.py`、`backend/tests/api/test_miniapp_catalog_api.py` 共 16 项通过；真实分类接口返回 `data=[]`；真实 tag 过滤仍可返回商品；商品列表 310 条按销量 934→191 排列。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `backend/app/repository/youzan_repo.py`; `backend/app/service/catalog/serialization.py`; `backend/tests/service/test_catalog.py`; `backend/tests/api/test_miniapp_catalog_api.py`; `miniapp/docs/api-contract.md`
- next_time_signal: 分类接口再次出现 `productCount=0`、分类 ID 与商品字段前缀不一致或点开为空时，先核对 `classification_ids_json` / `tag_ids_json` 实际值，禁止用随机 ID 前缀或缓存计数修补。

## M-20260912-080：商品详情泄露有赞同步原文，配件商品被错误承诺提前预订

- status: guarded
- first_seen: 2026-09-12
- severity: medium
- symptom: 商品详情 `description` 直接包含 `商品名称：`、`在售状态：`、秒级库存明细、`h5.youzan.com` 直购链接、`[UMP: ...]`；`tags/specs` 含 `8/3/9` 等数字同步标签。数字蜡烛和餐具因通用分类名“蛋糕”被判为蛋糕，卡片或详情曾提示“建议提前1天预订”。
- root_cause: 公开商品序列化直接输出知识条目的同步原文和标签；前端只做局部过滤。配送提示仅依据 `categoryName` 是否包含“蛋糕”，而有赞关键词把“蛋糕”泛化到了蜡烛、餐具等周边。
- impact: 顾客在朋友圈直达或商品详情中看到内部库存字段、平台链接和无意义数字，降低信任；配件被错误承诺制作周期，可能造成发货预期和客服沟通偏差。未造成订单、支付或库存写入。
- fix: 后端新增同步噪声行清洗、卡片副标题清洗和标签/规格过滤；公开 `description/subtitle/tags/specs` 不再输出内部字段、链接、UMP 标记和纯数字标签；前端共享 `getProductPurchaseHint()`，配件优先按现货/客服确认提示，蛋糕标题含蜡烛说明时仍保持蛋糕预订语义，详情页绑定动态下单说明；通用购买须知改为不假设手工现制。
- new_guardrail: 新增后端回归测试断言同步噪声不会进入公开字段；`miniapp/tests/utils/bakery.test.ts` 覆盖数字蜡烛、餐具、蛋糕标题中的蜡烛说明和真实现货标签；新的 DevTools 流程脚本断言详情直达无导入噪声。
- verification: 定向测试 16 passed；`npm run test:bakery` 4 项通过；`npm run devtools:verify-commerce-flows` 九节点 PASS，数字蜡烛详情 `fulfillmentHint=现货可直接下单，闪送费下单前确认`、`hasImportNoise=false`；截图 `miniapp/reports/devtools/commerce-flow-detail.png` 目视通过。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `backend/app/service/catalog/serialization.py`; `backend/tests/service/test_catalog.py`; `miniapp/miniprogram/utils/bakery.ts`; `miniapp/miniprogram/pages/products/index.ts`; `miniapp/miniprogram/pages/product-detail/index.ts`; `miniapp/miniprogram/pages/product-detail/index.wxml`; `miniapp/miniprogram/pages/cart/index.ts`; `miniapp/tests/utils/bakery.test.ts`; `miniapp/scripts/verify-miniapp-commerce-flows.cjs`
- next_time_signal: 新增商品详情字段或履约提示时，先核对真实同步值并跑噪声与配件语义测试；不得把通用分类名当作商品类型，也不得把原始有赞标签直接展示给顾客。

## M-20260912-081：分类命名空间首次修复把 item.base 分类当成 tag，点击分类为空

- status: guarded
- first_seen: 2026-09-12
- severity: medium
- symptom: 分类命名空间修复后的首轮全量回归中 `backend/tests/service/test_catalog_item_base_category.py::test_list_categories_and_filter_by_item_base_classification` 失败：期望分类列表包含 `youzan-classification-67`，实际返回空数组。
- root_cause: `youzan_product_categories.tag_id` 同时承接两类真实数据：有赞商品 tag id 与 `item.base` 的 classification id，两者分别落在商品宽表的 `tag_ids_json` 与 `classification_ids_json`。首次修复只按 tag 字段现场统计命中数，并把分类入口统一按 tag 命名空间输出，导致真实存在的 item.base 分类被当成零命中分类过滤掉。
- impact: 若随代码上线，会让靠 item.base 分类建目录的商品在顾客端失去分类入口（分类侧栏为空或退化到全部商品）；未造成订单、支付、库存或客户数据写入。
- fix: 仓储对 tag 与 classification 分别统计命中数；序列化按真实命中选择命名空间（classification 优先，与商品侧解析顺序一致），`productCount` 取所选命名空间的实际命中数，零命中才不公开。
- new_guardrail: 保留 `item.base` 分类回归测试，并新增 `test_category_namespace_prefers_classification_when_both_match` 覆盖“同一分类键同时命中 tag 与 classification”的计数与可点开一致性。
- verification: 修复后 `pytest backend/tests/service/test_catalog.py backend/tests/service/test_catalog_item_base_category.py backend/tests/api/test_miniapp_catalog_api.py backend/tests/test_lifespan_routes_services.py -q --no-cov` 21 项通过；真实分类接口在无有效映射时返回空数组。首轮全量回归（738.33s）捕获该缺陷，收口复跑未再出现该项失败；同次收口剩余 2 项隔离 Harness 失败已由 M-20260912-085 承接。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `backend/app/repository/youzan_repo.py`; `backend/app/service/catalog/serialization.py`; `backend/app/service/catalog/customer_text.py`; `backend/tests/service/test_catalog.py`; `backend/tests/service/test_catalog_item_base_category.py`
- next_time_signal: 改动分类列表、分类 ID 前缀或 `classification_ids_json` / `tag_ids_json` 命中逻辑时，必须先跑 `backend/tests/service/test_catalog_item_base_category.py`；分类列表的 `productCount` 必须与点击后返回的商品数一致。

## M-20260912-082：闪送配送服务接入后 lifespan 路由与服务装配测试长期未同步

- status: guarded
- first_seen: 2026-09-12
- severity: low
- symptom: 首轮全量回归中 `backend/tests/test_lifespan_routes_services.py` 两项失败，报 `KeyError: 'delivery_service'` 与 `KeyError: 'delivery_quote_repo'`，与商品分类改动无关联。
- root_cause: 闪送报价能力接入 `lifespan_services` 与 `lifespan_routes` 时，只跑了配送定向测试，未同步更新装配测试的仓储桩、路由桩和期望集合，导致全量回归长期残留 2 项失败。
- impact: 全量回归的真实失败信号被长期噪声掩盖，可能掩盖后续新缺陷；运行时代码本身正常，未影响订单、支付或库存写入。
- fix: 测试补上 `delivery_quote_repo` 仓储桩、`create_storefront_delivery_router` 路由桩与期望集合中的 `delivery_service`，并把包含路由数断言从 29 更新为 30。
- new_guardrail: 新增 `lifespan_services` / `lifespan_routes` 服务装配或路由注册时，必须同轮更新装配测试并跑该文件全量。
- verification: `pytest backend/tests/test_lifespan_routes_services.py -q --no-cov` 3 项通过；收口全量复跑无该文件失败。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `backend/tests/test_lifespan_routes_services.py`; `backend/app/lifespan_services.py`; `backend/app/lifespan_routes.py`
- next_time_signal: 全量回归出现 `KeyError` 的服务名或路由名时，先核对 `lifespan_services` 实际写入键与该测试的桩，禁止改被测代码迎合旧测试。

## M-20260912-083：文件体量门禁存量红，`payment_runtime.py` 未登记职责评审

- status: open
- first_seen: 2026-09-12
- severity: low
- symptom: `python -B backend/scripts/check_file_sizes.py` 退出码 1，报 `app/service/order/payment_runtime.py: 416 行（未评审阻断线 320 行，超出 96 行）`。该文件本轮未修改。
- root_cause: 该文件自 `9544acb` 审计整改后超过 320 行阻断线，但既未在 `backend/scripts/check_file_sizes.py` 的 `OVERSIZE_REVIEW_NOTES` 登记职责评审，也未完成拆分。
- impact: 文件体量门禁在 main 上长期为红，掩盖本轮新增文件体量问题；本轮 `serialization.py` 超线先被门禁定位并拆分为 `customer_text.py`，该存量项仍未解除。
- fix: 由订单支付域负责人完成 `payment_runtime.py` 职责评审：职责混杂则按稳定可独立测试边界拆分，职责内聚则在门禁中补充真实保留理由；禁止为压行数机械切分。
- new_guardrail: 收口时同时运行 `check_project.py --skip-tests` 与 `check_file_sizes.py`，存量红项单独记录，禁止写成“门禁全绿”。
- verification: `python -B backend/scripts/check_file_sizes.py` 退出码 1，仅剩该存量项；拆分后 `serialization.py` 为 276 行，本轮新增超线项已消除。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `backend/scripts/check_file_sizes.py`; `backend/app/service/order/payment_runtime.py`; `backend/app/service/catalog/serialization.py`; `backend/app/service/catalog/customer_text.py`
- next_time_signal: 再次看到文件体量门禁红时，先区分“本轮新增超线”与“存量未评审项”；新增项必须在同轮拆分或给出职务评审，存量项继续单列。

## M-20260912-084：全量后端测试耗时 738s 超 10 分钟阈值，需建立优化事项

- status: open
- first_seen: 2026-09-12
- severity: medium
- symptom: 本轮收口首轮全量 `pytest backend/tests -q` 耗时 738.33s（12.3 分钟），超过项目 10 分钟阈值；最近基线为 2026-09-06 的约 510s（`--no-cov`，1854 项），本轮命令默认启用覆盖率插桩，可比口径不同。
- root_cause: 主要差异来自默认 `--cov` 插桩开销（同仓文档记录的基线命令使用 `--no-cov`）；另有一批真实网络/加密与迁移重放类用例单次执行时间长。
- impact: 收口阶段的开发反馈周期长，全量回归不适合作为日常循环；不影响功能正确性，不改变上线边界。
- fix: 建立耗时优化事项并按以下方向评估：①全量收口统一使用 `--no-cov`，覆盖率单独按计划运行；②按慢用例名单拆出可标记的慢集合并提供定向入口；③核对迁移重放与真实网络类用例能否使用夹具复用。
- new_guardrail: 每轮全量必须记录命令与耗时；跨轮对比必须先统一覆盖率开关，否则不得直接归因于代码回归。
- verification: 本轮首轮全量 738.33s；收口全量复跑 745.7s，剩余 2 项隔离 Harness 失败由 M-20260912-085 定位修复并完成覆盖插桩定向验证；耗时事实已记入 `LOGBOOK.md` r26 条目与 `docs/harness-engineering/core/evidence-index.md` E-20260912-006。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `docs/tasks/20260906-项目负责人最终上线收口计划-OpenCode.md`; `backend/tests/`; `pytest.ini`
- next_time_signal: 全量耗时再次超过 10 分钟或较可比基线增长 20% 时，先确认覆盖率开关与慢用例名单，再判定是否为新回归。

## M-20260912-085：隔离整改 Harness 在覆盖率模式泄漏 SQLite 查询连接，Windows 临时库清理失败

- status: guarded
- first_seen: 2026-09-12
- severity: low
- symptom: 全量收口复跑剩余 2 项失败均为 `backend/tests/scripts/test_run_isolated_remediation_harness.py`；使用仓库默认覆盖率配置单跑可稳定复现。两个用例均在删除临时库时报 Windows `PermissionError: [WinError 32]`，并伴随 `ResourceWarning: unclosed database`。
- root_cause: `_wait_for_processing()` 使用 `with sqlite3.connect(...)` 轮询任务状态；Python 的 `sqlite3.Connection` 上下文管理器只提交/回滚事务，不关闭连接，覆盖率插桩延长对象存活时间后该连接会持续占用临时库文件，导致 Windows 无法删除。`--no-cov` 下此前因回收时机偶发通过，掩盖了真实资源泄漏。
- impact: 默认全量测试会产生 2 项稳定失败并阻止“全量 0 失败”结论；不影响生产运行、订单、支付或数据写入。
- fix: `_wait_for_processing()` 改用 `contextlib.closing(sqlite3.connect(...))`，保证每轮轮询后关闭连接；未修改任何断言、超时或清理保护逻辑。
- new_guardrail: 隔离脚本中打开同步 SQLite 文件时，必须显式使用 `closing(...)` 或 `try/finally` 关闭；覆盖率插桩模式下的目标测试通过后才能把 Harness 清理失败归为偶发。
- verification: 修复前 `python -m pytest tests/scripts/test_run_isolated_remediation_harness.py -q --tb=short` 稳定 2 failed（默认覆盖率）；修复后同文件 `--cov-fail-under=0` 4 passed；`test_harness_eval_regression.py + test_run_isolated_remediation_harness.py` 合跑 9 passed（`--no-cov`）。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `backend/scripts/run_isolated_remediation_harness.py`; `backend/tests/scripts/test_run_isolated_remediation_harness.py`; `backend/tests/scripts/test_harness_eval_regression.py`
- next_time_signal: Windows 下临时 SQLite 删除报 `WinError 32` 时，先排查所有 `sqlite3.connect` / `aiosqlite.connect` 是否真正关闭；不得通过忽略清理错误或跳过用例规避。

## M-20260912-086：全局按钮重置压过页面 class 规则，两个页面的主按钮变成白字透明底

- status: guarded
- first_seen: 2026-09-12
- severity: medium
- symptom: 未登录态的“我的优惠券”“积分明细”两页，`去登录` 按钮在 DevTools 里渲染成没有文字的白色圆角块；订单列表的 `order-action-primary` / `order-action-secondary` 按钮存在同一根因。
- root_cause: `app.wxss` 的按钮重置写成 `button, button:not([size="mini"])`，其中 `button:not([size="mini"])` 特异度为 (0,1,1)，高于页面裸 class 规则 `.primary-btn` / `.order-action-primary` 的 (0,1,0)。重置的 `background-color: transparent`、`border-radius: 0`、`padding: 0`、`min-height: 0` 生效，而 class 内的 `color: #FFFFFF` 仍然生效，形成白字透明底。
- impact: 顾客在优惠券页、积分页看不到登录入口，订单页的付款与取消动作不可见；未造成订单、支付、库存写入，但主路径动作在视觉上消失。
- fix: 优惠券/积分页改为 `.coupons-page button.primary-btn`、`.points-page button.primary-btn`，订单页改为 `.page button.order-action-*`，特异度提到 (0,2,1) 后压过重置；未改动全局重置本身，避免波及已正确的页面。
- new_guardrail: `miniapp/scripts/audit-miniapp-button-styles.mjs` 新增 `button-reset-overrides-class` 失败项，按属性计算最高特异度选择器，背景类属性被重置比下去即判失败；已用临时还原 `.primary-btn` 的方式反向验证该检查能真实报错。
- verification: 修复前 DevTools 计算样式为 `background-color: rgba(0, 0, 0, 0)`、`color: rgb(255, 255, 255)`、`font-size: 16px`；修复后为 `rgb(61, 51, 45)`、`rgb(255, 255, 255)`、`font-size: 13px`、`border-radius: 4px`。`npm run audit:button-styles` 106 控件 0 失败；`npm run devtools:verify-all-pages` 15/15 PASS，并新增未登录态截图覆盖；证据截图 `miniapp/reports/devtools/final-logged-out-coupons.png`、`miniapp/reports/devtools/final-logged-out-points.png`。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `miniapp/miniprogram/app.wxss`; `miniapp/miniprogram/pages/coupons/index.wxss`; `miniapp/miniprogram/pages/points/index.wxss`; `miniapp/miniprogram/pages/orders/index.wxss`; `miniapp/scripts/audit-miniapp-button-styles.mjs`
- next_time_signal: 页面按钮“样式写了却像没生效”或只看到空白圆角块时，先比对该规则与 `button:not([size="mini"])` 的特异度；页面按钮规则必须带页面作用域或 `button.` 前缀。

## M-20260912-087：商品卡“可预订”标签与现货履约提示互相矛盾

- status: guarded
- first_seen: 2026-09-12
- severity: medium
- symptom: 商品列表中数字蜡烛同时显示橙色“可预订”标签、`预订` 按钮和“现货可直接下单，闪送费下单前确认”提示；首页每张商品卡都挂着“可预订”角标并压住商品图。
- root_cause: 列表页 `getStockText()` 把“库存大于 5”渲染成“可预订”，与共享履约提示 `getProductPurchaseHint()` 的现货口径各自维护；首页用 `stock > 0 ? "可预订"` 生成角标，按钮文案固定为“预订”。同一张卡片的三处文案来自不同推导，彼此没有约束。
- impact: 顾客在同一张卡片上收到互斥的履约承诺，无法判断商品是现货还是必须提前预订；默认能力被当成卖点重复展示，也降低商品图的辨识度。
- fix: `miniapp/miniprogram/utils/bakery.ts` 新增 `getProductAvailabilityLabel` / `getProductActionLabel` / `getProductAddToastLabel` / `getProductCardTip` 四个共享口径：现货配件为“现货 + 加入购物车 + 已加入购物车”，现做商品不再显示默认标签并为“预订 + 提前 1 天预订”；列表与首页改为调用它们；图片角标只保留“已下架/暂时售罄”，详情页常驻“在售”标签改为仅不可售时展示原因。
- new_guardrail: `miniapp/tests/utils/bakery.test.ts` 增至 8 项，覆盖标签、按钮、提示、加购提示音的一致性；`miniapp/scripts/verify-devtools-commerce-states.cjs` 的允许动作集合加入“加入购物车”，并断言卡片可用性标签只能匹配 `现货|暂时售罄|已下架|仅余 N 件`。
- verification: `npm run test:bakery` 8 passed；`npm run typecheck`、`npm run check:miniapp` 通过；`npm run devtools:commerce-states` PASS，报告记录 `productActionText=加入购物车`、`stockLabelText=现货`、`badgeTexts=[]`；`npm run devtools:verify-all-pages` 15/15 PASS；截图 `miniapp/reports/devtools/final-products.png`、`miniapp/reports/devtools/final-home.png`。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `miniapp/miniprogram/utils/bakery.ts`; `miniapp/miniprogram/pages/products/index.ts`; `miniapp/miniprogram/pages/products/index.wxml`; `miniapp/miniprogram/pages/home/index.ts`; `miniapp/miniprogram/pages/home/index.wxml`; `miniapp/miniprogram/pages/product-detail/index.wxml`; `miniapp/tests/utils/bakery.test.ts`
- next_time_signal: 同一元素上标签、按钮、提示各说一套时，先查是否存在多份本地文案推导；商品可用性与履约文案必须来自单一共享函数。

## M-20260912-088：客服页未登录态标题写成“连接已断开”，与实际原因不符

- status: guarded
- first_seen: 2026-09-12
- severity: low
- symptom: 未登录进入客服页时，标题显示“客服连接已断开”，副文案却是“请在个人中心登录后与客服通话”。
- root_cause: 该空状态由 `wx:if="{{!canUseChat}}"` 渲染，而 `canUseChat` 只由本地登录态决定；标题沿用连接失败语义，副文案已改成登录引导，两者未同步。
- impact: 顾客会误判为客服掉线或网络故障，而不是需要先登录；不涉及数据写入。
- fix: 标题改为“登录后联系客服”，并补齐积分页未登录态缺失的副文案“登录后查看您的积分明细”，与优惠券页保持一致。
- new_guardrail: 未登录态截图覆盖加入 `miniapp/scripts/verify-all-15-pages-devtools.cjs` 的确定性未登录清单（优惠券、积分、客服），登录态字段不统一时优先读会话视图、回退页面自身 `loggedIn`。
- verification: `npm run devtools:verify-all-pages` 15/15 PASS（含扩展后的未登录态）；截图 `miniapp/reports/devtools/final-logged-out-chat.png`。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `miniapp/miniprogram/pages/chat/index.wxml`; `miniapp/miniprogram/pages/points/index.wxml`; `miniapp/scripts/verify-all-15-pages-devtools.cjs`
- next_time_signal: 状态标题出现“断开/失败/错误”类措辞时，先核对渲染条件是不是登录态或空数据态；标题必须与真实原因一致。

## M-20260912-089：触控扫描用 mock 商品 ID 打开详情页，真实后端下必现假失败

- status: guarded
- first_seen: 2026-09-12
- severity: low
- symptom: `npm run scan:button-touch-targets` 报 `product-detail .primary-button` 实际数量 0；同一页 `.ghost-button` 文本为“返回选购”，说明页面落在“商品不存在”态。
- root_cause: 扫描用本地 mock id `p_001` 打开商品详情，而有赞同步的真实商品 ID 为纯数字；页面按真实目录加载后进入不存在分支。脚本其他状态都用 `page.setData` 播种确定性数据，只有详情页依赖 mock id 命中。
- impact: 触控门禁出现与真实 UI 无关的红项，长期会掩盖真实触控缺陷；也说明该扫描此前未纳入常规串行复跑，只能在带 mock 目录的环境偶发通过。
- fix: 详情页扫描状态新增 `setup`，写入可购买商品与 `canPurchase` 等确定性数据，使断言校验真实操作栏；同结算页既有做法一致。
- new_guardrail: 新增页面状态校验时，若断言依赖具体商品或订单数据，必须用 `setup` 播种确定性数据，不得依赖 mock id 在真实后端命中。
- verification: `MINIAPP_AUTOMATOR_WS=ws://127.0.0.1:9420 npm run scan:button-touch-targets` 修复前 fail（39 selectors / 10 pages），修复后 pass（39 selectors / 10 pages），报告 `miniapp/reports/button-visual/button-touch-targets-20260912-140826.json`。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `miniapp/scripts/scan-miniapp-button-touch-targets.mjs`; `miniapp/reports/button-visual/button-touch-targets-latest.json`
- next_time_signal: 触控或视觉扫描出现“元素数量为 0”时，先确认页面是否落在兜底态（未传 ID、未登录、空数据），再判定为缺陷。

## M-20260912-090：订单详情未登录卡片被居中空态压窄，标题换行且副文案截断

- status: guarded
- first_seen: 2026-09-12
- severity: low
- symptom: 未登录进入订单详情时，会话提示卡片宽度只剩约 370/546px，标题“微信身份 · 未登录”折行，副文案“请先登录后查看订单详情”贴住右侧按钮；同一组件在订单列表、收货地址页是通栏卡片。
- root_cause: 订单详情把组件放进 `.empty` 空态容器，该容器是 `display: flex; align-items: center` 的纵向弹性容器；`session-notice` 宿主节点作为弹性项目按内容宽度收缩（shrink-to-fit），组件内部再按更窄的可用宽度排版。其他页面把组件直接放在纵向 stretch 的页面容器里，所以没有暴露。
- impact: 顾客在订单详情未登录态看到断行、贴边与截断文案，与相邻页面的同一组件视觉不一致；不涉及订单、支付或库存写入。
- fix: 组件宿主加 `class="empty-notice"`，页面样式补 `.empty-notice { width: 100%; box-sizing: border-box; }`；组件已声明 `styleIsolation: apply-shared`，宿主节点宽度由页面样式接管。
- new_guardrail: `miniapp/scripts/verify-all-15-pages-devtools.cjs` 的会话状态检查新增宽度断言：任何页面渲染出 `.session-notice` 时宽度低于视口 85% 即判失败，并在报告中记录 `sessionNoticeWidth`。
- verification: `npm run check:miniapp`（15 页 15 路由）、`npm run typecheck`、`npm run test:bakery`（8 passed）、`npm run audit:buttons`（106 控件）、`npm run audit:button-styles`（106 控件 0 失败）均通过；运行态复跑被 Windows 锁屏阻断（见 M-20260912-091），待解锁后执行 `npm run devtools:verify-all-pages` 并按 `sessionNoticeWidth` 复核。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `miniapp/miniprogram/pages/order-detail/index.wxml`; `miniapp/miniprogram/pages/order-detail/index.wxss`; `miniapp/scripts/verify-all-15-pages-devtools.cjs`
- next_time_signal: 自定义组件放进 `align-items: center` 的弹性容器后出现文字折行、贴边或截断时，先量宿主节点宽度是否退化成内容宽度；宿主需要显式 `width: 100%`。

## M-20260912-091：Windows 锁屏时 DevTools 自动化端口可连接但无响应，15 页审计全部假失败

- status: guarded
- first_seen: 2026-09-12
- severity: medium
- symptom: `npm run devtools:verify-all-pages` 每页都报 `Audit exception: timeout waiting for automator response`，`all-pages-devtools-audit.json` 写入 `status: FAIL`、`passed: 0`、`loggedOutFailed: 7`；与此同时 `netstat` 显示 9420 正在监听，`automator.connect()` 也能成功返回。
- root_cause: 运行会话处于 Windows 锁屏状态（`LogonUI.exe` 常驻、屏幕停在 PIN 登录界面），开发者工具渲染进程被挂起，WebSocket 建连成功但协议命令不再返回；表面症状容易被误判为“自动化端口未开”或“代码改坏了”。
- impact: 运行态视觉与交互门禁整轮假失败，并且该失败报告覆盖了上一份 15/15 PASS 的 `all-pages-devtools-audit.json`，额外消耗一次全量复跑与排查。
- fix: 审计脚本改为两段式响应探测（`automator.connect()` 与随后 `currentPage()` 各带超时），探测失败时输出明确原因并以退出码 2 快速失败，不写入报告，从而保留上一份运行态证据；最初实现的 `LogonUI` 进程名预检因假阳性被替换，见 M-20260912-094。
- new_guardrail: `verify-all-15-pages-devtools.cjs` 锁屏快速失败；三条症状对照：9420 无监听=自动化端口未开（`cli.bat auto --auto-port 9420`），端口监听但 `systemInfo()` 超时=锁屏或 IDE 卡死，单页失败=页面态问题。
- verification: 屏幕截图与 `Get-Process LogonUI` 确认锁屏；快速失败加入前 15/15 页超时并覆盖了上一份 PASS 报告，加入后未响应时脚本秒级以退出码 2 结束且报告 mtime 不变；响应探测版本在桌面可用时正常放行并完成 15/15 PASS（E-20260912-008）。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `miniapp/scripts/verify-all-15-pages-devtools.cjs`; `miniapp/reports/devtools/all-pages-devtools-audit.json`
- next_time_signal: 开发者工具“能连上但全部超时”时先查 Windows 是否锁屏，再怀疑代码；锁屏期间生成的审计报告不能当作 UI 回归结论。

## M-20260912-092：触控扫描给个人中心播种了错误字段名，审阅状态与截图出现空白入口图标

- status: guarded
- first_seen: 2026-09-12
- severity: low
- symptom: `final-profile.png` 里个人中心“我的订单”四个入口是空灰方块，与 `final-profile-member-summary.png` 中正常的“付/制/送/售”图标不一致。
- root_cause: `scan-miniapp-button-touch-targets.mjs` 的 profile 状态把订单入口播种为 `emoji` 字段，而页面 WXML 渲染的是 `order.iconText` / `service.iconText`；字段名不匹配所以图标为空。又因为 tab 页面用 `switchTab` 复用同一页面实例，播种数据留在页面栈里，后续 `verify-all-pages` 截图直接捕获了这份非真实状态。
- impact: 触控扫描实际量的是图标为空的入口，截图证据也与真实页面不一致，容易被误读成产品缺陷；未影响真实用户界面。
- fix: profile 状态改为按页面真实字段播种（`iconText` 为“付/制/送/售”与“电/微/售”，并沿用页面真实 `linkType`/`linkTarget`）。
- new_guardrail: `verify-all-15-pages-devtools.cjs` 新增 `inspectProfileShortcuts()`：个人中心订单入口不足 4 个、或订单/服务入口图标文本为空即判失败，并在报告记录 `profileShortcutIcons`。
- verification: `node --check` 两个脚本通过；`npm run check:miniapp`（15 页 15 路由）、`npm run audit:button-styles`（106 控件 0 失败）通过；运行态复跑 `devtools:verify-all-pages` 15/15 PASS，报告 `profileShortcutIcons={"order":4,"service":5}`，`final-profile.png` 目视确认 5 个服务图标与 4 个订单图标均非空。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `miniapp/scripts/scan-miniapp-button-touch-targets.mjs`; `miniapp/scripts/verify-all-15-pages-devtools.cjs`; `miniapp/miniprogram/pages/profile/index.wxml`
- next_time_signal: 播种态截图里出现空图标/空文案时，先对比页面 `wx:for-item` 实际读取的字段名与播种字段名；不要再假设播种对象形状天然正确。

## M-20260912-093：结算页写死的错误自提地址会进入闪送报价与订单快照

- status: guarded
- first_seen: 2026-09-12
- severity: medium
- symptom: 结算页存在两处写死的自提地址兜底：`pages/checkout/index.ts` 的“北京市朝阳区云熙烘焙工坊”（错城区 + 品牌错字“云熙”）和 `pages/checkout/index.wxml` 的“北京市朝阳区芸熙烘焙”；而门店真实经营地址在 `config/shop.ts` 为“北京市东城区南竹杆胡同2号银河SOHO”。
- root_cause: 门店自提地址没有单一来源；页面在早期联调阶段写入了本地兜底常量，后来门店地址配置落在 `config/shop.ts`，两处兜底没有回收。
- impact: 一旦门店设置接口未返回地址，界面会展示错误门店；更严重的是 `requestDeliveryQuote()` 与 `createOrder()` 都以 `pickupAddress` 为闪送起点，会按错误地址计算距离与运费，并把错误取货点写入订单快照，顾客也可能按界面信息去错门店。该问题不满足“只影响样式”的降级条件。
- fix: `getPickupAddressForQuote()` 回退改为 `SHOP_CONFIG.pickupAddress`；WXML 兜底改为不误导的“请联系客服确认取货地址”；新增静态门禁禁止页面写死其它北京市地址与品牌错字「云熙」。
- new_guardrail: `check-miniapp.mjs` 新增 `checkPickupAddressSourceOfTruth()`：以 `config/shop.ts` 的 `pickupAddress` 为唯一来源，扫描 `miniprogram/**` 的 `北京市…` 地址字面量与品牌错字；命中即退出码 1。
- verification: 反向验证——临时把错误地址写回 `pages/checkout/index.wxml` 后 `npm run check:miniapp` 退出码 1 并报“写死了非门店自提地址「北京市朝阳区芸熙烘焙」”，恢复后退出码 0；`npm run typecheck` 通过；正式检查 15 页 15 路由通过。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `miniapp/miniprogram/pages/checkout/index.ts`; `miniapp/miniprogram/pages/checkout/index.wxml`; `miniapp/miniprogram/config/shop.ts`; `miniapp/scripts/check-miniapp.mjs`
- next_time_signal: 门店地址、客服电话、营业时间这类经营事实只能来自 `config/shop.ts`；页面出现具体地址字面量时，先核对是否与配置一致，尤其是会被用于报价或下单的字段。

## M-20260912-094：锁屏预检用进程名判断产生假阳性，桌面可用时也拒绝跑运行态审计

- status: guarded
- first_seen: 2026-09-12
- severity: low
- symptom: `npm run devtools:verify-all-pages` 在桌面实际可用时输出“Windows 会话处于锁屏状态”并以退出码 2 快速失败；同一时刻 `automator.connect()` 建连成功且 `currentPage()` 返回 `pages/home/index`，`Get-NetTCPConnection -LocalPort 9420` 也在监听。
- root_cause: M-20260912-091 的预检把“`LogonUI` 进程存在”当作“桌面锁屏”的判定条件，但 `LogonUI.exe`/`LockApp.exe` 在解锁后仍可能长期常驻（本次 `LogonUI` PID 38836 与 `LockApp` PID 4252 均在），进程存在与输入桌面是否被锁并不同一。
- impact: 运行态证据在桌面可用时被门禁自己拦住，修复后的 UI 无法复跑验证；反过来，只要该进程消失（例如换 Windows 版本）真实锁屏又会漏拦，两个方向都不可靠。
- fix: 预检改为直接探测自动化是否真的响应：`automator.connect({ wsEndpoint })` 与 `miniProgram.currentPage()` 两段各自带 `MINIAPP_AUTOMATOR_TIMEOUT_MS`（默认 20000ms）超时；只有探测超时或抛错才以退出码 2 快速失败且不覆盖上一份报告，`LogonUI`/`LockApp` 进程数降级为失败时的日志线索。
- new_guardrail: `verify-all-15-pages-devtools.cjs` 的 `connectWithProbe()`/`describeEnvironmentHint()`；判定依据只看“自动化是否响应”，不再看进程名。
- verification: 同一环境先测到 `Get-Process LogonUI` 命中但 `node -e` 连接返回 `pages/home/index`，证明假阳性；改造后 `npm run devtools:verify-all-pages` 完成 15 页 15/15 PASS，报告写入 `miniapp/reports/devtools/all-pages-devtools-audit.json`。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `miniapp/scripts/verify-all-15-pages-devtools.cjs`; `ERRORS.md`
- next_time_signal: 环境类门禁不要用“某个进程存在”当判定依据；优先探测被测通道本身是否响应，把进程/端口这类证据降级为失败时的诊断上下文。

## M-20260912-095：触控扫描未播种登录态，登录门槛页面整页量到 0 个控件

- status: guarded
- first_seen: 2026-09-12
- severity: low
- symptom: `npm run scan:button-touch-targets` 报 `fail: 39 selectors across 10 pages`，7 项失败集中在 `address-list`（`.address-add`/`.address-card`/`.text-button`/`.danger`）与 `orders`（`.filter-tab-item`/`.order-card`/`.order-action-button`），全部是 `actualCount: 0`，而同页 `.page-nav-back` 正常量到 45×45。
- root_cause: `pages/address/index.wxml` 与 `pages/orders/index.wxml` 都用 `sessionView.loggedIn` 作为列表分支的总开关，而扫描脚本只播种了 `addresses`/`allOrders`/`filterTabs`，没有播种 `sessionView`；此前一次 PASS 只是因为开发者工具存储里恰好还留着真实登录会话，前一步的未登录态审计清掉 `miniappSession` 后同一脚本就必然失败。
- impact: 声称“使用确定性页面数据”的触控门禁实际依赖上一步遗留的存储状态，登出状态下整块登录后 UI（地址卡、订单卡、筛选标签）不再被量测，真实触控缺陷会被静默漏掉，同时产生 7 项噪声失败。
- fix: `address-list` 与 `orders` 两个状态的 `setup` 补播 `sessionView: { loggedIn: true, ... }`，订单态同时补 `canUseOrders: true` 与 `loginStateText`；另外把 `openPage()` 的路径比对改为忽略 query（`url.slice(1).split("?")[0]`），避免带 `?mode=select` 的页面白等满五轮。
- new_guardrail: 播种状态必须覆盖页面渲染分支依赖的全部开关字段；触控扫描报告保留每个选择器的 `expectedMinCount`/`actualCount`，出现整页 `actualCount: 0` 时优先怀疑渲染分支开关而不是控件尺寸。
- verification: 修复前 `button-touch-targets-20260912-155608.json` 为 `status: fail`、7 项失败；修复后 `npm run scan:button-touch-targets` 输出 `pass: 39 selectors across 10 pages`，报告 `button-touch-targets-20260912-155904.json`。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `miniapp/scripts/scan-miniapp-button-touch-targets.mjs`; `miniapp/miniprogram/pages/address/index.wxml`; `miniapp/miniprogram/pages/orders/index.wxml`
- next_time_signal: 扫描脚本给页面直接 `setData` 播种时，要先确认 WXML 的顶层 `wx:if` 开关字段也被播种；否则量到的是空态而不是控件。

## M-20260913-097：商品详情返回控件单独实现，与其它子页圆形容器不一致

- status: guarded
- first_seen: 2026-09-13
- severity: low
- symptom: `final-product-detail.png` 的返回控件是 88rpx、6rpx 圆角、无阴影的方块；订单、订单详情、积分、优惠券、充值、地址、结算、群内登记等子页都是全局 `.page-nav-back` 的 88rpx 圆形按钮（白底 + 细边框 + 阴影）。
- root_cause: 商品详情页自建 `.detail-back`，且同一份 `index.wxss` 写了两处 `.detail-back`：前一处 `border-radius: 50%`，靠后一处又覆盖成 `border-radius: 6rpx` 并去掉阴影，形成同一控件两套口径的历史残留。
- impact: 顾客在商品详情与其它子页之间切换时会看到两套导航样式，破坏“全页面视觉统一”；不涉及订单、支付、库存或地址写入。
- fix: 删除商品详情的 `.detail-back*` 定义与覆盖规则，WXML 改用全局 `<button class="page-nav-back">` 与 `page-nav-back__icon`；触控扫描的 product-detail 状态选择器同步改为 `.page-nav-back`。
- new_guardrail: `check:miniapp` 的 `checkNonTabPageBackNavigation()` 新增断言：非 tabBar 页面必须复用共享 `page-nav-back` 控件，禁止页内自建返回样式。
- verification: 反向验证——把商品详情临时改回 `detail-back` 后 `npm run check:miniapp` 退出码 1 并报 `does not use the shared page-nav-back control`，恢复后退出码 0；`npm run typecheck` 通过；`npm run devtools:verify-all-pages` 15/15 PASS，重生成的 `final-product-detail.png` 目视确认返回控件已为圆形；`npm run scan:button-touch-targets` 39 选择器/10 页面 pass。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `miniapp/miniprogram/pages/product-detail/index.wxml`; `miniapp/miniprogram/pages/product-detail/index.wxss`; `miniapp/scripts/check-miniapp.mjs`; `miniapp/scripts/scan-miniapp-button-touch-targets.mjs`
- next_time_signal: 同一文件里同一选择器出现两段重复规则时，先判断后一段是不是历史覆盖；返回按钮、主按钮这类跳页共享控件不要在页面内另起一套样式。

## M-20260913-098：WXML 标签平衡检查器把属性值中的 `>` 误判为标签结束

- status: guarded
- first_seen: 2026-09-13
- severity: low
- symptom: 给结算页抵扣开关补 `wx:if="{{pointsBalance > 0}}"` 后，`npm run check:miniapp` 将同一行自闭合的 `<switch />` 判为未闭合，并连续报 `closes </view> ... but the latest unclosed tag is <switch>`。
- root_cause: `checkWxmlTagBalance()` 使用 `/<\s*(\/?)([A-Za-z][\w-]*)([^>]*)>/g` 提取标签，`[^>]*` 会在属性值内部的 `>` 处提前截断；WXML 表达式、URL 查询串等属性值都可能合法包含 `>`，旧解析器没有引号状态。
- impact: 合法的模板表达式会被静态门禁误报，开发者只能用 `0 < value` 等等价改写绕过，真实未闭合标签反而可能被截断后的残片掩盖。
- fix: 新增 `scanWxmlTags()`，从标签名结束处逐字符扫描，只在引号之外识别 `>`，并把标签名、属性原文、行号和文本统一提供给标签平衡与按钮提取逻辑。
- new_guardrail: `check:miniapp` 现在直接覆盖属性值内含 `>` 的真实 WXML；反向验证仍能识别真正未闭合的 `<view>`，不得再以改写表达式为绕过手段。
- verification: 临时插入未闭合 `<view>` 后 `npm run check:miniapp` 退出码 1 并报 `pages/checkout/index.wxml leaves <view> from line 209 unclosed`；移除后 `npm run check:miniapp` 退出码 0（15 页 15 路由），含 `pointsBalance > 0` 与 `balanceFen > 0` 的模板通过；`node --check` 两个脚本通过。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `miniapp/scripts/check-miniapp.mjs`; `miniapp/miniprogram/pages/checkout/index.wxml`
- next_time_signal: WXML 解析不要用 `[^>]*` 这类不识别引号的简化正则；标签属性允许包含 `>`，扫描器必须带引号状态。

## M-20260913-099：结算页已登录时误现返回按钮，零资产抵扣项呈现禁用空胶囊

- status: guarded
- first_seen: 2026-09-13
- severity: low
- symptom: `final-checkout-zero-assets.png` 中已登录会话提示右侧出现深色“返回”主按钮，语义像登出或退回；`final-checkout-state-quoted.png` 中零积分、零余额两行各有一个浅色空胶囊，既看不出是开关也看不出不可用原因。
- root_cause: 会话提示的 `action-text` 只按登录状态切换文案，没有取消已登录时的动作；抵扣行则始终渲染 `<switch disabled>`，仅在无资产时降低透明度，导致禁用控件仍占据视觉焦点。
- impact: 顾客可能误把身份说明当成需要执行的返回操作，也会把不可用开关当成加载失败或空白占位；重复点击只会得到 toast，增加结算页理解成本。
- fix: 结算页已登录时 `action-text` 传空字符串，会话提示不再渲染动作按钮；积分、余额为零且未锁单时不渲染 switch，只保留“暂无可用积分/余额”的明确说明，整行点击仍给出原因提示。
- new_guardrail: `verify-devtools-commerce-states.cjs` 的 `zero-member-assets` 断言扩展为 `pointsSwitchVisible=false`、`balanceSwitchVisible=false`、`sessionActionVisible=false`，同时要求抵扣区仍包含“暂无可用积分”和“暂无可用余额”。
- verification: `npm run check:miniapp`、`npm run typecheck`、`node --check` 均通过；`npm run devtools:commerce-states` 退出码 0，报告记录三项可见性均为 false 且 `benefitText` 保留两条不可用说明；`npm run devtools:checkout-delivery-states` 退出码 0，重生成的 `final-checkout-state-quoted.png` 目视确认两行只剩文字说明，`final-checkout-zero-assets.png` 确认“返回”按钮消失。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `miniapp/miniprogram/pages/checkout/index.wxml`; `miniapp/miniprogram/pages/checkout/index.ts`; `miniapp/scripts/verify-devtools-commerce-states.cjs`
- next_time_signal: 不可执行的控件不要只做 disabled 降透明度；零资产、空列表这类状态应优先用文字说明替代无效控件，并同步补运行态可见性断言。

## M-20260913-100：触控扫描连接失败仍写入失败报告并覆盖上一份通过证据

- status: guarded
- first_seen: 2026-09-13
- severity: low
- symptom: 未设置 `MINIAPP_AUTOMATOR_WS` 时执行 `npm run scan:button-touch-targets`，开发者工具自动端口启动失败；脚本仍写入 `button-touch-targets-20260912-164125.json`（`status=fail`、`0 selectors across 0 pages`）并覆盖 `button-touch-targets-latest.json`，但 39 个选择器实际一个都未扫描。
- root_cause: 连接异常被写入 `report.error` 后，主流程仍在 `finally` 之后无条件生成时间戳报告并覆盖 latest；没有区分“环境未就绪”与“页面控件真实失败”。
- impact: DevTools 未开自动化端口会被误读成触控目标批量回归，且上一份有效 PASS 证据被 0 选择器失败报告覆盖，与 M-20260912-091 属于同一类证据完整性问题。
- fix: 在写报告前检查 `report.error`；连接/启动失败时输出具体原因与 `MINIAPP_AUTOMATOR_WS=ws://127.0.0.1:9420` 提示，退出码 2，不写时间戳报告也不覆盖 latest。
- new_guardrail: 运行态扫描的环境/连接失败必须保留上一份有效报告；只有成功建立自动化会话并完成页面采样后，才允许写入 pass/fail 结果。
- verification: 反向验证前 latest SHA256 `63594F9B4071358FE3C2B93B0DE549A2950F833FE6188B3FD72AB87D0775836D`、mtime `2026-09-12T16:42:36.3152180Z`；无端口执行后打印 `aborted without writing a report`，直接运行脚本 `exit_code=2`，哈希与 mtime 均未变化；带 `MINIAPP_AUTOMATOR_WS=ws://127.0.0.1:9420` 复跑输出 `pass: 39 selectors across 10 pages`，报告 `button-touch-targets-20260912-164811.json`。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `miniapp/scripts/scan-miniapp-button-touch-targets.mjs`; `miniapp/reports/button-visual/button-touch-targets-latest.json`
- next_time_signal: 运行态审计脚本出现 `0 selectors across 0 pages` 时，先判断是环境连接失败还是选择器失败；环境失败不得写报告或覆盖上一份有效证据。

## M-20260913-101：证据索引 result 使用未允许复合值，索引门禁在收口时失败

- status: guarded
- first_seen: 2026-09-13
- severity: low
- symptom: r30 收口执行 `python -B backend/scripts/check_evidence_index.py` 时输出 `E-20260913-001: invalid result pass_with_external_blocker`，索引本身 `malformed=1`、整体状态 failed。
- root_cause: 新增 r29 证据条目把机器字段 `result` 写成描述性复合值 `pass_with_external_blocker`，而检查器只允许 `pass`、`fail`、`partial`、`partial-pass` 四个枚举值。
- impact: 文件完整、内容可读的证据仍会让索引门禁失败并阻断收口，降低真实 malformed 条目的可辨识度。
- fix: 将 E-20260913-001 的 `result` 改为 `partial`；外部证书阻塞继续保留在同条目的 `residual_risks` 中，不把复合语义塞进机器枚举。
- new_guardrail: 证据条目 `result` 必须使用固定枚举；收口必须执行专项 `check_evidence_index.py`，不能只依赖汇总质量门禁。
- verification: 修正后 `python -B backend/scripts/check_evidence_index.py --summary` 输出 `status=passed total=437 failed=0 malformed=0`；`python -B backend/scripts/check_mistake_ledger.py` 输出 `[mistake-ledger] ok entries=135`。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `docs/harness-engineering/core/evidence-index.md`; `backend/scripts/check_evidence_index.py`; `ERRORS.md`
- next_time_signal: 证据索引机器字段不要写 `pass_with_...`、`done_but_...` 之类复合状态；枚举字段只填允许值，补充说明放 `summary`、`residual_risks` 或 `failure_class`。

## M-20260913-102：门店自提地址默认值是占位文案，结算页与闪送报价起点拿到错误地址

- status: guarded
- first_seen: 2026-09-13
- severity: high
- symptom: 本地 `GET /api/v1/miniapp/shop-settings` 返回 `pickupAddress=门店自提，具体地址请联系客服确认`；结算页“自提门店”直接展示这句占位文案，`requestDeliveryQuote()` 与 `createOrder()` 也把它当作闪送取货起点。
- root_cause: 后端 `DEFAULT_SHOP_OPERATIONS["pickupAddress"]` 写的是客服提示文案而不是真实门店地址；小程序兜底只判断空串，占位文案非空因此绕过回落 `config/shop.ts`；本地 `shop_config` 表没有保存该键（只有 `youzan_access_token` 与 `featured_products`），说明问题来自默认值而不是后台误存。
- impact: 顾客在结算页看不到真实到店地址；北京闪送报价起点不是北京市东城区南竹杆胡同2号银河SOHO，会按错误起点计算距离与运费，并把错误取货点写入订单快照。
- fix: 后端新增 `DEFAULT_PICKUP_ADDRESS` 与 `PICKUP_ADDRESS_PLACEHOLDER_MARKERS`，默认运营配置改回真实门店地址；`ShopOperationsService.get_shop_operations()`/`set_shop_operations()` 经 `resolve_pickup_address()` 把空值和含“请联系客服确认”的历史占位值统一归一化；小程序 `config/shop.ts` 新增 `resolvePickupAddress()`，由 `services/shop-settings.ts` 与结算页 `getPickupAddressForQuote()` 共用，结算页 `pickupAddress` 初值改为 `SHOP_CONFIG.pickupAddress`；管理后台默认设置同步为真实地址；契约示例中的旧地址一并修正。
- new_guardrail: `check-miniapp.mjs` 的 `checkPickupAddressSourceOfTruth()` 新增两项：小程序源码不得出现占位地址文案“具体地址请联系客服确认”；`backend/app/models/config.py` 的 `DEFAULT_PICKUP_ADDRESS` 与 `backend/web/admin/src/services/shopSettings.ts` 的默认 `pickupAddress` 必须与 `config/shop.ts` 完全一致。`verify-devtools-checkout-delivery-states.cjs` 新增 `pickup_address_source` 运行态断言，要求结算页自提文案与页面数据都等于真实门店地址。
- verification: 后端 `pytest tests/api/test_shop_operations_api.py tests/api/test_miniapp_delivery_api.py tests/service/delivery/test_order_quote_binding.py -q --no-cov` 14 passed（新增默认地址、历史占位归一化、后台保存占位回落三条用例）；重启本地后端后 `GET /api/v1/miniapp/shop-settings` 返回 `北京市东城区南竹杆胡同2号银河SOHO`；`npm run check:miniapp`（15 页 15 路由）与 `npm run typecheck` 通过；`npm run devtools:checkout-delivery-states` PASS，报告 `pickup_address_source` 记录 `pickupNoticeText` 与 `dataPickupAddress` 均为真实门店地址，截图 `final-checkout-pickup-address.png` 目视确认；`npm run devtools:commerce-states` PASS。反向验证：临时在小程序源码写入占位文案并把后端 `DEFAULT_PICKUP_ADDRESS` 改成错误地址后，`check:miniapp` 退出码 1 并分别报出两条断言；恢复后重新通过。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `backend/app/models/config.py`; `backend/app/service/shop_operations.py`; `backend/tests/api/test_shop_operations_api.py`; `miniapp/miniprogram/config/shop.ts`; `miniapp/miniprogram/services/shop-settings.ts`; `miniapp/miniprogram/pages/checkout/index.ts`; `backend/web/admin/src/services/shopSettings.ts`; `miniapp/docs/api-contract.md`; `miniapp/scripts/check-miniapp.mjs`; `miniapp/scripts/verify-devtools-checkout-delivery-states.cjs`
- next_time_signal: 运营配置里的地址字段要区分“真实履约地址”和“客服提示文案”；默认值与历史值都要在服务端归一化，前端只做最后一道兼底，并用静态门禁校验前后端地址默认值一致。

## M-20260913-103：交互控件用 84rpx/76rpx 作高度基线，低于 44px 最小触控尺寸

- status: guarded
- first_seen: 2026-09-13
- severity: medium
- symptom: DevTools 390px 视口实测群内登记页履约切换标签 162x43、三个时间选择器 333x43/162x43/162x43；购物车步进器（−/+）24x24、窄屏媒体查询把“去结算”压到 124x39；优惠券与积分页未登录“去登录”按钮 104x43。均低于微信与 iOS HIG 的 44px 最小可点区域，`verify-devtools-registration-policy.cjs` 首轮因此报 `registration_touch_targets` 失败。
- root_cause: 多个页面把 `min-height: 84rpx` 当作控件高度基线，而 rpx 随屏宽缩放（390px 视口下 84rpx=43.68px），设备越窄越小；购物车窄屏媒体查询又把 `88rpx` 回退到 `76rpx`，步进器沿用 `48rpx` 圆形按钮；既有 `scan-miniapp-button-touch-targets` 只覆盖 10 页 39 个选择器，未包含购物车、优惠券、积分和群内登记页。
- impact: 顾客在切换履约方式、选择预订时间、调整购物车数量、进入结算或登录时容易点不中；属于核心下单链路的可用性缺陷，小屏设备上命中率明显下降。
- fix: 群内登记页 `.fulfillment-tab`/`.time-picker`、购物车 `.stepper-btn` 与窄屏 `.cart-footer .primary-button`、优惠券/积分 `.primary-btn` 统一改为 `88rpx`（390px 视口 45px）；群内登记页输入框、提交按钮与返回控件保持 88rpx 基线。
- new_guardrail: `scan-miniapp-button-touch-targets.mjs` 新增 cart / coupons-login-gate / points-login-gate 三个注入态，覆盖面扩到 13 页 46 个选择器，任一控件低于 44px 即失败；`verify-devtools-registration-policy.cjs` 的 `registration_touch_targets` 把群内登记页输入框、选择器、履约标签、提交按钮与返回控件全部纳入 44px 校验。
- verification: `npm run devtools:registration-policy` PASS（pickers 与 tabs 均为 45px，`registration_touch_targets` 通过）；带 `MINIAPP_AUTOMATOR_WS=ws://127.0.0.1:9420` 的 `scan:button-touch-targets` PASS（46 选择器/13 页面，新增 cart、coupons-login-gate、points-login-gate 全部 ok）；`devtools:verify-all-pages` 15/15 PASS；`check:miniapp` 15 页 15 路由、`typecheck`、`audit:buttons` 106 控件、`audit:button-styles` 106 控件 0 失败；`final-cart-touch-targets.png` 目视确认放大后的步进器与结算按钮未挤压购物车行。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `miniapp/miniprogram/pages/group-registration/index.wxss`; `miniapp/miniprogram/pages/cart/index.wxss`; `miniapp/miniprogram/pages/coupons/index.wxss`; `miniapp/miniprogram/pages/points/index.wxss`; `miniapp/scripts/scan-miniapp-button-touch-targets.mjs`; `miniapp/scripts/verify-devtools-registration-policy.cjs`
- next_time_signal: 看到 `84rpx`/`76rpx` 作为交互控件高度时先换算 `rpx × 屏宽 / 750`；390px 视口下 84rpx=43.68px 已低于 44px，交互控件一律从 88rpx 起，窄屏媒体查询不得再回退到 76rpx 以下。

## M-20260913-104：微信原生 disabled 样式覆盖自定义主按钮，禁用 CTA 可读性不足

- status: guarded
- first_seen: 2026-09-13
- severity: medium
- symptom: 结算页未同意协议时禁用按钮目视几乎不可读，DevTools 实测仍是微信原生的 `color=rgba(0, 0, 0, 0.18)`、`background=rgb(250, 250, 250)`；充值页自定义金额输入框在 390px 视口仅 259x22px，只有浅色下划线，输入区域和触控目标都不明确。
- root_cause: 微信原生 `button[disabled]` 的样式优先级高于普通 `.primary-button[disabled]`，自定义禁用态看似存在却未落屏；稳定输入控件需要显式高度、边框、背景和单位容器，原有 `padding` 下划线写法无法保证 44px 触控基线。既有审计只检查按钮尺寸与存在性，没有读取 DevTools 实际计算色值，也没有覆盖充值页自定义输入结构。
- impact: 顾客在结算被协议阻断、充值提交中或客服发送未就绪时容易误判为空白/不可用控件；充值金额输入缺少可见边界和完整触控区域，降低输入完成率与页面可信度。
- fix: `.primary-button[disabled]` 与充值页 `.primary-btn[disabled]` 统一改为暖灰底 `--yunxi-surface-alt`、深灰文字 `--yunxi-text-secondary`、可见边框并显式 `!important`；充值自定义金额改为 88rpx 的 `custom-input-wrap`，输入框与“元”单位对齐，placeholder 使用统一的 muted 色；客服发送按钮继续使用同一暖色禁用态。
- new_guardrail: `verify-all-15-pages-devtools.cjs` 新增运行态 `interactionStates` 断言：充值容器和输入框高度均不得低于 44px、必须存在可见背景与细边框、单位不得越界或与输入控件重叠；结算主按钮与客服发送按钮读取实际计算颜色并要求禁用态对比度不低于 4.5:1。`node --check`、静态按钮审计与 DevTools 15 页走查均纳入收口。
- verification: `npm run devtools:verify-all-pages` PASS（15/15）；充值输入容器/输入框均为 259x45px，充值提交、结算提交、客服发送禁用态实际对比度均为 5.48:1，结算按钮计算色值为 `rgb(102, 94, 88)`/`rgb(241, 238, 232)`；`devtools:registration-policy` PASS；`scan:button-touch-targets` PASS（46 选择器/13 页面）；`devtools:commerce-states`、`devtools:checkout-delivery-states`、`devtools:verify-commerce-flows` 均 PASS；`check:miniapp`、`typecheck`、`audit:buttons`（106 控件）、`audit:button-styles`（106 控件 0 失败）均通过；截图 `final-recharge.png`、`final-checkout.png`、`final-chat.png` 目视确认。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `miniapp/miniprogram/app.wxss`; `miniapp/miniprogram/pages/recharge/index.wxml`; `miniapp/miniprogram/pages/recharge/index.wxss`; `miniapp/miniprogram/pages/chat/index.wxss`; `miniapp/scripts/verify-all-15-pages-devtools.cjs`
- next_time_signal: 小程序按钮禁用态不能只按普通 CSS 权重验证；必须读取 DevTools 实际计算样式并显式覆盖微信原生 `!important`。输入控件要同时验证容器高度、可见背景/边框、单位对齐和 44px 触控基线，不能只看元素是否存在。

## M-20260913-105：未登录受限页面只给顶部会话提示，主体整屏空白且引导不统一

- status: guarded
- first_seen: 2026-09-13
- severity: medium
- symptom: 清除微信登录存储后进入订单、收货地址、订单详情页，页面只有一条 `session-notice` 状态卡片，下方整屏空白；同一时刻的优惠券、积分、充值页却是居中空态，同一类“需要登录”场景在两套表达之间摇摆。首版统一空态后又实测到说明文案在 390px 视口换行，末尾只剩一个“券”字。
- root_cause: `session-notice` 组件定位是“顶部状态提示”，却被直接当成整页登录门槛使用；订单/地址/订单详情页的业务分支全部由 `loggedIn` 控制，未登录时没有任何后续分支，于是渲染出空页面。空态说明文案又没有按 `.yunxi-state__hint` 的 480rpx 最大宽度控制字数，长句必然折行。
- impact: 顾客在受限页面面对近空白页面，既不知道下一步做什么，也看不到登录后的收益；与已在购物车、结算、商品页建立的 `.yunxi-state` 空态语言冲突，页面显得未完成。
- fix: 7 个受限页面（orders/address/order-detail/coupons/points/recharge/checkout）统一改为 `.yunxi-state yunxi-state--page` 整页空态：图标 + 标题 + 单行说明 + “去登录”按钮，垂直居中；订单/地址/订单详情/结算页移除不再使用的 `session-notice` 注册，首页顺带清掉未使用的组件注册。
- new_guardrail: `verify-all-15-pages-devtools.cjs` 新增 `inspectLoginGate()`：对受限页注入确定性未登录态，断言图标/标题/说明/“去登录”按钮齐全、按钮不小于 48x44px、空态高度不低于 260px、说明文案不得换行（按计算行高判定），且不得同时渲染受限业务内容；`captureLoggedOutStates()` 覆盖页面从 7 个扩到 8 个（新增结算页）。
- verification: `npm run devtools:verify-all-pages` PASS（15/15 页面 + 8/8 确定性未登录态）；8 个空态实测 362~366x490px，“去登录”按钮 79x45px，说明文案高度均为 20px（单行），`final-logged-out-orders.png`、`final-logged-out-checkout.png` 等截图目视通过；`check:miniapp`、`typecheck`、`audit:buttons`（110 控件）、`audit:button-styles`（110 控件 0 失败）、`scan:button-touch-targets`（46 选择器/13 页面）均通过。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `miniapp/miniprogram/app.wxss`; `miniapp/miniprogram/pages/orders/index.wxml`; `miniapp/miniprogram/pages/address/index.wxml`; `miniapp/miniprogram/pages/order-detail/index.wxml`; `miniapp/miniprogram/pages/coupons/index.wxml`; `miniapp/miniprogram/pages/points/index.wxml`; `miniapp/miniprogram/pages/recharge/index.wxml`; `miniapp/miniprogram/pages/checkout/index.wxml`; `miniapp/scripts/verify-all-15-pages-devtools.cjs`
- next_time_signal: 需要登录才能使用的整页场景，不要复用顶部提示条；统一用带图标、标题、说明和唯一 CTA 的整页空态，并对空态做运行态几何与换行断言。空态说明按 480rpx 宽度控制在 18 个汉字以内，避免单字折行。

## M-20260913-106：无可用优惠券时仍显示下拉箭头，点开是空面板

- status: guarded
- first_seen: 2026-09-13
- severity: low
- symptom: 结算页会员权益区在 `availableCoupons.length === 0` 时仍显示“优惠券 暂无可用 ▼”，点击后展开一个只写着“暂无可用优惠券”的空面板。
- root_cause: 优惠券行统一绑定 `toggleCouponPanel`，箭头也只看 `showCouponPanel` 状态，没有按“有没有可选项”区分可点与纯信息两种形态。
- impact: 顾客看到可点的下拉暗示却点出空面板，属于典型的伪交互，降低结算页可信度，也浪费一次点击。
- fix: 无可用券时行文案改为 muted 的“暂无可用”，隐藏下拉箭头、取消按下反馈（`.benefit-row--static`），`toggleCouponPanel()` 直接短路并回收可能残留的展开态。
- new_guardrail: `verify-all-15-pages-devtools.cjs` 的 `interactionStates` 新增结算页优惠券断言：注入零可用券后，行文案必须包含“暂无可用”、不得存在 `.benefit-arrow`、点击后不得出现 `.coupon-panel`。
- verification: `npm run devtools:verify-all-pages` PASS，报告记录 `优惠券行：暂无可用；无下拉箭头=true；点击未展开=true`；`devtools:commerce-states`、`devtools:checkout-delivery-states`、`devtools:verify-commerce-flows` 均 PASS。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `miniapp/miniprogram/pages/checkout/index.wxml`; `miniapp/miniprogram/pages/checkout/index.ts`; `miniapp/miniprogram/pages/checkout/index.wxss`; `miniapp/scripts/verify-all-15-pages-devtools.cjs`
- next_time_signal: 任何“点击展开/跳转”的入口都要区分“有可选项”和“空结果”两种形态；空结果只做信息展示，不保留箭头、按下反馈或空面板。

## M-20260913-107：审计播种结算态未还原登录标志，污染后续按钮扫描与未登录断言

- status: guarded
- first_seen: 2026-09-13
- severity: low
- symptom: 把结算页纳入“清除登录存储”确定性未登录清单后，审计报出 `pages/checkout/index: 清除登录存储后页面仍显示已登录会话`；同一轮按钮扫描把“去选购”当成登录闸门 CTA，而结算页截图与 `loginGate` 断言都显示未登录空态正常。
- root_cause: `inspectFormFieldLabels()` 在没有表单字段时会把结算页播种为 `isLoggedIn: true` + 假商品以校验常驻标签，收尾只还原 `checkoutItems: []`，漏掉 `isLoggedIn`。主审计阶段截图早于该播种步骤，问题历史上未暴露；新增的未登录阶段在同页面做状态断言，才把泄漏状态读出来。
- impact: 审计脚本会留下与真实会话不一致的页面状态，使按钮扫描、未登录断言和截图口径互相矛盾，容易把测试脚手架缺陷当成产品缺陷反复排查。
- fix: 播种前记录 `isLoggedIn` 与 `checkoutItems` 原值，收尾用整对象一次性还原；注释明确播种态登录标志也必须还原。
- new_guardrail: `verify-all-15-pages-devtools.cjs` 的结算页确定性未登录断言与按钮扫描共享同一份状态；播种态还原后，主阶段 15/15 与未登录阶段 8/8 必须同时通过。
- verification: `npm run devtools:verify-all-pages` PASS（15/15 页面；未登录态 8/8）；结算页未登录态按钮仅剩返回与“去登录”（79x45px），`errors` 为空。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `miniapp/scripts/verify-all-15-pages-devtools.cjs`
- next_time_signal: 自动化脚本播种 UI 状态时必须成对还原全部被改字段；新增页面级断言前先确认该页面是否已被其他审计步骤播种，避免跨步骤状态泄漏造成假失败。

## M-20260913-108：门店自提订单沿用配送口径，展示闪送费与配送地址且缺少自提门店

- status: guarded
- first_seen: 2026-09-13
- severity: medium
- symptom: 目视复核订单列表与订单详情截图发现，选择门店自提的订单仍显示“闪送费”金额行，详情页出现“配送地址”而不显示自提门店地址，进度节点统一写“配送中”，与北京闪送履约完全同形。
- root_cause: 订单序列化只返回配送地址，没有自提地址快照；订单列表与详情页按“有配送信息即配送单”的默认分支渲染，进度文案写死在订单状态上，未按履约方式分叉。
- impact: 自提客户会看到本不存在的配送费用和地址，无法从订单页确认到店取货地点与取货时段，履约信息与实付金额互相矛盾，容易引发客服追问和退款争议。
- fix: `OrderSerializationService` 增加 `pickupAddress` 快照返回，`OrderSummary` 契约补字段；订单列表按履约方式改文案（“到店自提 · 联系人”/“北京闪送 · 收货人”、“预约取货”/“期望配送”）；订单详情自提单隐藏闪送费行、显示“自提门店”与快照地址、仅配送单显示“配送地址”，进度节点按履约方式区分“配送中”与“待取货”，并为待确认/制作/完成/取消各状态补齐对应文案。
- new_guardrail: `verify-miniapp-commerce-flows.cjs` 增加配送/自提两种订单详情语义断言；`verify-devtools-commerce-states.cjs` 增加履约信息可读性断言；`check-miniapp.mjs` 新增 `checkOrderFulfillmentPresentation()`，禁止自提单渲染闪送费用与配送地址。
- verification: `python -B -m pytest backend/tests/service/delivery/test_order_quote_binding.py -q --no-cov` 6/6 PASS；`backend/tests/api/test_miniapp_order_api.py -q --no-cov` 14/14 PASS；`npm run devtools:verify-commerce-flows` 与 `devtools:commerce-states` PASS，并输出 `commerce-flow-order-detail.png`、`commerce-flow-order-detail-pickup.png` 逐页目视确认。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `backend/app/service/order/serialization.py`; `miniapp/miniprogram/services/orders.ts`; `miniapp/miniprogram/pages/orders/index.ts`; `miniapp/miniprogram/pages/orders/index.wxml`; `miniapp/miniprogram/pages/order-detail/index.ts`; `miniapp/miniprogram/pages/order-detail/index.wxml`; `miniapp/docs/api-contract.md`; `miniapp/scripts/check-miniapp.mjs`
- next_time_signal: 任何履约方式分叉（自提/闪送/快递）都要从数据契约到列表、详情、进度、费用四个展示点整体核对；只按订单状态渲染会漏掉费用与地址口径。

## M-20260913-109：商品详情首图重复渲染销量角标，与元信息销量重复

- status: guarded
- first_seen: 2026-09-13
- severity: low
- symptom: 商品详情首图左上角浮层与标题下方元信息同时显示同一销量文案，同一事实在一屏内出现两次。
- root_cause: 早期为提升首图信息密度加了 `detail-sold-flag` 浮层，后续元信息已补齐销量字段但浮层未同步移除。
- impact: 首图被角标遮挡且信息重复，削弱商品图作为第一视觉主体的作用，与“商品优先”展示原则冲突。
- fix: 删除商品详情首图的 `detail-sold-flag` 节点及样式，销量只在元信息保留一处。
- new_guardrail: 商品详情展示走查核对销量文案单次出现，首图不再叠加营销角标。
- verification: `npm run devtools:verify-commerce-flows` PASS；`final-product-detail.png` 与 `commerce-flow-detail.png` 目视确认首图无角标、销量仅在元信息出现一次。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `miniapp/miniprogram/pages/product-detail/index.wxml`; `miniapp/miniprogram/pages/product-detail/index.wxss`
- next_time_signal: 新增首图浮层前先确认该信息是否已在元信息中存在；商品图优先保证无遮挡展示。

## M-20260913-110：已登录订单为空时只有裸空态，没有下一步动作

- status: guarded
- first_seen: 2026-09-13
- severity: low
- symptom: 已登录但无订单时，订单页只显示一句“暂无订单”，整屏无入口；同期未登录路径已统一为整页登录引导空态，两种空态表达不一致。
- root_cause: 订单页空态是登录闸门改造前的早期实现，只覆盖未登录分支，漏掉“已登录但为空”这一状态。
- impact: 老客户首次进入订单页看不到任何可执行动作，只能返回或猜测入口，与商品优先的浏览动线脱节。
- fix: 订单页已登录空态复用 `.yunxi-state yunxi-state--page` 结构，补图标、标题、说明与“去选购”按钮，`goProducts()` 使用统一路由常量并加存在性保护。
- new_guardrail: `verify-devtools-commerce-states.cjs` 增加已登录空订单断言（结构、CTA 文案、触控尺寸、受限内容不渲染）；`scan-miniapp-button-touch-targets.mjs` 纳入该空态按钮。
- verification: `npm run devtools:commerce-states` PASS，报告与 `final-orders-empty.png` 目视确认空态居中、CTA 可见；触控扫描 46 选择器/13 页面 PASS。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `miniapp/miniprogram/pages/orders/index.wxml`; `miniapp/miniprogram/pages/orders/index.ts`; `miniapp/miniprogram/pages/orders/index.wxss`; `miniapp/scripts/verify-devtools-commerce-states.cjs`
- next_time_signal: 空态必须覆盖“未登录”“已登录但为空”“加载失败”三种来源，且每种都要有一个明确下一步动作。

## M-20260913-111：app.json 与自定义 tabBar 标签不一致，同一入口出现两个名称

- status: guarded
- first_seen: 2026-09-13
- severity: low
- symptom: 自定义 tabBar 显示“商品”“我的”，而 `app.json` 声明为“全部分类”“会员中心”；同一 tab 在页面配置与渲染结果中名称不同。
- root_cause: 引入自定义 tabBar 后只维护了 `constants/tab-bar.ts` 文案，`app.json` 的原生声明未同步，且缺少一致性门禁。
- impact: 名称漂移会同时影响无障碍朗读、系统级导航提示和后续页面跳转文案，破坏导航语言一致性。
- fix: `app.json` 的 tabBar 文案统一为“商品”“我的”，与 `constants/tab-bar.ts` 对齐。
- new_guardrail: `check-miniapp.mjs` 新增 `checkTabBarLabels()`，逐项比对自定义 tabBar 路由与 `app.json` 文案，不一致即失败。
- verification: `npm run check:miniapp` PASS（15 页 / 15 路由）；`npm run devtools:verify-all-pages` PASS。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `miniapp/miniprogram/app.json`; `miniapp/miniprogram/constants/tab-bar.ts`; `miniapp/scripts/check-miniapp.mjs`
- next_time_signal: 自定义 tabBar 的文案、图标与路由存在两处来源时必须加一致性门禁，不能只靠人工核对页面截图。

## M-20260913-112：重新进入结算页后时间选择器与提交的期望时间不一致

- status: guarded
- first_seen: 2026-09-13
- severity: high
- symptom: 结算页三个时间选择器（日期/小时/分钟）显示值与“期望时间”提交值不一致：目视复核截图出现选择器显示 2026-09-13 18:00、下方期望时间却为 2026-09-15 15:00。
- root_cause: `loadCheckout()` 每次 onShow 都用 `selectedHourIndex: getDefaultCheckoutHourIndex(hourOptions)` 重置小时、且从不还原分钟索引，但 `expectTime` 保留用户已选值；选择器与提交值各算一套。
- impact: 客户改完配送时间后只要离开再返回结算页（如去选地址再回来），界面显示的时段与实际提交给后端的期望时间不同，预订单会按客户没看到的时间排产。
- fix: 新增 `resolveCheckoutSchedule()` 纯函数（`utils/checkout-time.ts`），由提交值反推日期/小时/分钟索引；已过截单日的旧时间自动抬到最早可预约日期；结算页新增 `syncExpectTimeSchedule()` 并在 `loadCheckout()` 中以服务端营业时段调用，选择器与 `expectTime` 共用同一份结果。
- new_guardrail: 新增 `npm run test:checkout-time`（5 项单测覆盖还原、当天保留、过截单日抬升、非法值回落）；`verify-devtools-checkout-delivery-states.cjs` 新增 `expect_time_picker_restore` 运行态断言；`check-miniapp.mjs` 新增 `checkCatalogHeadlineAndScheduleConsistency()` 要求结算页必须经 `syncExpectTimeSchedule` 重建选择器。
- verification: `npm run test:checkout-time` 5/5 PASS；`devtools:checkout-delivery-states` PASS，报告记录 `expectTime=2026-09-13 19:30 / restoredExpectTime=2026-09-13 19:30 / restoredHour=19 / restoredMinute=30`（种子索引对应 09:00，证明按提交值还原而非默认值）。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `miniapp/miniprogram/utils/checkout-time.ts`; `miniapp/miniprogram/pages/checkout/index.ts`; `miniapp/tests/utils/checkout-time.test.ts`; `miniapp/scripts/verify-devtools-checkout-delivery-states.cjs`; `miniapp/scripts/check-miniapp.mjs`; `miniapp/package.json`
- next_time_signal: 任何“选择器 + 汇总文案 + 提交值”三方存在的表单，都要用单一函数从提交值反推控件状态；重新进入页面时必须重算，不能沿用按钮默认值。

## M-20260913-113：登录后优惠券/积分空态缺少下一步动作，与订单页空态不一致

- status: guarded
- first_seen: 2026-09-13
- severity: low
- symptom: 登录后优惠券页只有“暂无可用优惠券”一行字、积分页只有标题加副标题，均无入口；同一 App 内订单页已是图标+标题+说明+“去选购”的整页空态。
- root_cause: 早期 `.empty-panel` 与后来的 `.yunxi-state` 两套空态并存，登录闸门改造只覆盖了未登录分支，已登录空结果与加载失败未同步升级。
- impact: 客户看到空结果后没有可执行动作，只能返回或猜测入口；同类场景多套表达也会让产品显得拼凑。
- fix: 优惠券/积分页的空结果与加载失败均改用 `.yunxi-state yunxi-state--page`，失败态补“重新加载”、空态补“去选购”；两页新增 `retryLoad()` 与 `goProducts()`，登录跳转改用 `ROUTES` 常量。
- new_guardrail: `verify-devtools-commerce-states.cjs` 新增 `logged-in-empty-coupons` 与 `logged-in-empty-points` 运行态断言（空态结构、标题文案、去选购按钮、44px 触控）。
- verification: `npm run devtools:commerce-states` PASS，报告记录优惠券“暂无可用优惠券/去选购”、按钮 79x45px；积分“暂无积分记录/去选购”；截图 `final-coupons-empty.png`、`final-points-empty.png` 目视确认。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `miniapp/miniprogram/pages/coupons/index.wxml`; `miniapp/miniprogram/pages/coupons/index.ts`; `miniapp/miniprogram/pages/points/index.wxml`; `miniapp/miniprogram/pages/points/index.ts`; `miniapp/scripts/verify-devtools-commerce-states.cjs`
- next_time_signal: 空态只允许一套结构；新增页面空结果前先看订单页/优惠券页的 `.yunxi-state` 写法，避免又回到裸文本面板。

## M-20260913-114：商品目录标题出现不可交互的“自提价”伪控件与无依据形容词副标题

- status: guarded
- first_seen: 2026-09-13
- severity: low
- symptom: 商品目录标题右侧渲染“自提价”胶囊块，外形与筛选标签一致但点不动；标题副文案为“人气汇聚”“匠心手作”“麦香现烤”“生活美学”等形容词，与真实商品数据无关。
- root_cause: 早期为提升“丰富度”写了分类副标题模板，又应门店价格口径加了静态价格 chip；两者都只是展示文本，未随真实数据演进。
- impact: 客户会把胶囊块当成筛选/切换控件反复点击；形容词副标题会让人误以为有人气榜、手作认证等依据，与“不虚构营销”口径相冲。
- fix: 移除标题区的静态 `products-heading__service` chip 及样式，价格口径只保留门店信息区的“自提价 / 北京闪送｜运费实算”；删除全部形容词副标题，侧栏副标题改为真实商品数“N 款”，标题副文案改为“N 款 · 按销量排序”（列表真实按 sold_num 排序）。
- new_guardrail: `check-miniapp.mjs` 新增 `checkCatalogHeadlineAndScheduleConsistency()`：禁止商品页再出现 `products-heading__service`、禁止“人气汇聚/匠心手作/麦香现烤/层层甜蜜/生活美学”等无依据副标题，并要求标题声明真实排序口径。
- verification: `npm run check:miniapp` PASS（15 页/15 路由）；`devtools:verify-all-pages` PASS（15/15）；`final-products.png` 目视确认标题为“全部商品 / 310 款 · 按销量排序”且无静态胶囊块。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `miniapp/miniprogram/pages/products/index.wxml`; `miniapp/miniprogram/pages/products/index.ts`; `miniapp/miniprogram/pages/products/index.wxss`; `miniapp/scripts/check-miniapp.mjs`
- next_time_signal: 展示层新增的非按钮元素如果长得像筛选/切换控件，就必须真的可点或改成纯文本；副标题只允许放可核验数据。

## M-20260913-115：有赞分类与商品标签命名空间零交集，分类接口恒为空导致目录无分类导航

- status: open
- first_seen: 2026-09-13
- severity: medium
- symptom: `/api/v1/miniapp/product-categories` 返回 `data: []`；本地库 `youzan_product_categories` 有 34 条公开分类，但 310 个在售商品的 `tag_ids_json` 与分类 `tag_id` 零交集，`classification_ids_json` 全为空，分类商品数全部为 0，被 `resolve_public_category()` 全部过滤；商品侧只能按关键词兜底成同一个“蛋糕”。
- root_cause: 分类同步走 `search_item_classifications()`（商品分类命名空间），商品标签走 item tag 命名空间；两者 ID 不同源且 item 接口不返回 classification，现有同步管道没有建立分类与商品的关联表或反向拉取。
- impact: 310 款商品的目录只剩单层列表与搜索，客户无法按用途/品类缩小范围；若后续把该字段当分类展示，还会出现蜡烛、餐具被归入“蛋糕”的误导。
- fix: 待办（需真实有赞接口权限）；可选方向：按 classification 反向分页拉取商品建立关联，或在新同步中落一张分类-商品关系表，再让 `list_public_categories()` 以真实命中数输出。
- new_guardrail: 分类接口返回空数组时商品页不得再渲染静态筛选胶囊或虚构分类名；`check-miniapp.mjs` 已禁止商品页出现无依据分类副标题。
- verification: 本地接口实测 `GET /api/v1/miniapp/product-categories` → `data=[]`；SQL 实测分类 34 条、商品数 310、`tag_ids_json` 与分类 `tag_id` 交集为 0；商品页运行态为单分区列表（`商品分区=1`），标题展示真实“310 款 · 按销量排序”。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `backend/app/repository/youzan_repo.py`; `backend/app/service/catalog/serialization.py`; `backend/scripts/sync_real_products_from_youzan.py`; `miniapp/miniprogram/pages/products/index.ts`
- next_time_signal: 分类/分组类导航上线前，先用 SQL 验证“分类 ID 与商品字段真实相交且命中数大于 0”，不要只看分类表行数就认定分类可用。
- update_20260913: 网关侧根因已由 M-20260913-148 定位（有赞返回 `gw_err_resp` 4007 被当成空数据 + 调用方 IP 未加白名单）；同步入口现会显式失败并不再误清目录，但分类-商品关联仍依赖有赞侧配置 IP 白名单后重跑同步，本条目保持 open。

## M-20260913-116：购物车商品名单行截断，41 字真实商品名只剩一个残句

- status: guarded
- first_seen: 2026-09-13
- severity: medium
- symptom: 购物车 `.cart-title` 使用单行省略，当前在售商品最长名称 41 个汉字（“树莓白色浪漫（树莓库利装饰，不是新鲜树莓，介意慎拍）小双层（上层有一层奥利奥夹心）”）只能显示约 14 字，客户无法从购物车确认具体商品。
- root_cause: 商品名与库存标签同处 `.cart-info__header` 横向竞争，名称被强制 `white-space: nowrap`；而推荐商品卡早已使用两行截断，同一 App 内两种策略不一致。
- impact: 同系列商品的名称前缀相近时（树莓/奥利奥、6 寸/8 寸、备注要求）客户无法在结算前核对规格，容易买错；长名称商品也无法从购物车跳回完整详情。
- fix: 重构购物车信息层级：勾选与商品图组合为左侧核对列，商品名独占信息列并允许两行；库存/购买提示标签移到价格行并与价格成组；商品名与商品图新增 `openProduct` 导航，点击进入完整商品详情；`openProduct()` 增加空商品 ID 保护与 `encodeURIComponent`。
- new_guardrail: 新增 `npm run devtools:cart-long-title`（`verify-devtools-cart-long-title.cjs`）用最长真实商品名向 `cartItems` 播种，断言两行 clamp、标题区宽高、标签与步进器不重叠、点击名称可进入商品详情；`verify-devtools-product-purchase-path.cjs` 增加购物车真实商品两行断言与 `final-cart-real-product.png` 截图。
- verification: `devtools:cart-long-title` PASS（titleLength=41、lineClamp=2、titleSize=278x39、标签/步进器重叠 0）；`devtools:product-purchase-path` PASS（真实商品加入购物车后标题区 278x39、商品卡 370x107）；`devtools:verify-commerce-flows`、`devtools:commerce-states`、`devtools:verify-all-pages`（15/15）均 PASS；`final-cart-long-title.png`、`final-cart-real-product.png` 目视确认。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `miniapp/miniprogram/pages/cart/index.wxml`; `miniapp/miniprogram/pages/cart/index.wxss`; `miniapp/miniprogram/pages/cart/index.ts`; `miniapp/scripts/verify-devtools-product-purchase-path.cjs`; `miniapp/scripts/verify-devtools-cart-long-title.cjs`; `miniapp/package.json`
- next_time_signal: 同一 App 内的列表文字不得各行其是；商品名在购买前核对位最少给两行，且两行仍放不下时必须提供进入完整名称的路径。

## M-20260913-117：购物车长状态标签被数量步进器覆盖，文字与控件重叠

- status: guarded
- first_seen: 2026-09-13
- severity: medium
- symptom: 购物车长名称专项截图显示“自提价展示，闪送费下单前确认”标签直接压在右侧圆形数量步进器下方，文字被控件遮断；标签与控件同一行竞争但没有宽度约束。
- root_cause: `.cart-info__footer` 使用 `space-between`，价格组虽设 `min-width: 0` 但未设 flex 收缩比例，`.tag` 也没有 `max-width` 与溢出省略，在长标签场景下占满整行并与固定宽度步进器重叠。
- impact: 状态标签是“现货/预订/库存上限”的语义来源，被数量控件遮挡后既看不清状态又显得界面损坏；重叠控件在真机上会进一步降低可点性。
- fix: `.cart-price-group` 增加 `flex: 1 1 auto`，价格禁止收缩；`.cart-price-group .tag` 增加 `max-width: 180rpx`、`overflow: hidden`、`text-overflow: ellipsis`、`white-space: nowrap`，长标签在步进器前完整截断。
- new_guardrail: `verify-devtools-cart-long-title.cjs` 增加 `cart-tag-stepper-separation`，计算标签与步进器的矩形交叠，任何同时大于 1px 的横纵重叠直接失败。
- verification: `devtools:cart-long-title` PASS，报告记录标签与步进器重叠为 0；`final-cart-long-title.png` 目视确认标签在圆形步进器左侧截断，不再被覆盖。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `miniapp/miniprogram/pages/cart/index.wxss`; `miniapp/scripts/verify-devtools-cart-long-title.cjs`
- next_time_signal: 同一行放“可变长文本 + 固定宽控件”时，必须给可变长元素设置收缩、上限和溢出策略，不能只靠 `space-between`。

## M-20260913-118：商品列表缓存键漏掉 limit，首页货架条数随访问顺序漂移

- status: guarded
- first_seen: 2026-09-13
- severity: medium
- symptom: 首页“今日推荐”货架商品数在多次审计间出现 4/5/6 三种结果，接口同时刻恒返回 6 条；同一次 DevTools 会话里先访问其他页面再回到首页，条数会变成 4 或 5。
- root_cause: `buildProductsCacheKey()` 只拼 `ids/categoryId/featured/sort`，未包含 `limit`；首页（featured+limit=6）、购物车推荐（featured+limit=4）、商品详情关联（featured+limit=5）共用同一个缓存键，5 分钟 TTL 内谁先请求谁的数据就被后续页面复用。
- impact: 首页货架会缺货般少展示 2 条推荐，网格末行只剩单张卡片；商品详情“搭配推荐”也可能拿到不足条数的列表，属于跨页面数据串用，而非单纯样式问题。
- fix: `buildProductsCacheKey()` 加入 `limit: options.limit ?? 0`，恢复“同一查询参数对应同一缓存”的契约；首页/购物车/详情各自独立缓存。
- new_guardrail: `check-miniapp.mjs` 新增 `checkProductListCacheKeyIncludesLimit()`，静态要求缓存键包含 `limit`；`verify-all-15-pages-devtools.cjs` 新增首页货架条数与 `/api/v1/miniapp/products?featured=true&limit=6` 的运行态交叉校验，并在计数稳定前轮询，避免把渲染中途帧当成失败。
- verification: 修复前审计记录“渲染=5，接口=6”失败；修复后 `devtools:verify-all-pages` PASS（15/15），首页记录“商品数=6；货架条数交叉校验：接口=6，渲染=6”；`npm run typecheck --prefix miniapp`、`npm run check:miniapp --prefix miniapp` 均 PASS。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `miniapp/miniprogram/services/products.ts`; `miniapp/scripts/check-miniapp.mjs`; `miniapp/scripts/verify-all-15-pages-devtools.cjs`
- next_time_signal: 给带参数的列表接口加缓存时，必须让缓存键覆盖所有影响返回条数与顺序的参数；发现同一接口在不同页面返回条数不同，先查缓存键再查接口。

## M-20260913-119：商品详情底部留白写死 220rpx，无安全区机型会多出大片空白

- status: guarded
- first_seen: 2026-09-13
- severity: low
- symptom: `.detail-page` 用固定 `padding-bottom: 220rpx` 顶开固定操作栏；操作栏真实高度是 `100rpx + env(safe-area-inset-bottom)`，在 iPhone 12/13 模拟器（安全区 40px）实测间隙 22.44px，而在无安全区机型上间隙会膨胀到约 62px。
- root_cause: 页面内容留白按早期更高的操作栏尺寸写死，未复用 `app.wxss` 里“安全区 + 固定操作栏高度”的自适应写法（如 `--yunxi-fixed-action-space`）。
- impact: 全面屏与安卓机型底部空隙不一致，长页滚到底后出现与操作栏之间的大片空白，看起来像内容加载不全。
- fix: 改为 `padding-bottom: calc(env(safe-area-inset-bottom) + 140rpx)`，与操作栏同样跟随安全区伸缩，并保留约 40rpx 呼吸间距。
- new_guardrail: `check-miniapp.mjs` 新增 `checkProductDetailFooterSpace()`，要求商品详情内容区底部留白叠加 `env(safe-area-inset-bottom)`；`verify-devtools-product-purchase-path.cjs` 新增 `product-detail-footer-gap`，滚到底后测量最后内容分区与操作栏间隙，小于 0（遮挡）或大于 48px（大片空白）都失败。
- verification: 修改前 `footer-gap` 记录 gap=22.44px（actions 高 92px）；改为自适应后同一审计 PASS，gap=14.44px，操作栏仍完整处于可视区域；`devtools:verify-all-pages` PASS（15/15）。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `miniapp/miniprogram/pages/product-detail/index.wxss`; `miniapp/scripts/check-miniapp.mjs`; `miniapp/scripts/verify-devtools-product-purchase-path.cjs`
- next_time_signal: 任何为固定底栏让位的滚动留白，都必须写成 `安全区 + 底栏真实高度 + 呼吸间距`，禁止对含 `env(safe-area-inset-bottom)` 的底栏使用写死的留白值。

## M-20260913-120：客服页把文字客服写成“与客服通话”，暗示不存在的电话能力

- status: guarded
- first_seen: 2026-09-13
- severity: low
- symptom: 客服页未登录空态提示“请在个人中心登录后与客服通话”，但该页是文字会话页，没有任何拨号或实时语音能力；真实电话入口是个人中心的“客服电话 13240240418”。
- root_cause: 空态文案按早期模板写法沿用“通话”二字，与页面实际能力（文本问答与转人工）不符，也没有在静态门禁里约束客服沟通能力表述。
- impact: 客户会期待可拨打的在线通话，登录后发现只有文字输入框，形成能力误导；与门店真实联系方式（个人中心电话入口）也不一致。
- fix: 客服页未登录提示改为“请在个人中心登录后与客服在线沟通”。
- new_guardrail: `check-miniapp.mjs` 的 `FORBIDDEN_CUSTOMER_COPY` 新增“与客服通话”，任一页面再次出现都直接失败。
- verification: `npm run check:miniapp --prefix miniapp` PASS（15 页/15 路由）；`npm run devtools:verify-all-pages --prefix miniapp` 15/15 PASS，客服页未登录态按新文案渲染。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `miniapp/miniprogram/pages/chat/index.wxml`; `miniapp/scripts/check-miniapp.mjs`
- next_time_signal: 顾客可见文案描述的能力必须在当前页面真实存在；电话入口只放在个人中心的客服电话，文字会话页不得使用“通话”表述。


## M-20260913-121：首页服务承诺卡说明单行截断，并把截单规则写成“17:00 前咨询”

- status: guarded
- first_seen: 2026-09-13
- severity: medium
- symptom: 首页服务承诺卡三项说明字号只有 18rpx 且 `white-space: nowrap`，真机上说明被截断；第三项写成“17:00 前咨询”，把已确认的截单规则弱化成咨询建议。
- root_cause: 承诺卡沿用早期占位文案与单行省略样式，没有与已确认的发货/截单口径对齐，也没有字号与换行守卫。
- impact: 顾客无法在首页读到当天 17:00 截单这一关键下单边界，容易误判当天订单能否受理。
- fix: 第三项改为“当天订单 17:00 截单”，说明字号提升到 22rpx 并允许两行展示（标题 24rpx）。
- new_guardrail: `check-miniapp.mjs` 的 `checkHomePromiseCardReadability()` 校验真实截单文案、禁止 nowrap、禁止“17:00 前咨询”、字号下限 20rpx、必须允许两行；`verify-all-15-pages-devtools.cjs` 运行态校验三项数量、截单文案与最小字号。
- verification: `npm run devtools:verify-all-pages --prefix miniapp` 15/15 PASS；服务承诺说明=当天制作 次日自取或配送 / 运费按地址单独计算 / 当天订单 17:00 截单，最小字号=11px。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `miniapp/miniprogram/pages/home/index.wxml`; `miniapp/miniprogram/pages/home/index.wxss`; `miniapp/scripts/check-miniapp.mjs`; `miniapp/scripts/verify-all-15-pages-devtools.cjs`
- next_time_signal: 首屏承诺类文案必须与已确认的截单、发货、运费口径逐条对齐，并同时约束字号与换行，不能只改字面。

## M-20260913-122：群内登记页把北京闪送写成“门店配送”，且未说明运费由顾客承担

- status: guarded
- first_seen: 2026-09-13
- severity: medium
- symptom: 群内登记页配送方式选项写成“门店配送”，且页面没有任何运费说明，顾客会以为门店包邮或由门店承担运费。
- root_cause: 登记页按早期“门店配送”模板实现，没有跟随已确认的北京闪送履约口径与运费自理规则更新。
- impact: 顾客在群内下单登记时对配送方式与运费承担产生错误预期，增加客服解释成本和纠纷风险。
- fix: 选项改为“北京闪送”，选择闪送时展示“北京同城闪送专送，运费按收货地址实测、由顾客承担，客服确认后告知”。
- new_guardrail: `check-miniapp.mjs` 的 `checkGroupRegistrationDeliveryCopy()` 禁止“门店配送”、要求“北京闪送”与运费说明；`verify-devtools-registration-policy.cjs` 运行态校验 `registration_delivery_copy`。
- verification: `npm run devtools:registration-policy --prefix miniapp` PASS，报告记录“北京闪送”与运费说明；`final-group-registration.png` 目视确认选项文案。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `miniapp/miniprogram/pages/group-registration/index.wxml`; `miniapp/miniprogram/pages/group-registration/index.wxss`; `miniapp/scripts/check-miniapp.mjs`; `miniapp/scripts/verify-devtools-registration-policy.cjs`
- next_time_signal: 履约方式必须使用真实承运口径（北京闪送），并同时说明运费计算方式与承担方，不能只写配送类型。

## M-20260913-123：商品详情滚动后透明悬浮栏导致正文穿透状态栏与返回控件

- status: guarded
- first_seen: 2026-09-13
- severity: medium
- symptom: 商品详情页悬浮栏始终为透明背景，向下滚动后图文详情正文穿透到状态栏与返回控件下方，“5:58”等系统时间与商品描述文字直接重叠。
- root_cause: `.detail-nav` 为了沉浸式大图固定写成 `background: transparent` 且没有滚动状态，页面用 `scroll-view` 承载滚动，缺少滚动到实底的切换逻辑。
- impact: 顶部长文案与系统状态栏文字叠字，属于最显眼的首屏区域渲染缺陷，直接影响商品详情的可信度与可读性。
- fix: `scroll-view` 绑定 `bindscroll="onScroll"`，`scrollTop > 8` 时切换 `detail-nav--solid`（白底 + 细分隔线 + 轻投影），回到顶部恢复透明。
- new_guardrail: `check-miniapp.mjs` 的 `checkProductDetailScrollNav()` 约束绑定、状态字段与不透明背景值；`verify-all-15-pages-devtools.cjs` 在空态下跳过（改由真实商品流程覆盖）；`verify-miniapp-commerce-flows.cjs` 的 `product-detail-scroll-nav` 用真实商品断言首屏透明、滚动实底、回顶复透明。
- verification: `npm run devtools:verify-commerce-flows --prefix miniapp` PASS，`initialNavClass` 无 solid、`scrolledNavClass` 含 `detail-nav--solid`、`scrolledNavBackground=rgb(255, 255, 255)`、`restoredNavClass` 回到透明；截图 `commerce-flow-detail-nav-solid.png` 目视通过。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `miniapp/miniprogram/pages/product-detail/index.wxml`; `miniapp/miniprogram/pages/product-detail/index.wxss`; `miniapp/miniprogram/pages/product-detail/index.ts`; `miniapp/scripts/check-miniapp.mjs`; `miniapp/scripts/verify-miniapp-commerce-flows.cjs`
- next_time_signal: 沉浸式透明导航栏必须配滚动阈值状态；只允许首屏透明，滚动后必须实底，否则正文会与系统状态栏争抢同一区域。

## M-20260913-124：DevTools 自动化用固定等待断言，导致滚动与提交状态假失败

- status: guarded
- first_seen: 2026-09-13
- severity: low
- symptom: 三类假失败：滚动后固定等待 360ms 读到旧的透明悬浮栏；输入后首次点击履约方式被吞；后端批次错误响应超过 2 秒被判定失败。
- root_cause: 断言与交互使用一次性固定等待，没有覆盖小程序 setData 渲染延迟、输入事件抢占与冷启动请求耗时。
- impact: 运行态门禁出现假失败，容易把正常实现误判为缺陷，也会掩盖真缺陷信号。
- fix: 悬浮栏断言改为轮询至目标状态（3s 预算）；履约方式切换按 3 次重试；批次错误响应预算放宽到 8s。
- new_guardrail: `verify-all-15-pages-devtools.cjs` 新增 `waitForDetailNavState()` 轮询助手；`verify-devtools-registration-policy.cjs` 保留重试与预算常量。
- verification: `npm run devtools:verify-all-pages --prefix miniapp` 与 `npm run devtools:verify-commerce-flows --prefix miniapp` 均 PASS。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `miniapp/scripts/verify-all-15-pages-devtools.cjs`; `miniapp/scripts/verify-devtools-registration-policy.cjs`
- next_time_signal: DevTools 断言必须轮询到目标状态或显式重试，不用固定 sleep 判定异步渲染与外部请求结果。


## M-20260913-125：购物车状态胶囊塞入长运费口径，被省略号截成“自提价展示，闪…”

- status: guarded
- first_seen: 2026-09-13
- severity: low
- symptom: 购物车商品卡的状态胶囊复用了商品卡购买提示，库存充足时渲染“自提价展示，闪送费下单前确认”，在窄胶囊内被截断为“自提价展示，闪…”，运费口径实际不可读。
- root_cause: `getCartStockText()` 在库存充足分支直接调用 `getProductPurchaseHint()`，把商品列表用的长文案塞进购物车专用短胶囊，而胶囊带 `max-width` 与省略号；原有门禁只覆盖标签与数量控件不重叠，没有覆盖文案长度与截断。
- impact: 顾客在购物车核对阶段读到断句，既拿不到完整的运费说明，也让卡片看起来像渲染故障；配件等真实商品同样会触发。
- fix: 库存充足分支改用 `getProductAvailabilityLabel()` 输出短事实（现货/仅余 N 件等），无额外事实时返回空串；WXML 胶囊改为 `wx:if="{{item.stockText}}"` 条件渲染；长运费口径保留在购物车底部“商品合计 · 不含闪送费”。
- new_guardrail: `check-miniapp.mjs` 新增 `checkCartTagCopy()`（禁止 `getCartStockText` 直接调用长购买提示、要求短事实标签、要求胶囊条件渲染）；`verify-devtools-cart-long-title.cjs` 新增 `cart-healthy-stock-tag`（库存充足时不得出现长胶囊）与 `cart-low-stock-tag`（低库存必须输出“仅余 3 件”且与数量控件零重叠）。
- verification: `npm run devtools:cart-long-title --prefix miniapp` PASS（healthy tagHidden=true；low stock “仅余 3 件” 46x16px；重叠 X=-35.9px 无重叠；长名仍为两行 278x39px；点击商品名进入详情）；`npm run devtools:verify-commerce-flows --prefix miniapp` PASS；`check:miniapp`、`typecheck` PASS；`final-cart-long-title.png` 目视确认。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `miniapp/miniprogram/pages/cart/index.ts`; `miniapp/miniprogram/pages/cart/index.wxml`; `miniapp/scripts/check-miniapp.mjs`; `miniapp/scripts/verify-devtools-cart-long-title.cjs`
- next_time_signal: 短胶囊/徽标只承载短事实标签，长规则统一放在页面级说明位；新增胶囊文案时同步补长度或不截断断言。

## M-20260913-126：购物车推荐卡动作文案与加购提示自相矛盾，且未复用首页统一口径

- status: guarded
- first_seen: 2026-09-13
- severity: low
- symptom: 同一件商品在首页/商品列表显示“预订”（现做）或“加入购物车”（现货配件），在购物车“推荐商品”卡上却显示裸“加入”；点击后 toast 恒为“已加入预订单”，配件商品会出现动作与提示互相矛盾的文案。
- root_cause: `pages/cart/index.ts` 的 `toRecommendedProductView()` 自建 `actionText: isUnavailable ? "查看" : "加入"`，加购回调写死 `wx.showToast({ title: "已加入预订单" })`，没有复用 `utils/bakery.ts` 的 `getProductActionLabel()` / `getProductAddToastLabel()` / `getProductCardTip()`；静态门禁只覆盖购物车状态胶囊，没有覆盖推荐卡。
- impact: 顾客在同一商品的不同入口看到不同动作词，配件加购后的提示与动作语义不符，削弱“现做预订 / 现货加购”这一购买路径口径。
- fix: 推荐卡提示改 `getProductCardTip()`、动作改 `getProductActionLabel()`、加购 toast 改 `getProductAddToastLabel()`；视图字段 `soldText` 更名为 `hintText`，样式类 `.recommend-sold` 更名为 `.recommend-hint` 并补两行 clamp、最小高度与 22rpx 字号。
- new_guardrail: `check-miniapp.mjs` 新增 `checkCartRecommendedActionCopy()`（推荐卡必须复用三个统一 helper、禁止写死“已加入…”提示）；`verify-devtools-cart-long-title.cjs` 新增 `cart-recommend-card-copy`（渲染文案必须与页面数据一致、动作只允许“预订/加入购物车/查看”、提示字号 ≥11px、价格与动作按钮零重叠）。
- verification: `npm run devtools:cart-long-title --prefix miniapp` PASS（4 张推荐卡：3 张“预订”、1 张“加入购物车”，hintFontSize=11，overlapX≤-52.7px 无重叠）；`check:miniapp`、`typecheck` PASS；变异测试移除 `getProductActionLabel` 后静态门禁精确失败。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `miniapp/miniprogram/pages/cart/index.ts`; `miniapp/miniprogram/pages/cart/index.wxml`; `miniapp/miniprogram/pages/cart/index.wxss`; `miniapp/scripts/check-miniapp.mjs`; `miniapp/scripts/verify-devtools-cart-long-title.cjs`
- next_time_signal: 同一个动作在不同入口必须来自同一 helper；新增卡片动作文案时同步补静态门禁与运行态“渲染文案=页面数据”断言。

## M-20260913-127：首页商品卡购买说明只有 19rpx，低于商品列表同口径的 11px 可读性基线

- status: guarded
- first_seen: 2026-09-13
- severity: low
- symptom: 首页货架商品卡的购买说明胶囊仍是 19rpx（约 9.5px），而商品列表同一句“提前1天预订 · 闪送/自取”已按 r39 口径提到 22rpx（11px）；最高频入口的次级文字反而最小。
- root_cause: r39 只把商品列表 `.product-hint` 提到 22rpx，静态守卫也只绑定该选择器；首页 `.product-tip` 未纳入同一可读性基线。
- impact: 首页商品卡承载预订与配送规则，字号过小会削弱扫读与可读性，并让同一口径在两个页面呈现不一致。
- fix: `.product-tip` 由 19rpx 提到 22rpx，补 `max-width: 100%`、`line-height: 1.35`、`box-sizing: border-box`，允许在卡片宽度内自然换行而不做 nowrap 截断。
- new_guardrail: `checkProductCardHintReadability()` 扩展到首页 `.product-tip`（字号 ≥22rpx、禁止 nowrap、必须限制 `max-width: 100%`）；`verify-all-15-pages-devtools.cjs` 首页新增商品卡购买说明量测（条数、最小字号 ≥11px、不得溢出所在卡片、行数 ≤3）。
- verification: `npm run devtools:verify-all-pages --prefix miniapp` 15/15 PASS（商品卡购买说明：条数=6，最小字号=11px，最大溢出=0.0px，最大行数≈1）；变异把字号改回 19rpx 后静态门禁精确失败。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `miniapp/miniprogram/pages/home/index.wxss`; `miniapp/scripts/check-miniapp.mjs`; `miniapp/scripts/verify-all-15-pages-devtools.cjs`
- next_time_signal: 可读性基线必须同时覆盖所有渲染同一文案的选择器，不能只给单页加守卫。

## M-20260913-128：DevTools 多实例/陈旧自动化端口把环境故障伪装成页面缺陷

- status: guarded
- first_seen: 2026-09-13
- severity: medium
- symptom: 同一份代码执行 `devtools:verify-all-pages` 时，products/profile 页面渲染空白（缺失 `.page-fixed-safe`、门店文案与订单入口），cart/recharge/checkout 报 `timeout waiting for automator response`；截图里只剩自定义 tabBar。同期 `devtools:cart-long-title` 却能正常渲染并 PASS。
- root_cause: 微信开发者工具存在多个 IDE 进程与端口（IDE HTTP 10701/13836 提示并存，旧实例仍在进程列表），此前用 `cli.bat auto` 在已有实例上补开自动化端口，未保证唯一实例，导致 automator 连到陈旧目标，渲染与响应间歇失效。
- impact: 环境故障被记成页面缺陷，会触发对不存在问题的错误“修复”，并污染运行态证据链。
- fix: 完全退出所有 `微信开发者工具` 进程，重新执行 `cli.bat auto --project D:\Project\YunxiBakery\miniapp --auto-port 9420 --port 10701 --trust-project`，确认 `127.0.0.1:9420` 监听后复跑；`verify-all-15-pages-devtools.cjs` 连接后新增渲染预检，无法渲染首页即以退出码 2 结束并提示重启实例，不覆盖上一份报告。
- new_guardrail: 审计脚本渲染预检（变异验证：强制预检失败时 exit=2 且提示准确）；`ERRORS.md` 本条即重启口径的权威记录。
- verification: 重启单一实例后 `devtools:verify-all-pages` 15/15 PASS、`devtools:cart-long-title` PASS、`devtools:verify-commerce-flows` PASS；未重启前的 10/15、11/15 失败不再复现。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `miniapp/scripts/verify-all-15-pages-devtools.cjs`; `miniapp/reports/devtools/all-pages-devtools-audit.json`; `miniapp/reports/devtools/final-products.png`; `miniapp/reports/devtools/final-profile.png`
- next_time_signal: 出现“多页同时缺失根容器 / automator timeout / 页面只剩 tabBar”时先按环境故障排查（单一 IDE 实例 + 9420 端口 + 渲染预检），不要直接按页面缺陷改代码。

## M-20260913-129：本地后端未运行时把兜底空态误读为页面缺陷

- status: guarded
- first_seen: 2026-09-13
- severity: medium
- symptom: 一轮 `devtools:verify-all-pages` 只有 11/15 通过：首页货架只剩 2 条兜底商品、商品页缺少自提价与北京闪送说明、会员中心订单入口为 0，并伴随多次 automator 超时；`http://127.0.0.1:7001` 连接被目标计算机积极拒绝。
- root_cause: 本地 uvicorn 进程已退出；develop 版小程序按 `miniapp/miniprogram/services/config.ts` 固定访问 `127.0.0.1:7001`，页面进入兜底/空态，审计把缺数据当成页面缺陷。
- impact: 无后端的运行态结果会误导 UI/UX 结论，甚至掩盖真实缺陷或制造假缺陷。
- fix: 用 `python -m uvicorn --app-dir backend app.main:app --host 127.0.0.1 --port 7001 --reload` 启动本地后端（日志重定向到 `D:\Temp`），确认 `/health` 返回 200、`/api/v1/miniapp/products?featured=true&limit=6` 返回 6 条后复跑审计。
- new_guardrail: 运行态审计前先验证 `127.0.0.1:7001/health` 与精选接口条数；本轮已把该前置口径写入 `PROJECT-STATE.md` 与本条目。
- verification: 后端恢复后 `devtools:verify-all-pages` 15/15 PASS（首页货架接口=6、渲染=6），`devtools:cart-long-title`、`devtools:verify-commerce-flows` PASS。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `miniapp/miniprogram/services/config.ts`; `miniapp/reports/devtools/all-pages-devtools-audit.json`; `PROJECT-STATE.md`
- next_time_signal: 审计前先确认本地后端与精选接口有数据，再解读页面级断言；不要用兜底空态结果下 UI/UX 结论。

## M-20260913-130：商品详情悬浮栏断言只等 class 不等背景过渡，产生实底假失败

- status: guarded
- first_seen: 2026-09-13
- severity: low
- symptom: `devtools:verify-commerce-flows` 在商品详情断言上报“商品详情滚动后悬浮栏未切实底”，但报告里 `scrolledNavClass` 已含 `detail-nav--solid`、`restoredNavClass` 也已恢复，只有 `scrolledNavBackground` 读到 `rgba(0, 0, 0, 0)`。
- root_cause: `.detail-nav` 带 `transition: background-color 0.18s ease`；断言轮询只判断 class 一旦变成 solid 就跳出，紧跟着读到的背景色还在过渡起点（透明），把过渡中间态当成未实底。
- impact: 与 M-20260913-124 同类：页面行为正确却产生运行态假失败，误导后续 UI/UX 判断与证据链。
- fix: 新增 `resolveColorAlpha()`，轮询条件改为“class 含 `detail-nav--solid` 且背景 alpha ≥ 0.9”，回顶恢复条件改为“class 不含 solid 且背景 alpha < 0.1”，不再只看 class。
- new_guardrail: `verify-miniapp-commerce-flows.cjs` 的 `product-detail-scroll-nav` 现在同时断言 class 与解析后的背景不透明度（白底 `rgb(255, 255, 255)`）。
- verification: 硬化后 `npm run devtools:verify-commerce-flows --prefix miniapp` PASS，报告 `scrolledNavBackground=rgb(255, 255, 255)`、`initialNavClass`/`restoredNavClass` 均不含 solid。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `miniapp/scripts/verify-miniapp-commerce-flows.cjs`; `miniapp/reports/devtools/miniapp-commerce-flows.json`; `miniapp/miniprogram/pages/product-detail/index.wxss`
- next_time_signal: 带 CSS transition 的状态断言必须轮询到“目标属性已达终态”，不能只看 class/属性标记；背景色至少校到 alpha 阈值。

## M-20260913-131：结算审计只注入 `expectTime`，造成选择器与预览时间矛盾

- status: guarded
- first_seen: 2026-09-13
- severity: low
- symptom: `commerce-flow-checkout-quoted.png` 中日期/小时控件显示 `2026-09-13 18:00`，底部“期望时间”却显示 `2026-09-15 15:00`，截图像结算页存在两个提交时间。
- root_cause: `verify-miniapp-commerce-flows.cjs` 的注入函数只直接写入 `expectTime: "2026-09-15 15:00"`，没有调用页面真实的 `syncExpectTimeSchedule()`，因此绕过日期、小时、分钟索引的派生同步。
- impact: 审计制造了页面不存在的状态冲突，截图不能作为有效视觉证据，也容易把脚本问题误当成业务页缺陷。
- fix: 删除直接日期注入，统一由 `syncExpectTimeSchedule()` 从提交值重建选择器；新增 `checkout-schedule-consistency`，同时比对 `expectTime`、日期、小时、分钟与“期望时间”预览。
- new_guardrail: `verify-miniapp-commerce-flows.cjs` 的 `readScheduleState()` 与 `checkout-schedule-consistency`；任何结算时间注入必须先经过页面真实同步方法。
- verification: `npm run devtools:verify-commerce-flows --prefix miniapp` PASS；报告记录 `expectTime=2026-09-13 18:00`、`previewText=期望时间：2026-09-13 18:00`、`selectedDateValue=2026-09-13`、`selectedHourValue=18`、`selectedMinuteValue=00`。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `miniapp/scripts/verify-miniapp-commerce-flows.cjs`; `miniapp/reports/devtools/miniapp-commerce-flows.json`; `miniapp/reports/devtools/commerce-flow-checkout-quoted.png`
- next_time_signal: DevTools 注入必须走页面真实状态转移，不能只写最终展示字段；派生字段必须有交叉一致性断言。

## M-20260913-132：登记成功态截图残留上一轮错误 Toast，形成“成功+失败”假冲突

- status: guarded
- first_seen: 2026-09-13
- severity: low
- symptom: `final-registration-success.png` 同时显示“登记已提交”和上一轮后端校验留下的“活动批次不存在或已结束”Toast。
- root_cause: 审计先验证真实后端的缺失活动批次错误，该错误会触发微信 Toast；脚本随后立即注入成功态并截图，没有清除仍然存活的 Toast。
- impact: 临时浮层被误读为业务状态自相矛盾，成功态截图与证据链失真。
- fix: 在注入成功态和截图前显式调用 `hideToast` 并等待 350ms，不再依赖 Toast 自然超时。
- new_guardrail: `verify-devtools-registration-policy.cjs` 成功态截图前固定清除上一轮 Toast；成功态断言继续校验面板、标题、说明、四行摘要与双操作按钮。
- verification: `npm run devtools:registration-policy --prefix miniapp` PASS；重生成 `final-registration-success.png`，页面内只剩成功态，不再出现错误 Toast。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `miniapp/scripts/verify-devtools-registration-policy.cjs`; `miniapp/reports/devtools/registration-policy-audit.json`; `miniapp/reports/devtools/final-registration-success.png`
- next_time_signal: 跨状态注入截图前必须隔离前一状态的 Toast/弹层；成功与错误反馈不得依赖固定超时碰运气。

## M-20260913-133：登记成功态只注入可提交状态，遗漏会话视图造成“成功但未登录”

- status: guarded
- first_seen: 2026-09-13
- severity: low
- symptom: 成功态截图显示“微信身份 · 未登录”，但仍展示“登记已提交”与后续操作。
- root_cause: 审计脚本只注入 `canSubmitRegistration/loginStateText/loginActionText`，没有同步 `sessionView.statusText/badgeText`，登录事实被拆成多份状态后出现分叉。
- impact: 成功态截图与真实登录前置条件不一致，无法证明顾客完成提交后的身份状态。
- fix: 未登录与已登录注入都显式提供完整 `sessionView`；成功态新增 `successSessionText` 断言，必须包含“已登录”。
- new_guardrail: `verify-devtools-registration-policy.cjs` 的匿名闸门与登录校验链分别注入完整会话视图，`registration_success_view` 校验 `successSessionText`、标题、说明、四行摘要和按钮尺寸。
- verification: `npm run devtools:registration-policy --prefix miniapp` PASS；报告 `successSessionText` 包含“微信身份 · 已登录”，`successRowCount=4`，两个操作按钮各 45px 高。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `miniapp/scripts/verify-devtools-registration-policy.cjs`; `miniapp/reports/devtools/registration-policy-audit.json`; `miniapp/reports/devtools/final-registration-success.png`
- next_time_signal: 登录/身份属于跨组件多字段状态时，测试注入必须一次同步完整视图并在关键结果页做可见性断言。

## M-20260913-134：商品目录搜索框输入后跳高 12px，输入位置随布局位移

- status: guarded
- first_seen: 2026-09-13
- severity: medium
- symptom: 在商品目录输入关键词后，搜索框外框由 33px 突变为 45px（输入框仍为 33px），搜索栏下方商品网格同步下移。
- root_cause: 清空按钮固定 `88rpx`（≈45px），而搜索栏 `min-height: 64rpx`（≈33px）且 `align-items: center`；flex 容器被最高的子元素撑高，空态没有该按钮所以只在输入瞬间暴露。
- impact: 商品优先主路径上每次开始搜索都会发生一次布局跳动，输入焦点、光标与下方卡片位置在用户手指仍在屏幕上时移动，属于可见的体验缺陷。
- fix: 搜索栏与输入框统一为 `88rpx` 高度；清空按钮保留 `88rpx` 触控盒，通过 `border: 18rpx solid transparent` + `background-clip: padding-box` 把可视圆点收进 52rpx，触达与视觉不再互相牵制。
- new_guardrail: `verify-devtools-product-search.cjs` 的 `search-bar-typed-geometry` 断言输入前后外框/输入框高度差 ≤ 1px，并要求清空按钮 ≥ 44px、不越出搜索栏、不与输入区重叠。
- verification: `npm run devtools:product-search --prefix miniapp` PASS；报告 `search-bar-idle-geometry.barSize.height=45`、`search-bar-typed-geometry.barSize.height=45`、`clearSize=45x45`。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `miniapp/miniprogram/pages/products/index.wxss`; `miniapp/scripts/verify-devtools-product-search.cjs`; `miniapp/reports/devtools/product-search-audit.json`
- next_time_signal: 固定尺寸容器里放触控目标时，必须计算“最高子元素”对容器高度的反作用；触达尺寸与视觉尺寸要分开实现。

## M-20260913-135：商品目录同时渲染两个清空按钮，审计只取首个匹配漏检

- status: guarded
- first_seen: 2026-09-13
- severity: low
- symptom: 输入“曲奇”后搜索栏右侧同时出现两个 × 圆钮（`clearOffset.left=270` 与 `323`），截图里两个按钮并列。
- root_cause: 上一轮 WXML 修改只追加了带 `aria-label` 的新写法，没有删除旧 `<text …>×</text>` 节点；同时 `page.$(".products-search__clear")` 只返回首个匹配，旧断言在全绿的同时看不到重复节点。
- impact: 同一操作出现两个入口，视觉拥挤且触控语义重复；更关键的是“唯一入口/唯一控件”没有被任何断言覆盖，重复元素可以静默进入截图证据。
- fix: 删除旧节点，只保留带 `aria-label="清空搜索"` 的清空按钮；审计新增 `clearCount` 断言：空闲态必须为 0，有内容时必须恰好为 1。
- new_guardrail: `verify-devtools-product-search.cjs` 的 `search-bar-idle-geometry.clearCount` 与 `search-bar-typed-geometry.clearCount`。
- verification: `npm run devtools:product-search --prefix miniapp` PASS，报告 `clearCount=0`（空闲）与 `clearCount=1`（有内容）；运行时桌面锁屏使本轮截图调用失败（审计只记为证据缺失，未判为断言失败），`final-product-search-results.png` 仍为修复前旧帧（含两个清空钮），解锁后需重跑 `devtools:product-search` 重新生成。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `miniapp/miniprogram/pages/products/index.wxml`; `miniapp/scripts/verify-devtools-product-search.cjs`; `miniapp/reports/devtools/product-search-audit.json`
- next_time_signal: 修改 WXML/WXSS 块时按“替换”而不是“追加”落地；审计对关键控件要断言数量，不能只用返回首个元素的 `$`。

## M-20260913-136：搜索无结果时缺少回全部商品的出口，提示文案使用内部术语“全局检索”

- status: guarded
- first_seen: 2026-09-13
- severity: low
- symptom: 输入无结果关键词后页面只剩“暂时没有匹配商品 / 请尝试输入其他关键词进行全局检索”，顾客只能自己点 × 或逐字删除才能回到分类浏览。
- root_cause: 空态只写了标题与提示，没有复用页面已有的 `.products-empty__action` 出口；提示文案沿用了实现视角的“全局检索”，没有给出下一步动作。
- impact: 无结果状态把顾客留在无出口页面，且提示词描述实现方式而不是顾客可执行动作，与商品优先型目录的兜底要求不符。
- fix: 空态提示改为“换个关键词试试，或先看看全部商品”，新增“查看全部商品”动作复用 `clearSearch`，一键回到原分类浏览状态。
- new_guardrail: `verify-devtools-product-search.cjs` 新增 `search-empty-state`（空态标题/提示可见）与 `search-empty-state-recovery`（必须存在一键出口且文案为“查看全部商品”）。
- verification: `npm run devtools:product-search --prefix miniapp` PASS；报告 `copy=["暂时没有匹配商品","换个关键词试试，或先看看全部商品"]`、`hasAction=true`。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `miniapp/miniprogram/pages/products/index.wxml`; `miniapp/scripts/verify-devtools-product-search.cjs`; `miniapp/reports/devtools/product-search-audit.json`
- next_time_signal: 每个空态都要给出可执行下一步；面向顾客的文案不得出现“全局检索/同步/接口”等实现视角词。

## M-20260913-137：目录把“非卖品仅展示/勿拍”商品当成可预订商品展示（待业务确认）

- status: guarded
- first_seen: 2026-09-13
- severity: medium
- symptom: 全量 310 款商品中有 5 款标题自述非卖品/勿拍，仍以正常商品卡和“预订”按钮出现在目录与搜索结果里，例如“总统黄油10kg(非卖品仅展示）用于做各种点心”自提价 ¥1140（id 4589414115）、“甜品台订制联系客服（虚拟价格勿拍）”（id 4487996522）。
- root_cause: 小程序目录只按有赞 `is_active` 展示，而这 5 款在同步数据里仍是“在售”；当前没有独立的展示类目字段或过滤口径，搜索又把描述/标签一起纳入命中范围，于是原料/占位商品会混进真实商品结果。
- impact: 顾客可以把非卖品加入购物车并进入结算，产生无效订单、计价争议与客服解释成本；搜索“曲奇”时原料商品与真实商品同屏，直接损害长尾查找的可信度。
- fix: 业务口径仍待客服/店主确认（这 5 款在有赞侧应下架、改到独立“仅展示”分组，还是按标签/分组过滤），但“不能下单”本身无需等待：后端新增 `isPurchasable` 读模型（标题含“非卖品/勿拍/虚拟价格/仅供展示”判为展示型），小程序目录卡与详情页不再生成预订、加购或立即购买动作，`service/order/inventory.py` 在下单校验中二次拦截并返回 `商品仅供展示，不可下单: <productId>`。确认后只需替换判定来源，不动页面与下单防线。
- new_guardrail: `isPurchasable=false` 必须同时覆盖读模型、页面动作与下单链路；`check-miniapp.mjs` 的 `checkDisplayOnlyProductGuard()` 与运行态审计 `devtools:display-only-products` 共同防止“只隐藏按钮但仍可下单”；标题关键词是业务确认前的保守口径，不得当成最终分类来源。
- verification: `GET http://127.0.0.1:7001/api/v1/miniapp/products?limit=500&sort=popular` 返回 310 条，按标题含“非卖品/仅展示/勿拍/虚拟价格”筛出 5 条（4487996522、4589335101、5552189607、4589414115、5552190749）；搜索“曲奇”命中 4589414115 的截图 `final-product-search-results.png` 可目视复核。
- verification_20260914: 重启本地后端（`127.0.0.1:7001`，PID 21892）后翻页拉全 310 款，恰好这 5 款 `isPurchasable=false`、其余 305 款为 `true`；用服务端签发的前台会话直连 `POST /api/v1/miniapp/orders`，5 款全部返回 `400 {"detail":"商品仅供展示，不可下单: <id>"}`；`npm run devtools:display-only-products` PASS（搜索结果卡 `actionText=查看`、`badgeText=仅供展示`，详情页 `canPurchase=false` 且无数量步进器/履约卡/购买按钮，强制调用 `addToCart`/`buyNow` 后购物车仍为空，截图 `miniapp/reports/devtools/display-only-product-detail.png` 采集成功）；后端定向 `pytest tests/service/test_catalog.py tests/service/test_order.py` 48/48、前端 `test:bakery` 9/9 与 `check:miniapp` 通过。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `backend/app/service/catalog/purchasability.py`; `backend/app/service/catalog/serialization.py`; `backend/app/repository/youzan_repo.py`; `backend/app/service/order/inventory.py`; `miniapp/miniprogram/utils/bakery.ts`; `miniapp/miniprogram/pages/product-detail/index.wxml`; `miniapp/scripts/verify-devtools-display-only-products.cjs`; `miniapp/reports/devtools/display-only-products-audit.json`; `miniapp/reports/devtools/display-only-product-detail.png`
- next_time_signal: “在售”不等于“可卖”；有赞同步商品需要区分售卖商品与展示/占位商品，过滤规则必须来自业务确认。

## M-20260913-138：锁屏环境下 DevTools 截图失败被计成 15/15 页面缺陷

- status: guarded
- first_seen: 2026-09-13
- severity: low
- symptom: `devtools:verify-all-pages` 15 个页面全部 FAIL，唯一错误是 `Audit exception: fail to capture screenshot`，但同一轮 commerce/overflow/buttons 断言均为通过。
- root_cause: 截图调用在页面审计 try 块内，抛错后直接跳到 catch，既跳过同页后续断言（首页图片降级、详情滚动悬浮栏等），又因为 `result.errors` 非空把页面计为失败；脚本虽然已有锁屏进程探测，却只在连接超时时调用。
- impact: 环境锁屏被记录成产品缺陷，误导 UI/UX 判断，也把“缺少截图证据”与“页面断言失败”混为一谈。
- fix: 连接后先探测 LogonUI/LockApp，锁屏则整轮跳过截图只跑页面断言；普通截图异常也只记 `screenshotSkipped/screenshotError`，不阻断同页其余检查；汇总状态区分 `PASS/FAIL/BLOCKED` 并写明 `blockedReason`。
- new_guardrail: `verify-all-15-pages-devtools.cjs` 的 `isDesktopLocked()`、`skipScreenshots` 与 `status="BLOCKED"`（退出码 2，与断言失败 exit 1 区分）。
- verification: 重跑 `npm run devtools:verify-all-pages --prefix miniapp` 得 15/15 页面断言 PASS、`status=BLOCKED`、`blockedReason=桌面锁屏导致 DevTools 截图不可用…`；解锁后仍需重跑以补齐截图证据。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `miniapp/scripts/verify-all-15-pages-devtools.cjs`; `miniapp/reports/devtools/all-pages-devtools-audit.json`
- next_time_signal: 截图/日志属于证据而不是断言；证据采集失败要独立标记为环境阻塞，且不得中断同页其它结构断言。

## M-20260913-139：搜索审计首轮把标签页保留的搜索词当成空闲态缺陷

- status: guarded
- first_seen: 2026-09-13
- severity: low
- symptom: 第二轮搜索审计在“空闲态不应有清空按钮”处失败，但页面实际保留了上一轮的“曲奇”搜索词。
- root_cause: 商品目录是 tabBar 页面，`switchTab` 复用已存在的页面实例，`searchText` 按设计保留；审计假定每次进入都是空态。
- impact: 审计会把合理的“返回标签页保留搜索词”当成缺陷，并可能诱导后续把保词行为改掉。
- fix: 审计在测量空闲态前先检查 `searchText/clearCount`，用页面自身的 `clearSearch` 复位并等待归零；同时把“标签页保留搜索词”登记为预期行为。
- new_guardrail: `verify-devtools-product-search.cjs` 的复位前置条件与 `search-bar-idle-geometry.clearCount=0`。
- verification: 复位后重跑 `npm run devtools:product-search --prefix miniapp` PASS；连续两轮运行不再出现空闲态假失败。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `miniapp/scripts/verify-devtools-product-search.cjs`; `miniapp/reports/devtools/product-search-audit.json`
- next_time_signal: 审计进入 tabBar 页面必须先显式复位或声明期望状态，不能假定 `switchTab` 会重建页面。

## M-20260913-140：商品搜索审计截图失败仍汇总为 PASS

- status: guarded
- first_seen: 2026-09-13
- severity: low
- symptom: `devtools:product-search` 在锁屏环境下把 `search-results-screenshot` 记为 `ok:false / fail to capture screenshot`，但顶层 `status` 仍写成 `PASS` 并返回退出码 0，流水线会把“缺截图证据”当成“全部验证通过”。
- root_cause: 截图失败按证据缺失降级处理，但脚本只有 `PASS/FAIL` 两态；成功路径无条件把状态置为 `PASS`，没有把 `screenshotBlocked` 带入汇总。
- impact: 页面断言通过时报告看似全绿，实际缺少本轮截图证据，后续可能把旧截图或未经目视确认的改动当成已验证结果。
- fix: 商品搜索审计新增 `screenshotBlocked` 标记与 `BLOCKED` 状态；截图失败时写入 `blockedReason` 并返回退出码 2，页面断言失败仍为 `FAIL` 与退出码 1。
- new_guardrail: `verify-devtools-product-search.cjs` 保持 `PASS=0 / FAIL=1 / BLOCKED=2` 与 15 页审计同一口径；证据缺失不得再汇总为 PASS。
- verification: 锁屏状态下重跑 `npm run devtools:product-search --prefix miniapp`，12 项页面断言全部通过，输出 `Product search audit: BLOCKED`、`blockedReason=桌面锁屏导致 DevTools 截图不可用…`、`EXIT=2`；`node --check` 通过。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `miniapp/scripts/verify-devtools-product-search.cjs`; `miniapp/reports/devtools/product-search-audit.json`
- next_time_signal: 任何把截图、日志、附件列为证据的审计脚本，都要显式区分“断言通过”和“证据采集完成”，不能因为断言通过就返回 PASS。

## M-20260913-141：全量商品目录浏览成本与搜索大结果集渲染无上限

- status: guarded
- first_seen: 2026-09-13
- severity: high
- symptom: 全量目录 310 款商品首屏只渲染 12 款，按每批 12 款点击“查看更多”需要 25 次才能看到尾部；搜索“蛋糕”命中 310 款时页面一次性渲染 310 张商品卡，`.products-global-search__inner` 内容高度达到 36281px。
- root_cause: 商品页通过 `listProducts({ limit: 500, sort: "popular" })` 本地全量过滤，`applySearch()` 把全部命中直接写入 `globalSearchResults`，没有渲染上限、分页或触底加载；常规目录使用 `INITIAL_PRODUCTS_PER_SECTION=12` 与 `PRODUCTS_PAGE_SIZE=12` 纯手动批次。
- impact: 目录浏览对长尾商品不友好，25 次点击超出正常选购耐心；一次构建 310 张商品卡会带来首屏渲染、内存和滚动压力，与“商品优先”主路径直接冲突。另测得全量 500 条请求体积 302510 字节、暖态中位 228ms，而 30 条请求体积 22274 字节、暖态中位 81ms，首屏冷启动与移动网络下载成本相差约 13.6 倍体积。
- fix: 第一阶段已于 r43.4 实施：商品页目录改由 `bindscrolltolower` 触底加载（`PRODUCTS_PAGE_SIZE=12`）并保留“查看更多”兜底；搜索首屏只渲染 30 款（`SEARCH_RENDER_PAGE_SIZE`），区分“共找到 N 款商品 / 已展示 M 款 · 按销量排序”，触底或“查看更多搜索结果”按同序递增到尾部；保留现有排序、卡片与预订行为，不依赖后端契约变更。第二阶段仍待上线前另立 API 契约与方案：后端增加分页游标/页码与服务端关键词搜索，首屏只取 20–30 条，把 302510 字节的冷启动全量下载降到约 22000 字节量级。
- new_guardrail: `check-miniapp.mjs` 新增 `checkCatalogIncrementalLoading()`，静态守住两个 `bindscrolltolower` 绑定、搜索首屏 30 款上限、命中数/已展示数双计数与 `slice(0, renderedCount)` 窗口；`verify-devtools-product-search.cjs` 新增 `search-render-bound`、`search-render-bound-screenshot`、`search-load-more-tail`、`catalog-scroll-load-more` 四项运行态断言，缺失任一即失败。
- verification: 只读运行态探针（不写临时文件，连接 DevTools 9420 + 本地后端 7001）实测：`catalogCount=310`、`initiallyRendered=12`、`hasMoreProducts=true`、`remainingLoadMoreClicks=25`、`broadSearchKeyword=蛋糕`、`broadSearchMatches=310`、`renderedSearchCards=310`、`searchInnerHeightPx=36281`；接口复测 `limit=30` 为 30 条 / 22274 字节 / 5 次暖态中位 81ms，`limit=500` 为 310 条 / 302510 字节 / 5 次暖态中位 228ms。
- verification_r43_4: 连接 DevTools 9420 + 本地后端 7001 复测：搜索“蛋糕”命中 310 款时首屏 DOM 30 张、`searchHasMore=true`、计数文案“共找到 310 款商品 / 已展示 30 款 · 按销量排序”；连续 10 次 `loadMoreSearchResults` 后 310/310 渲染、`searchHasMore=false`、首条排序基准不变；目录 `loadMoreProducts` 由 12 → 24 / 310。`devtools:product-search` 16 项检查 PASS（含新增 4 项）、`devtools:verify-all-pages` 15/15 页 + 8/8 未登录态 PASS、`check:miniapp`、`typecheck`、`test:bakery` 8/8、触控扫描 46 选择器 / 13 页、按钮审计 119 控件、按钮样式 0 失败 0 警告均 PASS。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `miniapp/miniprogram/pages/products/index.ts`; `miniapp/miniprogram/pages/products/index.wxml`; `miniapp/scripts/verify-devtools-product-search.cjs`
- next_time_signal: 当目录规模超过百款或单次搜索结果可能达到百条时，列表必须默认分页/限量渲染；审计只断言“全部能搜到”不够，还要断言 DOM 卡数有界且后续加载可达尾部。评估列表性能时必须同时看渲染卡数和首包体积，不能用本地缓存的暖态响应时间掩盖冷启动下载成本。

## M-20260913-142：多个 DevTools 审计把锁屏截图失败当成整轮致命错误

- status: guarded
- first_seen: 2026-09-13
- severity: medium
- symptom: `devtools:commerce-states` 在锁屏环境下以 `Error: fail to capture screenshot` 直接退出，页面断言的 11 项检查结果虽然已算出，但报告未写入、整轮无结论；`cart-long-title`、`checkout-delivery-states`、`product-purchase-path`、`registration-policy`、`commerce-flows` 与 `walkthrough:phase-c` 存在同类裸截图调用。
- root_cause: M-20260913-138 只修了 15 页审计，M-20260913-140 只修了商品搜索审计；其余脚本各自直接调用 `miniProgram.screenshot()`，没有共享的“截图属于证据而非断言”状态层，也没有统一的 PASS/FAIL/BLOCKED 退出码。
- impact: 一类环境问题在多个脚本重复制造假失败或直接阻断报告写入，降低逐页 UI/UX 审计的覆盖率和可信度。
- fix: 新增共享模块 `miniapp/scripts/lib/devtools-audit-status.cjs`，提供 `captureEvidenceScreenshot()`、`finalizeAuditStatus()`、`exitForAuditStatus()`；7 个审计脚本改为截图失败只记环境阻塞（BLOCKED），页面断言继续执行，状态统一为通过（PASS）退出 0 / 断言失败（FAIL）退出 1 / 环境阻塞（BLOCKED）退出 2。
- new_guardrail: 共享模块同时兼容 `screenshots[].status` 与 `checks[].state` 含 screenshot 且 `ok=false` 两种既有记录格式；后续新增 DevTools 审计必须复用该模块，不得再裸调截图。
- verification: 锁屏下串行复核：`commerce-states` 11 检查 0 错误、`cart-long-title` 5 检查、`checkout-delivery-states` 10 检查 0 错误、`product-purchase-path` 7 检查 0 错误、`registration-policy` 11 检查 0 错误、`commerce-flows` 12 检查 0 错误，均为 BLOCKED/退出码 2；`walkthrough:phase-c` 15/15 页导航成功、控制台 0 warning/0 error、15 页截图阻塞、退出码 2。所有页面断言均未发现产品缺陷。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `miniapp/scripts/lib/devtools-audit-status.cjs`; `miniapp/scripts/verify-devtools-commerce-states.cjs`; `miniapp/scripts/verify-devtools-cart-long-title.cjs`; `miniapp/scripts/verify-devtools-checkout-delivery-states.cjs`; `miniapp/scripts/verify-devtools-product-purchase-path.cjs`; `miniapp/scripts/verify-devtools-registration-policy.cjs`; `miniapp/scripts/verify-miniapp-commerce-flows.cjs`; `miniapp/scripts/walkthrough-phase-c.mjs`
- next_time_signal: 同一环境问题在第二个脚本复现时，必须抽共享守卫并批量收口，不能只修当前报错的那一个脚本。

## M-20260913-143：DevTools 审计用进程名预判锁屏，把可截图环境误判成“无截图证据”

- status: guarded
- first_seen: 2026-09-13
- severity: medium
- symptom: 桌面已解锁、15 页断言全部通过时，`devtools:verify-all-pages` 仍汇总为环境阻塞（BLOCKED），`blockedReason=桌面锁屏导致 DevTools 截图不可用`，而报告里没有任何真实截图失败记录。
- root_cause: `verify-all-15-pages-devtools.cjs` 用 `isDesktopLocked()` 判读 `LogonUI`/`LockApp` 进程是否存在来预判锁屏；这两个进程在解锁后仍长期常驻，预判为真后脚本跳过全部截图采集，再用“没有截图”反证“锁屏”。
- impact: 可截图环境被误判为缺证据，视觉验收无法收口；更严重的是预判会把真实截图失败与进程误判混在一起，掩盖真正的环境问题。
- fix: 删除全局锁屏预判，逐页真实调用截图；成功保留截图与尝试次数，失败只记 `screenshotSkipped`/`screenshotError`；`blockedByEnvironment` 只取决于真实截图失败，不再参考进程名。
- new_guardrail: 任何“环境不可用”的判断必须以真实调用结果为准；不得用辅助进程、窗口标题或时间等间接信号代替真实操作结果。
- verification: 重跑 `npm run devtools:verify-all-pages --prefix miniapp` 得 15/15 页 PASS、8/8 未登录态 PASS、23 张截图全部生成、`status=PASS`、`blockedReason` 为空（`all-pages-devtools-audit.json` generatedAt 2026-09-13T13:57:22Z）。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `miniapp/scripts/verify-all-15-pages-devtools.cjs`; `miniapp/reports/devtools/all-pages-devtools-audit.json`
- next_time_signal: 当审计报“环境不可用”而产物实际已生成时，优先怀疑判定逻辑而不是重跑。

## M-20260913-144：DevTools 截图单次超时无重试，一次自动化抖动就让整轮缺证据

- status: guarded
- first_seen: 2026-09-13
- severity: medium
- symptom: 15 页审计的第 23 张截图（`pages/chat/index` 未登录态）报 `timeout waiting for automator response`，其余 22 张正常，整轮仍被判为环境阻塞（BLOCKED）；同一现象在 `devtools:product-search` 与 `devtools:cart-long-title` 也出现过。
- root_cause: 各脚本直接调用一次 `miniProgram.screenshot()`，没有重试；自动化通道的偶发响应超时与真正的环境不可用无法区分。
- impact: 已解锁环境仍可能因一次抖动丢失整轮视觉证据，需要人工重跑，既浪费审计时间，也容易把环境噪声误判成产品缺陷。
- fix: 共享模块新增 `captureScreenshotWithRetry()`（默认 3 次、间隔 700ms，可用 `MINIAPP_SCREENSHOT_ATTEMPTS`/`MINIAPP_SCREENSHOT_RETRY_DELAY_MS` 覆盖）并记录 `attempts`；`verify-all-15-pages-devtools.cjs` 与 `verify-devtools-product-search.cjs` 改用该实现；阻塞文案从“桌面锁屏”改为“环境或自动化波动”。
- new_guardrail: 截图等证据类调用默认带重试；报告必须记录尝试次数，重试成功也要留下痕迹。
- verification: 用“失败两次后成功”的假 `miniProgram` 验证重试返回 `{ok:true,attempts:3}`，持续失败时返回 `{ok:false,attempts:2,message:"still down"}`；重跑 `devtools:verify-all-pages` 得 15/15 + 8/8 PASS、23 张截图 `attempts=1`；相关脚本 `node --check` 通过。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `miniapp/scripts/lib/devtools-audit-status.cjs`; `miniapp/scripts/verify-all-15-pages-devtools.cjs`; `miniapp/scripts/verify-devtools-product-search.cjs`
- next_time_signal: 任何“偶发超时”类环境失败，先加重试与尝试次数记录，再谈人工重跑。

## M-20260913-145：多轮 DevTools 审计后自动化通道整体超时，需重启 IDE 再复跑

- status: guarded
- first_seen: 2026-09-13
- severity: medium
- symptom: 连续多轮审计后，15 页断言全部 PASS 且截图正常，但紧接着的未登录态阶段 8 个页面全部报 `timeout waiting for automator response`，`callWxMethod` 全部失败，并连带出现“清除登录存储后页面仍显示已登录会话”；同批 `devtools:cart-long-title` 也在首个检查前超时（`checks` 为空）。
- root_cause: 长时间运行后 DevTools 自动化通道退化或阻塞，与页面代码无关；重启 IDE（`cli.bat quit` 后 `cli.bat auto --project ... --auto-port 9420 --trust-project`）后同一批脚本全部恢复。
- impact: 会把环境退化误报成产品缺陷（未登录态不生效、购物车长标题失败），若不识别会造成错误的整改方向。
- fix: 本轮已识别处置流程并复跑取证；未改产品代码。
- new_guardrail: 出现成批 `timeout waiting for automator response`、且 `checks` 为空或跨页面同时失败时，先重启 DevTools 单实例再复跑，禁止据此直接改页面逻辑。
- verification: 重启 IDE 后 `devtools:verify-all-pages` PASS（15/15 页 + 8/8 未登录态、23 张截图）；`devtools:cart-long-title` 复跑 PASS（5 项检查）。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `miniapp/reports/devtools/all-pages-devtools-audit.json`; `miniapp/reports/devtools/cart-long-title-audit.json`
- next_time_signal: 自动化层报错成批出现且报告为空时，先区分环境退化与产品缺陷，禁止用一页失败倒推业务逻辑。

## M-20260913-146：搜索面板与商品目录切换上下文后保留旧滚动偏移

- status: guarded
- first_seen: 2026-09-13
- severity: medium
- symptom: 搜索宽口径关键词（如“蛋糕”命中 310 款）后向下滚动再看结果，收窄到另一关键词时新结果仍停留在旧滚动位置；商品目录滚动后切换分类也存在同类偏移保留，用户会直接落进列表中段。
- root_cause: `products-global-search` 与 `products-content` 两个 `scroll-view` 只做了数据替换，没有在关键词、分类变化时复位滚动位置；页面也没有可复用的顶部锚点。
- impact: 商品优先主路径上，筛选后的首条结果不可见，用户需要手动滚回顶部才能继续选购，直接降低搜索与分类浏览效率。
- fix: 素材页新增 `searchScrollAnchor`/`catalogScrollAnchor` 与两个零高度顶部锚点，`applySearch()` 收窄关键词、`applyActiveCategory()` 切换分类时重置锚点；WXML 增加 `scroll-into-view` 与 `scroll-with-animation="{{false}}"`；WXSS 增加零高度锚点样式。
- new_guardrail: `check-miniapp.mjs` 静态守住两个 `scroll-into-view`、两个顶部锚点 id 和两个 reset helper 调用；`verify-devtools-product-search.cjs` 新增 `search-scroll-reset-on-keyword-change` 与 `catalog-scroll-reset-on-category-switch` 运行态断言，要求滚动前偏移真实发生、切换后回到首屏。
- verification: DevTools 9420 + 本地后端 7001：搜索“蛋糕”滚动到 `scrollTop=900` 后收窄为长尾关键词，实测 `scrollTopAfter=0`；分类滚动到 `scrollTop=900` 后切换分类，实测 `scrollTopAfter=8`、`catalogScrollAnchor=products-catalog-top`（8px 为切换后布局重算残余，属首屏内）。`devtools:product-search` 18 项检查 PASS。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `miniapp/miniprogram/pages/products/index.ts`; `miniapp/miniprogram/pages/products/index.wxml`; `miniapp/miniprogram/pages/products/index.wxss`; `miniapp/scripts/check-miniapp.mjs`; `miniapp/scripts/verify-devtools-product-search.cjs`; `miniapp/reports/devtools/product-search-audit.json`
- next_time_signal: 任何列表/面板在筛选条件、分类、分页上下文变化后，都要显式复位自身滚动位置；仅替换数据源不等于复位视图。

## M-20260913-147：DevTools 自动化注入输入与点击时 bindinput/bindtap 事件未送达

- status: guarded
- first_seen: 2026-09-13
- severity: low
- symptom: 商品搜索审计中 `input.input("曲奇")` 后输入框 `value` 确认为“曲奇”，但页面 `searchText` 仍为空、结果 0 条；清空按钮 `tap()` 后 `searchText` 与结果不变。同一环境直接 `page.callMethod("onSearchInput", ...)` 可正常得到 3 条命中。
- root_cause: 微信开发者工具自动化层在本轮出现事件绑定未送达（值已注入 DOM，但 `bindinput`/`bindtap` 未触发页面事件），与页面业务代码无关；页面方法路径实测正常。
- impact: 审计会把环境事件层故障误报成产品缺陷，反复产生假失败并误导整改方向。
- fix: `verify-devtools-product-search.cjs` 的 `typeKeyword()`/`clearByButton()` 改为真实输入与点击优先，事件未生效时回退到页面方法，并在报告 `inputPaths`/`clearPaths` 中显式记录实际路径。
- new_guardrail: DevTools 审计出现“DOM 已变但页面数据未变”时，必须先用 `page.callMethod` 验证业务逻辑，再判断是否为产品缺陷；审计报告必须保留事件路径字段。
- verification: 同轮审计 `inputPaths` 全部为 `input-injection`、`clearPaths.tap=tap`，18 项检查 PASS；此前失败轮次已确认回退路径可得到与接口一致的 3 条命中。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `miniapp/scripts/verify-devtools-product-search.cjs`; `miniapp/reports/devtools/product-search-audit.json`
- next_time_signal: 自动化前先区分“用户事件链路”与“页面方法链路”；两者结果不一致时优先怀疑工具事件层，而不是直接改业务逻辑。

## M-20260913-148：有赞网关 4007 被当成空数据，分类恒空且一次商品对账可误清空目录

- status: guarded
- first_seen: 2026-09-13
- severity: high
- symptom: `youzan.items.onsale.get`、`youzan.itemcategories.tags.get`、`youzan.item.base.search`、`youzan.item.classification.search` 真实调用返回 `{"gw_err_resp":{"err_code":4007,...}}`，客户端只取 `data`/`response`，四个同步接口全部按“0 条商品 / 0 个分组 / 0 个分类”正常返回；`ProductReconcileService.run()` 拿到空在售集合后会把本地 310 款在售商品全部软下架，小程序分类接口也一直返回空数组。
- root_cause: `YouzanClient._call()` 只校验 HTTP 状态码，不识别网关级 `gw_err_resp`，调用方把“网关拒绝”与“店铺确实没有数据”混为一谈；本次拒绝原因是有赞应用未配置调用方 IP 白名单（网关回包源 IP 111.199.244.119）。
- impact: 一是商品目录分类导航长期为空（M-20260913-115）；二是运营在后台触发一次商品对账就可能把 310 款在售商品整批下架，目录清空且需重新导入才能恢复；三是同步日志输出“拉取完成，共 0 条”，把权限故障伪装成正常空数据。
- fix: `client.py` 新增 `extract_gateway_error()`/`build_gateway_error_message()` 与 `_ensure_gateway_success()`，在 `list_onsale_items()`、`list_product_tags()`、`search_item_base()`、`search_item_classifications()` 四个同步入口显式抛出脱敏 `APIError`；`_call()` 保持原返回合同，不影响已自行识别 `gw_err_resp` 的单品查询与商品事件。`product_reconciler.py` 新增空在售集合保护：本地仍有在售商品而上游返回空集合时跳过整批下架并回报 `onsale_empty_guard`。
- new_guardrail: 网关级错误必须显式失败并带 `err_code`/`trace_id`，禁止等价于空数据；商品对账在“上游空集合 + 本地有在售”时必须拒绝下架并回报错误码，禁止静默清空目录。
- verification: 真实调用实测 `err_code=4007`（源 IP 未加白名单）；`tests/service/youzan` 70 项通过，含新增 7 项网关错误用例与 `test_product_reconcile_skips_deactivation_on_empty_onsale_result`；数据库副本端到端运行 `ProductReconcileService.run()` 抛出 `APIError` 且在售商品 before=after=310；`ruff check` 通过。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `backend/app/service/youzan/client.py`; `backend/app/service/youzan/product_reconciler.py`; `backend/tests/service/youzan/test_client_gateway_errors.py`; `backend/tests/service/youzan/test_product_reconciler.py`
- next_time_signal: 外部平台客户端把“网关错误”与“空业务结果”合并处理时，先补一条“错误码不得等价于空数据”的回归用例；目录级同步任务上线前必须先有“上游空集合不得整批下架”的保护。
- external_action: 需在有赞应用中心控制台把调用方公网 IP 加入白名单后再重跑同步，否则分类-商品关联、商品分组名与商品刷新仍不可用；该动作未完成前 `/api/v1/miniapp/product-categories` 继续返回空数组。

## M-20260914-001：群内登记页把时间基线固化在模块加载时，跨过 17:00 或零点后当天标记与可选日期过期

- status: guarded
- first_seen: 2026-09-14
- severity: medium
- symptom: 北京时间 00:01 运行 `devtools:same-day-scheduling` 时，页面 `dateStartValue`/`selectedDateValue` 已是今天 `2026-09-14`，但 `isSameDayRegistration=false`，且“当天登记由门店客服确认制作与履约安排”提示不显示；审计报“当天登记状态不符合当前北京时间：实际 false，预期 true”。
- root_cause: `pages/group-registration/index.ts` 的 `data` 默认值在模块求值时执行 `getCheckoutDateStart()`/`buildDefaultExpectTime()`/`buildCheckoutHourOptions()`/`isCheckoutDateToday()`，一个进程只求值一次；`onLoad` 只重算 `desiredTime` 与 `selectedDateValue`，日期起点、小时选项与当天标记都停留在小程序启动时刻。当次进程在 23:5x 启动，`isCheckoutDateToday("2026-09-14")` 在跨零点前算得 false，进入新的一天后不再更新。
- impact: 一是不展示“当天登记须客服确认”的提示，顾客与门店对当天单的预期不一致；二是 17:00 前启动的进程在 17:00 后打开登记页时，日期选择器仍以今天为起点、小时选项仍包含已过时段，顾客可提交违反 17:00 截单的当天登记；`backend/app/service/customer/group_operations.py` 只按字符串保存 `desiredTime` 且不做截单校验，违规登记会直接进入门店待办。
- fix: 新增 `REGISTRATION_BUSINESS_HOURS` 常量与 `buildRegistrationSchedule(expectTime?, now)`，用 `resolveCheckoutSchedule()` 一次产出日期起点/终点、可选小时、选中索引、`desiredTime` 与当天标记；`data`、`onLoad`、`onShow` 三处都按当前北京时间重建，`onShow` 会把过期选择抬到最早可预约时间。
- update_20260914: 群内登记服务端已补同源履约校验：`desiredTime` 改为必填，并在写入前调用共享 `OrderScheduleService.validate_expect_time()`；该服务与订单预约共用北京时间、当天 17:00 截单和营业时段规则，`lifespan_services.py` 向订单与客户群登记注入同一实例。
- new_guardrail: 页面中任何依赖当前时间的 `data` 默认值必须在 `onLoad`/`onShow` 重建，禁止只在模块求值时算一次；`check-miniapp.mjs` 新增 `checkRegistrationScheduleRefresh()` 并要求登记页营业时段来自单一常量；`verify-devtools-same-day-scheduling.cjs` 新增“当天标记必须等于所选日期是否为今天”“日期必须落在可选区间内”与“注入过期状态后调用 onShow 必须重建基线”三项断言。
- update_guardrail: 群内登记服务端必须引用订单同一套 `OrderScheduleService`，禁止页面校验或字符串保存替代后端截单校验；新增登记接口用例必须覆盖缺少时间、17:00 后当天登记和营业时段外三类拒绝。
- verification: `devtools:same-day-scheduling` PASS（`promptVisible=true`、`sameDayFlagMatchesSelection=true`、`dateWithinRange=true`；`stale-state-repair` 后 `dateStartValue=2026-09-14`、`hourOptions=09..19`）；修复前运行态实测 `isSameDayRegistration=false`，修复后为 `true`；`check:miniapp`、`typecheck` 通过；把 `onShow` 临时改名可复现静态守卫失败。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `miniapp/miniprogram/pages/group-registration/index.ts`; `miniapp/scripts/check-miniapp.mjs`; `miniapp/scripts/verify-devtools-same-day-scheduling.cjs`; `miniapp/reports/devtools/same-day-scheduling-audit.json`
- linked_files_update: `backend/app/service/order/schedule.py`; `backend/app/service/customer/group_operations.py`; `backend/app/service/order/application.py`; `backend/app/lifespan_services.py`; `backend/tests/service/test_customer_group_operations.py`; `backend/tests/api/test_customer_group_api.py`; `backend/tests/test_lifespan_routes_services.py`; `miniapp/docs/api-contract.md`
- update_verification: 后端定向套件 65/65 通过（客户群服务/API、lifespan 服务装配、订单服务域与小程序订单 API）；相关 7 个 Python 文件 `ruff check` 通过；本地最新代码后端 PID 32728 在 `127.0.0.1:7001` 返回 `/health=ok`，DevTools `wx.login` 与订单/地址/聊天受保护接口 4/4 PASS，`devtools:same-day-scheduling` PASS，`devtools:registration-policy` 页面断言全部通过但 Windows 锁屏导致截图证据 BLOCKED。
- next_time_signal: 审计在换日或跨截单点后报“当天标记与北京时间不符”时，先查该页时间基线是否只在模块加载时求值，而不是先改断言。

## M-20260914-002：结算审计注入自提态时复用配送字段和金额，生成自相矛盾截图

- status: guarded
- first_seen: 2026-09-14
- severity: medium
- symptom: `final-checkout-pickup-address.png` 显示日期/小时为 `2026-09-14 18:00`，但“期望时间”仍为 `2026-09-10 15:00`；自提模式下“自提备注”填入配送地址，且运费与实付估算继续沿用配送报价 `¥26.00 / ¥224.00`。页面断言虽然 PASS，截图却无法作为自提态视觉证据。
- root_cause: `verify-devtools-checkout-delivery-states.cjs` 的 `applyState()` 写死 `expectTime`，只调用 `refreshSubmitState()`，没有先调用 `syncExpectTimeSchedule()` 重建日期、小时和分钟选择器；同时无论自提还是配送都写入同一个配送地址，自提截图复用了 quoted 配送场景的运费和实付金额。
- impact: 审计报告会把夹具污染造成的矛盾状态误认为产品缺陷，或者把未验证的自提页面当成视觉通过；截图不能证明真实自提态的门店地址、备注、运费和预约时间一致性。
- fix: `applyState()` 改为按北京时间生成明天 15:00 的有效预约值，注入后先调用 `syncExpectTimeSchedule()`，再调用 `refreshEstimate()`/`refreshSubmitState()`；自提态清空配送地址与地址摘要，金额重置为自提免运费和 `¥198.00`；新增自提态预约预览与选择器一致、备注为空、运费状态免运费、实付估算不含配送费四项断言；自提截图改写到新路径 `final-checkout-pickup-state.png`，旧图不再被新报告引用。
- new_guardrail: 结算审计任何状态注入后都必须统一重算预约选择器、金额估算与提交态；配送态与自提态必须分别注入地址、运费状态和金额，禁止复用另一种履约方式的夹具数据。
- verification: 修改后 `node --check scripts/verify-devtools-checkout-delivery-states.cjs` 通过；`npm run check:miniapp`、`npm run typecheck` 通过；连接本地后端 `127.0.0.1:7001` 与 DevTools `9420` 跑 `devtools:checkout-delivery-states`，页面断言 `errors=[]`，自提态实测 `expectTime=2026-09-15 15:00`、`pickerExpectTime=2026-09-15 15:00`、`deliveryAddress=""`、`deliveryFeeText=免运费`、`estimateRemainFenText=¥198.00`；Windows 锁屏使 7 张截图 3 次重试均失败，整轮按环境阻塞（BLOCKED）记录。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `miniapp/scripts/verify-devtools-checkout-delivery-states.cjs`; `miniapp/reports/devtools/checkout-delivery-state-audit.json`
- next_time_signal: 结算审计截图与页面数据出现时间或金额不一致时，先检查审计夹具是否绕过页面的 `syncExpectTimeSchedule()` 和金额重算，再判断产品缺陷。

## M-20260914-003：分类 ID 的 JSON 片段参数把引号与百分号顺序写反，分类商品恒为空

- status: guarded
- first_seen: 2026-09-14
- severity: medium
- symptom: 新增商品搜索分页后，`list_products_by_category_key()` 和 `count_products_by_category_key()` 对确有命中的 `tag_ids_json` 始终返回空；5 项分类目录定向测试失败，关键词和分页之外的既有分类链路同时回归。
- root_cause: 错误的 `f'%"{raw_id}%"'` 生成字符顺序 `%`、`"`、`254005045`、`%`、`"`；正确写法应为 `f'%"{raw_id}"%'`，生成 `%`、`"`、`254005045`、`"`、`%`。两种写法在源码和日志中视觉接近，`_resolve_category_column()`、SQL 文本和参数类型均正确，导致排查极易误判为有赞数据或 SQLite 行为。
- impact: 所有 `youzan-*` 分类商品的接口返回空数组且 `meta.total=0`，会直接让商品目录分类导航失效；若缺少行为级分类测试，静态检查无法发现。
- fix: 两个仓库方法统一改为正确的 `f'%"{raw_id}"%'` 参数生成，并增加 API 分类响应 `meta.total=1` 断言，同时保留关键词搜索与 offset 分页用例。
- new_guardrail: 分类过滤必须有真实命中商品的 repository/service/API 回归链路同时覆盖列表与计数；调试“SQL 文本相同但结果不同”时，必须比较参数逐字符顺序，不得只看 `repr` 或 trace 渲染。
- verification: 修复前 21 项定向测试中 5 项失败；修复后 `python -B -m pytest backend/tests/service/test_catalog.py backend/tests/api/test_miniapp_catalog_api.py -q --no-cov` 21/21 通过；相关 6 个 Python 文件 `ruff check` 通过；商品页改用服务端分页后再以真实接口复核：`GET /api/v1/miniapp/products?keyword=曲奇&limit=30` 命中 3 款、`limit=3&offset=1&sort=popular` 返回 `meta.total=310`，`devtools:product-search` 19 项 PASS。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `backend/app/repository/youzan_repo.py`; `backend/tests/service/test_catalog.py`; `backend/tests/api/test_miniapp_catalog_api.py`
- next_time_signal: 分类接口出现“分类存在但商品为空”时，先断言真实商品命中与 `meta.total`，并逐字符检查 JSON LIKE 参数；不要把参数顺序错误归因到有赞标签映射或 SQLite 查询计划。

## M-20260914-004：静态检查器的 Page 正则未锚定行首，被 listProductPage({ 调用骗走方法扫描区域

- status: guarded
- first_seen: 2026-09-14
- severity: low
- symptom: 商品页改为服务端分页后，`npm run check:miniapp` 报 `pages/products/index.ts shows page-fixed-safe__home but does not define goHome` 与 `wxml binds "goHome" but ... does not define it`，但页面里确实定义了 `goHome`；同一轮还有 3 项基于页面方法的既有检查同时报错。
- root_cause: `extractPageMethods()` 用未锚定的 `/Page\s*\(\s*\{/` 定位页面定义，`listProductPage({ limit: ... })` 这类以 `Page(` 结尾的 service 调用同样命中，页面体从调用处开始截取；定义在调用之前的 `goHome`、`onLoad` 等方法全部不在扫描范围内。
- impact: 方法存在性检查会误报缺失，页面方法被截断后“本该报错的真缺失”也可能被放过；本次靠报错与源码矛盾才发现，否那么会误导成页面真的没写 `goHome`。
- fix: 页面定义正则锚定行首并支持可选泛型（`^\s*Page(?:<[^>]+>)?\s*\(\s*\{`），同时把商品分页服务更名为 `fetchProductListing`，不再让服务名与页面定义共享 `Page(` 字面量。
- new_guardrail: 静态检查器提取页面定义必须锚定行首 `Page`；新增以 `Page` 结尾的 service 函数或新增页面方法后，必须先跑 `npm run check:miniapp` 验证方法提取范围。
- verification: 修复后 `npm run check:miniapp` 通过（15 页、15 路由）；`devtools:product-search` 19 项 PASS（新增 `catalog-first-page`、`catalog-fixture-restore`）；`npm run typecheck` 通过。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `miniapp/scripts/check-miniapp.mjs`; `miniapp/miniprogram/pages/products/index.ts`; `miniapp/miniprogram/services/products.ts`
- next_time_signal: 再遇到“文件里明确写了 X 方法却报未定义”时，先查静态检查器的页面定义正则是否被其它 `Page(` 调用截断，不要误判为页面漏实现。

## M-20260914-005：购物车数量为 1 时减号渲染成 ✕，减量与删除语义混淆

- status: guarded
- first_seen: 2026-09-14
- severity: low
- symptom: 购物车商品行数量为 1 时，减量控件渲染为 `✕`；顾客会把它理解为“立即删除”，实际点击后还会再弹一次移除确认，操作预期与结果不一致。
- root_cause: 页面用 `{{item.quantity === 1 ? '✕' : '-'}}` 把“减到 0 需要确认删除”的实现细节直接映射成了图标变化，控件本身没有区分“减量”和“删除”两种语义。
- impact: 顾客在结算前调整数量时容易误判按钮作用，可能放弃修改或在不理解后果的情况下点掉确认框，购物车内容与预期不一致。
- fix: 减量控件固定渲染 `-`，移除语义仍由数量为 1 时的确认弹窗承担；`check-miniapp.mjs` 新增 `checkCartDecreaseButtonSemantics()` 静态守卫，禁止减号块出现 `✕` 且必须固定渲染 `-`。
- new_guardrail: 同一个控件不得因数量边界改变符号语义；数量为 1 时的减量动作与删除入口必须分别可预期，并在运行态断言中同时验证文案与触控尺寸。
- verification: `devtools:product-purchase-path` PASS，新增检查 `cart-stepper-minus-at-one` 记录 `quantity=1`、`text="-"`、`size=45x45`；`npm run check:miniapp`、`npm run typecheck`、`devtools:verify-commerce-flows`、`scan:button-touch-targets`（13 页 46 选择器）均通过。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `miniapp/miniprogram/pages/cart/index.wxml`; `miniapp/scripts/check-miniapp.mjs`; `miniapp/scripts/verify-devtools-product-purchase-path.cjs`
- next_time_signal: 任何步进器、开关或计数器在边界值改变图标、文案时，先确认它没有把“另一个动作”伪装成当前动作；删除语义只允许出现在删除入口或明确确认流程中。

## M-20260914-006：全页审计用搜索残留态与空态冒充商品页和商品详情视觉证据

- status: guarded
- first_seen: 2026-09-14
- severity: medium
- symptom: 全页审计产出的 `final-products.png` 实际是关键词搜索后的结果态，`final-product-detail.png` 实际是“商品不存在”空态；两者都不代表页面默认展示，却一直被当作页面视觉证据引用。
- root_cause: 商品页是 tabBar 页面，审计用 `switchTab` 复用上一轮搜索留下的页面实例，脚本没有复位搜索与滚动状态；商品详情页用 `reLaunch('/pages/product-detail/index')` 未携带真实商品 `id`，页面按空 `id` 分支渲染空态。
- impact: 视觉证据与目标页面状态不符：默认态排版问题会被搜索态掩盖，商品详情的悬浮栏与底部操作栏等真实商品断言因空态被整段跳过（本轮修复取证后立即暴露出悬浮栏背景断言此前从未真正执行）。
- fix: `verify-all-15-pages-devtools.cjs` 新增 `preparePageState()`：商品页先 `resetSearchState()` 并断言 `searchText` 为空、`activeProducts` 非空，再回滚到页面顶部；商品页滚动区是原生页面滚动（`view` 无 `scrollTo`），滚动复位回落 `wx.pageScrollTo`；商品详情页先从 `/api/v1/miniapp/products` 选一个真实在售商品 `id` 带参导航，未渲染真实商品直接报错。
- new_guardrail: 截图类证据必须先声明并断言“取证状态”；tabBar 页面截图前必须复位搜索、分类和滚动残留；实体详情页必须使用真实实体 ID，禁止用空态截图充当详情页视觉证据。
- verification: 报告 `defaultState` 记录商品页 `searchText=""`、`productCount=12`、`catalogTotal=310`，详情页 `productId=3610295088`、`canPurchase=true`；`devtools:verify-all-pages` 15/15 页 + 8/8 未登录态 PASS，截图 `final-products.png`、`final-product-detail.png` 逐张复核确认为默认目录与真实商品。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `miniapp/scripts/verify-all-15-pages-devtools.cjs`; `miniapp/reports/devtools/all-pages-devtools-audit.json`; `miniapp/reports/devtools/final-products.png`; `miniapp/reports/devtools/final-product-detail.png`
- next_time_signal: 看到“某页断言一直通过”先确认它到底渲染了哪种业务状态；断言被空态、搜索态或夹具态包裹时，要显式标注跳过原因并补一条默认态取证。

## M-20260914-007：商品详情悬浮栏背景断言读到过渡中间值，把正常动画判成透明缺陷

- status: guarded
- first_seen: 2026-09-14
- severity: low
- symptom: r49 首次执行真实商品取证时，滚动断言报“悬浮栏背景仍不透明可穿透：rgba(0, 0, 0, 0)”；同一元素在过渡结束后为 `rgb(255, 255, 255)`。r52 串行复跑时反向断言又复现：类名已恢复透明，但读取值停在 `rgba(255, 255, 255, 0.533)`。
- root_cause: `.detail-nav` 声明 `transition: background-color 0.18s ease`，DevTools 对合成层背景色的计算样式刷新存在延迟；单次读取会落在过渡起点，后续仅靠轮询仍可能在 3s 预算内取不到完全透明的稳定值。该样式又是“首屏透明 / 滚动实底”的功能态，不应依赖动画收敛。
- impact: 正常动画会被记录成“可穿透”或“仍为实底”两种相反误报，污染全页审计结论，并把排查方向引向并不存在的 CSS 覆盖问题。
- fix: 删除悬浮栏背景色过渡，只保留 `box-shadow 0.18s ease`；滚动状态通过 class 立即切换，背景色确定性收敛到 `rgb(255, 255, 255)` 或 `rgba(0, 0, 0, 0)`。保留 `waitForDetailNavBackground()` 轮询作为双向断言保护，并在 `check-miniapp.mjs` 增加“background 不得参与 transition”的静态守卫。
- new_guardrail: 功能状态样式必须立即切换，不能依赖过渡动画收敛；动画只用于非语义装饰。若样式断言在手工访问正常时失败，先区分“过渡中间值”“计算样式缓存滞后”“真实覆盖”，再决定是否移除动画。
- verification: r52 的 `devtools:verify-all-pages` 15/15 页 + 8/8 未登录态 PASS，报告记录 `scrolledBackground=rgb(255, 255, 255)`、`restoredClass` 无实底、`restoredBackground=rgba(0, 0, 0, 0)`、`errors=[]`；`npm run check:miniapp` 通过。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `miniapp/scripts/verify-all-15-pages-devtools.cjs`; `miniapp/miniprogram/pages/product-detail/index.wxss`; `miniapp/scripts/check-miniapp.mjs`; `miniapp/reports/devtools/all-pages-devtools-audit.json`
- next_time_signal: 同一个状态样式通过一次后又以中间值复发时，继续加长等待不是根治；要判断该动画是否值得保留，功能态优先使用确定性切换。

## M-20260914-008：DevTools 审计未校验后端与自动化端口前置条件，环境掉线仍按页面失败开跑

- status: guarded
- first_seen: 2026-09-14
- severity: medium
- symptom: 全页审计运行中 Node 侧 `fetch` 到 `http://127.0.0.1:7001` 持续 `fetch failed`，商品页默认态报“未渲染商品列表”、商品详情取证被跳过；随后 `ws://127.0.0.1:9420` 也无法连接，开发者工具实例已退出。用户在会话中两次提醒“先启动后端再测”。
- root_cause: 审计脚本只对自动化端口做连接探测，没有对本地后端 `/health` 做前置校验；后端进程与 DevTools 自动化端口在长会话中都会掉线，而脚本继续按页面缺陷写入报告。
- impact: 环境缺服务会被记成页面失败，覆盖上一份有效 PASS 报告；每轮浪费约 4-5 分钟且可能把环境问题误判为产品缺陷。
- fix: 重启本地后端（`python -B -m uvicorn --app-dir backend app.main:app --host 127.0.0.1 --port 7001`）并通过 `/health` 校验；用 `cli.bat auto --project D:\Project\YunxiBakery\miniapp --trust-project --port 10701 --auto-port 9420` 恢复自动化端口；`verify-all-15-pages-devtools.cjs` 新增 `probeBackendHealth()` 前置门禁，不通过时 `exit 2` 且不写报告，必要时用 `MINIAPP_ALLOW_BACKEND_DOWN=1` 显式降级。
- new_guardrail: 运行 DevTools 审计前先校验 `http://127.0.0.1:7001/health` 与 `ws://127.0.0.1:9420` 两项前置条件；任一不可用时只记环境阻塞并保留上一份报告，禁止用环境故障覆盖有效证据。
- verification: 故意指向 `http://127.0.0.1:7999` 复跑，脚本 `EXIT=2` 且报告 `generatedAt`/`status` 与上一份 PASS 完全一致；恢复后端与 9420 后 `devtools:verify-all-pages` 15/15 页 + 8/8 未登录态 PASS。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `miniapp/scripts/verify-all-15-pages-devtools.cjs`; `miniapp/reports/devtools/all-pages-devtools-audit.json`
- next_time_signal: 审计出现大面积 `fetch failed`、空列表或路由异常时，先核对后端健康与自动化端口，再决定是否归因到页面代码。

## M-20260914-009：DevTools 单击派发偶发丢失，展示型商品审计把正常页面判成未跳转

- status: guarded
- first_seen: 2026-09-14
- severity: low
- symptom: 新增的 `devtools:display-only-products` 首跑报“点击展示型商品的‘查看’没有进入商品详情”，但同一份报告里目录卡 `actionText=查看`、`badgeText=仅供展示`、购物车为空，其余断言全部通过；独立脚本复现同一元素时 `tap()` 一次即跳转。
- root_cause: DevTools 自动化 `element.tap()` 在搜索结果刚渲染、卡片仍处于 `stagger-fade-in` 动画时偶发只派发坐标而未触发事件；审计脚本只点一次并在 6s 内等待路由变化，取不到就判失败。
- impact: 正常页面动作被记成产品缺陷，且失败会覆盖上一份有效 PASS 报告，把排查方向引向并不存在的跳转逻辑问题。
- fix: 审计改为最多 3 次真实点击（每次独立等待 3s），仍不跳转才回退 `page.callMethod("quickAddProduct", { currentTarget: { dataset: { id } } })`，并把 `actionPath`、`tapAttempts`、`tapDispatchErrors` 写入报告。
- new_guardrail: DevTools 点击类断言必须允许“事件层抖动”重试并记录实际生效路径；`tap` 未生效时优先回退页面自身方法，不得凭一次未派发就定成页面缺陷。
- verification: 复跑 `npm run devtools:display-only-products` PASS，报告记录 `actionPath=tap`、`tapAttempts=2`、`tapDispatchErrors=[]`、`navigatedToDetail=true`、`cartProductIds=[]`，截图 `display-only-product-detail.png` 采集成功。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `miniapp/scripts/verify-devtools-display-only-products.cjs`; `miniapp/reports/devtools/display-only-products-audit.json`
- next_time_signal: DevTools 里“点了一次没反应”先看元素是否仍在入场动画/重渲染窗口内；点击断言应重试并记录路径，而不是单次定性。

## M-20260914-010：触控扫描默认自启 DevTools，已有自动化端口时反而连接失败

- status: guarded
- first_seen: 2026-09-14
- severity: low
- symptom: 整套串行回归最后一步 `npm run scan:button-touch-targets` 退出码 2：`Failed to launch wechat web devTools, please make sure cliPath is correctly specified`；同一时刻 `ws://127.0.0.1:9420` 仍由已打开的开发者工具监听。
- root_cause: 该脚本只在显式设置 `MINIAPP_AUTOMATOR_WS` 时 `automator.connect`，否则走 `automator.launch(cliPath …)` 重新拉起实例；默认 `cliPath` 与本机安装路径不一致，且已有实例时重复启动并无必要。
- impact: 已打开的自动化端口可用却整轮扫描失败，容易被误判成触控目标缺陷或 DevTools 安装损坏。
- fix: 复跑时显式传入 `MINIAPP_AUTOMATOR_WS=ws://127.0.0.1:9420` 连接既有实例，扫描通过（13 页 47 选择器）。
- new_guardrail: 运行需要 DevTools 的审计/扫描前先探测 `ws://127.0.0.1:9420`；端口已监听时统一用 `MINIAPP_AUTOMATOR_WS` 复用实例，不依赖默认 `cliPath` 自启。
- verification: `MINIAPP_AUTOMATOR_WS=ws://127.0.0.1:9420 npm run scan:button-touch-targets` PASS，报告 `miniapp/reports/button-visual/button-touch-targets-20260914-033503.json`：47 选择器 / 13 页。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `miniapp/scripts/scan-miniapp-button-touch-targets.mjs`; `miniapp/reports/button-visual/button-touch-targets-20260914-033503.json`
- next_time_signal: 扫描/审计报 `Failed to launch … cliPath` 时先查 9420 是否已经在监听；端口可用就复用，不要去改安装路径。

## M-20260914-011：定向 pytest 被全局覆盖率阈值拦截，退出码 1 被误读成用例失败

- status: guarded
- first_seen: 2026-09-14
- severity: low
- symptom: `python -B -m pytest -q tests/service/test_catalog.py tests/service/test_order.py` 退出码 1，输出中没有断言失败，实际是全局 `addopts` 的覆盖率门槛未达标，并额外写出 `backend/coverage.xml` 与 `backend/htmlcov/`。
- root_cause: 仓库 pytest 配置默认带 coverage 与 `--cov-fail-under`；定向只跑少量文件时总覆盖率必然低于门槛，失败与代码缺陷无关。
- impact: 定向回归被误报为失败，易触发无谓排查；每轮还会附带生成覆盖率产物。
- fix: 定向复跑统一追加 `-o addopts=""`（本轮 48/48 通过）；覆盖率只在全量/上线候选阶段按测试节奏执行；本轮生成的 `backend/coverage.xml`、`backend/htmlcov/` 已按白名单定向清理。
- new_guardrail: 定向 pytest 一律显式关闭全局 addopts；看到仅 coverage 摘要、没有 failed 用例时，先确认退出码来源再改代码。
- verification: `python -B -m pytest -q -o addopts="" tests/service/test_catalog.py tests/service/test_order.py` → 48 passed；`backend/coverage.xml` 与 `backend/htmlcov` 删除后确认 `Test-Path=False`。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `backend/tests/service/test_catalog.py`; `backend/tests/service/test_order.py`; `backend/pytest.ini`
- next_time_signal: 定向测试失败但输出只有 coverage 百分比时，先加 `-o addopts=""` 重跑，不要把覆盖率门槛当成用例失败。

## M-20260914-012：非卖品的同步占位价与库存被当成真实售价展示

- status: guarded
- first_seen: 2026-09-14
- severity: medium
- symptom: 逐张目视复核 r50 截图时发现，商品搜索结果里的“非卖品仅展示”条目仍显示同步占位价（¥99999.00 / ¥1600.00 / ¥1140.00）与“库存充足”，商品详情标题区也显示“门店自提价 ¥99999.00”和“库存充足”；接口对这些商品返回 `priceFen=9999900`、`stock=99999`、`soldText=库存充足`。
- root_cause: r50 只在动作层拦截了下单（加购/预订），价格与库存仍直接取有赞同步字段；有赞用极端占位价与库存表示“非卖品/虚拟价”，读模型没有区分“展示占位符”与“可售价”。商品详情搭配推荐位同样直接 `formatFen(item.priceFen)` 渲染。
- impact: 用户会把占位价与“库存充足”当成真实售价与可售状态，形成错误的下单预期；同时与“仅供展示”文案自相矛盾，削弱商品信息可信度。
- fix: `utils/bakery.ts` 新增 `getProductPriceText()`，非卖品统一输出“非卖品”；首页、商品列表、购物车推荐、详情页搭配推荐全部改走该口径；商品列表非卖品隐藏库存胶囊；详情页 `detail-meta`（自提价 + 库存文案）改由 `!isDisplayOnly` 条件渲染；购物车推荐与详情搭配推荐过滤 `isPurchasable=false` 商品（候选拉取条数上调以便回填）；`check-miniapp.mjs` 展示型商品守卫新增价格、样式类、库存、详情元信息与推荐位过滤断言；`devtools:display-only-products` 新增目录卡价格渲染断言与详情标题区文本断言。
- new_guardrail: 同步数据里的极端占位价/库存不得成为顾客可见的售价与库存事实；非卖品价格必须走统一 `getProductPriceText` 口径，推荐位只承载可下单商品。
- verification: `npm run typecheck`、`npm run test:bakery`（9/9）、`npm run check:miniapp`（15 页 / 15 路由）通过；`npm run devtools:display-only-products` PASS，报告 `reports/devtools/display-only-products-audit.json`：4 张展示型商品卡的 `priceText=非卖品`、`renderedWithFakePrice=[]`、详情页 `hasDetailMeta=false`，截图 `evidence-display-only-list-after.png` 与 `display-only-product-detail.png` 目视确认无 ¥ 与“库存充足”。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `miniapp/miniprogram/utils/bakery.ts`; `miniapp/miniprogram/pages/home/index.ts`; `miniapp/miniprogram/pages/products/index.ts`; `miniapp/miniprogram/pages/cart/index.ts`; `miniapp/miniprogram/pages/product-detail/index.ts`; `miniapp/miniprogram/pages/product-detail/index.wxml`; `miniapp/scripts/check-miniapp.mjs`; `miniapp/scripts/verify-devtools-display-only-products.cjs`
- next_time_signal: 页面只要出现 `99999` / `9999900` 这类极端数值，先确认它是不是有赞占位值，再决定是否展示。

## M-20260914-013：搜索空态文案晚一帧渲染，审计单次读取误报缺空态

- status: guarded
- first_seen: 2026-09-14
- severity: low
- symptom: 串行回归里的 `devtools:product-search` 首轮 `exit=1`，报“无结果搜索没有给出可见空态提示”，报告同时记录 `emptyStateExists=true`、`copy=[]`；同一脚本单独复跑 19 项全过，空态文案正常显示“暂时没有匹配商品 / 换个关键词试试，或先看看全部商品”。
- root_cause: 脚本在空态元素刚出现时立刻读取 `.products-empty text`；DevTools 已能查到元素，但文本节点尚未渲染完成，单次读取得到空数组。
- impact: 正常空态被记成缺提示，覆盖上一份有效 PASS 报告，并把排查方向引向并不存在的文案缺失。
- fix: 该断言改为先轮询（5s 预算、250ms 间隔）直到 `.products-empty text` 出现非空文案，再读取快照做断言。
- new_guardrail: 断言渲染文本时必须轮询到非空稳定值，禁止用元素刚出现时的单次读取给文案定性。
- verification: `MINIAPP_AUTOMATOR_WS=ws://127.0.0.1:9420 npm run devtools:product-search` 复跑 PASS，包含 `search-empty-state` 与 `search-empty-state-recovery`。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `miniapp/scripts/verify-devtools-product-search.cjs`; `miniapp/reports/devtools/product-search-audit.json`
- next_time_signal: DevTools 审计出现“元素存在但文案为空”时，先按渲染时序处理，不要直接判成页面缺文案。

## M-20260914-014：日志工具把条目写进旧镜像并顺带改写历史行结构

- status: guarded
- first_seen: 2026-09-14
- severity: low
- symptom: 运行 `python -B backend/scripts/append_logbook.py --type fix ...` 时脚本报告“✅ 条目已追加到 LOGBOOK.md”，但仓库根 `LOGBOOK.md` 没有变化；实际写入了 `backend/LOGBOOK.md`（monorepo 迁移前的旧镜像），并且该旧文件里一处含内嵌回车的历史行被拆成两行，产生无关 diff。
- root_cause: 脚本按旧单仓布局用 `Path(__file__).resolve().parent.parent` 推断仓库根，得到 `backend/`；monorepo 整合后权威日志在仓库根目录，其它治理脚本已统一改为 `parents[2]`。
- impact: 日志写进已废弃的旧镜像，权威 `LOGBOOK.md` 缺条目；同时会改写旧文件行结构，形成与本轮无关的 diff，干扰后续收口审计。
- fix: `LOGBOOK_FILE` 改为 `ROOT.parent / "LOGBOOK.md"`（版本号继续取 `backend/VERSION`），并加中文注释说明路径；误写进 `backend/LOGBOOK.md` 的条目用 `git diff -- backend/LOGBOOK.md | git apply -R -` 精确回退，不用破坏性 Git 命令。
- new_guardrail: 治理脚本改动后必须核对实际写入路径与 `git status`；发现写进旧镜像时先精确回退该文件，再修正脚本路径。
- verification: 修正后重跑脚本，r51 条目落在根目录 `LOGBOOK.md` 顶部（第 1-14 行）；`git status --porcelain -- backend/LOGBOOK.md` 无输出。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `backend/scripts/append_logbook.py`; `LOGBOOK.md`; `backend/LOGBOOK.md`
- next_time_signal: 脚本提示成功但目标文件没变化时，先确认它解析出的仓库根，再看 `git status` 里多出来的文件。

## M-20260914-015：商品详情底部服务入口用单汉字冒充图标

- status: guarded
- first_seen: 2026-09-14
- severity: low
- symptom: 商品详情页底部服务入口用单个汉字“询”“购”充当图标，与相邻的“加入购物车”“立即购买”按钮挤在同一横排；目视复核时像未替换的占位稿，顾客也难以分辨这两项是次要服务入口还是购买动作。
- root_cause: 首版把服务入口做成文字缩写占位，没有采用与全局 TabBar 一致的标准线性图标，也没有补充无障碍标签与运行态尺寸断言。
- impact: 底部操作区视觉像未完成稿，服务入口与购买动作的主次关系不清晰；缺少 aria-label 时读屏用户只能听到孤立汉字。
- fix: `pages/product-detail/index.wxml` 改用标准线性聊天与购物车图标，保留“客服 / 购物车”文字标签并补 `aria-label`；`index.wxss` 复用全局 TabBar 图标风格，运行态尺寸 19×19px；`check-miniapp.mjs` 新增禁止“询 / 购”单汉字回归的静态断言；`verify-devtools-product-purchase-path.cjs` 新增运行态断言（2 个无文字图标、背景图非空、尺寸不小于 18px）。
- new_guardrail: 底部服务入口必须使用标准图标并带可读标签，禁止用单汉字缩写充当图标；新增图标入口必须同时有静态守卫与运行态尺寸断言。
- verification: `npm run devtools:product-purchase-path` PASS：服务入口图标 2 个、无文字、实测 19×19、底栏间距 14.44px；截图 `miniapp/reports/devtools/final-product-detail-footer.png` 目视确认图标与标签正常。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `miniapp/miniprogram/pages/product-detail/index.wxml`; `miniapp/miniprogram/pages/product-detail/index.wxss`; `miniapp/scripts/check-miniapp.mjs`; `miniapp/scripts/verify-devtools-product-purchase-path.cjs`
- next_time_signal: 页面里出现单字按钮或单字入口（询、购、券、礼）时，先确认它是业务缩写还是占位符，再决定是否替换为标准图标加标签。

## M-20260914-016：只有行政区的地址可以保存并进入履约链路

- status: guarded
- first_seen: 2026-09-14
- severity: medium
- symptom: 地址簿里存在只有“北京市东城区”“北京市朝阳区”的地址记录；前端页面无任何提示，后端保存接口也只校验非空，这类地址可以一路进入结账与履约链路。
- root_cause: 地址保存只校验字段非空，没有定义最小可履约粒度；历史数据按同一宽松口径写入后，读取端也没有把“信息不完整”作为一种可见状态暴露给顾客。
- impact: 闪送按收货地址计算运费与派单，行政区级地址无法定位到取送点，会造成报价失真与配送失败；顾客在结算前也得不到补充地址的提示。
- fix: 新增 `utils/address.ts`（`isAddressDetailedEnough` / `getAddressDetailText`）定义最小粒度；`utils/address-book.ts` 在保存前要求补充小区、楼栋或门牌号；地址页对历史不完整地址标记 `needsDetailHint` 并提示“地址信息不完整，请编辑补充小区、楼栋或门牌号”，不删除也不改写旧数据；后端 `service/customer/address_support.py` 用同一口径拒绝行政区-only 地址。
- new_guardrail: 行政区-only 地址不得保存，也不得进入结账与履约链路；历史不完整数据必须以可见提示暴露，禁止静默放行或静默改写。
- verification: 重启本地后端后实调 `POST /api/v1/miniapp/addresses`：`北京市东城区` 返回 `400`（`请补充小区、楼栋或门牌号`），完整地址返回 `200` 且测试记录已删除；`npm run test:address`（2/2）与地址相关定向 pytest（17/17）通过；登录态截图 `miniapp/reports/devtools/evidence-address-completeness.png` 显示两条历史地址均出现完整性警告。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `miniapp/miniprogram/utils/address.ts`; `miniapp/miniprogram/utils/address-book.ts`; `miniapp/miniprogram/pages/address/index.ts`; `miniapp/miniprogram/pages/address/index.wxml`; `backend/app/service/customer/address_support.py`; `backend/tests/service/test_customer_address.py`
- next_time_signal: 地址、取件点或闪送报价相关字段只填到市/区级时，先按不可履约处理并要求补全，不要等到派单失败再暴露。

## M-20260914-017：结算与群内登记的日期/时分选择器没有可点击提示

- status: guarded
- first_seen: 2026-09-14
- severity: medium
- symptom: 逐页目视复核结算页与群内登记页截图时发现，“日期 / 小时 / 分钟”三个 picker 与只读的“期望时间：2026-09-15 15:00”预览渲染成完全相同的方框；页面上没有任何迹象能区分前三项可点击、最后一项不可点击。
- root_cause: picker 的 face 只渲染了纯文字，没有下拉指示；`.time-picker` 与 `.time-preview` 共用同一组背景、边框和字号样式，可点击控件和只读结果视觉完全同构。
- impact: 预约时间是预订链路的核心输入，顾客可能直接以默认时间提交，或在页面上找不到改时间、改日期的入口；对单店预订为主的经营场景直接造成沟通成本。
- fix: 两个页面的三个 picker face 增加 `time-picker__chevron` 下拉指示并把文案包进 `time-picker__value`（超长省略）；`.time-preview` 去掉背景与边框，改为次要文字行，与可点击控件区分。
- new_guardrail: 可点击 picker 必须带可见指示，只读预览不得与可点击控件同款；新增或改造 picker 必须同时扩静态守卫与运行态断言。
- verification: `check:miniapp` 新增 `checkTimePickerAffordance()`；`devtools:checkout-delivery-states` PASS（`timeChevrons` 3 个、实测 6×6、`timePreviewBackground=rgba(0, 0, 0, 0)`）；`devtools:registration-policy` PASS（`pickerFaces=3`、`chevrons=3`、`previewBackground` 透明）；`devtools:verify-all-pages` 15/15 PASS。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `miniapp/miniprogram/pages/checkout/index.wxml`; `miniapp/miniprogram/pages/checkout/index.wxss`; `miniapp/miniprogram/pages/group-registration/index.wxml`; `miniapp/miniprogram/pages/group-registration/index.wxss`; `miniapp/scripts/check-miniapp.mjs`; `miniapp/scripts/verify-devtools-checkout-delivery-states.cjs`; `miniapp/scripts/verify-devtools-registration-policy.cjs`
- next_time_signal: 页面上出现一排外观相同、功能不同的方框（可点与只读混排）时，先按可点击性重新分类样式，再补静态与运行态断言。

## M-20260914-018：登录空态副文案只是在重复标题

- status: guarded
- first_seen: 2026-09-14
- severity: low
- symptom: 逐页目视复核未登录态截图时发现，订单页标题“登录后查看订单”配副文案“请先登录后查看订单”、地址页“登录后管理收货地址”配“请先登录后管理地址”、优惠券“登录后查看优惠券”配“登录后查看可用与已用优惠券”，副文案只把标题重复了一遍。
- root_cause: 页面初始 `data` 里已经写了带信息的登录文案，但未登录分支重新 `setData` 时又覆盖成“请先登录后……”套话；优惠券与积分则把标题改写成副文案，没有定义“副文案必须补充什么信息”。
- impact: 登录引导只提供重复信息，顾客看不到登录能得到什么，削弱转化；同时把“占位文案”痕迹留在多个页面上。
- fix: 订单→“登录后可查看制作、自提与配送进度”；订单详情→“登录后可查看金额明细与履约进度”；地址→“登录后可保存常用地址，下单直接选择”；优惠券→“登录后可查看券面、有效期与使用范围”；积分→“登录后可查看积分余额与获取、抵扣记录”。
- new_guardrail: 登录引导副文案必须补充标题之外的信息，禁止“请先登录后……”式重复；同时受单行约束，文案长度必须用全页审计复核（本次地址文案 23 字换行被审计拦下，压缩到 17 字后通过）。
- verification: `check:miniapp` 新增 `checkLoginStateHintCopy()`；`devtools:verify-all-pages` PASS（15/15 页 + 8/8 未登录态），期间先复现“地址登录引导说明文案换行（39px / 行高 19.5px）”并修复后复跑通过。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `miniapp/miniprogram/pages/orders/index.ts`; `miniapp/miniprogram/pages/order-detail/index.ts`; `miniapp/miniprogram/pages/address/index.ts`; `miniapp/miniprogram/pages/coupons/index.wxml`; `miniapp/miniprogram/pages/points/index.wxml`; `miniapp/scripts/check-miniapp.mjs`; `miniapp/scripts/verify-all-15-pages-devtools.cjs`
- next_time_signal: 改任何空态副文案前先确认它是否只是标题改写，并检查目标页单行宽度上限；改完必须跑全页审计而不是只跑改动的页。

## M-20260914-019：结算金额面板用“-¥0.00”表示没有抵扣

- status: guarded
- first_seen: 2026-09-14
- severity: low
- symptom: 结算页金额面板里优惠券行与余额抵扣行在未使用时显示“-¥0.00”，而相邻的积分抵扣行显示“-”，同一列出现两种“没有抵扣”的写法。
- root_cause: 优惠券与余额抵扣用模板字符串 `-${formatFen(fen)}` 直接拼接，没有区分“未抵扣”和“抵扣了 0 元”；积分行用独立的 WXML 三元表达式处理，三行各写一套。
- impact: 顾客会把“-¥0.00”读成“优惠券抵扣了 0 元”或“产生了负金额”，与下方“实付（估算）”的对应关系变得难以理解。
- fix: `utils/money.ts` 新增 `formatDeductionFen()`，抵扣额 ≤0 统一输出“-”，大于 0 输出 `-¥xx.xx`；结算页优惠券与余额抵扣统一走该函数。
- new_guardrail: 抵扣金额禁止用模板字符串直接拼接，必须走统一格式化函数；零抵扣行必须与未使用状态一致。
- verification: 新增 `npm run test:money` 3/3 PASS；`devtools:checkout-delivery-states` 新增 `checkout_deduction_placeholder` 断言并通过（`estimateCouponFen=0` → `estimateCouponFenText="-"`、`balanceDeductText="-"`）。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `miniapp/miniprogram/utils/money.ts`; `miniapp/tests/utils/money.test.ts`; `miniapp/miniprogram/pages/checkout/index.ts`; `miniapp/scripts/check-miniapp.mjs`; `miniapp/scripts/verify-devtools-checkout-delivery-states.cjs`
- next_time_signal: 金额行出现“-¥0.00”“-0.00”这类值时，先确认它是“未使用”还是“使用了但金额为零”，再决定是用占位符还是金额。

## M-20260914-020：结构化补丁把匹配正文写进 context 字段导致锚定失败

- status: guarded
- first_seen: 2026-09-14
- severity: low
- symptom: 用结构化补丁向 `ERRORS.md`、`evidence-index.md` 追加条目时连续报 `Failed to find expected lines`：一次是把要匹配的正文写进了 hunk 的 `context` 字段；另一次是 hunk 里漏掉了锚点行之间的空行与行尾逗号。
- root_cause: 结构化 hunk 的 `context` 字段是 @@ 头部说明而非待匹配内容，匹配文本必须逐行放进 `lines` 且 `op=context/remove` 的文本要与文件完全一致（含空行、缩进与逗号）；同时一个 hunk 不能跨越多处不相邻的片段。
- impact: 每次失败都要回读原文件重新确认，单个追加动作消耗多轮工具调用；在很长的治理文档上反复重试会显著消耗上下文。
- fix: 追加到文件末尾统一用“最后一行 remove + 同一行 add + 新内容 add”作锚点并让 `context` 留空；多处不相邻改动拆成多个 hunk；长行锚点先回读原文再复制。
- new_guardrail: 补丁报找不到锚点时先核对 `context` 字段与空行/逗号，不要反复改正文内容试图碰中。
- verification: 按上述写法后 `ERRORS.md`、`PROJECT-STATE.md`、`evidence-index.md`、实施计划四处追加均一次成功，并有 `check_evidence_index.py` 与开发总表门禁复核。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `ERRORS.md`; `docs/harness-engineering/core/evidence-index.md`; `PROJECT-STATE.md`
- next_time_signal: 只要补丁报“找不到期望行”，先看 `context` 是不是被当成了匹配内容，再看空行与标点是否与原文一致。

## M-20260914-021：订单详情把开发环境支付口径展示给顾客

- status: guarded
- first_seen: 2026-09-14
- severity: medium
- symptom: 订单详情“支付方式”在 mock 支付订单上直接显示“MVP 模拟支付”，截图中顾客可见区域出现内部开发词汇。
- root_cause: 页面把后端支付方法枚举 `mock` 直接映射成带项目阶段名称的字面量，没有经过顾客语言适配；静态守卫只覆盖少量工程占位文案，未覆盖支付方式。
- impact: 顾客会看到开发环境术语，降低支付信息可信度；真实微信支付、余额支付和组合支付也缺少统一、可扩展的展示口径。
- fix: `utils/order-summary.ts` 新增 `formatPaymentMethodText()`，将 `wechat/balance/combined/mock/未知值` 分别映射为“微信支付/余额支付/组合支付/门店确认/待确认”；订单详情统一通过该函数渲染；DevTools 流程审计同时断言页面不出现“MVP”或“模拟支付”。
- new_guardrail: 顾客界面不得出现“MVP 模拟支付”“模拟支付”等开发口径；支付方式必须有统一映射函数，新增支付枚举必须补映射和测试。
- verification: `test:order-summary` 覆盖五种支付方式映射；`check:miniapp` 增加顾客文案禁用项与映射函数守卫；`devtools:verify-commerce-flows` 改为用“门店确认”夹具并断言页面不含内部词汇。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `miniapp/miniprogram/utils/order-summary.ts`; `miniapp/tests/utils/order-summary.test.ts`; `miniapp/miniprogram/pages/order-detail/index.ts`; `miniapp/scripts/check-miniapp.mjs`; `miniapp/scripts/verify-miniapp-commerce-flows.cjs`
- next_time_signal: 订单、支付、退款页面出现英文枚举、`mock`、`MVP`、内部环境名时，先做顾客语言映射再加页面断言，禁止直接展示后端原始值。

## M-20260914-022：会员中心订单与服务入口用单汉字充当图标

- status: guarded
- first_seen: 2026-09-14
- severity: medium
- symptom: 会员中心“我的订单”四个入口用“付/制/送/售”单汉字放在空白方块里充当图标；“特色服务”列表用“电/微/售/协/隐”单汉字放在圆圈里。截图上这些方块基本等于空白占位，顾客看不出入口含义。
- root_cause: 订单入口与特色服务入口的数据字段是 `iconText`，页面直接渲染文字；同类问题已在商品详情底部服务入口修复过一次（M-20260914-015），但当时只改了商品详情，未把检查推广到会员中心。
- impact: 会员中心是顾客查看待付款、制作中、配送与售后进度的主入口，图标不可辨识会直接降低入口可扫描性，也重复了已经判定的“单汉字冒充图标”缺陷。
- fix: 订单入口与特色服务入口改为 `iconKey` 驱动的 9 个内联线性图标（wallet/clock/truck/rotate-ccw/phone/message-circle/shield-check/file-text/lock），装饰图标补 `aria-hidden`；`check-miniapp.mjs` 新增 `checkProfileShortcutIcons()` 守卫；`verify-all-15-pages-devtools.cjs` 不再只断言“有图标元素”，改为断言背景图标可渲染、无文字占位、渲染尺寸不小于 16px。
- new_guardrail: 入口图标必须有可渲染的图形资源（背景图或图标组件），禁止用单汉字占位；图标审计必须检查背景图与渲染尺寸，不能只数元素个数。
- verification: `npm run check:miniapp` 通过（15 页 / 15 路由）；`devtools:verify-all-pages` 会员中心订单图标 4 个、服务图标 5 个，全部有背景图标且无文字占位。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `miniapp/miniprogram/pages/profile/index.ts`; `miniapp/miniprogram/pages/profile/index.wxml`; `miniapp/miniprogram/pages/profile/index.wxss`; `miniapp/scripts/check-miniapp.mjs`; `miniapp/scripts/verify-all-15-pages-devtools.cjs`; `miniapp/scripts/scan-miniapp-button-touch-targets.mjs`
- next_time_signal: 看到入口图标渲染成空心方块、单个汉字或空白圆底时，先检查 `iconKey` 对应的背景图规则是否存在且可解析，再考虑更换图标。

## M-20260914-023：把工具输出里的脱敏占位符当成真实前缀写进 WXSS

- status: guarded
- first_seen: 2026-09-14
- severity: low
- symptom: 新增会员中心图标样式时，data URI 前缀被写成工具输出里的字面占位符，而不是真实的 `data` 前缀；WXSS 可以编译，但 `background-image` 解析失败，DevTools 审计报“缺少可渲染背景图标”，截图上入口仍是空白方块。
- root_cause: 读取文件时长 data URI 会被输出层截断为占位文本；直接复制该占位文本进补丁，就把“显示层的省略”写成了文件内容。
- impact: 代码看起来“已改成图标”，静态检查也通过，但运行态图标全部不显示；只看代码不验收截图会把未完成误判为已完成。
- fix: 用真实 data 前缀批量修正 9 处 url()，并补上运行态断言（背景图非空 + 渲染尺寸下限），使同类错误无法再次通过。
- new_guardrail: 从工具输出复制长 data URI 前，先用字符串包含或长度对比确认文件里是真实内容；图标类改动必须跑一次运行态审计，不能只靠静态检查。
- verification: 修正后 `devtools:verify-all-pages` 会员中心图标断言通过，报告记录 9 个图标均有背景图。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `miniapp/miniprogram/pages/profile/index.wxss`; `miniapp/scripts/verify-all-15-pages-devtools.cjs`
- next_time_signal: DevTools 报“缺少背景图标”但代码里写了 `background-image` 时，先确认文件里存的是真实前缀，再怀疑选择器或类名。

## M-20260914-024：空态与身份徽标用单汉字/标点充当图标

- status: guarded
- first_seen: 2026-09-14
- severity: medium
- symptom: 13 处空态与登录引导在 140rpx 白底圆角方块内渲染单个汉字或标点（址/购/结/券/详/单/订/分/充/芸/!），群内登记与个人中心的身份徽标用“登/我”单汉字；截图上与未替换的占位稿无法区分。
- root_cause: `.yunxi-state__icon` 与 `.session-notice__icon` 靠 `font-size` 渲染文字，页面 WXML 直接把汉字写进图标节点；此前两次同类缺陷（M-20260914-015 商品详情入口、M-20260914-022 会员中心入口）只修了“入口图标”，没有推广到共用空态与身份徽标两个场景。
- impact: 空态是顾客遇到未登录、加载失败、暂无数据时的第一屏，占位式图标让页面看起来像未完成的半成品，也让刚收口的入口图标整改失去一致性。
- fix: app.wxss 为 13 个空态图标 key（map-pin / shopping-cart / shopping-bag / clipboard-check / ticket / receipt / file-question / package / loader / wifi-off / star / cake / wallet）定义内联线性图标并去掉文字字号；13 处页面 WXML 改为 `yunxi-state__icon--<key>` 并补 `aria-hidden`；`session-notice` 组件把 `iconText` 换成 `iconKey`（log-in / user-check），个人中心与群内登记调用方同步。
- new_guardrail: 空态与身份徽标禁止用文字充当图标；新增 icon key 必须同时在 app.wxss 定义背景图规则；静态守卫 `checkEmptyStateIcons()` 与全页审计双重拦截，审计从“图标文字非空”改为“背景图非空 + 尺寸下限 + 无文字”。
- verification: `npm run check:miniapp` PASS（15 页 / 15 路由）；`devtools:verify-all-pages` 15/15 页 + 8/8 未登录态 PASS，登录引导图标实测 72×72px 且 `iconBackground=set`、`iconText` 为空，群内登记身份徽标 31×31px 且无文字；`devtools:commerce-states`、`devtools:checkout-delivery-states`、`devtools:registration-policy`、`devtools:verify-commerce-flows`、`devtools:product-purchase-path`、触控扫描（13 页 47 选择器）均 PASS。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `miniapp/miniprogram/app.wxss`; `miniapp/miniprogram/components/session-notice/index.wxml`; `miniapp/miniprogram/components/session-notice/index.ts`; `miniapp/miniprogram/components/session-notice/index.wxss`; `miniapp/miniprogram/pages/{address,cart,checkout,coupons,group-registration,order-detail,orders,points,product-detail,products,profile,recharge}/index.wxml`; `miniapp/scripts/check-miniapp.mjs`; `miniapp/scripts/verify-all-15-pages-devtools.cjs`
- next_time_signal: 看到白底或深色方块里只有一个汉字、字母或标点时，先查该 icon key 在样式里有没有 `background-image` 规则，不要只调字号或换个汉字。

## M-20260914-025：修复图标时再次把工具输出的脱敏占位符写进 WXSS

- status: guarded
- first_seen: 2026-09-14
- severity: medium
- symptom: 首页履约图标改为图形节点后，`devtools:verify-all-pages` 报 3 个图标“缺少可渲染背景图”；文件里看起来有 `background-image`，但实际前三字符是终端展示用的 `[image omitted]`，不是可解析的 data URI。
- root_cause: 从工具输出读取内联 SVG 时，把展示层折叠文本当成真实内容写回了 `home/index.wxss` 与 `chat/index.wxss`；虽然 M-20260914-023 已记录同类风险，但当时只有人工注意，没有对所有 WXSS 做字面量静态拦截。
- impact: 静态检查只能看到 `background-image` 声明，仍可能放行；运行态页面会出现空白图标或无背景的装饰节点，视觉验收与实现状态不一致。
- fix: 用工作区已有可用图标复制真实 `data:image/svg+xml,` 前缀并批量修正 4 处错误 URL；`check-miniapp.mjs` 新增 `checkWxssDataUriIntegrity()`，递归扫描所有 WXSS 并直接阻断 `[image omitted]` 字面量。
- new_guardrail: 任何工具输出的长 data URI 必须先通过文件字面量包含检查；WXSS 中禁止出现 `[image omitted]`，新增图形图标必须同时有静态前缀守卫和 DevTools 背景图断言。
- verification: 修正后 `LITERAL_REDACTION_MARKERS=0`；`npm run check:miniapp` PASS（15 页 / 15 路由）；`devtools:verify-all-pages` PASS（15/15 页 + 8/8 未登录态，首页服务承诺图标 16×16px、客服空态图标 72×72px，均有背景图且无文字）；`devtools:verify-commerce-flows`、`devtools:product-purchase-path`、`devtools:commerce-states` 与触控扫描（13 页 47 选择器）均 PASS。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `miniapp/miniprogram/pages/home/index.wxss`; `miniapp/miniprogram/pages/chat/index.wxss`; `miniapp/scripts/check-miniapp.mjs`; `miniapp/scripts/verify-all-15-pages-devtools.cjs`
- next_time_signal: 运行态报图标背景为空时，先执行 `LITERAL_REDACTION_MARKERS` 字面量检查，再把问题定位到选择器、缓存或编译。

## M-20260918-001：沉浸式商品详情导航标题缺少底衬，深色商品图上不可读

- status: guarded
- first_seen: 2026-09-18
- severity: medium
- symptom: 商品详情首屏标题“商品详情”以深色文字直接压商家上传的商品大图；截图中标题正落在数字蜡烛包装的高光与金色图案交界处，文字与背景互相干扰；换成深色商品图时同一条标题会与背景同色，顾客读不到当前页身份。
- root_cause: `.detail-nav` 沉浸态把 `page-fixed-safe` 的白色底与应用级标题样式一起透明化，只保留了“滚动后切实底”的 class 切换；页面唯一可用的底衬 `.page-fixed-safe::after` 又被 `has-custom-title` 显式 `display: none`，标题可读性因此完全依赖商品图恰好够浅。
- impact: 商品详情是成交主路径，首屏标题是顾客确认“是否进对商品”的主要锚点；该缺陷只在深色或花哨商品图上暴露，只看浅色商品图的验收与静态检查都会漏掉。
- fix: `product-detail/index.wxss` 为沉浸态标题补半透明白底胶囊（`rgba(255, 255, 255, 0.92)` + 1rpx 边框 + 轻阴影，胶囊中心与返回按钮垂直居中对齐），滚动切实底后用 `.detail-nav--solid` 规则把底衬还原为透明，避免白底叠白底；`check-miniapp.mjs` 的 `checkProductDetailScrollNav()` 增加沉浸态底衬不透明度 ≥ 0.8、不得参与过渡、实底态必须移除底衬三条静态断言；`verify-miniapp-commerce-flows.cjs` 增加 `product-detail-immersive-title-contrast` 运行态断言，按“底衬叠到纯白图”与“底衬叠到纯黑图”两个边界各算一次对比度并取更差一侧，要求 ≥ 4.5:1，同时校验滚动实底后底衬消失、回滚顶部后恢复。
- new_guardrail: 沉浸式导航上的文字不得依赖商家图片明暗，必须自带底衬；底衬类改动必须同时有静态不透明度断言与 DevTools 运行态对比度断言，截图目视不能替代数值结论。
- verification: `npm run check:miniapp` PASS（15 页 / 15 路由）；`npm run typecheck` PASS；`devtools:verify-commerce-flows` PASS，运行态实测标题 `rgb(43, 39, 36)` 压 `rgba(255, 255, 255, 0.92)`，最坏情况对比度 12.37:1，实底态标题底衬 `rgba(0, 0, 0, 0)`、回顶后恢复 `rgba(255, 255, 255, 0.92)`；`devtools:verify-all-pages` 页面断言 15/15 页 + 8/8 未登录态通过、`devtools:product-purchase-path` 全部检查项无失败，两者截图证据因 DevTools `fail to capture screenshot` 环境阻断，报告记为 BLOCKED（`blockedReason` 已写明只缺截图）。
- linked_trace: `20260908-miniapp-commerce-ux-redesign`
- linked_files: `miniapp/miniprogram/pages/product-detail/index.wxss`; `miniapp/scripts/check-miniapp.mjs`; `miniapp/scripts/verify-miniapp-commerce-flows.cjs`
- next_time_signal: 看到“文字压在图片上”的页面（沉浸式详情、活动头图），先查文字自身有没有底衬或阴影，再讨论字号与位置。
