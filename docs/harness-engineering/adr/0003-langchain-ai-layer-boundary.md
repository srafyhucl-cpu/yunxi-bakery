# ADR 0003：LangChain 接管 AI 应用层边界

- status: accepted
- date: 2026-07-09
- trace_id: 20260709-langchain-ecosystem-ai-layer-takeover
- decision_owner: AI (Codex) / project owner
- related_docs:
  - `docs/architecture/langchain-ecosystem-ai-layer-takeover-plan.md`
  - `docs/architecture/bot-capability-matrix.md`
  - `docs/architecture/langchain-ai-layer-portfolio.md`

## Context

项目目标不是做一个框架 demo，而是把真实烘焙门店客服、订单、商品、知识、售后和员工助手做成可维护、可验证、可展示的工程项目。用户明确希望从长期可维护性、设计合理性和求职作品集角度评估 LangChain / LangGraph 的使用价值。

当前项目已经有强分层：`api -> service -> repository -> models`。订单、商品库存、客户线索、知识发布状态、转人工和观测日志都是业务事实层，必须保持可追溯和可测试。与此同时，大模型调用、工具绑定、RAG adapter、Agent 编排、structured output、tracing 和 eval 报告属于 AI 应用层，适合使用 LangChain 生态减少自研编排代码。

## Decision

采用 LangChain / LangGraph 接管 AI 应用层，但不接管业务领域层。

已接受的边界：

- 客户机器人使用 LangGraph 编排、LangChain chat model adapter、LangChain tools、LangChain Retriever adapter、query plan、rerank eval 和 tracing config。
- 员工助手使用 LangGraph 执行流、LangChain tools、LangChain structured output planner fallback 和 deterministic finalizer。
- RAG Advanced 策略先通过离线 eval 矩阵验证，再决定是否通过 feature flag 接入热路径。
- Agent Eval 统一报告聚合客户 RAG golden cases、员工 planner 探针和能力合约，用于回归和作品集证据。

明确不接管的边界：

- LangChain 不直接读写订单、商品、客户、知识库发布状态或转人工数据。
- LangChain 不绕过 repository 层直接操作 SQLite。
- 员工助手最终回复不交给 LLM 润色，经营事实继续由 deterministic finalizer 输出。
- 客户商品库存、价格、订单、售后和转人工事实仍来自工具、service 和 repository，不依赖 embedding 文本中的过期事实。

## Alternatives

- 全项目套入 LangChain：表面上更“彻底”，但会把业务规则、数据库访问、工具执行、记忆和回复策略揉在一起，削弱分层和审计能力。
- 只保留自研链路：短期稳定，但长期在模型适配、工具协议、structured output、tracing 和 eval 生态上会重复造轮子，不利于作品集展示。
- 只做文档不改代码：无法证明框架接入能力，也不能量化迁移收益。

## Consequences

- 正向影响：AI 应用层更接近主流大模型工程栈，关键能力有 LangChain / LangGraph 代码证据和可执行 eval 证据。
- 正向影响：业务领域层仍保持项目原有强分层，订单、库存、客户和知识治理不会被框架隐式接管。
- 负向影响：短期代码量有所增加，因为 adapter、eval 和回退边界需要并存一段时间。
- 后续要求：移除旧 LLM JSON fallback、打开 planned/rerank 热路径或接入更多 LangSmith tracing 之前，必须先跑对应探针、golden cases 和矩阵报告。

## Verification

- `python scripts/report_agent_eval.py --latest`
- `python scripts/report_retrieval_eval_matrix.py --db data/bot.db --fixture tests/fixtures/customer_rag_golden_cases.json --k 5`
- `python scripts/check_wecom_employee_agent_plans.py --json`
- `python scripts/check_employee_agent_capability_contracts.py --summary`
- `python scripts/check_project.py --skip-tests`
