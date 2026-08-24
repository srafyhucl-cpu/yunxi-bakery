# 双机器人能力目录

> trace_id: `20260706-plan-review-capability-matrix`
> 状态：LangChain 生态化后更新
> 日期：2026-07-09
> 适用范围：客户机器人、企微员工助手、共享业务服务、验证入口
> 关联文档：
> - [GitHub 参考项目借鉴与可实施计划](./github-reference-benchmark-and-implementation-plan.md)
> - [客户会话摘要设计](./customer-session-summary-design.md)
> - [客户长期记忆治理计划](./customer-memory-governance-plan.md)
> - [企微员工助手开发计划书](./wecom-employee-agent-development-plan.md)
> - [企微智能机器人工具清单](./wecom-intelligent-bot-tools.md)
> - [项目边界](./project-boundaries.md)

______________________________________________________________________

## 一、结论

当前项目已经具备执行“客户机器人 / 员工助手分线治理”的基础，没有发现会阻断阶段 1 的不可实现项。

2026-07-09 后，AI 应用层已完成 LangChain / LangGraph 生态化小切片：

- 客户机器人：LangGraph 编排、LangChain chat model adapter、LangChain tools、Retriever adapter、query plan、离线 rerank eval 和 RAG 矩阵报告。
- 员工助手：LangGraph 执行流、LangChain structured planner fallback、LangChain tools、deterministic finalizer 和统一 Agent Eval。
- 业务事实层：订单、商品库存、客户线索、知识发布状态、转人工和观测日志仍由项目 service/repository 管理，不交给 LangChain 直接接管。

需要坚持的边界：

- **客户机器人**面向消费者，允许自然语言表达，但必须受 RAG、工具结果、回复 guard 和转人工机制约束。
- **员工助手**面向内部经营，最终回复必须确定性直出，LLM 只允许作为结构化规划兜底。
- 两个机器人可以共享 `order`、`catalog`、`knowledge`、`conversation`、`ops` 等底层 service，但不能共享同一套回复策略。
- MiniApp 只提供客户侧客服入口和页面体验，不实现 AI 主逻辑。

本文件是后续新增工具、补探针、改知识库治理、做 MiniApp 页面差距分析时的能力索引。

______________________________________________________________________

## 二、机器人边界

| 项 | 客户机器人 | 员工助手 |
|---|---|---|
| 用户 | 消费者、客户、企微客服客户 | 店员、运营、管理者 |
| 入口 | MiniApp 客服、有赞托管消息、企微客服消息 | 企微智能机器人插件 / 群内机器人 |
| 主要目标 | 回答咨询、导购、售后解释、安抚、转人工 | 查订单、查库存、查待办、查系统状态、查客户线索 |
| 回复策略 | 自然语言 + RAG + 工具结果 + guard | 工具结果 + 模板化确定性回复 |
| LLM 使用 | LangChain 模型适配、RAG 回答、工具调用循环、必要的自然表达 | 规则优先，LangChain structured output 只做 planner fallback，最终回复不交给 LLM 改写 |
| 失败兜底 | 转人工、保守回复、回复 guard | 明确空结果 / 缺参数 / 工具不可用，不编造 |
| 验证重点 | 不乱承诺、不脱离知识库、能转人工、长上下文不爆、RAG eval 不退化 | 计划正确、数值保真、工具结果不被改写、探针通过、structured fallback 不破坏 rule-first |

______________________________________________________________________

## 三、客户机器人能力矩阵

当前代码证据：

- 前台客服 API：`app/api/channels/storefront/chat.py`
- 前台会话服务：`app/service/conversation/storefront.py`
- 客户主链路：`app/service/chat_message_flow.py`
- AI 主编排：`app/service/chat_ai_loop.py` -> `app/service/agents/customer/service.py`
- RAG 上下文：`app/service/chat_context.py`
- LangGraph 节点：`app/service/agents/customer/graph.py`、`app/service/agents/customer/nodes.py`
- LangChain 工具：`app/service/agents/tools/customer.py`
- LangChain 模型适配：`app/service/agents/customer/model.py`
- LangChain Retriever adapter：`app/service/agents/rag/retriever.py`
- RAG query plan / rerank：`app/service/agents/rag/query.py`、`app/service/agents/rag/rerank.py`
- RAG eval 矩阵：`scripts/report_retrieval_eval_matrix.py`
- OpenAI tool 消息：`app/service/agents/customer/tool_messages.py`
- 转人工：`app/service/chat_transfer.py`、`app/service/transfer_manager.py`
- 客户记忆：`app/service/customer_memory.py`、`app/service/offline/agent_memory.py`

| 能力 | 当前状态 | 入口 / 工具 | 底层 service | 回复策略 | 验证入口 | 后续动作 |
|---|---|---|---|---|---|---|
| 商品咨询 / 导购 | 已有 | `get_product_info`、`search_knowledge` | `catalog`、`knowledge_retriever`、有赞商品同步 | 自然语言回答，商品事实来自工具和知识库 | `tests/service/youzan/*`、商品同步测试、客户聊天链路测试、`scripts/report_agent_eval.py --latest` | 持续扩充客户 RAG golden cases |
| 商品实时价格 / 库存 | 已有 | `get_product_info` | `function_tool_product.py`、有赞 client、知识库回写 | 客户可读解释，不能编造库存 | `tests/service/youzan/test_full_chain_e2e.py` 等 | 观测工具调用成功率 |
| 订单详情查询 | 已有 | `get_order_info` | `function_tool_order.py`、有赞订单接口 / 本地订单数据 | 仅查询客户本人或明确订单号，回复需谨慎 | `tests/service/youzan/*`、托管消息测试 | 加强客户身份和订单归属说明 |
| 物流查询 | 已有 | `get_logistics_info` | `function_tool_order.py` | 解释物流状态，缺物流时保守说明 | 物流相关 service 测试 | 建立“暂无物流”客户问法回归 |
| 售后 / 配送 / FAQ | 已有 | `search_knowledge` | `knowledge_retriever`、`knowledge_base`、LangChain Retriever adapter | 基于知识库自然回答，资料不足转人工 | `tests/scripts/test_seed_baseline_knowledge.py`、`scripts/eval_retrieval.py`、`scripts/report_retrieval_eval_matrix.py` | 用真实 no_match 样本反哺知识 |
| 转人工 | 已有 | `transfer_to_human`、`/api/v1/miniapp/chat/transfer` | `chat_transfer.py`、`transfer_manager.py`、`transfer_repo` | 客户引导 + 工单创建 + 人工接管 | `tests/service/wecom/test_kf_callback_processor.py`、admin transfer tests | 增加转人工原因分类观测 |
| AI 失败自动转人工 | 已有 | LLM 失败路径 | `chat_ai_failure.py` | AI 降级时自动接人工 | 相关聊天链路测试 | 把失败原因纳入观测指标 |
| 客户长期记忆 | 已有基础 | prompt 注入客户画像 | `customer_memory.py`、`profile_prompt.py`、`offline/agent_memory.py` | 只作为提示，不作为事实结论 | 离线复盘 / memory 相关测试、`scripts/check_customer_memory_governance_plan.py --summary` | 已冻结证据、置信度、撤销、过期和会话摘要隔离治理计划，后续再实现 schema 或后台操作 |
| 长上下文截断 | 已有基础 | `SessionManager.build_context` + active 会话摘要 | `session_manager.py`、`conversation_summary_memory.py`、`chat_context.py` | token budget 内保留最近上下文，active 摘要只读注入 system prompt | `tests/service/test_chat_refactor.py`、`tests/scripts/test_check_customer_long_context_summary_smoke.py` | 会话摘要设计、独立数据层、生成 service、回复后异步触发、草稿保存、只读注入和离线长上下文 smoke 已完成，后续做生产观察 |
| 图片 / 多模态咨询 | 已有入口 | `image_base64` | `chat_multimodal.py` | 图片进入 LLM 消息，不应绕过知识和转人工 | 当前需补场景化验证 | 后续按真实图片咨询补验收 |

客户机器人当前最明显的缺口不是“能力不存在”，而是：

- 知识库命中和引用没有形成稳定观测。
- 长上下文摘要已完成明确设计、独立数据层、摘要生成 service、回复后异步触发、active 草稿保存、热路径只读注入和离线长上下文 smoke；仍需生产观察 token 压力变化和真实回复质量。
- 长期记忆有基础字段，证据、置信度、撤销、过期和会话摘要隔离规则已冻结为 [客户长期记忆治理计划](./customer-memory-governance-plan.md)，并已接入静态验收；后续再实现 schema 或后台操作。

______________________________________________________________________

## 四、员工助手能力矩阵

当前代码证据：

- 企微智能机器人入口：`app/api/integrations/wecom_intelligent_bot.py`
- 员工助手编排：`app/service/wecom/employee_agent_service.py`
- 员工 LangGraph 编排：`app/service/agents/employee/graph.py`、`app/service/agents/employee/nodes.py`
- 员工助手规划：`app/service/wecom/employee_agent_planner.py`
- LangChain structured planner：`app/service/agents/employee/structured_planner.py`、`app/service/agents/employee/prompts.py`
- 能力检索卡：`app/service/wecom/employee_agent_capabilities.py`
- 能力合约清单：`app/service/wecom/employee_agent_capability_contracts.py`
- 结构化计划模型：`app/models/employee_agent.py`
- 订单动态查询：`app/service/wecom/intelligent_bot_order_lookup.py`
- 业务工具：`app/service/wecom/intelligent_bot_tools.py`
- 运营工具：`app/service/wecom/intelligent_bot_ops_tools.py`
- 状态工具：`app/service/wecom/intelligent_bot_status_tools.py`
- 探针：`scripts/wecom_employee_agent_probe_cases.py`、`scripts/check_wecom_employee_agent_plans.py`
- 能力合约验收：`scripts/check_employee_agent_capability_contracts.py --json`，并已接入 `scripts/check_project.py --skip-tests`
- 统一 Agent Eval：`scripts/eval_employee_agent.py --summary`、`scripts/report_agent_eval.py --latest`

| 能力 | 当前状态 | 工具名 / endpoint | 底层 service | 回复策略 | 验证入口 | 后续动作 |
|---|---|---|---|---|---|---|
| 订单动态查询 | 已有 | `order_dynamic_query` / `/tools/order-lookup` | `WeComOrderLookupService`、`order` 仓库 | 确定性统计 / 列表 / 明细 / 下一步 | `tests/service/test_wecom_employee_agent.py`、`tests/service/test_wecom_intelligent_bot_order_lookup.py`、探针脚本 | 持续把真实员工问法沉淀为探针 |
| 商品库存 / 价格 / 上架 | 已有 | `product_lookup` / `/tools/product-lookup` | `CatalogApplicationService` | 确定性商品列表和员工下一步 | `tests/api/test_wecom_intelligent_bot_plugin_api.py`、员工探针 | 补商品别名和规格问法回归 |
| 知识库话术 / 规则 | 已有 | `knowledge_answer` / `/tools/knowledge-answer` | `employee_knowledge_retriever` | 列来源和可复制建议，不做自由润色 | `tests/api/test_wecom_intelligent_bot_plugin_api.py`、`test_wecom_intelligent_bot_knowledge_reply.py`、`scripts/check_knowledge_audience_governance_smoke.py --json`、`scripts/check_knowledge_retrieval_logs_smoke.py --json`、`scripts/report_knowledge_retrieval_logs.py --db <db> --limit 100 --json`、`GET /api/v1/admin/knowledge-retrieval-report/summary`、后台 `/knowledge-retrieval-report` | 后续基于 no_match 数据补知识 |
| 商品 + 话术组合 | 已有 | `product_lookup + knowledge_answer` | 商品工具 + 知识工具 | `mixed_reply` 模板化组合 | `tests/service/test_wecom_employee_agent.py`、探针脚本 | 继续覆盖缺货替代、客户回复话术 |
| 订单 + 话术组合 | 已有 | `order_dynamic_query + knowledge_answer` | 订单工具 + 知识工具 | `mixed_reply` 模板化组合 | 员工探针脚本 | 补更多售后/履约组合问法 |
| 观察台摘要 | 已有 | `ops_summary` / `/tools/ops-summary` | `ObservabilityService` | 确定性状态摘要和排查建议 | `tests/api/test_wecom_intelligent_bot_plugin_api.py` | 观测字段稳定后再扩展指标 |
| 同步 / Webhook 排障 | 已有 | `integration_status` / `/tools/integration-status` | `ObservabilityService.get_webhooks` | 确定性失败 webhook 列表 | `tests/api/test_wecom_intelligent_bot_plugin_api.py`、员工探针 | 已补 capability card 和规划探针 |
| 待人工列表 | 已有 | `handoff_pending` / `/tools/handoff-pending` | `TransferManager` | 确定性列表，脱敏客户标识 | `tests/api/test_wecom_intelligent_bot_plugin_api.py`、员工探针 | 补接单 / 关闭动作仍走后台，不在机器人里写操作 |
| 客户地址线索 | 已有 | `customer_lookup` / `/tools/customer-lookup` | `CustomerAddressService` | 脱敏线索 + 人工核对提示 | `tests/api/test_wecom_intelligent_bot_plugin_api.py`、员工探针 | 后续客户主档成熟后再升级为 CRM 查询 |
| 客户群活动汇总 | 已有 | `group_campaign_summary` / `/tools/group-campaign-summary` | `CustomerGroupOperationsService` | 汇总文案和待跟进列表 | `tests/api/test_wecom_intelligent_bot_plugin_api.py`、员工探针 | 与 MiniApp 登记页继续同 trace 验证 |
| 离线复盘摘要 | 已有 | `offline_review_summary` / `/tools/offline-review-summary` | `OfflineReviewScheduler` summary provider | 确定性复盘结果和跳过原因翻译 | `tests/api/test_wecom_intelligent_bot_plugin_api.py`、ops format tests | LangGraph 只能在此类离线流程试点 |
| 弱关键词规划兜底 | 已有 | `EmployeeAgentPlanner._plan_with_llm` | LangChain structured output，失败后回落旧 JSON fallback | 不生成用户可见回复 | `tests/service/test_wecom_employee_agent.py`、`tests/service/agents/test_employee_structured_planner.py` | 保持 rule-first；未来移除旧 fallback 前先跑 live structured planner 探针 |

员工助手当前最明显的缺口：

- 员工助手已有工具很多，新增能力前必须先补探针，否则规划会退化。
- 所有经营数据类回复都不能恢复 LLM 润色。
- 每个能力已具备首版合约清单，且已接入统一质量门禁；后续新增工具时必须同步参数规则、缺参数口径、空结果口径、异常口径和对应探针。

______________________________________________________________________

## 五、共享底层能力

| 共享能力 | 客户机器人使用方式 | 员工助手使用方式 | 边界 |
|---|---|---|---|
| `knowledge_retriever` | 生成客户可读回答，使用 `audience='customer'` | 员工助手使用独立 `employee_knowledge_retriever`，列来源、员工可复制话术 | 共享 repository 和数据真相，入口 audience 与回复策略分开 |
| LangChain / LangGraph | 客户 Agent 编排、工具绑定、Retriever adapter、RAG eval | 员工 Agent 编排、structured planner、工具 adapter、Agent Eval | 只接管 AI 应用编排层，不接管业务领域层和数据库事实层 |
| `order` 域 | 查询客户订单 / 物流 | 查询经营订单 / 统计 / 风险 | 权限和口径不同 |
| `catalog` 域 | 商品咨询、导购 | 库存、价格、上架状态 | 同源数据，展示不同 |
| `conversation` / `transfer` | 客户转人工 | 员工查待人工列表 | 客户触发，员工处理 |
| `offline` | 不直接暴露 | 查复盘摘要 | 离线结果只给员工 |
| `customer` | 客户画像提示 | 地址线索 / 客户群活动 | 员工侧必须脱敏和提示人工核对 |

共享 service 的原则：

1. 数据真相可以共享。
2. 回复策略不能共享。
3. 权限和脱敏规则必须按机器人区分。
4. 每个共享能力必须有至少一条客户侧验证或员工侧验证。

______________________________________________________________________

## 六、当前计划可实施性 Review

### 没有硬阻塞的项

| 计划项 | 判断 | 依据 |
|---|---|---|
| 阶段 1：双机器人能力目录 | 可立即做 | 当前已有客户链路、员工能力卡、工具 endpoint 和测试入口 |
| 阶段 2：客户上下文治理 | 可做，但需先出设计 | 已有 token budget、客户画像和离线记忆基础 |
| 阶段 3：知识库治理 | 可做，但要分批 | 已有知识库、后台、同步和检索，字段迁移需单独计划 |
| 阶段 4：员工助手能力增强 | 可继续做 | 已有确定性回复、能力卡、能力合约、探针和工具服务 |
| 阶段 5：MiniApp 商城体验对照 | 可做 | MiniApp 已有 home/products/product-detail/cart/checkout/orders/chat 等页面和 services |
| 阶段 6：观测和发布闭环 | 可做 | 已有 check_project、smoke、ready、员工 callback probe 基础 |

### 需要前置条件的项

| 计划项 | 前置条件 | 原因 |
|---|---|---|
| 知识库 audience / 有效期 / 审核字段 | 已完成兼容迁移、字段级门禁、repository 默认过滤、入口显式 audience、后台展示编辑、脚本级 smoke、首版命中日志、只读趋势报表、后台只读 API 和后台只读页面 | 后续仍需用真实 no_match 样本反哺知识库 |
| 客户会话摘要 | 已冻结设计并完成独立表、repository、摘要生成 service、回复后异步触发、草稿保存和只读注入小切片 | 避免摘要污染长期记忆或增加 token 成本 |
| 员工更多 `integration_status` 真实问法 | 继续补计划探针 | 首版已覆盖“同步失败有哪些”，还需从生产真实问法继续沉淀 |
| MiniApp 发布自动化 | 需要在 MiniApp 仓单独执行 | 涉及 `miniprogram-ci` 配置、appid/private key、微信开发者流程 |
| 双仓联动 trace | 需要两个仓同步 LOGBOOK / 文档口径 | 不是 Platform 单仓能完全闭环 |

### 只能作为可选试点的项

| 计划项 | 判断 |
|---|---|
| LangGraph 离线流程试点 | 可选，必须先做对比报告，不能替换现有离线流程 |
| LangChain loader/splitter | 可选，只能用于入库实验，结果进入待审核 |
| 复杂会员营销引擎 | 当前不建议做，先保留为 MiniApp / Platform 后续路线图参考 |
| 多租户平台化 | 当前不做，`Yunxi` 仍是首个实例，先把单实例闭环做稳 |

结论：计划整体可执行，没有发现需要推翻的项。执行顺序应保持“能力目录 -> 上下文治理 -> 知识库治理”，不要先上框架迁移。

______________________________________________________________________

## 七、下一步执行建议

P0：

- 持续把 `integration_status` 真实排障问法补进员工助手规划探针。
- 已为客户机器人建立第一批 RAG golden cases，覆盖配送、退款售后、商品咨询、转人工；结构校验入口为 `scripts/check_customer_rag_golden_cases.py`，离线检索评估入口为 `scripts/eval_retrieval.py --fixture tests/fixtures/customer_rag_golden_cases.json`，结构校验已接入 `scripts/check_project.py --skip-tests` 的“业务合约检查”。
- 已输出客户上下文预算观测快照，记录最近消息、RAG、客户画像、system prompt、运行时工具结果、预算压力等级和会话摘要候选标记。
- 已冻结客户会话摘要设计并完成独立数据层、生成 service、回复后异步触发、只读注入和离线长上下文 smoke，采用“观测触发、异步生成、下轮使用”，摘要只作为短期上下文，不直接进入长期客户画像。

P1：

- 已设计并实现知识库 `audience / valid_from / valid_until / review_status` 兼容迁移、首版命中日志、只读趋势报表、后台只读 API 和后台只读页面：`docs/architecture/knowledge-governance-migration-plan.md`、`app/migrations/v015_knowledge_governance_fields.sql`、`app/migrations/v016_knowledge_retrieval_logs.sql`、`KnowledgeRepo` 默认过滤、客户/员工入口显式 audience、后台展示编辑、`check_knowledge_governance_plan.py`、`check_knowledge_audience_governance_smoke.py`、`check_knowledge_retrieval_logs_smoke.py`、`report_knowledge_retrieval_logs.py`、`app/api/admin/knowledge_retrieval_report.py` 和 `web/admin/src/pages/knowledge/KnowledgeRetrievalReportPage.vue` 已落地，知识治理计划静态验收已接入统一质量门禁，后续用真实 no_match 样本反哺知识库。
- 已为员工助手建立能力合约清单和静态验收：`app/service/wecom/employee_agent_capability_contracts.py` 覆盖 9 个能力的参数规则、缺参数口径、空结果口径、异常口径和探针名；`scripts/check_employee_agent_capability_contracts.py --json` 已证明能力卡、合约和探针三者一致；`scripts/check_project.py --skip-tests` 已接入员工助手能力合约、客户 RAG golden cases、知识治理计划和客户长期记忆治理计划四类业务合约检查；`scripts/preflight_production.py --json` 也会输出 `business_contracts.static_checks` 及四类合约状态明细，把合约证据纳入发布前预检。
- 给客户转人工和 AI 失败自动转人工补原因分类统计。
- 在 MiniApp 仓输出页面差距清单，逐页映射 Platform API。

P2：

- 评估 LangGraph 是否能降低离线复盘编排复杂度。
- 评估 `miniprogram-ci` 的发布接入条件和密钥保管方式。
