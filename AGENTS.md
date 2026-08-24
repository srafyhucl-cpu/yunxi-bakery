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

### Step 3：识别涉及的代码范围 → 调用对应 Guard Skill

| 涉及范围 | 必须调用的 Skill |
|---------|----------------|
| `app/api/` / `app/service/` / `app/repository/` / `app/models/` 任意一层 | **yunxi-architecture-guard** |
| `app/service/llm/`（Prompt、Function Calling、意图识别、对话循环） | **yunxi-llm-guard** |
| 任意 `.py` 文件（新增内容 / 修改函数 / 新增类） | **yunxi-file-size-guard** |
| 代码 Review / 发现命名混乱 / 魔法数字 / 函数过长 | **yunxi-clean-code-guard** |

> 文件体量阈值只用于触发职责评审，目标是防止上帝类。不得为了压行数机械拆文件；职责混杂时按稳定、可独立测试的边界拆分，职责高度内聚时记录评审理由后保留。详见 ADR 0004。

### Step 4：读取 LOGBOOK.md 最新条目

快速扫描 `LOGBOOK.md` 前 30 行，了解最近一次变更的上下文。

### Step 5：确认修改范围不跨越架构边界

架构分层：`api/ → service/ → repository/ → models/`，禁止任何层级向上穿透。

### Step 6：确认 Storefront MiniApp 上线边界（项目级红线）

- 截至 **2027 年 5 月 31 日（含）**，小程序仅用于开发、调试和测试，不向真实用户开放，不承接真实用户业务操作。
- **2027 年 6 月只是最早候选上线窗口，不是自动上线日期**。只有项目负责人明确批准后，才允许开放真实用户访问。
- 截至 **2026 年 8 月 14 日**，项目尚不具备受控真实微信支付 / 退款及真实有赞券测试条件，禁止冒充已完成真实验收。
- 未来条件具备后，如需在正式上线前开展受控真实测试，必须使用授权测试账号、小额可核对交易，事前获得项目负责人批准，并完整记录退款、对账、测试数据清理和证据。
- 代码部署、生产 API 可用、体验版上传、微信审核通过或受控测试通过，均不等于已向真实用户正式上线。

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
| 禁止根 API 兼容文件承载真实 Router | `app/api/miniapp_*.py`、`admin_*.py`、`webhook.py`、`wecom.py`、`channel_router.py` 只做兼容入口，真实实现放在 canonical 子目录 |
| 禁止 `service/` 直接调用 `aiosqlite` | 必须经过 `repository/` |
| 禁止 `models/` 引用上层模块 | `models/` 只依赖标准库和 pydantic |
| 禁止 SQL f-string 拼接 | 必须使用 `?` 参数化绑定 |
| 禁止静默吞异常（`except: pass`） | 至少记录 `logger.error` |
| 禁止 `print()` 调试 | 使用 `logger.debug()` |
| 禁止硬编码密钥/Token | 通过 `app/config.py` 的 `get_settings()` 获取 |
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


## 小程序开发规范
# YunxiBakeMiniApp Agent 工作规范

本项目是 `Bakery Commerce Platform` 的 `Storefront MiniApp` 渠道仓，独立于后端项目 `YunxiBakeBot`。

## 启动检查

每次开始任务前先阅读：

1. 本文件。
2. `LOGBOOK.md` 最新条目。
3. `docs/harness-engineering/README.md`。
4. 如果涉及接口、字段、支付、订单、客服、客户群登记或后端协作，先阅读 `docs/api-contract.md`。
5. 如果涉及发布、体验版、真机、审核、支付联调或生产验证，先阅读 `docs/release/manual-acceptance-checklist.md`。

较大任务必须分配 `trace_id`，并在收口时更新 `LOGBOOK.md`。验证和证据规则见 `docs/harness-engineering/core/verification-matrix.md` 与 `docs/harness-engineering/core/evidence-index.md`。

## 项目边界

- 当前仓库只放微信小程序前台渠道代码。
- 后端能力通过 HTTP API 调用 `YunxiBakeBot`，即 `Platform` 主仓；接口契约记录在 `docs/api-contract.md`。
- 不在本项目内实现 AI 对话、订单持久化、支付回调、商品同步等后端逻辑。
- 涉及后端能力变更时，只更新本项目契约和调用代码；后端实现应回到 `YunxiBakeBot` 项目处理。

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
- 追溯：每个较大任务使用 `YYYYMMDD-topic` 格式的 `trace_id`。
- 契约：API 字段变更先更新 `docs/api-contract.md`，再改 `miniprogram/services/` 和页面调用。
- 验证：按 `docs/harness-engineering/core/verification-matrix.md` 选择最低验证。
- 证据：页面截图、微信开发者工具验证、接口联调、审核发布记录登记到 `docs/harness-engineering/core/evidence-index.md`。
- 交接：长任务或上下文重置使用 `docs/harness-engineering/core/agent-handoff-template.md`。
- 防重犯：值得记住的错误写入 `docs/harness-engineering/core/mistake-ledger.md`。
- 路线图：跨阶段范围、MVP 后续能力和客户群运营闭环记录在 `docs/roadmap.md`。
- ADR：项目边界、渲染基线、支付/订单归属、发布策略等长期决策记录在 `docs/harness-engineering/adr/`。

管理文档收口时至少检查：

- `LOGBOOK.md` 是否有本轮条目。
- `docs/harness-engineering/core/evidence-index.md` 是否登记文档、命令或报告证据。
- `docs/harness-engineering/README.md` 的入口地图是否仍能覆盖新增文档。
- 若改动影响发布、真机或支付，`docs/release/manual-acceptance-checklist.md` 是否同步。

## 文件操作红线

禁止批量删除文件或目录。

不要使用：

- `del /s`
- `rd /s`
- `rmdir /s`
- `Remove-Item -Recurse`
- `rm -rf`

需要删除文件时，只能一次删除一个明确路径的文件。

## 下载、安装与临时文件规则

- 不要把下载物、安装包、依赖缓存、构建产物或大体积工具安装到 C 盘。
- 需要安装 npm 依赖时，优先设置缓存目录到非 C 盘，例如：

```powershell
$env:npm_config_cache="D:\Project\.npm-cache"
npm install
```

- 临时文件必须随用随清。
- 清理临时文件时仍只能一次删除一个明确路径的文件。

## 开发约定

- 页面优先保持小而清晰，业务请求放在 `miniprogram/services/`。
- 通用格式化、购物车本地状态等工具放在 `miniprogram/utils/`。
- API 字段变更先更新 `docs/api-contract.md`，再改页面调用。
- 不把真实 AppID、密钥、支付商户配置写入仓库。

