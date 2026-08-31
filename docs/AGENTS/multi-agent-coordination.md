# 多 Agent 协作统一约束

> 生效日期：2026-08-29
> 目的：让并行 Agent 共享同一份当前事实，避免因快照过期、职责越界或临时文件污染而走向不同方向。

## 一、权威源层级

| 层级 | 唯一职责 | 冲突时的处理 |
|---|---|---|
| `AGENTS.md` | 不可违背的操作红线、项目边界和协作流程 | 优先服从，不写入动态版本或任务状态 |
| `PROJECT-STATE.md` | 当前阶段、阻塞项、范围和决策状态 | 作为当前状态唯一入口，由任务 owner 更新 |
| `backend/VERSION` | 技术版本号唯一机器源 | 文档只读取，不自行复制旧版本 |
| `git rev-parse HEAD` | 当前代码快照 | 任务指令必须记录 `as_of_commit`，不把旧 SHA 当现状 |
| `LOGBOOK.md` | 按时间排列的变更和验证证据 | 只记录历史，不覆盖当前状态 |
| `docs/待办优先级清单_*.md` | 当前活动队列和依赖 | 不重新定义阶段状态，引用 `PROJECT-STATE.md` |
| `docs/tasks/*.md` | 可复制执行的任务指令快照 | 必须标 `status`、`status_label`、`as_of_commit`、`version`；不是状态源 |
| `docs/archive/`、根计划书 | 历史材料和决策背景 | 不得作为当前执行起点 |

同一职能尽可能只保留一个正式文件：状态看 `PROJECT-STATE.md`，历史看 `LOGBOOK.md`，错误看根目录 `ERRORS.md`。旧仓镜像或兼容页只能指向正式文件，不得复制条目或继续并行维护；发现多入口时先停止扩展并统一权威源。

出现冲突时，先停止扩展工作，依次核对：

~~~powershell
Get-Content PROJECT-STATE.md -TotalCount 40
Get-Content backend/VERSION
git rev-parse HEAD
git status --short --branch
~~~

在核对完成前不得猜测、不得把“已完成”改写成“已关闭”，也不得沿用过期任务指令。

## 二、统一启动顺序

每个 Agent 在分析、回答或修改前按以下顺序读取：

1. `AGENTS.md`
2. `PROJECT-STATE.md`
3. `LOGBOOK.md` 前 30 行
4. `docs/harness-engineering/README.md`
5. `docs/待办优先级清单_20260829.md`（涉及具体待办时）
6. `miniapp/docs/api-contract.md` 与发布清单（涉及小程序接口、发布、真机或支付时）
7. 本轮对应的 `docs/tasks/*.md`（仅作为执行说明）

## 三、任务与并行规则

每个中大型任务必须声明以下字段：

~~~text
trace_id:
parent_trace_id:
owner:
status: active | blocked | completed | historical
status_label: 进行中（active） | 已阻塞（blocked） | 已完成（completed） | 待处理（pending） | 已暂缓（deferred） | 历史（historical）
as_of_commit:
version:
allowed_paths:
forbidden_paths:
~~~

运行级字段（写入任务交接或 episode 摘要）：

~~~text
run_id:
parent_run_id:
model_id:
tool_policy_hash:
input_artifact_hash:
output_artifact_hash:
failure_class:
latency_ms:
cost:
human_intervention:
replayable:
~~~

- `trace_id` 表示任务链，`run_id` 表示一次实际执行；重试和换 Agent 必须新建 `run_id`，并保留 `parent_run_id`。
- 运行摘要不得只保存最终结论，至少保留计划、关键工具调用、验证命令、策略摘要和恢复点。
- 运行摘要只保存最小必要信息，禁止写入密钥、客户原文、完整订单号或未经批准的生产数据。

- 一个任务只允许一个 owner 修改 `PROJECT-STATE.md`、`LOGBOOK.md` 和任务状态字段；其他 Agent 通过消息回报证据，不直接覆盖。
- 并行 Agent 必须在动手前读取同一 `PROJECT-STATE.md` 和同一 `as_of_commit`；发现工作区已有改动时只修改授权路径。
- 子任务不得擅自扩大范围、修复未授权缺陷、提交或推送；需要扩大范围时先回报 owner。
- 技术完成与治理关闭分开记录：测试通过不等于负责人批准，部署成功不等于正式上线。
- `status` 仅作为机器枚举保留英文；面向人展示必须使用 `status_label` 或中文状态并附机器码，禁止在中文叙述中裸写 `active`、`blocked`、`completed`、`pending`、`deferred`、`historical`。
- 任何“通过”“完成”“无风险”结论都要附实际命令、退出码或证据路径；未执行写“未验证”。
- 任何“完成”结论还必须区分结果正确、策略合法、证据完整和可回放四项，不得以单一成功命令替代。

## 四、文档一致性规则

- 动态文档头部至少写 `updated_at`、`as_of_commit`、`version`；不能复制历史快照而不标日期。
- `PROJECT-STATE.md` 只保留当前状态；历史变更进入 LOGBOOK，旧方案进入 `docs/archive/` 并加历史说明。
- `docs/tasks/` 必须在文件头标明 `status` 和 `status_label`。已完成指令保留作证据，但不得继续被当作活动任务。
- 发现状态、版本、路径或范围不一致时，先记录差异，再以权威源校正；禁止为了“对齐数量”编造业务事实。
- 仅修改文档时也要做链接、路径、版本和关键词检查，并在 LOGBOOK 记录本轮同步原因。
- 运行级事实不得回写成任务级历史：`run_id`、耗时、成本和失败分类留在 episode/证据摘要，`PROJECT-STATE.md` 只保留当前任务状态。

## 五、临时文件与清理

### 当前进度最小阅读集

快速了解项目进度时只需读取 `AGENTS.md` 与 `PROJECT-STATE.md`；执行具体任务再读取对应 `docs/tasks/*.md`，专业契约按需追加。不要为了确认当前状态通读全部代码、历史计划或归档文档。

新改动点必须先在 `PROJECT-STATE.md` 建立或认领 `task_id`；状态变化先改总表，再改任务说明或 `LOGBOOK.md`。总表守卫命令：`python -B backend/scripts/check_project_development_register.py`。

- 只清理确认无用、可重新生成且有替代证据的临时或构建产物；删除前先核对引用和哈希。
- 允许对本轮创建或清理脚本白名单内的目录递归扫描并批量清理；未知目录、业务数据、生产目录、有效报告和其他 Agent 的有效工件仍禁止递归或批量删除。
- 缓存、虚拟环境、`node_modules` 等目录只有在预览核对并获得任务或用户明确授权后，才能使用预览输出的 `-PreviewToken <令牌> -Execute` 批量清理；仍不得触碰 `backend/data/`、`backend/reports/`、`miniapp/reports/` 或有效报告。
- 不确定是否属于用户记忆、审计证据或发布证据的文件一律保留，改用 `.gitignore` 防止误提交。
- 新建的临时文件必须放在项目磁盘或仓库外的 D 盘临时目录，并在任务结束前按白名单递归批量清理。

本仓库的本机清理入口为 `scripts/cleanup-local-artifacts.ps1`：不带 `-Execute` 只预览并输出目标清单授权令牌，带匹配的 `-PreviewToken <令牌> -Execute` 才执行白名单内递归批量清理；脚本不会删除 `backend/reports/`、`miniapp/reports/` 或 `backend/data/`，仅允许清理脚本内明确列出的过期重复报告例外，并在删除前校验所有目标位于当前工作区或指定的 D 盘临时根目录。脚本使用 UTF-8 BOM，兼容 Windows PowerShell 5.1；质量门禁子进程的 `TMP`/`TEMP`/`TMPDIR` 固定到项目所在磁盘的一次性目录，避免第三方库把缓存写入 C 盘。

## 六、交接与收口

交接至少说明：目标、当前状态、已完成改动、未完成事项、验证命令及退出码、工作区 dirty/staged/untracked 事实、风险与下一步。收口前检查：

1. `PROJECT-STATE.md`、任务队列和本轮代码事实一致。
2. `LOGBOOK.md` 有本轮 trace 条目。
3. 证据文件已登记，或明确说明无需登记。
4. 临时或可重建产物已按白名单递归批量清理，剩余缓存和目录已列明。
5. 没有把历史计划、旧仓路径或已完成指令留作默认执行入口。
