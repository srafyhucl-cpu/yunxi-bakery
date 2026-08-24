# ADR 0005：框架优先与单一路径治理

- status: accepted
- date: 2026-07-11
- trace_id: 20260711-global-risk-remediation
- decision_owner: project owner / AI (Codex)
- related_docs:
  - `docs/architecture/global-risk-remediation-and-framework-convergence-plan.md`
  - `docs/harness-engineering/adr/0003-langchain-ai-layer-boundary.md`
  - `docs/architecture/langchain-langgraph-migration-plan.md`

## Context

项目已经引入 LangChain、LangGraph 和 LangSmith，但当前仍有部分 AI 通用能力同时存在框架实现和自研实现，例如模型客户端、工具执行、消息转换、JSON 解析、trace 事件和 provider 选择。双轨会造成行为漂移、重复测试和维护成本。

同一轮全局审计还确认，认证、支付、事务、幂等、队列、隐私和发布恢复属于业务安全或基础设施问题。这些能力不能为了追求“全面 LangChain 化”而塞进 AI 框架，也不能继续用缺少约束的临时实现替代成熟标准。

## Decision

### 1. 采用框架优先决策顺序

新增或重构通用能力时，按以下顺序决策：

1. 使用项目已引入框架的稳定公开 API。
2. 使用同一生态的官方扩展或维护活跃的成熟组件。
3. 写一个只做协议转换的薄 adapter，业务规则仍留在领域层。
4. 只有前三项都不满足安全、资源、许可或可测试性要求时，才允许自研；例外必须在 ADR 或计划中记录原因、owner、验收和退出条件。

禁止为了“以后可能会用”提前再造框架已有能力。禁止长期维护功能等价的框架路径和自研路径。

### 2. AI 应用层使用 LangChain / LangGraph 单一路径

以下通用能力默认由 LangChain / LangGraph / LangSmith 提供：

- chat model adapter 和 provider 配置；
- prompt template、Runnable 组合和 structured output；
- typed tool schema、tool invocation 和 graph 路由；
- retriever / Document adapter；
- graph compile、checkpoint adapter 和运行配置；
- callback、trace、eval 和采样。

因此不再新增：

- 直接面向文本对话的 OpenAI SDK 调用封装；
- 与 LangChain tool 并行维护的 function schema；
- 第二套手写 tool loop 或 graph runner；
- 手写通用 JSON 提取、重试、fallback 或消息协议转换；
- 每请求创建模型客户端、HTTP transport 或编译 graph 的路径；
- 作为主要观测链路但没有持久 sink 的自研 trace 数组。

ASR、图片协议等框架没有合适抽象的专用能力可以保留窄 SDK adapter，但不得顺带承载文本对话编排。

缓存 compiled graph 前必须先消除工具对单次 session 的闭包捕获，请求身份和会话上下文只通过 state/config 传入。标准 tracing 的 metadata 过滤也不能替代 prompt、completion 和 tool result 脱敏；输入输出隐藏和实际导出检查完成前，LangSmith 生产外发保持关闭。

### 3. 业务领域层不交给 LangChain

以下能力继续由 `api -> service -> repository -> models` 管理：

- 身份认证、授权和资源归属；
- 商品、价格、库存、订单、支付和退款状态机；
- Unit of Work、数据库约束、inbox/outbox 和业务幂等；
- 客户同意、撤回、删除、TTL 和数据脱敏；
- Webhook 验签、重放防护、发布、备份和恢复；
- 员工事实回复 finalizer、事实 guard 和人工接管规则。

这些能力优先使用各自领域的标准库、官方 SDK 或成熟中间件。LangChain tool 只调用领域 service，不直接读写数据库，也不决定授权、金额或履约状态。

### 4. 兼容路径必须限时

迁移期间允许 thin facade 或 feature flag，但必须同时满足：

- 只有一个生产默认路径；
- 旧路径只用于同一发布列车内回滚；
- 新旧路径不得长期双写或分别维护业务规则；
- 迁移工作包必须写明旧入口删除或收缩条件；
- 最迟在下一个发布列车结束前删除旧通用实现，或提交例外 ADR。
- 旧调用点必须通过静态搜索归零；只新增 adapter、没有删除旧入口不算迁移完成。

### 5. 框架选型不是无条件引入依赖

引入新组件前必须检查：

- 是否解决已确认问题，而不是只减少几行代码；
- 维护活跃度、许可、Python 版本和当前依赖兼容性；
- 生产内存、进程模型、外部服务和运维成本；
- 失败语义、幂等、恢复和可观测能力；
- 隐私、数据出境和密钥边界；
- 能否通过薄 adapter 隔离，避免业务代码绑定框架细节。

不在 P0/P1 整改中为追求统一而同时引入 ORM、消息队列和迁移框架的大规模重写。先止血并建立正确合同，再按独立工作包替换基础设施。

## Alternatives

- 全部自研：依赖少，但会继续重复实现模型协议、工具调用、图编排、structured output、trace 和 eval，维护成本最高。
- 全部交给 LangChain：表面统一，但认证、支付、事务和数据治理会失去清晰领域边界，不可接受。
- 框架和自研长期双轨：短期回滚方便，长期产生行为漂移和两套测试，明确拒绝。

## Consequences

- AI 通用能力会逐步收敛到一套 LangChain / LangGraph 运行路径。
- 业务领域代码不会因为框架迁移而减少，重点转为合同、状态机和一致性测试。
- 迁移期可以有短暂 adapter，但每个 adapter 都需要退出条件。
- 新依赖需要最小 spike 和资源评估，不能以“框架优先”为由无条件扩张技术栈。
- 现有 LangChain E1-E6 生产增强工作在全局 P0/P1 门禁关闭前暂停扩大生产范围。

## Verification

- 搜索生产代码中的直接模型 SDK 调用、重复 tool schema、手写 tool loop 和每请求 graph 构造。
- Agent 相关改动运行 customer / employee graph、tool registry、structured output 和 eval 门禁。
- 每个迁移工作包记录保留的领域代码、删除的通用代码和例外原因。
- 发布前确认只有一个生产默认编排路径，旧路径不存在长期双写。

## Current Evidence

- 2026-07-11 已落地 LangChain 模型 registry 和共享 HTTP transport，`get_langchain_chat_model` 不再每次创建 client，lifespan shutdown 统一释放 registry 资源。
- 2026-07-11 已新增共享 provider resolver，文本 `chat_completion`、LangChain 工厂和 query rewrite 的默认 provider 解析口径统一为 MiMo；显式非 MiMo 模型才进入 DeepSeek fallback。
- 2026-07-11 文本 `chat_completion` 已改为 LangChain model/Runnable，OpenAI SDK client 仅保留 ASR 窄 adapter；这一步删除了通用文本 SDK 生产路径。
- 2026-07-12 customer graph 工具执行已改用 LangGraph `ToolNode`；生产工具和测试替身统一采用 `StructuredTool` 与 `AIMessage`，不保留旧式任意对象 `ainvoke` 的手工执行旁路。customer ToolNode 定向回归和全量测试通过。
- 2026-07-12 customer graph state 已统一保存 LangChain `BaseMessage`；字典消息只在上下文构造、外发隐私适配和测试断言边界使用。删除了旧 tool 参数 parser/message append helper，并补充工具参数中裸订单号的外发脱敏合同。
- 2026-07-12 employee structured planner 已直接把 `with_structured_output(EmployeeStructuredPlan)` 映射为领域 `AgentPlan`，删除 `model_dump -> json.dumps -> parse_llm_plan` 和旧 `chat_completion` JSON fallback；失败只回到已有规则规划。
- 2026-07-12 customer RAG 的 `hybrid`、`planned-hybrid`、`planned-hybrid-rerank` 已统一通过同一个 LangChain `BaseRetriever` adapter；query expansion 和 rerank 只作为策略注入，small-talk 的关键词检索保留为明确领域分支。
- 2026-07-12 增加可注入本地 JSONL trace sink：只接收已脱敏 `AgentTraceRun`，哈希 `conversation_id`，异步写入且 sink 失败不影响回复；默认空路径保持关闭，生产启用和真实导出仍受隐私/发布门禁约束。
- 2026-07-12 R4-B 增加独立 AES-256-GCM SQLite 备份首片：密钥由仓外 32 字节 key file 提供，备份封装 nonce、版本和 SHA-256 元数据，拒绝覆盖并在解密临时库上执行 integrity check；不把密钥托管或生产备份位置伪装成本地测试证据。
- 2026-07-12 R4-C 将 Python 3.11 slim base image 固定到已核对 digest，并补充 Dockerfile 合同测试；本机 Docker/Scout 不可用，真实 build、容器 smoke 和漏洞扫描保持未验证。
- 2026-07-12 R5 checkpoint 取舍完成：当前没有暂停恢复需求，删除未启用的 `MemorySaver`、checkpointer 注入和对应测试；客户 graph 保留 `thread_id` 仅作为运行/trace 关联配置，不把 thread_id 伪装成 checkpoint。
- 2026-07-12 employee graph 通用工具执行改用 LangGraph `ToolNode`；订单查询 service 保留为领域层例外，避免把授权、查询计划和事实 finalizer 塞进通用工具节点。
- 2026-07-12 R4-A readiness 重型检查改为启动期 snapshot：NumPy embedding、SQLite schema 和 admin dist 检查只在 lifespan 初始化后计算一次，`/ready` 优先读取快照，未初始化时保留实时回退。
- 2026-07-12 R6 类型质量首片：仓储 cursor 返回值显式收窄为 `bool`，JSON 配置列表先做结构校验；7 个相关 repository 文件 mypy 独立通过，未改变事务和 SQL 语义。
- 2026-07-12 R6 Agent 类型质量首片：`rag/documents.py`、`llm.py`、`customer/model.py`、`employee/nodes.py` 4 个 Agent 文件独立 mypy 通过；定向 Agent 回归 23 项通过，未将该首片表述为全仓 Agent mypy 清零。
- 2026-07-12 R6 Harness 证据完整性首片：`check_evidence_index.py` 校验本地文件/目录引用，输出本地文件 SHA-256；历史重命名路径通过显式 alias 解析，生产路径保留为外部未验证引用，未把本地结果冒充生产证据。
- 2026-07-12 R6 后台最小 Playwright E2E：真实浏览器链路覆盖登录/订单页、向量接口未登录 401 与 Cookie 会话、`/ready` degraded 503 语义；E2E 暴露的请求体 receive 递归已修复并有回归测试，未使用自有 API mock。
- 2026-07-12 R6 分层收敛首片：`AdminService` 不再通过 `KnowledgeRepo._db` 临时构造知识商品、知识管理和历史仓储，改由组装根显式注入；随后继续完成知识实时增强和 LLM 工具上下文的依赖收敛。
- 2026-07-12 R6 商品工具职责拆分：`function_tool_product.py` 只保留商品检索/工具编排，缓存、实时 API 刷新、RAG 回写和变更历史记录移入 `function_tool_product_live.py`；未保留旧实现双写路径。
- 2026-07-12 R6 Webhook 负载职责拆分：`youzan/webhook.py` 只保留签名和 JSON 解析，商品 `item_id` 多级降级提取移入 `youzan/webhook_payload.py`，事件分发器切换到新 canonical 路径。
- 2026-07-12 R6 商品事件/客服队列职责拆分：`event_item.py` 删除无调用方的旧 RAG 构建/同步实现，标签提取移入 `event_item_parser.py`；`kf_message_queue.py` 的商品卡片发送移入 `kf_card_sender.py`，队列保留消息持久化、非文本处理和会话编排。
- 2026-07-12 R6 客服输入适配拆分：`kf_message_queue.py` 的图片下载、语音转码/ASR 和非文本兜底移入 `kf_message_preprocessor.py`；队列主文件只保留持久消息、会话状态、AI 回复和 UMP 发送编排，未改变消息状态语义。
- 2026-07-12 R6 文档事实收敛：README、Harness quick reference 和 docs 导航统一到 `VERSION=0.105.19`、MiMo 默认 provider、单 worker 生产启动和加密 SQLite 备份；不再把旧版本、四 worker 或明文复制备份作为当前操作说明。
- 2026-07-12 R5 prompt/Runnable 收敛：query rewrite 与 handoff 摘要默认路径改用 `ChatPromptTemplate | LangChain model | StrOutputParser`，保留显式 caller 仅作为测试/边界注入；`chat_completion` 剩余调用已缩小到意图识别、会话摘要和离线 Agent，未将该首片表述为全部文本能力完成。
- 2026-07-12 R5 意图识别收敛：意图识别默认路径也改用 `ChatPromptTemplate | LangChain model | StrOutputParser`，保留原有 `LLMError` 回退合同；兼容调用剩余会话摘要和三个离线 Agent。
- 2026-07-12 R5 离线文本路径收敛：会话摘要、知识缺口和离线质检已改用统一 Runnable，保留各自 JSON 校验、重试和业务回退；`agent_memory.py` 是当前唯一剩余的 service 层 `chat_completion` 调用。
- 2026-07-12 R5 文本路径收口：顾客画像 memory 也已迁移并删除通用 `chat_completion` facade；`app/service` 和测试中的旧文本调用静态扫描归零，`client.py` 仅保留 ASR SDK adapter。
- 2026-07-12 R6 质量门禁收敛：全仓 `app tests scripts` 的 Ruff check 通过，补修 5 个链式运维测试脚本中的 19 个存量问题；格式化检查仍有 6 个既有文件提示，未将格式化噪音与本轮行为整改混在一起。
- 2026-07-12 R6 分层收敛完成：知识实时增强、客户 graph 工具上下文、订单/物流工具和商品 RAG 实时刷新改为显式注入仓储与向量依赖；`rg "repo\\._db|knowledge_retriever\\._repo\\._db|repository\\._db" app/service --glob "*.py"` 零命中。`YouzanEventHandler` 保留显式事件处理依赖，不以兼容测试替身绕过组装根。
- 本首片不代表 LangSmith callback 外发或生产 trace 导出已经完成；这些仍按全局整改计划 R5 分阶段收敛。
- 生产 trace 外发仍受 R3 隐私门禁约束，未因 registry 首片而自动开启 LangSmith。
