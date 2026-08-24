# GitHub 参考项目借鉴与可实施计划

> trace_id: `20260706-github-reference-benchmark`
> 状态：阶段 0 已冻结；阶段 1 首版能力目录已执行；阶段 2 上下文治理小切片已执行；阶段 3 知识库治理 v015/v016、入口 audience 分流、后台治理字段编辑、audience smoke、命中日志 smoke、只读日志趋势报表、后台只读 API 和后台只读页面已执行；阶段 4 员工助手能力合约清单首版已执行；阶段 5 Platform 侧和 MiniApp 仓页面 API 覆盖合约首版已执行；阶段 6 客户机器人可观测合约、MiniApp 仓可观测合约和 miniprogram-ci 发布准备合约首版已执行；主计划静态边界门禁已接入统一质量门禁和生产预检
> 日期：2026-07-06
> 适用范围：`Bakery Commerce Platform` 主仓、`Storefront MiniApp` 渠道仓、客户机器人、员工助手
> 关联文档：
> - [项目边界](./project-boundaries.md)
> - [企微员工助手开发计划书](./wecom-employee-agent-development-plan.md)
> - [企微智能机器人工具清单](./wecom-intelligent-bot-tools.md)
> - [Platform / MiniApp API 契约](./platform-miniapp-api-contract-v1.md)
> - [双机器人能力目录](./bot-capability-matrix.md)
> - [客户会话摘要设计](./customer-session-summary-design.md)
> - [客户长期记忆治理计划](./customer-memory-governance-plan.md)
> - [客户机器人可观测合约](./customer-observability-contract.md)
> - [MiniApp 页面 API 覆盖合约](./miniapp-page-api-coverage-contract.md)
> - [知识库治理兼容迁移计划](./knowledge-governance-migration-plan.md)

______________________________________________________________________

## 一、核心结论

本项目不应该照搬某一个开源项目，也不应该把两个机器人统一改造成一个全功能 Agent 平台。

更稳的路线是：

1. **客户机器人**继续走“自然语言客服 + RAG + 工具调用 + 转人工”的客服链路，重点补知识库治理、上下文压缩、引用证据、转人工原因和对话观测。
2. **员工助手**继续走“确定性规划 + 确定性工具结果 + 模板化回复”的事实链路，LLM 只保留在结构化规划兜底，不参与最终事实回复。
3. **Platform 主仓**继续作为客户、商品、订单、AI 会话、后台配置和第三方集成的业务真相源。
4. **Storefront MiniApp**继续作为前台渠道仓，只负责页面、组件、微信能力、API client 和本地体验状态。
5. **LangChain / LangGraph**可以局部引入到离线流程或实验性编排层，但不建议迁移客户热路径和员工助手主链路。

一句话：**借鉴外部项目的模块边界、治理能力和验证闭环，不借鉴它们的体量和平台化负担。**

______________________________________________________________________

## 二、当前项目拆解

### 2.1 两个代码仓

| 仓 | 当前角色 | 应继续承担 | 不应承担 |
|---|---|---|---|
| `YunxiBakeBot` | `Platform` 主仓 | 客户、商品、订单、履约、AI 会话、后台、企业微信、有赞、支付、离线复盘 | 小程序页面交互细节 |
| `YunxiBakeMiniApp` | `Storefront MiniApp` 渠道仓 | 微信小程序页面、组件、登录、支付唤起、API client、购物车和本地体验状态 | 客户主档、订单规则、商品真相、AI 主逻辑、CRM 策略 |

这条边界是合理的，后续优化应围绕“契约更清晰、发布更稳、观测更完整”推进，不需要合仓或再拆第三个仓。

### 2.2 两个机器人

| 机器人 | 用户 | 核心价值 | 失败代价 | 推荐架构 |
|---|---|---|---|---|
| 客户机器人 | 消费者 / 客户 | 快速回答、导购、安抚、转人工 | 误导客户、承诺错误、客诉 | RAG + 受控工具调用 + 人工接管 |
| 员工助手 | 店员 / 运营 / 管理者 | 快速查订单、库存、履约、待办、复盘 | 数字错误、状态错误、经营判断错误 | 规则规划优先 + LLM 结构化规划兜底 + 确定性回复 |

这两个机器人不能只用“是否用了 AI”来归类。它们的产品目标不同，容错空间不同，所以架构也应该分开。

### 2.3 当前已有资产

从当前代码和文档看，项目已经具备一些不应推倒重来的资产：

- `api -> service -> repository -> models` 分层已经成型。
- `channels/storefront` 已经承接小程序渠道 facade。
- `conversation/storefront.py`、`chat.py`、`chat_message_flow.py`、`chat_ai_loop.py` 已经形成客户客服链路。
- `knowledge_retriever.py`、`knowledge_sync.py`、`knowledge_admin.py` 已经形成知识库基础。
- `customer_memory.py`、`offline/agent_memory.py` 已经有客户记忆热路径读取和离线沉淀。
- `wecom/employee_agent_*` 已经把员工助手收口到确定性回复方向。
- `scripts/check_wecom_employee_agent_plans.py`、员工助手探针和相关测试已经形成行为验证资产。

因此，本计划的重点是“补治理、补观测、补契约、补验证”，不是“换框架重写”。

______________________________________________________________________

## 三、GitHub 参考项目分组

### 3.1 AI 客服 / RAG / 多渠道参考

| 项目 | 参考价值 | 可借鉴模块 | 不建议照搬 |
|---|---|---|---|
| [LangBot](https://github.com/langbot-app/LangBot) | 多 IM 平台接入、插件系统、知识库和流水线式配置 | channel adapter、插件注册、流水线配置、消息平台抽象 | 不照搬完整机器人平台，不把员工助手改成自由 Agent |
| [ChatWiki](https://github.com/zhimaAi/chatwiki) | AI 客服知识库、微信生态接入、后台配置 | 知识库后台、客服接入、转人工、引用来源 | 不照搬它的整体产品形态，避免后台膨胀 |
| [Tencent/WeKnora](https://github.com/Tencent/WeKnora) | 企业级 RAG、知识库、权限、评估与可观测 | 文档治理、检索评估、权限、多租户、观测 | 体量偏企业平台，不适合小店 MVP 全量采用 |
| [xliking/wechat_ai](https://github.com/xliking/wechat_ai) | 微信客服 / 企业微信客服场景接近 | 消息入口、用户配置、知识库文件上传 | 技术栈与项目不同，只看功能组织 |
| [rag-chatbot-app-with-fastapi](https://github.com/jodog0412/rag-chatbot-app-with-fastapi) | FastAPI + RAG 最小实现 | 最小 RAG API、文档上传问答 | 过于简化，不覆盖订单、转人工、企业微信、后台 |

### 3.2 微信小程序商城 / 点单 / 会员参考

| 项目 | 参考价值 | 可借鉴模块 | 不建议照搬 |
|---|---|---|---|
| [gooking/bread](https://github.com/gooking/bread) | 面包店 / 点单场景接近 | 首页、点单、商品详情、自取时间、订单、会员、FAQ | 不复制代码，只借鉴烘焙前台用户路径和字段 |
| [linlinjava/litemall](https://github.com/linlinjava/litemall) | 完整商城系统，含后台、H5、小程序和 API | 商品、购物车、订单、地址、优惠券、后台模块边界 | Java 技术栈不同，不迁移后端架构 |
| [eastworld/wechat-app-mall](https://github.com/eastworld/wechat-app-mall) | 经典微信小程序商城 | 小程序页面结构、购物流程、会员入口 | 项目较老，需要只看交互流程 |
| [iamdarcy/hioshop-miniprogram](https://github.com/iamdarcy/hioshop-miniprogram) | 精简商城小程序 | 商品列表、购物车、订单页基础体验 | 不把前端 mock 规则变成业务真相 |
| [fushengqian/fuint](https://github.com/fushengqian/fuint) | 会员营销、积分、储值、优惠券、线下门店 | 会员体系、营销模块、门店运营后台 | 当前阶段不引入复杂会员营销引擎 |
| [miniprogram-ci](https://www.npmjs.com/package/miniprogram-ci) | 微信小程序自动化上传、预览、构建 | MiniApp 发布流水线、体验版上传、CI 验证 | 非 GitHub 业务项目，只作为发布工具参考 |

核验说明：

- 本表项目在 2026-07-06 通过 GitHub API 或 npm registry 做过元数据核验。
- `fuint` 为 AGPL-3.0，后续只能借鉴会员营销能力边界，不能复制代码进入本项目。
- `miniprogram-ci` 的 npm 包可用，GitHub 仓地址未作为本文件依据。

______________________________________________________________________

## 四、可借鉴能力映射

### 4.1 通道适配层

外部参考：LangBot 的多平台适配思路。

当前问题：

- 项目已经有 `channels/storefront`，但企业微信客户客服、企微员工助手、后台工具、离线任务的入口心智还比较分散。
- 客户机器人和员工助手都接企业微信生态，但它们不是同一个产品，应避免混用同一个“智能机器人”概念。

建议落地：

| 方向 | 具体动作 | 优先级 |
|---|---|---|
| 客户通道 | 明确 `channels/customer_service` 或同等概念，承接有赞客服、微信客服、企微客服这类客户入口 | P1 |
| 员工通道 | 保留 `integrations/wecom_intelligent_bot.py` 作为员工助手入口，文档中明确它不是客户机器人 | P0 |
| 统一观测 | 所有通道统一记录 `channel_type`、`bot_type`、`intent`、`trace_id`、`handoff_reason` | P1 |

不建议：

- 不建议把客户客服和员工助手放进同一个 `AgentService`。
- 不建议让一个 LLM 自主判断“我是客服还是员工助手”。

### 4.2 知识库治理

外部参考：ChatWiki、WeKnora。

当前问题：

- 项目已有知识库、向量同步和后台管理，但“知识从哪里来、是否生效、是否过期、被哪次回答引用”还可以更清楚。
- 客户机器人和员工助手都用知识库，但使用方式不同：客户需要自然回答，员工更需要引用和原文。

建议落地：

| 能力 | 客户机器人 | 员工助手 |
|---|---|---|
| 引用来源 | 面向客户可隐藏细节，但内部日志必须记录 | 回复中可以直接列出命中的规则标题或后台路径 |
| 生效状态 | 只检索已发布内容 | 只检索已发布内容，允许员工查草稿时走后台工具 |
| 过期治理 | 配置 `effective_from / effective_to / review_status` | 同样使用，但员工回复必须暴露“资料可能过期”的提示 |
| 检索评估 | 用真实客户问法构建回归集 | 用员工问法构建意图和知识命中回归集 |

推荐新增的治理字段或概念：

- `source_type`：FAQ、商品、售后政策、配送规则、员工话术、活动规则。
- `audience`：customer、employee、both。
- `valid_from` / `valid_until`：规则有效期。
- `review_status`：draft、published、archived。
- `last_verified_at`：最后人工确认时间。
- `source_url` / `source_note`：来源证明。

这些字段不一定要一次性改表，可以先从文档和后台展示计划开始，再分批迁移。

### 4.3 上下文与长短期记忆

外部参考：RAG 项目的记忆和知识库组合思路，但业务规则需要自研。

当前判断：

- 短期记忆不应无限保留聊天全文，而应保留“最近消息 + 摘要 + 当前任务状态”。
- 长期记忆不应是 LangChain Memory 里的一串自然语言，而应是可审计的客户画像字段。
- 项目当前已有 `customer_profiles`、`customer_memory.py` 和离线 `agent_memory.py`，方向是对的。

建议补齐：

| 记忆类型 | 当前方向 | 下一步 |
|---|---|---|
| 短期上下文 | token budget + 最近消息 | 增加“会话摘要”字段，超过阈值时离线或同步压缩 |
| 客户画像 | `preferences_json`、`allergens_json`、`source_evidence_json` | 增加置信度、更新时间、可撤销状态、证据片段 |
| 员工助手记忆 | 不应记员工闲聊偏好 | 只记操作上下文，例如最近查询的订单号、客户、日期范围，且短时有效 |
| 知识缺口 | 已有离线 knowledge gap | 加入“是否已补知识库 / 是否已验证”闭环 |

LangChain 不是不能用，但它提供的是通用 memory primitive，不会自动解决：

- 客户是否同意长期记忆。
- 过敏原是不是可靠事实。
- 哪条记忆来自哪次对话。
- 记忆过期后如何撤销。
- 员工助手哪些上下文可以临时复用，哪些不能复用。

这些仍然必须由业务自己定义。

### 4.4 工具注册与能力目录

外部参考：LangBot 插件系统、员工助手当前 capabilities。

当前问题：

- 员工助手已有 capabilities，但还可以更像“能力目录”：每个工具的输入、输出、错误、权限、适用机器人、测试用例都清楚。
- 客户机器人工具调用和员工助手工具调用应共享底层 service，但不共享回复策略。

建议能力目录字段：

| 字段 | 含义 |
|---|---|
| `tool_name` | 稳定工具名 |
| `bot_type` | customer / employee / both |
| `intent` | 对应意图 |
| `input_schema` | 参数结构 |
| `output_schema` | 返回结构 |
| `permission` | 是否员工可见、客户可见、后台可见 |
| `reply_policy` | customer_natural / employee_deterministic / no_user_reply |
| `test_cases` | 对应探针或单测 |
| `fallback_policy` | 缺参数、无数据、系统异常时怎么回 |

这比直接上 LangChain Tool 更重要。LangChain Tool 可以作为适配层，但内部仍需要这张业务能力目录。

### 4.5 MiniApp 商城与点单体验

外部参考：gooking/bread、litemall、wechat-app-mall、hioshop。

当前目标：

- 小程序不承担业务真相。
- 但小程序需要具备完整消费者体验：看商品、加购、结算、支付、查订单、联系客服。

建议从外部项目借鉴的页面路径：

```text
首页
-> 分类 / 商品列表
-> 商品详情
-> 规格选择
-> 购物车
-> 结算页
-> 地址 / 自取时间 / 备注
-> 支付
-> 订单详情
-> 客服入口
```

烘焙业务特别需要补强的字段：

- 配送 / 自取日期。
- 期望送达时间。
- 蛋糕尺寸、口味、夹心、蜡烛、餐具。
- 祝福语 / 备注。
- 过敏提醒。
- 是否需要客服确认。
- 是否活动 / 团购来源。

这些字段的校验规则应放在 Platform，MiniApp 只做输入体验和错误展示。

### 4.6 发布与验收自动化

外部参考：miniprogram-ci、项目现有 Harness。

建议：

- Platform 继续用 `/health`、`/ready`、preflight、smoke、探针脚本做验证。
- MiniApp 补 `miniprogram-ci` 预览/上传脚本，输出二维码或上传结果。
- 双仓联动功能必须有同一个 trace_id，分别记录 Platform API 验证和 MiniApp 真机验证。

______________________________________________________________________

## 五、LangChain / LangGraph 使用建议

### 5.1 不建议使用的地方

| 位置 | 原因 |
|---|---|
| 客户机器人热路径整体迁移 | 当前链路已与订单、商品、转人工、有赞、客户记忆耦合，迁移收益小、回归风险大 |
| 员工助手最终回复 | 员工助手需要事实保真，确定性回复优先级高于自然表达 |
| 订单/库存/履约查询 | 这些是业务查询，不是开放式推理，应该由 service/repository 保证正确 |
| MiniApp 前台 | 小程序只调用 API，不需要 LangChain |

### 5.2 可以试点的地方

| 位置 | 使用方式 | 条件 |
|---|---|---|
| 离线复盘 | LangGraph 编排 QA review、knowledge gap、memory consolidation | 不进入客户实时回复链路 |
| 知识库评估 | LangChain evaluator 或自研脚本对检索结果打分 | 必须保留本地 golden cases |
| 文档入库实验 | 用 LangChain loader/splitter 对比现有切分效果 | 结果进入待审核，不直接发布 |
| 复杂员工工作流 | LangGraph 做固定节点流程，例如“生成草稿 -> 校验 -> 重写一次 -> 输出” | 节点、循环次数、工具权限写死 |

### 5.3 决策原则

引入 LangChain / LangGraph 前先问四个问题：

1. 它是否减少了我们自己维护的复杂编排代码？
2. 它是否不会削弱业务可控性？
3. 它是否能被现有测试和探针覆盖？
4. 它是否可以被包在独立 adapter 后面，未来不用时能移除？

只有四个答案都为“是”，才值得引入。

______________________________________________________________________

## 六、可实施计划

### 阶段 0：架构基线和决策冻结（0.5 天）

目标：防止后续讨论反复在“要不要全量 LangChain / 要不要 Agent 化”上打转。

动作：

- 更新本文件为当前决策入口。
- 在 `docs/README.md` 的当前权威口径中挂载本文件。
- 明确两个机器人边界：
  - 客户机器人：可自然表达，但必须引用知识和支持转人工。
  - 员工助手：确定性回复，LLM 只做结构化规划兜底。
- 明确两个仓边界：
  - Platform 是业务真相源。
  - MiniApp 是渠道体验层。

验收：

- 文档存在且可从 `docs/README.md` 找到。
- `LOGBOOK.md` 有本轮 trace 记录。

### 阶段 1：双机器人能力目录（1 天）

目标：把客户机器人和员工助手的能力拆清楚，避免后续加功能时混线。

产出：

- 新增或更新 `docs/architecture/bot-capability-matrix.md`。
- 梳理每个能力的 `bot_type`、入口、底层 service、回复策略、测试入口。

建议表结构：

| 能力 | 客户机器人 | 员工助手 | 底层 service | 回复策略 | 验证 |
|---|---|---|---|---|---|
| 商品问答 | 是 | 是 | catalog / knowledge | 客户自然回复，员工列来源 | RAG cases + 员工探针 |
| 订单查询 | 客户查本人订单 | 员工查经营订单 | order | 客户解释型，员工确定性 | API tests + 探针 |
| 售后政策 | 是 | 是 | knowledge | 客户安抚，员工引用规则 | 知识库 cases |
| 转人工 | 是 | 查询待人工 | conversation / ops | 客户引导，员工列表 | smoke + tool tests |
| 离线复盘 | 不直接暴露 | 是 | offline | 员工摘要 | service tests |

验收：

- 每个已存在能力都有归属。
- 没有“bot_type 不明”的工具。
- 员工助手探针与能力目录能互相映射。

### 阶段 2：客户机器人上下文治理（2 天）

目标：解决上下文爆炸和长期记忆可维护性。

执行状态：

- 2026-07-06 已落地第一片：客户机器人上下文预算快照进入 `timing.context_budget` 和 `reply_latency.meta_data`。
- 2026-07-06 已补第二片：工具调用轮次新增的 assistant/tool 消息进入 `timing.context_budget`，记录工具上下文消息数、工具结果消息数和 token 估算。
- 2026-07-06 已补第三片：`context_budget` 增加历史预算占比、总 prompt 预算占比、压力等级和会话摘要候选标记，用于提前发现上下文爆炸风险。
- 2026-07-06 已冻结客户会话摘要设计：[客户会话摘要设计](./customer-session-summary-design.md)，明确采用“观测触发、异步生成、下轮使用”的方案，首版不写长期画像、不引入 LangChain / LangGraph、不进入本轮同步回复链路。
- 2026-07-06 已完成会话摘要数据层小切片：新增 `conversation_summaries` 独立表、model、repository、v014 migration、readiness / apply_migrations 必需表门禁和仓库测试。
- 2026-07-06 已完成会话摘要生成 service 小切片：新增 `conversation_summary_service.py`，支持 LLM JSON 摘要草稿、来源消息记录、长度限制和完整手机号/地址/订单号敏感信息丢弃。
- 2026-07-06 已完成回复后异步触发小切片：新增 `conversation_summary_scheduler.py`，正常 AI 回复保存和 `reply_latency` 记录后按 `context_budget.needs_session_summary_candidate` 排队生成并保存 active 摘要；失败只记录日志，不阻断当前客服回复。
- 2026-07-06 已完成 active 摘要只读注入小切片：新增 `conversation_summary_memory.py`，由 `chat_ai_loop` 只读加载 active 摘要并传给 `chat_context`；摘要作为 system prompt 中的“本会话早期摘要”片段出现，最近消息窗口、RAG 检索、客户画像和工具调用行为不变。
- 2026-07-06 已补离线长上下文 smoke：新增 `scripts/check_customer_long_context_summary_smoke.py`，无 LLM、无数据库验证 active 摘要 prompt 注入、最近消息保留、RAG query 稳定、工具结果压力不误触发摘要候选。
- 2026-07-06 已冻结客户长期记忆治理计划：[客户长期记忆治理计划](./customer-memory-governance-plan.md)，明确长期画像只作为可审计服务提示，必须有 `source_evidence_json`、置信度、状态、撤销、过期和会话摘要隔离边界；静态验收 `scripts/check_customer_memory_governance_plan.py --summary` 已接入统一业务合约门禁。
- 会话摘要当前已完成设计冻结、独立数据层、摘要生成 service、异步触发、草稿保存、热路径只读注入和离线长上下文 smoke；长期记忆证据规则、敏感字段撤销/过期已冻结为治理计划和静态验收，不混入热路径。

动作：

- 梳理当前上下文来源：
  - 最近消息。
  - 会话摘要。
  - 客户画像。
  - RAG 知识。
  - 工具结果。
  - 转人工规则。
- 增加“上下文预算表”，明确每类上下文最大 token 或最大条数。
- 会话摘要机制已完成设计冻结：
  - 预算压力只标记候选，本轮回复不等待摘要生成。
  - 摘要采用异步生成、下轮使用，失败不阻断客服回复。
  - 摘要只保留当前会话短期状态，不直接写入长期画像，长期画像仍由离线记忆任务审核。
  - active 摘要只读注入 system prompt，且明确订单、库存、配送、价格仍以工具和知识库为准。
- 增加记忆证据规则：
  - 每条长期记忆必须有来源对话或来源订单。
  - 过敏原、特殊日期等敏感字段必须低频写入、高门槛更新。

建议验证：

- 构造长对话测试：多轮商品咨询、订单追问、售后转人工。
- 验证 prompt 不超过预算。
- 验证无资料时不会编造。
- 验证长期记忆只作为提示，不作为事实结论。
- 已有离线 smoke 覆盖摘要注入和工具压力边界；生产观察仍需看真实 token 压力、回复质量和摘要生成失败降级。

### 阶段 3：知识库治理升级（2-3 天）

目标：借鉴 ChatWiki / WeKnora，把知识库从“能搜”升级为“可运营、可追溯、可评估”。

执行状态：

- 2026-07-06 已落地客户机器人首批 RAG golden cases：`tests/fixtures/customer_rag_golden_cases.json`。
- 新增结构校验入口 `scripts/check_customer_rag_golden_cases.py`，先保证商品咨询、配送、退款售后、转人工四类客服场景持续存在。
- `scripts/eval_retrieval.py` 已支持 `--fixture tests/fixtures/customer_rag_golden_cases.json`，可按客服场景 group 输出 Recall@K / MRR。
- `scripts/check_customer_rag_golden_cases.py --summary` 已接入 `scripts/check_project.py --skip-tests` 的“业务合约检查”，避免后续删减客服核心场景而绕过统一门禁。
- 本片只建立评测样本、校验脚本和离线评估入口，不改变知识库字段、检索算法或线上回复。
- 2026-07-06 已冻结知识库治理兼容迁移计划：[知识库治理兼容迁移计划](./knowledge-governance-migration-plan.md)，明确 `audience / review_status / valid_from / valid_until / reviewed_by / reviewed_at` 的默认值、枚举、过滤语义和实施顺序。
- 新增静态验收入口 `scripts/check_knowledge_governance_plan.py`，并通过 `--summary` 接入 `scripts/check_project.py --skip-tests`，防止后续迁移绕过 audience、有效期、审核状态、兼容默认值和禁止重构主表的边界。
- 2026-07-06 已实现 v015 兼容迁移：新增 `v015_knowledge_governance_fields.sql`、schema 默认字段、`KnowledgeEntry` 字段、`KnowledgeRepo` 默认发布治理过滤，以及 `/ready`、preflight、`apply_migrations.py` 字段级门禁。
- 2026-07-06 已实现入口 audience 分流：客户机器人、有赞客服事件处理使用 `audience='customer'` 检索器，企微员工助手订单/知识工具使用 `audience='employee'` 检索器；默认 `knowledge_retriever` key 保持客户侧兼容。
- 2026-07-06 已实现后台治理字段编辑：知识配置列表和抽屉表单展示并保存 audience、review_status、valid_from、valid_until，新增知识默认共同可见、已发布、长期有效。
- 2026-07-06 已补 audience / 有效期治理 smoke：`scripts/check_knowledge_audience_governance_smoke.py --json` 使用内存库和真实 `KnowledgeRetriever` 证明默认视角只返回 `all`，客户视角返回 `all + customer`，员工视角返回 `all + employee`，草稿、归档、过期和未生效条目均不会被返回。
- 2026-07-06 已补知识命中日志：新增 v016 `knowledge_retrieval_logs`，`KnowledgeRetriever` 在客户、员工和 no_match 检索后写入 bot_type、audience、query、retrieval_mode、命中知识 ID/标题、结果数和 fallback；`scripts/check_knowledge_retrieval_logs_smoke.py --json` 可用内存库证明日志链路。
- 2026-07-06 已补知识命中日志只读报表：`scripts/report_knowledge_retrieval_logs.py --db <db> --limit 100 --json` 可输出命中数、no_match 率、bot_type/audience/retrieval_mode/fallback 聚合、按天趋势、top no_match query 和最近日志；脚本只读打开 SQLite，目标库未应用 v016 时不自动迁移。
- 2026-07-06 已补知识命中日志后台只读 API 和页面：新增 `KnowledgeRetrievalReportService`、`/api/v1/admin/knowledge-retrieval-report/summary` 和后台 `/knowledge-retrieval-report` 页面，脚本、后台 API 和前端页面共用同一套聚合口径。

动作：

- 以 [知识库治理兼容迁移计划](./knowledge-governance-migration-plan.md) 作为字段迁移入口。
- 规划知识条目的 audience、有效期、审核状态、来源说明。
- 增加知识命中日志：
  - `question`
  - `bot_type`
  - `matched_entry_ids`
  - `score`
  - `reply_used`
  - `fallback_reason`
- 为客户机器人建立 RAG golden cases。
- 为员工助手建立知识问答探针。

分批策略：

1. 先加文档、静态验收和命中日志。（文档、静态验收、命中日志和只读报表已完成）
2. 再按兼容迁移计划补 `v015_knowledge_governance_fields.sql`、schema、model 和 repository 过滤。（已完成）
3. 再补后台展示和导出。（入口显式 audience、后台展示和编辑已完成）
4. 最后评估索引调整和灰度发布。

### 阶段 4：员工助手能力目录和确定性计划增强（2 天）

目标：让员工助手变成稳定的经营工具，而不是聊天机器人。

动作：

- 对齐 `wecom-employee-agent-development-plan.md` 的结论：回复期不走 LLM。
- 把 `employee_agent_capabilities.py` 的能力整理成文档矩阵。
- 每个工具补齐：
  - 参数提取规则。
  - 缺参数追问。
  - 空结果回复。
  - 异常回复。
  - 对应探针。
- 继续扩展 `scripts/check_wecom_employee_agent_plans.py`，把真实员工问法沉淀为计划验证。

当前进展：

- 2026-07-06 已新增员工助手能力合约清单：`app/service/wecom/employee_agent_capability_contracts.py` 为每个能力补齐参数规则、缺参数口径、空结果口径、异常口径和对应探针名。
- 2026-07-06 已新增静态验收：`scripts/check_employee_agent_capability_contracts.py --json` 会检查能力卡与合约一一对应、探针覆盖的工具均存在、合约引用的探针存在且确实覆盖对应工具。
- `scripts/check_employee_agent_capability_contracts.py --summary` 已接入 `scripts/check_project.py --skip-tests` 的“业务合约检查”，与客户 RAG golden cases、知识治理计划一起作为统一静态门禁。
- 本片只增加治理和验证资产，不改变 `EmployeeAgentPlanner`、工具调用、确定性回复或员工可见文本生成。

禁止项：

- 不恢复 LLM 润色。
- 不让 LLM 自主选择无限工具。
- 不把客户客服的语气策略套到员工助手上。

### 阶段 5：MiniApp 商城体验对照优化（2-3 天）

目标：借鉴烘焙/商城小程序，把消费者链路补完整，但不破坏 Platform 真相边界。

动作：

- 对照 `gooking/bread`、`litemall`、`wechat-app-mall` 梳理页面差距：
  - 首页。
  - 分类。
  - 商品详情。
  - 规格。
  - 购物车。
  - 结算。
  - 订单详情。
  - 客服入口。
  - 会员入口。
- 更新 `YunxiBakeMiniApp` 的 roadmap 或页面差距清单。
- 对每个页面标出依赖的 Platform API。
- 缺 API 时先回 Platform 定义契约，不在 MiniApp 写业务规则。

验收：

- 每个前台页面能对应到 Platform API 或明确的待补 API。
- 小程序没有新增客户、商品、订单、营销真相。
- 真机验收清单覆盖商品、购物车、结算、支付、客服入口。

执行状态：

- 2026-07-07 已冻结 Platform 侧 MiniApp 页面 API 覆盖合约：[MiniApp 页面 API 覆盖合约](./miniapp-page-api-coverage-contract.md)，明确 `pages/home/index`、`pages/products/index`、`pages/product-detail/index`、`pages/cart/index`、`pages/checkout/index`、`pages/policy/index`、`pages/address/index`、`pages/orders/index`、`pages/order-detail/index`、`pages/group-registration/index`、`pages/chat/index`、`pages/profile/index` 对应的 Platform API。
- 合约明确会员权益、积分、储值余额、优惠券、配送费 / 满减 / 活动价属于待补 Platform API，不允许 MiniApp 本地计算或伪装成真实权益。
- `scripts/check_miniapp_page_api_contract.py --summary` 已接入 `scripts/check_project.py --skip-tests` 和生产预检 `business_contracts.static_checks`；该合约新增时作为第六类业务合约静态门禁，当前已纳入七类总体业务合约门禁。
- 本片只补 Platform 侧契约和静态验收，不改 MiniApp 页面、不改 Platform API 行为、不新增前端业务规则。
- 2026-07-07 已在 `YunxiBakeMiniApp` 仓补 MiniApp 本地镜像：`docs/page-api-coverage.md` 和 `scripts/check-page-api-coverage.mjs`，并接入 `npm run check:page-api-coverage`；该门禁检查 12 个页面、24 个 API 术语和 8 条业务边界，保证前端仓继续以 Platform 为业务真相源。

### 阶段 6：可观测和发布闭环（1-2 天）

目标：把“机器人好不好”变成可检查，而不是靠聊天体验主观判断。

Platform 指标：

- 客户机器人：
  - 知识命中率。
  - 转人工率。
  - 无资料兜底率。
  - 工具调用成功率。
  - 长上下文截断次数。
- 员工助手：
  - 意图规划命中率。
  - 工具成功率。
  - 空结果率。
  - 探针通过率。
  - 生产回调成功率。

MiniApp 指标：

- 页面接口失败率。
- 商品详情打开成功率。
- 购物车提交成功率。
- 支付唤起成功率。
- 客服入口点击率。

发布闭环：

- Platform：
  - `python scripts/check_project.py --skip-tests`
    - 已包含员工助手能力合约、客户 RAG golden cases、知识治理计划、客户长期记忆治理计划、客户机器人可观测合约、MiniApp 页面 API 覆盖合约、GitHub 参考实施计划七类业务合约静态检查。
  - `python scripts/preflight_production.py --json`
    - 已包含 `business_contracts.static_checks`，发布前会报告员工助手能力合约、客户 RAG golden cases、知识治理计划、客户长期记忆治理计划、客户机器人可观测合约、MiniApp 页面 API 覆盖合约、GitHub 参考实施计划七类状态明细；合约失败只给出只读修复步骤，不自动改库、不改配置。
  - `python scripts/check_preflight_business_contracts.py "<preflight-report.json>" --summary`
    - 用于发布证据归档后复核 preflight JSON 里的七类业务合约状态，整体预检因环境配置失败时也能单独证明业务合约是否通过。
  - 相关 pytest。
  - `/health`
  - `/ready`
  - 客户机器人 smoke。
  - 员工助手 callback probe。
- MiniApp：
  - `npm run check` 或现有检查脚本。
  - `miniprogram-ci` 预览 / 上传。
  - 真机验收清单。

执行状态：

- 2026-07-06 已冻结客户机器人可观测合约：[客户机器人可观测合约](./customer-observability-contract.md)，明确 `knowledge_hit_rate`、`no_data_fallback_rate`、`handoff_rate`、`tool_success_rate`、`context_pressure_rate` 等指标，以及 `trace_id`、`channel_type`、`bot_type`、`intent`、`handoff_reason`、`fallback_reason` 等事件字段。
- `scripts/check_customer_observability_contract.py --summary` 已接入 `scripts/check_project.py --skip-tests` 和生产预检 `business_contracts.static_checks`，当前与 MiniApp 页面 API 覆盖合约、GitHub 参考实施计划一起纳入七类业务合约静态门禁。
- 本片只冻结指标、事件字段和隐私边界，不新增数据库迁移，不改客户机器人热路径，不改员工助手 planner、工具调用或确定性回复。
- 2026-07-07 已在 `YunxiBakeMiniApp` 仓补 MiniApp 可观测合约：`docs/observability-contract.md` 和 `scripts/check-observability-contract.mjs`，并接入 `npm run check:observability-contract`；该门禁冻结页面接口失败、商品详情打开、购物车进结算、下单、支付准备、支付唤起、客服入口、转人工、会话门槛和客户群登记等 10 个前台指标，同时明确隐私边界和观测失败不得阻断用户路径。
- 2026-07-07 已在 `YunxiBakeMiniApp` 仓补 miniprogram-ci 发布准备合约：`docs/release/miniprogram-ci-readiness.md` 和 `scripts/check-miniprogram-ci-readiness.mjs`，并接入 `npm run check:miniprogram-ci-readiness` 与 `release:readiness`；该探针只读检查项目配置、依赖声明、仓库内密钥风险、上传私钥路径和上传环境变量，未配置私钥或未安装依赖时报告 `needs_configuration`，不执行真实上传、不生成体验版、不替代真机验收。
- 2026-07-07 已补 GitHub 参考实施计划静态门禁：`scripts/check_github_reference_implementation_plan.py --summary` 会校验阶段状态、边界、资产、LangGraph 试点限制和禁止性指令，并接入 `scripts/check_project.py --skip-tests`、`scripts/preflight_production.py --json` 和 `scripts/check_preflight_business_contracts.py "<preflight-report.json>" --summary`，作为第七类业务合约静态门禁；本片不引入 LangChain / LangGraph，不改客户机器人热路径、不改员工助手 planner、工具调用或确定性回复。

### 阶段 7：LangGraph 离线流程试点（可选，2 天）

目标：只在低风险离线场景验证 LangGraph 是否真的减少维护成本。

试点对象：

```text
离线会话
-> QA review
-> knowledge gap
-> memory extraction
-> conflict check
-> pending review
```

边界：

- 不进入客户实时回复。
- 不影响员工助手事实回复。
- 节点和最大循环次数写死。
- 每个节点输出结构化 JSON。
- 保留现有 offline agent 作为回滚路径。

验收：

- 同一批离线会话，新旧流程输出可对比。
- 失败可隔离，不影响主服务启动。
- 代码复杂度确实下降，否则不继续引入。

______________________________________________________________________

## 七、Review 结论

### P0：必须坚持的边界

1. **员工助手不能 Agent 化成自由推理。**
   订单、库存、履约、营收、待人工这类结果必须来自确定性查询和模板，不能让 LLM 最终改写。

2. **MiniApp 不能沉淀业务真相。**
   烘焙字段、订单规则、库存、支付和会员权益都必须由 Platform 决定，MiniApp 只做输入和展示。

3. **长期记忆不能直接等于聊天摘要。**
   客户偏好、过敏、特殊日期必须有证据、置信度和撤销路径。

### P1：最值得补的能力

1. **知识库治理。**
   这是客户机器人和员工助手共同依赖的底座，优先级高于引入 LangChain。

2. **能力目录。**
   把两个机器人能做什么、怎么回复、怎么验证整理清楚，可以显著降低后续维护成本。

3. **观测日志。**
   没有意图、命中知识、工具调用和兜底原因，后续只能靠肉眼看聊天记录排查。

4. **MiniApp 页面差距清单。**
   烘焙小程序要尽快从“能访问 API”走向“消费者完整下单体验”。

### P2：可以延后

1. 全量 LangChain 改造。
2. 多租户平台化。
3. 复杂会员营销引擎。
4. 开放式 Agent 工作流。
5. MiniApp 重构为复杂前端框架。

### 风险清单

| 风险 | 表现 | 缓解 |
|---|---|---|
| 盲目框架迁移 | LangChain 引入后测试失效、回归面扩大 | 只做 adapter 或离线试点 |
| 两个机器人混线 | 员工助手变自然但不准确，客户机器人变生硬 | 明确 `bot_type` 和 `reply_policy` |
| 知识库污染 | 草稿、过期政策、员工内部话术被客户看到 | 增加 audience、状态、有效期 |
| 记忆误用 | 把客户一次表达当成永久偏好 | 增加证据、置信度、人工可查 |
| MiniApp 规则外溢 | 前端写死商品、订单、营销规则 | 缺规则先补 Platform API |

______________________________________________________________________

## 八、推荐执行顺序

```text
阶段 0：冻结本决策和文档入口
-> 阶段 1：双机器人能力目录
-> 阶段 2：客户机器人上下文治理
-> 阶段 3：知识库治理升级
-> 阶段 4：员工助手能力目录增强
-> 阶段 5：MiniApp 商城体验对照
-> 阶段 6：观测和发布闭环
-> 阶段 7：LangGraph 离线试点
```

如果只能先做三件事，顺序应是：

1. 双机器人能力目录。
2. 客户机器人上下文和记忆治理。
3. 知识库治理和命中观测。

这三件事完成后，再讨论 LangChain / LangGraph 才有意义。

______________________________________________________________________

## 九、验收标准

本计划不能只看“文档写完”，后续执行时应按以下标准验收：

- 客户机器人和员工助手有独立能力目录。
- 每个能力有入口、底层 service、回复策略和验证方式。
- 客户机器人长上下文有预算、摘要和长期记忆边界。
- 知识库条目能区分客户可见、员工可见、草稿、发布、过期。
- 员工助手新增问法必须进探针或测试。
- MiniApp 页面依赖的 Platform API 有契约记录。
- 双仓联动功能有同一个 trace_id 和两边验证证据。
- LangChain / LangGraph 如引入，必须有回滚边界和对比报告。

______________________________________________________________________

## 十、本轮自审记录

本轮 review 按“目标是否覆盖、边界是否清晰、计划是否可执行、风险是否暴露”四项检查。

| 检查项 | 结果 |
|---|---|
| GitHub 借鉴是否分组 | 已按 AI 客服 / RAG / 多渠道、小程序商城 / 会员 / 发布两组拆分 |
| 外部项目是否核验 | GitHub 项目已用 GitHub API 核验描述、更新时间、许可；`miniprogram-ci` 已用 npm registry 核验 |
| 是否考虑两个项目 | 已分别覆盖 `Platform` 主仓和 `Storefront MiniApp` 渠道仓 |
| 是否考虑两个机器人 | 已分别覆盖客户机器人和员工助手，且回复策略分开 |
| 是否给出可实施计划 | 已拆为阶段 0 到阶段 7，并标出目标、动作和验收 |
| 是否给出 LangChain 取舍 | 已明确不迁移热路径，只在离线和固定流程中试点 |
| 是否暴露风险 | 已列出 P0 / P1 / P2 和风险缓解 |

残余风险：

- 外部 GitHub 项目仍需在真正实施前按许可证和最新代码再做一次确认，本文件只作为架构借鉴，不授权复制代码。
- 阶段 1 的能力目录需要结合当前真实代码再做一次逐工具盘点，本文件只给出结构和优先级。
- MiniApp 页面/API 覆盖和前台可观测合约已在 `YunxiBakeMiniApp` 仓补首版本地门禁；真机/体验版、真实微信登录和真实支付联调仍需后续补证。

______________________________________________________________________

## 十一、阶段 1 可实施性复核

复核日期：2026-07-06

复核结论：**计划整体可实施，没有发现需要推翻的硬阻塞。**

已确认可直接推进：

- 双机器人能力目录：已落地到 [bot-capability-matrix.md](./bot-capability-matrix.md)。
- 客户机器人能力盘点：当前已有客服 API、主链路、RAG、Function Calling、转人工、客户记忆和离线沉淀。
- 员工助手能力盘点：当前已有 capability registry、能力合约清单、结构化 planner、确定性回复、企微工具 endpoint、探针和测试。

需要前置条件后再做：

- 知识库 `audience / valid_from / valid_until / review_status` 等字段已完成兼容迁移、默认过滤、客户/员工入口显式 audience 分流、后台展示编辑、隔离 smoke、首版命中日志、只读趋势报表、后台只读 API 和后台只读页面；后续可继续基于真实 no_match 数据补知识库。
- 客户会话摘要需要先明确写入位置、触发阈值和与长期记忆的隔离规则。
- MiniApp 发布自动化已在 `YunxiBakeMiniApp` 仓补 `miniprogram-ci` 准备合约和只读探针；真实预览 / 上传仍需要仓库外微信平台上传私钥、`miniprogram-ci` 依赖、机器人号、版本号、说明和二维码 / 真机证据。
- `integration_status` 工具已补入员工助手能力卡，并增加“同步失败有哪些”规划探针；后续只需要继续沉淀更多真实排障问法。

仍保持可选试点：

- LangGraph 只适合离线复盘流程对比试点。
- LangChain loader / splitter 只适合文档入库实验，不直接发布知识。
- 多租户、复杂会员营销和全功能 Agent 平台继续延后。
