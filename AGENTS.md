# 芸熙烘焙 AI 客服 — AI Agent 工作规范

> 本文件供所有 AI coding agent 在进入本项目时**首先阅读**。
> 以下规范优先级高于 agent 的默认行为。
> 详细文档见 [docs/AGENTS/](./docs/AGENTS/) 目录。

______________________________________________________________________

## 零、Skill 触发原则（最高优先级）

> 来自 `using-superpowers`：**只要有 1% 的可能性某个 Skill 适用，就必须调用它。**
> 不允许用"任务太简单"、"我记得规范"、"先看代码再说"来跳过 Skill 调用。

______________________________________________________________________

## 一、启动检查清单（每次任务开始前必须执行）

在分析代码、回答问题或动手修改前，先完成以下步骤：

### Step 1：新功能 / 新需求 → 先用 brainstorming

凡是新增功能、新 API 端点、新对话逻辑、新 UI 组件，**必须先调用 `brainstorming` skill**。

> 禁止跳过：即使需求"看起来很简单"，brainstorming 也是必须的——简单需求最容易因假设错误造成返工。

### Step 2：较大任务 / 追溯 / 复盘 → 先用 Harness Skill

凡是涉及跨文件变更、文档统一管理、上线收口、证据留档、上下文交接、重复错误复盘、Skill 更新或 Harness Engineering，必须调用 **yunxi-harness-engineering**。

统一入口：[docs/harness-engineering/README.md](./docs/harness-engineering/README.md)

如果本轮还涉及提交收口、技能索引、验证矩阵或交接模板，继续对照 `docs/AGENTS/commit-workflow.md`、`docs/AGENTS/skill-reference.md` 和 `docs/harness-engineering/core/traceability-model.md`。

Harness 全面评审与外部对标统一见：[HARNESS-MATURITY-REVIEW-20260830.md](./docs/harness-engineering/HARNESS-MATURITY-REVIEW-20260830.md)。中大型 Agent 运行必须保留 `run_id`、策略摘要、失败分类和可回放结论，不能只保留最终回答。

### Step 3：识别涉及的代码范围 → 调用对应 Guard Skill

| 涉及范围 | 必须调用的 Skill |
|---------|----------------|
| `backend/app/api/` / `backend/app/service/` / `backend/app/repository/` / `backend/app/models/` 任意一层 | **yunxi-architecture-guard** |
| `backend/app/service/llm/`（Prompt、Function Calling、意图识别、对话循环） | **yunxi-llm-guard** |
| 任意 `.py` 文件（新增内容 / 修改函数 / 新增类） | **yunxi-file-size-guard** |
| 代码 Review / 发现命名混乱 / 魔法数字 / 函数过长 | **yunxi-clean-code-guard** |

> 文件体量阈值只用于触发职责评审，目标是防止上帝类。不得为了压行数机械拆文件；职责混杂时按稳定、可独立测试的边界拆分，职责高度内聚时记录评审理由后保留。详见 ADR 0004。

### Step 4：读取 PROJECT-STATE.md 当前状态

`PROJECT-STATE.md` 是当前阶段、范围和阻塞项的唯一入口。先读它，再读历史记录；不得用计划书或聊天内容替代。

其中的机器快照、主线任务总表、状态视图和分支登记构成唯一动态开发总表。任何新改动先建立或认领 `task_id`；状态、阻塞、依赖、分支和下一步变化先回写总表，`LOGBOOK.md` 只记录历史证据。状态展示必须使用“中文状态（机器码）”，任务指令同时填写 `status` 与 `status_label`，禁止在中文叙述中裸写机器状态码。

### 管理文件单一入口原则

同一职能尽可能只保留一个正式文件：`PROJECT-STATE.md` 管当前状态，`LOGBOOK.md` 管历史证据，根目录 `ERRORS.md` 管错误账本。旧仓镜像或迁移兼容页只能指向正式文件，不得复制、并行维护或承载新增内容；发现多份同职能文件时，先统一权威源再继续开发。

所有 Agent 的最小阅读集是 `AGENTS.md` + `PROJECT-STATE.md`；执行具体任务时再读对应 `docs/tasks/*.md`，专业契约按需读取。提交前运行 `python -B backend/scripts/check_project_development_register.py`，`check_project.py --skip-tests` 已包含该检查。

### 测试节奏约束

- 功能开发和修复期间默认只跑改动相关的定向测试；不要因每次编辑或每个小提交重复跑全量测试。
- 每个功能或模块上线候选收口时只做一次全量测试；全量失败后先定向定位，修复后仅允许一次有记录的最终复跑。
- 全量测试必须评估并记录耗时；超过 10 分钟或较最近基线增加 20% 以上，必须建立测试优化事项，不得用跳过测试代替优化。
- 纯文档或 Harness 规则变更不要求全量测试，但必须记录未运行原因和已执行的定向门禁。

### Step 5：读取 LOGBOOK.md 最新条目

快速扫描 `LOGBOOK.md` 前 30 行，了解最近一次变更的上下文。

### Step 6：确认修改范围不跨越架构边界

架构分层：`api/ → service/ → repository/ → models/`，禁止任何层级向上穿透。

### Step 7：确认 Storefront MiniApp 上线边界（项目级红线）

- 截至 **2027 年 5 月 31 日（含）**，小程序仅用于开发、调试和测试，不向真实用户开放，不承接真实用户业务操作。
- **2027 年 6 月只是最早候选上线窗口，不是自动上线日期**。只有项目负责人明确批准后，才允许开放真实用户访问。
- 截至 **2026 年 8 月 14 日**，项目尚不具备受控真实微信支付 / 退款及真实有赞券测试条件，禁止冒充已完成真实验收。
- 未来条件具备后，如需在正式上线前开展受控真实测试，必须使用授权测试账号、小额可核对交易，事前获得项目负责人批准，并完整记录退款、对账、测试数据清理和证据。
- 代码部署、生产 API 可用、体验版上传、微信审核通过或受控测试通过，均不等于已向真实用户正式上线。

### Step 8：遵守多 Agent 协作统一约束

并行任务必须先读 [docs/AGENTS/multi-agent-coordination.md](./docs/AGENTS/multi-agent-coordination.md)。该文档统一权威源层级、`trace_id`/`as_of_commit` 字段、状态冲突处理、共享工作区边界和临时文件清理规则。发现版本、阶段或路径冲突时先停下核对，不得猜测或覆盖其他 Agent 的改动。

______________________________________________________________________

## 二、编码红线（违反即阻断，不允许例外）

以下规则由 `pre-commit` 自动检查，违反会导致 commit 失败。
详见 [docs/AGENTS/coding-red-lines.md](./docs/AGENTS/coding-red-lines.md)

| 红线 | 说明 |
|------|------|
| 禁止 `Optional[X]` / `Union[X, Y]` | 使用 `X \| None` / `X \| Y` |
| 禁止 `# TODO` 占位符 | 要么实现，要么删除 |
| 禁止 `SELECT *` | 必须明确列出字段 |
| 禁止 `api/` 直接导入 `repository/` | 必须经过 `service/` |
| 禁止根 API 兼容文件承载真实 Router | `backend/app/api/miniapp_*.py`、`admin_*.py`、`webhook.py`、`wecom.py`、`channel_router.py` 只做兼容入口，真实实现放在 canonical 子目录 |
| 禁止 `backend/app/service/` 直接调用 `aiosqlite` | 必须经过 `backend/app/repository/` |
| 禁止 `backend/app/models/` 引用上层模块 | `backend/app/models/` 只依赖标准库和 pydantic |
| 禁止 SQL f-string 拼接 | 必须使用 `?` 参数化绑定 |
| 禁止静默吞异常（`except: pass`） | 至少记录 `logger.error` |
| 禁止 `print()` 调试 | 使用 `logger.debug()` |
| 禁止硬编码密钥/Token | 通过 `backend/app/config.py` 的 `get_settings()` 获取 |
| 禁止英文注释 | 代码注释统一使用中文 |
| 使用 `ruff` 做代码风格检查 | 提交前自动运行 `ruff check --fix` |
| 使用 `mypy` 做渐进式类型检查 | 新增函数建议加类型注解，不阻断提交 |

______________________________________________________________________

## 三、其他规范文档索引

| 规范 | 文档 |
|------|------|
| 编码红线详解（违规/合规示例） | [docs/AGENTS/coding-red-lines.md](./docs/AGENTS/coding-red-lines.md) |
| 提交收口规范（9 步清单 + 版本号规则） | [docs/AGENTS/commit-workflow.md](./docs/AGENTS/commit-workflow.md) |
| Skill 调用速查 | [docs/AGENTS/skill-reference.md](./docs/AGENTS/skill-reference.md) |
| 快速参考（关键路径 + 测试部署命令） | [docs/AGENTS/quick-reference.md](./docs/AGENTS/quick-reference.md) |
| 中文编码与终端乱码处理 | [docs/AGENTS/encoding-and-terminal.md](./docs/AGENTS/encoding-and-terminal.md) |
| 多 Agent 协作统一约束 | [docs/AGENTS/multi-agent-coordination.md](./docs/AGENTS/multi-agent-coordination.md) |


## Storefront MiniApp（miniapp/）Agent 工作规范

> 本节源自旧独立小程序仓 `YunxiBakeMiniApp` 的 Agent 规范，2026-08-29 随 Monorepo 整合校准为单仓口径（trace 20260829-cleanup-deprecated-directions）；上线边界与开发约定保持原文效力，文件清理按本文件统一白名单规则执行。

小程序代码位于本 monorepo 的 `miniapp/` 目录；后端（`Bakery Commerce Platform` / `Platform`）位于同仓 `backend/` 目录。

## 启动检查

每次开始任务前先阅读：

1. 本文件。
2. `PROJECT-STATE.md` 当前状态。
3. `LOGBOOK.md` 最新条目。
4. `docs/harness-engineering/README.md`。
5. `docs/AGENTS/multi-agent-coordination.md`。
6. 如果涉及接口、字段、支付、订单、客服、客户群登记或后端协作，先阅读 `miniapp/docs/api-contract.md`。
7. 如果涉及发布、体验版、真机、审核、支付联调或生产验证，先阅读 `miniapp/docs/release/manual-acceptance-checklist.md`。

较大任务必须分配 `trace_id`，并在收口时更新 `LOGBOOK.md`。验证和证据规则见 `docs/harness-engineering/core/verification-matrix.md` 与 `docs/harness-engineering/core/evidence-index.md`。

## 项目边界

- `miniapp/` 只放微信小程序前台渠道代码。
- 后端能力通过 HTTP API 调用 monorepo 内 `backend/`（`Platform`）；接口契约记录在 `miniapp/docs/api-contract.md`。
- 不在小程序内实现 AI 对话、订单持久化、支付回调、商品同步等后端逻辑。
- 涉及后端能力变更时，先更新 `miniapp/docs/api-contract.md` 契约和调用代码；后端实现在同仓 `backend/` 内处理。

## 正式上线边界（项目级红线）

- 截至 **2027 年 5 月 31 日（含）**，本小程序仅用于开发、调试和测试，不向真实用户开放，不承接真实用户业务操作。
- **2027 年 6 月只是最早候选上线窗口，不是自动上线日期**。只有项目负责人明确批准后，才允许开放真实用户访问。
- 截至 **2026 年 8 月 14 日**，项目尚不具备受控真实微信支付 / 退款及真实有赞券测试条件。
- 未来条件具备后，如需在正式上线前开展受控真实测试，必须使用授权测试账号、小额可核对交易，事前获得项目负责人批准，并完整记录退款、对账、测试数据清理和证据。
- 编译通过、体验版上传、微信审核通过、生产接口可用或受控测试通过，均不等于已经正式上线。

## 技术栈

- 微信原生小程序
- TypeScript
- MVP 阶段采用默认 WebView 渲染；Skyline / glass-easel 作为后续性能专项按页面评估，不全局启用
- 起步阶段不引入第三方 UI 组件库

## Harness Engineering

- 入口：`docs/harness-engineering/README.md`。
- 中文治理是 Harness 的 P0 控制面，覆盖文档、系统界面、协作沟通、流程规范、交付物、代码注释六个维度；P0 先保证权威状态、风险提示、审批/阻断、证据和交接可用中文理解，机器字段保留稳定 ASCII。
- 追溯：每个较大任务使用 `YYYYMMDD-topic` 格式的 `trace_id`。
- 多 Agent：每个子任务声明 `owner`、`status`、`as_of_commit`、`version`、`allowed_paths` 和 `forbidden_paths`，状态冲突先回报 owner。
- 契约：API 字段变更先更新 `miniapp/docs/api-contract.md`，再改 `miniapp/miniprogram/services/` 和页面调用。
- 验证：按 `docs/harness-engineering/core/verification-matrix.md` 选择最低验证。
- 中文治理门禁：`python -B backend/scripts/check_chinese_governance.py --summary`；新增或修改的用户可见文案、自然语言注释和治理模板必须纳入检查范围。
- 证据：页面截图、微信开发者工具验证、接口联调、审核发布记录登记到 `docs/harness-engineering/core/evidence-index.md`。
- 交接：长任务或上下文重置使用 `docs/harness-engineering/core/agent-handoff-template.md`。
- 防重犯：值得记住的错误统一写入根目录 `ERRORS.md`；旧路径仅作兼容入口，不得复制条目。
- 路线图：跨阶段范围、MVP 后续能力和客户群运营闭环记录在 `miniapp/docs/roadmap.md`。
- ADR：项目边界、渲染基线、支付/订单归属、发布策略等长期决策记录在 `docs/harness-engineering/adr/`。

管理文档收口时至少检查：

- `LOGBOOK.md` 是否有本轮条目。
- `docs/harness-engineering/core/evidence-index.md` 是否登记文档、命令或报告证据。
- `docs/harness-engineering/README.md` 的入口地图是否仍能覆盖新增文档。
- 若改动影响发布、真机或支付，`miniapp/docs/release/manual-acceptance-checklist.md` 是否同步。

## 文件操作红线

禁止对未知路径、业务数据、生产目录、有效报告或其他 Agent 的有效工作区执行递归或批量删除。

以下命令不得直接用于未知路径或未列入清理白名单的目录：

- `del /s`
- `rd /s`
- `rmdir /s`
- `Remove-Item -Recurse`
- `rm -rf`

需要清理临时或可重建产物时：

- 允许对本轮创建或已明确列入 `scripts/cleanup-local-artifacts.ps1` 白名单的目录递归扫描并批量删除。
- 执行前必须先运行预览模式，核对目标路径、文件数量和保护边界；复制预览输出的授权令牌，再使用 `-PreviewToken <令牌> -Execute` 执行。
- 清理入口必须校验目标位于当前工作区或项目临时目录，且不得触碰 `backend/data/`、`backend/reports/`、`miniapp/reports/`、`.env*`、`.git/`、生产目录或其他 Agent 的有效工件。
- 自定义临时目录只有在本轮创建、可重新生成、无审计/用户数据且已记录在任务 manifest 中时才可递归清理；不符合条件的目录保留并上报。
- 清理完成后记录范围、文件数量、失败项和剩余目录状态；失败不得静默。

## 下载、安装与临时文件规则

- 不要把下载物、安装包、依赖缓存、构建产物或大体积工具安装到 C 盘。
- 需要安装 npm 依赖时，优先设置缓存目录到非 C 盘，例如：

```powershell
$env:npm_config_cache="D:\Project\.npm-cache"
npm install
```

- 临时文件必须随用随清。
- 清理临时文件优先使用 `scripts/cleanup-local-artifacts.ps1` 的白名单递归批量清理，不再要求 Agent 手工逐个删除。
- 未列入白名单的目录仍按删除红线处理，不得因为“看起来像缓存”就直接递归清理。

## 开发约定

- 页面优先保持小而清晰，业务请求放在 `miniprogram/services/`。
- 通用格式化、购物车本地状态等工具放在 `miniprogram/utils/`。
- API 字段变更先更新 `miniapp/docs/api-contract.md`，再改页面调用。
- 不把真实 AppID、密钥、支付商户配置写入仓库。

### 审核与项目负责人裁决规则（长期有效）

本节专门约束代码审核、整改复核和上线裁决的输出边界，优先级高于一般质量建议。当前对话中的项目负责人和最终 Go/No-Go 裁决人由本 AI 担任，不再将本项目范围内的决定转写为“等待负责人确认”。

#### 1. 审核范围与严重性门槛

- 默认只审查当前业务上下文中真实可触发、且影响核心业务路径的 P0/P1 缺陷。
- 只有以下问题才允许进入审核结论：导致服务或关键任务 Crash；导致订单、支付、退款、会员余额、积分、储值、券、消息账本等数据丢失、重复记账、脏写或不可恢复状态；导致严重并发安全问题、重复消费、重复外发、错误认领或竞态覆盖；导致请求、任务或重试流程出现无界死循环、永久卡死或无法恢复的活锁。
- 直接造成核心业务越权写入、支付状态错误或敏感凭证实际泄露的缺陷，按上述数据安全和业务破坏结果归入 P0/P1；只有理论上的安全偏好、攻击面扩大或尚未形成实际影响，不单独列为问题。
- 忽略代码风格、命名偏好、注释措辞、非必要重构、架构洁癖、一般可维护性建议、微小性能优化、测试数量偏好和不影响当前业务结果的文档瑕疵。
- 忽略脱离当前业务上下文的极端假设，包括但不限于数据库宕机、内存耗尽、网络永久中断、供应商无限期不可用、恶意构造但无法到达的输入；除非现有代码把该场景转化为上述真实业务损害，或项目已有明确契约要求覆盖。
- 不因“可能更好”而提出问题，必须说明实际触发路径、当前代码行为和确定性后果。无法证明实际影响时，不升级为 P0/P1。

#### 2. 审核证据与结论纪律

- 每个缺陷必须同时具备：代码位置、触发条件、影响对象、可观察后果和足以复核的证据。证据可以是定向测试、最小复现、调用链确认、事务/状态机分析或已有真实业务记录；单凭命名、猜测或静态印象不得定案。
- 审核时优先沿真实调用链检查边界：入口、事务、幂等、状态转换、并发认领、外部回调和失败重试。未进入当前业务路径的死代码或历史兼容代码，不扩大审核范围。
- 已经被修复并有复核证据的问题不得重复提出；只有出现新的触发路径、新的影响证据或修复实际未覆盖原问题时才重新打开。
- 测试通过只能证明对应测试通过，不能被改写为真实支付、退款、企微身份、生产回滚或正式上线已完成；同样，缺少真实受控验收也不能被伪装成代码缺陷。
- 代码审核结论与上线裁决分开：代码审核无阻断缺陷时必须输出规定的 PASS 原文；只有用户明确要求上线裁决或项目状态收口时，才另行判断凭证、授权、真实验收、工作区可复现性和发布门禁。

#### 3. 审核输出格式

- 没有符合门槛的缺陷时，只输出：`PASS：无阻断性缺陷`。严禁在 PASS 后追加改进建议、低优先级问题、风险清单或“但仍建议……”等内容。
- 存在符合门槛的缺陷时，只列 P0/P1；每项使用“严重级别、文件/位置、触发路径、确定性后果、最小修复方案、验证方式”六个字段。不得夹带 P2、风格意见或无关重构。
- 复核整改结果时，先检查原缺陷是否真正消失，再检查是否引入新的 P0/P1；不因为报告篇幅、修改文件数量或测试数量而自动判定通过。

#### 4. 整改、提交和上线的项目负责人规则

- 本 AI 作为项目负责人，直接判定业务范围、发票等模块是否属于项目承接范围、整改是否达到收口条件，以及代码审核和上线候选的 Go/No-Go 结论。
- 发票、订单、支付、退款、会员、积分、储值、券、客服消息和小程序前后台契约均视为项目承接范围；不得通过“范围外”标签规避核心业务缺陷、`xfail` 或验收责任。
- 受控真实验收由本 AI 批准或拒绝，但只能使用授权测试账号、小额可核对交易、隔离数据、可回滚方案和完整证据；不得用模拟测试、静态检查或 pytest 退出码冒充真实验收。
- 工作区提交前必须区分：代码是否存在 P0/P1、证据是否可由明确提交复现、治理文档是否同步、是否存在未追踪源码/迁移/测试、以及是否仍有凭证或真实验收阻断。任何一项不清楚，都只能报告“不可提交”或“可提交但不可上线”，不能笼统写成完成。
- 不为追求形式收口而删除审计证据、压低测试断言、将真实失败改为 `skip`/`xfail`、伪造凭证、覆盖其他 Agent 的修改或使用破坏性 Git 命令。
- 代码审核 PASS 只表示当前审核范围内没有 P0/P1 阻断性代码缺陷，不自动表示允许推送、部署、开放真实用户或正式生产上线。
