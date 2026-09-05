# Verification Matrix

本文件用于减少 Vibe Coding 收口时的随机性。每次变更完成后，先按变更类型选择最低验证；涉及生产、数据、跨层调用或高风险路径时，再执行加强验证。

## 测试节奏与全量测试门禁

1. **开发阶段**：默认运行与改动直接相关的定向测试；不因每次编辑、每个小提交或每轮文档调整重复运行全量测试。
2. **上线候选收口**：每个功能或模块在进入上线候选版本时执行一次全量测试，作为该收口轮次的权威结果。
3. **全量失败处理**：先用定向测试定位和修复；修复后允许一次最终全量复跑，并在 `LOGBOOK.md` 记录初次失败、修复范围、复跑原因和最终结果。
4. **耗时评估**：全量测试记录命令、退出码、测试数量、开始时间、结束时间和总耗时。单次超过 10 分钟，或较最近基线增加 20% 以上，必须登记测试优化评估。
5. **优化方向**：优先采用测试分片、并行执行、夹具隔离、缓存和 `slow` 标记；禁止通过删测、静默跳过失败或降低覆盖率阈值伪造提速。
6. **纯文档/Harness 变更**：未触及代码行为时不要求全量测试，验证记录必须明确写出未运行原因和已执行的定向门禁。

推荐的 Windows PowerShell 耗时记录方式：

```powershell
$startedAt = Get-Date
$timer = [Diagnostics.Stopwatch]::StartNew()
python -B -m pytest tests/ -q --no-cov
$testExit = $LASTEXITCODE
$timer.Stop()
$finishedAt = Get-Date
Write-Output "FULL_TEST_EXIT=$testExit"
Write-Output "FULL_TEST_STARTED_AT=$startedAt"
Write-Output "FULL_TEST_FINISHED_AT=$finishedAt"
Write-Output "FULL_TEST_DURATION_SECONDS=$([math]::Round($timer.Elapsed.TotalSeconds, 2))"
```

______________________________________________________________________

## 通用基线

| 场景 | 命令 |
|---|---|
| 查看工作区 | `git status --short` |
| 红线扫描 | `python scripts/check_project.py --skip-tests` |
| 红线规则自测 | `python -m pytest tests/test_red_line_rules.py -q --tb=short --no-cov` |
| 全量测试 | `python -m pytest tests/ -q` |
| Ruff 检查 | `python -m ruff check <paths>` |
| Ruff 格式检查 | `python -m ruff format --check <paths>` |
| Harness 运行契约 | 运行摘要包含 `run_id`、`task_id`、`as_of_commit`、`version`、策略摘要和 `replayable` |
| Harness 自评 | 运行 Harness eval fixture，输出数据集版本、评估器版本、阈值、失败分类和与上一基线差异 |
| Harness 中文治理（P0） | `python -B backend/scripts/check_chinese_governance.py --summary`；权威状态、责任、阻塞、证据、交接和高风险用户可见路径有中文说明；机器字段保留稳定 ASCII；无裸机器状态码和关键模板缺字段；六维覆盖率为 1.0 |

______________________________________________________________________

## 按变更类型选择

| 变更类型 | 最低验证 | 加强验证 |
|---|---|---|
| `app/api/` 路由 | `python -m pytest tests/api -q --no-cov` | `python scripts/check_project.py` |
| `app/service/` 业务逻辑 | 对应 `tests/service` 文件 | 上线候选收口时执行一次全量 `python -m pytest tests/ -q`，并记录耗时 |
| `app/repository/` 数据访问 | 对应 `tests/repository` 文件 | migration/preflight 相关测试 |
| `app/models/` 模型 | 相关 service/repository 测试 | `python scripts/check_project.py` |
| 数据库迁移 | `python -m pytest tests/migrations tests/scripts/test_apply_migrations.py -q --no-cov` | dry-run + JSON 报告 |
| 客户正式迁移 | `python -m pytest tests/scripts/test_import_youzan_customers.py tests/scripts/test_audit_youzan_customer_migration.py tests/scripts/test_verify_youzan_customer_import.py -q --no-cov` | 审计报告 + dry-run 报告 + apply 后报告 + 核对报告 |
| 生产预检 | `python -m pytest tests/scripts/test_preflight_production.py tests/scripts/test_check_preflight_business_contracts.py -q --no-cov` | `python scripts/preflight_production.py --json --output "reports/preflight-before-{timestamp}.json"` 后运行 `python scripts/check_preflight_business_contracts.py "<报告路径>" --summary`，报告需包含 `business_contracts.static_checks` 和七类业务合约状态明细 |
| 冒烟脚本 | `python -m pytest tests/scripts/test_smoke_test.py -q --no-cov` | 本地服务启动后跑 smoke |
| 知识种子 | `python -m pytest tests/scripts/test_seed_baseline_knowledge.py -q --no-cov` | dry-run + apply 后报告 |
| 向量重建 | `python -m pytest tests/scripts/test_rebuild_embeddings.py -q --no-cov` | dry-run + apply 后报告 |
| RAG/检索 | `python -m pytest tests/service/test_knowledge_retriever.py tests/service/test_retrieval_fusion.py -q --no-cov` | `python scripts/eval_retrieval.py` |
| LLM 对话循环 | 相关 `tests/service/test_chat*.py` | 关键链路脚本或手工对话验收 |
| 转人工 | `tests/service/test_transfer_*` | 企微相关测试和 smoke |
| 后台前端 | 对应前端 lint/build/test | `/ready` 和 smoke 校验 dist |
| 文档 | `Test-Path` + `Select-String` 链接/关键词检查 | LOGBOOK 和进度清单同步检查 |
| Harness 文档 | `Test-Path docs/harness-engineering/...` | 检查无未完成占位 |
| Harness 脚本 | `python -B -m pytest backend/tests/scripts/test_harness_snapshot.py backend/tests/scripts/test_check_mistake_ledger.py backend/tests/scripts/test_check_evidence_index.py backend/tests/scripts/test_check_chinese_governance.py backend/tests/scripts/test_harness_policy.py backend/tests/scripts/test_harness_run_manifest.py backend/tests/scripts/test_harness_p0_gate.py -q --no-cov` | `python -B backend/scripts/harness_p0_gate.py --summary --json-out backend/reports/harness/p0-gate.json` + `pre-commit run --all-files` |
| 中文治理六维回归 | `python -B -m pytest backend/tests/scripts/test_check_chinese_governance.py -q --no-cov` | 对模型缺维度、协作模板缺字段、英文界面文案和英文自然语言注释执行负向测试；报告同时核对 `coverage.dimension_ratio` |
| Harness P0 统一门禁 | `python -B backend/scripts/harness_p0_gate.py --summary` | 根级 CI `.github/workflows/harness-p0.yml` 在安装依赖前运行 `check_requirements_lock_alignment.py`，上传 `reports/harness/*.json`；失败时保留可用报告并按 `failure_class` 归因 |
| Harness workflow / CI 证据包 | `python -B -m pytest backend/tests/scripts/test_harness_workflow_contract.py backend/tests/scripts/test_build_harness_artifact_index.py backend/tests/scripts/test_harness_ci_summary.py -q --no-cov -p no:cacheprovider` | workflow YAML 可解析、上传路径 `backend/reports/harness/**` + `if-no-files-found: error`、artifact index 必需集合覆盖 `.run.json`、候选目录和 summary；`python -B backend/scripts/build_harness_artifact_index.py --report-dir backend/reports/harness --run-id <run_id> --summary` |
| 错误候选闭环 | `python -B -m pytest backend/tests/scripts/test_harness_failure_candidate.py backend/tests/scripts/test_review_failure_candidate.py backend/tests/scripts/test_check_mistake_ledger.py -q --no-cov -p no:cacheprovider` | `python -B backend/scripts/check_mistake_ledger.py`；accept 需重新核对新 `M-YYYYMMDD-NNN` 条目与 `fingerprint` 回链；候选生成/reject/defer 不得修改 `ERRORS.md` |
| 文件体量与职责治理 | `python -m pytest tests/scripts/test_check_file_sizes.py -q --no-cov` + `python scripts/check_file_sizes.py` | 对超线目标记录职责、变化原因、候选边界、测试成本和 `split_by_responsibility / keep_cohesive_with_review / defer_with_boundary_plan` 结论 |
| ADR / 证据索引 | `python scripts/check_evidence_index.py --summary` | 搜索 `trace_id`、`related_adr`、`evidence_type` 关键字段；证据条目不得缺必填字段、不得重复 ID |
| Harness 全面评审 | `Test-Path docs/harness-engineering/HARNESS-MATURITY-REVIEW-20260830.md` + 入口链接检查 | 评审报告、PROJECT-STATE、LOGBOOK、证据索引四者一致 |

______________________________________________________________________

## 生产同步最低证据

生产同步前后建议至少保留：

```powershell
python scripts/preflight_production.py --json --output reports/preflight-before-{timestamp}.json
python scripts/audit_youzan_customer_migration.py --json --output reports/youzan-customer-audit-{timestamp}.json
python scripts/import_youzan_customers.py --json --output reports/youzan-customer-import-dry-run-{timestamp}.json
python scripts/apply_migrations.py --json --output reports/migration-dry-run-{timestamp}.json
python scripts/seed_baseline_knowledge.py --json --output reports/baseline-seed-before-{timestamp}.json
python scripts/rebuild_embeddings.py --json --output reports/rebuild-embeddings-before-{timestamp}.json
python scripts/verify_youzan_customer_import.py --json --output reports/youzan-customer-import-verify-{timestamp}.json
python scripts/smoke_test.py --json --output reports/smoke-after-{timestamp}.json
```

如果执行写入型 `--apply`，必须额外保存 apply 后报告。

______________________________________________________________________

## 验证结果记录格式

```markdown
- `python -m pytest tests/scripts/test_preflight_production.py -q --no-cov` 通过
- `python scripts/preflight_production.py --json` 通过，报告显示 failed=0
- 未运行全量测试：本轮仅修改文档，无代码行为变更；已完成定向 Harness 门禁
- 全量测试耗时记录：`FULL_TEST_DURATION_SECONDS=<seconds>`，与最近基线比较后决定是否建立优化事项
```

没有运行的验证要明确写原因，不能写成“已验证”。

## Agent / Harness 评估收口格式

除通过数外，评估报告至少包含：

- `dataset_version`、`evaluator_version`、`thresholds`；
- `passed`、`failed`、`failure_class_counts`；
- `latency_ms`、`cost`、`tool_call_count`、`human_intervention_count`；
- 与上一基线的差异，以及是否存在“最终答案正确但过程越权/证据缺失”的幸运通过。
