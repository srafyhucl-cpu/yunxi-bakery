# LangChain 生态全面接管 AI 应用层计划书

> trace_id: `20260709-langchain-ecosystem-ai-layer-takeover`
> 日期：2026-07-09
> 状态：计划冻结，待分阶段执行
> 适用范围：客户机器人、企微员工助手、RAG、Prompt 上下文、工具调用、短期记忆、观测、评估、Agent 工程展示
> 前置计划：[LangChain / LangGraph 双机器人迁移执行计划](./langchain-langgraph-migration-plan.md)

## 一、结论

本计划建议继续推进，但目标必须定义准确：

```text
不是 LangChain 全面接管整个项目。
是 LangChain / LangGraph / LangSmith 生态全面接管 AI 应用层。
```

项目的业务真相仍由现有领域服务负责：

```text
api -> service -> repository -> models
```

LangChain 生态接管的范围是：

```text
Agent 编排
模型调用
工具绑定
Retriever 适配
Prompt 组件
Memory / Checkpoint
Tracing / Observability
Eval / Golden Cases
```

最终架构目标：

```text
Channel API
  -> Bot Application Service
    -> LangGraph Agent Workflow
      -> LangChain Chat Model
      -> LangChain Tools
      -> LangChain Retriever Adapter
      -> LangGraph Memory / Checkpoint Adapter
      -> Trace / Eval Hooks
        -> Existing Domain Services
          -> Existing Repositories
            -> SQLite / Youzan / WeCom / Admin APIs
```

## 二、当前基线

截至 2026-07-09，本项目已经完成第一轮 LangChain / LangGraph 接入：

| 能力 | 当前状态 | 证据路径 |
|---|---|---|
| 依赖 | 已锁定 `langchain==1.3.11`、`langgraph==1.2.8`、`langchain-openai==1.3.3`、`langsmith==0.9.8` | `requirements.in`、`requirements.txt` |
| 客户机器人编排 | 已由 LangGraph 接管主编排入口 | `app/service/agents/customer/graph.py` |
| 员工助手编排 | 已由 LangGraph 接管主编排入口 | `app/service/agents/employee/graph.py` |
| 客户工具 | 已注册为 LangChain `StructuredTool` | `app/service/agents/tools/customer.py` |
| 员工工具 | 已注册为 LangChain `StructuredTool` | `app/service/agents/tools/employee.py` |
| 旧手写客户工具循环 | 已退场 | `chat_llm.py`、`chat_tools.py`、`llm/function_defs.py`、`llm/functions.py` 已删除 |
| RAG | 仍由项目内 `KnowledgeRetriever` / `EmbeddingSearcher` 承载 | `app/service/knowledge_retriever.py`、`app/service/embedding_search.py` |
| 客户模型请求 | 仍主要走项目内 `request_llm_choice()` | `app/service/chat_llm_request.py` |
| Prompt 上下文 | 仍由项目内函数拼装 messages | `app/service/chat_context.py`、`app/service/llm/prompt.py` |
| 会话摘要 | 已有项目内只读注入和回复后异步生成 | `app/service/conversation_summary_*` |
| Trace | 当前为本地 `trace_events` / `timing` / smoke 报告 | `app/service/agents/*/nodes.py`、`scripts/check_*` |

当前结论：

- 第一轮迁移已经证明框架可以进入双机器人主路径。
- 现在的短板不是“是否用了 LangChain”，而是没有把 LangChain 生态的模型抽象、Retriever、Memory、Tracing 和 Eval 串成统一工程面。
- 第二轮推进应避免重写业务层，集中改造 AI 应用层。

## 三、设计原则

### 3.1 接管边界

LangChain 生态应该接管：

1. 模型请求封装。
2. 工具绑定和工具选择约束。
3. RAG retriever 标准接口。
4. Prompt 组件和 message assembly。
5. Graph state、checkpoint、短期记忆适配。
6. 节点级 tracing、评估样本和回放。
7. Agent 运行报告和求职展示材料。

LangChain 生态不应该接管：

1. 订单、商品、售后、客户主档等领域服务。
2. SQLite repository 和 migration。
3. 有赞 / 企微 webhook 原始业务处理。
4. 管理后台业务 API。
5. 员工助手事实型最终回复的自由润色。

### 3.2 工程质量原则

1. AI 层可以框架化，业务层不能被框架侵入。
2. 每个阶段必须有可运行验收命令。
3. 每个阶段必须保留回退点或至少保留可定位差异的 golden cases。
4. 客户机器人允许自然语言表达，但事实必须来自 RAG 或工具。
5. 员工助手继续保持确定性最终回复，LLM 只做规划或结构化理解。
6. 生产服务器内存较紧，LangChain 重依赖仍必须懒加载。
7. 框架接管的最终效果必须能被简历、面试、架构图和评估报告表达。

## 四、目标目录形态

当前已有：

```text
app/service/agents/
  llm.py
  models.py
  customer/
  employee/
  tools/
```

本计划建议演进为：

```text
app/service/agents/
  llm.py                         # LangChain ChatOpenAI 工厂与模型策略
  messages.py                    # LangChain message 与项目 message 的转换
  observability.py               # LangSmith / 本地 trace 适配
  evaluation.py                  # Agent 运行样本、断言和报告模型
  checkpoints.py                 # LangGraph checkpointer 与会话映射
  runtime.py                     # Agent runtime config、超时、fallback 策略
  customer/
    graph.py
    state.py
    nodes.py
    prompts.py                   # 客户 Prompt 组件
    retrievers.py                # 客户 LangChain Retriever adapter
    memory.py                    # 客户短期 memory adapter
    service.py
  employee/
    graph.py
    state.py
    nodes.py
    prompts.py                   # 员工 planner prompt
    memory.py                    # 员工 graph state / checkpoint adapter
    service.py
  tools/
    registry.py
    customer.py
    employee.py
  rag/
    documents.py                 # KnowledgeEntry -> Document
    retriever.py                 # BaseRetriever adapter
    rerank.py                    # rerank / fusion adapter
    evals.py                     # RAG eval helpers
```

## 五、阶段路线图

### 阶段 0：二轮基线冻结

目标：确认当前 LangGraph 化后的真实状态，避免第二轮改造时误判退化。

改动范围：

- 不改运行时代码。
- 只新增或更新计划、验收清单和基线报告。

执行步骤：

1. 记录当前依赖版本。
2. 记录客户 graph、员工 graph、tool registry 当前入口。
3. 记录当前未 LangChain 化的部分：`request_llm_choice()`、`KnowledgeRetriever`、Prompt 拼装、会话摘要、trace。
4. 复跑现有关键验收。

验收命令：

```powershell
python -m pytest tests/service/agents tests/service/test_chat_refactor.py -q --no-cov
python scripts/check_customer_rag_golden_cases.py --summary
python scripts/check_knowledge_audience_governance_smoke.py --json
python scripts/check_knowledge_retrieval_logs_smoke.py --json
python scripts/check_wecom_employee_agent_plans.py --json
python scripts/check_employee_agent_capability_contracts.py --summary
python scripts/probe_langchain_capacity.py --include-app-import
python scripts/check_project.py --skip-tests
```

完成标准：

- 当前双机器人 graph 验收通过。
- 明确哪些缺口属于第二轮计划范围。
- 生产内存约束继续有效：`app.main` 冷导入不得加载 `langchain_openai` 或 `langgraph`。

### 阶段 1：模型调用 LangChain 化

目标：把客户机器人主模型请求从项目内 OpenAI request wrapper 迁到 LangChain chat model，统一使用 `ChatOpenAI`、LangChain messages 和 `bind_tools()`。

当前问题：

- `CustomerAgentNodes.model_with_tools()` 仍调用 `request_llm_choice()`。
- 工具 schema 虽然来自 LangChain tools，但最终请求仍转回 OpenAI function schema。
- LangChain 模型工厂已经存在，但没有成为客户热路径主模型接口。

建议改动：

1. 新增 `app/service/agents/messages.py`：
   - `to_langchain_messages(messages: list[dict])`
   - `from_langchain_ai_message(message)`
   - `extract_tool_calls(message)`
2. 扩展 `app/service/agents/llm.py`：
   - 支持客户文本模型、客户视觉模型、员工 planner 模型的选择策略。
   - 保持 MiMo / DeepSeek base_url 和 header 兼容。
3. 新增 `app/service/agents/customer/model.py`：
   - 封装 `ChatOpenAI.bind_tools(customer_tools)`。
   - 处理 timeout、fallback、first token latency、告警。
4. 改造 `CustomerAgentNodes.model_with_tools()`：
   - 从 `request_llm_choice()` 迁到新的 LangChain model adapter。
   - 保留 `timing`、`failure_alerter`、`fallback_reply` 语义。
5. 保留 `request_llm_choice()` 一小段时间作为回退实现，阶段 1 验收后进入退场候选。

验收命令：

```powershell
python -m pytest tests/service/agents/test_llm_factory.py -q --no-cov
python -m pytest tests/service/agents/test_customer_graph.py -q --no-cov
python -m pytest tests/service/test_chat_refactor.py -q --no-cov
python scripts/check_customer_rag_golden_cases.py --summary
python scripts/probe_langchain_capacity.py --include-app-import
python scripts/check_project.py --skip-tests
```

完成标准：

- 客户 graph 模型节点使用 LangChain chat model。
- 客户工具通过 `bind_tools()` 进入模型。
- fallback、timeout、告警、工具轮次限制不退化。
- 干净导入 `app.main` 仍不加载 LangChain 重依赖。

回退策略：

- 保留 `request_llm_choice()` adapter 一阶段。
- 若 LangChain 模型调用对 MiMo 兼容性有问题，customer graph 可切回旧 adapter，但 tool schema 继续保持单一来源。

### 阶段 2：RAG Retriever LangChain 化

目标：把项目内 `KnowledgeRetriever` 包装成 LangChain Retriever，使 RAG 进入标准 `Document` / metadata / retriever adapter 口径。

当前问题：

- RAG 检索可用，但不是 LangChain retriever。
- 检索结果、metadata、score、audience、source_id 主要在项目模型内流转。
- 后续做 rerank、multi-query、LangSmith trace 时缺统一对象。

建议改动：

1. 新增 `app/service/agents/rag/documents.py`：
   - `knowledge_hit_to_document(hit)`
   - `document_to_guard_source(document)`
   - metadata 包含 `knowledge_id`、`title`、`category`、`audience`、`score`、`product_id`、`retrieval_mode`。
2. 新增 `app/service/agents/rag/retriever.py`：
   - 实现 LangChain retriever adapter。
   - 底层继续调用 `KnowledgeRetriever`，不重写 repository。
3. 客户 graph 新增或拆分 `retrieve_knowledge` 节点：
   - 使用 LangChain retriever 获取 documents。
   - 再交给 prompt context composer。
4. 员工知识工具可选择复用 retriever adapter：
   - employee audience 固定为 `employee`。
   - 回复仍由工具服务或 deterministic finalizer 生成。
5. 保留当前 exact normalized dot product 向量搜索，不在本阶段引入外部向量库。

验收命令：

```powershell
python -m pytest tests/service/agents/test_rag_retriever.py -q --no-cov
python -m pytest tests/service/test_knowledge_retriever.py -q --no-cov
python -m pytest tests/service/test_embedding_search.py tests/service/test_embedding_io.py -q --no-cov
python scripts/check_customer_rag_golden_cases.py --summary
python scripts/check_knowledge_audience_governance_smoke.py --json
python scripts/check_knowledge_retrieval_logs_smoke.py --json
python scripts/check_project.py --skip-tests
```

完成标准：

- `KnowledgeRetriever` 可以通过 LangChain retriever adapter 返回 `Document`。
- audience、review_status、valid_from、valid_until 的治理过滤不退化。
- 检索日志仍记录 customer / employee / no_match。
- 客户 golden cases 不退化。

回退策略：

- retriever adapter 是包装层，底层 `KnowledgeRetriever` 不变。
- 若 adapter 有问题，graph 可临时调用原 `prepare_ai_conversation_messages()`，但新增 adapter 测试必须保留。

### 阶段 3：Prompt 上下文组件化

目标：把当前分散在 `chat_context.py`、`llm/prompt.py`、`profile_prompt.py`、`conversation_summary_memory.py` 的上下文拼装，整理成 LangChain prompt component。

当前问题：

- Prompt 上下文增强已经存在，但组件边界不够清晰。
- RAG、客户画像、会话摘要、工具结果、system prompt 的责任散在多个函数。
- 面试表达时很难说明“Prompt 层如何治理事实、记忆和上下文预算”。

建议改动：

1. 新增 `app/service/agents/customer/prompts.py`：
   - `build_customer_system_prompt()`
   - `build_rag_context_messages()`
   - `build_profile_hint_messages()`
   - `build_summary_hint_messages()`
   - `build_tool_result_context()`
2. 将 `chat_context.py` 收缩为兼容 facade 或纯 context budget 适配器。
3. 使用 LangChain message types 作为 graph 内部对象：
   - SystemMessage
   - HumanMessage
   - AIMessage
   - ToolMessage
4. 保持对现有 OpenAI dict message 的兼容转换，避免一次性打穿所有测试。
5. 为每个 prompt component 建立单测，锁定：
   - 没有知识命中时不能编造。
   - 商品标题约束仍生效。
   - 客户画像只作为提示，不作为事实。
   - 会话摘要只读注入，不写入长期画像。

验收命令：

```powershell
python -m pytest tests/service/agents/test_customer_prompts.py -q --no-cov
python -m pytest tests/service/test_chat_refactor.py -q --no-cov
python scripts/check_customer_rag_golden_cases.py --summary
python scripts/check_customer_memory_governance_plan.py --summary
python scripts/check_customer_observability_contract.py --summary
python scripts/check_project.py --skip-tests
```

完成标准：

- Prompt 组件可独立测试。
- graph 节点不再承担大段 prompt 拼装细节。
- 客户上下文预算观测仍保留。
- 客户画像、会话摘要、RAG 的边界可在架构文档中清楚解释。

回退策略：

- 保留 `prepare_ai_conversation_messages()` facade。
- 新组件先由 facade 调用，稳定后再让 graph 直接调用组件。

### 阶段 4：Memory / Checkpoint LangGraph 化

目标：把短期会话摘要和 graph state/checkpoint 统一到 LangGraph 运行口径，同时不破坏现有数据库治理。

当前问题：

- 会话摘要由项目内 scheduler / repository 管理，热路径只读注入。
- LangGraph state 当前是单次请求状态，没有 checkpointer。
- 客户长期画像、会话摘要、最近消息之间的生命周期没有被 graph 显式表达。

建议改动：

1. 新增 `app/service/agents/checkpoints.py`：
   - 映射 `session.id` / employee thread id 到 LangGraph thread id。
   - 提供内存 checkpointer 和 SQLite checkpointer 的选择入口。
2. 新增 `app/service/agents/customer/memory.py`：
   - 读取 active conversation summary。
   - 读取 customer profile hint。
   - 输出 read-only memory block。
3. customer graph 拆出：
   - `load_recent_history`
   - `load_short_term_summary`
   - `load_customer_profile`
   - `compose_context`
4. 不直接用 LangChain Memory 改写现有 `customer_profiles` 或 `conversation_summaries` 表。
5. checkpoint 首版只记录 graph 中间状态和 trace，不作为业务真相。

验收命令：

```powershell
python -m pytest tests/service/test_conversation_summary_service.py -q --no-cov
python -m pytest tests/service/test_conversation_summary_scheduler.py -q --no-cov
python -m pytest tests/repository/test_conversation_summary_repo.py -q --no-cov
python -m pytest tests/service/agents/test_customer_graph.py -q --no-cov
python scripts/check_customer_memory_governance_plan.py --summary
python scripts/check_project.py --skip-tests
```

完成标准：

- LangGraph state 明确表达短期记忆输入。
- 会话摘要仍是回复后异步生成、下一轮只读使用。
- 长期客户画像不被会话摘要污染。
- checkpointer 不替代 repository。

回退策略：

- checkpoint 可先以 no-op / memory saver 方式接入。
- 任何生产持久化 checkpoint 必须单独设计表结构和迁移。

### 阶段 5：Tracing / LangSmith / 本地观测接管

目标：把 graph 节点、模型调用、工具调用、RAG 命中、fallback、转人工、上下文预算统一记录为 Agent trace。

当前问题：

- 当前有 `timing`、`trace_events`、知识检索日志和 smoke 报告，但不是统一 Agent trace。
- `langsmith` 依赖已存在，但没有形成可开关的观测方案。

建议改动：

1. 新增 `app/service/agents/observability.py`：
   - `AgentTraceEvent`
   - `record_graph_node_start`
   - `record_graph_node_end`
   - `record_tool_call`
   - `record_retrieval`
   - `record_fallback`
   - `export_local_trace`
2. 增加配置：
   - `LANGCHAIN_TRACING_ENABLED`
   - `LANGCHAIN_PROJECT`
   - `LANGSMITH_API_KEY`
   - `AGENT_LOCAL_TRACE_ENABLED`
3. 默认生产不开 LangSmith 外发，只保留本地 trace。
4. 本地 trace 可写入 reports 或现有日志，不直接写业务表。
5. 将客户和员工 graph 的 `trace_events` 迁入统一 event model。

验收命令：

```powershell
python -m pytest tests/service/agents/test_observability.py -q --no-cov
python -m pytest tests/service/agents/test_customer_graph.py tests/service/agents/test_employee_graph.py -q --no-cov
python scripts/check_customer_observability_contract.py --summary
python scripts/check_knowledge_retrieval_logs_smoke.py --json
python scripts/check_project.py --skip-tests
```

完成标准：

- 每次 graph 运行可以导出节点级 trace。
- 工具、RAG、fallback、handoff 都有结构化事件。
- LangSmith 是可选开关，不影响默认生产启动。
- trace 不包含敏感明文或密钥。

回退策略：

- 本地 trace adapter 可关闭。
- LangSmith 只作为可选能力，不作为业务可用性前提。

### 阶段 6：RAG Advanced 化

目标：在 LangChain retriever adapter 稳定后，引入更完整的 RAG 工程能力，而不是只做 naive retrieval。

当前问题：

- 当前 RAG 属于偏 Modular RAG，但高级检索策略有限。
- 商品、FAQ、政策、售后都在同一个 knowledge_base 结果空间中。
- 检索前 query rewrite、metadata filter、rerank 和 eval 还不完整。

建议改动：

1. Query rewrite：
   - 客户问法转标准检索 query。
   - 商品名、规格、配送、退款、转人工分意图补强。
2. Multi-query retrieval：
   - 对复杂售后问题生成 2-3 个检索子查询。
   - 保留原 query 与 rewritten query 的 trace。
3. Metadata filter：
   - customer / employee audience。
   - category：product / faq / policy / after_sales。
   - product_id 精确过滤。
4. Rerank：
   - 首版可做规则 rerank。
   - 后续可接 reranker 模型。
5. Hybrid search：
   - 保留 keyword-only fallback。
   - vector + keyword 用 RRF 融合。
6. Eval：
   - 扩展 `tests/fixtures/customer_rag_golden_cases.json`。
   - 增加召回率、命中标题、no_match、答案引用覆盖率。

验收命令：

```powershell
python -m pytest tests/service/agents/test_rag_retriever.py tests/service/test_knowledge_retriever.py -q --no-cov
python scripts/check_customer_rag_golden_cases.py --summary
python scripts/eval_retrieval.py --fixture tests/fixtures/customer_rag_golden_cases.json
python scripts/report_knowledge_retrieval_logs.py --db data/bot.db --limit 100 --json
python scripts/check_project.py --skip-tests
```

完成标准：

- golden cases 召回不低于现有基线。
- 商品实时事实仍通过工具或 live data 注入，不依赖过期 embedding 文本。
- RAG trace 能解释 query rewrite、retriever、rerank、最终引用。
- 未命中知识不会被模型编造。

回退策略：

- 每个高级策略都由 feature flag 控制。
- RRF / rerank 可独立关闭。
- exact normalized dot product 保留为基础向量检索路径。

### 阶段 7：员工助手 Planner LangChain 化

目标：把员工助手 planner 从项目内 LLM JSON wrapper 升级为 LangChain structured output，但最终回复仍保持确定性。

当前问题：

- 员工助手 graph 已接管执行流，但 planner 仍是既有 `EmployeeAgentPlanner`。
- 规则优先策略是对的，但 LLM fallback 的 structured output 可进一步标准化。

建议改动：

1. 新增 `app/service/agents/employee/prompts.py`。
2. 使用 LangChain chat model 的 structured output 能力生成 `AgentPlan`。
3. 保留 rule-first：
   - 明确订单、商品、知识、待人工、系统状态等关键词仍先走规则。
   - LLM planner 只处理弱关键词或多工具组合。
4. planner 输出继续使用 `app/models/employee_agent.py`。
5. finalizer 不改成 LLM。

验收命令：

```powershell
python -m pytest tests/service/test_wecom_employee_agent.py -q --no-cov
python -m pytest tests/service/agents/test_employee_graph.py -q --no-cov
python scripts/check_wecom_employee_agent_plans.py --json
python scripts/check_employee_agent_capability_contracts.py --summary
python scripts/check_project.py --skip-tests
```

完成标准：

- 员工助手规划探针通过。
- 能力合约通过。
- 订单、库存、客户线索类回复仍由 deterministic finalizer 输出。
- LLM planner 失败时返回明确不支持或缺参数提示，不编造工具结果。

回退策略：

- `EmployeeAgentPlanner` 规则部分保留。
- structured output adapter 只替换 LLM fallback 层。

### 阶段 8：Agent Eval 与回放系统

目标：让项目具备可展示的 Agent 评估闭环：每次改 Prompt、Retriever、工具、模型都能量化是否退化。

当前问题：

- 已有多个 check 脚本，但分散在 RAG、员工助手、知识治理、观测合约。
- 缺少统一 Agent eval 报告。

建议改动：

1. 新增 `app/service/agents/evaluation.py`：
   - `AgentEvalCase`
   - `AgentEvalResult`
   - `AgentEvalAssertion`
2. 新增脚本：
   - `scripts/eval_customer_agent.py`
   - `scripts/eval_employee_agent.py`
   - `scripts/report_agent_eval.py`
3. 客户 eval 覆盖：
   - 商品咨询。
   - 配送政策。
   - 退款售后。
   - 转人工。
   - 无资料兜底。
4. 员工 eval 覆盖：
   - 订单查询。
   - 商品库存。
   - 知识话术。
   - 待人工。
   - 同步排障。
5. 输出报告：
   - JSON 给机器门禁。
   - Markdown 给求职展示和复盘。

验收命令：

```powershell
python scripts/eval_customer_agent.py --summary
python scripts/eval_employee_agent.py --summary
python scripts/report_agent_eval.py --latest
python scripts/check_project.py --skip-tests
```

完成标准：

- 每个 Agent 有稳定 eval fixture。
- 报告能说明通过率、失败原因、涉及节点、涉及工具、涉及知识。
- 可作为简历作品集证据。

回退策略：

- eval 脚本不影响线上。
- 初期不接入 pre-commit，稳定后再纳入 `check_project.py --skip-tests`。

### 阶段 9：文档、ADR、作品集收口

目标：把技术迁移沉淀为清晰的工程资产，不只停留在代码变更。

建议交付物：

1. 更新 README 技术栈：
   - FastAPI
   - LangGraph
   - LangChain
   - LangSmith optional
   - RAG
   - SQLite
   - WeCom / Youzan integration
2. 更新 `docs/AGENTS/quick-reference.md`：
   - AI 入口。
   - customer graph。
   - employee graph。
   - retriever adapter。
   - observability。
   - eval scripts。
3. 更新 `docs/architecture/bot-capability-matrix.md`：
   - LangChain 生态化后的能力矩阵。
4. 新增 ADR：
   - `docs/harness-engineering/adr/ADR-xxxx-langchain-ai-layer-boundary.md`
   - 说明为什么只接管 AI 应用层，不接管业务领域层。
5. 新增作品集说明：
   - 架构图。
   - 关键代码路径。
   - eval 报告。
   - 生产约束和回滚策略。

验收命令：

```powershell
python scripts/check_text_encoding.py README.md docs/AGENTS/quick-reference.md docs/architecture/bot-capability-matrix.md docs/architecture/langchain-ecosystem-ai-layer-takeover-plan.md
python scripts/check_logbook.py
python scripts/check_evidence_index.py --summary
python scripts/check_project.py --skip-tests
```

完成标准：

- 文档与代码事实一致。
- 架构取舍有 ADR。
- 简历可以明确写出“LangChain 生态化 AI 应用层”，而不是泛泛写“使用 LangChain”。

## 六、分阶段依赖关系

```text
阶段 0 基线冻结
  -> 阶段 1 模型调用 LangChain 化
    -> 阶段 2 RAG Retriever LangChain 化
      -> 阶段 3 Prompt 上下文组件化
        -> 阶段 4 Memory / Checkpoint LangGraph 化
          -> 阶段 5 Tracing / LangSmith / 本地观测
            -> 阶段 6 RAG Advanced 化
              -> 阶段 7 员工 Planner LangChain 化
                -> 阶段 8 Agent Eval 与回放
                  -> 阶段 9 文档、ADR、作品集收口
```

推荐执行顺序不建议跳过阶段 1-3。原因：

- 如果模型调用不 LangChain 化，后续 tracing 和 tool binding 会一直有双结构。
- 如果 retriever 不标准化，RAG eval 和 LangSmith trace 的解释力有限。
- 如果 prompt 不组件化，Memory 和 RAG 的治理边界仍然难以表达。

## 七、验收总矩阵

| 维度 | 必须保留 | 新增目标 | 验收方式 |
|---|---|---|---|
| 客户回复 | RAG、工具、转人工、guard、fallback | LangChain model + retriever + prompt component | 客户 graph 测试、RAG golden cases |
| 员工回复 | deterministic finalizer、能力合约、规划探针 | LangChain structured planner fallback | 员工 graph 测试、plan probe |
| RAG | audience、review_status、检索日志、exact cosine | LangChain retriever、Document metadata、rerank trace | RAG adapter 测试、retrieval eval |
| Memory | 会话摘要只读注入、长期画像隔离 | Graph state / checkpoint adapter | summary 测试、memory governance |
| Tool | StructuredTool、return_direct | bind_tools、tool trace、权限过滤 | tool registry 测试、agent eval |
| Observability | timing、trace_events、knowledge logs | Agent trace、LangSmith optional、本地 trace export | observability tests、contract check |
| 生产安全 | 懒加载、容量探针、回退点 | 首次调用 RSS 观测 | probe script、health / ready |
| 求职展示 | 业务案例真实 | 架构图、ADR、eval 报告 | 文档与报告 |

## 八、代码量收益预估

LangChain 生态带来的代码量收益不应理解为“业务代码少写”。订单、商品、客户、售后、库存、退款、转人工和后台管理仍然需要项目自己的领域代码。真正减少的是 AI 应用层的重复基础设施代码：模型请求包装、工具 schema 转换、tool call message 拼接、retriever 标准对象、prompt 组件、checkpoint、trace 和 eval glue code。

### 8.1 总体估算

| 口径 | 预估减少 | 说明 |
|---|---:|---|
| 避免继续自研 AI 基础设施 | 约 700-1300 行 | 如果不用 LangChain / LangGraph，后续要自己实现 bind tools、retriever adapter、message types、checkpoint、trace、eval runner 等基础设施 |
| 本仓完成生态化后的净减少 | 约 300-700 行 | 因为会新增 adapter、测试和治理代码，净减少低于“避免自研”的毛收益 |
| AI 编排层复杂度下降 | 约 20%-35% | 主要来自删除重复 tool schema、模型请求包装、手写 message 转换、零散 trace 和 eval glue |
| 业务领域层代码减少 | 基本不减少 | 领域 service / repository 不能交给 LangChain，否则会破坏业务边界 |

这组数字是工程估算，不是精确承诺。每个阶段完成后应以 `git diff --stat`、`cloc` 或 `python` 行数统计复核实际变化。

### 8.2 分模块收益

| 模块 | 能少写或少维护的代码 | 预估收益 | 原因 |
|---|---|---:|---|
| 模型调用 | 自研 OpenAI tool request wrapper、部分 timeout / response 解析 glue | 80-150 行 | `ChatOpenAI`、LangChain message 和 `bind_tools()` 承担通用模型接口 |
| 工具绑定 | OpenAI tool schema 手写映射、tool call 参数解析重复逻辑 | 100-220 行 | `StructuredTool`、Pydantic schema 和 `bind_tools()` 成为单一工具定义来源 |
| RAG Retriever | 自定义检索结果对象到上下文的多处分发代码 | 120-250 行 | `Document`、metadata 和 retriever adapter 统一 RAG 输出形态 |
| Prompt 组件 | 分散在多个函数里的 message 拼接和上下文块拼装 | 100-180 行 | Prompt component 让 RAG、画像、摘要、工具结果形成可测试组合 |
| Memory / Checkpoint | 手写 graph state 快照、thread id 映射和短期状态 glue | 80-160 行 | LangGraph checkpointer 提供标准状态生命周期 |
| Tracing / Eval | 自研节点 trace、工具 trace、评估样本 runner 和报告 glue | 220-400 行 | LangSmith / LangChain eval 口径可复用通用 trace 和 run metadata |

### 8.3 不会减少的代码

这些代码不应该因为使用 LangChain 而减少：

1. 订单查询、物流查询、退款售后、库存同步、有赞 webhook 等业务服务代码。
2. `repository`、migration、SQLite schema 和数据完整性代码。
3. 客户隐私、员工脱敏、转人工状态更新和权限边界代码。
4. golden cases、业务合约、smoke、preflight 和回归测试。
5. 为生产可控性保留的 fallback、guard、capacity probe 和 harness 证据。

如果这些代码被 LangChain “省掉”，通常不是工程收益，而是把业务真相和治理边界藏进了框架调用里，长期会更难维护。

### 8.4 最值得删除的重复代码

第二轮执行时，优先寻找这些可退场对象：

1. 客户模型请求中的 OpenAI tool schema 二次转换。
2. LangChain tool 和 OpenAI function definition 的并行维护。
3. graph 内部 dict message 与 LangChain message 的重复转换。
4. RAG hit 到 prompt 文本的散落拼接逻辑。
5. 各节点本地 `trace_events` 的重复字典结构。
6. eval / smoke 中重复的运行结果解析代码。

首个切片完成后，应在阶段报告中补一行：

```text
代码量收益：新增 X 行，删除 Y 行，净变化 Z 行；减少的主要是 <模块> 的重复基础设施代码。
```

## 九、生产容量策略

已知事实：

- 生产服务器内存余量有限。
- `langchain_openai` 冷导入是主要内存压力。
- 最小 LangGraph 编译和调用本身较轻。

硬约束：

1. `app.main`、router 注册、service 装配阶段不得导入 `langchain_openai`、`langgraph` 重依赖。
2. graph、tool registry、chat model 必须继续懒加载。
3. 每个阶段都要运行：

```powershell
python scripts/probe_langchain_capacity.py --include-app-import
```

4. 任何阶段首次进入生产热路径后，都要观察：
   - `systemctl is-active yunxibakebot`
   - `/health`
   - `/ready`
   - 进程 RSS
   - 首次 Agent 调用耗时
5. 如果生产可用内存低于 250MB，不继续扩大 LangChain 热路径范围，先做进程内存优化或服务器升级。

## 十、回滚和降级原则

| 阶段 | 回滚方式 |
|---|---|
| 模型 LangChain 化 | 切回 `request_llm_choice()` adapter |
| Retriever adapter | graph 暂时调用原 `KnowledgeRetriever` / `prepare_ai_conversation_messages()` |
| Prompt 组件化 | 保留旧 facade，组件内部回退 |
| Checkpoint | 关闭 checkpointer，保留单次 graph state |
| LangSmith | 关闭外发 tracing，仅本地 trace |
| Advanced RAG | feature flag 关闭 rewrite / rerank / hybrid |
| Employee planner | 保留 rule-first 和旧 LLM fallback |
| Eval | eval 不影响线上，只阻断合并或发布 |

长期不允许回滚成“双编排长期并存”。回滚只能用于阶段内排障；稳定后必须删除或收缩旧入口。

## 十一、简历和面试表达目标

完成本计划后，项目可以这样表达：

```text
基于 FastAPI + LangGraph + LangChain 构建双机器人业务 Agent 系统。
客户机器人使用 LangGraph 编排 RAG、工具调用、转人工、上下文记忆和失败兜底；
员工助手使用规则优先 + LangChain structured planner + LangChain tools + deterministic finalizer，
保证订单、库存、客户线索等事实型输出不被 LLM 改写。
RAG 层通过 LangChain Retriever adapter 统一 Document metadata、audience 过滤、query rewrite、rerank 和评估回放。
观测层支持节点级 trace、工具调用 trace、知识命中日志、上下文预算和 Agent eval 报告。
```

这个表述比“用了 LangChain”更有含金量，因为它同时体现：

1. 框架工程能力。
2. 业务分层能力。
3. RAG 治理能力。
4. Agent 可观测和评估能力。
5. 生产约束下的取舍能力。

## 十二、首个执行切片建议

建议先执行阶段 0 和阶段 1，不建议一口气改 RAG、Prompt、Memory、Trace。

首个切片名称：

```text
phase-1-langchain-customer-model-binding
```

首个切片目标：

- 客户 `model_with_tools` 从 `request_llm_choice()` 迁到 LangChain chat model adapter。
- 客户工具通过 `bind_tools()` 绑定。
- 保持 fallback、timeout、告警、工具轮次限制和 golden cases。
- 不改 RAG、不改 Prompt、不改 Memory、不改业务 service。

首个切片验收：

```powershell
python -m pytest tests/service/agents/test_llm_factory.py tests/service/agents/test_customer_graph.py -q --no-cov
python -m pytest tests/service/test_chat_refactor.py -q --no-cov
python scripts/check_customer_rag_golden_cases.py --summary
python scripts/probe_langchain_capacity.py --include-app-import
python scripts/check_project.py --skip-tests
```

首个切片完成后，再进入：

```text
phase-2-langchain-knowledge-retriever-adapter
```

这样推进节奏最稳，也最适合留下可展示的阶段证据。

## 十三、阶段 1 落地记录

2026-07-09 已完成 `phase-1-langchain-customer-model-binding` 首版：

- 新增 `app/service/agents/customer/model.py`，客户 `model_with_tools` 通过 LangChain chat model 调用模型，并使用 `bind_tools()` 绑定客户 `StructuredTool`。
- 新增 `app/service/agents/messages.py`，使用 LangChain 官方 `convert_to_messages()` 将项目内 OpenAI dict messages 转成 LangChain messages，保留图片 message block 和 tool message。
- `CustomerAgentNodes.model_with_tools()` 不再调用旧 `request_llm_choice()`，改为调用 `request_customer_model_with_tools()`。
- `CustomerAgentNodes` 在单次请求内复用 `tools_by_name`，避免同一个 compiled graph 在多 session 场景里缓存旧 session 工具，同时避免 bind 和 execute 重复构造工具。
- `app/service/agents/customer/tool_messages.py` 已兼容 LangChain 原生 tool call dict 和旧 OpenAI SDK object 两种形态。
- `app/service/agents/llm.py` 为 LangChain `ChatOpenAI` 同时配置 sync / async `httpx` client，均使用 `trust_env=False`，避免异步调用路径意外读取系统代理。

阶段 1 代码量记录：

```text
新增 app/service/agents/customer/model.py：117 行
新增 app/service/agents/messages.py：10 行
修改 customer graph / tool message / llm factory：薄适配为主
本阶段净代码量暂时增加，原因是保留旧 request_llm_choice() 作为回退和兼容测试对象；后续阶段稳定后可删除旧 wrapper，代码量收益才会体现。
```

阶段 1 验收：

```powershell
python -m pytest tests/service/agents/test_llm_factory.py tests/service/agents/test_customer_model.py tests/service/agents/test_customer_graph.py tests/service/test_chat_refactor.py -q --no-cov
python scripts/check_customer_rag_golden_cases.py --summary
python scripts/probe_langchain_capacity.py --include-app-import
python -c "import sys; import app.main; print({name: (name in sys.modules) for name in ['langchain_core.tools','langchain_openai','langgraph']})"
python -m ruff check app/service/agents/messages.py app/service/agents/customer/model.py app/service/agents/customer/tool_messages.py app/service/agents/customer/nodes.py app/service/agents/customer/state.py app/service/agents/llm.py tests/service/agents/test_customer_model.py tests/service/agents/test_customer_graph.py
python -m ruff format --check app/service/agents/messages.py app/service/agents/customer/model.py app/service/agents/customer/tool_messages.py app/service/agents/customer/nodes.py app/service/agents/customer/state.py app/service/agents/llm.py tests/service/agents/test_customer_model.py tests/service/agents/test_customer_graph.py
```

阶段 1 已知结论：

- `langchain_openai` 冷导入仍是主要内存压力，本地探针约 316.83MB RSS 增量。
- 最小 LangGraph 编译和调用仍很轻，本地探针约 0.4MB RSS 增量。
- 干净进程导入 `app.main` 后，`langchain_core.tools=False`、`langchain_openai=False`、`langgraph=False`。
- 后续阶段 2 可以继续做 `KnowledgeRetriever -> LangChain Retriever` adapter，但不要同时改 Prompt 和 Memory。

## 十四、阶段 2 落地记录

2026-07-09 已完成 `phase-2-langchain-knowledge-retriever-adapter` 最小首版：

- 新增 `app/service/agents/rag/documents.py`，将 `KnowledgeEntry` 转换为 LangChain `Document`，metadata 保留 `knowledge_id`、`title`、`category`、`content_type`、`audience`、`review_status`、`youzan_item_id`、`priority`、有效期和同步来源。
- 新增 `app/service/agents/rag/retriever.py`，将项目内 `KnowledgeRetriever` 包装为 LangChain `BaseRetriever`，异步调用继续走原 `KnowledgeRetriever.search()`。
- 本阶段不接入客户 graph，不改变 RAG 在线行为；底层 audience、发布状态、有效期、实时库存注入和知识检索日志仍由原服务负责。
- 新增 `tests/service/agents/test_rag_retriever.py`，覆盖 `KnowledgeEntry -> Document` metadata 保真和 retriever async 调用。

阶段 2 代码量记录：

```text
新增 app/service/agents/rag/documents.py：约 30 行
新增 app/service/agents/rag/retriever.py：约 45 行
新增 tests/service/agents/test_rag_retriever.py：约 60 行
本阶段是能力接入层，净代码量增加；后续将客户 RAG prompt 拼接和检索结果分发迁入 Document 口径后，才会体现减少重复 glue code 的收益。
```

阶段 2 验收：

```powershell
python -m pytest tests/service/agents/test_rag_retriever.py tests/service/test_knowledge_retriever.py -q --no-cov
python scripts/check_knowledge_audience_governance_smoke.py --json
python scripts/check_knowledge_retrieval_logs_smoke.py --json
```

## 十五、阶段 3 落地记录

2026-07-09 已完成 `phase-3-customer-prompt-components` 最小首版：

- 新增 `app/service/agents/customer/prompts.py`，将客户 system prompt、会话短期摘要注入、上下文 messages、商品标题提取和 guard source 构造集中为可测试组件。
- `app/service/chat_context.py` 继续作为热路径 facade，调用新的客户 Prompt 组件，不改变消息结构、RAG 检索、context budget、图片消息处理或会话摘要读取策略。
- 新增 `tests/service/agents/test_customer_prompts.py`，覆盖会话摘要只读注入、客户画像提示、system message 顺序、商品标题和 guard source。

阶段 3 代码量记录：

```text
新增 app/service/agents/customer/prompts.py：约 45 行
新增 tests/service/agents/test_customer_prompts.py：约 65 行
chat_context.py 删除原私有 prompt helper，改为调用组件；本阶段主要收益是职责边界清晰和可测试性提升，净代码量仍可能增加。
```

阶段 3 验收：

```powershell
python -m pytest tests/service/agents/test_customer_prompts.py tests/service/test_chat_refactor.py -q --no-cov
python scripts/check_customer_rag_golden_cases.py --summary
```

## 十六、阶段 4 落地记录

2026-07-09 已完成 `phase-4-customer-memory-checkpoint-boundary` 最小首版：

- 新增 `app/service/agents/customer/memory.py`，将 active 会话摘要和已由热路径加载的客户画像聚合为 `CustomerMemoryBlock`，只作为当前轮 graph 的 read-only memory 输入。
- 新增 `app/service/agents/checkpoints.py`，提供 `build_thread_id()`、`build_customer_graph_config()` 和 `create_in_memory_checkpointer()`；`MemorySaver` 保持函数内懒加载，避免 `app.main` 冷导入 LangGraph。
- `CustomerAgentGraphService.answer()` 每次调用 graph 时传入 `configurable.thread_id=customer:<session_id>`，为后续 checkpoint / trace 按会话聚合留标准入口。
- `build_customer_agent_graph()` 支持通过 `CustomerGraphDependencies.checkpointer` 可选注入 checkpointer，但默认生产热路径不启用。
- 新增 `app/service/agents/customer/contracts.py`，将 graph dependencies、request 和 initial state 从 `nodes.py` 拆出，避免节点文件继续膨胀。
- 本阶段不修改 `conversation_summaries`、`customer_profiles` schema，不改变回复后异步摘要生成，不把 LangGraph checkpoint 作为业务真相。

阶段 4 代码量记录：

```text
新增 app/service/agents/checkpoints.py：约 35 行
新增 app/service/agents/customer/memory.py：约 40 行
新增 app/service/agents/customer/contracts.py：约 60 行
customer/nodes.py 拆出契约后降到约 255 行；本阶段主要收益是 graph memory/checkpoint 边界清晰，净代码量仍增加。
```

阶段 4 验收：

```powershell
python -m pytest tests/service/agents/test_checkpoints.py tests/service/agents/test_customer_memory.py tests/service/agents/test_customer_graph.py tests/service/test_chat_refactor.py -q --no-cov
python -c "import sys; import app.main; print({name: (name in sys.modules) for name in ['langchain_core.tools','langchain_openai','langgraph']})"
python -m ruff check app/service/agents/checkpoints.py app/service/agents/customer/contracts.py app/service/agents/customer/memory.py app/service/agents/customer/state.py app/service/agents/customer/nodes.py app/service/agents/customer/graph.py app/service/agents/customer/service.py app/service/chat_ai_loop.py tests/service/agents/test_checkpoints.py tests/service/agents/test_customer_memory.py tests/service/agents/test_customer_graph.py
python -m ruff format --check app/service/agents/checkpoints.py app/service/agents/customer/contracts.py app/service/agents/customer/memory.py app/service/agents/customer/state.py app/service/agents/customer/nodes.py app/service/agents/customer/graph.py app/service/agents/customer/service.py app/service/chat_ai_loop.py tests/service/agents/test_checkpoints.py tests/service/agents/test_customer_memory.py tests/service/agents/test_customer_graph.py
```

阶段 4 已知结论：

- 当前 `CustomerAgentState` 仍包含 `ToolExecutionContext`、callable、tool objects 和 LLM message 等运行时对象，不适合直接做生产持久化 checkpoint。
- 生产默认不启用 `MemorySaver`，避免长生命周期 compiled graph 按 thread_id 积累进程内 checkpoint。
- 下一阶段做 observability / LangSmith 前，可以复用 `thread_id` 和 memory trace 字段，但仍需避免把敏感明文直接外发。

## 十七、阶段 5 落地记录

2026-07-09 已完成 `phase-5-agent-local-observability` 最小首版：

- 新增 `app/service/agents/observability.py`，定义 `AgentTraceEvent`、`build_node_trace_event()` 和 `append_trace_event()`。
- 客户 graph 和员工助手 graph 节点 trace event 改为通过统一 helper 生成，事件继续保留 `node` 顶层字段，并新增 `event=node` 字段，兼容现有本地 state 与后续统一观测。
- 本阶段不新增 LangSmith 配置，不把 trace 写入数据库，不外发 prompt、客户画像、会话摘要或工具结果明文。
- 员工助手 trace 已迁移到同一 helper，但 planner、工具选择、工具执行和确定性回复保持不变。

阶段 5 代码量记录：

```text
新增 app/service/agents/observability.py：约 30 行
新增 tests/service/agents/test_observability.py：约 35 行
customer/nodes.py 与 employee/nodes.py 仅替换 trace event 构造方式，行为保持兼容。
```

阶段 5 验收：

```powershell
python -m pytest tests/service/agents/test_observability.py tests/service/agents/test_customer_graph.py tests/service/agents/test_employee_graph.py tests/service/agents/test_checkpoints.py tests/service/agents/test_customer_memory.py tests/service/test_chat_refactor.py -q --no-cov
python scripts/check_wecom_employee_agent_plans.py --json
python scripts/check_employee_agent_capability_contracts.py --summary
python -m ruff check app/service/agents/observability.py app/service/agents/customer/nodes.py app/service/agents/employee/nodes.py tests/service/agents/test_observability.py tests/service/agents/test_customer_graph.py tests/service/agents/test_employee_graph.py
python -m ruff format --check app/service/agents/observability.py app/service/agents/customer/nodes.py app/service/agents/employee/nodes.py tests/service/agents/test_observability.py tests/service/agents/test_customer_graph.py tests/service/agents/test_employee_graph.py
```

阶段 5 后续：

- 下一小切片才考虑 `LANGCHAIN_TRACING_ENABLED`、`LANGCHAIN_PROJECT`、`LANGSMITH_API_KEY` 等配置，且默认生产关闭外发。

## 十八、阶段 5b 落地记录

2026-07-09 已完成 `phase-5b-langchain-tracing-config-boundary` 首版：

- `app/config.py` 新增 `LANGCHAIN_TRACING_ENABLED`、`LANGCHAIN_PROJECT`、`LANGSMITH_API_KEY`、`AGENT_LOCAL_TRACE_ENABLED`，默认 LangSmith 外发关闭，本地 trace 开启。
- `app/service/agents/observability.py` 新增 `AgentTracingConfig` 和 `get_agent_tracing_config()`，提供 LangSmith 环境变量映射和 LangChain `RunnableConfig` 构造。
- `request_customer_model_with_tools()` 调用 LangChain `ainvoke()` 时传入脱敏 `run_name`、`tags` 和 metadata，只包含 `has_image`、`tool_count`、`langsmith_enabled`、`langchain_project` 等低敏字段。
- `AgentTracingConfig.to_runnable_config()` 会过滤 `api_key`、`token`、`secret`、`message`、`history`、`profile`、`tool_result` 等敏感 metadata key，避免后续调用方误传明文上下文。
- `get_agent_tracing_config()` 不在函数默认参数捕获 `settings`，默认调用时实时读取当前应用配置，便于测试和运行时注入。
- 本阶段不导入 `langsmith`，不在启动期导入 `langchain_openai` / `langgraph`，不把 prompt、客户画像、会话摘要、工具结果或 API key 写入 `RunnableConfig` metadata。

阶段 5b 代码量记录：

```text
app/config.py 增加 4 个配置字段
app/service/agents/observability.py 增加 tracing config helper
app/service/agents/customer/model.py 增加 RunnableConfig 注入
本阶段净代码量增加较小，收益是把 LangSmith 可选外发边界、默认关闭策略和脱敏 metadata 固化为可测试代码。
```

阶段 5b 验收：

```powershell
python -m pytest tests/test_config.py tests/service/agents/test_observability.py tests/service/agents/test_customer_model.py -q --no-cov
python -m ruff check app/config.py app/service/agents/observability.py app/service/agents/customer/model.py tests/test_config.py tests/service/agents/test_observability.py tests/service/agents/test_customer_model.py
python -m ruff format --check app/config.py app/service/agents/observability.py app/service/agents/customer/model.py tests/test_config.py tests/service/agents/test_observability.py tests/service/agents/test_customer_model.py
```

阶段 5b 后续：

- LangSmith 环境变量是否真正注入生产进程，留到部署配置阶段单独处理。
- 下一阶段进入 RAG Advanced 化前，继续保留 `app.main` 冷导入不加载 LangChain 重依赖的容量约束。

## 十九、阶段 6a 落地记录

2026-07-09 已完成 `phase-6a-rag-query-plan-adapter` 首版：

- 新增 `app/service/agents/rag/query.py`，提供 `RagQueryPlan`、`RagQueryVariant` 和保守规则版 `build_customer_rag_query_plan()`。
- `LangChainKnowledgeRetriever` 支持可选 `query_planner`，默认仍是单查询，显式注入 planner 时才启用 multi-query 检索。
- multi-query 检索会按知识条目稳定 key 去重，并在 Document metadata 中写入 `original_query`、`retrieval_query`、`query_variant_index`、`query_variant_reason`，方便后续 trace、eval 和 rerank 分析。
- 本阶段不接入客户热路径，不改变 `KnowledgeRetriever` 的 audience、发布状态、有效期、实时库存注入、检索日志或向量搜索策略。

阶段 6a 代码量记录：

```text
新增 app/service/agents/rag/query.py：约 50 行
扩展 app/service/agents/rag/retriever.py：约 50 行
扩展 tests/service/agents/test_rag_retriever.py：覆盖 query plan、multi-query、去重和 metadata
本阶段净代码量增加；收益是后续 query rewrite / rerank / retrieval eval 可以复用同一个 LangChain Retriever 入口，不再在 graph 或 prompt 层散落多查询逻辑。
```

阶段 6a 验收：

```powershell
python -m pytest tests/service/agents/test_rag_retriever.py tests/service/test_knowledge_retriever.py tests/service/test_embedding_search.py -q --no-cov
python -m ruff check app/service/agents/rag/query.py app/service/agents/rag/documents.py app/service/agents/rag/retriever.py tests/service/agents/test_rag_retriever.py
python -m ruff format --check app/service/agents/rag/query.py app/service/agents/rag/documents.py app/service/agents/rag/retriever.py tests/service/agents/test_rag_retriever.py
```

阶段 6a 后续：

- 下一切片可把 planner 挂到离线 eval 或实验脚本，不直接打开客户热路径。
- 若要进入线上路径，需要 feature flag、golden cases 对比和知识检索日志字段扩展。

## 二十、阶段 6b 落地记录

2026-07-09 已完成 `phase-6b-rag-query-plan-eval-mode` 首版：

- `scripts/eval_retrieval.py` 新增 `planned-vector` 和 `planned-hybrid` 两个离线评测模式。
- 新增 `PlannedQueryEvalSearcher`，复用阶段 6a 的 `build_customer_rag_query_plan()`，先生成查询变体，再调用原 vector 或 hybrid searcher，并按 key 去重。
- 每个 query variant 仍使用 `k` 作为检索 limit，避免 planned 模式通过扩大候选池造成 Recall@K 虚高。
- query plan 无 variants 时回退到原始 query，和生产 adapter 的 fallback 行为保持一致。
- 原 `vector` / `hybrid` 模式保持兼容；planned 模式只在显式传参时启用，不接入客户热路径。
- 本阶段不导入 `langchain_openai`、`langgraph` 或 `langsmith`，只复用轻量 query planning 组件。

阶段 6b 代码量记录：

```text
扩展 scripts/eval_retrieval.py：新增 planned 模式、常量和 PlannedQueryEvalSearcher
扩展 tests/scripts/test_eval_retrieval.py：覆盖 query plan 扩展、去重和无扩展查询回退
本阶段净代码量增加较小；收益是 query rewrite / multi-query 的效果可以先在离线 eval 中量化，再决定是否进入线上路径。
```

阶段 6b 验收：

```powershell
python -m pytest tests/scripts/test_eval_retrieval.py tests/service/agents/test_rag_retriever.py -q --no-cov
python -m ruff check scripts/eval_retrieval.py tests/scripts/test_eval_retrieval.py
python -m ruff format --check scripts/eval_retrieval.py tests/scripts/test_eval_retrieval.py
```

阶段 6b 后续：

- 下一步可在真实或脱敏评测库上对比 `vector`、`hybrid`、`planned-vector`、`planned-hybrid` 的 Recall@K / MRR。
- 如果 planned 模式稳定提升，再考虑通过 feature flag 接入线上 retriever adapter。

## 二十一、阶段 6c 落地记录

2026-07-09 已完成 `phase-6c-rag-rule-rerank-adapter` 首版：

- 新增 `app/service/agents/rag/rerank.py`，提供轻量规则版 `rerank_documents_by_query_rules()`，按客户 query 与 Document 的 title、content、category 相关性稳定排序。
- `LangChainKnowledgeRetriever` 新增可选 `document_reranker` 参数；默认不传时行为不变，仍按原检索顺序和 limit 返回。
- 传入 reranker 时，multi-query 会先收集各 query variant 的候选 Document，再统一 rerank 并截断到 `limit`。
- 本阶段不接入客户热路径，不导入 `langchain_openai`、`langgraph` 或 `langsmith`，只建立规则 rerank 的标准 adapter 边界。

阶段 6c 代码量记录：

```text
新增 app/service/agents/rag/rerank.py：约 60 行
扩展 app/service/agents/rag/retriever.py：新增可选 document_reranker 参数
扩展 tests/service/agents/test_rag_retriever.py：覆盖规则排序和 retriever 可选 rerank 接入
本阶段净代码量增加；收益是后续 reranker 模型或规则实验可以复用同一 Document rerank 接口，不把排序逻辑散落到 graph、prompt 或 eval 脚本中。
```

阶段 6c 验收：

```powershell
python -m pytest tests/service/agents/test_rag_retriever.py tests/scripts/test_eval_retrieval.py -q --no-cov
python -m ruff check app/service/agents/rag/rerank.py app/service/agents/rag/retriever.py tests/service/agents/test_rag_retriever.py scripts/eval_retrieval.py tests/scripts/test_eval_retrieval.py
python -m ruff format --check app/service/agents/rag/rerank.py app/service/agents/rag/retriever.py tests/service/agents/test_rag_retriever.py scripts/eval_retrieval.py tests/scripts/test_eval_retrieval.py
python -c "import sys; import app.service.agents.rag.rerank; print({name: (name in sys.modules) for name in ['langsmith','langchain_openai','langgraph']})"
```

阶段 6c 后续：

- 下一步可让离线 eval 支持可选 rerank，对比 planned/no-rerank 与 planned/rerank 的 Recall@K / MRR。
- 若 rerank 在脱敏评测库稳定提升，再考虑 feature flag 接入线上 retriever adapter。

## 二十二、阶段 6d 落地记录

2026-07-09 已完成 `phase-6d-rag-rerank-eval-mode` 首版：

- `scripts/eval_retrieval.py` 新增显式 `--rerank` 开关和 `--rerank-candidate-multiplier` 参数。
- 新增 `RerankEvalSearcher`，在离线 eval 中复用 `rerank_documents_by_query_rules()`；默认不启用，原 `vector` / `hybrid` / `planned-*` 指标兼容不变。
- 启用 `--rerank` 时会按候选池倍数扩大检索结果，再将 corpus 中的 key/title/content 转成轻量 Document 形态做规则 rerank，最后截断到 `k`。
- 报告和 JSON summary 会标记 `rerank=true` 与候选池倍数，避免把 rerank 扩池评测误读成默认 Recall@K 基线。
- 本阶段不接入客户热路径，不导入 `langchain_openai`、`langgraph` 或 `langsmith`。

阶段 6d 代码量记录：

```text
扩展 scripts/eval_retrieval.py：新增 RerankEvalSearcher、--rerank 和候选池倍数参数
扩展 tests/scripts/test_eval_retrieval.py：覆盖 rerank 候选池扩展、规则排序和倍数下限
本阶段净代码量增加；收益是 rerank 规则可以先在离线评测中量化，再决定是否通过 feature flag 接入线上 retriever。
```

阶段 6d 验收：

```powershell
python -m pytest tests/scripts/test_eval_retrieval.py tests/service/agents/test_rag_retriever.py -q --no-cov
python -m ruff check scripts/eval_retrieval.py tests/scripts/test_eval_retrieval.py app/service/agents/rag/rerank.py app/service/agents/rag/retriever.py tests/service/agents/test_rag_retriever.py
python -m ruff format --check scripts/eval_retrieval.py tests/scripts/test_eval_retrieval.py app/service/agents/rag/rerank.py app/service/agents/rag/retriever.py tests/service/agents/test_rag_retriever.py
python -c "import sys; import scripts.eval_retrieval; print({name: (name in sys.modules) for name in ['langsmith','langchain_openai','langgraph']})"
```

阶段 6d 后续：

- 有脱敏评测库后，跑 `vector`、`hybrid`、`planned-hybrid`、`planned-hybrid --rerank` 四组 Recall@K / MRR 对比。
- 若 `--rerank` 只提升 MRR 但降低 Recall@K，优先作为排序优化而不是召回优化接入。

## 二十三、阶段 6e 落地记录

2026-07-09 已完成 `phase-6e-rag-eval-matrix-report` 首版：

- 新增 `scripts/report_retrieval_eval_matrix.py`，一条命令输出 `vector`、`hybrid`、`planned-hybrid`、`planned-hybrid+rerank` 四组 Recall@K / MRR 对比。
- 矩阵脚本复用 `scripts/eval_retrieval.py` 的 corpus loader、golden case loader、评测指标、hybrid/planned/rerank wrapper，不重复实现检索评分逻辑。
- 同一轮只构建一次向量索引和一次 BM25 索引，再给不同场景复用，避免四组评测重复 embedding，降低服务器承载压力。
- 报告支持 text 与 JSON 输出，并按 Recall@K、MRR、evaluable 数选择 `best`，用于后续判断是否打开 feature flag。
- 本阶段仍然只做离线评测工具，不接入客户热路径。

阶段 6e 代码量记录：

```text
新增 scripts/report_retrieval_eval_matrix.py：约 260 行
新增 tests/scripts/test_report_retrieval_eval_matrix.py：约 130 行
本阶段净代码量增加；收益是 Advanced RAG 策略可以用固定矩阵对比，避免靠单次脚本输出人工拼结论。
```

阶段 6e 验收：

```powershell
python -m pytest tests/scripts/test_report_retrieval_eval_matrix.py tests/scripts/test_eval_retrieval.py tests/service/agents/test_rag_retriever.py -q --no-cov
python -m ruff check scripts/report_retrieval_eval_matrix.py tests/scripts/test_report_retrieval_eval_matrix.py
$env:YUNXI_USE_FAKE_EMBEDDING='1'; python scripts/report_retrieval_eval_matrix.py --db data/bot.db --fixture tests/fixtures/customer_rag_golden_cases.json --k 5
Remove-Item Env:\YUNXI_USE_FAKE_EMBEDDING -ErrorAction SilentlyContinue; python scripts/report_retrieval_eval_matrix.py --db data/bot.db --fixture tests/fixtures/customer_rag_golden_cases.json --k 5
```

阶段 6e fake embedding 管线验证结果：

```text
语料库: data\bot.db（400 条启用知识）
标注集: tests\fixtures\customer_rag_golden_cases.json
vector: Recall@5=0.375, MRR=0.1917
hybrid: Recall@5=1.0, MRR=0.8125
planned-hybrid: Recall@5=1.0, MRR=0.8125
planned-hybrid+rerank: Recall@5=1.0, MRR=1.0
best: planned-hybrid+rerank
```

说明：以上分数来自 `YUNXI_USE_FAKE_EMBEDDING=1`，只证明矩阵脚本、SQLite 语料、BM25、planned wrapper、rerank wrapper 的流程可跑通；真实召回质量仍需在本地模型或脱敏评测库上复跑。

阶段 6e 真实 embedding 验证结果：

```text
模型: BAAI/bge-small-zh-v1.5
语料库: data\bot.db（400 条启用知识）
向量构建耗时: 约 29.06 秒
整轮矩阵耗时: 约 77 秒
vector: Recall@5=1.0, MRR=0.9167
hybrid: Recall@5=1.0, MRR=1.0
planned-hybrid: Recall@5=1.0, MRR=1.0
planned-hybrid+rerank: Recall@5=1.0, MRR=1.0
best: hybrid
```

说明：当前只有 400 条启用知识，且矩阵脚本已改为复用索引；在当前本机数据规模下，LangChain/RAG 评测链路没有表现出服务器承载问题。上线热路径是否开启 planned/rerank，仍应以脱敏生产库和真实 query 分布为准。

阶段 6e 后续：

- 用真实 embedding 模型在脱敏评测库上复跑矩阵，并把 JSON 结果归档到 `reports/`。
- 若真实矩阵中 `planned-hybrid+rerank` 不降低 Recall@K 且提升 MRR，再考虑通过 feature flag 接入线上 `LangChainKnowledgeRetriever`。

## 二十四、阶段 7 落地记录

2026-07-09 已完成 `phase-7-employee-structured-planner` 首版：

- 新增 `app/service/agents/employee/prompts.py`，把员工助手 planner prompt 从旧 wecom LLM JSON helper 中分离出来，作为 LangChain structured planner 的消息入口。
- 新增 `app/service/agents/employee/structured_planner.py`，定义 `EmployeeStructuredPlan` / `EmployeeStructuredOrderPlan` pydantic schema，并通过 `get_langchain_chat_model(...).with_structured_output()` 请求结构化计划。
- 结构化结果继续复用 `parse_llm_plan()` 转成 `AgentPlan`，因此 intent、answer style、date field、limit、order query kind 等安全收敛逻辑保持原样。
- `EmployeeAgentPlanner` 仍然 rule-first；只有规则规划返回 `unsupported` 且 `enable_llm=True` 时才进入 LangChain planner。
- LangChain structured planner 失败时回落旧 `llm_chat` JSON fallback；旧 fallback 也失败时返回规则兜底，不编造工具结果。
- deterministic finalizer、工具执行、订单/库存/客户线索事实回复不改。

阶段 7 代码量记录：

```text
新增 app/service/agents/employee/prompts.py：约 30 行
新增 app/service/agents/employee/structured_planner.py：约 95 行
扩展 app/service/wecom/employee_agent_planner.py：约 90 行
新增 tests/service/agents/test_employee_structured_planner.py：约 110 行
本阶段新增代码集中在 planner adapter，不把确定性回复、工具执行或数据库查询迁移到 LLM。
```

阶段 7 验收：

```powershell
python -m pytest tests/service/test_wecom_employee_agent.py tests/service/agents/test_employee_graph.py tests/service/agents/test_employee_structured_planner.py -q --no-cov
python scripts/check_wecom_employee_agent_plans.py --json
python scripts/check_employee_agent_capability_contracts.py --summary
python -c "import sys; import app.service.wecom.employee_agent_planner; print({name: (name in sys.modules) for name in ['langchain_openai','langgraph','langsmith']})"
```

阶段 7 验证结果：

```text
员工助手服务/graph/structured planner 测试：51 项通过
员工助手规划探针：48 项通过，失败 0
员工助手能力合约：66 项通过，失败 0
employee_agent_planner 冷导入：langchain_openai=False, langgraph=False, langsmith=False
```

阶段 7 后续：

- 可以增加一个只读脚本专门探测 structured planner live API 延迟、失败率和 schema 合规率。
- 若后续决定关闭旧 `llm_chat` JSON fallback，需要先让 live structured planner 通过独立探针和回放用例。

## 二十五、阶段 8 落地记录

2026-07-09 已完成 `phase-8-agent-eval-report` 首版：

- 新增 `app/service/agents/evaluation.py`，统一 `AgentEvalAssertion`、`AgentEvalCase`、`AgentEvalResult` 与双机器人聚合报告模型。
- 新增 `scripts/eval_customer_agent.py`，把 `tests/fixtures/customer_rag_golden_cases.json` 与 fixture governance 检查包装成客户机器人 eval 报告。
- 新增 `scripts/eval_employee_agent.py`，复用 `check_wecom_employee_agent_plans.py` 和 `check_employee_agent_capability_contracts.py`，输出员工助手 eval 报告。
- 新增 `scripts/report_agent_eval.py`，聚合客户机器人和员工助手结果，支持 text、summary、JSON 输出。
- 本阶段不调用线上 LLM，不改客户或员工热路径，不接入 pre-commit；先作为可执行评估报告和作品集证据。

阶段 8 代码量记录：

```text
新增 app/service/agents/evaluation.py：约 110 行
新增 scripts/eval_customer_agent.py：约 157 行
新增 scripts/eval_employee_agent.py：约 111 行
新增 scripts/report_agent_eval.py：约 79 行
新增 tests/service/agents/test_evaluation.py：约 66 行
新增 tests/scripts/test_agent_eval_scripts.py：约 84 行
本阶段代码增加集中在离线 eval 包装层；收益是分散脚本变成统一 Agent Eval 视角，可用于回归、展示和后续门禁。
```

阶段 8 验收：

```powershell
python -m pytest tests/service/agents/test_evaluation.py tests/scripts/test_agent_eval_scripts.py -q --no-cov
python scripts/eval_customer_agent.py --summary
python scripts/eval_employee_agent.py --summary
python scripts/report_agent_eval.py --latest
```

阶段 8 验证结果：

```text
customer_agent_eval status=passed total=9 failed=0 pass_rate=1.0
employee_agent_eval status=passed total=49 failed=0 pass_rate=1.0
agent_eval status=passed total=58 failed=0 pass_rate=1.0
```

阶段 8 后续：

- 可以为 `scripts/report_agent_eval.py` 增加 `--json-out`，把每轮报告归档到 `reports/`。
- 后续接真实回放时，应继续把模型调用和线上状态隔离在显式参数之后，默认保持离线、可重复。

## 二十六、阶段 9 落地记录

2026-07-09 已完成 `phase-9-docs-adr-portfolio-closure` 首版：

- 更新 `README.md`，把当前技术栈从旧的 FastAPI + DeepSeek + RAG 口径更新为 FastAPI + LangChain / LangGraph + RAG + SQLite，并补充 LangChain、LangGraph、LangSmith、Mimo、Agent Eval 等当前能力。
- 更新 `docs/AGENTS/quick-reference.md`，增加 LangChain 模型工厂、客户/员工 graph、RAG retriever adapter、query plan、rerank、structured planner 和 Agent Eval 入口。
- 更新 `docs/README.md`，把当前代码事实更新到 2026-07-09 / VERSION 0.84.0，并加入 LangChain 生态化计划、作品集说明、RAG 矩阵和 Agent Eval 报告入口。
- 更新 `docs/architecture/bot-capability-matrix.md`，把双机器人能力矩阵刷新为 LangChain 生态化后的边界：AI 应用层交给 LangChain / LangGraph，业务事实层仍由项目 service/repository 管理。
- 新增 `docs/harness-engineering/adr/0003-langchain-ai-layer-boundary.md`，固化“LangChain 接管 AI 应用层，不接管业务领域层”的长期决策。
- 新增 `docs/architecture/langchain-ai-layer-portfolio.md`，形成可用于求职/作品集展示的项目说明，覆盖架构边界、关键代码路径、eval 证据、迁移收益和回滚策略。

阶段 9 代码量记录：

```text
新增 ADR：docs/harness-engineering/adr/0003-langchain-ai-layer-boundary.md
新增作品集说明：docs/architecture/langchain-ai-layer-portfolio.md
更新 README、docs/README、quick-reference、bot-capability-matrix
本阶段为文档收口，不改运行时代码。
```

阶段 9 验收：

```powershell
python scripts/report_agent_eval.py --latest
python scripts/report_retrieval_eval_matrix.py --db data/bot.db --fixture tests/fixtures/customer_rag_golden_cases.json --k 5
python scripts/check_project.py --skip-tests
python scripts/check_evidence_index.py --summary
python scripts/check_logbook.py
git diff --check
```

阶段 9 后续：

- 若要对外展示，可优先引用 `docs/architecture/langchain-ai-layer-portfolio.md`，再附 `scripts/report_agent_eval.py --latest` 和 RAG 矩阵输出。
- 若后续开启 planned/rerank 热路径或移除旧 planner fallback，必须新增独立阶段记录和回滚说明。
