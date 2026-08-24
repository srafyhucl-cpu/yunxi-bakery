# 客户机器人可观测合约

> trace_id: `20260706-customer-observability-contract`
> 状态：治理设计冻结；首版只补指标合约和静态验收，不改热路径、不改数据库 schema
> 日期：2026-07-06
> 适用范围：客户机器人、RAG 检索、工具调用、转人工、上下文预算、发布预检
> 关联文档：
> - [GitHub 参考项目借鉴与可实施计划](./github-reference-benchmark-and-implementation-plan.md)
> - [双机器人能力目录](./bot-capability-matrix.md)
> - [客户会话摘要设计](./customer-session-summary-design.md)
> - [客户长期记忆治理计划](./customer-memory-governance-plan.md)
> - [知识库治理兼容迁移计划](./knowledge-governance-migration-plan.md)

______________________________________________________________________

## 一、设计结论

客户机器人可观测的目标不是给模型更多自由，而是让客服链路的质量可以被复盘、被预检、被发布证据证明。

首版只冻结指标、事件字段和隐私边界：

| 范围 | 当前策略 | 禁止 |
|---|---|---|
| 客户机器人 | 记录 RAG、工具、转人工、兜底和上下文压力信号 | 指标不能驱动自动改写回复 |
| 员工助手 | 继续由能力合约、探针和 callback 证明行为 | 套用客户客服口径 |
| MiniApp | 后续单独记录页面接口和支付体验指标 | 在前端沉淀业务真相 |

本合约不引入 LangChain / LangGraph，不改变 `chat_ai_loop.py`、`knowledge_retriever.py`、`customer_memory.py` 或转人工主链路。

______________________________________________________________________

## 二、核心指标

客户机器人至少需要能从日志或报告中计算以下指标：

| 指标 | 说明 | 最小来源 |
|---|---|---|
| `knowledge_hit_rate` | 用户问题是否命中可用知识 | `knowledge_retrieval_logs`、RAG golden cases |
| `no_data_fallback_rate` | 因资料不足而兜底或转人工的比例 | fallback 事件、`handoff_reason` |
| `handoff_rate` | 客户会话转人工比例和原因分布 | transfer / handoff 记录 |
| `tool_success_rate` | 订单、商品、售后等受控工具调用成功比例 | tool 事件 |
| `context_pressure_rate` | 超出上下文预算、触发摘要或降级的比例 | `conversation_summaries`、token budget |
| `response_guardrail_rate` | 因知识不足、敏感信息或不确定事实触发保守回复的比例 | reply policy 事件 |

这些指标只用于运营复盘、知识库补齐和发布验收，不能作为订单、价格、库存、配送或售后承诺的事实来源。

______________________________________________________________________

## 三、事件字段

后续新增日志或报表时，事件至少应围绕以下字段组织；已有日志可分批映射，不要求一次性改表：

| 字段 | 说明 |
|---|---|
| `trace_id` | 单次请求、发布或验证链路追踪号 |
| `session_id` | 客户会话 ID |
| `channel_type` | 客户入口，例如 storefront、wecom_kf、youzan |
| `bot_type` | 固定为 customer_bot，避免和 employee_bot 混线 |
| `intent` | 产品咨询、售后、订单、闲聊、无法识别等分类 |
| `retrieval_status` | hit / no_match / filtered / error |
| `knowledge_doc_ids` | 命中的知识条目 ID 列表，不记录正文全文 |
| `tool_name` | 被调用的受控工具名称 |
| `tool_status` | success / failed / skipped |
| `handoff_reason` | 转人工原因 |
| `fallback_reason` | 兜底原因 |
| `context_budget_tokens` | 当前上下文预算估算 |
| `summary_used` | 是否使用会话摘要 |
| `latency_ms` | 关键步骤耗时 |

字段命名必须稳定，优先写入 Platform 后端或只读报告；MiniApp 只能上报页面和接口状态，不能自己推导业务结论。

______________________________________________________________________

## 四、隐私和敏感边界

客户机器人观测日志必须坚持最小可用原则：

- 不记录完整手机号。
- 不记录完整地址。
- 不记录完整订单号。
- 不记录完整交易号。
- 不记录密钥、Token、Cookie、企业微信回调签名或支付凭证。
- `knowledge_doc_ids` 可以记录 ID，知识正文、客户原话全文只能在有明确留存策略的会话消息中保存。
- 过敏原、特殊日期和客户偏好只允许引用已有长期记忆治理规则，不在观测日志中重复沉淀为新事实。
- 观测失败必须降级为空指标，不能阻断客服回复。

______________________________________________________________________

## 五、发布与复盘入口

当前可用入口：

- `scripts/check_customer_rag_golden_cases.py`：验证客户 RAG 行为样例。
- `scripts/eval_retrieval.py --fixture tests/fixtures/customer_rag_golden_cases.json`：评估检索质量。
- `scripts/report_knowledge_retrieval_logs.py`：生成知识命中趋势只读报告。
- `scripts/check_customer_long_context_summary_smoke.py`：验证长上下文摘要链路。
- `scripts/check_customer_memory_governance_plan.py`：冻结长期记忆边界。
- `scripts/preflight_production.py --json`：发布前输出业务合约状态。
- `scripts/check_preflight_business_contracts.py "<preflight-report.json>" --summary`：复核归档预检报告中的业务合约证据。

后续如果新增客户机器人仪表盘，必须优先消费这些可追溯来源，不直接从 prompt 文本或模型输出中猜测指标。

______________________________________________________________________

## 六、阶段边界

首版只做合约和静态验收：

- 不新增数据库迁移。
- 不改客户机器人热路径。
- 不改员工助手 planner、工具调用或确定性回复。
- 不把 LangChain / LangGraph 放入生产客服主链路。
- 观测字段不能沉淀为客户画像，也不能成为订单事实。

后续实现运行时观测时，应按小切片推进：

1. 先补只读报表或现有日志聚合。
2. 再补后台展示。
3. 最后再考虑新增专门事件表。

每一步都必须能通过静态合约、相关 pytest 和发布预检复核。

______________________________________________________________________

## 七、静态验收

本计划由 `scripts/check_customer_observability_contract.py` 验收，并接入 `scripts/check_project.py --skip-tests` 的业务合约检查。

静态验收必须覆盖：

- `knowledge_hit_rate`、`no_data_fallback_rate`、`handoff_rate`、`tool_success_rate`、`context_pressure_rate` 五类核心指标。
- `trace_id`、`session_id`、`channel_type`、`bot_type`、`intent`、`handoff_reason`、`fallback_reason` 等事件字段。
- RAG、工具调用、转人工、上下文预算和发布预检入口。
- 不记录完整手机号、完整地址、完整订单号、完整交易号、密钥、Token、Cookie。
- 指标不能驱动自动改写回复，观测字段不能沉淀为客户画像，也不能成为订单事实。

______________________________________________________________________

## 八、当前结论

客户机器人下一阶段最值得补的是可观测闭环，但正确顺序是先冻结指标和隐私边界，再逐步把已有 RAG、转人工、工具调用和上下文摘要证据聚合起来。当前切片只把这些边界固化为业务合约，不引入新框架、不改生产回复路径。
