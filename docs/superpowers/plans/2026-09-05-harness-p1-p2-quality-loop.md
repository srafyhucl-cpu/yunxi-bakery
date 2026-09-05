# Harness P1/P2 Quality Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 P1/P2 CI 在保留完整 artifact 的同时明确暴露失败，并把 CI/本地运行纳入 Harness 趋势观测与扩展回归集。

**Architecture:** 新增一个轻量 CI 汇总脚本读取步骤结果和 JSON 报告，统一写 GitHub Summary/annotation 并以失败退出。回归脚本生成真实 `.run.json` manifest，观测脚本继续消费同一目录；文档仅记录当前证据与待办，不虚增成熟度评级。

**Tech Stack:** GitHub Actions YAML、Python 3.13、pytest、现有 Harness manifest/observation 脚本、PowerShell 清理脚本。

## Global Constraints

- 不删除或覆盖已有有效报告；输出文件使用新路径或按现有拒绝覆盖约定处理。
- 所有新增 Python 函数使用类型注解，注释使用中文，不引入新依赖。
- CI 保留 artifact 产出，但最终汇总 job 必须在任一质量项失败时失败。
- 临时目录仅通过 `scripts/cleanup-local-artifacts.ps1` 预览令牌流程清理。
- 本轮使用 trace_id `20260905-harness-p1-p2-quality-loop`。

---

### Task 1: CI 结果汇总与运行 manifest 接入

**Files:**
- Create: `backend/scripts/harness_ci_summary.py`
- Modify: `.github/workflows/harness-p1-p2.yml`
- Test: `backend/tests/scripts/test_harness_ci_summary.py`

**Interfaces:**
- `build_summary(eval_report, observation_report, doc_garden_report, step_outcomes) -> dict[str, object]`
- CLI exits `0` only when all required checks pass; writes GitHub Summary and annotations when environment variables are present.

- [ ] 写失败测试：报告失败、步骤失败和缺报告分别被汇总为失败，并保留 artifact 友好信息。
- [ ] 运行定向测试确认失败。
- [ ] 实现汇总脚本与 manifest 输出。
- [ ] 修改 workflow：步骤写出 outcome 文件，新增 always 汇总步骤，汇总失败后 job 失败；升级 actions 到 Node 24 兼容主版本。
- [ ] 运行定向测试与 YAML 静态检查。

### Task 2: 扩展 Harness 回归集

**Files:**
- Modify: `backend/scripts/harness_eval_regression.py`
- Modify: `docs/harness-engineering/evals/harness-eval-dataset.json`
- Modify: `backend/tests/scripts/test_harness_eval_regression.py`

**Interfaces:**
- 新增四个 evaluator：`shallow_clone_history_contract`、`ci_corpus_contract`、`state_snapshot_parent_contract`、`artifact_failure_visibility_contract`。

- [ ] 为四个 evaluator 写失败测试。
- [ ] 实现最小可验证检查，避免依赖真实网络或生产数据。
- [ ] 将数据集版本提升为 `1.1.0`，总计 12 项并保持 100% 通过。
- [ ] 运行回归脚本和定向测试。

### Task 3: 观测样本与本地入口

**Files:**
- Modify: `backend/scripts/observe_harness_runs.py`
- Modify: `backend/scripts/harness_run_manifest.py`（仅在需要时）
- Modify: `backend/tests/scripts/test_observe_harness_runs.py`

**Interfaces:**
- 观测报告继续输出 `metrics.total_runs`，并支持 CI 生成的 manifest 路径；缺样本时明确 `no_runs` 状态而非静默成功。

- [ ] 添加目录/显式 manifest 混合发现测试。
- [ ] 添加本地运行 manifest 生成与观测汇总测试。
- [ ] 实现最小改动并确保旧调用兼容。
- [ ] 运行定向观测测试。

### Task 4: 成熟度、doc garden、中文治理和 Actions 跟踪文档

**Files:**
- Modify: `docs/harness-engineering/HARNESS-MATURITY-REVIEW-20260830.md`
- Modify: `docs/harness-engineering/README.md`
- Modify: `docs/AGENTS/skill-reference.md`（如入口变化）
- Modify: `LOGBOOK.md`
- Modify: `PROJECT-STATE.md`

- [ ] 明确评级仍为 3.0/5，列出趋势样本门槛和本轮新增证据。
- [ ] 将 14 个历史归档断链标注为不可复原历史引用或补可达替代入口。
- [ ] 记录低风险中文治理与 Node 24 action 升级为 P2 跟踪项。
- [ ] 登记本轮 trace、验证命令、退出码和临时目录清理结果。

### Task 5: 验证与临时 artifact 清理

**Files:**
- No source changes; generated evidence under `backend/reports/harness/` only when required.

- [ ] 运行改动相关 pytest、Harness 自评、观测、doc garden、项目登记检查。
- [ ] 运行清理脚本预览 `.tmp-harness-p0-r6/`，核对令牌与保护边界。
- [ ] 使用预览令牌执行清理并记录文件数、失败项和剩余状态。
- [ ] 最终检查 `git diff`、工作区状态和证据索引。
