# 客户长期记忆治理计划

> trace_id: `20260706-customer-memory-governance-plan`
> 状态：治理设计冻结；首版只补文档和静态验收，不改热路径、不改 `customer_profiles` schema
> 日期：2026-07-06
> 适用范围：客户机器人长期画像、离线 `MemoryAgent`、`customer_profiles`、会话摘要与长期记忆边界
> 关联文档：
> - [GitHub 参考项目借鉴与可实施计划](./github-reference-benchmark-and-implementation-plan.md)
> - [双机器人能力目录](./bot-capability-matrix.md)
> - [客户会话摘要设计](./customer-session-summary-design.md)

______________________________________________________________________

## 一、设计结论

客户长期记忆只能作为**可审计的服务提示**，不能作为订单、库存、价格、配送、支付、售后承诺的事实来源。

当前继续复用 `customer_profiles` 作为 AI 画像层，短期会话摘要继续留在 `conversation_summaries`。两者边界如下：

| 类型 | 数据落点 | 生命周期 | 作用 | 禁止 |
|---|---|---|---|---|
| 短期会话摘要 | `conversation_summaries` | 当前会话 | 压缩早期上下文 | 不能直接写入长期画像 |
| 长期客户画像 | `customer_profiles` | 跨会话 | 只读提示偏好、过敏提醒、特殊日期 | 不能作为事实结论 |

本计划的第一目标不是立刻改表，而是先冻结长期记忆的写入、读取、撤销和过期边界，让后续 schema 或后台能力扩展都有统一验收。

______________________________________________________________________

## 二、当前基础

当前项目已有：

- `customer_profiles` 表：保存 `preferences_json`、`order_summary_json`、`special_dates_json`、`allergens_json`、`consent_status`、`source_evidence_json`。
- `MemoryConsentStatus`：已有 `unknown / granted / revoked` 三种留存状态。
- `customer_memory.py`：热路径只读加载顾客画像，失败时空画像降级。
- `profile_prompt.py`：将长期画像渲染为提示，并要求特殊日期先自然核对、过敏原只作为核对提醒。
- `offline/agent_memory.py`：离线 `MemoryAgent` 从会话消息中抽取画像，写入 `customer_profiles`，并记录 `source_evidence_json`。
- `session_scope`：已区分机器人阶段、转人工阶段和人工消息是否可见。
- `conversation_summaries`：当前会话短期摘要独立存储，不写入 `customer_profiles`。

当前缺口：

- `source_evidence_json` 已存在，但还没有统一规定每类画像事实必须保存哪些 evidence 片段。
- `consent_status=revoked` 已有枚举，但撤销后的读取、写入和后台操作边界还没有形成计划。
- 画像事实还没有独立的 `confidence`、`status`、`expires_at` 字段。
- 过敏原、特殊日期、偏好、订单摘要的写入门槛没有分级说明。
- 会话摘要不能直接提升为长期画像的边界还需要静态门禁持续提醒。

______________________________________________________________________

## 三、治理字段目标

后续如需升级 `customer_profiles`，优先考虑新增字段或结构化 JSON，不直接把短期摘要并入画像。

建议目标字段或 JSON key：

| 字段 / key | 说明 |
|---|---|
| `source_evidence_json` | 每条画像事实必须指向来源 `session_id`、`message_id` 或可见范围 |
| `confidence` | `low / medium / high`，默认低置信度 |
| `status` | `active / revoked / expired / disputed` |
| `expires_at` | 事实过期时间，空表示未设置 |
| `last_verified_at` | 最近人工或明确对话确认时间 |
| `withdrawn_at` | 用户撤销或人工删除时间 |
| `sensitivity` | `normal / sensitive`，过敏原、特殊日期属于敏感提醒 |

首版不立即要求这些字段已经落库，但文档和后续脚本必须以这些概念为准。

______________________________________________________________________

## 四、写入规则

长期记忆只允许冷路径写入：

```text
会话消息 + session_scope + evidence
-> 离线 MemoryAgent
-> 结构化解析
-> 证据和敏感字段检查
-> customer_profiles
```

写入规则：

| 记忆类型 | 写入门槛 | 置信度默认值 | 过期策略 |
|---|---|---|---|
| 普通偏好 | 客户明确表达，且能指向来源消息 | `low` | 可按最近确认时间刷新 |
| 过敏原 | 客户明确说自己或订单相关人过敏 | `medium` | 每次涉及成分时重新提醒核对 |
| 特殊日期 | 客户明确说明日期、对象或用途 | `low` | 日期不完整时不得推测 |
| 订单摘要 | 来自订单工具、人工消息或明确会话事实 | `low` | 只能作上下文提示，不跨订单承诺 |

禁止规则：

- 热路径不能写 `customer_profiles`。
- 会话摘要不能从会话摘要直接提升为长期画像。
- `bot_then_handoff_partial` 可见范围下，不能把机器人阶段意向写成最终确认事实。
- 电话、完整地址、完整订单号、完整交易号不进入长期画像。
- 过敏原和特殊日期只作为服务提醒，不作为食品安全或履约事实结论。

______________________________________________________________________

## 五、读取规则

热路径读取长期画像时必须保守：

- `customer_memory.py` 读取失败必须空画像降级，不能阻断客服回复。
- `profile_prompt.py` 渲染的长期画像只能作为提示。
- 订单、库存、物流、配送、价格仍以工具、订单系统和知识库为准。
- `consent_status=revoked` 时，应禁止继续向回复 prompt 注入长期画像。
- 过期或撤销的画像事实不得进入 prompt。

读取提示口径：

| 字段 | prompt 口径 |
|---|---|
| `preferences_json` | “顾客可能偏好”，不要强行推荐 |
| `special_dates_json` | “仅作为服务提醒”，涉及日期和对象时先自然核对 |
| `allergens_json` | “登记过敏原”，涉及成分时主动提醒顾客核对 |
| `order_summary_json` | 只做历史上下文提示，不替代订单工具 |

______________________________________________________________________

## 六、撤销和过期规则

后续实现撤销和过期时，优先保证用户安全和可审计：

| 场景 | 行为 |
|---|---|
| 用户明确说“不用记了” | 将相关事实标记为 `revoked`，记录 `withdrawn_at` |
| 用户撤销全部记忆 | 将 `consent_status` 设为 `revoked`，热路径不再注入画像 |
| 事实长期未确认 | 标记为 `expired` 或降低 `confidence` |
| 用户纠正事实 | 保留旧证据但新事实优先，旧事实标记 `disputed` |
| 后台人工删除 | 记录操作者和时间，不做静默删除 |

首版可以先通过 JSON key 表达这些状态，后续再视后台运营需求迁移为独立字段。

______________________________________________________________________

## 七、会话摘要边界

`conversation_summaries` 是短期上下文压缩层，不是长期画像来源。它可以帮助离线审核理解上下文，但不能跳过消息证据。

必须坚持：

- 会话摘要不能直接写入长期画像。
- 不能从会话摘要直接提升为 `preferences_json`、`special_dates_json` 或 `allergens_json`。
- 离线 `MemoryAgent` 必须能追溯到原始消息、会话范围或人工消息可见性。
- 摘要中出现的客户目标、待确认项和服务边界只属于当前会话。

______________________________________________________________________

## 八、静态验收

本计划由 `scripts/check_customer_memory_governance_plan.py` 验收，并接入 `scripts/check_project.py --skip-tests` 的业务合约检查。

静态验收必须覆盖：

- `customer_profiles` 和 `conversation_summaries` 的边界。
- `source_evidence_json`、`consent_status`、`confidence`、`status`、`expires_at`、`last_verified_at`、`withdrawn_at` 等治理概念。
- `MemoryAgent`、`customer_memory.py`、`profile_prompt.py` 三个职责点。
- `session_scope` 和 `bot_then_handoff_partial` 可见范围边界。
- 过敏原、特殊日期、撤销、过期规则。
- 禁止热路径直接写长期画像，禁止会话摘要直接提升为长期画像。

______________________________________________________________________

## 九、当前结论

客户长期记忆治理下一步应先把“证据、置信度、状态、撤销、过期、会话摘要隔离”作为业务合约固定下来，再考虑 schema 或后台操作能力。当前切片只补文档和静态验收，不改热路径、不改 `MemoryAgent` 写入策略、不改 `customer_profiles` 表结构；后续真正实现撤销、过期或置信度字段时，必须继续保持长期记忆只是提示，不是事实来源。
