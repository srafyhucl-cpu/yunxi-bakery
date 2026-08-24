# LangChain AI 应用层后续增强可执行计划书

> trace_id: `20260709-langchain-ai-layer-production-enhancement`
> 日期：2026-07-10
> 状态：持续执行中（E0 已完成；E1 接入工具链已增强，等待仓库外真实脱敏输入；E2 交接工具链已增强，等待仓库外真实脱敏 RAG shadow log；E6a 证据清单已完成；P23a 外部证据交接汇总包已完成，P23b 已补交接动作分类，P23c 已补提交前自检摘要，P23d 已补计划层交接合同门禁，P23e 已补 readiness 真值汇总，P23f 已补 Markdown 可发送交接包，但 E6 完整态仍依赖 E1-E5）
> 上游计划：[LangChain AI 应用层生产增强计划书](./langchain-ai-layer-production-enhancement-plan.md)

## 一、目标

本计划承接 LangChain / LangGraph AI 应用层接管后的剩余增强工作，不再讨论是否迁移框架，而是把现有成果推进到可长期维护、可生产观测、可灰度、可作品集展示的状态。

核心目标：

```text
把当前 LangChain AI 应用层从“已接管、可运行”推进到“真实数据可评估、线上效果可观测、RAG 可灰度、发布证据可复盘”。
```

## 二、当前已收口基线

截至 `0.105.16`：

1. 客户机器人主编排已由 LangGraph 接管。
2. 员工助手主编排已由 LangGraph 接管。
3. LangChain tool、retriever adapter、structured planner fallback、trace 报告、release gate 和生产证据包已落地。
4. 生产 `/opt/yunxibakebot` 已部署 `0.105.16 / dbf3bb2`，严格发布证据包和严格作品集工程证据均通过，`packet_ready=true`、`verified_evidence_ready=true`。
5. 真实脱敏样本仍未接入，`candidate_ready=false`、`real_sample_ready=false` 仍是正确状态。
6. LangSmith 生产外发仍未启用，`langsmith_enabled=false` 仍是正确状态。
7. RAG 生产默认模式仍为 `hybrid`；`planned-hybrid` 只能作为受控灰度候选，`planned-hybrid+rerank` 继续 shadow-only。

## 三、执行原则

1. LangChain / LangGraph 继续负责模型调用、工具绑定、Agent 编排、retriever adapter、structured output、trace 和 eval。
2. 业务事实继续由 service / repository / models 管理，不让 LangChain 直接接管订单、库存、退款、客户主档或知识发布状态。
3. 所有真实客户样本必须先脱敏、审核、证明来源，不能用合成样本冒充真实样本。
4. 所有生产灰度必须先有只读证据，再有小流量开关，最后才允许扩大。
5. 所有发布收口必须能通过 LOGBOOK、evidence index、release gate JSON 和证据包追溯。

## 四、阶段 E0：P22a 生产证据基线复核

### 目标

确认当前 `0.105.16` 生产发布证据已经收口，后续增强从干净基线开始。

### 当前状态

已完成：

```text
production commit=dbf3bb2adc049da7cd931c42216dd8a040a8e639
runtime VERSION=0.105.16
service=active
packet_ready=true
verified_evidence_ready=true
```

### 复核命令

```powershell
git status -sb
git rev-parse master origin/master server/master
python scripts\check_langchain_production_runtime_version.py --summary
python scripts\build_langchain_release_evidence_packet.py --require-production-evidence --summary
python scripts\check_evidence_index.py --summary
```

### 完成标准

1. 本地、`origin/master`、`server/master` 指向同一 commit。
2. 生产 runtime version 等于本地 `VERSION`。
3. 严格发布证据包通过，`packet_ready=true`。
4. evidence index 结构检查通过。

## 五、阶段 E1：P17b 首批真实脱敏样本接入

### 目标

把真实客服会话从仓库外脱敏输入推进到 replay candidate，通过准入审计后进入真实样本池。

### 前置条件

1. 必须有仓库外真实客服记录持有人提供的脱敏 JSON / JSONL。
2. 每条样本必须声明来源类型、脱敏方法、审核人、审核时间、原始来源不入仓。
3. 不允许提交原始客户消息、手机号、地址、open_id、完整订单号。

### 当前进度

1. `scripts\build_real_conversation_replay_intake_packet.py` 已输出可填写的仓库外交接模板，模板字段与现有导出器的扁平输入合同一致。
2. 操作包命令链已显式包含真实来源标识、候选审计 JSON、真实来源类型和原始来源不入仓声明。
3. `scripts\prepare_real_conversation_replay_pool_entry.py` CLI 已暴露 `--source-type` 和 `--raw-source-retention`，命令行声明会进入 manifest entry 草稿并受断言保护。
4. 当前仍没有仓库外真实脱敏输入，因此 E1 尚未完成，`candidate_ready=false`、`real_sample_ready=false` 仍是正确状态。
5. 接入模板与命令链增强已部署到生产 `0.105.14`；runtime、加强 release gate、P13b 复核和严格证据包均通过，但这不改变真实样本 readiness。

### 输入合同

仓库外交接 JSON / JSONL 使用以下合同；`handoff_declaration` 用于人工审核和后续命令参数，导出器消费 `records`：

```text
handoff_declaration.source_type=real_customer_conversation
handoff_declaration.contains_sensitive_data=false
handoff_declaration.redaction_method
handoff_declaration.redaction_reviewer
handoff_declaration.redaction_reviewed_at
handoff_declaration.raw_source_retention=not_committed
handoff_declaration.evidence_id
records[].golden_case_id
records[].user_message
records[].final_reply
records[].case_id                  # 可选
records[].source                   # 可选
records[].group                    # 可选
records[].intent                   # 可选
```

导出后的 replay fixture 使用现有 checker 合同：

```text
metadata.source
metadata.redaction
metadata.contains_sensitive_data=false
cases[].case_id
cases[].golden_case_id
cases[].user_message
cases[].final_reply
cases[].source
cases[].group
cases[].intent
```

### 执行步骤

1. 使用 `scripts\build_real_conversation_replay_intake_packet.py --json` 生成并检查外部接入模板与命令链。
2. 在仓库外按 `handoff_template` 准备已脱敏输入，不把原始客服记录写入仓库。
3. 运行导出器生成 gitignored replay fixture，并通过 replay contract 与 coverage 检查。
4. 运行候选准入审计并保存 JSON，只生成报告和 manifest entry draft，不直接改 manifest。
5. 人工复核候选审计报告和 entry draft。
6. 通过后再由人工把 entry 写入真实 replay pool manifest。
7. 跑 real replay、coverage、pool、intake readiness 和聚合 eval。

### 验收命令

```powershell
python scripts\build_real_conversation_replay_intake_packet.py --summary
python scripts\export_real_conversation_replay_fixture.py --input <仓库外已脱敏输入路径> --source <真实脱敏来源标识> --output <redacted-fixture-path> --summary
python scripts\check_real_conversation_replay.py --fixture <redacted-fixture-path> --summary
python scripts\check_real_conversation_replay_coverage.py --fixture <redacted-fixture-path> --summary
python scripts\audit_real_conversation_replay_candidate.py --fixture <redacted-fixture-path> --require-fixture --source-type real_customer_conversation --redaction-method <脱敏方法> --redaction-reviewer <审核人> --redaction-reviewed-at <YYYY-MM-DD> --raw-source-retention not_committed --evidence-id <证据ID> --json-out reports\agent-eval\real-replay-candidate-audit.json --summary
python scripts\prepare_real_conversation_replay_pool_entry.py --fixture <redacted-fixture-path> --name <样本池条目名称> --evidence-id <证据ID> --redaction-method <脱敏方法> --redaction-reviewer <审核人> --redaction-reviewed-at <YYYY-MM-DD> --source-type real_customer_conversation --raw-source-retention not_committed --json-out reports\agent-eval\real-replay-pool-entry-draft.json --summary
python scripts\check_real_conversation_replay_pool.py --manifest <真实样本池manifest路径> --require-real --summary
python scripts\check_real_conversation_replay_intake_readiness.py --manifest <真实样本池manifest路径> --require-real --summary
python scripts\report_agent_eval.py --latest --include-real-replay --real-replay-fixture <redacted-fixture-path> --summary
```

### 完成标准

1. `candidate_ready=true` 只在真实脱敏候选输入存在且审计通过后出现。
2. `real_sample_ready=true` 只在真实样本池 manifest 满足准入要求后出现。
3. eval 报告能展示真实 replay 样本数量、覆盖场景和失败定位。
4. LOGBOOK 和 evidence index 记录真实样本只含脱敏数据，不含敏感原文。

### 回滚策略

若发现样本来源或脱敏证明不完整：

1. 不写入真实样本池 manifest。
2. 保持 `candidate_ready=false` 或 `real_sample_ready=false`。
3. 只保留审计失败摘要，不提交敏感样本内容。

## 六、阶段 E2：真实 RAG Shadow Log 接入

### 目标

用真实脱敏用户检索日志评估 `hybrid`、`planned-hybrid`、`planned-hybrid+rerank` 的线上候选差异，避免只靠 golden cases 决策。

### 前置条件

1. 仓库外提供脱敏 RAG shadow log。
2. 默认不输出 query 原文。
3. `metadata.contains_sensitive_data=false` 必须为真。

### 当前进度

1. `scripts\build_rag_shadow_log_intake_packet.py` 已提供仓库外交接模板、必填字段、脱敏要求、提交前自检清单和可执行命令链。
2. `scripts\report_rag_shadow_log_observability.py` 的严格输入合同已要求真实来源类型、脱敏方法、审核人、ISO 审核日期、原始来源不入仓和 evidence ID，并机械拦截 query 中明显的手机号、长数字和 open_id 形态。
3. 交接模板中的审核人和 evidence ID 可由命令参数预填，脱敏方法与审核日期保留为必须人工填写的字段。
4. 提交前自检清单要求外部日志持有人/脱敏审核人/仓库维护者确认真实来源、原始日志不入仓、query 脱敏、metadata 证明字段和 evidence ID 登记。
5. 当前仍没有仓库外真实脱敏日志，因此 `shadow_log_ready=false`，E2 尚未完成。

### 输入合同

```text
metadata.source_type
metadata.contains_sensitive_data
metadata.redaction_method
metadata.redaction_reviewer
metadata.redaction_reviewed_at
metadata.raw_source_retention
metadata.evidence_id
records[].id
records[].query
records[].baseline_top_keys
records[].group
```

### 执行步骤

1. 运行交接包生成器，向日志持有人提供可填写模板和脱敏声明。
2. 用默认模式确认当前没有真实输入时仍明确 `shadow_log_ready=false`。
3. 在仓库外完成 query 脱敏和人工审核，原始生产日志不得入仓。
4. 接入仓库外脱敏 shadow log，并运行严格模式复算 planned / rerank 候选差异。
5. 输出按 group 的 changed cases、recall delta、排序差异。
6. 给出是否允许 E3 灰度的机器结论。

### 验收命令

```powershell
python scripts\build_rag_shadow_log_intake_packet.py --summary
python scripts\report_rag_shadow_log_observability.py --summary
python scripts\report_rag_shadow_log_observability.py --input <redacted-shadow-log-path> --require-input --summary
python scripts\report_rag_shadow_log_observability.py --input <redacted-shadow-log-path> --require-input --json-out reports\retrieval-shadow\rag-shadow-log-latest.json
python scripts\check_langchain_ai_layer_production_plan.py --summary
```

### 完成标准

1. 严格模式在真实脱敏输入存在时通过。
2. 报告默认只输出 `query_hash`，不输出 query 原文。
3. `planned-hybrid` 不低于 baseline 时才可进入 E3。
4. `planned-hybrid+rerank` 若 recall 仍低于 baseline，继续 shadow-only。
5. `source_type=real_customer_rag_shadow_log`、脱敏审核字段、`raw_source_retention=not_committed` 和 evidence ID 必须齐全。

## 七、阶段 E3：RAG planned-hybrid 小流量灰度

### 目标

在真实 shadow 证据支持下，把 `planned-hybrid` 从候选路径推进到受控热路径灰度。

### 前置条件

1. E2 真实 shadow log 证明 `planned-hybrid` 不低于 baseline。
2. `planned-hybrid+rerank` 未达标前不得热启。
3. 生产默认仍保持 `hybrid`，灰度必须有显式环境变量或配置变更。

### 执行步骤

1. 确认当前生产 RAG 模式为 `hybrid`。
2. 准备灰度配置 `RAG_RETRIEVAL_MODE=planned-hybrid`。
3. 先在本地和 staging 等价环境跑 release gate。
4. 生产启用小流量后跑 runtime、capacity、callback、客户 RAG smoke。
5. 观察真实 shadow log 和用户回复风险。
6. 指标下降时立即回滚到 `hybrid`。

### 验收命令

```powershell
python scripts\report_retrieval_eval_matrix.py --db data\bot.db --fixture tests\fixtures\customer_rag_golden_cases.json --k 5
python scripts\report_rag_shadow_observability.py --summary
python scripts\check_langchain_ai_layer_capacity.py --include-production-runtime --summary
python scripts\check_langchain_ai_layer_release_gate.py --include-production-smoke --include-observability-evidence --include-production-runtime-capacity --summary
python scripts\build_langchain_release_evidence_packet.py --require-production-evidence --summary
```

### 完成标准

1. 生产灰度前后都有 release evidence。
2. `planned-hybrid` 灰度期间无 release gate 失败。
3. 回复回放、事实敏感断言和 callback probe 不回退。
4. 回滚命令写入 LOGBOOK 或 evidence index。

## 八、阶段 E4：LangSmith 生产小流量外发

### 目标

在合规、脱敏和容量可控的前提下，让 LangChain trace 小流量进入 LangSmith。

### 前置条件

1. 人工确认允许向 LangSmith 外发脱敏 metadata。
2. API key 不入仓，不打印。
3. 初始采样率建议 `0.01` 到 `0.05`。
4. 缺少 key 或配置错误时主流程必须降级，不影响回复。

### 执行步骤

1. 运行 LangSmith runtime config 检查。
2. 生成生产启用操作包。
3. 人工确认外发合规。
4. 注入生产环境变量。
5. 重启服务。
6. 跑容量门禁和 release gate。
7. 验证 LangSmith 项目中出现脱敏 trace。
8. 若延迟、内存或错误率升高，关闭 tracing。

### 验收命令

```powershell
python scripts\check_langsmith_runtime_config.py --summary
python scripts\check_langsmith_production_rollout.py --summary
python scripts\build_langsmith_production_enablement_packet.py --summary
python scripts\check_langchain_ai_layer_capacity.py --include-production-runtime --summary
python scripts\check_langchain_ai_layer_release_gate.py --include-production-smoke --include-observability-evidence --include-production-runtime-capacity --summary
```

### 完成标准

1. `langsmith_enabled=true` 只在人工合规确认和生产配置完成后出现。
2. trace metadata 不含敏感字段。
3. 生产容量门禁通过。
4. 关闭 LangSmith 后主流程仍正常。

## 九、阶段 E5：事实敏感场景真实样本强化

### 目标

把订单、售后、退款、库存、价格、转人工等高风险场景从合成 eval 推进到真实脱敏 replay 覆盖。

### 执行步骤

1. 基于 E1 的真实 replay pool 按场景统计覆盖。
2. 每类事实敏感场景至少接入 5 条真实脱敏样本。
3. 对每条样本声明必须出现事实、禁止出现内容和允许转人工条件。
4. 跑 real replay coverage 和 forbidden reply patterns。
5. 将失败 case 输出为可复现命令。

### 验收命令

```powershell
python scripts\check_real_conversation_replay_coverage.py --fixture <redacted-fixture-path> --summary
python scripts\report_agent_eval.py --latest --include-real-replay --include-reply-replay --summary
python scripts\check_langchain_ai_layer_release_gate.py --include-real-replay --include-real-replay-coverage --summary
```

### 完成标准

1. order、refund、after_sales、inventory、price、human_transfer 每类至少 5 条。
2. 禁止回复模式检查通过。
3. 失败能定位到 case id、场景、断言和实际输出摘要。

## 十、阶段 E6：作品集证据包升级

### 目标

把工程成果整理成能在面试中讲清楚的证据链，而不是只说“用了 LangChain”。

### 当前进度

1. P5a 已有作品集说明、Mermaid 架构图、代码路径、Agent Eval、RAG 矩阵和事实敏感治理证据。
2. E6a 新增 `scripts\build_langchain_portfolio_evidence_packet.py`，统一聚合当前版本 Agent Eval、RAG shadow、trace、严格生产 release packet 和 E1-E5 readiness。
3. 清单分别输出 `verified_evidence_ready`、`external_evidence_complete` 和 `portfolio_complete`；默认生成清单不会把缺失外部证据算作失败，但严格 `--require-complete` 会阻断。
4. E4 不能只凭 LangSmith key 或 tracing 开关完成；还必须有同版本、人工外发批准、受控采样率和实际 trace 验证报告。
5. E5 必须使用真实样本池对应的事实敏感 coverage 报告；`tests/fixtures` 下的合成覆盖样例不能让该阶段 ready。
6. `scripts\build_langchain_external_evidence_handoff_packet.py` 已把 E1 真实 replay 接入包、E2 真实 RAG shadow log 接入包和 E6 作品集缺口聚合成统一交接汇总，输出 `required_external_inputs`、`action_groups`、`action_group_details`、可填写模板、P17b/P19c 提交前自检清单、顶层 `pre_submission_checklist_summary`、`readiness_truth`、命令链、摘要动作计数和边界声明，并可通过 `--markdown-out` 生成 `LangChain 外部证据交接包` Markdown 文档，供人工/仓库外记录持有人按一份可发送清单准备真实脱敏输入，并先完成对应提交前自检；生产增强计划静态门禁已要求这些交接合同字段持续存在。
7. 当前工程证据可复核，E1-E5 外部证据仍未完成，因此 `verified_evidence_ready=true`、`external_evidence_complete=false`、`portfolio_complete=false` 是正确状态。

### 输出物

1. 一页架构图。
2. LangChain / LangGraph 接管边界。
3. Modular RAG 说明。
4. RAG shadow 和灰度证据。
5. Agent Eval 和真实 replay 证据。
6. LangSmith / trace 观测证据。
7. 生产 release evidence packet。
8. 关键取舍说明：为什么 AI 应用层接管，而业务领域层不交给 LangChain。

### 验收命令

```powershell
python scripts\report_agent_eval.py --latest --json-out reports\agent-eval\portfolio-latest.json
python scripts\report_rag_shadow_observability.py --summary
python scripts\report_langchain_observability_evidence.py --summary
python scripts\build_langchain_external_evidence_handoff_packet.py --summary
python scripts\build_langchain_external_evidence_handoff_packet.py --markdown-out reports\harness\langchain-external-evidence-handoff.md --summary
python scripts\build_langchain_release_evidence_packet.py --require-production-evidence --summary
python scripts\build_langchain_portfolio_evidence_packet.py --require-verified-evidence --summary
python scripts\build_langchain_portfolio_evidence_packet.py --require-complete --summary
python scripts\check_project.py --skip-tests
```

### 完成标准

1. 每个作品集亮点都能对应代码路径。
2. 每个效果结论都有命令或报告证据。
3. 文档能解释长期维护边界，而不是把 LangChain 当作业务框架。
4. `portfolio_complete=true` 只能在 E1-E5 的真实外部证据全部完成后出现；当前 `--require-complete` 预期失败。

## 十一、推荐执行顺序

```text
E0 P22a 生产证据基线复核
  -> E1 P17b 首批真实脱敏样本接入
  -> E2 真实 RAG shadow log 接入
  -> E3 RAG planned-hybrid 小流量灰度
  -> E4 LangSmith 生产小流量外发
  -> E5 事实敏感场景真实样本强化
  -> E6 作品集证据包升级
```

## 十二、暂停条件

遇到以下情况必须暂停，不得伪造完成：

1. 没有真实脱敏样本，却试图让 `real_sample_ready=true`。
2. 没有真实 RAG shadow log，却试图打开 RAG 灰度。
3. 没有人工合规确认，却试图开启 LangSmith 生产外发。
4. release gate、capacity gate、callback probe 任一失败。
5. 发现样本、trace 或报告包含敏感原文。

## 十三、下一步

立即下一步应执行 E1：

```text
接入首批真实脱敏客服会话 replay 样本。
```

如果暂时拿不到真实样本，则可以先执行 E2 的输入包准备和严格门禁复核，但不能把 readiness 状态改为 ready。
