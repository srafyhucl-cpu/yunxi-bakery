# 项目完整开发总表与中文优先 Harness 改造实施计划

> **For agentic workers:** 本计划按任务逐项执行；每项完成后运行对应验证，并在 `PROJECT-STATE.md` 更新状态。

**目标：** 将 Harness 改造成中文优先、单一进度入口、可自动校验且支持多 Agent 交接的项目管理系统。

**架构：** `PROJECT-STATE.md` 作为唯一动态开发总表，包含当前快照、主线任务、状态视图和分支登记；`AGENTS.md` 与 Harness 文档只承载静态规则。新增只读 Python 守卫解析带标记的 Markdown 区块，校验状态、版本、提交、分支和任务指令元数据，并由现有 `check_project.py` 统一调用。

**技术栈：** Markdown、Python 3.11+、标准库 `re`/`subprocess`/`dataclasses`、现有 pytest、pre-commit、Git。

## 全局约束

- 进度事实只写入 `PROJECT-STATE.md`，不得新建第二个动态状态源。
- 人类可读内容优先使用中文；`task_id`、`status`、`owner`、`branch`、`as_of_commit`、`version` 等机器字段保持 ASCII。
- 状态码固定为 `completed`、`active`、`blocked`、`pending`、`deferred`、`historical`。
- 当前版本只能读取 `backend/VERSION`；当前分支和提交必须由 Git 实时确认。
- 删除、生产写入、真实支付、客户数据导入和正式上线不在本轮范围。
- 不修改业务代码；不覆盖其他 Agent 已有改动；不提交或推送。
- 每个任务结束都必须记录验证命令、退出码和未验证项。

---

### 任务 1：扩展项目状态总表

**文件：**
- 修改：`PROJECT-STATE.md`

**交付：**
- 增加机器快照区：`updated_at`、`as_of_commit`、`version`、`current_branch`、`workspace_state`、`state_owner`。
- 增加主线任务登记表，覆盖已完成、进行中、阻塞、待处理、暂缓和历史任务。
- 增加六类状态视图，视图只引用任务 ID。
- 增加本仓分支与外部历史轨道登记，明确只有真实存在的分支才可写入事实表。
- 在表头写明中文优先和最小阅读集。

**验证：** `Get-Content PROJECT-STATE.md -TotalCount 180`，确认机器区块、任务区块、视图区块和分支区块均存在。

### 任务 2：实现开发总表自动守卫

**文件：**
- 新增：`backend/scripts/check_project_development_register.py`
- 新增测试：`backend/tests/scripts/test_check_project_development_register.py`

**交付：**
- 解析 `PROJECT-STATE.md` 的标记区块和 `docs/tasks/*.md` 顶部元数据。
- 检查必填字段、固定状态码、任务 ID 唯一性、状态视图覆盖、版本一致性、Git 提交可解析性、当前分支登记和任务指令元数据。
- 输出中文 PASS/FAIL 和可定位的文件、任务 ID、修复提示。
- 提供可测试函数，不写文件、不生成报告。

**验证：**
- `python -B backend/scripts/check_project_development_register.py` → EXIT=0。
- `python -B -m pytest backend/tests/scripts/test_check_project_development_register.py -q --no-cov` → 全部通过。
- 负向测试覆盖重复任务、非法状态、版本漂移、缺元数据和虚构分支。

### 任务 3：接入现有项目总守卫

**文件：**
- 修改：`backend/scripts/check_project.py`
- 修改：`backend/tests/scripts/test_check_project.py`

**交付：**
- `check_project.py --skip-tests` 调用开发总表守卫并纳入统一结果。
- 保持单一执行链，不在 `.pre-commit-config.yaml` 重复注册相同检查。
- 失败时阻断提交，成功时显示中文摘要。

**验证：** `python -B backend/scripts/check_project.py --skip-tests` → EXIT=0；现有 `test_check_project.py` 全部通过。

### 任务 4：统一任务指令元数据和中文状态

**文件：**
- 修改：`docs/tasks/20260829-P0-1-指令.md`
- 修改：`docs/tasks/20260829-P1-4-知识缺口回填-指令.md`
- 修改：`docs/tasks/20260829-P1-5-发票承接验收-指令.md`
- 修改：`docs/tasks/20260829-P1-6-模拟器BCDE走查-指令.md`
- 修改：`docs/tasks/20260829-P1-7-FAQ回收-指令.md`

**交付：**
- 每份指令顶部增加稳定 `task_id` 和 `branch`。
- 将未开始的任务从 `active` 校准为 `pending`；等待店家或负责人决策的任务使用 `blocked`；P0-1 保持 `historical`。
- 保留原始执行快照正文，不把历史快照改写成当前事实。

**验证：** 守卫逐份解析 5 个文件并报告元数据完整；旧快照正文中的历史版本不参与当前字段判断。

### 任务 5：同步静态规则入口

**文件：**
- 修改：`AGENTS.md`
- 修改：`docs/AGENTS/multi-agent-coordination.md`
- 修改：`docs/AGENTS/quick-reference.md`
- 修改：`docs/AGENTS/skill-reference.md`
- 修改：`docs/harness-engineering/README.md`

**交付：**
- 明确“新改动先建任务行，状态变化先回写总表”。
- 明确最小阅读集：`AGENTS.md` + `PROJECT-STATE.md`；仅按任务追加专业文档。
- 增加开发总表守卫命令和故障处理方式。
- 明确历史计划、归档文档和 LOGBOOK 不是当前进度入口。

**验证：** 链接路径检查、关键词检查、`git diff --check`。

### 任务 6：日志、交接和最终验证

**文件：**
- 修改：`LOGBOOK.md`
- 修改：`docs/AGENT-HANDOFF-20260829.md`

**交付：**
- 登记本轮 trace、改动范围、守卫结果、未验证项和工作区状态。
- 将 Harness 改造任务从 `active` 收口为 `completed`，并附验证证据。

**验证：**
- `python -B backend/scripts/check_project_development_register.py` → EXIT=0。
- `python -B backend/scripts/check_project.py --skip-tests` → EXIT=0。
- `python -B backend/scripts/check_mistake_ledger.py` → EXIT=0。
- `python -B backend/scripts/check_text_encoding.py` → EXIT=0。
- `git diff --check` → EXIT=0。
- 复核 `backend/data/`、`backend/reports/`、`miniapp/reports/` 未被修改。

---

## 自审结果

- 覆盖设计规格的所有要求：单一总表、中文优先、任务状态、分支事实、自动守卫、最小阅读集和证据闭环。
- 不新增第二个动态状态文件。
- 不依赖第三方 YAML 解析库；标记区块和标准库解析足以稳定运行。
- 守卫只读，不会因检查而修改状态或业务数据。
- 完整 pytest 和 MiniApp typecheck 不在本轮重复安装执行，保留为已知验证缺口。

