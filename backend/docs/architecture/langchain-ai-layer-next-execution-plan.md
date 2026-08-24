# LangChain AI 应用层下一阶段可执行计划书

> trace_id: `20260710-langchain-ai-layer-next-execution`
> 日期：2026-07-10
> 当前基线：`VERSION=0.105.10`
> 上游计划：`docs/architecture/langchain-ai-layer-production-enhancement-plan.md`
> 状态：待执行

## 一、目标

本计划接在 LangChain AI 应用层生产增强计划之后，目标不是继续堆框架覆盖率，而是把项目推进到更适合真实上线、长期维护和作品集展示的状态。

下一阶段的核心结果是：

```text
真实样本可准入、线上观测可灰度、RAG 可控增强、发布证据可复核、作品集可讲清。
```

衡量标准：

1. 没有真实数据时，所有 readiness 报告必须明确 `ready=false`，不得伪造成已完成。
2. 有真实脱敏输入后，strict gate 能阻断结构错误、脱敏不足、覆盖不足和来源证明不足。
3. LangSmith / RAG 灰度只能在合规、容量、回滚和效果证据齐全后开启。
4. 每个上线切片都有测试、ruff、release gate、生产 runtime gate 和 evidence index 记录。
5. 面试展示时能讲清 LangChain 负责什么、业务层负责什么、为什么这样分边界。

## 二、执行原则

1. 小切片推进，每个切片单独提交、推送、生产验证。
2. 默认不改变热路径；需要改变热路径时必须有 feature flag 和回滚命令。
3. 默认不访问真实业务数据库；需要真实样本时只读取仓库外的脱敏文件。
4. 默认不向 LangSmith 外发；打开外发前必须有人工合规确认和采样率限制。
5. `reports/*` 只做本地或生产证据归档，不强制入库。
6. 禁止为了让门禁通过而降低阈值、删除失败样本或伪造真实样本。

## 三、阶段总览

| 阶段 | 名称 | 主要价值 | 是否改热路径 | 是否需要真实输入 |
|---|---|---|---|---|
| E1 | 真实 replay 候选样本准入审计 | 给真实样本进入样本池前加最后一道门 | 否 | 可选 |
| E2 | 首批真实脱敏 replay 样本接入 | 让真实样本 strict gate 真正通过 | 否 | 是 |
| E3 | 真实 RAG shadow log 接入 | 用真实问题分布评估 planned-hybrid | 否 | 是 |
| E4 | LangSmith 小流量外发灰度 | 验证线上 trace 外发、容量和回滚 | 低风险 | 需要 key 与合规确认 |
| E5 | RAG planned-hybrid 受控灰度 | 把已证明不劣于 baseline 的模式进入小流量 | 是 | 建议有真实 shadow log |
| E6 | 事实敏感场景回放增强 | 用真实回复分布压测订单、售后、退款边界 | 否 | 是 |
| E7 | 发布证据一键收口 | 把生产 release evidence 收成固定报告包 | 否 | 否 |
| E8 | 作品集与面试材料升级 | 把工程证据转成可展示故事线 | 否 | 否 |

推荐顺序：

```text
E1 -> E2 -> E3 -> E4 -> E5 -> E6 -> E7 -> E8
```

如果短期拿不到真实样本，则执行：

```text
E1 -> E7 -> E8
```

并保持 E2 / E3 / E6 的 strict gate 失败为预期状态。

## 四、E1 真实 replay 候选样本准入审计

### 目标

新增一个候选样本包审计入口，在真实脱敏客服会话写入 replay pool manifest 之前，先检查结构、脱敏、覆盖和来源证明。

### 建议改动

新增：

- `scripts/audit_real_conversation_replay_candidate.py`
- `tests/scripts/test_audit_real_conversation_replay_candidate.py`

接入：

- `scripts/check_project.py`
- `scripts/check_langchain_ai_layer_production_plan.py`
- `docs/architecture/langchain-ai-layer-production-enhancement-plan.md`
- `docs/harness-engineering/core/evidence-index.md`
- `LOGBOOK.md`

### 行为契约

默认无输入时：

```text
status=passed
candidate_ready=false
missing_actions=["provide_redacted_real_replay_candidate_fixture"]
```

严格模式无输入时：

```text
status=failed
candidate_ready=false
```

有输入时必须检查：

1. fixture 可被 `check_real_conversation_replay.py` 通过。
2. coverage 可被 `check_real_conversation_replay_coverage.py` 通过。
3. `metadata.contains_sensitive_data=false`。
4. 来源不能是 `synthetic`、`schema_sample`、`contract_shape_only`。
5. CLI 必须显式提供：
   - `--source-type real_customer_conversation`
   - `--redaction-method`
   - `--redaction-reviewer`
   - `--redaction-reviewed-at`
   - `--raw-source-retention not_committed`
   - `--evidence-id`
6. 输出 manifest entry draft，但不直接修改 manifest。

### 验收命令

```powershell
python -m pytest tests\scripts\test_audit_real_conversation_replay_candidate.py tests\scripts\test_check_langchain_ai_layer_production_plan.py -q --no-cov
python -m ruff check scripts\audit_real_conversation_replay_candidate.py scripts\check_langchain_ai_layer_production_plan.py scripts\check_project.py tests\scripts\test_audit_real_conversation_replay_candidate.py tests\scripts\test_check_langchain_ai_layer_production_plan.py
python -m ruff format --check scripts\audit_real_conversation_replay_candidate.py scripts\check_langchain_ai_layer_production_plan.py scripts\check_project.py tests\scripts\test_audit_real_conversation_replay_candidate.py tests\scripts\test_check_langchain_ai_layer_production_plan.py
python scripts\audit_real_conversation_replay_candidate.py --summary
python scripts\audit_real_conversation_replay_candidate.py --require-fixture --summary
python scripts\check_langchain_ai_layer_production_plan.py --summary
python scripts\check_project.py --skip-tests
```

说明：`--require-fixture` 在没有真实候选 fixture 时失败是预期结果，不接入默认 `check_project.py`。

### 完成标准

1. 默认 readiness 通过但明确 `candidate_ready=false`。
2. strict mode 缺输入失败。
3. 合成样本不能被标记为真实候选。
4. 通过审计后只能生成 manifest draft，不能自动把真实样本写入仓库。

## 五、E2 首批真实脱敏 replay 样本接入

### 目标

由人工或授权流程提供仓库外真实客服会话，经过脱敏、审计和人工确认后，接入 replay pool，让真实样本 strict gate 首次通过。

### 输入要求

真实输入必须放在仓库外或 gitignored `reports/agent-eval/` 下，且不得提交原始客户会话。

最小覆盖建议：

| 场景 | 最小条数 |
|---|---:|
| 订单查询 | 5 |
| 退款 | 5 |
| 售后 | 5 |
| 库存 | 5 |
| 价格 | 5 |
| 转人工 | 5 |

### 执行步骤

1. 由人工导出原始客服会话到仓库外路径。
2. 运行脱敏导出器生成 replay fixture draft。
3. 运行 E1 候选审计。
4. 由人工复核脱敏结果。
5. 生成 manifest entry draft。
6. 人工确认后写入 replay pool manifest。
7. 运行 real replay、coverage、pool、intake readiness 和 release gate。

### 验收命令

```powershell
python scripts\export_real_conversation_replay_fixture.py --input <warehouse_path> --output reports\agent-eval\real-conversation-replay-draft.json --summary
python scripts\audit_real_conversation_replay_candidate.py --fixture reports\agent-eval\real-conversation-replay-draft.json --require-fixture --source-type real_customer_conversation --redaction-method manual --redaction-reviewer <reviewer> --redaction-reviewed-at 2026-07-10 --raw-source-retention not_committed --evidence-id <evidence_id> --summary
python scripts\prepare_real_conversation_replay_pool_entry.py --fixture reports\agent-eval\real-conversation-replay-draft.json --source-type real_customer_conversation --redaction-method manual --redaction-reviewer <reviewer> --redaction-reviewed-at 2026-07-10 --raw-source-retention not_committed --evidence-id <evidence_id> --summary
python scripts\check_real_conversation_replay.py --fixture reports\agent-eval\real-conversation-replay-draft.json --summary
python scripts\check_real_conversation_replay_coverage.py --fixture reports\agent-eval\real-conversation-replay-draft.json --summary
python scripts\check_real_conversation_replay_pool.py --require-real --summary
python scripts\check_real_conversation_replay_intake_readiness.py --require-real --summary
python scripts\check_langchain_ai_layer_release_gate.py --include-real-replay --include-real-replay-coverage --include-real-replay-pool --require-real-replay-pool --include-real-replay-intake-readiness --summary
```

### 完成标准

1. `real_sample_ready=true`。
2. `real_pool_ready=true`。
3. 原始客户会话没有入仓。
4. 真实样本 replay、coverage、pool、intake readiness 全部通过。
5. evidence index 记录来源证明、脱敏审核人、审核时间和报告路径。

## 六、E3 真实 RAG shadow log 接入

### 目标

把真实脱敏 RAG 检索日志接入 `report_rag_shadow_log_observability.py`，用真实问题分布评估 `planned-hybrid` 和 `planned-hybrid+rerank`。

### 输入要求

输入文件必须满足：

```json
{
  "metadata": {
    "source_type": "real_rag_shadow_log",
    "contains_sensitive_data": false
  },
  "records": [
    {
      "id": "stable-id",
      "query": "已脱敏用户问题",
      "baseline_top_keys": ["knowledge-key-1"],
      "group": "inventory"
    }
  ]
}
```

默认报告只输出 `query_hash`，不输出 query 原文。

### 验收命令

```powershell
python scripts\report_rag_shadow_log_observability.py --input <redacted_shadow_log.json> --require-input --summary
python scripts\report_rag_shadow_log_observability.py --input <redacted_shadow_log.json> --require-input --json-out reports\agent-eval\rag-shadow-log-real-latest.json
python scripts\report_rag_shadow_observability.py --summary
python scripts\check_langchain_ai_layer_release_gate.py --include-observability-evidence --include-production-runtime-capacity --summary
```

### 完成标准

1. `shadow_log_ready=true`。
2. `planned-hybrid` 在真实日志上不低于 baseline，或报告明确保持 shadow-only。
3. `planned-hybrid+rerank` 不达标时继续禁止热启。
4. 报告不包含手机号、地址、open_id、订单明文或 query 原文。

## 七、E4 LangSmith 小流量外发灰度

### 目标

在人工确认外发合规、生产 key 已注入、容量门禁通过后，打开极低采样率 LangSmith trace 外发，并验证可回滚。

### 前置条件

1. 人工确认 trace metadata 不含敏感明文。
2. 生产环境已注入 LangSmith API key 和 project。
3. `LANGCHAIN_TRACING_V2=true`。
4. 采样率不超过 `0.1`，首轮建议 `0.01`。
5. 回滚命令已经写入 enablement packet。

### 验收命令

```powershell
python scripts\check_langsmith_runtime_config.py --require-enabled --summary
python scripts\check_langsmith_production_rollout.py --require-enabled --external-export-approved --sample-rate 0.01 --summary
python scripts\build_langsmith_production_enablement_packet.py --sample-rate 0.01 --external-export-approved --summary
python scripts\check_langchain_ai_layer_capacity.py --include-production-runtime --summary
python scripts\check_langchain_ai_layer_release_gate.py --include-production-smoke --include-observability-evidence --include-production-runtime-capacity --summary
python scripts\check_langchain_production_observability_release.py --report reports\agent-eval\langchain-ai-layer-release-gate-with-production-observability-latest.json --summary
```

### 完成标准

1. LangSmith runtime config strict mode 通过。
2. rollout report 显示 `safe_to_enable=true`。
3. 生产容量门禁通过。
4. 生产 release evidence 记录 LangSmith 开启状态、采样率和回滚命令。
5. 若出现容量异常或外发异常，立即回滚到 tracing 关闭态。

## 八、E5 RAG planned-hybrid 受控灰度

### 目标

在离线 golden cases 和真实 shadow log 都证明 `planned-hybrid` 不低于 baseline 后，将 `RAG_RETRIEVAL_MODE=planned-hybrid` 进入小流量灰度。

### 前置条件

1. P19a 离线 shadow report 通过。
2. E3 真实 shadow log report 通过。
3. `planned-hybrid+rerank` 未达标前不得启用。
4. 有明确回滚方式：恢复 `RAG_RETRIEVAL_MODE=hybrid` 并重启服务。

### 验收命令

```powershell
python scripts\report_rag_shadow_observability.py --summary
python scripts\report_rag_shadow_log_observability.py --input <redacted_shadow_log.json> --require-input --summary
python scripts\report_retrieval_eval_matrix.py --db data\bot.db --fixture tests\fixtures\customer_rag_golden_cases.json --k 5
python scripts\check_langchain_ai_layer_capacity.py --include-production-runtime --summary
python scripts\check_langchain_ai_layer_release_gate.py --include-production-smoke --include-observability-evidence --include-production-runtime-capacity --summary
```

### 完成标准

1. 生产配置可观测到 `RAG_RETRIEVAL_MODE=planned-hybrid`。
2. 客户回复 eval 与 callback probe 不回退。
3. RAG shadow 指标不低于 baseline。
4. 出现召回下降、事实错误或容量异常时能在一条命令内回滚。

## 九、E6 事实敏感场景回放增强

### 目标

把真实脱敏会话或生产 shadow replies 接入现有客户回复回放检查，重点覆盖订单、退款、售后、库存、价格和转人工。

### 执行步骤

1. 从 E2 真实 replay fixture 或生产 shadow replies 生成 replies JSON。
2. 运行 forbidden reply patterns 检查。
3. 运行 agent eval 扩展模式。
4. 汇总每类敏感场景的失败原因。
5. 如果出现不当承诺或事实编造，先补 eval，再修回复策略。

### 验收命令

```powershell
python scripts\check_customer_reply_replay.py --replies-json <redacted_replies.json> --summary
python scripts\report_agent_eval.py --latest --include-reply-replay --json-out reports\agent-eval\latest-with-reply-replay.json
python scripts\check_langchain_ai_layer_release_gate.py --include-real-replay --include-real-replay-coverage --include-observability-evidence --summary
```

### 完成标准

1. 真实回复回放不包含 forbidden patterns。
2. 每类事实敏感场景都有真实脱敏样本覆盖。
3. 失败报告能定位到 case、scenario、pattern 和实际输出摘要。

## 十、E7 发布证据一键收口

### 目标

把目前分散的 release gate、runtime gate、capacity gate、observability release checker 和 evidence index 检查收成一个固定发布收口命令。

### 建议改动

新增：

- `scripts/build_langchain_release_evidence_packet.py`
- `tests/scripts/test_build_langchain_release_evidence_packet.py`

该脚本只编排已有门禁，不降低任何门禁标准。

### 输出内容

报告建议包含：

1. local commit / origin commit / server commit / production commit。
2. `VERSION` 与 `/health`、`/ready` runtime version。
3. release gate summary。
4. production smoke / callback summary。
5. observability evidence summary。
6. capacity runtime summary。
7. LangSmith 状态。
8. RAG mode 与 RAG shadow 结论。
9. real replay readiness。
10. rollback commands。

### 验收命令

```powershell
python -m pytest tests\scripts\test_build_langchain_release_evidence_packet.py -q --no-cov
python -m ruff check scripts\build_langchain_release_evidence_packet.py tests\scripts\test_build_langchain_release_evidence_packet.py
python -m ruff format --check scripts\build_langchain_release_evidence_packet.py tests\scripts\test_build_langchain_release_evidence_packet.py
python scripts\build_langchain_release_evidence_packet.py --summary
python scripts\check_evidence_index.py --summary
python scripts\check_project.py --skip-tests
```

### 完成标准

1. 一条命令能生成上线证据包。
2. 报告中任何关键门禁失败都会让总状态失败。
3. 报告不包含敏感明文。
4. evidence index 可追溯到该证据包。

## 十一、E8 作品集与面试材料升级

### 目标

把 LangChain / LangGraph 迁移和生产增强成果整理为面试可讲的材料：架构边界、演进路线、核心证据、工程取舍和风险治理。

### 建议改动

更新：

- `docs/architecture/langchain-ai-layer-portfolio.md`
- `README.md`
- `docs/README.md`

可新增：

- `docs/architecture/langchain-ai-layer-interview-brief.md`

### 内容结构

1. 一句话项目定位。
2. 为什么从自研链路迁到 LangChain / LangGraph。
3. LangChain 接管范围：
   - Agent graph
   - model adapter
   - tools
   - retriever adapter
   - structured output
   - tracing / eval
4. LangChain 不接管范围：
   - 订单事实
   - 商品库存
   - 客户主档
   - 售后退款规则
   - SQLite repository
5. 关键工程亮点：
   - 双机器人 LangGraph 编排
   - RAG planned-hybrid shadow compare
   - 事实敏感场景 eval
   - 真实脱敏 replay 门禁
   - LangSmith 可选外发与容量门禁
   - 生产 release evidence
6. 代码与命令证据索引。
7. 面试问答版本：
   - 为什么不用 LlamaIndex
   - 为什么不是全项目 LangChain
   - 为什么业务数据库不交给 Agent
   - 如何保证客服回复可控
   - 如何评估 RAG 是否真的变好

### 验收命令

```powershell
python scripts\check_langchain_ai_layer_production_plan.py --summary
python scripts\check_evidence_index.py --summary
python scripts\check_project.py --skip-tests
```

### 完成标准

1. 作品集文档能从 README 追溯到代码、测试和生产证据。
2. 面试材料不是口号，每个亮点都有文件路径和命令证据。
3. 明确说明当前未完成项：真实样本接入、LangSmith 外发灰度、RAG planned-hybrid 生产灰度。

## 十二、提交与上线节奏

每个涉及版本变化的切片按以下顺序收口：

```powershell
git status -sb
python -m pytest <targeted_tests> -q --no-cov
python -m ruff check <changed_files>
python -m ruff format --check <changed_files>
python scripts\check_project.py --skip-tests
git diff --check
git add <changed_files>
$env:SKIP_VERSION_BUMP='1'; git commit -m "<type>: <summary>"
git -c http.version=HTTP/1.1 push origin master
git push server master
ssh -o BatchMode=yes -o ConnectTimeout=8 root@47.94.102.250 "cd /opt/yunxibakebot && git rev-parse HEAD && cat VERSION && git status --short && systemctl is-active yunxibakebot"
ssh -o BatchMode=yes -o ConnectTimeout=8 root@47.94.102.250 "systemctl restart yunxibakebot && systemctl is-active yunxibakebot"
python scripts\check_langchain_production_runtime_version.py --summary
python scripts\check_langchain_ai_layer_release_gate.py --include-production-smoke --include-observability-evidence --include-production-runtime-capacity --json-out reports\agent-eval\langchain-ai-layer-release-gate-with-production-observability-latest.json --summary
python scripts\check_langchain_production_observability_release.py --report reports\agent-eval\langchain-ai-layer-release-gate-with-production-observability-latest.json --summary
```

生产验证完成后追加：

1. `LOGBOOK.md`
2. `docs/harness-engineering/core/evidence-index.md`
3. `项目进度与配置清单.md`

## 十三、下一步建议

立即执行 E1。

原因：

1. E1 不需要真实客户数据，可以马上推进。
2. E1 能把 P17b 真实样本接入前的最后一段人工判断变成机器审计。
3. E1 完成后，如果用户或同事提供真实脱敏样本，可以直接进入 E2；如果短期没有样本，也不会误报真实样本已经准备好。

E1 完成后，根据外部条件选择：

```text
有真实客服样本 -> E2
有真实 RAG 检索日志 -> E3
有 LangSmith key 和合规确认 -> E4
都没有 -> E7 + E8
```
