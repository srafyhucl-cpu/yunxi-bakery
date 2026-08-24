# 客户会话摘要设计

> trace_id: `20260706-customer-session-summary-design`
> 状态：设计冻结；数据层、摘要生成 service、回复后异步触发、草稿保存、active 摘要只读注入和离线长上下文 smoke 已实现
> 日期：2026-07-06
> 适用范围：客户机器人短期上下文治理、长对话压缩、上下文预算观测
> 关联文档：
> - [GitHub 参考项目借鉴与可实施计划](./github-reference-benchmark-and-implementation-plan.md)
> - [双机器人能力目录](./bot-capability-matrix.md)
> - [客户长期记忆治理计划](./customer-memory-governance-plan.md)

______________________________________________________________________

## 一、设计结论

客户会话摘要应该作为**短期上下文压缩层**，只服务当前会话的后续回复，不等同于长期客户画像，也不直接进入 `customer_profiles`。

推荐路径是：

```text
最近消息 + 会话摘要 + RAG 知识 + 客户画像只读提示 + 工具结果观测
```

其中：

- 最近消息继续由 `SessionManager.build_context()` 控制滑动窗口。
- 会话摘要只在历史上下文接近预算上限时生成，用于替代被截断的早期对话。
- 长期客户画像仍由离线 `MemoryAgent` 审核写入，不能从会话摘要直接提升。
- 工具结果过大时优先治理工具输出裁剪和分页，不用会话摘要掩盖工具结果膨胀。

______________________________________________________________________

## 二、当前状态

当前项目已有：

- `SessionManager.build_context()`：按 `CONVERSATION_TOKEN_BUDGET=16000` 从最近消息向前保留，超出时插入“历史已被截断”系统提示。
- `chat_context_budget`：记录历史、RAG、客户画像、system prompt、工具结果、预算压力等级和会话摘要候选标记。
- `customer_memory.py`：热路径只读加载 `CustomerProfile`。
- `offline/agent_memory.py`：离线抽取长期客户画像，带证据和会话范围判断。
- `Transfer` 的 `conversation_summary`：给人工接待使用的转人工摘要。
- `conversation_summaries`：客户会话短期摘要独立表，已完成 schema、model、repository、迁移门禁、active 摘要保存和只读读取能力。
- `conversation_summary_service.py`：生成会话摘要草稿，负责 LLM JSON 解析、摘要渲染、来源消息记录、长度限制和敏感信息丢弃，不保存数据库。
- `conversation_summary_scheduler.py`：回复保存和延迟埋点完成后，根据 `context_budget.needs_session_summary_candidate` 排队生成并保存 active 摘要；失败只记录日志，不阻断当前回复。
- `conversation_summary_memory.py`：热路径只读加载 active 摘要，失败时空摘要降级。
- `chat_context.py`：把 active 摘要作为 system prompt 中的“本会话早期摘要”片段注入，并明确订单、库存、配送、价格仍以工具和知识库为准。
- `scripts/check_customer_long_context_summary_smoke.py`：无 LLM、无数据库的离线 smoke，验证摘要注入、最近消息保留、检索 query 稳定、工具结果压力不误触发摘要候选。

当前缺口：

- 已有 active 摘要可以承接被截断的早期客户诉求，并已补离线长上下文 smoke。
- 仍缺生产观察，尚未验证实际 token 压力下降幅度和真实回复质量变化。
- 长期记忆证据、置信度、撤销和过期规则已冻结为 [客户长期记忆治理计划](./customer-memory-governance-plan.md)，当前仍未改表；会话摘要不能直接提升为客户画像。

______________________________________________________________________

## 三、方案比较

| 方案 | 做法 | 优点 | 风险 | 结论 |
|---|---|---|---|---|
| A. 同步热路径即时摘要 | 每轮发现预算压力就调用 LLM 生成摘要并立刻进入本轮回复 | 实时性最好 | 增加延迟和成本，LLM 失败影响客服回复，回归面大 | 不采用 |
| B. 观测触发、异步生成、下轮使用 | 本轮只记录摘要候选；后台任务或回复后任务生成摘要；下一轮构造上下文时读取 | 不影响当前回复，失败可隔离，容易灰度 | 摘要可能滞后一轮 | 推荐 |
| C. 只离线夜间生成摘要 | 复用离线调度，只在夜间批处理长会话 | 风险最低 | 不能解决白天长会话即时上下文爆炸 | 作为兜底，不作为主方案 |

推荐采用 **方案 B**：

1. 热路径只做预算观测和候选标记。
2. 摘要生成在回复完成后异步执行，失败只记录日志。
3. 下一轮 `build_context` 或 `prepare_chat_context` 读取已存在摘要。
4. 摘要输出必须结构化、短文本、可丢弃。

______________________________________________________________________

## 四、职责边界

### 会话摘要负责

- 保留当前会话内已明确的客户诉求。
- 保留还未解决的问题、待确认信息和客服已经给出的边界。
- 保留对当前购买或售后有用的短期偏好，例如“这次想要低糖蛋糕”。
- 标记资料不足、已转人工、工具无结果等上下文状态。

### 会话摘要不负责

- 不写入 `customer_profiles`。
- 不保存过敏原、生日、纪念日等长期敏感事实。
- 不保存电话、地址、完整订单号、完整交易号、完整企业微信外部联系人 ID。
- 不作为订单、库存、物流、价格事实来源。
- 不替代 RAG、订单工具、商品工具或人工接管记录。

### 长期画像边界

长期画像仍只由离线 `MemoryAgent` 负责：

```text
会话消息 + session_scope + evidence -> 离线审核 -> customer_profiles
```

会话摘要可以作为离线审核的参考材料，但不能跳过证据审核直接合并进画像。

______________________________________________________________________

## 五、数据落点设计

数据层已按独立表实现，而不是把摘要塞进 `sessions.extra_info`：

```text
conversation_summaries
```

建议字段：

| 字段 | 含义 |
|---|---|
| `id` | 摘要记录 ID |
| `session_id` | 对应会话 |
| `channel` | 渠道 |
| `user_id` | 渠道用户 ID |
| `summary_text` | 给 LLM 使用的短摘要 |
| `state_json` | 未解决事项、已确认信息、待确认信息 |
| `source_message_ids_json` | 摘要覆盖的消息 ID 列表 |
| `source_until_message_id` | 摘要覆盖到哪条消息 |
| `token_estimate` | 摘要 token 估算 |
| `status` | active / superseded / discarded |
| `created_at` | 创建时间 |
| `updated_at` | 更新时间 |

不放入首版的字段：

- 长期画像字段。
- 审核状态字段。
- 人工客服评价字段。
- 跨会话复用字段。

这些属于客户主档或离线复盘范畴，不属于短期上下文摘要。

______________________________________________________________________

## 六、触发规则

当前 `context_budget` 已有：

- `history_budget_ratio`
- `prompt_budget_ratio`
- `budget_pressure_level`
- `needs_session_summary_candidate`
- `summary_candidate_policy`

建议实现阈值：

| 条件 | 行为 |
|---|---|
| `history_budget_ratio < 0.7` | 不生成摘要 |
| `history_budget_ratio >= 0.7` | 标记摘要候选 |
| `history_budget_ratio >= 0.9` | 高优先级生成摘要 |
| `prompt_budget_ratio >= 0.9` 且历史占比低 | 不生成摘要，记录工具或 RAG 膨胀风险 |
| 会话处于人工接管中 | 不生成 AI 会话摘要 |
| 会话已关闭 | 可由离线任务生成归档摘要，但不进入热路径 |

摘要生成频率：

- 同一会话最多每 8 条新消息生成一次。
- 同一会话已有 active 摘要且覆盖到最近窗口之前时，优先增量重写。
- LLM 失败时保留旧摘要，不阻断客服回复。

______________________________________________________________________

## 七、摘要格式

推荐让摘要生成器输出 JSON，再渲染为 prompt 片段。

```json
{
  "customer_goal": "客户本轮想解决什么",
  "confirmed_facts": ["已明确事实"],
  "pending_questions": ["还需要确认的信息"],
  "service_boundaries": ["已告知的边界或限制"],
  "handoff_state": "none | requested | pending | active",
  "source_scope": {
    "from_message_id": "msg-1",
    "until_message_id": "msg-8"
  }
}
```

渲染到 prompt 时使用短文本：

```text
【本会话早期摘要】
- 客户目标：...
- 已确认：...
- 待确认：...
- 服务边界：...
```

硬限制：

- `summary_text` 建议不超过 800 个中文字符。
- JSON 解析失败时丢弃本次摘要。
- 摘要里出现完整手机号、完整地址或完整订单号时丢弃并记录告警。
- 摘要只覆盖被滑动窗口挤出的早期消息，不重复概括仍在最近窗口内的消息。

______________________________________________________________________

## 八、实现边界

首个代码实现应拆成四片：

1. **Repository 和模型**（已完成）
   - 新增 `conversation_summaries` 表、model、repository。
   - 只提供 upsert active summary、get active summary、discard summary。
   - migration 必须单独 dry-run 验证。

2. **摘要生成服务**（已完成）
   - 新增独立 service，例如 `conversation_summary_service.py`。
   - 输入为会话消息片段和现有摘要。
   - 输出结构化 JSON 和短摘要。
   - 不访问订单、商品、知识库和客户画像 repository。

3. **热路径读取**（已完成）
   - `prepare_ai_conversation_messages` 或 `SessionManager.build_context` 仅读取 active 摘要。
   - 摘要作为独立 system/context 片段插入。
   - 保留最近消息窗口，不让摘要替代最后几轮对话。
   - 已通过 `conversation_summary_memory.py` 只读加载 active 摘要，并由 `chat_context.py` 追加到 system prompt。

4. **异步生成触发**（已完成）
   - 回复完成后根据 `context_budget.needs_session_summary_candidate` 触发。
   - 失败只记录 `logger.warning` 或 `logger.error`。
   - 不影响当前回复。
   - 已通过 `conversation_summary_scheduler.py` 在回复保存和 `reply_latency` 记录后排队执行，并通过 repository 写入 active 摘要。

禁止在首版做：

- 不引入 LangChain Memory。
- 不引入 LangGraph。
- 不把摘要写入 `customer_profiles`。
- 不把摘要生成放进本轮 LLM 回复前的同步路径。
- 不把工具结果直接压缩进会话摘要。

______________________________________________________________________

## 九、验证计划

实现前置验证：

- 文档存在且被 `docs/README.md` 和阶段计划引用。
- 占位符扫描不命中本设计文档。
- `python scripts/check_project.py --skip-tests` 通过。

首个代码实现最低验证：

- migration dry-run 和 apply 测试。
- repository 单测覆盖 active / superseded / discarded。
- 摘要服务单测覆盖 JSON 解析、敏感信息丢弃、长度限制。
- 客服长对话测试覆盖：
  - 摘要存在时 prompt 包含早期摘要。
  - 最近消息仍保留。
  - 工具结果压力不触发摘要。
  - 人工接管中不触发摘要。
- `scripts/check_customer_long_context_summary_smoke.py --json` 已覆盖：
  - 摘要段和事实边界进入 system prompt。
  - 最近用户和助手消息仍在历史上下文中。
  - 摘要文本不泄漏进历史消息。
  - 长历史压力会标记摘要候选。
  - 工具结果压力可标记 critical，但不会误触发摘要候选。
  - RAG 检索 query 不因摘要注入发生漂移。

上线前增强验证：

- 基于生产流量观察 `context_budget` 中压力变化。
- 检查回复不因摘要引入订单、库存、配送承诺幻觉。
- 观察摘要生成失败时客服回复不受影响。

______________________________________________________________________

## 十、残余风险

| 风险 | 缓解 |
|---|---|
| 摘要遗漏早期关键信息 | 最近消息窗口仍保留，摘要只作为补充；长对话回归覆盖待确认事项 |
| 摘要引入幻觉 | JSON schema、敏感信息扫描、来源消息 ID、失败丢弃 |
| 摘要污染长期画像 | 长期画像仍由离线 `MemoryAgent` 审核，不允许直接提升 |
| 成本和延迟增加 | 异步生成、失败不阻断、同会话频率限制 |
| 工具结果过大被误判 | 候选标记只看历史压力，工具压力另行治理 |

______________________________________________________________________

## 十一、当前结论

客户会话摘要可以实现，但必须按“观测 -> 设计 -> 独立存储 -> 摘要生成 -> 异步触发 -> 下轮读取 -> 长上下文 smoke”的顺序推进。当前阶段已完成独立存储、摘要生成 service、回复后异步触发、草稿保存、active 摘要只读注入和离线长上下文 smoke；下一步应做生产观察，确认 token 压力变化、真实回复质量和摘要事实边界，并继续保持不压缩工具结果、不污染长期画像。
