# 项目状态活页（PROJECT STATE）

> **这是唯一的项目状态入口**。每周收口时由 AI 员工更新，架构师复核。
> 迷路时先看这里，不要去翻计划书和历史文档。
> 中文优先：人类可读内容使用中文；`task_id`、`trace_id`、`status`、`owner`、`branch`、`as_of_commit`、`version` 和路径保持稳定机器字段。
> 最小阅读集：所有 Agent 先读 `AGENTS.md` 与本文件；执行具体任务时再读对应 `docs/tasks/*.md`，按需读取专业契约。

**最后更新**：2026-09-14（as_of_commit: `2318eb4156ea761c4aa7341d6b0f6bbf245f78ac`；version: `0.133.0-p2trial.3`）

> 当前状态口径：P1 承接验证已于 2026-08-30 经项目负责人确认正式关闭；P2 准备段已完成，真人执行段已阻塞（blocked），尚未启动。Harness P0 与中文治理控制面已完成，版本号以 `backend/VERSION` 为准，代码快照以当前 `git rev-parse HEAD` 为准。

<!-- PROJECT_STATE_MACHINE_START -->
## 机器快照（当前事实）

```yaml
updated_at: 2026-09-14
as_of_commit: 2318eb4156ea761c4aa7341d6b0f6bbf245f78ac
version: 0.133.0-p2trial.3
current_branch: main
workspace_state: clean
state_owner: 项目负责人＋AI 员工
```

`workspace_state: clean` 表示当前工作区没有尚未提交的文件变更；这不代表已推送或已完成生产发布。

## 主线任务总表（唯一动态明细源）

| task_id | 任务 | status | 状态说明 | 优先级 | owner | branch | as_of_commit | 依赖 | 证据 | 下一步 |
|---|---|---|---|---|---|---|---|---|---|---|
| T-P0-MONOREPO | Monorepo 整合与架构收口 | completed | 已完成（completed） | P0 | 项目负责人＋AI 员工 | main | 1c2a3ea | — | LOGBOOK: 20260817 | 保持主线基线可复现 |
| T-P05-ASSET-MIGRATION | 凭证、知识和商品资产迁移 | completed | 已完成（completed） | P0 | AI 员工 | main | 4ee06c8 | T-P0-MONOREPO | PROJECT-STATE 状态记录 | 仅按正式流程处理客户数据 |
| T-P1-ACCEPTANCE | P1 全模块承接验证 | completed | 已完成（completed） | P0 | 项目负责人 | main | 4ee06c8 | T-P05-ASSET-MIGRATION | LOGBOOK: 20260825-p1-wrap; 20260830-p1-close-confirmation | P1 已正式关闭，保持验收证据可复现 |
| T-P2-PREP | P2 试运行准备段 | completed | 已完成（completed） | P0 | AI 员工 | main | 4ee06c8 | T-P1-ACCEPTANCE | LOGBOOK: 20260826-p2trial-sim-fixes | 维持真人执行前门禁 |
| T-P2-RUN | P2 真人执行段（B/C/D/E） | blocked | 已阻塞（blocked） | P0 | 项目负责人＋AI 员工 | main | 4ee06c8 | T-P1-ACCEPTANCE,T-P2-PREP | docs/specs/2026-08-25-p2-manual.md | 获负责人批准后按手册执行 |
| T-P1-4-KNOWLEDGE | 知识缺口枚举与回填 | blocked | 已阻塞（blocked） | P1 | AI 员工＋项目负责人 | main | b4f25db | T-P2-RUN | docs/tasks/20260829-P1-4-知识缺口回填-指令.md | 当前 bot.db 为 0 条，待确认历史“5 条”来源或关闭 |
| T-P1-5-INVOICE | 发票承接专用测试与 E2E 验收 | blocked | 已阻塞（blocked） | P1 | AI 员工 | main | 220a8fe | T-P2-PREP | docs/tasks/20260829-P1-5-发票承接验收-指令.md；E-20260906-017 | 代码测试已完成；E1-E4 真实客服、后台和联动验收仍未执行，完成前保持阻塞 |
| T-P1-5-INVOICE-FIX | 发票状态与必填校验修复 | completed | 已完成（completed） | P1 | 项目负责人＋AI 员工 | main | 220a8fe | T-P1-5-INVOICE | docs/tasks/20260830-P1-5-发票实现修复-指令.md；E-20260906-017；ERRORS: M-20260830-004 | 代码修复与定向测试已完成；真实 E1-E4 由 T-P1-5-INVOICE 继续承接 |
| T-P1-6-SIMULATOR | 模拟器 B/C/D/E 走查 | blocked | 已阻塞（blocked） | P1 | AI 员工＋项目负责人 | main | b4f25db | T-P2-RUN | docs/tasks/20260829-P1-6-模拟器BCDE走查-指令.md | 等真人授权和测试号条件 |
| T-P1-7-FAQ | FAQ 10 条店家事实回收（已否决） | historical | 历史（historical） | P1 | 项目负责人 | main | b4f25db | — | docs/tasks/20260829-P1-7-FAQ回收-指令.md；LOGBOOK: 20260830-p1p2-state-correction | 已被项目负责人否决，不再执行，不进入当前待办 |
| T-P3-SEARCH | 商品搜索入口增强 | deferred | 已暂缓（deferred） | P3 | 项目负责人 | main | 4ee06c8 | T-P2-RUN | PROJECT-STATE 风险记录 | P2 稳定后重新排期 |
| T-D1-REVIEW | D1 账务核心独立审阅轨道 | deferred | 已暂缓（deferred） | P3 | 项目负责人 | external:D:\Project\YunxiBakeBot | 7afd44b | T-P0-MONOREPO | docs/archive/ 与旧仓记录 | 仅获批准时审阅，不合入主线 |
| T-P0-1-CHAT-TIMEOUT | 小程序 AI 聊天超时守卫 | historical | 历史（historical） | P0 | AI 员工 | main | 4ee06c8 | T-P2-PREP | docs/tasks/20260829-P0-1-指令.md | 仅供复盘，不得重执行 |
| T-HARNESS-REGISTER | 中文优先 Harness 与开发总表 | completed | 已完成（completed） | P0 | 项目负责人＋AI 员工 | main | 4ee06c8 | T-P0-1-CHAT-TIMEOUT | 本轮 trace: 20260829-project-development-register-and-chinese-governance；开发总表守卫与边界测试 EXIT=0 | 保持总表守卫随任务状态同步 |
| T-HARNESS-STATUS-LABEL-GUARD | 中文状态展示防回归守卫 | completed | 已完成（completed） | P0 | AI 员工 | main | 4ee06c8 | T-HARNESS-REGISTER | LOGBOOK: 20260830-chinese-status-display-guard；专项测试 12/12 通过 | 新任务继续使用中文状态说明并保留机器状态码 |
| T-HARNESS-TEST-CADENCE | 测试节奏与耗时治理 | completed | 已完成（completed） | P0 | AI 员工 | main | 4ee06c8 | T-HARNESS-STATUS-LABEL-GUARD | LOGBOOK: 20260830-test-cadence-governance；验证矩阵与提交流程已同步 | 开发阶段定向测试，上线候选执行一次全量并记录耗时 |
| T-HARNESS-EVIDENCE-INDEX | 历史证据索引来源与统计口径收敛 | completed | 已完成（completed） | P0 | AI 员工 | main | 4ee06c8 | T-HARNESS-REGISTER | trace: 20260830-evidence-index-origin-and-summary；来源冲突回归已修复；摘要 total=364、failed=0 | 后续新证据显式声明 repository_origin；历史条目按来源只读核验 |
| T-HARNESS-RUNTIME-CLEANUP | 质量门禁临时目录与跨 PowerShell 清理收口 | completed | 已完成（completed） | P0 | AI 员工 | main | 4ee06c8 | T-HARNESS-EVIDENCE-INDEX | 本轮 trace: 20260830-harness-runtime-cleanup-and-closeout；E-20260830-002；专项测试与双 PowerShell 预览 EXIT=0 | 后续新增质量门禁继续复用 D 盘一次性临时目录 |
| T-HARNESS-CLEANUP-POLICY | Harness 临时与可重建产物递归清理规则收口 | completed | 已完成（completed） | P0 | AI 员工＋项目负责人 | main | b4f25db | T-HARNESS-RUNTIME-CLEANUP,T-HARNESS-POLICY-AS-CODE | 本轮 trace: 20260831-cleanup-policy；run_id: 20260831-045839-140531c67c4d；E-20260831-002 | 白名单临时/可重建产物允许预览后递归批量清理；未知路径和受保护路径继续阻断 |
| T-HARNESS-ERRORS-LEDGER | 错误账本唯一入口与重复 ID 守卫 | completed | 已完成（completed） | P0 | AI 员工 | main | 4ee06c8 | T-HARNESS-RUNTIME-CLEANUP | LOGBOOK: 20260830-errors-ledger-canonicalization；错误账本专项测试 13/13；检查器 EXIT=0 | 后续错误统一写入根目录 ERRORS.md，不得创建同职能副本 |
| T-HARNESS-MATURITY-REVIEW | Harness Engineering 全面评审与外部对标 | completed | 已完成（completed） | P0 | 项目负责人＋AI 员工 | main | b4f25db | T-HARNESS-ERRORS-LEDGER | HARNESS-MATURITY-REVIEW-20260830；本轮定向 Harness 门禁 | 保持评审报告与唯一入口同步，不另起动态状态表 |
| T-HARNESS-CHINESE-GOVERNANCE | Harness 中文治理控制面 | completed | 已完成（completed） | P0 | 项目负责人＋AI 员工 | main | bcdd30c | T-HARNESS-MATURITY-REVIEW | trace: 20260831-p0-execution；run_id: 20260831-p0-execution-r1；E-20260831-008 | 中文权威源、六维模型、关键路径状态、协作/证据模板和中文治理覆盖率守卫已落地 |
| T-HARNESS-RUN-MANIFEST | 统一运行 manifest 与 episode 回放 | completed | 已完成（completed） | P0 | AI 员工 | main | b4f25db | T-HARNESS-MATURITY-REVIEW | 本轮 trace: 20260831-p0-execution；run_id: 20260831-p0-execution-r1；E-20260831-001 | JSON schema、生成器、检查器和最小回放报告已落地 |
| T-HARNESS-POLICY-AS-CODE | 工具权限与生产边界策略即代码 | completed | 已完成（completed） | P0 | AI 员工＋项目负责人 | main | b4f25db | T-HARNESS-MATURITY-REVIEW | 本轮 trace: 20260831-p0-execution；run_id: 20260831-p0-execution-r1；E-20260831-001 | 路径、网络、生产开关和高风险工具策略快照与阻断门禁已落地 |
| T-HARNESS-CI-ENTRY | 仓库级 Harness CI 统一入口 | completed | 已完成（completed） | P0 | AI 员工 | main | b4f25db | T-HARNESS-MATURITY-REVIEW,T-HARNESS-CHINESE-GOVERNANCE | 本轮 trace: 20260831-p0-execution；run_id: 20260831-p0-execution-r1；E-20260831-001 | 根级可发现 CI 已落地，复用治理脚本并强制中文治理、状态、证据和安全检查 |
| T-HARNESS-EVAL-REGRESSION | Harness 自评数据集与趋势基线 | completed | 已完成（completed） | P1 | AI 员工 | main | b4f25db | T-HARNESS-MATURITY-REVIEW | 本轮 trace: 20260831-harness-eval-regression；run_id: 20260831-053324-6f048e5f42ce；P1 自评 8/8；运行观测 4 个 manifest；恢复点覆盖率 1.0 | 后续按周期运行自评与观测，追加 baseline 差异并观察样本量增长 |
| T-HARNESS-DOC-GARDEN | 文档园艺扫描与低风险中文维护 | completed | 已完成（completed） | P2 | AI 员工 | main | b4f25db | T-HARNESS-RUN-MANIFEST,T-HARNESS-POLICY-AS-CODE,T-HARNESS-CI-ENTRY | 本轮 trace: 20260831-doc-garden；P2 文档园艺扫描 135 个文件、0 个错误、16 个低风险警告；P2 CI 不阻断 P0 | 按周运行扫描；历史归档断链和未登记旧报告按 warning 逐步治理，不删除审计证据 |
| T-HARNESS-P1-FOUR-FIXES | Harness P1 四项缺陷复核与修复 | completed | 已完成（completed） | P1 | AI 员工 | main | b4f25db | T-HARNESS-CI-ENTRY,T-HARNESS-RUN-MANIFEST,T-HARNESS-CHINESE-GOVERNANCE,T-HARNESS-CLEANUP-POLICY | trace: 20260831-harness-p1-four-fixes-hardening；定向测试 32/32；P0 总门禁 8 项 0 失败；run_id: p0-gate-cc6e8922a14f4a2a | 持续观察 CI 事件基线、Schema 约束和高风险中文语义断言 |
| T-HARNESS-P0-HARDENING | Harness P0 失败关闭与中文语义硬化 | completed | 已完成（completed） | P0 | AI 员工 | main | c7b139a | T-HARNESS-P1-FOUR-FIXES,T-HARNESS-CHINESE-GOVERNANCE,T-HARNESS-RUN-MANIFEST,T-HARNESS-POLICY-AS-CODE,T-HARNESS-CI-ENTRY | trace: 20260831-harness-p0-hardening；E-20260905-001,E-20260905-002,E-20260905-003；远端 P0 已通过，P1/P2 浅克隆偏差已修复，中文治理六维 coverage=1.0 | 保持 P0 门禁和中文治理作为 Harness 控制面；P1/P2 周期信号继续观察 |
| T-HARNESS-P1-P2-QUALITY-LOOP | P1/P2 CI 结果表达、运行观测与回归扩展 | completed | 已完成（completed） | P1 | AI 员工 | main | c7b139a | T-HARNESS-P0-HARDENING | trace: 20260905-harness-p1-p2-quality-loop；定向 pytest 6/6；自评 12/12；观测 12 runs；doc garden 0 errors/17 warnings；清理预览令牌执行完成 | 后续按周期积累 CI manifest 趋势样本，成熟度维持 3.0/5 |
| T-HARNESS-CI-EVIDENCE-COMPLETE | Harness CI 证据包完整性修复 | completed | 已完成（completed） | P1 | AI 员工 | main | d0af4dfd5a6ce98cf3903cae1516793ed2a96d4c | T-HARNESS-P1-P2-QUALITY-LOOP | trace: 20260905-harness-evidence-error-loop；E-20260905-005；定向 pytest 73 项通过；P0 门禁 9/9；最终 artifact index 覆盖含 Summary 共 64 文件 0 缺失 | 远端 CI 推送后核验 P1/P2 artifact index 与中文 Summary |
| T-HARNESS-ERROR-CANDIDATE-LOOP | 错误候选生成与人工确认闭环 | completed | 已完成（completed） | P1 | AI 员工 | main | d0af4dfd5a6ce98cf3903cae1516793ed2a96d4c | T-HARNESS-CI-EVIDENCE-COMPLETE | trace: 20260905-harness-evidence-error-loop；E-20260905-005；候选/review/账本定向测试 24 项通过；ERRORS.md 保持 26 条 | 下一次真实 CI 失败由项目负责人人工 accept 验证正式入账 |
| T-AUDIT-20260905-COMPREHENSIVE | 项目负责人视角代码库全面审计 | completed | 已完成（completed） | P0 | 项目负责人＋AI 员工 | main | 220a8fe0dcd1126dfe43e3745667a3f7f58fc262 | — | `docs/audit/20260905-project-comprehensive-audit.md`；`LOGBOOK.md`：20260905-comprehensive-project-audit；`evidence-index.md`：E-20260905-006 | 保持 No-Go，按报告 P0/P1/P2 整改并重新申请上线评审 |
| T-AUDIT-REMEDIATION-20260906 | 审计整改执行（P0-A/B→P1→P2） | active | 进行中（active） | P0 | OpenCode | main | 220a8fe0dcd1126dfe43e3745667a3f7f58fc262 | T-AUDIT-20260905-COMPREHENSIVE | trace: 20260906-audit-remediation-final；run_id: 20260906-audit-remediation-final5；E-20260906-015；收口计划执行中 | 复核收口计划执行中，保持 No-Go；M-20260906-003 关闭前禁止上线 |
| T-AUDIT-CLOSEOUT-20260906 | 审计复核收口执行（部署恢复/全量前置/凭证审计） | active | 进行中（active） | P0 | OpenCode | main | 220a8fe0dcd1126dfe43e3745667a3f7f58fc262 | T-AUDIT-REMEDIATION-20260906 | trace: 20260906-audit-remediation-final；run_id: 20260906-audit-remediation-final5；E-20260906-015；收口计划执行中 | 按计划 Task 1→5 执行并收口证据，保持 No-Go 直至门禁与负责人动作完成 |
| T-AUDIT-GO-LIVE-20260906 | 最终上线收口执行（三态识别/测试治理/凭证与验收） | active | 进行中（active） | P0 | OpenCode | main | 220a8fe0dcd1126dfe43e3745667a3f7f58fc262 | T-AUDIT-CLOSEOUT-20260906 | trace: 20260906-audit-remediation-final；run_id: 20260906-audit-remediation-final6；E-20260906-016；全量 1854 项退出码 0 | 三态识别与测试治理已代码完成但负责人动作缺失，保持 No-Go；M-20260906-003 关闭前禁止上线 |
| T-MINIAPP-DISPLAY-POLISH-01 | MiniApp 全页面与次级交互链路大厂级统一整改及 DevTools 走查 | active | 进行中（active） | P1 | AI 员工 | main | b738ecf8192e4dc30a5a3f829158ba6d337fe1f1 | — | trace: 20260908-miniapp-console-zero-error；DevTools 控制台 0 warning / 0 error；全 15 页面自动化走查 15/15 PASS；单测与门禁通过 | 保持 DevTools 实机高保真与大厂验收标准，推进二期业务闭环 |
| T-MINIAPP-COMMERCE-UX-REDESIGN | MiniApp 商品优先型 UI/UX 与北京闪送履约重构 | active | 进行中（active） | P1 | AI 员工 | main | 2318eb4156ea761c4aa7341d6b0f6bbf245f78ac | T-MINIAPP-DISPLAY-POLISH-01 | trace: 20260908-miniapp-commerce-ux-redesign；E-20260909-001,E-20260909-002,E-20260909-003,E-20260909-004,E-20260909-005,E-20260909-006,E-20260909-007,E-20260909-008,E-20260909-009,E-20260909-010,E-20260909-011,E-20260909-012,E-20260909-013,E-20260909-014,E-20260909-015,E-20260909-017,E-20260909-018,E-20260909-019,E-20260909-020,E-20260909-021,E-20260909-022,E-20260912-001,E-20260912-002,E-20260912-003,E-20260912-004,E-20260912-005,E-20260912-006,E-20260912-007,E-20260912-008,E-20260913-001,E-20260913-002,E-20260913-003,E-20260913-004,E-20260913-005,E-20260913-006,E-20260913-007,E-20260913-008,E-20260913-009,E-20260913-010,E-20260913-011,E-20260913-012,E-20260913-013,E-20260913-014,E-20260913-015,E-20260913-016；商品优先核心购买链路、全页面视觉统一、未登录结算收敛、商品/订单金额明细、营业时段同步、当天预约边界、商品目录清单化、空购物车结算收敛、商品目录触控目标、展示语言收敛、商品目录快速预订、购物车服务商品推荐、按钮样式零警告、无用前端代码清理和本地后端+DevTools 运行态复核已完成；本轮额外修复本地商品验证器的绝对 CDN URL 处理、迁移态空分类计数假设、会话 CTA 触控尺寸及全局安全区布局，未删除任何商品、配送、支付或验收能力；源码、类型、页面结构、API 覆盖、商品 API、15 页面运行态、真实在售商品购买路径、商品状态、结算配送和当天预约边界均通过；20260910 结算闪送状态指引与串行复测收口（run_id: 20260910-miniapp-serial-rerun-r20，same-day 误报按 M-20260910-070 重载后复跑 PASS）；20260912 表单与货架层级视觉修复收口（run_id: 20260912-miniapp-form-visual-r21；ERRORS: M-20260912-071；E-20260912-001）；20260912 首页图片加载失败降级与版本文本漂移修复收口（run_id: 20260912-miniapp-home-image-fallback-r22；ERRORS: M-20260912-073、M-20260912-074；E-20260912-002）；20260912 表单字段常驻标签与触控高度收口（run_id: 20260912-miniapp-form-labels-r23；ERRORS: M-20260912-075；E-20260912-003）；20260912 零资产状态、订单隐私信息与会员展示收口（run_id: 20260912-miniapp-customer-polish-r24；ERRORS: M-20260912-076；E-20260912-004）；20260912 商品目录真实销量排序与伪营销徽标清理收口（run_id: 20260912-miniapp-popular-catalog-r25；ERRORS: M-20260912-077；E-20260912-005）；20260912 商品目录分类命名空间、同步噪声、配件提示与隔离 Harness 收口（run_id: 20260912-miniapp-category-noise-r26；ERRORS: M-20260912-079～M-20260912-085；E-20260912-006）；20260912 商品卡可用性口径统一与按钮可见性修复收口（run_id: 20260912-miniapp-card-semantics-and-button-visibility-r27；ERRORS: M-20260912-086～M-20260912-089；E-20260912-007）；20260912 未登录提示宽度、DevTools 响应探测与门店地址单一来源收口（run_id: 20260912-miniapp-notice-width-and-devtools-lock-guard-r28；ERRORS: M-20260912-090～M-20260912-095；E-20260912-008）；20260913 真实链路 API 预检与返回控件统一收口（run_id: 20260913-miniapp-real-api-preflight-and-back-button-r29；ERRORS: M-20260912-078、M-20260913-097；E-20260913-001）；20260913 结算页零资产控件、会话动作与 WXML 标签解析护栏收口（run_id: 20260913-miniapp-checkout-affordance-and-wxml-scanner-r30；ERRORS: M-20260913-098、M-20260913-099；E-20260913-002）；20260913 门店自提地址来源归一化收口（run_id: 20260913-miniapp-pickup-address-source-r31；ERRORS: M-20260913-102；E-20260913-003）；20260913 群内登记与政策页运行态审计与触控 44px 基线收口（run_id: 20260913-miniapp-registration-policy-audit-r32；ERRORS: M-20260913-103；E-20260913-004）；20260913 充值金额输入与禁用操作可读性收口（run_id: 20260913-miniapp-control-affordance-r33；ERRORS: M-20260913-104；E-20260913-005）；20260913 未登录整页引导空态与优惠券伪交互收口（run_id: 20260913-miniapp-login-gate-and-coupon-affordance-r34；ERRORS: M-20260913-105、M-20260913-106、M-20260913-107；E-20260913-006）；20260913 订单履约口径分叉与商品目录层级收口（run_id: 20260913-miniapp-order-fulfillment-and-catalog-hierarchy-r35；ERRORS: M-20260913-108～M-20260913-111；E-20260913-007） | 后台保存 09:00-19:30 运营配置；获得受控测试授权后复核真实认证结算与报价状态；真实闪送平台资料到位后验证报价、订单金额快照、创建运单和回调幂等；门店提供统一商品图后替换有赞迁移素材；真实支付、生产验收和正式上线仍未验证；`/ready` 为本地测试降级态，不可作为生产就绪；商品人气依赖有赞 `sold_num` 同步新鲜度，长期不同步会再次偏离真实销量；覆盖率模式隔离 Harness 已定向修复，全量全绿需按测试节奏另次复跑确认；r28 运行态串行复跑 15/15 PASS（sessionNoticeWidth=362/390、profileShortcutIcons=4+5）、commerce-states、product-purchase-path、verify-commerce-flows、checkout-delivery-states、same-day-scheduling 与触控扫描 39 选择器均 PASS；r29 逐页目视复核后统一商品详情返回控件并新增预检（15/15 PASS、触控扫描 39/39 pass）；r30 结算页零资产态与已登录会话提示经 DevTools 复核（三项可见性均为 false、截图目视通过），WXML `>` 解析误报已修复并完成反向验证；r31 后端默认运营配置、历史占位值与后台默认设置统一为真实门店地址，小程序结算页不再展示占位自提文案（后端 14 项定向用例、check:miniapp、typecheck、checkout-delivery-states、commerce-states 均 PASS）；闪送报价起点仍由客户端传入、后端以报价哈希一致性兜底，待真实闪送接入时改为服务端下发；生产域名 `yunxifood.cn` 证书未续期，真实链路脚本与生产验收保持阻塞（M-20260912-078）；r32-r34 运行态复核显示 15/15 页面、8/8 确定性未登录态 PASS，受限页面统一为 362~366x490px 整页登录引导空态（CTA 79x45px、说明单行），结算页无可用券不再保留下拉箭头与空面板；r35 显示自提单已不再展示闪送费与配送地址、进度按履约方式区分“待取货/配送中”，商品详情首图重复销量与已登录空订单裸空态同步收口（后端 6/6 与 14/14 定向用例、check:miniapp、typecheck、test:bakery 8/8、commerce-flows、commerce-states、all-pages、触控扫描均 PASS）；r36 收口结算页选择器与提交值不一致（5 项单测 + 运行态还原断言）、优惠券/积分已登录空态、商品目录伪控件与无依据副标题（run_id: 20260913-miniapp-schedule-wysiwyg-and-empty-states-r36；ERRORS: M-20260913-112～M-20260913-115；E-20260913-008）；r37 处理购物车长商品名信息层级与长状态标签重叠、统一充值记录分区空态（run_id: 20260913-miniapp-cart-long-title-and-recharge-empty-r37；ERRORS: M-20260913-116、M-20260913-117；E-20260913-009）：41 字真实商品名改为两行并可点击进入商品详情，标签与数量步进器零重叠；r38 修复商品列表缓存键漏掉 limit 导致的首页货架 4/5/6 条漂移（run_id: 20260913-miniapp-product-cache-limit-and-detail-footer-r38；ERRORS: M-20260913-118、M-20260913-119；E-20260913-010），并把商品详情底部写死留白改为“安全区 + 底栏高度”自适应；r39 逐页目视复核收口首页服务承诺卡字号与截单口径、群内登记“北京闪送”与运费承担说明、商品详情滚动实底导航（run_id: 20260913-miniapp-promise-registration-and-detail-nav-r39；ERRORS: M-20260913-121～M-20260913-124；E-20260913-012，客服文案 E-20260913-011/M-20260913-120）；r40 将购物车状态胶囊改为短事实标签、库存充足时不渲染空胶囊，长运费口径统一保留在“商品合计 · 不含闪送费”（run_id: 20260913-miniapp-cart-tag-copy-r40；ERRORS: M-20260913-125；E-20260913-013）；r41 统一购物车推荐卡动作与加购提示口径、把首页商品卡购买说明提到 22rpx，并固化审计环境前置（本地后端 7001 健康、DevTools 单实例渲染预检）（run_id: 20260913-miniapp-cart-recommend-parity-and-audit-preflight-r41；ERRORS: M-20260913-126～M-20260913-130；E-20260913-014），其中 M-20260913-128/129 为审计环境假失败（DevTools 多实例与本地后端未启动），已分别用渲染预检与启动前置收口；有赞分类与商品标签命名空间零交集导致分类接口恒为空（M-20260913-115，open），目录分类导航暂为单层列表，需先取得真实有赞接口权限建立分类-商品关联；r43 将商品目录搜索与长尾查找纳入运行态门禁（run_id: 20260913-miniapp-product-search-and-catalog-integrity-r43；ERRORS: M-20260913-134～M-20260913-139；E-20260913-016）：搜索栏输入前后高度恒定 45px、清空按钮唯一且触达 45×45px、页面目录与接口同为 310 款且顺序一致、“曲奇”长尾 3 条全部命中首屏 12 款之外、无结果空态带“查看全部商品”出口、搜索结果可直接预订并进入详情；搜索仍为本地全量（limit=500）过滤，服务端搜索未实现；同轮把截图失败从 15 页产品失败改为环境阻塞（BLOCKED）；r43.3 修正“用进程名预判锁屏”的误判并给截图加重试，解锁后复跑补齐 23 张截图（ERRORS M-20260913-143～145；E-20260913-017）；r43.4 落地目录触底加载与搜索首屏 30 款限量渲染（M-20260913-141 转 guarded；E-20260913-018），并记录目录 5 款“非卖品仅展示/勿拍”商品仍可预订（M-20260913-137，open，待业务确认）；r43.5 修复搜索关键词收窄与商品分类切换后保留旧滚动偏移（run_id: 20260913-miniapp-products-scroll-reset-r43.5；ERRORS: M-20260913-146、M-20260913-147；E-20260913-019）：两个 scroll-view 增加零高度顶部锚点并在数据变化后重置，运行态实测搜索结果 scrollTop 900→0、分类列表 scrollTop 900→8 且锚点为 products-catalog-top，devtools:product-search 扩到 18 项 PASS；闪送开放平台资料与测试权限未到位，计划书 Task 1 Step 3 与 Task 3 Step 5 保持外部阻塞；r44 修复有赞网关 4007（调用方 IP 未加白名单）被当成空数据的问题（run_id: 20260913-youzan-gateway-error-guard-r44；ERRORS: M-20260913-148；E-20260913-020）：在售列表/商品分组/ITEM_INFO/商品分类四个同步入口改为显式抛脱敏 APIError，商品对账新增空集合下架保护，数据库副本端到端验证抛 APIError 且在售商品保持 310 款，定向 pytest tests/service/youzan 70/70 与 ruff 通过；分类-商品关联仍待有赞侧配置 IP 白名单后重跑同步 |

## 状态视图（只引用主表 task_id）

> r45 证据登记：`T-MINIAPP-COMMERCE-UX-REDESIGN` 本轮新增 `E-20260914-001`（群内登记时间基线跨日收口，run_id `20260914-miniapp-registration-schedule-baseline-r45`）；该任务仍为进行中（active），无新增阻塞项，主表证据列在下一次整体收口时合并。
> r46 证据登记：`T-MINIAPP-COMMERCE-UX-REDESIGN` 新增 `E-20260914-002`（群内登记服务端复用订单预约校验，run_id `20260914-miniapp-registration-server-schedule-r46`）；该任务仍为进行中（active），主表证据列在下一次整体收口时合并。
> r46 运行边界：本地后端最新代码在 `127.0.0.1:7001` 健康运行；真实 DevTools `wx.login` + 订单/地址/聊天接口 4/4 与当天预约 PASS。`registration-policy` 11 项页面断言通过，但 Windows 锁屏使截图证据为环境阻塞（BLOCKED），解锁后补帧；生产验收、真实支付/退款、真实闪送和有赞 IP 白名单仍未完成。
> r47 运行态复测：`T-MINIAPP-COMMERCE-UX-REDESIGN` 新增 `E-20260914-003`（结算自提态审计夹具修正与本地运行态复测，run_id `20260914-miniapp-checkout-pickup-audit-r47`）。本地后端定向 65/65、DevTools 真实接口 4/4、当天预约 PASS、结算页面断言 0 错误、15/15 页面与 8/8 未登录态断言 PASS；结算自提态实测 `2026-09-15 15:00`、空备注、`免运费`、`¥198.00`。Windows 锁屏使截图证据为环境阻塞（BLOCKED），解锁后补帧；真实支付/退款、真实闪送、生产验收和有赞 IP 白名单仍未完成。
> r48 商品目录分页：`T-MINIAPP-COMMERCE-UX-REDESIGN` 新增 `E-20260914-004`（商品目录服务端分页与搜索收口，run_id `20260914-miniapp-products-server-pagination-r48`）。商品页首屏改为服务端 12 条分页（接口总 310 款）、搜索每页 30 条、触底与分类切换按 `meta.offset + meta.limit` 续页，页面不再缓存全量目录；`devtools:product-search` 19 项、15/15 页面与 8/8 未登录态、购买路径、电商流程与触控扫描（13 页 46 选择器）均 PASS；有赞分类接口仍因 IP 白名单返回空数组，分类导航降级为单一“全部商品”分区（M-20260913-115）。
> r49 视觉取证与底栏金额来源：`T-MINIAPP-COMMERCE-UX-REDESIGN` 新增 `E-20260914-005`（购物车减号语义、结算底栏金额来源与全页视觉取证收口，run_id `20260914-miniapp-visual-evidence-and-cart-stepper-r49`）。购物车数量为 1 时减号固定为 `-`（删除语义仍走确认弹窗），结算固定栏新增“已含闪送费 / 自提价 · 免运费 / 闪送费未计入”次要说明；全页审计新增默认态取证：商品页先清搜索残留并回顶（原生页面滚动回落 `wx.pageScrollTo`），商品详情页带真实在售商品 ID 取证，并新增后端健康前置门禁（不通过时 `exit 2` 且保留上一份报告）。运行态结果：15/15 页 + 8/8 未登录态 PASS、购买路径 PASS（`cart-stepper-minus-at-one`：`-`、45×45px）、结算配送状态 PASS（`已含闪送费 ¥26.00`、自提 `自提价 · 免运费`）、电商流程 PASS、触控扫描 13 页 46 选择器 PASS；新增 ERRORS M-20260914-005～M-20260914-008。真实支付/退款、真实闪送、生产验收与有赞 IP 白名单仍未完成。
> r50 展示型商品只读收敛：`T-MINIAPP-COMMERCE-UX-REDESIGN` 新增 `E-20260914-006`（展示型商品只读收敛与运行态回归收口，run_id `20260914-miniapp-display-only-purchase-guard-r50`）。`M-20260913-137` 由 open 转 guarded：后端新增 `isPurchasable` 读模型（标题含“非卖品/勿拍/虚拟价格/仅供展示”判为展示型），`service/order/inventory.py` 下单前逐单拦截并返回 `400 商品仅供展示，不可下单`；小程序首页、目录、购物车推荐与详情页不再为这 5 款生成预订/加购/立即购买动作，详情页改只读说明卡 + “返回选购 / 咨询客服”。运行态：重启后 7001 翻页拉全 310 款，恰好 5 款 `isPurchasable=false`、其余 305 款 `true`；新增 `devtools:display-only-products` PASS 并产出 `display-only-product-detail.png`；15/15 页 + 8/8 未登录态、购买路径、搜索 19 项、电商流程、结算配送状态与触控扫描（13 页 47 选择器）均 PASS。展示型判定仍为业务确认前的标题关键词保守口径，有赞正式分组待客服/店主确认。

> r56 视觉收口：`T-MINIAPP-COMMERCE-UX-REDESIGN` 新增 `E-20260914-012`（首页履约、快捷入口与客服空态图标收口，run_id `20260914-miniapp-content-icons-r56`）。首页履约卡改为 3 个线性图标，快捷入口回退改为 `iconKey` 并保留旧配置兼容，客服未登录空态改为 support 图标；新增全 WXSS 脱敏占位符守卫。运行态 15/15 页 + 8/8 未登录态、核心成交、购买路径、电商状态与触控扫描 PASS；首页履约图标 16×16px、客服空态图标 72×72px。首轮 `[image omitted]` 回归已修正并记录 M-20260914-025；闪送真实联调两项与真实支付/退款、生产验收仍未完成。
> r57 图标键白名单：`T-MINIAPP-COMMERCE-UX-REDESIGN` 把首页快捷入口 `iconKey` 从任意小写键收紧为 points/recharge/link 白名单（未知键回退 link），并由 `check-miniapp.mjs` 静态守卫锁定；本地后端保持 `127.0.0.1:7001` 健康，`devtools:service-smoke` 真实接口 4/4、15/15 页 + 8/8 未登录态、电商流程与购买路径复测 PASS；当前线上装修配置未下发 `quickLinks` 块，该图标键路径由静态守卫、typecheck 与 r56 的 DevTools 注入验证覆盖，证据登记为 `E-20260914-012` 的 update_20260914_r56b。

### 已完成（completed）

`T-P0-MONOREPO`、`T-P05-ASSET-MIGRATION`、`T-P1-ACCEPTANCE`、`T-P2-PREP`、`T-P1-5-INVOICE-FIX`、`T-HARNESS-REGISTER`、`T-HARNESS-STATUS-LABEL-GUARD`、`T-HARNESS-TEST-CADENCE`、`T-HARNESS-EVIDENCE-INDEX`、`T-HARNESS-RUNTIME-CLEANUP`、`T-HARNESS-CLEANUP-POLICY`、`T-HARNESS-ERRORS-LEDGER`、`T-HARNESS-MATURITY-REVIEW`、`T-HARNESS-CHINESE-GOVERNANCE`、`T-HARNESS-RUN-MANIFEST`、`T-HARNESS-POLICY-AS-CODE`、`T-HARNESS-CI-ENTRY`、`T-HARNESS-EVAL-REGRESSION`、`T-HARNESS-DOC-GARDEN`、`T-HARNESS-P1-FOUR-FIXES`、`T-HARNESS-P0-HARDENING`、`T-HARNESS-P1-P2-QUALITY-LOOP`、`T-HARNESS-CI-EVIDENCE-COMPLETE`、`T-HARNESS-ERROR-CANDIDATE-LOOP`、`T-AUDIT-20260905-COMPREHENSIVE`

### 进行中（active）

`T-AUDIT-REMEDIATION-20260906`、`T-AUDIT-CLOSEOUT-20260906`、`T-AUDIT-GO-LIVE-20260906`、`T-MINIAPP-DISPLAY-POLISH-01`、`T-MINIAPP-COMMERCE-UX-REDESIGN`

### 未完成（pending / blocked / deferred）

`T-P2-RUN`（已阻塞（blocked），待负责人批准及测试号/体验版条件）、`T-P1-4-KNOWLEDGE`（已阻塞（blocked），当前数据库为 0 条，待确认历史口径）、`T-P1-5-INVOICE`（已阻塞（blocked），代码测试已完成，E1-E4 真实客服、后台和联动验收尚未执行）、`T-P1-6-SIMULATOR`（已阻塞（blocked），真人授权/测试号）、`T-P3-SEARCH`（已暂缓（deferred），P2 后排期）、`T-D1-REVIEW`（已暂缓（deferred），外部冻结轨道）。

### 历史（historical）

`T-P0-1-CHAT-TIMEOUT`：已完成任务指令快照，不能作为当前执行入口。
`T-P1-7-FAQ`：项目负责人已否决，不能作为当前执行入口。

## 分支与开发轨道登记

| branch_or_track | 类型 | 状态 | 用途 | 基线 | owner | 绑定任务 |
|---|---|---|---|---|---|---|
| main | 本仓 Git 分支 | 当前 | Monorepo 唯一开发主线 | 4ee06c8 | 项目负责人 | 全部主线任务 |
| D:\Project\YunxiBakeBot | 外部历史轨道（非 Git 分支） | 冻结 | D1 审阅与历史证据 | 7afd44b | 项目负责人 | T-D1-REVIEW |
| D:\Project\YunxiBakeMiniApp | 外部过期副本（非 Git 分支） | 停用 | 迁移前参考，不得开发 | 历史快照 | 项目负责人 | — |

不存在的本地或远端分支不登记为事实；候选分支只能在任务说明中描述，不能放入本表。
<!-- PROJECT_STATE_MACHINE_END -->

---

## 一句话定位

**自研烘焙电商 + AI 客服平台（有赞替代）：完整承接已建成的全部模块，2027 年 6 月为最早候选上线窗口，非自动上线日期。**

小程序当前跑在有赞上，本项目是替代方案——电商、会员、积分、券、储值、AI 客服**全部在范围内，不可砍**。

---

## 当前位置（时间线）

```
P0 整合 ✅ → P0.5 资产迁移 ✅ → P1 承接验证 ✅（2026-08-30 负责人确认关闭）
                                    ↓
▶ P2 试运行准备完成（准备段完成 ✅ / 等待项目负责人组织真人执行段（未获 P2 批准前不启动实测）后方可启动 P2 实测）
                                    ↓
   P3 上线准备 → 2027-06 最早候选上线窗口（须负责人批准，非自动上线）
```

> **【关键】P1 已关闭，但未获 P2 真人执行批准、授权测试号和体验版条件前，不得启动 P2 实测。**

> **Harness P0 执行状态**：中文治理六维模型、运行 manifest、策略即代码和统一 CI 已纳入 P0 控制面；远端 P0 已通过，P1/P2 浅克隆导致的自评偏差已修复，`T-HARNESS-P0-HARDENING` 已完成（completed）。本轮不启动 P2 真人实测、不访问生产、不处理真实支付或客户数据。

---

## 资产地图（东西都在哪）

| 资产 | 位置 | 状态 |
|------|------|------|
| **代码主线（唯一开发场所）** | `D:\Project\YunxiBakery` | ✅ 后端 16 服务域 + 小程序 15 页面，**M1-M5 全部模块已在基线中** |
| 旧仓全量历史 + D1 存档 | `D:\Project\YunxiBakeBot` | 🔒 冻结，只读，永不删 |
| 凭证（有赞/企微/AI 全套） | 旧仓 `.env` → 复制到新仓 `backend/.env`（本地，不入库） | ✅ 已迁移并实测连通（有赞 token 刷新+商品拉取、企微 token 刷新均通过） |
| 业务知识（638 条，含 24 条人工沉淀） | 旧仓 `bot.db` → 新仓 24 条人工沉淀已迁入 | ✅ 迁移完成，BM25 检索命中验证通过 |
| 客户数据（2.4 万条） | 仅存在于旧仓 bot.db | ⛔ 永不复制进新仓，未来走正式导入流程 |
| 商品快照（614 条） | 旧库 | ✅ **已真实同步 309 条在售**（2026-08-25；旧 614 为历史快照含已下架，309 为当前在售真实口径，与有赞后台一致） |

---

## 范围修正记录（v1.2，2026-08-24）

- **撤回** v1.0 计划书中"小程序端推迟/积分/储值/优惠券推迟 v2.0"——这些是有赞替代核心，必须完全承接
- **继续推迟（deferred）**：D1 账务核心（留在旧仓审阅分支独立轨道）、真实微信支付（按既有门禁）、客户群运营增强（当前状态：已阻塞（blocked）或已暂缓（deferred））
- P1 从"开发三大功能"改为"**全模块承接验证**"——验证已有模块，不开发新功能

## 优先级调整记录（v1.3，2026-08-25，项目负责人决策）

- **主线调整为 MiniApp 承接优先**：P1 的 Phase C（跨端链路）提前为当前焦点；微信开发者工具安装 + 真机走查 + 数据接通作为关键路径
- **知识缺口回填降级**：5 条 production 缺口（knowledge_gaps）+ FAQ 补充均**不阻塞**——转人工链路已验证可用（Phase A），缺口全部由转人工兜底，回填排入 P2 试运行前
- **依据**：知识缺口=内容问题（低风险，可兜底）；MiniApp=替代有赞的核心（高风险，不可拖）

## 状态校准记录（v1.4，2026-08-25，项目负责人三条件核实）

| 原状态 | 校准后 | 说明 |
|--------|--------|------|
| ⛔ 微信开发者工具已阻塞（BLOCKED）（Phase B 误判：仅探测 Program Files 目录） | ✅ **工具已安装并登录**（本机长期存在） | Phase B 实机走查 + Phase C 阻塞**全部解除**；此为探测方法缺陷，记入任务包问题区 #7 并补充探测范围 |
| 数据策略未定（A mock / B 真实待选） | ✅ **B：真实有赞数据**，本机出口 IP `10.161.106.143` 已加有赞白名单 | 商品同步走真实链路；如同步时遇 60020，回读实际出口 IP 与白名单核对（`10.x` 为内网段，需确认 NAT 后出口 IP） |
| 微信支付商户号未知 | 📅 **暂无，申请流程流转中** | 支付环节以 mock 为准（ALLOW_MOCK_PAYMENT 本地开启）；商户号通过后真实支付/退款按既有受控门禁执行（授权测试账号+小额+对账+清理） |

---

## 已完成

- [x] Monorepo 整合 + 架构评审修正（2026-08-17）
- [x] 基线冒烟 4 项实证（2026-08-24）
- [x] BM25 关键词检索落地，向量路径战略禁用
- [x] 7 钩子 pre-commit + push 回读规范
- [x] 旧库资产盘点 + MVP 范围修正 v1.2（小程序/会员模块回归范围）
- [x] 有赞真实商品同步：309/309 在售全量入柜（2026-08-25，无 IP 拦截）
- [x] 有赞功能对标表·证据版（2026-08-25）：核心链路全满足，唯一真缺口=发票（已定方案，见下），负证据判定 4 项不承接（评价/会员等级/营销/物流卡片）
- [x] 发票承接实现落地（commit `e2639d4`）：知识话术+转人工+后台人工登记；专用测试与端到端验收待完成
- [x] Phase C 第三步跨端全链路闭环（2026-08-25）：真实商品下单/支付/详情/取消拦截；发票 #9566 命中（验收第 1 条过）；#9 iOS 日期修复（单测 5/5）；#10 诊断完成（limit 未透传恒 50 + 分类语义混用 + 分类表 0 条，修复方案待产品决策）

## 进行中 / 阻塞

| 事项 | 状态 | 等谁 |
|------|------|------|
| 资产迁移（凭证+知识） | ✅ 完成（2026-08-24） | — |
| P1 Phase A 后端 API 冒烟 + 数据隔离 | ✅ 完成（2026-08-25） | — |
| P1 Phase B 静态检查（四项全过） | ✅ 完成；实机走查误报已解除 | — |
| ▶ **P2 准备段：真人执行前置** | 准备段完成；真人执行段待负责人批准，测试号体验版能力仍阻塞 | AI 员工 + 项目负责人 |
| 商品真实同步（有赞在售商品） | ✅ 完成 309/309（2026-08-25，真实凭证无 IP 拦截，双轨落库 youzan_products + knowledge_base product 各 309） | — |
| 知识缺口回填（5 条 + FAQ 补充） | ⏸ **降级不阻塞**——转人工兜底已验证，排 P2 试运行前 | — |
| 发票承接（后台人工登记） | ✅ 代码已落地（`e2639d4`）；专用测试与 E2E 验收待完成 | AI 员工 |
| 商品搜索入口 | 📋 P3 增强（309 SKU 无搜索，后端参数现成） | — |
| ▶ **P1 阶段收尾（T-P1-WRAP-01）** | 🔄 四个小项已全部执行完（①limit 500 常量+回归 311 ②#13 API 不可行+兜底落地 ③口径核对 ④收口登记） | AI 员工 |
| **P1 阶段关闭** | ✅ **已关闭（2026-08-30，项目负责人确认）** | — |

## 下一步顺序

1. ✅ 商品真实数据同步（309/309）
2. ✅ Phase B 实机走查（15/15 页面导航渲染成功，95 页走查报告入库；发现 P2×2：#9 日期 iOS 兼容 / #10 商品可见范围）
3. ✅ **Phase C 第三步：跨端全链路闭环**（真实商品 + mock 支付）——下单/支付/详情/取消拦截闭环；发票 #9566 命中（验收第 1 条过）；#9 已修复（单测 5/5）；#10 诊断完成（limit 未透传恒 50 为主因 + 分类语义混用 + 分类表 0 条因同步未采集，修复方案待产品决策）
4. ✅ **Phase D 修复三连**（limit 透传 / 分类语义 / 分类采集）+ 结算三分支补证
5. ✅ **P1 收尾四小项与阶段关闭**（①limit 魔法数字 ②#13 分类关联兜底 ③商品口径核对 ④收口登记；2026-08-30 负责人确认关闭）
6. P1-5 发票实现修复 → 移除严格 xfail → E1-E4 验收
7. 阶段评审 → P2 试运行前：知识缺口回填 + 发票专用测试/E2E 验收

## 状态记录（v22，2026-08-30，P1/P2 继续推进）

- P1-4：当前 `backend/data/bot.db` 的 `knowledge_gaps` 总数与未结数均为 0；历史“5 条”来源仍待负责人确认，未猜测回填。
- P1-5：专用 API 测试已固化，发票状态与必填字段代码修复已完成；E1-E4 真实客服、后台和联动验收尚未执行，未将代码测试写成真实验收。
- P1-7：已被项目负责人否决；不再回收 FAQ、不再发送填写版、不再入库。
- P2：真人 B/C/D/E 未启动，负责人批准、授权测试号和体验版条件仍是硬阻塞。

## 状态记录（v23，2026-09-12，MiniApp 商品目录清洗与分类命名空间收口）

- 本轮 run_id：`20260912-miniapp-category-noise-r26`，绑定任务 `T-MINIAPP-COMMERCE-UX-REDESIGN`，证据 `E-20260912-006`。
- 分类命名空间：`youzan_product_categories.tag_id` 同时承载商品 tag id 与 `item.base` classification id，两类命中数分开现场统计；公开分类只输出有真实在售商品命中的项，`productCount` 与所选命名空间一致，把 tag 伪装成 classification 的空分类不再进入侧栏。首轮全量回归捕获了首次修复的命名空间错配（`ERRORS.md` M-20260912-081）。
- 同步噪声：公开 `description/subtitle/tags/specs` 过滤 `商品名称：`、秒级库存明细、`h5.youzan.com` 直购链接、`[UMP: ...]` 与纯数字标签；清洗规则独立到 `backend/app/service/catalog/customer_text.py`，同时满足文件体量门禁（M-20260912-080）。
- 履约提示：数字蜡烛、餐具等配件不再提示“提前 1 天预订”，改为现货/客服确认；蛋糕标题含蜡烛说明时仍保持蛋糕预订语义（`miniapp/miniprogram/utils/bakery.ts`）。
- 测试与阻塞：首轮全量 738.33s、8 项失败，逐项定位为分类命名空间回归（M-081）、lifespan 装配测试未同步（M-082）及 workspace/派生检查；收口全量复跑 745.7s，剩余 2 项为隔离 Harness 在覆盖率模式下泄漏 SQLite 查询连接（M-085）。修复改用 `closing(...)` 后，覆盖插桩单文件 4 项通过，Harness 评估与隔离用例合跑 9 项通过；按测试节奏约束未再启动第二次全量复跑，因此不声明全量 0 失败。
- 门禁与开放项：`payment_runtime.py` 存量文件体量门禁仍红（M-083，非本轮改动）；全量耗时超过 10 分钟（M-084）继续作为优化事项。
- 外部阻断：生产域名 `yunxifood.cn` 证书已于 2026-09-03 过期，生产 API 检查全项失败（M-20260912-078，status open），需运维续期；本轮不通过关闭 TLS 校验绕过。
- 未验证边界保持：真实微信认证支付/退款、真实闪送开放平台报价-建单-回调、真实生产验收均未执行；2027-05-31 前小程序仅限开发、调试与测试，2027-06 不是自动上线日期。

## 状态记录（v24，2026-09-12，MiniApp 商品卡可用性与按钮可见性收口）

- 本轮 run_id：`20260912-miniapp-card-semantics-and-button-visibility-r27`，绑定任务 `T-MINIAPP-COMMERCE-UX-REDESIGN`，证据 `E-20260912-007`。
- 按钮可见性：`app.wxss` 的 `button:not([size="mini"])` 重置（特异度 0,1,1）会把页面裸 class 规则的背景、圆角、内边距清零，优惠券/积分页的“去登录”和订单页操作按钮因此变成白字透明底（M-20260912-086）。三处规则改为带页面作用域后特异度提到 (0,2,1)，DevTools 计算样式恢复 `background rgb(61, 51, 45)`、`font-size 13px`、`border-radius 4px`。
- 商品卡口径：新增共享 `getProductAvailabilityLabel` / `getProductActionLabel` / `getProductAddToastLabel` / `getProductCardTip`，数字蜡烛等现货配件为“现货 + 加入购物车”，现做商品不再显示零信息量的“可预订”标签（M-20260912-087）；图片角标只保留已下架/暂时售罄，详情页常驻“在售”改为仅不可售时展示原因。
- 文案与扫描：客服页未登录标题由“客服连接已断开”改为“登录后联系客服”，积分页补齐未登录副文案（M-20260912-088）；触控扫描的商品详情状态改为播种确定性数据，消除 mock 商品 ID 造成的假失败（M-20260912-089）。
- 门禁：`audit-miniapp-button-styles` 新增 `button-reset-overrides-class` 检查并做过反向验证；`verify-all-15-pages-devtools` 的确定性未登录清单扩展到优惠券、积分、客服三页，本轮 15/15 PASS。
- 未验证边界保持：真实微信认证支付/退款、真实闪送开放平台报价-建单-回调、真实生产验收均未执行；2027-05-31 前小程序仅限开发、调试与测试，2027-06 不是自动上线日期。遗留开放项仍为 `payment_runtime.py` 存量文件体量门禁与全量测试耗时优化。

## 状态记录（v25，2026-09-13，MiniApp 真实链路预检与返回控件统一）

- 本轮 run_id：`20260913-miniapp-real-api-preflight-and-back-button-r29`，绑定任务 `T-MINIAPP-COMMERCE-UX-REDESIGN`，证据 `E-20260913-001`。
- 真实链路环境：生产域名 `yunxifood.cn` 的 Let's Encrypt 证书 `NotAfter=2026-09-03 09:41:58` 仍未续期，`check:production-domain` 与 `check:production-miniapp-api` 于 2026-09-13 复跑继续 fail（M-20260912-078，status open）；本轮不通过关闭 TLS 校验绕过。
- 防反复试错：新增 `miniapp/scripts/lib/real-api-preflight.mjs`，`devtools:product-buy-now`、`devtools:cart-checkout-real-product`、`devtools:service-smoke` 在连接开发者工具前探测 `/health`，证书/域名/网络异常时 1.9–2.3s 退出码 2 并输出具体原因（此前是 13s 后的 `timeout waiting for automator response`，易被误判为页面缺陷）；地址可用 `MINIAPP_REAL_API_BASE_URL` 覆盖，本地 `http://127.0.0.1:7001/health` 实测 200 放行。
- UI/UX：逐页目视复核 15 页运行态截图，发现商品详情返回控件为 88rpx 圆角方块（页内 `.detail-back` 覆盖了同文件前一处 `border-radius: 50%`），与其它 10 个子页的全局圆形 `.page-nav-back` 不一致；已删除页内两套规则并改用共享控件，`check:miniapp` 新增“非 tabBar 页面必须复用共享返回控件”断言，反向验证命中退出码 1（M-20260913-097）。
- 运行态复跑：`devtools:verify-all-pages` 15/15 PASS、`scan:button-touch-targets` 39 选择器/10 页面 pass、`typecheck`、`test:bakery` 8 passed、`audit:buttons` 106 控件、`audit:button-styles` 0 失败；重生成 `final-product-detail.png` 目视确认圆形返回控件生效。
- 未验证边界保持：真实微信认证支付/退款、真实闪送开放平台报价-建单-回调、真实生产验收均未执行；2027-05-31 前小程序仅限开发、调试与测试，2027-06 不是自动上线日期。


## 状态记录（v26，2026-09-13，MiniApp 结算页零资产控件、会话动作与 WXML 解析护栏）

- 本轮 run_id：`20260913-miniapp-checkout-affordance-and-wxml-scanner-r30`，绑定任务 `T-MINIAPP-COMMERCE-UX-REDESIGN`，证据 `E-20260913-002`。
- 结算页交互：已登录会话提示不再展示语义不清的“返回”主按钮；积分或余额为零且未锁单时不渲染 disabled switch，只保留“暂无可用积分/余额”说明与整行点击原因提示。运行态报告记录 `pointsSwitchVisible=false`、`balanceSwitchVisible=false`、`sessionActionVisible=false`，重生成截图目视确认空胶囊和返回按钮消失（M-20260913-099）。
- 静态门禁：`check-miniapp.mjs` 新增带引号状态的 `scanWxmlTags()`，修复旧正则把属性值 `{{pointsBalance > 0}}` 内的 `>` 当作标签结束而误报未闭合；反向插入未闭合 `<view>` 时仍能退出码 1，恢复后 15 页 15 路由通过（M-20260913-098）。
- 收口验证：`devtools:commerce-states` 与 `devtools:checkout-delivery-states` 均 PASS；带自动化端口补跑 `scan:button-touch-targets` 39 选择器/10 页面 PASS、`devtools:verify-all-pages` 15/15 PASS；`test:bakery` 8 passed、`audit:buttons` 106 控件、`audit:button-styles` 106 控件 0 失败、中文治理 coverage=1.0、开发总表 38 项、`check_project.py --skip-tests` 通过。触控扫描连接失败现在退出码 2 且不覆盖上一份有效报告（M-20260913-100）。
- 未验证边界保持：本轮仍为本地后端与 DevTools 模拟器验收；真实微信认证支付/退款、真实闪送开放平台报价-建单-回调、真实生产验收均未执行；生产域名证书过期与闪送开放平台资料/测试权限仍是外部阻塞。

## 状态记录（v27，2026-09-13，MiniApp 门店自提地址来源归一化）

- 本轮 run_id：`20260913-miniapp-pickup-address-source-r31`，绑定任务 `T-MINIAPP-COMMERCE-UX-REDESIGN`，证据 `E-20260913-003`。
- 问题来源：本地 `GET /api/v1/miniapp/shop-settings` 实测返回占位文案“门店自提，具体地址请联系客服确认”；本地 `shop_config` 表未保存 `shop_operations`，确认来自后端默认值而非后台误存（M-20260913-102）。
- 修复口径：后端 `DEFAULT_PICKUP_ADDRESS` 改为真实门店地址，`ShopOperationsService` 对空值与含“请联系客服确认”的历史占位值统一归一化；小程序 `resolvePickupAddress()` 由配置、服务与结算页共用，结算页自提地址初值改为真实门店地址；管理后台默认设置与小程序 API 契约示例同步修正。
- 门禁：`check-miniapp.mjs` 校验小程序源码不含占位地址文案，并校验后端默认运营配置与管理后台默认地址与 `config/shop.ts` 完全一致；`devtools:checkout-delivery-states` 新增 `pickup_address_source` 运行态断言。
- 本轮验证：后端定向 14 项用例通过；本地后端重启后接口返回真实地址；`check:miniapp`、`typecheck`、`devtools:checkout-delivery-states`、`devtools:commerce-states` 均通过；截图 `final-checkout-pickup-address.png` 目视确认自提门店展示真实地址。
- 未验证边界保持：闪送报价起点目前由小程序传入、后端按报价哈希一致性兜底校验，未改为服务端下发；真实闪送开放平台报价-建单-回调、真实微信支付/退款与生产验收仍未执行。

## 状态记录（v28，2026-09-13，MiniApp 群内登记与政策页运行态审计与触控基线）

- 本轮 run_id：`20260913-miniapp-registration-policy-audit-r32`，绑定任务 `T-MINIAPP-COMMERCE-UX-REDESIGN`，证据 `E-20260913-004`。
- 新增审计：`miniapp/scripts/verify-devtools-registration-policy.cjs`（`npm run devtools:registration-policy`）覆盖群内登记页结构、未登录闸门、CTA 可达性、触控目标、时间选择器联动、六步必填校验链、后端错误落页、提交成功态，以及隐私/协议/售后三个政策变体与默认回落，10 项断言全部通过。
- 真实缺陷：履约标签与时间选择器在 390px 视口仅 43px（根因 `min-height: 84rpx`）；扩展排查发现购物车步进器 24x24、窄屏“去结算”39px、优惠券/积分“去登录”43px，统一收到 88rpx（45px）并纳入触控扫描（10 页 39 选择器 → 13 页 46 选择器），记录为 `ERRORS.md` M-20260913-103。
- 自动化诊断：校验链首轮“点击无反馈”为自动化输入后的事件竞争，加入 260ms 事件队列稳定等待后 6/6 首次点击即通过；未登录闸门改为注入态固定（开发工具会话当前为已登录），不替代真实微信授权登录验证。
- 未验证边界保持：运行态证据来自本地开发服务与 DevTools 模拟器；真实微信登录、真实微信支付/退款、真实闪送开放平台报价-建单-回调与生产验收仍未执行。

## 状态记录（v21，2026-08-30，P1 正式关闭）

## 状态记录（v29，2026-09-13，MiniApp 充值金额输入与禁用操作可读性）

- 本轮 run_id：`20260913-miniapp-control-affordance-r33`，绑定任务 `T-MINIAPP-COMMERCE-UX-REDESIGN`，证据 `E-20260913-005`。
- 真实缺陷：充值页自定义金额在 390px 视口仅 259x22px，只有浅色下划线；结算与充值禁用按钮仍被微信原生 `button[disabled]` 覆盖成 `rgba(0,0,0,0.18)`/`rgb(250,250,250)`，自定义禁用态未落屏（M-20260913-104）。
- 修复口径：充值金额改为 88rpx 可见输入框并保留对齐的“元”单位；主按钮与客服发送按钮统一为暖灰底/深灰字，主按钮用 `!important` 覆盖微信原生禁用态。`verify-all-15-pages-devtools.cjs` 新增 `interactionStates`，读取 DevTools 实际尺寸和计算颜色。
- 本轮验证：充值容器/输入框均为 259x45px，三个禁用按钮对比度均为 5.48:1；`devtools:verify-all-pages` 15/15、`devtools:registration-policy`、`scan:button-touch-targets` 46/13、`devtools:commerce-states`、`devtools:checkout-delivery-states`、`devtools:verify-commerce-flows` 均 PASS；`check:miniapp`、`typecheck`、`audit:buttons` 106 控件、`audit:button-styles` 106 控件均通过；`final-recharge.png`、`final-checkout.png`、`final-chat.png` 目视确认。
- 未验证边界保持：仍为本地后端与 DevTools 模拟器验收；真实微信认证支付/退款、真实闪送开放平台报价-建单-回调与生产验收均未执行。

## 状态记录（v30，2026-09-13，MiniApp 未登录整页引导空态与优惠券伪交互）

- 本轮 run_id：`20260913-miniapp-login-gate-and-coupon-affordance-r34`，绑定任务 `T-MINIAPP-COMMERCE-UX-REDESIGN`，证据 `E-20260913-006`。
- 问题来源：未登录进入订单、收货地址、订单详情页时只有一条顶部 `session-notice`，主体整屏空白；优惠券、积分、充值页却是居中空态，同类场景两套表达（M-20260913-105）。结算页在无可用优惠券时仍显示“▼”，点开是空面板（M-20260913-106）。
- 修复口径：7 个受限页面统一为 `.yunxi-state yunxi-state--page` 整页空态（图标 + 标题 + 单行说明 + 去登录），并清理订单/地址/订单详情/结算/首页 5 处不再使用的 `session-notice` 注册；结算页无可用券时隐藏箭头、取消按下反馈，`toggleCouponPanel()` 直接短路。
- 门禁：`verify-all-15-pages-devtools.cjs` 新增 `inspectLoginGate()`（结构、CTA 文案、48x44px 触控、整页高度、说明不换行、受限内容不渲染）与结算页优惠券行断言；确定性未登录态从 7 页扩到 8 页；收口时修复审计脚手架 inspectFormFieldLabels() 播种结算态漏还原 isLoggedIn 的跨步骤状态泄漏（M-20260913-107）。
- 本轮验证：`devtools:verify-all-pages` 15/15 PASS、未登录态 8/8 PASS（空态 362~366x490px、CTA 79x45px、说明高度 20px 单行）；`devtools:commerce-states`、`devtools:checkout-delivery-states`、`devtools:verify-commerce-flows`、`scan:button-touch-targets`（46/13）、`check:miniapp`、`typecheck`、`test:bakery` 8/8、`audit:buttons`（110 控件）、`audit:button-styles`（110 控件 0 失败）均通过；`final-logged-out-orders.png`、`final-logged-out-checkout.png` 等截图目视确认。
- 未验证边界保持：仍为本地后端与 DevTools 模拟器验收；“去登录”后的真实微信授权登录链路、真实微信支付/退款、真实闪送开放平台报价-建单-回调与生产验收均未执行。

## 状态记录（v31，2026-09-13，MiniApp 订单履约口径分叉与商品目录层级收口）

- 本轮 run_id：`20260913-miniapp-order-fulfillment-and-catalog-hierarchy-r35`，绑定任务 `T-MINIAPP-COMMERCE-UX-REDESIGN`，证据 `E-20260913-007`。
- 问题来源：目视复核运行态截图发现门店自提订单仍按北京市内闪送口径渲染，列表与详情都显示“闪送费”、只给配送地址、进度统一写“配送中”（M-20260913-108）；商品详情首图与元信息重复展示同一销量（M-20260913-109）；已登录无订单时只剩一句裸空态、整屏无入口（M-20260913-110）；`app.json` 与自定义 tabBar 文案不一致（M-20260913-111）。
- 修复口径：后端 `OrderSerializationService` 新增 `pickupAddress` 快照返回，`OrderSummary` 契约与 API 文档同步；订单列表按履约方式改文案；订单详情自提单隐藏闪送费、展示“自提门店”与快照地址、仅配送单展示“配送地址”，进度按履约方式区分“待取货/配送中”并补齐各状态说明；商品详情移除首图重复销量角标；订单页已登录空态补整页空态与“去选购”；`app.json` tabBar 文案对齐“商品/我的”。
- 门禁：`check-miniapp.mjs` 新增 `checkOrderFulfillmentPresentation()` 与 `checkTabBarLabels()`；`verify-miniapp-commerce-flows.cjs` 覆盖配送/自提两种订单详情语义；`verify-devtools-commerce-states.cjs` 覆盖履约信息可读性与已登录空订单引导。
- 本轮验证：后端定向用例 6/6 与 14/14 PASS；`typecheck`、`check:miniapp`（15 页 15 路由）、`test:bakery` 8/8、`devtools:verify-commerce-flows`、`devtools:commerce-states`、`devtools:verify-all-pages`（15/15 页、8/8 未登录态）、触控扫描（46 选择器/13 页面）与 5 个审计脚本 `node --check` 均 PASS；`commerce-flow-order-detail.png`、`commerce-flow-order-detail-pickup.png`、`final-orders-readable-meta.png`、`final-orders-empty.png` 目视确认。
- 未验证边界保持：仍为本地后端（127.0.0.1:7001）与 DevTools 模拟器验收；自提地址取订单创建时快照，存量历史订单仍为旧值；真实微信支付/退款、真实闪送开放平台报价-建单-回调与生产验收均未执行。


## 状态记录（v32，2026-09-13，MiniApp 结算时间 WYSIWYG、已登录空态与商品目录展示收口）

- 本轮 run_id：`20260913-miniapp-schedule-wysiwyg-and-empty-states-r36`，绑定任务 `T-MINIAPP-COMMERCE-UX-REDESIGN`，证据 `E-20260913-008`。
- 问题来源：目视复核发现结算页重新进入后用默认小时重置选择器、但提交值仍保留用户已选 `expectTime`，选择器显示 18:00 而实际提交 19:30（M-20260913-112）；优惠券/积分登录后空结果仍是裸文本面板、与订单页整页空态不一致（M-20260913-113）；商品目录标题有不可点击的“自提价”伪控件与“人气汇聚/匠心手作/麦香现烤/层层甜蜜/生活美学”等无数据依据副标题（M-20260913-114）。
- 修复口径：新增 `utils/checkout-time.ts` 的 `parseExpectTime()`/`resolveCheckoutHourIndex()`/`resolveCheckoutMinuteIndex()`/`resolveCheckoutSchedule()`，由提交值反推日期/小时/分钟索引并将过截单日抬到最早可预约日期；结算页 `loadCheckout()` 经 `syncExpectTimeSchedule()` 统一重建选择器与 `expectTime`。优惠券/积分空结果与加载失败态统一为 `.yunxi-state yunxi-state--page`，空态“去选购”、失败态“重新加载”。商品目录移除静态 `products-heading__service` chip 与装饰性副标题，侧栏显示真实 `N 款`，标题显示 `N 款 · 按销量排序`。
- 门禁：新增 `test:checkout-time` 5 项单测；`verify-devtools-checkout-delivery-states.cjs` 新增 `expect_time_picker_restore`；`verify-devtools-commerce-states.cjs` 新增优惠券/积分已登录空态与 44px 触控断言；`check-miniapp.mjs` 新增 `checkCatalogHeadlineAndScheduleConsistency()`。
- 本轮验证：`test:checkout-time` 5/5、`typecheck`、`check:miniapp`（15 页/15 路由）、`check:page-api-coverage`（15 页/34 术语/9 边界）、`test:bakery` 8/8、`test:member-assets` 12/12、`test:order-summary` 6/6、`audit:buttons` 115 控件、`audit:button-styles` 115 控件 0 失败均通过；`devtools:checkout-delivery-states` 记录 `expectTime=2026-09-13 19:30 / restoredHour=19 / restoredMinute=30`，`devtools:commerce-states` 记录优惠券/积分空态与 79x45px“去选购”，`devtools:verify-all-pages` 15/15、`devtools:verify-commerce-flows` 与触控扫描（46 选择器/13 页面）PASS；`final-products.png`、`final-coupons-empty.png`、`final-points-empty.png` 目视确认。
- 新增未决缺口：有赞商品分类与商品标签 ID 不同源，本地库 34 条公开分类与 310 款在售商品 `tag_ids_json` 零交集、`classification_ids_json` 全为空，分类接口恒为空，商品页只能单层展示（M-20260913-115，open）；需取得真实有赞接口权限后建立分类-商品关联或反向拉取方案，当前不得用静态分类名兜底。
- 未验证边界保持：仍为本地后端（127.0.0.1:7001）与 DevTools 模拟器验收；真实微信授权登录、真实微信支付/退款、真实闪送开放平台报价-建单-回调与生产验收均未执行；生产域名证书过期、闪送开放平台资料/测试权限与有赞分类接口权限仍未解除。

## 状态记录（v33，2026-09-13，MiniApp 购物车长名称与充值记录空态收口）

- 本轮 run_id：`20260913-miniapp-cart-long-title-and-recharge-empty-r37`，绑定任务 `T-MINIAPP-COMMERCE-UX-REDESIGN`，证据 `E-20260913-009`。
- 问题来源：逐页目视复核 15 页截图发现购物车商品名单行截断，当前最长真实商品名 41 个汉字只能显示一个残句（M-20260913-116）；同一页面长状态标签被右侧数量步进器覆盖（M-20260913-117）；充值记录空态仍是裸文本，与订单/优惠券/积分页统一空态不一致。
- 修复口径：购物车卡片重构为“勾选 + 商品图”左侧核对列与独占信息列，商品名允许两行并与商品图一同进入完整商品详情；库存/购买提示标签移到价格行，加 `max-width: 180rpx`、溢出省略与收缩约束。充值记录空态改为 `.yunxi-state yunxi-state--section`（标题“暂无充值记录”、说明“充值成功后，记录会显示在这里”），`app.wxss` 新增分区空态样式。
- 门禁：新增 `devtools:cart-long-title`（41 字真实商品名播种，断言两行 clamp、标题区宽高、标签与步进器零重叠、点击名称进入详情）；`verify-devtools-product-purchase-path.cjs` 增加真实商品购物车两行断言；`verify-all-15-pages-devtools.cjs` 增加充值记录空态结构/尺寸断言；`check-miniapp.mjs` 增加 `checkRechargeRecordsEmptyState()`。
- 本轮验证：`typecheck`、`check:miniapp`、`check:page-api-coverage`、`devtools:checkout-delivery-states` 均 PASS；`devtools:cart-long-title` PASS（lineClamp=2、标题区 278x39px、标签/步进器重叠 0）；`devtools:product-purchase-path` PASS；`devtools:verify-commerce-flows`、`devtools:commerce-states`、`devtools:verify-all-pages` 15/15 PASS（充值空态 337x92px）；`final-cart-long-title.png`、`final-cart-real-product.png` 目视确认。
- 未验证边界保持：仍为本地后端（127.0.0.1:7001）与 DevTools 模拟器验收；真实微信授权登录、真实微信支付/退款、真实闪送开放平台报价-建单-回调与生产验收均未执行；有赞分类-商品关联缺口（M-20260913-115）仍为 open。

## 状态记录（v42，2026-09-14，MiniApp 展示型商品只读收敛）

- 本轮 run_id：`20260914-miniapp-display-only-purchase-guard-r50`，绑定任务 `T-MINIAPP-COMMERCE-UX-REDESIGN`，证据 `E-20260914-006`。
- 问题来源：目录里 5 款标题自述“非卖品仅展示 / 勿拍 / 虚拟价格”的有赞同步商品仍带“预订”按钮，可以加入购物车并进入结算（M-20260913-137）。
- 修复口径：后端新增 `isPurchasable` 读模型（`service/catalog/purchasability.py` + `serialization.py`），`youzan_repo.get_prices_and_stocks()` 返回 `title` 供下单校验使用，`service/order/inventory.py` 在库存与价格校验前逐单拦截展示型商品；小程序 `utils/bakery.ts` 统一输出“仅供展示 / 查看 / 仅用于原料或产品展示，不参与下单”，首页、商品目录、购物车推荐与商品详情四页阻断快捷预订、加购与立即购买，详情页改为只读说明卡 + “返回选购 / 咨询客服”。
- 门禁：`check-miniapp.mjs` 新增 `checkDisplayOnlyProductGuard()` 静态守卫；新增运行态审计 `devtools:display-only-products`（`verify-devtools-display-only-products.cjs`），覆盖服务端读模型集合、目录卡动作与标签、详情页控件收敛、强制调用 `addToCart`/`buyNow` 后购物车仍为空，并产出 `display-only-product-detail.png` 证据。
- 本轮验证：重启本地后端（`127.0.0.1:7001`，PID 21892）后翻页拉全 310 款，恰好 5 款 `isPurchasable=false`、其余 305 款为 `true`；5 款直连 `POST /api/v1/miniapp/orders` 全部返回 `400 商品仅供展示，不可下单`；后端定向 `pytest tests/service/test_catalog.py tests/service/test_order.py` 48/48，前端 `typecheck`、`test:bakery` 9/9、`check:miniapp`、`devtools:display-only-products` PASS；整套运行态回归 `devtools:verify-all-pages`（15/15 页 + 8/8 未登录态）、`devtools:product-purchase-path`、`devtools:product-search`（19 项）、`devtools:verify-commerce-flows`、`devtools:checkout-delivery-states`、`scan:button-touch-targets`（13 页 47 选择器）全部 PASS。
- 未验证边界保持：展示型判定当前是标题关键词保守口径，有赞侧的正式“仅展示”分组/标签仍需客服/店主确认；真机、真实微信支付/退款、真实闪送与生产验收仍未执行；有赞分类-商品关联仍待 IP 白名单（M-20260913-115、M-20260913-148）；闪送开放平台资料与测试权限未到位，计划书 Task 1 Step 3 与 Task 3 Step 5 保持外部阻塞。

## 状态记录（v41，2026-09-14，MiniApp 群内登记服务端履约校验收口）

- 本轮 run_id：`20260914-miniapp-registration-server-schedule-r46`，绑定任务 `T-MINIAPP-COMMERCE-UX-REDESIGN`，证据 `E-20260914-002`。
- 修复口径：`OrderScheduleService` 开放共享的 `validate_expect_time()`，把北京时间、营业时段和当天 17:00 截单规则抽成纯函数；`CustomerGroupOperationsService` 要求 `desiredTime` 并复用该 service，`lifespan_services.py` 向订单与客户群登记注入同一实例，`OrderApplicationService` 保持可选注入与原有默认行为。
- 本轮验证：后端定向 65/65、相关 Python 文件 `ruff check` 通过；最新代码在本地 `127.0.0.1:7001` 重启（PID 32728），`/health=ok`，日志保留在 `backend/reports/local-runtime/`；DevTools `wx.login` 与订单/地址/聊天真实受保护接口 4/4 PASS，`devtools:same-day-scheduling` PASS，`devtools:registration-policy` 11 项页面断言通过。
- 环境边界：Windows 会话处于锁屏状态，`registration-policy` 的 7 张截图连续 3 次采集失败，整轮按环境阻塞（BLOCKED）记录；未把它伪报为 PASS，解锁后需补视觉帧。
- 未验证边界保持：有赞分类-商品关联仍待 IP 白名单（M-20260913-115、M-20260913-148）；5 款“非卖品仅展示/勿拍”商品仍可预订（M-20260913-137，待业务确认）；真机、真实微信支付/退款、真实闪送与生产验收仍未执行。
- update_20260914：其中“5 款非卖品仍可预订”已由 r50 收口（M-20260913-137 转 guarded，E-20260914-006）；本条其余内容保留为 r46 时点快照。

## 状态记录（v40，2026-09-14，MiniApp 群内登记时间基线跨日收口）

- 本轮 run_id：`20260914-miniapp-registration-schedule-baseline-r45`，绑定任务 `T-MINIAPP-COMMERCE-UX-REDESIGN`，证据 `E-20260914-001`。
- 问题来源：北京时间 00:01 复跑 `devtools:same-day-scheduling` 时，群内登记页 `dateStartValue`/`selectedDateValue` 已是 `2026-09-14`，但 `isSameDayRegistration=false` 且当天客服确认提示不显示（M-20260914-001）。根因是页面 `data` 默认值在模块求值只算一次，`onLoad` 只重算 `desiredTime` 与 `selectedDateValue`，日期起点、小时选项与当天标记停留在小程序启动时刻。
- 影响面：不展示“当天登记须客服确认”提示；17:00 前启动的进程在 17:00 后打开登记页时，日期选择器仍以今天为起点、小时选项含已过时段，可提交违反截单规则的当天登记，而群内登记后端只按字符串保存 `desiredTime`、无兜底校验。
- 修复口径：新增 `REGISTRATION_BUSINESS_HOURS` 与 `buildRegistrationSchedule(expectTime?, now)`，用 `resolveCheckoutSchedule()` 统一产出日期起点/终点、可选小时与选中索引、`desiredTime` 与当天标记；`data`、`onLoad`、`onShow` 三处统一重建，过期选择抬到最早可预约时间。
- 门禁：`check-miniapp.mjs` 新增 `checkRegistrationScheduleRefresh()`（并扩展 `extractPageDataKeys()` 解析 `...buildXxx()` 展开字段）；`verify-devtools-same-day-scheduling.cjs` 新增三项运行态断言：当天标记=所选日期是否为今天、日期落在可选区间、注入过期状态后 `onShow` 必须重建基线。
- 本轮验证：`devtools:same-day-scheduling` PASS（`promptVisible=true`、`sameDayFlagMatchesSelection=true`、`dateWithinRange=true`；`stale-state-repair` 后 `dateStartValue=2026-09-14`、`hourOptions=09..19`）；`devtools:verify-all-pages` 15/15 页 + 8/8 未登录态 PASS；`devtools:registration-policy`、`devtools:product-search`（18 项）、`commerce-states`、`checkout-delivery-states`、`cart-long-title`、`product-purchase-path`、`scan:button-touch-targets`（46 选择器 / 13 页）、`audit:button-styles`（119 控件 / 0 失败 0 警告）PASS；`check:miniapp`、`typecheck` PASS；`final-group-registration.png` 目视确认当天提示已渲染。
- 未验证边界保持：群内登记后端缺截单服务端校验（M-20260914-001 后续补强项）；结算页在持续可见并跨过 17:00 的窄窗口不重建选择器，但后端 `order/schedule.py` 会以“当天订单已于 17:00 截止”拒绝提交；有赞分类-商品关联仍待 IP 白名单（M-20260913-115、M-20260913-148）；真机、真实微信支付/退款、真实闪送与生产验收仍未执行。

## 状态记录（v39，2026-09-13，MiniApp 商品目录搜索与长尾查找收口）

- 本轮 run_id：`20260913-miniapp-product-search-and-catalog-integrity-r43`，绑定任务 `T-MINIAPP-COMMERCE-UX-REDESIGN`，证据 `E-20260913-016`。
- 问题来源：商品优先型目录的主路径是“先搜到想要的商品”，但此前没有任何专项审计覆盖搜索。运行态复核发现：输入关键词后搜索栏外框由 33px 跳到 45px（M-20260913-134）；搜索栏同时渲染两个 × 清空按钮，且旧断言只取首个匹配（M-20260913-135）；无结果时没有回全部商品的出口，提示还在用内部术语“全局检索”（M-20260913-136）；锁屏环境下截图失败被计成 15/15 页面缺陷（M-20260913-138）。
- 问题来源（r43.1）：商品搜索审计自身在截图失败时把 `search-results-screenshot` 记为 `ok:false`，顶层仍输出 `PASS`，证据缺失被误报为绿灯（M-20260913-140）。
- 修复口径：搜索栏与输入框统一 88rpx，清空按钮保留 88rpx 触控盒、可视圆点收到 52rpx；删除残留的重复清空节点；空态改为“换个关键词试试，或先看看全部商品”并加“查看全部商品”一键出口；搜索结果新增“共找到 N 款商品 / 按销量排序”计数行；`verify-all-15-pages-devtools.cjs` 新增锁屏探测、截图跳过与环境阻塞（BLOCKED）状态。
- 门禁：新增 `devtools:product-search`（`verify-devtools-product-search.cjs`），断言目录完整性（页面=接口 310 款且顺序一致）、长尾命中（“曲奇”3 条全部在首屏 12 款之外）、搜索栏输入前后高度差 ≤1px、清空按钮唯一且 ≥44px、空态出口、结果快捷预订与进详情；`clearCount` 断言防止重复控件回归。
- 门禁（r43.1）：`verify-devtools-product-search.cjs` 与 15 页审计统一三态：通过（PASS）退出码 0、断言失败（FAIL）退出码 1、环境阻塞（BLOCKED）退出码 2；页面断言失败按断言失败处理，截图证据采集失败按环境阻塞处理，二者不再混为通过。
- 本轮验证：`devtools:product-search` PASS（bar 高度 45→45px、clearCount 0→1、clearSize 45x45、快捷预订写入并出现底栏）；`scan:button-touch-targets` PASS（46 选择器 / 13 页）；`devtools:verify-all-pages` 15/15 页 PASS、未登录态 8/8 PASS（23 张截图齐全，无环境阻塞）；`devtools:commerce-states`、`cart-long-title`（复跑 5/5）、`checkout-delivery-states`、`product-purchase-path`、`registration-policy`、`verify-commerce-flows`、`walkthrough:phase-c`、`devtools:product-search`（r43.3 为 12/12；r43.4 扩到 16 项，验证首屏 30 款/310 命中、10 次增量到 310/310、目录触底 12→24；r43.5 扩到 18 项，验证关键词收窄后 scrollTop 900→0、分类切换后 scrollTop 900→8 且锚点为 products-catalog-top）均 PASS；`check:miniapp`、`typecheck`、`test:bakery` 8/8、`scan:button-touch-targets`（46 选择器 / 13 页）、`audit:buttons`（119 控件）、`audit:button-styles`（0 失败 0 警告）PASS。
- 本轮验证（r43.1）：锁屏状态下 `devtools:product-search` 12 项页面断言全部通过，截图项为 `fail to capture screenshot`，整轮输出 环境阻塞（BLOCKED）与退出码 2（修正前会误报通过）；`devtools:verify-all-pages` 15/15 页面断言通过、整轮为 环境阻塞（BLOCKED）；`node --check`、`check:miniapp`、`typecheck` PASS。
- 问题来源（r43.2）：`devtools:commerce-states` 在锁屏下以 `fail to capture screenshot` 直接整轮失败；盘点发现 7 个审计脚本仍存在同类裸截图调用，属于 M-20260913-138 同类问题第二次出现（M-20260913-142）。
- 修复口径（r43.2）：新增共享模块 `miniapp/scripts/lib/devtools-audit-status.cjs`，统一截图证据捕获、状态汇总与退出码；`commerce-states`、`cart-long-title`、`checkout-delivery-states`、`product-purchase-path`、`registration-policy`、`commerce-flows`、`walkthrough-phase-c` 全部改为页面断言继续执行、截图失败只记环境阻塞。
- 本轮验证（r43.2）：锁屏下串行复核 `commerce-states` 11 检查 0 错误、`cart-long-title` 5 检查、`checkout-delivery-states` 10 检查 0 错误、`product-purchase-path` 7 检查 0 错误、`registration-policy` 11 检查 0 错误、`commerce-flows` 12 检查 0 错误，均为环境阻塞（BLOCKED）退出码 2；`walkthrough:phase-c` 15/15 页导航成功、控制台 0 warning / 0 error、15 页截图阻塞、退出码 2；页面断言未发现产品缺陷。
- 未验证边界保持：搜索仍是本地全量（`limit=500`）过滤，未做服务端分页搜索；全量目录 310 款首屏仅 12 款、需点“查看更多”25 次，搜索“蛋糕”一次渲染 310 卡且内容高度 36281px（M-20260913-141，open，已列入下一轮 UI/UX 方案）；运行态仍为本地后端（127.0.0.1:7001）与 DevTools 模拟器（iPhone 12/13、SDK 3.15.2、390px）；目录 5 款“非卖品仅展示/勿拍”商品仍可预订（M-20260913-137，open，待业务确认）；有赞分类-商品关联缺口（M-20260913-115）仍为 open；真实支付/退款、真实闪送开放平台与生产验收均未执行。


## 状态记录（v38，2026-09-13，MiniApp 结算调度审计与群内登记成功态收口）

- 本轮 run_id：`20260913-miniapp-schedule-audit-and-registration-success-r42`，绑定任务 `T-MINIAPP-COMMERCE-UX-REDESIGN`，证据 `E-20260913-015`。
- 问题来源：结算审计截图显示选择器 `2026-09-13 18:00` 与预览 `2026-09-15 15:00` 并存（M-20260913-131）；登记成功态截图残留上一轮“活动批次不存在或已结束”Toast（M-20260913-132），并出现“登记已提交”与“微信身份 · 未登录”并存（M-20260913-133）；成功结果面板本身仅有裸文本堆叠，信息层级弱于其他页面。
- 修复口径：结算审计删除直接写入 `expectTime` 的旁路，统一调用页面 `syncExpectTimeSchedule()`；新增 `checkout-schedule-consistency` 同时校验提交值、日期、小时、分钟与预览。登记审计成功态截图前调用 `hideToast`，匿名/登录状态都注入完整 `sessionView`，并断言成功标题、说明、四行摘要、登录身份和双按钮尺寸。群内登记成功面板改为确认图标、说明、四行摘要和等宽双操作按钮；保留原有业务文案与提交行为。
- 环境前置：本地 uvicorn `127.0.0.1:7001` 进程 30316 运行中，`/health` 返回 `status=ok`；DevTools 自动化端口 `9420` 已监听。
- 本轮验证：`devtools:verify-commerce-flows` PASS（`expectTime=2026-09-13 18:00`，date/hour/minute/previewText 一致）；`devtools:registration-policy` PASS（`successSessionText=微信身份 · 已登录`、四行摘要、两个 45px 操作按钮）；`devtools:verify-all-pages` 15/15 PASS、8/8 未登录态 PASS；`check:miniapp`、`typecheck`、两个修改脚本 `node --check` 均 PASS；两张关键截图目视确认。
- 未验证边界保持：运行态仍为本地后端与 DevTools 模拟器（iPhone 12/13、SDK 3.15.2、390px）；首次登记政策复跑出现一次 automator 响应超时，原样单实例复跑通过，未形成产品失败证据；真机微信登录、真实微信支付/退款、真实闪送开放平台报价-建单-回调与生产验收均未执行；有赞分类-商品关联缺口 M-20260913-115 仍为 open。


## 状态记录（v37，2026-09-13，MiniApp 购物车推荐卡口径统一、首页商品卡可读性与 DevTools 审计环境预检）

- 本轮 run_id：`20260913-miniapp-cart-recommend-parity-and-audit-preflight-r41`，绑定任务 `T-MINIAPP-COMMERCE-UX-REDESIGN`，证据 `E-20260913-014`。
- 问题来源：购物车“推荐商品”卡自建动作文案（裸“加入”）且加购提示恒为“已加入预订单”，与首页/商品列表统一 helper 分叉，配件商品出现动作与提示矛盾（M-20260913-126）；首页商品卡购买说明仅 19rpx，低于商品列表 22rpx/11px 基线（M-20260913-127）。
- 环境问题（已入错账）：DevTools 多实例/陈旧自动化端口导致 products/profile 页面空白与 cart/recharge/checkout automator 超时的假失败（M-20260913-128）；本地 uvicorn 未运行时页面进入兜底空态，首轮审计仅 11/15（M-20260913-129）；商品详情悬浮栏断言只等 class 不等背景过渡，产生实底假失败（M-20260913-130）。
- 修复口径：推荐卡改用 `getProductActionLabel()` / `getProductAddToastLabel()` / `getProductCardTip()`，`soldText`→`hintText`、`.recommend-sold`→`.recommend-hint`（两行 clamp + 22rpx）；首页 `.product-tip` 19rpx→22rpx 并限制在卡片宽度内换行；审计脚本新增连接后渲染预检，无法渲染首页即 exit=2 且不覆盖上一份报告。
- 门禁：`check-miniapp.mjs` 新增 `checkCartRecommendedActionCopy()`、扩展 `checkProductCardHintReadability()` 到首页；`verify-devtools-cart-long-title.cjs` 新增 `cart-recommend-card-copy`；`verify-all-15-pages-devtools.cjs` 新增首页商品卡购买说明量测。
- 本轮验证：`devtools:cart-long-title` PASS（3×“预订”+1×“加入购物车”，hintFontSize=11px，价格/动作零重叠）；`devtools:verify-all-pages` 15/15 PASS（购买说明 6 条、最小字号 11px、最大溢出 0.0px）；`devtools:verify-commerce-flows` PASS；`check:miniapp`、`typecheck` PASS；三项门禁变异测试均精确失败。
- 未验证边界保持：运行态仍为本地后端（127.0.0.1:7001）与 DevTools 模拟器（iPhone 12/13、SDK 3.15.2、390px）；本地后端必须保持运行；小屏机型、真机、真实支付/退款、真实闪送开放平台与生产验收均未执行；有赞分类-商品关联缺口（M-20260913-115）仍为 open。


## 状态记录（v36，2026-09-13，MiniApp 购物车状态胶囊长文案截断收口）

- 本轮 run_id：`20260913-miniapp-cart-tag-copy-r40`，绑定任务 `T-MINIAPP-COMMERCE-UX-REDESIGN`，证据 `E-20260913-013`。
- 问题来源：逐页目视复核购物车真实商品链路截图发现状态胶囊被省略号截断为“自提价展示，闪…”，运费口径不可读（M-20260913-125）。
- 修复口径：库存充足分支改用 `getProductAvailabilityLabel()` 输出“现货/仅余 N 件”等短事实，无额外事实时不渲染胶囊（`wx:if="{{item.stockText}}"`）；长运费口径保留在底部“商品合计 · 不含闪送费”。
- 门禁：`check-miniapp.mjs` 新增 `checkCartTagCopy()`；`verify-devtools-cart-long-title.cjs` 新增 `cart-healthy-stock-tag` 与 `cart-low-stock-tag`，并在刷新后重新获取元素句柄避免断言假失败。
- 本轮验证：`devtools:cart-long-title` PASS（healthy tagHidden=true；low stock “仅余 3 件”且零重叠；长名仍两行并可点击进详情）；`devtools:verify-commerce-flows` 与 `devtools:verify-all-pages` 15/15 PASS；`check:miniapp`、`typecheck` PASS。
- 未验证边界保持：仍为本地后端（127.0.0.1:7001）与 DevTools 模拟器验收；小屏机型未复测；真实微信支付/退款、真实闪送开放平台与生产验收均未执行；有赞分类-商品关联缺口（M-20260913-115）仍为 open。


## 状态记录（v35，2026-09-13，MiniApp 首页服务承诺、群内登记闪送口径与商品详情滚动悬浮栏收口）

- 本轮 run_id：`20260913-miniapp-promise-registration-and-detail-nav-r39`，绑定任务 `T-MINIAPP-COMMERCE-UX-REDESIGN`，证据 `E-20260913-012`（另含 `E-20260913-011` 客服文案）。
- 问题来源：逐页目视复核发现首页服务承诺卡说明只有 18rpx 且单行截断，第三项把已确认的截单规则弱化为“17:00 前咨询”（M-20260913-121）；群内登记页把北京闪送写成“门店配送”且全页没有运费承担说明（M-20260913-122）；商品详情滚动后正文穿透透明悬浮栏，与状态栏时间和返回控件直接叠字（M-20260913-123）；三处 DevTools 断言用固定等待造成假失败（M-20260913-124）。
- 修复口径：首页第三项改为“当天订单 17:00 截单”，标题 24rpx、说明 22rpx 并允许两行；群内登记配送选项改为“北京闪送”，选闪送时展示“运费按收货地址实测、由顾客承担”；商品详情新增 `navSolid` 滚动状态，`scrollTop > 8` 切实底导航栏、回顶恢复透明；商品卡购买说明提升到 22rpx 并允许两行。
- 门禁：`check-miniapp.mjs` 新增 `checkHomePromiseCardReadability()`、`checkGroupRegistrationDeliveryCopy()`、`checkProductDetailScrollNav()` 与 `checkProductCardHintReadability()`；`verify-all-15-pages-devtools.cjs` 新增 `inspectProductDetailScrollNav()`/`waitForDetailNavState()`（空态跳过，真实商品由商务流程覆盖）；`verify-miniapp-commerce-flows.cjs` 新增 `product-detail-scroll-nav`。
- 本轮验证：`devtools:verify-all-pages` 15/15 PASS（服务承诺说明三项完整、最小字号 11px）；`devtools:verify-commerce-flows` PASS（`scrolledNavBackground=rgb(255, 255, 255)`，首屏透明/滚动实底/回顶复透明均成立）；`devtools:registration-policy` PASS（`tabText=北京闪送` 与运费说明）；`check:miniapp`、`typecheck` 均 PASS。
- 未验证边界保持：仍为本地后端（127.0.0.1:7001）与 DevTools 模拟器验收（iPhone 12/13、SDK 3.15.2、390px 视口）；DevTools 截图顶部边缘存在模拟器旧帧残留，页面 DOM 量测确认导航区 0~88px、内容区自 88px 起，非页面缺陷；真机与小屏机型未复测；真实微信支付/退款、真实闪送开放平台与生产验收均未执行；有赞分类-商品关联缺口（M-20260913-115）仍为 open。


## 状态记录（v34，2026-09-13，MiniApp 商品列表缓存键与详情底部安全区收口）

- 本轮 run_id：`20260913-miniapp-product-cache-limit-and-detail-footer-r38`，绑定任务 `T-MINIAPP-COMMERCE-UX-REDESIGN`，证据 `E-20260913-010`。
- 问题来源：首页“今日推荐”货架商品数在多次 DevTools 审计间出现 4/5/6 条漂移，同一时刻精选接口恒返回 6 条（M-20260913-118）；商品详情内容区底部留白写死 `220rpx`，而固定操作栏高度为 `100rpx + env(safe-area-inset-bottom)`，无安全区机型会多出约 62px 空白（M-20260913-119）。
- 根因：`buildProductsCacheKey()` 未包含 `limit`，首页（featured+6）、购物车推荐（featured+4）、商品详情关联（featured+5）共用同一 5 分钟缓存条目，访问顺序决定后续页面拿到的条数。
- 修复口径：缓存键补 `limit: options.limit ?? 0`，三个调用点各自独立缓存；商品详情底部改为 `calc(env(safe-area-inset-bottom) + 140rpx)`，与真实底栏高度同源伸缩并保留 40rpx 呼吸间距。
- 门禁：`check-miniapp.mjs` 新增 `checkProductListCacheKeyIncludesLimit()` 与 `checkProductDetailFooterSpace()`；`verify-all-15-pages-devtools.cjs` 首页货架新增“接口条数 vs 渲染条数”交叉校验并轮询至计数稳定；`verify-devtools-product-purchase-path.cjs` 新增 `product-detail-footer-gap`（<0 遮挡或 >48px 大片空白均失败）。
- 本轮验证：修复前审计报“渲染=5，接口=6”；修复后 `devtools:verify-all-pages` 15/15 PASS（首页“商品数=6；接口=6，渲染=6”）；`devtools:product-purchase-path` PASS（footer gap 22.44px → 14.44px，操作栏高 92px）；`typecheck`、`check:miniapp`（15 页/15 路由）与两个改动脚本 `node --check` 均 PASS；`final-home.png` 目视确认货架为完整两列网格。
- 未验证边界保持：仍为本地后端（127.0.0.1:7001）与 DevTools 模拟器验收（iPhone 12/13、SDK 3.15.2、390px 视口）；无安全区机型只做了策略收口、未真机复测；真实微信授权登录、真实微信支付/退款、真实闪送开放平台报价-建单-回调与生产验收均未执行；有赞分类-商品关联缺口（M-20260913-115）仍为 open。

- P1 四小项（T-P1-WRAP-01）已全部执行并有独立可复现证据（命令输出/DB 查询）：①`GET /products?limit=500` → 311 条（default 仍 50）；②#13 有赞 item.get/onsale 无 classification 字段（深度遍历零命中）+ 兜底文案已落地（"该分类暂无商品/查看全部"）；③库 311 vs 有赞在售 310（差集仅 5811485729 已下架残留，0 缺）——"309 全量"为首次同步快照口径；④LOGBOOK trace 20260825-p1-wrap。
- **P1 阶段关闭：已完成**——2026-08-30 经项目负责人明确确认；P2 准备段保持完成，P2 真人执行段继续已阻塞（blocked），不因 P1 关闭自动启动。

## 状态记录（v19，2026-08-26，P2 模拟器首测 4 缺陷修复收口）

- P2 模拟器首测（A 项商品浏览）发现 4 缺陷，由架构师现场修复（授权偏差，即时排障，已在 LOGBOOK trace 20260826-p2trial-sim-fixes 如实记录）；AI 员工独立复核 + 分 4 commit 收口（C1 621753c / C2 12cc895 / C3 ec1e9d5 / C4 23f0c4e），当前 VERSION=0.133.0-p2trial.3（后续 77f9346 完成超时守卫收口）。
- 4 缺陷：① 首页 wx:for-item 缺失（变量遮蔽→商品卡全空、点击空 id 报"商品不存在"）② 开发版 API 默认连远程线上配置（本地修复不可见）③ featured 空配置返回空属特性但占位模板 manual 占位 ID 永不命中→空白货架 ④ 图片 http 被 3.x 基础库拒 + 代理端点 500（fetch 异常未保护）。
- P2 模拟器 **A 项完成**；B/C/D/E 待走查。
- **体验版状态拆分**：3a DevTools `Empty file` 瞬时竞态已解除；3b 测试号不支持体验版，仍等 mp 后台/正式 AppID 条件（不向真实用户开放、不提审）。
- **部署遗留项（上线前必须）**：生产库上线前须配置 `shop_config.featured_products` 精选 6 款（当前仅本地库直写，无 DB 迁移/发布配置覆盖 home-featured 默认值）。
- 遗留观察：模拟器 Console Error: timeout 未定位（Launch Time 偏慢），非阻断。

## 状态记录（v20，2026-08-26，新仓全量 pytest 首次基线清零）

- 上轮（T-COMMIT-P2TRIAL-FIXES-01）将 5-6 个失败统称"gbk 解码/环境问题"定性不准；本轮回溯给出三类真实根因（trace 20260826-test-baseline-zero）：①lifespan 桩缺 app.api.admin.invoices（e2639d4 发票承接真实回归）②进度清单头未随 VERSION bump 同步③backup C 盘守卫 Windows 开发机不兼容（skipif win32 跳过，守卫不改）。
- 偏差追加：第 4 个 test_cli_help 同样因 Windows gbk 子进程解码失败，同属 Windows 不兼容，已如实披露加第 4 跳过。
- **新仓全量 pytest 首次基线清零**：`pytest --no-cov -q` rc=0；miniapp `npm run typecheck` rc=0。
- 教训沉淀（commit-workflow.md 已写入）：VERSION 变更必须与根目录 + backend/ 两份 `项目进度与配置清单.md` 表头同步，否则 `test_repository_progress_header_matches_version_file` 会红；报告失败必须给根因证据而非归类标签。
- 该历史段落对应的 D1/真实支付/客户群事项当前均为已阻塞（blocked）或已暂缓（deferred），具体以主线任务总表为准。
> r51 非卖品价格与库存口径：`T-MINIAPP-COMMERCE-UX-REDESIGN` 新增 `E-20260914-007`（非卖品占位价与库存不再当作真实售价展示，run_id `20260914-miniapp-display-only-price-truthfulness-r51`）。r50 只在动作层拦截下单，价格与库存仍取有赞同步原值（`¥99999.00` / `库存充足`），本轮新增 `getProductPriceText()` 统一非卖品价格口径为“非卖品”，目录卡隐藏库存胶囊、详情页隐藏自提价与库存元信息，购物车与详情推荐位只承载可下单商品；`devtools:display-only-products` 新增价格渲染与推荐位断言并产出 `evidence-display-only-list-after.png`；15/15 页 + 8/8 未登录态、搜索 19 项、购买路径、电商流程、结算配送状态、电商状态与触控扫描（13 页 47 选择器）均 PASS。展示型判定仍是标题关键词保守口径，占位价格字段仅前端不展示（M-20260914-012）。

> r52 服务入口与地址可履约性：`T-MINIAPP-COMMERCE-UX-REDESIGN` 新增 `E-20260914-008`（商品详情服务入口图标与收货地址可履约性收口，run_id `20260914-miniapp-service-entry-and-address-guard-r52`）。商品详情底部“询 / 购”单汉字入口改为标准线性图标 + “客服 / 购物车”标签 + `aria-label`，运行态图标 19×19px、底栏间距 14.44px；地址口径新增最小可履约粒度：`utils/address.ts` + `address-book.ts` + `pages/address` 对历史行政区-only 地址给出可见提示且不删除不改写，后端 `service/customer/address_support.py` 同口径拒绝；详情悬浮导航去掉背景色过渡，滚动态 `rgb(255,255,255)`、回顶 `rgba(0,0,0,0)` 双向断言稳定通过。重启后本地后端实调：`北京市东城区` 返回 `400`、完整地址返回 `200`；`test:address` 2/2、地址定向 pytest 17/17、15/15 页 + 8/8 未登录态、购买路径、电商状态与触控扫描（13 页 47 选择器）均 PASS。历史不完整地址仅提示不自动改写，地址粒度仍为启发式口径；闪送真实联调保持外部阻塞。

> r53 预约时间控件与登录引导文案：`T-MINIAPP-COMMERCE-UX-REDESIGN` 新增 `E-20260914-009`（预约时间控件可识别性与登录引导文案收口，run_id `20260914-miniapp-time-picker-affordance-and-login-copy-r53`）。逐页目视评审 15 页截图后发现并修复三处：结算/群内登记的日期与时分 picker 与只读“期望时间”预览长成同一个方框，现加 `time-picker__chevron` 下拉指示、预览改为无底色次要文字；订单/订单详情/地址/优惠券/积分登录空态副文案只是在重复标题，现改为补充登录后可获得的信息；结算金额面板零抵扣显示“-¥0.00”，现统一走 `formatDeductionFen()` 输出“-”。`check:miniapp` 新增三组静态守卫，两个 DevTools 脚本新增运行态断言；`devtools:verify-all-pages` 15/15 页 + 8/8 未登录态 PASS（期间复现并修复地址副文案 23 字换行）、`devtools:checkout-delivery-states`（3 个下拉指示 6×6、预览背景透明、零抵扣为“-”）、`devtools:registration-policy`、`devtools:verify-commerce-flows`、`devtools:commerce-states`、`devtools:product-purchase-path` 与触控扫描（13 页 47 选择器）均 PASS；新增 ERRORS M-20260914-017～M-20260914-020。

> r54 会员中心图标与支付口径：`T-MINIAPP-COMMERCE-UX-REDESIGN` 新增 `E-20260914-010`（会员中心入口图标线性化与支付方式顾客口径收口，run_id `20260914-miniapp-profile-icons-and-payment-copy-r54`）。会员中心“我的订单”与“特色服务”的 9 个单汉字占位图标改为 `iconKey` 驱动的内联线性图标并补 `aria-hidden`，订单详情把“MVP 模拟支付”改为 `formatPaymentMethodText()` 统一映射（微信支付/余额支付/组合支付/门店确认/待确认）；图标审计从“有元素”改为断言背景图可渲染、无文字占位、尺寸不小于 16px。`devtools:verify-all-pages` 15/15 页 + 8/8 未登录态（订单图标 4 个、服务图标 5 个）、`devtools:verify-commerce-flows`、`devtools:product-purchase-path`、`devtools:checkout-delivery-states`、`devtools:registration-policy`、`devtools:commerce-states`、`test:order-summary` 7/7 与触控扫描（13 页 47 选择器）均 PASS；新增 ERRORS M-20260914-022、M-20260914-023。

> r55 空态图标：`T-MINIAPP-COMMERCE-UX-REDESIGN` 新增 `E-20260914-011`（空态与身份徽标图标线性化，run_id `20260914-miniapp-empty-state-icons-r55`）。13 处空态/登录引导在 140rpx 白底方块里用单汉字或标点充当图标（址/购/结/券/详/单/订/分/充/芸/!），群内登记与个人中心身份徽标用“登/我”；现改为 app.wxss 中 13 个 key 驱动的内联线性图标并补 `aria-hidden`，`session-notice` 由 `iconText` 改为 `iconKey`（log-in/user-check）。`checkEmptyStateIcons()` 与全页审计双重拦截（背景图非空 + 尺寸下限 + 无文字）。`devtools:verify-all-pages` 15/15 页 + 8/8 未登录态 PASS（登录引导图标 72×72px、徽标 31×31px），其余 DevTools 套件与触控扫描全部 PASS；新增 ERRORS M-20260914-024。

## 状态记录（v47，2026-09-14，MiniApp 空态与身份徽标图标线性化）

- 本轮 run_id：`20260914-miniapp-empty-state-icons-r55`，绑定任务 `T-MINIAPP-COMMERCE-UX-REDESIGN`，证据 `E-20260914-011`。
- 问题来源：逐页目视评审截图时发现空态/登录引导的白底方块里只有“址/购/结/券/详/单/订/分/充/芸/!”等单个汉字或标点，群内登记与个人中心的身份徽标分别显示“登/我”，与未替换的占位稿无法区分（M-20260914-024）。这是 M-20260914-015（商品详情入口）与 M-20260914-022（会员中心入口）同一类缺陷在共用空态与身份徽标上的残留。
- 修复口径：`app.wxss` 用 13 个 key 定义空态线性图标（map-pin/shopping-cart/shopping-bag/clipboard-check/ticket/receipt/file-question/package/loader/wifi-off/star/cake/wallet），并去掉 `font-size` 文字渲染；13 处页面 WXML 改为按 key 渲染并补 `aria-hidden`；`session-notice` 组件 `iconText` → `iconKey`（log-in/user-check），个人中心与群内登记调用方同步。
- 门禁：`check-miniapp.mjs` 新增 `checkEmptyStateIcons()`（空态图标不得有文字内容、必须声明 key 修饰类、必须标 `aria-hidden`、key 必须在 app.wxss 有背景图规则、页面不得再向会话提示传 `icon-text`）；`verify-all-15-pages-devtools.cjs` 的登录引导断言由“图标文字非空”改为“背景图非空 + 渲染尺寸 ≥32px + 无文字”，并新增身份徽标断言。
- 本轮验证：`typecheck`、`check:miniapp`（15 页/15 路由）、`devtools:verify-all-pages`（15/15 页 + 8/8 未登录态；登录引导图标 72×72px、`iconBackground=set`、`iconText` 为空；群内登记徽标 31×31px、无文字）、`devtools:commerce-states`、`devtools:checkout-delivery-states`、`devtools:registration-policy`、`devtools:verify-commerce-flows`、`devtools:product-purchase-path`、触控扫描（13 页 47 选择器）均 PASS；后端保持 `127.0.0.1:7001` 健康（PID 8948），未重启。
- 环境记录：触控扫描首轮因 automator 超时中止且未写报告，按环境阻塞处理，重试后 PASS；未将其伪报为一次通过。
- 未验证边界保持：新增空态 icon key 必须同步补 app.wxss 规则；仅本地后端与 DevTools 模拟器验收，真机、真实微信支付/退款、真实闪送与生产验收均未执行；闪送开放平台资料与测试权限、有赞分类-商品接口 IP 白名单仍为外部阻塞。

## 状态记录（v46，2026-09-14，MiniApp 会员中心入口图标线性化与支付方式顾客口径收口）

- 本轮 run_id：`20260914-miniapp-profile-icons-and-payment-copy-r54`，绑定任务 `T-MINIAPP-COMMERCE-UX-REDESIGN`，证据 `E-20260914-010`。
- 问题来源：逐张目视复核会员中心截图时，“我的订单”四个入口用“付/制/送/售”单汉字放在空白方块里（M-20260914-022），与已收口的商品详情同类问题重范；订单详情在 mock 支付订单上直接把“MVP 模拟支付”展示给顾客（M-20260914-021）。
- 修复口径：`pages/profile/index.ts` 把 `iconText` 改为 `iconKey`（wallet/clock/truck/rotate-ccw、phone/message-circle/shield-check/file-text/lock），`index.wxml` 按 `iconKey` 渲染装饰图标节点并补 `aria-hidden`，`index.wxss` 为 9 个 key 定义内联线性图标（订单 40rpx、服务 24rpx 圆底 + 30rpx 字形）；`utils/order-summary.ts` 新增 `formatPaymentMethodText()`，订单详情统一走该映射。
- 门禁：`check-miniapp.mjs` 新增 `checkProfileShortcutIcons()`（禁止 `iconText` 占位、要求 9 个 key 样式与 `aria-hidden`）与支付方式文案禁用词；`verify-all-15-pages-devtools.cjs#inspectProfileShortcuts()` 改为断言背景图非空、图标内无文字、渲染尺寸不小于 16px；`verify-miniapp-commerce-flows.cjs` 与 `scan-miniapp-button-touch-targets.mjs` 夹具同步为 `iconKey`。
- 本轮验证：本地后端 `127.0.0.1:7001` 健康（PID 8948，`0.133.0-p2trial.3`，未重启）；`typecheck`、`check:miniapp`（15 页/15 路由）、`test:order-summary` 7/7、`devtools:verify-all-pages` 15/15 页 + 8/8 未登录态、`devtools:verify-commerce-flows`、`devtools:product-purchase-path`、`devtools:checkout-delivery-states`、`devtools:registration-policy`、`devtools:commerce-states`、触控扫描（13 页 47 选择器）均 PASS；运行态图标实测 20×20px（订单）与 24×24px（服务）。
- 过程记录：首轮全页审计以“图标缺少可渲染背景图标”FAIL，根因是新增 WXSS 里的 data URI 前缀被写成了工具输出里的脱敏占位符（M-20260914-023），修正 9 处后复跑通过；该失败未被隐去，保留了修复前后两份报告。
- 未验证边界保持：图标为内联 data URI，新增 `iconKey` 必须同步补 WXSS 修饰类；仅本地后端与 DevTools 模拟器验收，真机、真实微信支付/退款、真实闪送与生产验收均未执行；闪送开放平台资料与测试权限、有赞分类-商品接口 IP 白名单仍为外部阻塞。

## 状态记录（v45，2026-09-14，MiniApp 预约时间控件可识别性与登录引导文案收口）

- 本轮 run_id：`20260914-miniapp-time-picker-affordance-and-login-copy-r53`，绑定任务 `T-MINIAPP-COMMERCE-UX-REDESIGN`，证据 `E-20260914-009`。
- 问题来源：逐页目视评审当前运行态截图时发现——（1）结算页与群内登记页的“日期/小时/分钟”picker 与只读的“期望时间”预览外观完全一致，顾客无法判断哪里可以点（M-20260914-017）；（2）订单、订单详情、地址、优惠券、积分的登录引导副文案只是在重复标题（M-20260914-018）；（3）结算金额面板未使用优惠券与余额时显示“-¥0.00”，与相邻积分行的“-”不一致（M-20260914-019）。
- 修复口径：picker face 增加可见下拉指示并保留输入框外观，超长文案用 `time-picker__value` 省略；只读预览去掉边框与底色；登录引导副文案改为说明登录后可获得的订单进度、金额明细、地址复用、券面信息与积分记录；新增 `utils/money.ts#formatDeductionFen()` 把零抵扣统一成“-”。
- 门禁：`check-miniapp.mjs` 新增 `checkTimePickerAffordance()`、`checkDeductionPlaceholder()`、`checkLoginStateHintCopy()`；`verify-devtools-checkout-delivery-states.cjs` 新增三个下拉指示尺寸与预览背景断言、`checkout_deduction_placeholder` 数据断言；`verify-devtools-registration-policy.cjs` 新增 `registration_picker_affordance`；新增 `npm run test:money`。
- 本轮验证：`typecheck`、`check:miniapp`（15 页/15 路由）、`test:money` 3/3、`test:address` 2/2、`test:bakery` 9/9、`test:checkout-time` 5/5、`test:order-summary` 6/6、`devtools:checkout-delivery-states`、`devtools:registration-policy`、`devtools:verify-all-pages`（15/15 页 + 8/8 未登录态）、`devtools:verify-commerce-flows`、`devtools:commerce-states`、`devtools:product-purchase-path`、`scan:button-touch-targets`（13 页 47 选择器）全部 PASS。
- 未验证边界保持：登录引导副文案受空态单行宽度约束，后续加长会触发全页审计失败；历史行政区-only 地址仍只提示不自动改写；仅本地后端与 DevTools 模拟器验收，真机、真实微信支付/退款、真实闪送与生产验收均未执行；闪送开放平台资料与测试权限、有赞分类-商品接口 IP 白名单仍为外部阻塞。

## 状态记录（v44，2026-09-14，MiniApp 服务入口图标与地址可履约性收口）

- 本轮 run_id：`20260914-miniapp-service-entry-and-address-guard-r52`，绑定任务 `T-MINIAPP-COMMERCE-UX-REDESIGN`，证据 `E-20260914-008`。
- 问题来源：逐图目视复核发现商品详情底部服务入口用单汉字“询 / 购”充当图标，像未替换的占位稿且与购买动作挤在一排（M-20260914-015）；同时地址簿里存在只有“北京市东城区”“北京市朝阳区”的记录，前后端都只校验非空，这类地址无法支撑闪送派单（M-20260914-016）。
- 修复口径：底部服务入口改用与全局 TabBar 一致的标准线性聊天/购物车图标，保留“客服 / 购物车”标签并补 `aria-label`；新增 `utils/address.ts` 定义最小可履约粒度，`utils/address-book.ts` 保存前拦截，地址页对历史不完整地址标记 `needsDetailHint` 并提示“地址信息不完整，请编辑补充小区、楼栋或门牌号”（不删除、不改写旧数据），后端 `service/customer/address_support.py` 用同一口径拒绝；商品详情悬浮导航改为只过渡阴影，背景色在滚动状态间确定性切换。
- 门禁：`check-miniapp.mjs` 新增禁止“询 / 购”单汉字回归的静态断言与悬浮栏背景色不得参与 transition 的守卫；`verify-devtools-product-purchase-path.cjs` 新增 2 个无文字图标、背景图非空、尺寸不小于 18px 的运行态断言；新增 `miniapp/tests/utils/address.test.ts` 与 npm `test:address`，后端新增行政区-only 地址拒绝用例。
- 本轮验证：重启本地后端（`127.0.0.1:7001`，PID 8948，version `0.133.0-p2trial.3`）后实调 `POST /api/v1/miniapp/addresses`：`北京市东城区` 返回 `400`、完整地址返回 `200`，测试地址与临时 token 均已清理；`npm run typecheck`、`check:miniapp`（15 页 / 15 路由）、`test:bakery` 9/9、`test:address` 2/2、地址相关定向 pytest 17/17、`devtools:product-purchase-path`、`devtools:verify-all-pages`（15/15 页 + 8/8 未登录态）、`devtools:commerce-states`、`scan:button-touch-targets`（13 页 47 选择器）全部 PASS。
- 未验证边界保持：历史行政区-only 地址仍保留原记录（仅提示、需主动补全），地址粒度判断是启发式口径，未接入微信地址解析或地图校验；仅本地后端与 DevTools 模拟器验收，真机、真实微信支付/退款、真实闪送与生产验收均未执行；闪送开放平台资料与测试权限、有赞分类-商品接口 IP 白名单仍为外部阻塞。

## 状态记录（v43，2026-09-14，MiniApp 非卖品价格与库存口径修复）

- 本轮 run_id：`20260914-miniapp-display-only-price-truthfulness-r51`，绑定任务 `T-MINIAPP-COMMERCE-UX-REDESIGN`，证据 `E-20260914-007`。
- 问题来源：逐张目视复核 r50 截图发现 5 款展示型商品仍显示有赞同步占位价（¥99999.00 / ¥1600.00 / ¥1140.00）与“库存充足”，详情页标题区同显“门店自提价 ¥99999.00”；r50 只在动作层拦住下单，价格与库存字段仍是同步原值（M-20260914-012）。
- 修复口径：`utils/bakery.ts` 新增 `getProductPriceText()`，非卖品统一输出“非卖品”；首页、商品目录、购物车推荐与详情搭配推荐全部改走该口径；目录非卖品隐藏库存胶囊；详情页 `.detail-meta` 改由 `!isDisplayOnly` 条件渲染；购物车推荐（12 取 4）与详情搭配推荐（8 取 4）过滤 `isPurchasable=false` 商品并回填候选。
- 门禁：`check-miniapp.mjs` 展示型商品守卫新增价格函数、三页价格样式类、库存胶囊、详情元信息与推荐位过滤断言；`devtools:display-only-products` 新增目录卡价格渲染断言（“非卖品”与 ¥/“库存充足”互斥）、详情标题区断言与搭配推荐断言，并新增 `evidence-display-only-list-after.png`；`devtools:product-search` 空态文案改为轮询到非空值再断言（M-20260914-013）。
- 本轮验证：后端 `127.0.0.1:7001` 健康（PID 21892）；`typecheck`、`test:bakery` 9/9、`check:miniapp`（15 页 15 路由）、`devtools:display-only-products` PASS（4 张卡特卖品 `priceText=非卖品`、`renderedWithFakePrice=[]`、`hasDetailMeta=false`）；运行态 `devtools:verify-all-pages`（15/15 + 8/8 未登录态）、`devtools:product-search`、`devtools:product-purchase-path`、`devtools:verify-commerce-flows`、`devtools:checkout-delivery-states`、`devtools:commerce-states`、`scan:button-touch-targets`（13 页 47 选择器）全部 PASS；两张新截图目视确认无占位价与“库存充足”。
- 治理修复：`backend/scripts/append_logbook.py` 在 monorepo 下会把条目写进旧镜像 `backend/LOGBOOK.md`，已改为写仓库根 `LOGBOOK.md`，并用 `git diff | git apply -R` 精确回退误写内容（M-20260914-014）。
- 未验证边界保持：展示型判定仍是标题关键词保守口径（M-20260913-137），有赞正式分组待确认；占位价格字段仍留在同步数据中，仅前端不展示；真机、真实微信支付/退款、真实闪送与生产验收未执行；闪送开放平台资料与测试权限、有赞分类-商品接口 IP 白名单仍为外部阻塞。
