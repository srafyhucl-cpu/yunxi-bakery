# LangChain / LangGraph 双机器人迁移执行计划

> trace_id: `20260708-langchain-langgraph-agent-migration`
> 日期：2026-07-08
> 状态：执行中（阶段 4 首版已完成）
> 适用范围：客户机器人、企微员工助手、LLM 编排层、工具调用层、RAG / 记忆 / 观测适配层

## 一、目标结论

本计划将项目中属于 LLM 应用编排范畴的能力迁移到 LangChain / LangGraph：

- 客户机器人和员工助手的 Agent 编排统一由 LangGraph 承载。
- 当前旧 OpenAI tool schema / 旧工具分发器 / 手写 tool loop 迁移为 LangChain tools + LangGraph ToolNode / 条件边。
- RAG、记忆、上下文注入、转人工、fallback、guard、日志和探针验收进入 graph state / node / middleware 口径。
- 现有业务 service、repository、models 不迁入 LangChain；它们作为工具和节点的底层依赖继续提供业务真相。

最终形态不是“双轨并存”，而是：

```text
API / channel adapter
  -> Bot application service
    -> LangGraph workflow
      -> LangChain tools / retrievers / memory adapters
        -> existing domain services
          -> repository
            -> database / external APIs
```

## 二、迁移原则

1. Agent 编排层彻底迁移，不长期保留自研 loop 和 LangGraph 双轨。
2. 业务领域层保持现有分层，不让 graph node 直接访问 repository 或 `aiosqlite`。
3. 客户机器人和员工助手共享 tool adapter，但不共享 graph、state、prompt 和最终回复策略。
4. 员工助手的订单、经营、客户线索类输出继续支持确定性直出；LangChain tool 可使用 `return_direct` 或 graph finalizer 保证不被二次润色。
5. 迁移验收以现有 golden cases、员工探针、知识治理 smoke、业务合约检查为基线。
6. 每个阶段必须可独立回退；旧链路只有在新 graph 通过同等验收后才删除。

## 三、当前模块归属

| 当前模块 | 迁移后归属 | 处理方式 |
|---|---|---|
| `app/service/chat_llm.py` | LangGraph 客户图 | 用 graph loop / ToolNode 替代，最终删除 |
| `app/service/chat_ai_loop.py` | 客户 graph 入口适配 | 保留短期 facade，内部调用 customer graph，稳定后收缩 |
| `app/service/llm/function_defs.py` | LangChain tool schemas | 迁成 typed tools，旧定义删除 |
| `app/service/llm/functions.py` | Tool registry | 迁成 `app/service/agents/tools/`，旧工具分发器删除 |
| `app/service/chat_context.py` | customer graph context node | 保留上下文构建逻辑，改成 node / adapter 调用 |
| `app/service/knowledge_retriever.py` | retriever adapter 底层依赖 | 不重写，包装为 LangChain retriever/tool |
| `app/service/wecom/employee_agent_planner.py` | employee graph planner node | 迁为 structured-output planner node |
| `app/service/wecom/employee_agent_service.py` | employee graph application service | 保留入口，内部调用 employee graph |
| `app/service/wecom/intelligent_bot_*` | LangChain tools 底层依赖 | 不重写，包装为工具 |
| `app/models/employee_agent.py` | graph state / structured output schema | 复用或拆出 agent state models |

## 四、目标目录

```text
app/service/agents/
  __init__.py
  models.py                    # Agent state / context / result models
  llm.py                       # LangChain chat model factory
  observability.py             # LangSmith / 本地 trace 事件适配
  checkpoints.py               # checkpointer 选择与 thread_id 映射
  customer/
    graph.py                   # 客户机器人 StateGraph
    state.py                   # CustomerAgentState
    nodes.py                   # context / model / guard / handoff / final nodes
    prompts.py                 # 客户侧 prompt 组装
    service.py                 # ChatService 调用的 application adapter
  employee/
    graph.py                   # 员工助手 StateGraph
    state.py                   # EmployeeAgentState
    nodes.py                   # planner / tool / deterministic finalizer
    prompts.py                 # 员工侧 planner prompt
    service.py                 # EmployeeAgentService 调用的 application adapter
  tools/
    registry.py                # 按机器人、权限、阶段过滤工具
    knowledge.py               # knowledge_answer / search_knowledge
    product.py                 # product_lookup / get_product_info
    order.py                   # order lookup / logistics
    handoff.py                 # transfer_to_human / handoff_pending
    customer.py                # customer_lookup
    ops.py                     # ops_summary / integration_status / offline_review
```

## 五、阶段执行计划

### 阶段 0：迁移基线冻结

目标：冻结当前行为，避免迁移过程中不知道是否退化。

改动：

- 新增本计划文档。
- 整理客户机器人和员工助手当前验收命令。
- 确认当前 `requirements.txt` 中无 LangChain / LangGraph 依赖。

验收：

```powershell
python scripts/check_project.py --skip-tests
python scripts/check_customer_rag_golden_cases.py --summary
python scripts/check_employee_agent_capability_contracts.py --summary
python scripts/check_wecom_employee_agent_plans.py --json
python scripts/check_knowledge_audience_governance_smoke.py --json
python scripts/check_knowledge_retrieval_logs_smoke.py --json
```

完成标准：

- 上述命令形成迁移前基线。
- 明确哪些失败属于既有环境/数据缺口，哪些是迁移阻断。

### 阶段 1：依赖和模型适配层

目标：引入 LangChain / LangGraph，但不接入真实机器人入口。

改动：

- `requirements.txt` / `requirements-dev.txt` 增加：
  - `langchain`
  - `langgraph`
  - `langchain-openai`
  - 可选：`langsmith`
- 新增 `app/service/agents/llm.py`，封装 MiMo / DeepSeek 兼容 OpenAI 接口。
- 新增 `app/service/agents/models.py`，定义共享 `AgentRuntimeContext`、`AgentResult`、错误原因枚举。
- 新增 `tests/service/agents/` 基础单测，验证模型工厂不在 import 阶段读取网络。

验收：

```powershell
python -m pytest tests/service/agents -q
python scripts/check_project.py --skip-tests
```

完成标准：

- 可以在本地构造 LangChain chat model。
- 不改变 `ChatService` 和 `EmployeeAgentService` 当前行为。

### 阶段 2：LangChain Tool Registry

目标：把当前可调用能力标准化为 LangChain tools，并保留底层业务 service。

改动：

- 新增 `app/service/agents/tools/registry.py`。
- 将客户侧工具迁入：
  - `get_product_info`
  - `get_order_info`
  - `get_logistics_info`
  - `search_knowledge`
  - `transfer_to_human`
- 将员工侧工具迁入：
  - `order_dynamic_query`
  - `product_lookup`
  - `knowledge_answer`
  - `ops_summary`
  - `integration_status`
  - `handoff_pending`
  - `customer_lookup`
  - `group_campaign_summary`
  - `offline_review_summary`
- 对员工侧事实类工具优先使用确定性返回：工具输出直接进入 finalizer，不让模型二次改写。
- 阶段 2 临时保留旧工具分发器，但新增等价测试证明新旧工具输出一致。

验收：

```powershell
python -m pytest tests/service/agents/test_tools_*.py -q
python -m pytest tests/api/test_wecom_intelligent_bot_plugin_api.py -q
python scripts/check_employee_agent_capability_contracts.py --summary
```

完成标准：

- 每个旧工具都有新 LangChain tool 对应项。
- 同一输入下，新工具输出与旧工具业务语义一致。
- graph 尚未接管入口，风险可控。

### 阶段 3：员工助手 LangGraph 化

目标：先迁员工助手，因为它更像确定性工作流，迁移收益和展示价值最高。

目标图：

```text
START
  -> load_employee_context
  -> plan_intent
  -> select_tools
  -> execute_tools
  -> validate_tool_facts
  -> deterministic_finalizer
  -> record_trace
  -> END
```

改动：

- 新增 `app/service/agents/employee/state.py`。
- 新增 `app/service/agents/employee/nodes.py`。
- 新增 `app/service/agents/employee/graph.py`。
- `EmployeeAgentService.answer()` 改为调用 employee graph。
- 旧 `EmployeeAgentPlanner` 改为 graph planner node 内部实现或适配器。
- 保留员工助手确定性回复模板，不恢复 LLM 润色。

验收：

```powershell
python -m pytest tests/service/test_wecom_employee_agent.py -q
python -m pytest tests/service/test_wecom_intelligent_bot_order_lookup.py -q
python -m pytest tests/api/test_wecom_intelligent_bot_plugin_api.py -q
python scripts/check_wecom_employee_agent_plans.py --json
python scripts/check_employee_agent_capability_contracts.py --summary
```

完成标准：

- 员工助手 13 类自由问法计划结果不退化。
- 订单、商品、知识、待人工、客户线索等工具结果不被模型改写。
- 旧 `EmployeeAgentPlanner` 不再作为主编排入口。

回退：

- `EmployeeAgentService.answer()` 可通过 feature flag 回退旧实现。
- 回退开关只保留到阶段 5，不长期保留双轨。

### 阶段 4：客户机器人 LangGraph 化

目标：迁移客户客服主链路，替代手写 LLM tool loop。

目标图：

```text
START
  -> load_session_context
  -> load_customer_memory
  -> retrieve_knowledge
  -> model_with_tools
  -> execute_tools
  -> decide_continue_or_finish
  -> guard_reply
  -> maybe_handoff
  -> record_trace
  -> END
```

改动：

- 新增 `app/service/agents/customer/state.py`。
- 新增 `app/service/agents/customer/nodes.py`。
- 新增 `app/service/agents/customer/graph.py`。
- 新增 `app/service/agents/customer/service.py`，由 `ChatService` / `chat_ai_loop.py` 调用。
- 将客户工具轮次限制迁入 graph config。
- 将 `chat_ai_failure.py`、`chat_transfer.py`、`chat_reply.py` 的关键逻辑以 node 形式接入。
- `KnowledgeRetriever` 通过 retriever/tool adapter 进入 graph，不直接重写。

验收：

```powershell
python -m pytest tests/service/test_chat_refactor.py -q
python -m pytest tests/service/youzan -q
python scripts/check_customer_rag_golden_cases.py --summary
python scripts/eval_retrieval.py --fixture tests/fixtures/customer_rag_golden_cases.json
python scripts/check_knowledge_audience_governance_smoke.py --json
python scripts/check_knowledge_retrieval_logs_smoke.py --json
```

完成标准：

- 客户 RAG golden cases 不退化。
- 转人工路径可触发。
- 工具轮次限制、超时兜底、失败降级仍生效。
- 知识命中日志仍记录 `bot_type`、`audience`、`retrieval_mode`、fallback。

回退：

- `ChatService` 可通过 feature flag 回退旧手写工具循环。
- 阶段 5 删除旧链路前必须至少跑完整客户侧回归。

### 阶段 5：旧编排退场

目标：删除长期双轨，避免维护两套 Agent 编排。

候选删除或收缩：

- `app/service/chat_llm.py`
- `app/service/chat_tools.py`
- `app/service/llm/function_defs.py`
- `app/service/llm/functions.py` 中的旧工具分发器
- `EmployeeAgentPlanner` 的旧外部入口

注意：

- 删除文件必须遵守项目 AGENTS 红线：如需删除，只能一次删除一个明确路径文件；不得批量删除目录。
- 若某文件仍被兼容导入使用，先改为 thin facade，再单独删除。

验收：

```powershell
rg -n "旧编排入口生产路径引用" app tests docs
python -m pytest tests/ -q
python scripts/check_project.py --skip-tests
```

完成标准：

- 旧编排入口无生产路径引用。
- 测试、文档和 quick reference 更新到 LangGraph 口径。

### 阶段 6：观测、文档和求职展示收口

目标：把迁移沉淀成可展示的生产级 Agent 工程案例。

改动：

- `docs/architecture/bot-capability-matrix.md` 更新为 LangGraph 后的能力矩阵。
- `docs/AGENTS/quick-reference.md` 更新 Agent 入口。
- `README.md` 技术栈更新为 FastAPI + LangGraph/LangChain + RAG + SQLite。
- 可选接入 LangSmith tracing；如不接入，则 `observability.py` 输出本地 trace event。
- 新增迁移 ADR：为什么选择 LangGraph、为什么保留业务分层。

验收：

```powershell
python scripts/check_text_encoding.py README.md docs/AGENTS/quick-reference.md docs/architecture/bot-capability-matrix.md docs/architecture/langchain-langgraph-migration-plan.md
python scripts/check_logbook.py
python scripts/check_project.py --skip-tests
```

完成标准：

- 文档入口和代码事实一致。
- 简历表述可以明确写成：基于 LangGraph 的双机器人业务 Agent 编排，覆盖 RAG、工具调用、记忆、转人工、确定性员工助手和生产验收。

## 六、验收矩阵

| 能力 | 员工助手迁移后 | 客户机器人迁移后 |
|---|---|---|
| 订单查询 | `test_wecom_employee_agent.py`、订单 lookup 测试 | 客户订单 / 物流相关测试 |
| 商品查询 | 员工探针、plugin API 测试 | 有赞商品同步和客户聊天测试 |
| 知识检索 | employee knowledge reply、audience smoke | RAG golden cases、retrieval eval |
| 转人工 | `handoff_pending` 工具测试 | MiniApp chat transfer、KF callback |
| 记忆 / 上下文 | 员工 graph state 不泄漏客户隐私 | 长上下文 smoke、客户记忆治理检查 |
| 失败兜底 | 工具错误转确定性提示 | LLM 失败转人工 / fallback |
| 观测 | 员工 plan trace、tool trace | knowledge retrieval logs、tool round trace |

## 七、风险和控制

| 风险 | 影响 | 控制 |
|---|---|---|
| LangChain / LangGraph 版本变化 | API 变动导致迁移返工 | 依赖固定版本，阶段 1 先做最小 spike |
| 生产服务器内存余量不足 | FastAPI 启动或首次 Agent 调用被挤压 | LangChain 重依赖必须懒加载，启动阶段禁止导入 `langchain_openai` / `langgraph` |
| 工具过多导致模型误选 | 客户回复和员工规划退化 | tool registry 按 bot_type、权限、阶段动态过滤 |
| 员工工具结果被模型改写 | 数值和订单事实失真 | 事实类工具走 deterministic finalizer / return_direct |
| graph node 直接访问 repository | 分层被破坏 | node 只调用 service / adapter，新增架构红线测试 |
| 旧链路未删除 | 长期维护两套编排 | 阶段 5 设为强制退场阶段 |
| 迁移后只剩框架外壳 | 求职展示空泛 | 保留真实业务验收、探针、日志、转人工、RAG 评估证据 |

## 八、阶段 1 容量探针结论

2026-07-08 已执行第一轮 LangChain / LangGraph 承载探针：

- 本地 Python：3.13.2。
- 生产服务器只读资源探针：总内存约 1608MB，可用内存约 417MB，swap 1024MB，`yunxibakebot` active。
- `langchain_openai` 冷导入是主要内存来源，本地 RSS 增量约 330MB。
- 最小 `StateGraph` 编译和调用本身很轻，本地 RSS 增量约 0.34MB。
- `app.main` 冷启动验证未加载 `langchain_openai` / `langgraph`，RSS 增量约 30MB。

硬约束：

1. 任何生产入口不得在模块 import 阶段导入 `langchain_openai`、`langgraph` 或其他 LangChain 重依赖。
2. LangChain chat model、StateGraph 和 tool registry 必须通过工厂函数或服务启动后的懒加载路径构造。
3. 每个后续阶段必须运行：

```powershell
python scripts/probe_langchain_capacity.py --include-app-import
```

4. 当首次 Agent 调用引入 LangChain 重依赖后，必须重新观察生产容器/进程 RSS；若可用内存低于 250MB，不继续扩大迁移范围。

## 九、阶段 2 工具注册表落地记录

2026-07-08 已完成 LangChain tool registry 第一版：

- 客户机器人 5 个旧 Function Calling 工具已注册为 LangChain `StructuredTool`：
  - `get_order_info`
  - `get_product_info`
  - `get_logistics_info`
  - `transfer_to_human`
  - `search_knowledge`
- 员工助手 9 个能力合约工具已注册为 LangChain `StructuredTool`：
  - `order_dynamic_query`
  - `product_lookup`
  - `knowledge_answer`
  - `ops_summary`
  - `integration_status`
  - `handoff_pending`
  - `customer_lookup`
  - `group_campaign_summary`
  - `offline_review_summary`
- 员工助手工具统一 `return_direct=True`，后续 graph finalizer 可以直接使用工具 JSON，避免订单、库存、客户线索等事实被二次润色。
- 现阶段只新增 tool registry，不接管 `ChatService` 或 `EmployeeAgentService` 热路径。

阶段 2 验收：

```powershell
python -m pytest tests/service/agents -q --no-cov
python -m ruff check app/service/agents tests/service/agents
python scripts/check_project.py --skip-tests
```

硬约束：

1. `app.main` 启动阶段仍不得加载 `langchain_core.tools`、`langchain_openai` 或 `langgraph`。
2. 员工工具输出先保持 JSON 字符串，后续 employee graph 再决定 finalizer 展示格式。
3. 旧工具分发器和员工助手原工具服务暂不删除；等阶段 3 / 4 graph 接管并通过等价验收后，再进入阶段 5 退场。

## 十、阶段 3 员工助手 LangGraph 落地记录

2026-07-08 已完成员工助手 LangGraph 首版接管：

- 新增 `app/service/agents/employee/state.py`、`nodes.py`、`graph.py`、`service.py`。
- `EmployeeAgentService.answer()` 已改为调用 `EmployeeAgentGraphService`，旧服务入口不再手写执行计划循环。
- employee graph 当前节点链路为：

```text
START
  -> load_employee_context
  -> plan_intent
  -> select_tools
  -> execute_tools
  -> validate_tool_facts
  -> deterministic_finalizer
  -> record_trace
  -> END
```

- `plan_intent` 复用既有 `EmployeeAgentPlanner`，保持 48 项自由问法规划基线。
- `execute_tools` 对非订单能力使用阶段 2 的 LangChain `StructuredTool` 注册表；订单动态查询保留 `order_lookup_service + query_plan` 精细路径，避免退化到粗粒度订单兜底。
- `deterministic_finalizer` 保留确定性回复策略，不恢复 LLM 润色，订单、商品、知识、待人工和客户线索事实不被模型二次改写。
- LangGraph 仍保持懒加载：`app.main` 冷导入不加载 `langchain_core.tools`、`langchain_openai` 或 `langgraph`。

阶段 3 验收：

```powershell
python -m pytest tests/service/agents -q --no-cov
python -m pytest tests/service/test_wecom_employee_agent.py -q --no-cov
python -m pytest tests/service/test_wecom_intelligent_bot_order_lookup.py -q --no-cov
python -m pytest tests/api/test_wecom_intelligent_bot_plugin_api.py -q --no-cov
python scripts/check_wecom_employee_agent_plans.py --json
python scripts/check_employee_agent_capability_contracts.py --summary
python scripts/probe_langchain_capacity.py --include-app-import
python -c "import sys; import app.main; print({name: (name in sys.modules) for name in ['langchain_core.tools','langchain_openai','langgraph']})"
python scripts/check_project.py --skip-tests
```

结果：

- 员工助手 48 项自由问法规划检查通过，失败 0。
- 员工助手能力合约检查通过，66 项失败 0。
- 相关单测和 API 插件测试通过。
- 容量探针结论延续阶段 1：`langchain_openai` 冷导入仍是主要内存压力，本地 RSS 增量约 330MB；最小 LangGraph 编译和调用增量约 0.34MB。
- 干净进程单独导入 `app.main` 后，`langchain_core.tools=False`、`langchain_openai=False`、`langgraph=False`。

阶段 3 后续约束：

1. 阶段 4 迁客户机器人前，继续保留员工助手确定性 finalizer，不把员工事实类回复交给模型润色。
2. 阶段 5 旧编排退场时，`EmployeeAgentPlanner` 可作为 planner node 依赖保留，但不应再作为 `EmployeeAgentService.answer()` 的主编排入口。
3. 若后续要扩展员工 graph 观测，优先把 `trace_events` 接到本地 observability，而不是在节点里直接写数据库。

## 十一、阶段 4 客户机器人 LangGraph 首版落地记录

2026-07-08 已完成客户机器人 LangGraph 首版接管：

- 新增 `app/service/agents/customer/state.py`、`nodes.py`、`graph.py`、`service.py`。
- `run_ai_conversation_loop()` 已改为调用 `CustomerAgentGraphService`，客户 AI 主编排入口进入 LangGraph。
- customer graph 当前节点链路为：

```text
START
  -> load_session_context
  -> model_with_tools
  -> execute_tools
  -> model_with_tools
  -> finalize_reply / tool_round_limit
  -> record_trace
  -> END
```

- `load_session_context` 复用既有 `prepare_ai_conversation_messages`，保持 RAG、会话摘要、客户画像、多模态图片和 context budget 观测。
- `model_with_tools` 复用既有 `request_llm_choice`，保持 MiMo/视觉模型选择、LLM 失败兜底和告警逻辑。
- `execute_tools` 使用阶段 2 的 LangChain `StructuredTool` 注册表和 `ToolNode` 执行客户工具；graph state 使用 LangChain `BaseMessage`，只在外部边界转换消息格式。
- `transfer_to_human` 在 LangChain tool context 中接回 `request_human_transfer`，保持转人工状态更新和摘要策略。
- `tool_round_limit` 保留客户工具轮次限制和 `llm_failure_reason=tool_round_limit` 观测。
- `record_trace` 保留工具输出进入 `guard_source_text` 的事实保护输入。
- `app.main` 冷导入仍不加载 `langchain_core.tools`、`langchain_openai` 或 `langgraph`。

阶段 4 验收：

```powershell
python -m pytest tests/service/agents tests/service/test_chat_refactor.py -q --no-cov
python -m pytest tests/service/test_chat_refactor.py -q --no-cov
python -m pytest tests/service/youzan -q --no-cov
python scripts/check_customer_rag_golden_cases.py --summary
python scripts/check_knowledge_audience_governance_smoke.py --json
python scripts/check_knowledge_retrieval_logs_smoke.py --json
python scripts/probe_langchain_capacity.py --include-app-import
python -c "import sys; import app.main; print({name: (name in sys.modules) for name in ['langchain_core.tools','langchain_openai','langgraph']})"
python scripts/check_project.py --skip-tests
```

结果：

- `tests/service/agents` 与 `tests/service/test_chat_refactor.py` 通过。
- `tests/service/youzan` 通过。
- 客户 RAG golden cases 13 项通过，失败 0。
- 知识 audience smoke 5 项通过，失败 0。
- 知识检索日志 smoke 4 项通过，失败 0。
- 容量探针通过；本轮本地 `langchain_openai` 冷导入 RSS 增量约 313.54MB，最小 graph 增量约 0.24MB。
- 干净进程单独导入 `app.main` 后，`langchain_core.tools=False`、`langchain_openai=False`、`langgraph=False`。
- `python scripts/check_project.py --skip-tests` 通过，函数长度 WARN 仍为既有 52 处。

未完成验证：

- `python scripts/eval_retrieval.py --fixture tests/fixtures/customer_rag_golden_cases.json` 未执行成功，原因是本机缺少 `data\prod_snapshot\eval.db`，脚本要求先拉取生产评估语料库。

阶段 4 后续约束：

1. 阶段 5 才删除或收缩 `chat_llm.py`、`chat_tools.py`、`app/service/llm/function_defs.py`、`app/service/llm/functions.py` 等旧编排/兼容入口。
2. 删除前必须再次跑客户 RAG golden cases、转人工路径、工具轮次限制和知识检索日志 smoke。
3. 若要补 `eval_retrieval.py` 证据，先按脚本提示获取 `data\prod_snapshot\eval.db`，不要临时改脚本绕过语料库缺口。

## 十二、阶段 5 旧编排退场记录

2026-07-08 已完成旧手写编排退场：

- 删除 `app/service/chat_llm.py`，客户主工具循环不再存在第二套入口。
- 删除 `app/service/chat_tools.py`，OpenAI tool message 拼装迁入 `app/service/agents/customer/tool_messages.py`。
- 删除 `app/service/llm/function_defs.py`，客户 OpenAI tool schema 改由 `app/service/agents/tools/customer.py` 统一生成。
- 删除 `app/service/llm/functions.py`，客户 LangChain tools 直接调用 `function_tool_order.py` / `function_tool_product.py` 中已有服务级函数。
- 客户 graph 的工具轮次限制改为 `CUSTOMER_TOOL_ROUND_LIMIT`，避免继续复用旧编排符号。
- `scripts/test_function_calling.py` 改为使用 `build_customer_openai_tool_definitions()`，保持人工 function calling 探针可用。

阶段 5 后当前入口：

```text
run_ai_conversation_loop
  -> CustomerAgentGraphService
  -> CustomerAgentNodes
  -> build_tools("customer")
  -> app/service/agents/tools/customer.py
```

阶段 5 验收口径：

```powershell
rg -n "旧编排入口生产路径引用" app tests docs
python -m pytest tests/service/agents tests/service/test_chat_refactor.py -q --no-cov
python scripts/check_customer_rag_golden_cases.py --summary
python scripts/check_knowledge_audience_governance_smoke.py --json
python scripts/check_knowledge_retrieval_logs_smoke.py --json
python scripts/check_wecom_employee_agent_plans.py --json
python scripts/check_employee_agent_capability_contracts.py --summary
python scripts/probe_langchain_capacity.py --include-app-import
python scripts/check_project.py --skip-tests
```

## 十三、推荐执行顺序

1. 阶段 0：冻结基线。
2. 阶段 1：引入依赖和模型适配。
3. 阶段 2：工具注册表。
4. 阶段 3：员工助手先迁。
5. 阶段 4：客户机器人后迁。
6. 阶段 5：旧编排退场。
7. 阶段 6：文档、观测、展示收口。

不建议客户机器人先迁。员工助手确定性更强，适合作为 LangGraph 首个落地点；客户机器人涉及自然语言回复、RAG、转人工和多模态入口，应在工具层和员工图稳定后再迁。

## 十四、最终交付物

- 代码：
  - `app/service/agents/**`
  - 更新后的 `ChatService` / `EmployeeAgentService`
  - 删除或收缩后的旧 LLM 编排模块
- 测试：
  - `tests/service/agents/**`
  - 更新后的客户聊天、员工助手、工具和脚本测试
- 文档：
  - 本迁移计划
  - 更新后的能力矩阵
  - 更新后的 quick reference
  - 迁移 ADR
- 证据：
  - 迁移前后 `check_project.py --skip-tests`
  - 客户 RAG golden cases
  - 员工助手 plan probe
  - 知识治理 smoke
  - 可选 LangSmith / 本地 trace 截图或报告

## 十五、执行决策

本计划建议执行。迁移目标不是“为了使用 LangChain”，而是把当前已经存在的 LLM 编排、工具调用、RAG、记忆、状态流转和观测能力，统一迁入主流 Agent 工程框架，使系统在长期维护、架构表达和求职展示上更清晰。
