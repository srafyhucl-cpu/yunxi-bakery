# Agent Handoff — 芸熙烘焙智能经营平台

- **trace_id**: `20260829-cleanup-temp-and-agent-governance`
- **parent_trace_id**: `20260829-cleanup-deprecated-directions`
- **updated_at**: 2026-08-30
- **owner**: 项目负责人（人工决策方）＋ AI 员工（执行方，OpenCode / CodeBuddy 等多会话接力）
- **current_goal**: 完成本机临时产物清理、活动文档口径统一、多 Agent 协作约束和历史证据索引收口
- **current_status**: 临时产物已清理；文档治理、开发总表守卫和证据索引来源收口已完成；P1 技术验收已完成、阶段关闭待项目负责人确认；项目整体处于 **P2 试运行准备完成、真人执行段尚未启动** 状态
- **snapshot_head**: 77f9346（工作区当前 HEAD，未表示本轮改动已推送）
- **snapshot_version**: 0.133.0-p2trial.3（来源：backend/VERSION）
- **workspace_state**: dirty；已有 staged renames、文档修改和未跟踪任务/治理文件；本交接不宣称已提交或已推送

> 使用规则（承接 `docs/harness-engineering/core/agent-handoff-template.md`）：未实际运行的验证一律写入「未验证」；非本轮改动的文件标注「不要覆盖」；生产/数据库写入必须写明 dry-run 与 apply 状态。当前无任何生产或数据库写入。

---

## 本次追加收口（trace: 20260829-cleanup-temp-and-agent-governance）

- **清理结果**：按单文件路径清理前阶段约 47,485 个可重新生成文件（约 1.27 GB）；追加清理 14,560 个文件、152,851,850 字节（管理端 `node_modules` 13,568 个、后端 `__pycache__` 984 个、Ruff 缓存 6 个、覆盖率文件 2 个）。目标包括本机 Agent 记忆、Python/Node 依赖环境、测试/覆盖率缓存和一份与 `latest.json` 重复的报告。
- **保留内容**：`backend/data/`、`backend/reports/`、`miniapp/reports/` 有效证据、`docs/tasks/` 活动/历史任务指令、`docs/archive/` 和历史计划材料。
- **治理变更**：新增 `docs/AGENTS/multi-agent-coordination.md`；任务指令统一补 `owner`、`status`、`as_of_commit`、`version`、`allowed_paths`、`forbidden_paths`；当前状态统一引用 `PROJECT-STATE.md`、`backend/VERSION` 和实时 HEAD；开发总表守卫新增任务分支、工作区状态和未知状态视图引用校验。
- **状态拆分**：体验版问题明确为 3a DevTools 瞬时竞态已解决、3b 测试号/AppID 条件仍阻塞；P1 技术完成与负责人确认关闭分开记录。
- **最终验证**：`check_project.py --skip-tests` EXIT=0；开发总表专项测试 9/9、专项守卫 EXIT=0；MiniApp 页面/API 合约 43/43；错误账本 EXIT=0（14 条）；编码检查 EXIT=0（108 文件）；`git diff --check` EXIT=0。临时缓存已逐文件清理并复核。
- **当前工作区**：仍为 dirty；本轮未提交、未推送、未写生产或数据库。

## 后续专项收口（trace: 20260830-evidence-index-origin-and-summary）

- **目标**：修正证据索引在 Monorepo 整合后的仓库来源、路径基准和摘要分类，保留历史证据的原始绑定，不伪造当前仓提交。
- **已完成**：默认入口统一为根目录 `docs/harness-engineering/core/evidence-index.md`；`repo:` 相对路径按 Monorepo 根解析；Git 工件按当前仓与冻结旧仓 `D:\Project\YunxiBakeBot` 依次核验；摘要新增 `current_repo_verified`、`legacy_repo_verified`、`external_unverified`、`malformed`、`missing_repo_file`、`hash_mismatch`；根索引与 `backend/docs` 镜像统计一致。
- **验证**：证据索引专项测试 30/30 通过；ruff check/format 通过；`check_evidence_index.py --summary` EXIT=0，361 条、20 条 retired、1,604 个旧仓 Git 工件可验证、0 个外部未验证、0 个缺失、0 个哈希不一致；JSON 报告位于 `backend/reports/harness/evidence-index-origin-summary-20260830.json`。
- **未完成**：历史条目尚未逐条新增 `repository_origin` 字段，当前来源由检查器推断；新证据写入规范已更新，后续新增条目应显式写 `repository_origin: monorepo`，旧仓历史条目如需人工审计再补 `legacy:YunxiBakeBot`。
- **工作区事实**：仍 dirty；未提交、未推送；没有生产或数据库写入。全量 pytest、MiniApp typecheck 和 pre-commit 全量执行未在本专项运行。

## 本轮运行时治理收口（trace: 20260830-harness-runtime-cleanup-and-closeout）

- **目标**：消除质量门禁把第三方缓存写入 C 盘的风险，并让本机临时文件清理入口兼容 Windows PowerShell 5.1。
- **已完成**：`backend/scripts/check_project.py` 固定 D 盘一次性 `TMP`/`TEMP`/`TMPDIR` 并设置 `PYTHONDONTWRITEBYTECODE=1`；`scripts/cleanup-local-artifacts.ps1` 使用 UTF-8 BOM、覆盖根目录/ backend / miniapp / scripts 可重建缓存，且只逐文件删除；新增专项回归测试。
- **验证**：专项 pytest、ruff check/format、`check_project.py --skip-tests`、开发总表、证据索引、错误账本、编码检查、Windows PowerShell 5.1 预览和 pwsh 预览均 EXIT=0；证据 `E-20260830-002` 与报告 `backend/reports/harness/harness-runtime-cleanup-20260830.json`。
- **状态**：`PROJECT-STATE.md` 已将 `T-HARNESS-RUNTIME-CLEANUP` 置为 `completed`；工作区仍 dirty，未提交、未推送；本轮未执行 `-Execute`、未写生产或客户数据。

---

## 一、项目背景与目标

- **项目定位**：自研烘焙电商 + AI 客服平台（替代有赞 SaaS），单店铺（芸熙烘焙）试用，未来可能多租户。
- **仓库**：`D:\Project\YunxiBakery`＝唯一活跃 Monorepo（2026-08-17 由旧后端仓 YunxiBakeBot 与旧小程序仓 YunxiBakeMiniApp 合并，GitHub: github.com/srafyhucl-cpu/yunxi-bakery）。
  - 旧仓 `D:\Project\YunxiBakeBot`：🔒 冻结，只读，永不删（最后提交 7afd44b 2026-08-16；D1 账务审阅轨道留在此仓）。
  - `D:\Project\YunxiBakeMiniApp`：过期小程序副本，停用（处置见待办⑪，不要删除，删除需负责人明确指示）。
- **时间线**：P0 Monorepo 整合 ✅（08-17）→ P0.5 资产迁移 ✅（08-24）→ P1 全模块承接验证技术完成（阶段关闭待负责人确认）→ **▶ P2 试运行准备完成**（真人执行段尚未启动）→ P3 上线准备。目标上线 **2027-06（最早候选窗口，不是自动上线日期）**。
- **项目级红线**：截至 2027-05-31（含），小程序仅用于开发、调试和测试，不向真实用户开放；P2 实测启动、真实微信支付/退款、真实有赞券测试、客户数据正式导入，均需项目负责人事前明确批准。编译通过、体验版上传、微信审核通过、受控测试通过均不等于正式上线。
- **开发方式**：Vibe Coding（AI 生成代码，开发者指导方向）；Harness Engineering 追溯体系（trace_id、LOGBOOK、证据索引、防重犯账本）。

## 二、系统架构

- **backend/**（Python 3.11+）：FastAPI + SQLite + LangChain/LangGraph（AI 应用层编排）+ Pydantic。分层 `api → service → repository → models`，禁止向上穿透。路由装配入口 `backend/app/lifespan_routes.py`；canonical 渠道目录 `backend/app/api/channels/storefront/`、`admin/`、`integrations/`；根层 `miniapp_*.py` 等仅为兼容入口。16 服务域，含会员/积分/储值/券（M1-M5 已建成）。
- **检索口径**：BM25 关键词检索已落地；**向量检索路径战略禁用**（PROJECT-STATE v20）。
- **miniapp/**（TypeScript）：微信原生小程序，15 页面 M1-M5；契约单一来源 `miniapp/docs/api-contract.md`；静态守卫 `npm run check:miniapp`（15 pages / 15 routes）；AI 消息超时 60000ms、其余默认 12000ms。
- **质量门禁**：`.pre-commit-config.yaml` 7 钩子（detect-secrets、verify-secrets-baseline、check-project、check-redline-selftest、ruff-format、mypy（非阻断）、core-tests）；sync-version / check-logbook / check-file-sizes / check-mistake-ledger / check-evidence-index / check-text-encoding 改为每周手动跑（backend/scripts/ 下）。
- **版本**：以 backend/VERSION 为准（当前 0.133.0-p2trial.3；快照 HEAD=77f9346；根/backend 两份《项目进度与配置清单.md》表头已同步）。

## 三、已完成（截至 2026-08-29）

- P0 Monorepo 整合（1379 文件、commit 1c2a3ea，原仓备份 `D:\Project\_archive_20260817`）；P0.5 资产迁移（凭证迁 `backend/.env` 实测连通；知识 24 条人工沉淀已迁；商品 309 在售已真实同步；**客户数据 2.4 万条不复制进新仓，走正式导入**）。
- P1 全模块承接验证 08-25 全过（**关闭待项目负责人确认**）；pytest 基线清零（2026-08-26，trace 20260826-test-baseline-zero）。
- P2 准备段完成：模拟器 A 项走查 + 4 缺陷修复（621753c / 12cc895 / ec1e9d5 / 23f0c4e）；AI 聊天超时守卫放宽（77f9346，trace 20260829-chat-timeout-override，含变异验证，**未做真机/DevTools 实测**）。
- 有赞对标：核心链路全满足，唯一真缺口＝发票；**负证据 4 项不承接**（评价 / 会员等级 / 营销 / 物流卡片）。
- **前轮（20260829-cleanup-deprecated-directions）**：废弃方向文档归档 15 篇（`git mv` 单路径，零删除）；`langchain-ai-layer-production-enhancement-plan.md` 加废弃横幅保留原位（被 backend/scripts 守卫脚本+测试引用）；重写根 README 与 docs/README 导航；AGENTS.md 小程序段从「独立于 YunxiBakeBot」双仓口径校准为 monorepo 口径；harness README 旧仓脚本路径改 `backend/scripts/` 前缀；修复 2 处活跃文档失效引用；新建 `docs/archive/README.md` 归档索引。
- **本轮（20260829-cleanup-temp-and-agent-governance）**：清理可重新生成的本机临时产物；统一 `PROJECT-STATE.md`、待办清单、历史评估说明、任务元数据和交接字段；新增 `docs/AGENTS/multi-agent-coordination.md` 与清理脚本；LOGBOOK 顶部追加本 trace。

## 四、未完成 / 当前进行

1. **P2 真人执行段启动**（P0 级，纯决策）：项目负责人确认 P1 关闭 + 批准启动 P2；执行手册 `docs/specs/2026-08-25-p2-manual.md`（模拟器 B/C/D/E 项走查在 `docs/tasks/20260829-P1-6-*.md`；P1-4 至 P1-6 是当前活动指令，P1-7 已被否决，仅保留历史记录）。
2. **体验版上传**：拆两问题——3a DevTools「project.config.json: Empty file」报错＝瞬时竞态（DevTools 自动重写配置与编译并发，commit ec1e9d5 相关），点「编译」Ctrl+B 重编译即消，磁盘文件本身合法；3b 测试号 wx4b59baadd9187a2e 硬阻塞，正式 AppID wxdd53813d16c27a6e 待商家确认后按「同壳换芯」切换（改 `backend/.env` 与 `miniapp/project.config.json` 两处）。
3. **P1 级待办**（详见 `docs/待办优先级清单_20260829.md`）：④ 知识缺口回填（先枚举，清单在 `backend/app/migrations/v004_agent_foundation_tables.sql:40` 附近）⑤ 发票承接（代码已在 e2639d4 落地，缺测试与端到端验收；backend/tests 无 invoice 测试）⑥ 模拟器 BCDE 走查；FAQ 回收已被否决，不再列入待办。
4. **P2 级待办**：⑧ featured_products 精选 6 款无 DB 迁移（上线前必须）⑨ 支付商户号跟进 ⑩ 有赞 IP 白名单 NAT 出口确认 ⑪ 过期副本处置 ⑫ 里程碑计划重新基线化（计划书 5.1 时间线被 v1.2/v1.3/v1.4 三次修正绕开未回写）⑬ 生产部署状态复核（最新证据 2026-08-10 v0.109.16）。
5. **P3 级**：商品搜索、FP-5 技术债、D1 冻结独立轨道（D1-A 不合入 master、D1-B 不放行，留旧仓）、Windows 4 项 skipif 测试、模拟器 timeout 根因。

## 五、遗留技术债与风险

- **D1 账务核心**：冻结独立轨道，D1-A 不得合入 master、D1-B 不得放行；R6 组合支付通知绕过统一服务与 P8 outbox fencing 为 D1-C 硬门槛。
- **真实支付**：商户号未下，`ALLOW_MOCK_PAYMENT`；到账人工确认口径。
- **客户数据**：2.4 万条永不复制进新仓，正式导入需负责人批准。
- **文档镜像**：`backend/docs/` 是旧仓文档树完整镜像（与根 docs/ 大量重复，停在整合时点）；处置需负责人指示，本轮未动。
- **本轮遗留**：`docs/tasks/` 5 份任务指令与 2 份 20260829 评估/待办文档仍未跟踪（是否入库待负责人决定）；本机 `.workbuddy/`、缓存、虚拟环境和 `node_modules/` 已清理；归档移动与治理文档仍未提交。证据索引专项已完成，但历史条目仍保留旧仓原始提交，不逐条重写。
- **证据索引当前状态**：`check_evidence_index.py --summary` EXIT=0（361 条、retired=20、failed=0）；1,604 个历史 Git 工件由冻结旧仓只读核验，新证据必须显式声明 `repository_origin: monorepo` 并绑定当前 Monorepo 有效提交。
- **防重犯账本**：本轮无新错误需要录入 mistake-ledger（文档漂移问题已于 2026-08-24 M-20260824-001 与待办⑫在案）；防线落点＝docs/README 重写 + 归档索引。

## 六、当前工作区（截至本 handoff 生成时）

- **modified_files（未提交）**：以 `git status --short` 为准，当前包含 `.gitignore`、`AGENTS.md`、`LOGBOOK.md`、`PROJECT-STATE.md`、`README.md`、`项目重构与推进计划书.md`、根/`backend/`/`miniapp/` 的相关 Skill 与 `docs/AGENTS/`、`docs/harness-engineering/`、`docs/specs/` 文档；本轮治理新增的任务/评估/待办文件见下方 untracked 清单。
- **staged renames（15 个 `git mv`，零内容删除）**：根 4 篇执行/评审文档 → `docs/archive/p0-monorepo-20260817/`；AI-EMPLOYEE-INSTRUCTIONS.md、MVP-DEVELOPMENT-GUIDE.md → `docs/archive/v1-scope-retracted/`；two-repo-rollout-plan、platform-miniapp-api-contract-v1、miniapp-phase1-execution-checklist、miniapp-ai-handoff-plan、AI对话页面原型设计说明 → `docs/archive/two-repo-era/`；langchain takeover/migration/next×2 → `docs/archive/langchain-legacy-plans/`。
- **untracked（提交决策留负责人）**：`docs/tasks/`（5 份指令：1 份历史 + 4 份活动）、`docs/交接文档评估与项目进度梳理_20260829.md`、`docs/待办优先级清单_20260829.md`；本轮新增 `docs/archive/README.md`、`docs/AGENT-HANDOFF-20260829.md`、`docs/AGENTS/multi-agent-coordination.md`、`scripts/cleanup-local-artifacts.ps1` 及治理计划/规格文件。
- **files_intentionally_untouched（不要覆盖）**：`backend/**` 全部业务代码、`docs/architecture/langchain-ai-layer-portfolio.md`（被脚本引用）、`backend/docs/`（镜像处置待决）、`backend/data/`、有效 `backend/reports/` 与 `miniapp/reports/` 证据；`PROJECT-STATE.md` 与 `LOGBOOK.md` 的历史内容未回写，本轮仅追加当前状态与 trace。

## 七、关键决策

1. **归档不删除**：遵守 AGENTS 文件操作红线（禁批量删除），全部用单路径 `git mv` 移入 `docs/archive/` 分组目录，历史可 `git log --follow` 追溯。
2. **被脚本引用的文档不移**：`langchain-ai-layer-production-enhancement-plan.md`（check 脚本+测试）、`langchain-ai-layer-portfolio.md`（作品集证据包脚本）保留原位，前者加废弃横幅（横幅措辞避开守卫脚本的禁用短语与占位词校验）。
3. **保留原位的历史文档**：`项目重构与推进计划书.md`（含附录D v1.2 撤回条款，是待办⑫重新基线化基础）；`github-reference-benchmark` / `global-risk-remediation` 两篇已执行计划（导航标注历史）。
4. **AGENTS.md 小程序段只改口径不动红线**：上线边界、文件操作红线、开发约定原文保留。
5. **`backend/docs/` 镜像与旧仓/过期副本处置**：只登记不动，删除需负责人明确指示。

## 八、已验证 / 未验证

- **已验证（本轮执行，真实退出码）**：
  - `git status`：15 个 rename 全部 staged，无意外删除。
  - `git grep` 全仓引用排查：被移动文件名在活跃文档中仅剩 2 处引用，均已同步改为归档路径或现行契约路径；其余命中均为历史记录（LOGBOOK、evidence-index、进度清单、ADR、backend/docs 镜像、superpowers 历史计划、monorepo-merge.ps1），无需回写。
  - `python backend/scripts/check_project.py --skip-tests`（红线门禁，结果见 LOGBOOK 本轮条目）。
  - `python backend/scripts/check_evidence_index.py --summary`、`python backend/scripts/check_mistake_ledger.py`（结构性检查，结果见 LOGBOOK 本轮条目）。
  - 临时路径逐项 `Test-Path` 复核：`.workbuddy/`、缓存、虚拟环境、`miniapp/node_modules/` 和重复报告均不存在；业务数据与有效报告路径保留。
- **未验证**：
  - 全量 pytest 回归（本轮纯文档/归档变更，未运行；下轮含代码变更时必须 exit=0）。
  - `pre-commit run --all-files`（未运行；建议提交前执行）。
  - 归档文档内容的逐篇校对（仅核对存在性与引用关系，未通读 2449 行长文）。
  - P2 手册 C1-C5 与模拟器 BCDE 现场执行（等真人执行段）。

## 九、联系人

| 角色 | 说明 |
|---|---|
| 项目负责人 | 唯一人工决策方：P2 启动 / P1 关闭确认 / 支付商户 / 真实数据导入 / 上线批准 / 破坏性处置（删除类）的唯一授权人。姓名未在仓内文档登记。 |
| AI 员工 | 执行方，多会话接力（OpenCode、CodeBuddy 等）；按 AGENTS.md + harness 规范工作，trace_id 收口。 |
| 店员 A/B/C | 真人使用侧（最多 3 名），P2 试运行阶段的实际操作者。 |
| 外部依赖 | 商家（AppID 切换、FAQ 回收、资质）、有赞开放平台（IP 白名单）、微信支付（商户号）。

## 十、下一步（建议顺序）

1. 负责人复核本轮归档与导航重写 → 确认后按 commit-workflow 提交（建议 docs/chore 类型提交；`docs/tasks/` 与两份 20260829 文档是否入库一并决定）；提交后补登 evidence-index `E-20260829-001`（校验器要求完整 40 位 commit_sha）。
2. 负责人确认 P1 关闭 + 批准 P2 真人执行段（拆解见 `docs/待办优先级清单_20260829.md` P0-②）。
3. 按 P2 手册执行模拟器 B/C/D/E 走查与体验版重编译验证（3a 竞态应随重编译消失，若复现按 LOGBOOK 20260829 排障结论升级）。
4. P1 级四项（知识缺口枚举 → 发票测试 → FAQ 回收推进）与 P2 级六项按清单依赖推进。
5. 里程碑重新基线化（待办⑫）时以 PROJECT-STATE v20 + 计划书附录D 为底稿。

## 十一、参考入口

- 状态与待办：`PROJECT-STATE.md` ｜ `docs/待办优先级清单_20260829.md` ｜ `docs/交接文档评估与项目进度梳理_20260829.md`
- 规范：`AGENTS.md` ｜ `docs/AGENTS/coding-red-lines.md` ｜ `docs/AGENTS/commit-workflow.md` ｜ `docs/AGENTS/quick-reference.md`
- Harness：`LOGBOOK.md`（唯一编年史）｜ `docs/harness-engineering/README.md` ｜ `core/verification-matrix.md` ｜ `core/evidence-index.md` ｜ `core/mistake-ledger.md`
- 契约与边界：`miniapp/docs/api-contract.md` ｜ `docs/architecture/project-boundaries.md` ｜ `docs/release/server-layout.md`
- 归档：`docs/archive/README.md`（归档原因、保留原位清单、待决事项）
