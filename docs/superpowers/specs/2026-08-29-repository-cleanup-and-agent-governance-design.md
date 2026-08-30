# 仓库清理与多 Agent 治理设计

- `trace_id`: `20260829-cleanup-temp-and-agent-governance`
- `updated_at`: 2026-08-29
- `owner`: 当前任务 owner（AI 执行，项目负责人保留破坏性处置授权）

## 目标

清理仓库中明确可重新生成的本机临时产物，保留业务数据、源码、有效审计证据和仍在使用的任务文档；同时建立单一事实源、统一路径和状态语义，避免并行 Agent 按过期快照继续工作。

## 权威事实源

1. `AGENTS.md`：操作红线、项目边界和协作流程。
2. `PROJECT-STATE.md`：当前阶段、阻塞项、范围和决策状态。
3. `backend/VERSION`：唯一技术版本源。
4. `git rev-parse HEAD`：当前代码快照。
5. `LOGBOOK.md`：历史变更和验证证据。
6. `docs/待办优先级清单_20260829.md`：活动队列，不重新定义项目阶段。
7. `docs/tasks/*.md`：任务执行说明，必须带状态和基线，不是状态源。

## 清理边界

删除以下明确的本机临时或重复产物，并按单文件路径执行：

- `.workbuddy/memory/` 中的两份本机 Agent 记忆。
- 根目录与 `miniapp/` 下的 Ruff 缓存。
- `backend/.mypy_cache/`、`backend/.pytest_cache/`、`backend/htmlcov/`。
- `backend/.venv/` 与 `miniapp/node_modules/`（可由锁定依赖重新生成）。
- 重复的 `miniapp/reports/miniprogram-ci/miniprogram-ci-readiness-20260826-010232.json`，保留 canonical `latest.json`。

保留以下内容：

- `backend/data/` 业务数据库和本地运行数据。
- `backend/reports/`、`miniapp/reports/` 中可追溯的验证证据。
- `docs/tasks/` 活动任务指令及其历史执行快照。
- `docs/archive/` 和根计划书历史材料。

## 文档统一

- 所有后端路径在根文档中显式使用 `backend/` 前缀。
- 当前版本和提交统一为 `backend/VERSION` 与 `git rev-parse --short HEAD` 的实时值。
- P1 统一表述为“承接验证完成，阶段关闭待项目负责人确认”。
- 体验版问题拆为“DevTools 空文件竞态已解决”和“测试号/AppID 条件仍阻塞”。
- 历史计划和准备快照保留原值，但必须加“不可作为当前执行依据”说明。
- `.workbuddy/` 纳入根 `.gitignore`，禁止被 Agent 当作项目权威输入。

## 验证

- 清理后确认目标临时路径不存在，canonical 报告仍存在。
- `backend/VERSION`、HEAD、PROJECT-STATE、待办、交接文档的当前值一致。
- 对根文档执行失效路径、旧版本、旧仓入口扫描。
- 运行 `python backend/scripts/check_project.py --skip-tests`；若存量证据索引检查仍失败，记录为既有风险，不扩大范围。

