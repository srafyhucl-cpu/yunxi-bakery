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
