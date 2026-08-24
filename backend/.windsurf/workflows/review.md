---
description: 代码 Review 工作流，针对芸熙烘焙 AI 客服项目的变更进行 bug、安全和规范全面审查
---

# 代码 Review 工作流

## 步骤 0：先调用相关 Skill

在开始 Review 前，根据变更文件先调用对应 Skill，确保对规则的理解是最新的：

- 涉及 `app/api/` / `app/service/` / `app/repository/` → **芸熙架构守卫**
- 涉及 `app/service/llm/` → **芸熙LLM守卫**
- 涉及任意 `.py` 文件行数增长 → **芸熙文件体量守卫**
- 发现硬编码 / 命名质量问题 → **芸熙洁净代码守卫**

### 0.5 先对照 Harness 证据

- 如果本轮是较大任务，先看 `docs/harness-engineering/core/traceability-model.md`
- 如果有产物要留档，先看 `docs/harness-engineering/core/evidence-index.md`
- 如果发现可复用教训，优先核对 `docs/harness-engineering/core/mistake-ledger.md`

你是一位极其资深的 Python/FastAPI 后端工程师，正在对芸熙烘焙 AI 客服系统的代码变更进行深度 Review。

## 审查目标

找出所有潜在 bug、安全隐患和规范违反。聚焦以下维度：

1. **逻辑错误**：边界条件、空值处理、异步竞态（如 `asyncio.ensure_future` 未处理异常）
1. **分层越权**：`api/` 直接调 `repository/`，`service/` 直接操作 `aiosqlite`
1. **SQL 注入风险**：f-string / `+` 拼接 SQL 参数
1. **异常处理缺失**：外部 API 调用（DeepSeek/有赞/企微）未用 try/except 包裹，或 `except: pass` 静默吞掉
1. **幂等性**：Webhook 消息是否经过 `channel_msg_id` 去重，避免重复处理
1. **资源泄漏**：数据库连接、HTTP 客户端是否在异常路径中正确关闭
1. **LLM 安全**：Prompt 是否存在注入风险；Function Calling dispatch 是否有未处理的工具名
1. **配置硬编码**：API Key、Token、域名是否写死在代码中
1. **类型注解**：是否使用了被禁止的 `Optional[X]` / `Union[X, Y]`（应为 `X | None` / `X | Y`）
1. **现有规范契约**：是否违反 `CLAUDE.md` 中的任一开发红线
1. **Harness 收口**：是否有对应 `trace_id`、LOGBOOK 记录、证据索引或交接材料

## 执行要求

1. 并行读取多个相关文件以提高效率，不要顺序逐一读取。
1. 只报告有实际代码依据的问题，不做推测性判断。
1. 发现预存 bug（非本次变更引入）也必须报告，标注为"预存问题"。
1. 每个问题说明：**位置（文件+行号）→ 问题描述 → 修复建议**。
1. Review 完成后给出整体评级：✅ 可合入 / ⚠️ 需整改后合入 / ❌ 阻断合入。

## 🔗 联动 Skill

| 场景 | Skill |
|------|-------|
| 分层越权 / Webhook 幂等 / db 操作 | `芸熙架构守卫` |
| LLM 调用 / Function Calling / 意图识别 | `芸熙LLM守卫` |
| 硬编码 / 命名质量 / 函数过长 | `芸熙洁净代码守卫` |
| 文件行数超警戒线 | `芸熙文件体量守卫` → `/large-file-refactor-review` |
