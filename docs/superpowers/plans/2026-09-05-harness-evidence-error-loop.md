# Harness 证据完整性与错误候选闭环实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans or subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **执行状态（2026-09-05，trace: `20260905-harness-evidence-error-loop`）**
> - Task 1–Task 10 已全部实施并通过本地定向门禁：定向 pytest 73 项、P0 门禁 9/9（run_id `p0-gate-7788e47fb0114e42`）、中文治理 coverage=1.0/dimension_ratio=1.0、自评 18/18（数据集 1.2.0）、证据索引 384 条 failed=0（E-20260905-005）。
> - 审查修复轮已完成：①最终 artifact index 步骤位于 Summary 之后，覆盖并哈希校验 `ci-summary-*.md`（本地与 workflow 同名口径索引 `local-20260905-a2-final` 65 文件 0 缺失，可直接核验）；②accept 改为原子顺序（先 review 记录后账本，账本失败回滚 review）并固化回归测试；③Ruff 清零。
> - **复选框收口条件**：提交推送后核验远端 GitHub Actions P1/P2 run 的最终 artifact index 与中文 Summary（`gh run download`），确认后再统一把 `- [ ]` 更新为 `[x]` 并正式关闭本 trace。
> - `LOGBOOK.md` 2026-09-05 条目与 `docs/harness-engineering/core/evidence-index.md` E-20260905-005 记录完整验证命令、退出码与失败分类。

**Goal:** 修复 Harness CI 证据包不完整问题，并建立“自动生成错误候选、人工确认、正式写入 `ERRORS.md`”的可回放工作流。

**Architecture:** 第一部分增强现有 P1/P2 GitHub Actions，使 workflow YAML 可解析、失败时仍保留全部报告、运行 manifest、汇总和候选文件，并生成带哈希的 artifact 索引。第二部分新增独立的错误候选模块：从结构化失败报告生成候选，使用稳定 fingerprint 去重，通过人工 review 命令接受、拒绝或延期，只有接受后才修改根目录 `ERRORS.md`。

**Tech Stack:** Python 3.13、pytest、现有 Harness manifest/schema、GitHub Actions、PowerShell、Markdown。

## Global Constraints

- 工作区已有未提交改动不得覆盖、回滚或重写；先读取并与现有改动协作。
- 不访问生产、真实支付、客户数据或旧仓有效工作区。
- 不新增第三方依赖；优先复用现有 `harness_run_manifest.py`、`check_mistake_ledger.py` 和 `build_release_manifest.py` 中的哈希模式。
- 所有新增 Python 函数必须有类型注解；自然语言注释和人类可读输出使用中文。
- `ERRORS.md` 仍是唯一正式错误账本；候选文件不得被当作正式错误条目。
- CI 失败必须保留证据并最终失败；不能用 `continue-on-error` 掩盖最终 job 结果。
- 生成物不得覆盖已有报告；使用带 run_id 或时间戳的唯一文件名。
- 本轮统一使用 `trace_id: 20260905-harness-evidence-error-loop`。
- 新增或认领任务必须登记到 `PROJECT-STATE.md`，任务状态同时填写 `status` 与中文 `status_label`。
- 实施期间只运行定向测试；上线候选式全量测试不属于本轮范围。

## 文件边界总览

### CI 证据完整性

- Modify: `.github/workflows/harness-p1-p2.yml`
- Modify: `.github/workflows/harness-p0.yml`（仅在需要统一 artifact 索引时）
- Create or modify: `backend/scripts/build_harness_artifact_index.py`
- Test: `backend/tests/scripts/test_build_harness_artifact_index.py`
- Modify: `backend/scripts/harness_ci_summary.py`
- Test: `backend/tests/scripts/test_harness_ci_summary.py`
- Modify: `backend/scripts/harness_eval_regression.py`
- Test: `backend/tests/scripts/test_harness_eval_regression.py`

### 错误候选闭环

- Create: `backend/scripts/harness_failure_candidate.py`
- Create: `backend/scripts/review_failure_candidate.py`
- Create: `backend/tests/scripts/test_harness_failure_candidate.py`
- Create: `backend/tests/scripts/test_review_failure_candidate.py`
- Modify: `docs/harness-engineering/core/failure-candidate.schema.json`
- Modify: `docs/harness-engineering/README.md`
- Modify: `docs/harness-engineering/core/traceability-model.md`
- Modify: `docs/harness-engineering/core/verification-matrix.md`
- Modify: `backend/scripts/harness_ci_summary.py`
- Modify: `.github/workflows/harness-p1-p2.yml`
- Modify: `.github/workflows/harness-p0.yml`（仅在需要接入候选生成时）

### 管理与收口

- Modify: `PROJECT-STATE.md`
- Modify: `LOGBOOK.md`
- Modify: `docs/harness-engineering/HARNESS-MATURITY-REVIEW-20260830.md`
- Modify: `docs/harness-engineering/core/evidence-index.md`
- Create: `docs/tasks/20260905-Harness证据与错误闭环-指令.md`

---

## Task 1: 建立任务登记和执行边界

**Files:**
- Modify: `PROJECT-STATE.md`
- Create: `docs/tasks/20260905-Harness证据与错误闭环-指令.md`

**Required task records:**

- `T-HARNESS-CI-EVIDENCE-COMPLETE`
- `T-HARNESS-ERROR-CANDIDATE-LOOP`
- `trace_id: 20260905-harness-evidence-error-loop`
- `owner: AI 员工`
- `status: active`
- `status_label: 进行中（active）`
- `as_of_commit`: 开始实施前通过 `git rev-parse HEAD` 获取完整 40 位 SHA
- `version`: 读取 `backend/VERSION`
- `allowed_paths`: 本计划列出的 workflow、Harness scripts/tests、Harness docs、状态和证据文件
- `forbidden_paths`: `backend/app/**`、`miniapp/**`、`backend/data/**`、生产目录、真实支付、客户数据、旧仓

- [ ] 先读取工作区状态，确认既有未提交文件。
- [ ] 在 `PROJECT-STATE.md` 主表新增两个任务，状态说明使用中文。
- [ ] 创建任务指令文件，写明目标、边界、依赖、验收标准、风险和恢复点。
- [ ] 运行 `python -B backend/scripts/check_project_development_register.py`。

Expected result: 两个任务均可被总表守卫识别，不改变现有任务状态。

---

## Task 2: 修复并验证 P1/P2 workflow YAML

**Files:**
- Modify: `.github/workflows/harness-p1-p2.yml`
- Test: 新增或修改 `backend/tests/scripts/test_harness_workflow_contract.py`

**Required behavior:**

- `if: always()`、`uses:`、`with:` 同级缩进。
- workflow 必须能被 YAML parser 解析。
- 质量步骤可以使用 `continue-on-error: true` 来保留后续报告，但最终汇总步骤必须失败退出。
- 上传步骤必须使用 `if: always()`。
- workflow 中保留 `fetch-depth: 0`。

- [ ] 先写测试，读取 workflow 文本并验证 YAML 根节点、job、steps 和 artifact step 结构。
- [ ] 运行该测试，确认当前错误缩进会失败。
- [ ] 只修复 YAML 结构，不顺便改动业务或无关 action。
- [ ] 验证 `upload-artifact` step 的 `if`、`uses`、`with` 位于同一 step 映射层级。
- [ ] 运行 workflow 合同测试。

Run:

```powershell
python -B -m pytest backend/tests/scripts/test_harness_workflow_contract.py -q --no-cov -p no:cacheprovider
```

Expected result: workflow contract tests pass；不依赖 GitHub 网络。

---

## Task 3: 实现完整 artifact 索引

**Files:**
- Create: `backend/scripts/build_harness_artifact_index.py`
- Create: `backend/tests/scripts/test_build_harness_artifact_index.py`

**Interface:**

```python
def build_artifact_index(
    report_dir: Path,
    *,
    run_id: str,
    required_patterns: tuple[str, ...],
) -> dict[str, object]:
    ...

def write_artifact_index(path: Path, payload: dict[str, object]) -> None:
    ...
```

**Required output fields:**

```text
schema_version
artifact_index_type
generated_at
run_id
commit_sha
files[]
  path
  size_bytes
  sha256
  exists
required_files[]
missing_files[]
status
```

**Required file set for P1/P2:**

```text
harness-eval-*.json
harness-observation-*.json
doc-garden-*.json
ci-quality-loop*.run.json
artifact-index*.json
failure-candidates/*.json
```

- [ ] 测试空目录、缺失 required file、正常目录、哈希稳定性和拒绝覆盖。
- [ ] 使用 `hashlib.sha256` 对实际文件计算哈希。
- [ ] 路径必须限制在 `report_dir` 内，拒绝目录穿越。
- [ ] 缺少必需文件时返回 `status=failed`，但仍输出索引报告。
- [ ] 写入已存在路径时失败，不能覆盖旧证据。
- [ ] 运行定向测试。

Run:

```powershell
python -B -m pytest backend/tests/scripts/test_build_harness_artifact_index.py -q --no-cov -p no:cacheprovider
```

---

## Task 4: 接入完整 CI artifact 和失败摘要

**Files:**
- Modify: `.github/workflows/harness-p1-p2.yml`
- Modify: `backend/scripts/harness_ci_summary.py`
- Modify: `backend/tests/scripts/test_harness_ci_summary.py`

**Required behavior:**

- 汇总脚本必须将缺报告、步骤失败、manifest 缺失和 artifact index 失败列入 `failures`。
- 设置 `GITHUB_STEP_SUMMARY` 时输出中文摘要。
- 每个失败项继续输出 GitHub annotation。
- 汇总脚本退出码：
  - 所有检查通过：`0`
  - 任一检查失败：`1`
- `record_observation` 失败不能阻止 artifact 上传。
- artifact 上传路径必须覆盖 `.run.json`、所有 JSON 报告、候选文件和 summary。

- [ ] 为缺少 `.run.json`、缺少候选目录和 artifact index 失败补测试。
- [ ] 修改 workflow，在汇总前生成 artifact index。
- [ ] 将 `ci-quality-loop.run.json` 明确加入 artifact。
- [ ] 将 `GITHUB_STEP_SUMMARY` 输出写入 `backend/reports/harness/ci-summary.md`，或使用 step summary 与 artifact 双写。
- [ ] 上传：

```text
backend/reports/harness/**
```

- [ ] 保留 `if: always()` 和 `if-no-files-found: error`；若允许失败路径没有某类报告，必须先生成结构化失败报告而不是静默缺失。
- [ ] 汇总步骤放在上传步骤前后均可，但最终 job 必须继承汇总退出码。
- [ ] 运行定向测试和 workflow 合同测试。

Run:

```powershell
python -B -m pytest backend/tests/scripts/test_harness_ci_summary.py backend/tests/scripts/test_harness_workflow_contract.py -q --no-cov -p no:cacheprovider
```

---

## Task 5: 建立错误候选数据模型和 fingerprint

**Files:**
- Create: `docs/harness-engineering/core/failure-candidate.schema.json`
- Create: `backend/scripts/harness_failure_candidate.py`
- Create: `backend/tests/scripts/test_harness_failure_candidate.py`

**Interface:**

```python
def build_failure_candidate(
    *,
    source: str,
    failure_class: str,
    summary: str,
    run_id: str | None,
    trace_id: str | None,
    task_id: str | None,
    commit_sha: str,
    evidence_files: list[str],
    suggested_guardrail: str,
    root_dir: Path,
) -> dict[str, object]:
    ...

def compute_failure_fingerprint(
    *,
    failure_class: str,
    summary: str,
    normalized_files: list[str],
) -> str:
    ...

def discover_duplicate(
    candidate: dict[str, object],
    *,
    candidate_dir: Path,
    ledger_path: Path,
) -> str | None:
    ...
```

**Candidate fields:**

```text
schema_version
candidate_id
fingerprint
status: pending | accepted | rejected | deferred
source
created_at
failure_class
summary
symptom
root_cause: ""
impact: ""
suggested_guardrail
run_id
trace_id
task_id
as_of_commit
version
evidence_files
duplicate_of
review:
  operator
  reviewed_at
  decision
  reason
```

- [ ] 先写 schema 和负向测试，覆盖缺字段、非法状态、非法 SHA 和重复 fingerprint。
- [ ] fingerprint 只使用稳定字段，不能包含生成时间、绝对路径或随机 ID。
- [ ] 候选 ID 可以随机生成，但 fingerprint 必须可重复。
- [ ] 候选默认状态必须为 `pending`。
- [ ] `discover_duplicate` 同时检查候选目录和 `ERRORS.md`，不能只查候选目录。
- [ ] 不允许候选生成器修改 `ERRORS.md`。
- [ ] 运行定向测试。

Run:

```powershell
python -B -m pytest backend/tests/scripts/test_harness_failure_candidate.py -q --no-cov -p no:cacheprovider
```

---

## Task 6: 实现人工 review 和正式入账

**Files:**
- Create: `backend/scripts/review_failure_candidate.py`
- Create: `backend/tests/scripts/test_review_failure_candidate.py`
- Modify: `backend/scripts/check_mistake_ledger.py`（仅增加候选关联字段或一致性检查）
- Modify: `ERRORS.md`（只在实际 accept 测试 fixture 或人工确认后新增正式条目）

**Interface:**

```powershell
python backend/scripts/review_failure_candidate.py `
  --candidate <path> `
  --decision accept|reject|defer `
  --operator "<负责人>" `
  --reason "<确认理由>" `
  --root-dir <repo>
```

**Rules:**

- `reject`：更新候选 review 状态，不修改 `ERRORS.md`。
- `defer`：更新候选 review 状态，不修改 `ERRORS.md`。
- `accept`：必须提供 `root_cause`、`impact`、`fix`、`new_guardrail`、`verification`、`next_time_signal` 等正式账本字段；缺失时拒绝入账。
- accept 后生成新的 `M-YYYYMMDD-NNN` ID，不能复用 candidate ID。
- accept 后运行 `check_mistake_ledger.py`。
- accept 失败时不得留下半条正式条目；使用临时内容校验后一次性写入。
- 已有 `duplicate_of` 的候选默认禁止再次 accept，除非显式提供 `--override-duplicate` 和理由。
- 候选文件本身必须不可覆盖，review 应生成新版本或新 review 文件，不能篡改历史候选。

- [ ] 先写 reject/defer/accept 三条路径测试。
- [ ] 测试缺字段、重复候选、重复账本 ID、非法 operator 和路径越界。
- [ ] 实现 review 结果追加文件，例如：

```text
backend/reports/harness/failure-candidates/<candidate_id>.review.json
```

- [ ] 实现 accept 入账前的 Markdown 字段校验。
- [ ] 实现安全 ID 分配：扫描 `ERRORS.md` 现有当天序号并递增。
- [ ] 运行 review 测试和错误账本检查。

Run:

```powershell
python -B -m pytest backend/tests/scripts/test_review_failure_candidate.py backend/tests/scripts/test_check_mistake_ledger.py -q --no-cov -p no:cacheprovider
python -B backend/scripts/check_mistake_ledger.py
```

---

## Task 7: 将失败运行接入候选生成

**Files:**
- Modify: `backend/scripts/harness_ci_summary.py`
- Modify: `.github/workflows/harness-p1-p2.yml`
- Modify: `.github/workflows/harness-p0.yml`（如 P0 也生成候选）
- Modify: `backend/tests/scripts/test_harness_ci_summary.py`
- Modify: `backend/tests/scripts/test_harness_workflow_contract.py`

**Required behavior:**

- CI 失败时生成 candidate JSON。
- CI 成功时不生成错误候选，除非报告内部存在明确 `failed` 或 `failure_class != none`。
- 候选包含 `run_id`、`trace_id`、`task_id`、`as_of_commit`、失败分类、摘要和证据路径。
- 候选生成失败不能覆盖原始 CI 失败；必须在 Summary 中标记 `failure_candidate_generation`。
- 候选生成不会自动写入 `ERRORS.md`。
- 同一个 fingerprint 的失败只生成一个 pending 候选，并在新运行中记录 `duplicate_of`。

- [ ] 先为失败/成功/候选生成失败写测试。
- [ ] 在 workflow 的 `if: always()` 阶段调用候选生成。
- [ ] 将候选目录纳入 artifact index 和 artifact 上传。
- [ ] 将候选状态和重复关系写入中文 Summary。
- [ ] 运行定向测试。

---

## Task 8: 增加 Harness 自评和中文治理覆盖

**Files:**
- Modify: `backend/scripts/harness_eval_regression.py`
- Modify: `docs/harness-engineering/evals/harness-eval-dataset.json`
- Modify: `backend/tests/scripts/test_harness_eval_regression.py`
- Modify: `backend/scripts/check_chinese_governance.py`（仅在需要扫描新模板时）
- Modify: `backend/tests/scripts/test_check_chinese_governance.py`
- Modify: `docs/harness-engineering/core/chinese-governance.json`

**Required evaluator cases:**

- workflow YAML 可解析。
- artifact index 覆盖 `.run.json`。
- failure candidate 默认不修改 `ERRORS.md`。
- review accept 才能修改 `ERRORS.md`。
- review reject/defer 不修改 `ERRORS.md`。
- 中文 Summary 包含失败分类、证据路径和未验证范围。

- [ ] 新增 evaluator 前先补数据集 case。
- [ ] 所有 evaluator 使用临时目录或 fixture，不访问网络、生产和客户数据。
- [ ] 扩展测试断言数据集版本、总数和失败分类。
- [ ] 中文治理模型纳入新任务模板、candidate/review 模板中的人类可读字段。
- [ ] 运行中文治理专项测试。

---

## Task 9: 文档、状态和证据收口

**Files:**
- Modify: `docs/harness-engineering/README.md`
- Modify: `docs/harness-engineering/core/traceability-model.md`
- Modify: `docs/harness-engineering/core/verification-matrix.md`
- Modify: `docs/harness-engineering/HARNESS-MATURITY-REVIEW-20260830.md`
- Modify: `PROJECT-STATE.md`
- Modify: `LOGBOOK.md`
- Modify: `docs/harness-engineering/core/evidence-index.md`
- Create or modify: `docs/tasks/20260905-Harness证据与错误闭环-指令.md`

- [ ] 记录 CI artifact 包含的完整文件集合和哈希索引规则。
- [ ] 记录候选状态机：`pending → accepted/rejected/deferred`。
- [ ] 明确 `ERRORS.md` 只接受人工确认后的正式条目。
- [ ] 更新验证矩阵，增加 workflow YAML、artifact index、candidate/review 测试。
- [ ] 中文治理文档明确区分：
  - 静态中文治理覆盖率；
  - CI/运行输出中文可读性；
  - 证据包完整性；
  - 人工批准与错误入账。
- [ ] 成熟度仍维持 `3.0/5`，除非已有多个周期趋势证据满足升级条件。
- [ ] 在 LOGBOOK 记录本轮 trace、两个 task_id、验证命令、退出码、失败分类和未验证范围。
- [ ] 在 evidence index 登记最终报告、artifact index、candidate fixture、review fixture 和远端 CI run。

---

## Task 10: 最终验证和交付给 OpenCode

**Required commands:**

```powershell
python -B -m pytest `
  backend/tests/scripts/test_harness_workflow_contract.py `
  backend/tests/scripts/test_build_harness_artifact_index.py `
  backend/tests/scripts/test_harness_ci_summary.py `
  backend/tests/scripts/test_harness_failure_candidate.py `
  backend/tests/scripts/test_review_failure_candidate.py `
  backend/tests/scripts/test_harness_eval_regression.py `
  backend/tests/scripts/test_check_chinese_governance.py `
  backend/tests/scripts/test_check_mistake_ledger.py `
  -q --no-cov -p no:cacheprovider
```

```powershell
python -B backend/scripts/check_chinese_governance.py --summary
python -B backend/scripts/check_mistake_ledger.py
python -B backend/scripts/check_project_development_register.py
python -B backend/scripts/harness_eval_regression.py --summary
python -B backend/scripts/harness_p0_gate.py --summary
python -B backend/scripts/check_doc_garden.py --summary --fail-on error
git diff --check
git status --short --branch
```

**Acceptance criteria:**

- workflow YAML 可被解析。
- P1/P2 失败时仍上传完整 artifact。
- artifact index 列出并哈希校验所有报告、manifest、candidate 和 summary。
- 模拟失败能生成 `pending` candidate。
- 候选生成不会修改 `ERRORS.md`。
- `reject`/`defer` 不修改 `ERRORS.md`。
- `accept` 才能生成合法 `M-YYYYMMDD-NNN` 条目。
- 重复 fingerprint 能识别已有候选或账本条目。
- P0 门禁通过。
- 中文治理 `coverage=1.0`、`dimension_ratio=1.0`。
- 所有失败、未验证范围和人工确认均有中文说明。
- 没有执行生产、真实支付、客户数据或旧仓操作。

**OpenCode handoff:**

OpenCode 必须先读取：

```text
AGENTS.md
PROJECT-STATE.md
LOGBOOK.md
docs/harness-engineering/README.md
docs/AGENTS/multi-agent-coordination.md
docs/harness-engineering/core/verification-matrix.md
```

执行顺序必须为：

```text
Task 1 → Task 2 → Task 3 → Task 4
       → Task 5 → Task 6 → Task 7 → Task 8
       → Task 9 → Task 10
```

每个任务完成后单独运行定向测试并保留输出。任何 workflow、状态、证据或路径冲突先停止并回报，不得覆盖现有 Agent 改动。
