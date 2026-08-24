# Verification Matrix

本文件用于减少 Vibe Coding 收口时的随机性。每次变更完成后，先按变更类型选择最低验证；涉及生产、数据、跨层调用或高风险路径时，再执行加强验证。

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

______________________________________________________________________

## 按变更类型选择

| 变更类型 | 最低验证 | 加强验证 |
|---|---|---|
| `app/api/` 路由 | `python -m pytest tests/api -q --no-cov` | `python scripts/check_project.py` |
| `app/service/` 业务逻辑 | 对应 `tests/service` 文件 | 全量 `python -m pytest tests/ -q` |
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
| Harness 脚本 | `python -m pytest tests/scripts/test_harness_snapshot.py tests/scripts/test_check_mistake_ledger.py tests/scripts/test_check_evidence_index.py -q --no-cov` | `python scripts/harness_snapshot.py --json` + `python scripts/check_mistake_ledger.py` + `python scripts/check_evidence_index.py --summary` + `pre-commit run check-mistake-ledger --all-files` + `pre-commit run check-evidence-index --all-files` |
| 文件体量与职责治理 | `python -m pytest tests/scripts/test_check_file_sizes.py -q --no-cov` + `python scripts/check_file_sizes.py` | 对超线目标记录职责、变化原因、候选边界、测试成本和 `split_by_responsibility / keep_cohesive_with_review / defer_with_boundary_plan` 结论 |
| ADR / 证据索引 | `python scripts/check_evidence_index.py --summary` | 搜索 `trace_id`、`related_adr`、`evidence_type` 关键字段；证据条目不得缺必填字段、不得重复 ID |

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
- 未运行全量测试：本轮仅修改文档，无代码行为变更
```

没有运行的验证要明确写原因，不能写成“已验证”。
