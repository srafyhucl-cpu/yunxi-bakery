# Bakery Commerce Platform — 检索与 Agent 化升级架构设计

> 适用：开发者 / 架构评审
> 核心问题：在不牺牲实时客服 SLA 的前提下，如何升级检索质量，并引入规划、反思、长期记忆与多 Agent 编排能力？
> 版本：v2（2026-06-09）
> 状态：设计评审中，未进入实现
>
> 说明：这份文档关注检索与 Agent 能力升级路线，写于 canonical 领域重组之前。若文中的文件路径、模块组织或产品命名与当前仓不一致，优先以 `docs/architecture/project-boundaries.md` 和现有代码目录为准。

本方案包含两条**正交**的升级线，可独立推进、互不阻塞：

- **线 A — 检索质量升级**（第三章）：热路径内的纯检索优化（BM25 + jieba + RRF 混合检索），不引入任何 LLM 往返，风险最低，建议先行。
- **线 B — Agent 化能力**（第四~七章）：长期记忆、确定性校验、离线质检与多 Agent 编排，以「热 / 冷路径分离」为核心。

______________________________________________________________________

## 一、设计目标与约束

### 1.1 目标

1. **检索质量升级**：把现有「向量 + LIKE 兜底」的半成品混合检索，升级为 BM25 + 向量 + RRF 融合的正经混合检索，提升长尾与专有名词召回。
2. **长期记忆**：跨会话记住顾客称呼、口味偏好、最近订单、过敏原。
3. **反思（确定性校验）**：回复投递前做规则级自检，拦截幻觉、错误价格、越权承诺、食品安全风险。
4. **离线质检与知识缺口挖掘**：复盘会话质量，从「答不上来」的问题反推知识库补全建议。
5. **多 Agent 编排**：以上离线能力由编排器串联，形成可调度的离线流水线。

### 1.2 硬约束（来自现状，不可违反）

| 约束 | 现状事实 | 设计影响 |
| :--- | :--- | :--- |
| 实时延迟 | 顾客在企微 / 有赞实时等回复；现链路 = 意图识别 + RAG + 客户工具轮次上限 | **热路径禁止新增任何 LLM 往返**；纯 CPU 检索优化（线 A）不在此列 |
| 硬件 | 2 核 2GB | 离线任务必须低频、可批处理、与热路径资源隔离；检索索引须 CPU 友好、内存可控 |
| LLM | 小米 MiMo（`MIMO_CHAT_MODEL`，`MIMO_TIMEOUT_SECONDS=120`） | 离线 Agent 复用同一 `chat_completion` 入口，对延迟不敏感 |
| 身份键 | `sessions(channel, user_id)` 稳定（见 `app/migrations/schema.py`） | 长期记忆以 `(channel, user_id)` 为主键，身份对齐由渠道天然保证 |
| 业务性质 | 食品（烘焙） | 过敏 / 安全类信息只能「提醒」，**禁止 Bot 自主下「能否食用」结论** |

### 1.3 核心设计决策：热 / 冷路径分离

将昂贵、非确定性的 Agentic 步骤（规划、LLM 反思、多 Agent）全部下沉到**离线冷路径**；
热路径只增量挂载**低成本、确定性**的组件：混合检索（线 A）、只读记忆注入、规则校验门。

> 决策依据：实时客服的核心质量指标是延迟、成本、确定性与可靠性。规划 / LLM 反思 / 多 Agent 的本质都是「在链路上追加 LLM 往返」，与实时客服的核心指标直接冲突；而 BM25 + RRF 是纯 CPU 统计计算（微秒级），不构成 LLM 往返，可安全置于热路径。

______________________________________________________________________

## 二、总体架构（含线 A 检索改造）

```text
┌──────────────────── 热路径（实时，确定性，禁止新增 LLM 往返）────────────────────┐
│                                                                                │
│  Webhook → 队列(BaseWeComMessageQueue) → ChatService.handle_message            │
│                    │  handle_chat_message (chat_message_flow.py)               │
│                    ├─ 去重 / 建会话 / 落库用户消息                              │
│                    ├─[线B 新] 只读拉取 customer_profile（一次主键查询，~ms）     │
│                    ├─ 意图识别 detect_intent_with_timing (chat_intent.py)       │
│                    │                                                           │
│                    ├─ 知识检索 KnowledgeRetriever.search()                      │
│                    │   ┌───────────────────────────────────────────────┐      │
│                    │   │ query rewrite 改写                              │      │
│                    │   │   ├─ 向量通道 bge 本地语义（已有）             │      │
│                    │   │   └─[线A 新] BM25 通道 jieba 分词 + BM25 打分   │      │
│                    │   │        └─[线A 新] RRF 融合（取代纯拼接去重）    │      │
│                    │   │   → 注入主推款 → 实时库存/价格反查（已有）      │      │
│                    │   └───────────────────────────────────────────────┘      │
│                    │       └─[线B 新] 把 profile 注入 system prompt            │
│                    │                                                           │
│                    ├─ 单 Agent + 有界 tool loop (chat_llm.py，保持不动)         │
│                    └─[线B 新] 确定性校验门 (chat_reply.postprocess_reply 扩展)  │
│                            └─ 纯规则，不调 LLM；命中→改写 / 转人工 / 埋点        │
│                                                                                │
└────────────────────────────────────────────────────────────────────────────────┘
                                     │ 落库 messages / sessions / analytics_events
                                     ▼ （冷路径只读这些表）
┌──────────────────── 冷路径（离线，可慢，多 Agent 合法区）─────────────────────────┐
│                                                                                │
│  OfflineReviewScheduler（lifespan asyncio.Task，低频 / 夜间触发）               │
│        │  orchestrator.run_once()                                              │
│        ├─ Agent① 会话质检    → conversation_reviews 表                          │
│        ├─ Agent② 知识缺口    → knowledge_gaps 表（人工审核后才进 knowledge_base）│
│        └─ Agent③ 记忆固化    → customer_profiles 表（过敏走安全规则）           │
│                                                                                │
└────────────────────────────────────────────────────────────────────────────────┘
```

**解耦原则**：

- 线 A 改动收敛在 `KnowledgeRetriever.search()` 内部，输入输出契约不变（进 `query`、出 `list[KnowledgeEntry]`），上下游无感。
- 冷路径**只读**热路径产出（`messages` / `human_transfers` / `analytics_events`），**只写**自己的新表（`conversation_reviews` / `knowledge_gaps`）与 `customer_profiles`。
- 冷路径整体故障**不影响**实时回复。
- 热路径读 `customer_profiles` 失败时空记忆降级，**绝不阻断回复**（沿用 `chat_context.load_knowledge_entries` 检索失败 `return []` 的现成范式）。

______________________________________________________________________

## 三、线 A — 检索质量升级（BM25 + jieba + RRF 混合检索）

### 3.1 现状诊断（为什么要改）

当前 `KnowledgeRetriever.search()`（`app/service/knowledge_retriever.py:44-69`）的「混合」是半成品：

1. **向量通道正常**：`EmbeddingSearcher` 用本地 `bge-small-zh-v1.5` 做语义检索（已是本地推理，非 API）。
2. **关键词通道几乎失效**：`KnowledgeRepo.search()`（`knowledge_repo.py:23-32`）是 `WHERE title/content/keywords LIKE %query%`，**拿整句 query 去模糊匹配**。顾客问「草莓蛋糕多少钱」时，整句几乎不可能命中任何字段——关键词通道形同虚设，因为它**没有分词**。
3. **融合是纯拼接**：`_merge_entries()`（`knowledge_retriever.py:132-147`）只是「向量结果在前、关键词结果垫后、去重、截断」，**没有分数融合**。一条「两个通道都排前」的强信号文档，得不到任何加权。

结论：现状是「**有向量检索 + 一个不工作的关键词兜底 + 无融合**」，不是真正的混合检索。线 A 补齐这三点。

### 3.2 目标方案

```text
query ──rewrite──┬──▶ 向量通道（bge 本地）         ──▶ 排序结果 A（key→rank）
                 └──▶ BM25 通道（jieba 分词 + BM25） ──▶ 排序结果 B（key→rank）
                                                            │
                                       RRF 融合 score(d)=Σ 1/(k + rank_i(d))
                                                            │
                                                            ▼  融合后 top-K
                                          注入主推款 → 实时库存/价格反查（不变）
```

**RRF（Reciprocal Rank Fusion）公式**：对每个文档 d，融合分

```
score(d) = Σ_i  1 / (k + rank_i(d))
```

- `rank_i(d)`：文档 d 在第 i 个通道结果中的排名（从 1 起；未召回则该项不计）。
- `k`：平滑常数，取经验值 **60**（RRF 论文默认，弱化头部名次的过度主导）。
- 用 RRF 而非「加权分数相加」的原因：向量的 cosine 分数与 BM25 分数**量纲不可比**，直接加权需要脆弱的归一化调参；RRF 只用**排名**，天然跨通道可比、无需归一化，工程上稳健。

### 3.3 改造点（全部收敛在检索层）

| # | 改动 | 文件 | 说明 |
| :--- | :--- | :--- | :--- |
| 1 | 新增 BM25 索引器 | `app/service/bm25_search.py`（新） | 封装 jieba 分词 + `rank_bm25` 的 `BM25Okapi`；接口对齐 `EmbeddingSearcher`：`build(docs)` / `search(query, limit) -> list[(key, score)]` |
| 2 | 启动构建 BM25 索引 | `app/lifespan_vector.py` | 与向量索引同源构建：复用 `KnowledgeRepo.get_all_titles_with_keys()` 的 `(key, title, content)`，分词后建 BM25。纯内存、无磁盘模型，重建成本极低 |
| 3 | RRF 融合替换纯拼接 | `app/service/knowledge_retriever.py` | 新增 `_fuse_results(vec_ranked, bm25_ranked, limit)` 取代 `_merge_entries`；`search()` 内并行取两路 rank 列表后融合，再回表取 entries |
| 4 | 注入 BM25 实例 | `KnowledgeRetriever.__init__` | 新增 `bm25: BM25Searcher \| None = None` 入参，模式同现有 `vs` |

**关键实现约束**：

- BM25 检索在 `asyncio.to_thread` 中执行（同现有向量 `await asyncio.to_thread(self._vs.search, ...)`，`knowledge_retriever.py:59`），不阻塞事件循环。
- 融合在拿到两路 **key→rank** 后进行，**再用融合后的 key 集合一次性回表** `get_by_youzan_item_ids()`，避免两次回表。
- BM25 缺失（`bm25 is None` 或空索引）时自动退化为「仅向量」，**不阻断检索**（同现状容错风格）。
- `_inject_featured` 与 `_prepend_live_data`（主推款注入、实时库存反查）**保持不动**，接在融合之后。

### 3.4 依赖与资源

| 项 | 选型 | 资源影响 |
| :--- | :--- | :--- |
| 中文分词 | `jieba`（纯 Python） | CPU 微秒级；首次 import 加载词典约几十 MB 内存，可接受 |
| BM25 | `rank_bm25`（纯 Python，`BM25Okapi`） | 索引为内存中的词频结构，知识库百条量级内存可忽略 |
| 融合 | 自实现 RRF（几行，无依赖） | 纯计算，无额外依赖 |

新增依赖写入 `requirements.in` 后 `pip-compile` 锁定（遵循现有 pip-tools 流程）。

> **延迟评估**：BM25 检索 + RRF 融合在百条知识库上是亚毫秒级，相对一次 MiMo 往返（百毫秒~秒级）完全淹没，顾客无感。线 A 不违反 1.2 的热路径延迟约束。

### 3.5 评测（改造的验收前提）

检索改造最大的风险是「改完感觉变好、实则未必」。线 A 必须配一个**离线评测集**做改造前后对比，否则不允许上线：

1. **数据来源**：从现有 `messages` 表捞**真实顾客问法**（`role='user'`），人工标注每条「应当召回的知识 key」（商品 `youzan_item_id` 或 `kb_{id}`），构成 30~50 条标注集。
2. **指标**：`Recall@K`、`MRR`（平均倒数排名）。
3. **对比**：同一评测集上跑「纯向量（现状）」vs「向量+BM25+RRF（线 A）」，要求 `Recall@K` 不降、长尾问法（专有名词、短词）明显提升。
4. **载体**：新增 `scripts/eval_retrieval.py`（离线脚本，不进热路径），输出对比报告。评测集 JSON 纳入 `tests/fixtures/`。

> 该评测脚本同时是「检索效果可量化」的工程资产，后续 embedding 领域微调（见第八章）也复用同一评测集判断收益。

### 3.6 明确不做：cross-encoder 重排序（rerank）

经评估，rerank 在本系统**两条路径都不适用**，明确排除：

- **热路径不可行**：cross-encoder（如 `bge-reranker-base`）需对每个候选 query-doc 对过一次模型，2 核 2GB 上重排 20 个候选可能数百 ms~1s+，违反延迟约束。
- **冷路径喂不饱**：rerank 的冷路径价值在于「为高频重复 query 预计算并缓存最佳结果」。但本系统是「对话式客服 + 实时电商数据」——① 价格/库存由 `_prepend_live_data` 现场反查，结果无法缓存；② 客服对话 query 高度发散，缓存命中率极低；③ 真正瓶颈是 LLM 往返而非检索精度。预计算收益≈0，是纯负债。

> 结论：rerank 是「静态知识库问答」的标配，但本系统是「对话 + 实时数据」客服，场景不同则取舍不同。能说清「为什么这个常见组件在本场景不适用」，比硬塞一个更重要。

______________________________________________________________________

## 四、线 B — 数据层变更

新增 3 张表，写入 `app/migrations/schema.py`，沿用现有 WAL / 索引 / `*_json` 命名风格。无破坏性变更（纯加表，可独立上线）。

### 4.1 `customer_profiles` — 长期记忆

热路径只读，冷路径 Agent③ 写。

| 列 | 类型 | 说明 |
| :--- | :--- | :--- |
| `id` | TEXT PK | uuid4 |
| `channel` | TEXT | 渠道标识 |
| `user_id` | TEXT | 渠道用户 ID |
| `display_name` | TEXT | 顾客称呼 |
| `preferences_json` | TEXT | 口味 / 尺寸 / 甜度偏好（JSON） |
| `order_summary_json` | TEXT | 最近订单摘要（JSON，复购场景用） |
| `allergens_json` | TEXT | **过敏原标记（JSON），单独成列，绑定安全规则** |
| `consent_status` | TEXT | 记忆留存同意态（unknown / granted / revoked） |
| `source_evidence_json` | TEXT | 每条画像事实指向来源 session_id / message_id，可审计回溯 |
| `last_interaction_at` | TEXT | 最近交互时间（北京时间，`now_str()`） |
| `created_at` / `updated_at` | TEXT | 时间戳 |

约束与索引：

- `UNIQUE(channel, user_id)` —— 身份对齐主键。
- `idx_cp_channel_user ON (channel, user_id)`。

### 4.2 `conversation_reviews` — 会话质检结果

冷路径 Agent① 写。

| 列 | 类型 | 说明 |
| :--- | :--- | :--- |
| `id` | INTEGER PK AUTO | |
| `session_id` | TEXT FK | 关联 sessions |
| `quality_score` | INTEGER | 0–100 |
| `issues_json` | TEXT | 问题清单（答错 / 答漏 / 态度 / 安全，JSON 数组） |
| `reviewer_model` | TEXT | 评审所用模型名（可追溯） |
| `reviewed_at` | TEXT | 评审时间 |

索引：`idx_cr_session ON (session_id)`、`idx_cr_score ON (quality_score)`。

### 4.3 `knowledge_gaps` — 知识缺口建议

冷路径 Agent② 写，**人工审核后**才进 `knowledge_base`。

| 列 | 类型 | 说明 |
| :--- | :--- | :--- |
| `id` | INTEGER PK AUTO | |
| `question_norm` | TEXT | 归一化后的高频问题 |
| `frequency` | INTEGER | 出现次数 |
| `status` | TEXT | open / proposed / resolved / rejected |
| `proposed_answer` | TEXT | Agent 起草的候选答案 |
| `related_sessions_json` | TEXT | 来源会话 ID 列表（JSON） |
| `created_at` / `updated_at` | TEXT | 时间戳 |

索引：`idx_kg_status ON (status)`、`idx_kg_freq ON (frequency)`。

> 设计克制：只加 3 张表，不引入图数据库 / 向量记忆库。SQLite + 现有 repo 模式足够，避免引入新运维面。

______________________________________________________________________

## 五、线 B — Repository 层变更

新增 3 个 repo，继承 `BaseRepository`（`app/repository/base.py`），沿用 Context-Local 连接 + `self._db.execute / commit` 范式。

### 5.1 `CustomerProfileRepo`（`app/repository/customer_profile_repo.py`）

```python
class CustomerProfileRepo(BaseRepository):
    async def get(self, channel: str, user_id: str) -> CustomerProfile | None: ...
    async def upsert(self, profile: CustomerProfileUpsert) -> CustomerProfile: ...
    async def touch_interaction(self, channel: str, user_id: str) -> None: ...
```

- `get`：单条主键查询，热路径调用，必须快且容错（异常时上层吞掉返回 None）。
- `upsert`：冷路径 Agent③ 调用，按 `UNIQUE(channel, user_id)` 做 `INSERT ... ON CONFLICT ... DO UPDATE`。

### 5.2 `ConversationReviewRepo`、`KnowledgeGapRepo`

仅冷路径调用，提供 `create` / `list_by_*` / `update_status`，模式同 `TransferRepo`（见 `app/repository/transfer_repo.py`）。

### 5.3 装配

在 `app/main.py` 的 `_init_repositories()` 中以 `None` 占位初始化（沿用现有 13 个 repo 的占位范式），由 `db_session_scope` 在请求 / 任务上下文注入连接。

______________________________________________________________________

## 六、线 B — 热路径改造（两处，均低风险、可开关）

### 6.1 只读长期记忆注入

**落点**：`app/service/chat_context.py`。

**改造点**：

1. `prepare_chat_context()` 新增可选入参 `profile: CustomerProfile | None`。
2. 在 `build_system_prompt()`（`app/service/llm/prompt.py`）的模板中新增「## 顾客档案」段落占位，由 profile 渲染。
3. 加载时机：在 `chat_message_flow.complete_ai_reply()` 调用链中，于检索之前用 `CustomerProfileRepo.get(channel, user_id)` 拉取一次。

**注入语义（关键）**：

- 普通偏好直接拼接，例如「顾客偏好：少糖、6 寸」。
- **过敏原必须写成给 AI 的提醒指令，而非判断结论**：

  > 「该顾客登记过敏原：坚果。涉及成分时主动提醒顾客核对，**不要替顾客判断能否食用**。」

  禁止注入「该顾客能吃 / 不能吃 X」这类结论性语句。

**容错**：profile 查询为 None 或抛异常 → 空档案继续，记一条 warning，**不阻断回复**。

**开关**：新增配置项 `ENABLE_CUSTOMER_MEMORY`（默认 false），灰度开启。

### 6.2 确定性校验门（规则反思，不调 LLM）

**落点**：`app/service/chat_reply.py` 的 `postprocess_reply()` 之后、`save_assistant_reply()` 之前，新增 `apply_reply_guard()`。

**校验规则（纯确定性，微秒级）**：

| # | 规则 | 命中动作 |
| :--- | :--- | :--- |
| 1 | **商品白名单**：回复中出现的商品名必须 ∈ 本轮检索注入的商品标题集合 | 复用并强化现有反幻觉机制；越界则改写 / 转人工 |
| 2 | **价格校验**：回复中的价格数字须来自工具返回或知识库 | 否则掩码价格并追加「具体价格请咨询客服确认」 |
| 3 | **配送承诺闸**：禁止自主承诺具体送达日期 / 时间 | 改写为「以门店实际排期为准」 |
| 4 | **食品安全闸**：命中过敏 / 成分 / 医疗 / 安全关键词 | 强制转人工或仅追加安全提示，**Bot 不自主下结论** |

**实现要点**：

- 规则 1 需要把「本轮检索注入的商品标题集合」从 `prepare_chat_context` 传递到校验门（目前该集合在 `build_system_prompt` 内部构造，需提升为可返回值）。该集合正是线 A 融合后 top-K 中 `category=='product'` 的标题，两条线在此自然衔接。
- 命中规则记一条 `analytics_events`（`event_type="reply_guard_hit"`），复用 `record_reply_latency` 的埋点范式，便于后续度量拦截率。
- 校验门是「反思」的确定性降级版：把昂贵的 LLM 自评换成廉价可靠的规则，符合 1.2 的热路径约束。

______________________________________________________________________

## 七、线 B — 冷路径：离线多 Agent 流水线

### 7.1 调度器

**落点**：`app/main.py` lifespan 的 `_start_background_tasks()`（现为返回空 set 的任务注册点）。

新增 `OfflineReviewScheduler`，复用 `BaseWeComMessageQueue`（`app/service/wecom/base_queue.py`）同款 `asyncio.Task` + 单条异常隔离 + 优雅 `stop()` 范式：

- 触发方式：固定间隔（默认每 6 小时）或夜间定时（可配 `OFFLINE_REVIEW_CRON_HOUR`）。
- 每轮调用 `orchestrator.run_once()`。
- 任务强引用加入 `bg_tasks` 集合（防 GC，沿用现有范式）。
- 关闭时 `await scheduler.stop()`。

### 7.2 编排器与 Agent

**新增模块**：`app/service/offline/`

```text
app/service/offline/
├── orchestrator.py        # run_once()：按序调度三个 Agent，单 Agent 失败隔离
├── agent_qa_review.py     # Agent① 会话质检
├── agent_knowledge_gap.py # Agent② 知识缺口挖掘
└── agent_memory.py        # Agent③ 记忆固化
```

所有 Agent 通过现有 `app/service/llm/client.py` 的 `chat_completion(messages, tools=None)` 调用 LLM（不传 tools，纯文本/JSON 输出），在 `db_session_scope` 上下文内运行以复用 repo 连接路由。

| Agent | 输入（只读） | LLM 职责 | 输出（只写） | 必须离线的原因 |
| :--- | :--- | :--- | :--- | :--- |
| **① 质检** | 当天 closed / 转人工会话的 messages | 打质量分、列出答错 / 答漏 / 态度问题 | `conversation_reviews` | 每会话一次 LLM 调用，热路径扛不住 |
| **② 知识缺口** | 低分会话 + `human_transfers.reason` + 答不上来的问句 | 跨会话聚类归一、起草候选答案 | `knowledge_gaps`（待人工审核） | 聚类需跨多会话，天然批处理 |
| **③ 记忆固化** | 单顾客历史会话 | 抽取结构化画像事实（偏好 / 订单 / 过敏） | `customer_profiles`（upsert） | 写记忆不能放在回客户的关键路径上 |

### 7.3 编排顺序与失败隔离

```python
# orchestrator.run_once() 伪代码
async def run_once() -> None:
    async with db_session_scope() as conn:
        reviews = await _safe(agent_qa_review.run, conn)        # ① 不抛
        await _safe(agent_knowledge_gap.run, conn, reviews)     # ② 依赖①输出
        await _safe(agent_memory.run, conn)                     # ③ 独立
# _safe：捕获并记录单 Agent 异常，不中断整轮（同 base_queue 的异常隔离思想）
```

______________________________________________________________________

## 八、安全与责任边界

| 项 | 规则 |
| :--- | :--- |
| **过敏 / 食品安全** | 存储并用于「提醒顾客与人工客服」；**禁止 Bot 自主判定能否食用**；命中即转人工或仅提醒。 |
| **PII 最小化** | 电话 / 地址等按 key 名引用、必要才存；`consent_status` 控制留存；画像变更全部可审计（`source_evidence_json` 指回来源会话）。 |
| **记忆写入隔离** | 仅冷路径写 `customer_profiles`，抽取出错不影响实时回复，且有审计兜底。 |
| **知识缺口需人工采纳** | Agent② 只产出 `knowledge_gaps` 建议，**不自动写入** `knowledge_base`，避免错误知识自我污染。 |
| **校验门埋点** | 所有拦截命中落 `analytics_events`，可度量、可回归。 |

______________________________________________________________________

## 九、配置新增（`app/config.py`）

| 字段 | 默认 | 所属 | 说明 |
| :--- | :--- | :--- | :--- |
| `ENABLE_HYBRID_RETRIEVAL` | `false` | 线 A | BM25+RRF 混合检索总开关（灰度；关闭时退化为现状纯向量+LIKE） |
| `RRF_K` | `60` | 线 A | RRF 平滑常数 |
| `ENABLE_CUSTOMER_MEMORY` | `false` | 线 B | 热路径记忆注入总开关（灰度） |
| `ENABLE_REPLY_GUARD` | `false` | 线 B | 确定性校验门总开关（灰度） |
| `ENABLE_OFFLINE_REVIEW` | `false` | 线 B | 离线流水线总开关 |
| `OFFLINE_REVIEW_INTERVAL_HOURS` | `6` | 线 B | 离线调度间隔 |
| `OFFLINE_REVIEW_MAX_SESSIONS` | `200` | 线 B | 单轮质检会话上限（控成本） |

所有开关默认全关，确保合入后线上行为零变化，逐项灰度。

______________________________________________________________________

## 十、分阶段实施

两条线正交，可并行；每阶段独立可上线、可回滚（靠配置开关）。

| 阶段 | 线 | 内容 | 风险 | 验收 |
| :--- | :--- | :--- | :--- | :--- |
| **A0** | A | 评测脚本 + 标注集（`scripts/eval_retrieval.py` + fixtures） | 极低（离线脚本） | 跑出现状基线 `Recall@K` / `MRR` |
| **A1** | A | BM25 索引器 + lifespan 构建 + RRF 融合（开关默认关） | 低（收敛在检索层，可回退） | 开关关闭行为零变化；开启后评测集召回不降、长尾提升 |
| **P0** | B | 3 张新表 + 3 个 repo + 迁移 + 单测 | 极低（纯加表） | 迁移幂等、repo 单测通过、`pytest` 全绿 |
| **P1** | B | 热路径记忆注入 + 确定性校验门（开关默认关） | 低（只读 + 纯规则） | 开关关闭时行为零变化；开启后注入/拦截单测通过 |
| **P2** | B | 冷路径 Agent① 质检 + 调度器 | 低（离线，不碰线上） | 离线跑通、`conversation_reviews` 落库、异常隔离生效 |
| **P3** | B | Agent②③ + orchestrator | 中（多 Agent，但离线） | 三 Agent 串联跑通、单 Agent 失败不拖垮整轮 |

**建议落地顺序**：A0 → A1（先把检索这条最低风险、即时见效的做完并量化），再 P0 → P1 → P2 → P3。每阶段独立提交并随 `LOGBOOK.md` / 进度清单更新（遵循 `AGENTS.md` 提交收口）。

______________________________________________________________________

## 十一、测试策略

| 层 | 用例 |
| :--- | :--- |
| 检索（线A） | RRF 融合排序正确性（构造两路 rank 验证融合分）；BM25 缺失时退化为纯向量不报错；`eval_retrieval.py` 在标注集上前后对比 |
| 迁移 | 新表创建幂等、PRAGMA 一致（沿用 `tests/` 现有迁移测试模式） |
| Repo | `CustomerProfileRepo` upsert 冲突更新、`get` 命中 / 未命中 |
| 热路径记忆 | 注入开关开 / 关行为；profile 缺失降级不阻断；过敏注入为提醒语义而非结论 |
| 校验门 | 4 条规则各双样本（命中 / 不命中），命中埋点落库 |
| 冷路径 | orchestrator 单 Agent 抛异常时整轮不中断；质检结果落库；知识缺口聚合计数正确 |

目标：维持现有 `--cov-fail-under=70` 覆盖率门禁，新增模块覆盖率不低于该线。

______________________________________________________________________

## 十二、后续可选项（本方案不含，仅登记）

- **embedding 领域微调**：用 `messages` 表里「顾客真实问法 ↔ 命中知识」构造正样本对，以 `sentence-transformers` 对比学习微调 `bge-small-zh-v1.5`。训练需云 GPU 数小时，**产物仍是 256 维小模型，推理照旧本地 CPU**，生产成本不变。与线 A 正交：线 A 改「融合方式」，微调改「向量通道本身的质量」，复用第三章同一评测集判断收益。待线 A 稳定后再单独评估。

______________________________________________________________________

## 十三、明确不做（Out of Scope）

- ❌ **cross-encoder 重排序（rerank）**：热路径太重、冷路径喂不饱，本场景不适用（详见 3.6）。
- ❌ 热路径上的 planner-executor 规划循环（顾客 95% 为单轮 / 浅层意图，现有有界 tool loop 已是轻量隐式规划）。
- ❌ 热路径上的 LLM 自我反思往返（违反 1.2 延迟约束）。
- ❌ 热路径上的多 Agent 路由（现有 `chat_intent` 已做轻量意图路由；多 Agent 仅增延迟、降确定性）。
- ❌ 引入向量记忆库 / 图数据库（SQLite 足够，避免新增运维面）。
- ❌ 手搓 / 本地部署 LLM 替代 MiMo API（2 核 2GB 跑不动可用质量的模型；客服场景 API 质量/成本碾压本地小模型）。
