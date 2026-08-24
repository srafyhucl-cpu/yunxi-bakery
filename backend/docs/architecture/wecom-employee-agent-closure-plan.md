# 企微员工助手确定性重构收口落地计划书（可执行版）

> 状态：阶段 0-4 已执行；生产 `/health`、`/ready` 与 45 问回调探针证据已补齐
> 创建日期：2026-07-05
> 环境：Windows 11 / PowerShell，`core.autocrlf=true`，仓库无 `.gitattributes`
> 适用范围：本轮「员工助手回复链路改为确定性直出」重构的收尾提交、CRLF 阻塞处理、生产证据补齐、格式债清理
> 关联文档：[wecom-employee-agent-development-plan.md](./wecom-employee-agent-development-plan.md)、[2026-07-04-wecom-employee-agent-deterministic-reply-design.md](../superpowers/specs/2026-07-04-wecom-employee-agent-deterministic-reply-design.md)、[wecom-intelligent-bot-tools.md](./wecom-intelligent-bot-tools.md)

______________________________________________________________________

## 一、背景与当前真实状态

上一轮已按开发计划书方案 A 完成核心重构：回复链路改为 `query → planner → tools → deterministic reply → clean_plain_text_reply → return`，删除回复期 LLM 润色与两个 guard 文件（`employee_agent_reply_guard.py`、`employee_agent_order_list_guard.py`），全量测试通过、覆盖率 79.08%。

**当前 git 状态（执行前务必复核，可能与此处描述有偏差）**：

- `HEAD` 已包含独立 `style(scripts): apply ruff format to legacy scripts` 提交 `f067dc0`。
- 阶段 0 已确认暂存区归零，重构改动作为独立工作区变更继续推进。

**已核实的关键事实（供执行时直接引用，不必重新查）**：

1. 26 个 `scripts/*.py` 是**纯 ruff format**：`python -m ruff format --check scripts/` 报 `50 files already formatted`；`git diff` 扫描确认仅单引号转双引号、长行折行、空行规范化，零逻辑变更。
2. **CRLF 阻塞根因**：pre-commit 提交**部分文件**时，会把未暂存改动 stash 成 patch，再用 `git -c core.autocrlf=false apply` 重放。工作区是 CRLF、patch 按 LF 生成，行尾对不上导致 `patch does not apply`，提交中止。**只要提交时存在未暂存改动，就会触发此路径。**
3. `git add scripts/*.py` 会因通配命中 `.gitignore` 里的 `scripts/_*.py` 而整条退出；**必须用 `git add -u scripts/`**（只暂存已跟踪的修改）。
4. 回调探针脚本 `scripts/check_wecom_employee_agent_callback.py` 支持 `--json --output`，目标文件已存在会拒绝覆盖。
5. `scripts/wecom_employee_agent_probe_cases.py` **无 argparse**，没有现成快照 dump 参数。
6. pre-commit hooks（`.pre-commit-config.yaml`，均为 local）：`detect-secrets`、`sync-version`、`check-logbook`、`check-file-sizes`、`check-project`、`check-redline-selftest`、`check-mistake-ledger`、`check-text-encoding`、`ruff-check`、`ruff-format-check`、`mypy`。其中 `sync-version` 会自动改写并暂存 `VERSION`。

______________________________________________________________________

## 二、目标与非目标

### 2.1 目标

1. **绕过 CRLF 阻塞完成提交**：用「先 stash 未暂存改动、再提交已暂存」的方式规避 pre-commit 的 patch 重放失败，全程不 `--no-verify`。
2. **提交分层干净**：格式债（26 个 scripts）与重构核心拆成两个独立提交，各自语义单一、可独立回滚。
3. **验收链路当下复现**：提交前用设计文档 `verification` 全套复跑，确认「当下真实通过」。
4. **补齐生产证据**：生产 `/health`、`/ready` 与 45 问回调探针落机器可读证据，销掉 spec 的 `residual_risks`。

### 2.2 非目标

- 不改任何员工助手业务逻辑或回复文案（只落地，不改行为）。
- 不新增能力。
- 不改客户客服链路、企微回调基础设施。
- 不重写全仓行尾策略（不新增 `.gitattributes`、不做全仓 renormalize）——那是独立的大改动，见附录 C。本计划只用 stash 局部规避。

______________________________________________________________________

## 三、CRLF 阻塞处理方案（核心新增，阶段 1/2 都依赖它）

**问题**：提交部分文件时，pre-commit 需 stash 未暂存改动 → CRLF/LF patch 重放失败 → 提交中止。

**方案（推荐）：`git stash --keep-index` 隔离未暂存改动**

原理：把「未暂存」的改动临时藏起来，只留「已暂存」的在工作区。pre-commit 此时无未暂存改动可 stash，不触发 patch 重放路径，hook 正常跑完并提交。提交后 pop 恢复。

每个提交的通用配方（阶段 1、阶段 2 各执行一次）：

```powershell
# 1. 精确暂存本次要提交的文件（见各阶段）
git add -u scripts/            # 或阶段 2 的核心文件列表

# 2. 把其余未暂存改动藏起来，只留已暂存的在工作区
git stash push --keep-index -m "closure-plan-temp"

# 3. 提交（pre-commit 此时无未暂存改动，不会触发 patch 重放）
git commit -m "<message>"

# 4. 恢复藏起来的改动
git stash pop
```

**执行前必须确认的点**：

- 若 `sync-version` hook 在提交时改写并暂存了 `VERSION`，而 `VERSION` 又属于「重构提交」范畴，会造成格式提交里混入 VERSION 改动。阶段 1 提交前需确认 `VERSION` 未被暂存（`git status --short VERSION` 应为空或 `?? / M ` 在工作区侧）。若 hook 强行改 VERSION，见阶段 1 的处置分支。
- `git stash pop` 在 CRLF 环境偶尔也会报冲突。若 pop 失败，改动仍安全存在 `git stash list` 里，用 `git stash show -p stash@{0}` 查看、`git checkout --theirs` / 手动 resolve 恢复，**不要 `git stash drop`**。

**备选方案（仅在 stash 方案反复失败时，且需你显式同意）**：先 `pre-commit run --files <本次文件>` 手动过一遍 hook 确认全绿，再 `git commit --no-verify`。此法跳过 hook 的自动运行，**默认不采用**，需你点头。

______________________________________________________________________

## 四、分阶段执行

### 阶段 0：归零到干净起点（10 分钟）

**目标**：清掉上次失败残留的暂存状态，回到「所有改动都在工作区、无一暂存」的确定起点。

```powershell
# 0.1 看清现状
git status --short
git log --oneline -1          # 应为 68ddc0c；若已变说明上次其实提交成功了，停下核对

# 0.2 取消所有暂存（不丢改动，只把 index 里的挪回工作区）
git reset

# 0.3 复核：第一列应无 M/A/D（全部改动落在第二列 = 未暂存）
git status --short
```

**通过判据**：`git log` 仍在 `68ddc0c`；`git status --short` 中所有条目第一列为空（未暂存）。
**回滚**：`git reset` 不丢改动，无需回滚；若 `git log` 已前进，改为核对那次提交内容后决定是否 `git reset --soft HEAD~1`（需你确认，属改历史）。

### 阶段 1：格式债独立提交（20 分钟）

**目标**：26 个纯 ruff format 的 scripts 单独成一个 `style` 提交。

```powershell
# 1.1 再次确认这批是纯格式（预期：50 files already formatted）
python -m ruff format --check scripts/

# 1.2 只暂存已跟踪的 scripts 修改（用 -u，避免通配命中 gitignore 文件）
git add -u scripts/

# 1.3 确认暂存范围只有 scripts、且 VERSION 没被带进来
git status --short
git diff --cached --name-only        # 应全部是 scripts/*.py

# 1.4 隔离未暂存改动后提交（CRLF 方案）
git stash push --keep-index -m "closure-plan-temp"
git commit -m "style(scripts): apply ruff format to legacy scripts"
git stash pop

# 1.5 验证提交内容无逻辑变更
git show --stat HEAD
git diff -w HEAD~1 HEAD -- scripts/   # 应无输出（去空白后零差异）
```

**处置分支（`sync-version` hook 改了 VERSION）**：若 1.3 看到 `VERSION` 被暂存，先 `git restore --staged VERSION` 移出暂存，再继续 1.4。若 hook 在 commit 时又强行改回，检查 hook 是否因 VERSION 内容与 `pyproject/config` 不一致而触发——此时 VERSION 的改动本就该属阶段 2，让它留在工作区即可。

**通过判据**：`HEAD` 新增一个 `style(scripts)` 提交；`git diff -w HEAD~1 HEAD -- scripts/` 无输出；`git stash list` 为空（pop 成功）。
**回滚**：`git reset --soft HEAD~1`（撤提交、保留暂存），或 `git revert HEAD`（已推送时）。

### 阶段 2：重构核心提交（30 分钟）

**目标**：本轮确定性重构作为单一 `refactor` 提交。**先跑阶段 3 的验证全绿，再执行本阶段提交动作。**

要暂存的核心文件（逐一列出，避免 `git add -A` 误纳）：

```powershell
git add app/service/wecom/employee_agent_service.py
git add app/service/wecom/employee_agent_reply_guard.py          # 删除
git add app/service/wecom/employee_agent_order_list_guard.py     # 删除
git add app/service/wecom/intelligent_bot_ops_format.py
git add tests/service/test_wecom_employee_agent.py
git add tests/service/test_wecom_employee_privacy_format.py
git add VERSION
git add LOGBOOK.md
git add docs/architecture/wecom-intelligent-bot-tools.md
git add docs/architecture/wecom-employee-agent-development-plan.md
git add docs/architecture/wecom-employee-agent-closure-plan.md
git add "docs/superpowers/specs/2026-07-04-wecom-employee-agent-deterministic-reply-design.md"
git add "项目进度与配置清单.md"
```

```powershell
# 2.1 确认暂存范围 = 上面列表，无遗漏无多余
git diff --cached --name-only

# 2.2 隔离未暂存改动后提交
git stash push --keep-index -m "closure-plan-temp"
git commit -m "refactor(wecom): employee agent reply switched to deterministic direct output"
git stash pop        # 若阶段 1 已提交所有 scripts，此时 stash 可能为空，pop 报 "No stash" 属正常

# 2.3 验证
git show --stat HEAD
git status --short   # 理想情况：干净，或仅剩生产证据待补的文件
```

**通过判据**：`HEAD` 新增 `refactor(wecom)` 提交，包含上述全部文件（含两个 guard 的删除 `D`）；两个 guard 在 `git show --stat HEAD` 中显示为删除。
**回滚**：`git reset --soft HEAD~1` 撤回；重构回滚会恢复 `_polish_reply` 与两个 guard 文件。

### 阶段 3：验收链路复现（30 分钟，在阶段 2 提交动作之前执行）

**目标**：不依赖上一轮记忆，当下把设计文档 `verification` 全套复跑一遍。**任一失败则停止提交，先修复。**

```powershell
# 3.1 全量测试 + 覆盖率门槛（pytest.ini 默认 addopts 已含 --cov-fail-under=70）
python -m pytest tests/ -q
# 预期：全绿；末行覆盖率 ≥ 70%（上一轮 79.08%）

# 3.2 员工助手计划探针（预期 45/45）
python scripts/check_wecom_employee_agent_plans.py --json

# 3.3 相关套件单独复跑（关掉覆盖门槛，只看用例本身）
python -m pytest tests/service/test_wecom_employee_agent.py tests/scripts/test_check_wecom_employee_agent_callback.py tests/api/test_wecom_intelligent_bot_plugin_api.py -o addopts="" --no-cov

# 3.4 pre-commit 全量（含红线自检、ruff、mistake-ledger、mypy）
pre-commit run --all-files

# 3.5 架构分层扫描（三条均应零输出）
rg "from app\.repository" app/api -g "*.py"
rg "import aiosqlite|\.execute\(|\.fetchone\(|\.fetchall\(" app/service -g "*.py"
rg "from app\.(service|repository|api)" app/models -g "*.py"
```

**通过判据**：3.1 全绿且覆盖率 ≥ 70%；3.2 报 45/45；3.3 全绿；3.4 全绿；3.5 三条零输出。
**注意**：`pre-commit run --all-files` 不走 `staged_files_only` 的 stash 路径（它直接对全部文件跑），所以**不会触发 CRLF 阻塞**——CRLF 问题只在 `git commit` 提交部分文件时出现。
**失败处置**：3.1 若因某测试挂掉，先定位是重构引入还是环境问题；不得为了过门槛下调 `--cov-fail-under`。3.4 若 `ruff-format-check` 报未格式化文件，说明还有格式债没纳入阶段 1，补跑 `python -m ruff format <文件>` 并归入阶段 1 的 style 提交，不要混进重构提交。

### 阶段 4：生产证据补齐（1 小时，依赖生产环境可达）

**目标**：销掉设计文档 `residual_risks` 的两条。**若当前连不上生产，跳过本阶段并在 LOGBOOK 注明「待生产窗口」，不阻塞阶段 0-3。**

```powershell
# 4.1 生产健康检查（<PROD_HOST> 换成实际地址；若走跳板机由你手动执行）
#     预期 /health 200、/ready 200，offline_review=true 等关键字段正常
#     健康检查只读，安全

# 4.2 45 问回调探针落机器可读证据（脚本已支持 --json --output，已存在会拒绝覆盖）
$ts = Get-Date -Format "yyyyMMdd-HHmmss"
New-Item -ItemType Directory -Force -Path reports/wecom-employee-agent | Out-Null
python scripts/check_wecom_employee_agent_callback.py --json --output "reports/wecom-employee-agent/callback-$ts.json"

# 4.3 核对报告：45 问全过，回复为确定性直出，无「润色篡改」类失败项
```

- [x] 把 4.1 的 `/health`、`/ready` 结果与 4.2 的探针报告路径补进 `LOGBOOK.md` 本轮条目（`trace_id: 20260704-wecom-employee-agent-deterministic-reply`）的验证结果段。
- [x] 把 spec `2026-07-04-*.md` 的 `residual_risks` 从「需在同步后补最终证据」收口为「已补齐，证据见 LOGBOOK / reports」。
- [x] 上述文档改动归入一个独立的 `docs(wecom)` 收尾提交（同样走阶段 3 的 CRLF 配方）。

**通过判据**：探针报告落盘、45/45 全过；LOGBOOK 与 spec 已更新；生产 `/health`、`/ready` 正常。
**回滚**：本阶段仅新增证据文件与文档更新，`git revert` 对应 docs 提交即可；不涉及生产变更（只读健康检查 + 探针）。

______________________________________________________________________

## 五、涉及文件与归属提交

| 文件 | 归属提交 | 说明 |
|------|---------|------|
| `scripts/*.py`（26 个已跟踪） | 阶段 1 `style` | 纯 ruff format,无逻辑变更 |
| `app/service/wecom/employee_agent_service.py` | 阶段 2 `refactor` | 确定性直出 |
| `app/service/wecom/employee_agent_reply_guard.py` | 阶段 2 `refactor` | 删除 |
| `app/service/wecom/employee_agent_order_list_guard.py` | 阶段 2 `refactor` | 删除 |
| `app/service/wecom/intelligent_bot_ops_format.py` | 阶段 2 `refactor` | `transfer_line()` 缺省 summaryPreview 兜底 |
| `tests/service/test_wecom_employee_agent.py` | 阶段 2 `refactor` | 确定性直出断言 |
| `tests/service/test_wecom_employee_privacy_format.py` | 阶段 2 `refactor` | 断言同步当前文案 |
| `VERSION` | 阶段 2 `refactor` | 0.74.32（注意 `sync-version` hook 交互，见阶段 1 处置分支） |
| `LOGBOOK.md` | 阶段 2 + 阶段 4 | 本轮条目 + 生产验证结果 |
| `docs/architecture/wecom-intelligent-bot-tools.md` | 阶段 2 `refactor` | 回复方式说明 |
| `docs/architecture/wecom-employee-agent-development-plan.md` | 阶段 2 `refactor` | 原开发计划书 |
| `docs/architecture/wecom-employee-agent-closure-plan.md` | 阶段 2 `refactor` | 本收口计划书 |
| `docs/superpowers/specs/2026-07-04-*.md` | 阶段 2 + 阶段 4 | residual_risks 收口 |
| `项目进度与配置清单.md` | 阶段 2 `refactor` | 现状与待办 |
| `reports/wecom-employee-agent/callback-*.json` | 阶段 4 `docs` | 探针证据（新增） |

______________________________________________________________________

## 六、风险与回滚

| 风险 | 影响 | 缓解 |
|------|------|------|
| **CRLF 导致 pre-commit patch 重放失败** | 提交部分文件时中止（已实际发生） | 阶段 3 的 stash `--keep-index` 配方隔离未暂存改动；全程不 `--no-verify` |
| `sync-version` hook 自动改 VERSION | 格式提交混入 VERSION 改动 | 阶段 1 提交前 `git restore --staged VERSION`，让 VERSION 归阶段 2 |
| `git add scripts/*.py` 命中 gitignore 整条退出 | 暂存失败 | 统一用 `git add -u scripts/` |
| `git stash pop` 在 CRLF 下冲突 | 改动看似丢失 | 改动仍在 `git stash list`；用 `git stash show -p` 恢复，**禁止 `git stash drop`** |
| 生产环境本窗口不可达 | 阶段 4 无法完成 | 阶段 4 可延后,不阻塞 0-3;LOGBOOK 注明「待生产窗口」 |
| 探针快照逐条对比缺 dump 机制 | 无法做去润色前后 diff | `probe_cases.py` 无 argparse;本轮用 45 问回调探针 `--json` 作等价证据,快照 dump 若需另立项(见附录 C) |
| 为过覆盖率门槛而下调阈值 | 掩盖真实回归 | 明确禁止;门槛失败必须定位根因 |

**总体回滚**：三个提交（style / refactor / docs）各自独立，任一可单独 `git reset --soft HEAD~1`（未推送）或 `git revert`（已推送）。重构回滚会恢复 `_polish_reply` 与两个 guard 文件。

______________________________________________________________________

## 七、验收标准（Definition of Done）

1. 工作区从阶段 0 的干净起点出发，最终 `git status --short` 干净（无未提交的重构/格式改动）。
2. 提交历史含**独立的** `style(scripts)` 与 `refactor(wecom)` 两个提交，各自语义单一；`git diff -w HEAD~1 HEAD -- scripts/`（对 style 提交）无输出。
3. `python -m pytest tests/ -q` 当下通过，覆盖率 ≥ 70%。
4. `pre-commit run --all-files` 全绿；全程未使用 `--no-verify`。
5. 生产 `/health`、`/ready` 正常，45 问回调探针 `--json` 报告落档、全过（或明确标记「待生产窗口」）。
6. LOGBOOK 本轮条目含最终生产验证结果，spec `residual_risks` 收口。

______________________________________________________________________

## 附录 A：执行顺序速查

```
阶段0 归零起点
  → 阶段1 格式债提交（git add -u + stash 配方）
  → 阶段3 验收复现（全绿才继续）
  → 阶段2 重构提交（stash 配方）
  → 阶段4 生产证据 + docs 收尾提交
```

> 阶段 3 的验证在阶段 2 的**提交动作**之前完成，故顺序上 3 先于 2 的 commit。

## 附录 B：CRLF stash 配方速记

```powershell
git add -u <scope>
git stash push --keep-index -m "closure-plan-temp"
git commit -m "<msg>"
git stash pop
```

## 附录 C：本计划不做、但值得单独立项的两件事

1. **全仓行尾治本**：新增 `.gitattributes`（如 `*.py text eol=lf`）+ `git add --renormalize .`，根除 CRLF/LF patch 重放问题。影响面覆盖全仓，会产生一次性大 diff，须单独规划与评审。
2. **探针快照 dump**：给 `scripts/wecom_employee_agent_probe_cases.py` 加 argparse + `--dump`，支持去润色前后逐条快照 diff。本轮用 45 问回调探针 `--json` 作等价证据替代。
