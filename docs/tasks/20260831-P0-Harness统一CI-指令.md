# P0 任务指令：仓库级 Harness CI 统一入口

> owner: AI 员工
> status: completed
> status_label: 已完成（completed）
> task_id: T-HARNESS-CI-ENTRY
> as_of_commit: b4f25db
> version: 0.133.0-p2trial.3
> branch: main
> allowed_paths: `.github/workflows/harness-p0.yml`、`backend/scripts/harness_p0_gate.py`、`backend/tests/scripts/test_harness_p0_gate.py`、`docs/harness-engineering/**`、`docs/AGENTS/**`、本任务文件
> forbidden_paths: `backend/app/**`、`miniapp/**`、`backend/data/**`、生产环境、真实支付、客户数据、旧仓 `D:\Project\YunxiBakeMiniApp`
> source_of_truth: PROJECT-STATE.md

## 本轮目标

建立根级可发现的 GitHub Actions 入口，统一执行中文治理、策略即代码、运行 manifest、开发总表、错误账本、证据索引、文本编码和项目红线检查，并上传 JSON 报告。

## 执行步骤

1. 本地运行 `python -B backend/scripts/harness_p0_gate.py --summary`。
2. CI 运行 `python backend/scripts/harness_p0_gate.py --summary --json-out reports/harness/p0-gate.json`。
3. 无论门禁成功或失败，都保留 JSON 报告供审计和回放。

## 验收

- 根目录 `.github/workflows/harness-p0.yml` 可被 GitHub Actions 自动发现。
- P0 总门禁 8 项检查全部通过时退出码为 0，任一检查失败时正确传播非零退出码。
- CI 使用项目盘临时目录和缓存，不写入 C 盘项目缓存。

## 本轮追溯

- trace_id: `20260831-p0-execution`
- run_id: `20260831-p0-execution-r1`
- replayable: 是；失败分类：无；人工介入：无。
- completed_at: 2026-08-31
- evidence: `backend/reports/harness/p0-gate-20260831-p0-execution.json`；根级 `.github/workflows/harness-p0.yml`
- result: 已完成（completed）；本地 P0 门禁 8 项检查全部通过，CI 失败时保留 JSON 报告。
