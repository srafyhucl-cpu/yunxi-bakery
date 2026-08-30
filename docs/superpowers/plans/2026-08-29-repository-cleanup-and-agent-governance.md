# 仓库清理与多 Agent 治理实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use inline execution with the project cleanup checklist. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 清理明确的本机临时产物，并让所有当前文档遵循同一套事实源、版本、路径和状态约束。

**Architecture:** 保留代码、业务数据和验证证据；仅删除可重生成缓存、依赖环境、本机记忆和已确认重复文件。文档治理采用根级权威源，子目录文档只引用而不复制当前事实。

**Tech Stack:** PowerShell 单文件清理、Markdown 文档、Git、现有 Python 质量门禁。

## Global Constraints

- 当前技术版本唯一来源为 `backend/VERSION`。
- 当前代码快照以 `git rev-parse HEAD` 为准。
- `PROJECT-STATE.md` 是唯一当前状态入口。
- 每次删除只能针对一个明确文件路径；不使用递归删除或批量删除目录。
- 不删除 `backend/data/`、有效报告、业务源码和活动任务文档。
- 本轮 trace 为 `20260829-cleanup-temp-and-agent-governance`。

---

### Task 1: 清理本机临时产物

**Files:**
- Delete: `.workbuddy/memory/MEMORY.md`
- Delete: `.workbuddy/memory/2026-08-29.md`
- Delete: `miniapp/reports/miniprogram-ci/miniprogram-ci-readiness-20260826-010232.json`
- Delete: files under `.ruff_cache/`, `miniapp/.ruff_cache/`, `backend/.mypy_cache/`, `backend/.pytest_cache/`, `backend/htmlcov/`, `backend/.venv/`, `miniapp/node_modules/` one explicit path at a time

- [x] 记录清理前文件数量、总大小和重复文件哈希。
- [x] 逐个删除上述明确文件路径，保留 `backend/reports/`、`miniapp/reports/` 其他证据。
- [x] 重新统计并确认 `backend/VERSION`、业务数据库和 canonical 报告未被删除。

### Task 2: 固化多 Agent 统一约束

**Files:**
- Modify: `.gitignore`
- Modify: `AGENTS.md`
- Modify: `docs/AGENTS/multi-agent-coordination.md`
- Modify: `docs/AGENTS/commit-workflow.md`
- Modify: `docs/AGENTS/quick-reference.md`

- [x] 将 `.workbuddy/` 纳入根忽略规则。
- [x] 将后端 Guard、版本和脚本路径全部写成 `backend/...`。
- [x] 在根 Agent 规范中链接多 Agent 统一约束，并声明冲突停工核对顺序。
- [x] 统一提交前版本源、验证命令和 dirty/staged/untracked 交接字段。

### Task 3: 校准当前状态与活动入口

**Files:**
- Modify: `PROJECT-STATE.md`
- Modify: `README.md`
- Modify: `docs/README.md`
- Modify: `docs/AGENT-HANDOFF-20260829.md`
- Modify: `docs/待办优先级清单_20260829.md`
- Modify: `docs/交接文档评估与项目进度梳理_20260829.md`
- Modify: `docs/specs/2026-08-25-p2-manual.md`
- Modify: `docs/tasks/20260829-P0-1-指令.md`
- Modify: `docs/tasks/20260829-P1-6-模拟器BCDE走查-指令.md`

- [x] 把当前版本统一为 `0.133.0-p2trial.3`，当前提交统一为 `77f9346`。
- [x] 把 P1 统一为“承接验证完成，阶段关闭待项目负责人确认”。
- [x] 把当前焦点改为 P2 真人执行段等待负责人确认。
- [x] 把发票状态改为代码已落地、专用测试和端到端验收待完成。
- [x] 为 P2 手册和 P0-1 指令标注历史基线属性。
- [x] 将体验版上传拆成 3a 竞态已解决、3b 测试号/AppID 仍阻塞。
- [x] 为根计划书增加历史底稿横幅，不改写历史正文。

### Task 4: 验证与追溯

**Files:**
- Modify: `LOGBOOK.md`

- [x] 运行 `git status --short --branch` 并记录现有 dirty/staged/untracked 事实。
- [x] 使用 `Select-String` 扫描根活动文档中的旧版本、双仓入口和缺失 `backend/` 前缀。
- [x] 运行 `python backend/scripts/check_project.py --skip-tests`。
- [x] 运行 `python backend/scripts/check_mistake_ledger.py`。
- [x] 记录清理数量、保留证据、验证命令和残余风险到 `LOGBOOK.md` 顶部。
