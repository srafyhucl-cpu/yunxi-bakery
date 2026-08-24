---
name: 芸熙LLM守卫
version: 1.0.0
description: "【必须在动代码前调用】芸熙烘焙 AI 客服 LLM 集成守卫。只要涉及 app/service/llm/ 下任意文件（Prompt、Function Calling、意图识别、Query 改写、对话循环、兜底策略），必须先调用本 Skill 读取规范约束，再开始实现或修改。"
---

# 芸熙烘焙 LLM 守卫

## Harness 联动

如果本次 LLM 问题涉及幻觉、意图误判、工具循环失控、兜底缺失、转人工遗漏或 Prompt 规则回归，先联动 `yunxi-harness-engineering`：

- 把失败案例沉淀为可复现测试或评估样本。
- 在 `docs/harness-engineering/core/mistake-ledger.md` 记录根因和新增防线。
- 上线前按 `docs/harness-engineering/core/verification-matrix.md` 选择 LLM/客服链路验证。

## DeepSeek 调用规范

### 客户端单例（`app/service/llm/client.py`）

```python
# 正确：模块级单例，避免重复连接
_client: AsyncOpenAI | None = None

def get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=get_settings().deepseek_api_key,
            base_url="https://api.deepseek.com",
        )
    return _client
```

### 必须 try/except 包裹，LLMError 兜底

```python
# 正确
try:
    response = await get_client().chat.completions.create(...)
    return response.choices[0].message.content
except Exception as exc:
    logger.error("DeepSeek 调用失败 model=%s err=%s", model, exc)
    raise LLMError(str(exc)) from exc

# 调用侧：捕获 LLMError，给用户兜底回复，不向上抛
try:
    reply = await chat_completion(messages, tools)
except LLMError:
    logger.warning("LLM 调用失败，使用兜底回复 session=%s", session_id)
    return "非常抱歉，AI 客服暂时无法响应，请稍后再试或联系人工客服。"
```

## Function Calling 规范

### 最多 3 轮（`MAX_TOOL_ROUNDS = 3`）

```python
for _round in range(MAX_TOOL_ROUNDS):
    response = await chat_completion(messages, tools=FUNCTION_DEFINITIONS)
    tool_calls = response.choices[0].message.tool_calls

    if not tool_calls:
        break  # 无工具调用，退出循环

    # 追加 assistant 消息（含 tool_calls）
    messages.append({"role": "assistant", "tool_calls": tool_calls, ...})

    # 执行工具并追加结果
    for tc in tool_calls:
        result = await dispatch_tool(tc.function.name, tc.function.arguments)
        messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})
else:
    # 超过 3 轮，强制兜底
    return FALLBACK_REPLY
```

### dispatch_tool 必须处理未知工具名

工具实现已拆分至子模块：`function_defs.py`（常量）/ `function_tool_order.py` / `function_tool_product.py`，`functions.py` 仅保留 `dispatch_tool` 入口。

```python
async def dispatch_tool(
    tool_name: str,
    args: dict,
    session: Session | None = None,
    knowledge_retriever: KnowledgeRetriever | None = None,
) -> str:
    match tool_name:
        case "get_order_info":
            return await get_order_info(knowledge_retriever, **args)
        case "get_product_info":
            return await get_product_info(knowledge_retriever, session, **args)
        case "get_logistics_info":
            return await get_logistics_info(knowledge_retriever, **args)
        case "search_knowledge":
            return await search_knowledge(knowledge_retriever, **args)
        case "transfer_to_human":
            # 由 ChatService 工具调度循环拦截，此处为安全底吟
            return json.dumps({"status": "pending"}, ensure_ascii=False)
        case _:
            logger.warning("未知工具调用 name=%s", tool_name)
            return json.dumps({"error": f"未知工具: {tool_name}"}, ensure_ascii=False)
```

## 意图识别规范（`app/service/llm/intent*.py`）

意图模块已拆分为 7 个文件（满足单文件体量约束）：

| 文件 | 职责 |
|------|------|
| `intent.py` | 意图识别主入口（调用 LLM + 容错解析） |
| `intent_types.py` | `IntentType` 枚举定义 |
| `intent_taxonomy.py` | 8 类意图分类体系元数据 |
| `intent_behavior_keywords.py` | 行为目的关键词表 |
| `intent_domain_keywords.py` | 主题域关键词表 |
| `intent_keywords.py` | 关键词快速匹配工具 |
| `intent_prompt.py` | 意图识别专用 System Prompt |

> ⚠️ 超阈强制禁止：禁止将意图相关逻辑归并回单文件。

意图分类为 8 类，轻量调用（`max_tokens=4`，`temperature=0`）：

| ID | 类别 | 触发场景 |
|----|------|----------|
| 1 | 商品咨询 | 多少钱、怎么买、有什么口味 |
| 2 | 规则咨询 | 退款规则、截单时间、发票政策 |
| 3 | 运费费用 | 运费、邮费、包邮吗 |
| 4 | 配送履约 | 几天到、什么时候发货、配送范围 |
| 5 | 订单办理 | 改地址、改口味、取消订单 |
| 6 | 售后异常 | 投诉、蛋糕坏了、少了东西 |
| 7 | 人工服务 | 要人工、转客服、找专员 |
| 8 | 闲聊其他 | 你好、谢谢、没事了 |

> 判定原则：先识别用户**行为目的**（问规则/要求办理/反馈异常/要求人工），再看主题域。ORDER_SERVICE(5)、AFTER_SALES_ISSUE(6)、HUMAN_ASSISTANCE(7) 均触发转人工。

```python
# 正确：解析时做容错
try:
    intent_id = int(response.strip())
    if intent_id not in range(1, 9):
        intent_id = 1  # 默认商品咨询
except ValueError:
    intent_id = 1
```

## Query 改写规范（`app/service/llm/query_rewriter.py`）

改写目的：将指代不明的用户 query（如"这个多少钱"）改写为完整独立的搜索语句（如"草莓蛋糕多少钱"），提升知识检索精度。

```python
# 改写仅在 query 含指代词或上下文依赖时才调用，避免浪费 token
AMBIGUOUS_PATTERNS = ["这个", "那个", "它", "上面说的", "刚才"]

def _needs_rewrite(query: str, history: list) -> bool:
    return any(p in query for p in AMBIGUOUS_PATTERNS) and len(history) > 0
```

## System Prompt 规范（`app/service/llm/prompt.py`）

- 动态注入当前时间（优先使用 `app.utils.now_beijing()`，强制北京时间）
- 需要持久化 `%Y-%m-%d %H:%M:%S` 时间字符串时使用 `app.utils.now_str()`，禁止在 LLM 模块新增裸 `datetime.now()` / `utcnow()`
- 动态注入知识库检索结果（最多 5 条）
- 知识条目为空时启用"无知识库"模式，严禁幻觉

```python
# 有知识条目时：
"以下是相关知识库内容，请严格基于此回答，不得编造：\n{knowledge}"

# 无知识条目时：
"当前知识库无相关信息，请如实告知用户你不清楚，并建议联系人工客服。"
```

## 输出后处理规范

### Markdown 清理

有赞小程序和企微均为纯文本渠道，需去除 Markdown 符号：

```python
import re

def clean_markdown(text: str) -> str:
    text = re.sub(r"\*{1,3}(.+?)\*{1,3}", r"\1", text)  # 粗体/斜体
    text = re.sub(r"#{1,6}\s+", "", text)                # 标题
    text = re.sub(r"`(.+?)`", r"\1", text)               # 行内代码
    text = re.sub(r"\n{3,}", "\n\n", text)               # 多余空行
    return text.strip()
```

### 安抚策略（`app/service/llm/soothe.py`）

```python
SOOTHE_KEYWORDS = ["投诉", "不满意", "太差了", "骗人", "退款"]
SOOTHE_PREFIX = "非常抱歉给您带来不好的体验，"

def apply_soothe(user_msg: str, reply: str) -> str:
    if any(k in user_msg for k in SOOTHE_KEYWORDS):
        if "抱歉" not in reply and "对不起" not in reply:
            return SOOTHE_PREFIX + reply
    return reply
```

## 验收清单

- [ ] DeepSeek 调用有 try/except，抛出 `LLMError`
- [ ] 调用侧捕获 `LLMError`，返回兜底回复，不向上抛
- [ ] Function Calling 循环 ≤ `MAX_TOOL_ROUNDS`（3），超限返回兜底
- [ ] `dispatch_tool` 有 `case _:` 处理未知工具名
- [ ] 意图识别结果有容错（非 1-8 时默认为 1）
- [ ] System Prompt 无知识条目时有明确提示，不允许幻觉
- [ ] 输出经过 Markdown 清理
- [ ] 含敏感关键词时追加安抚前缀
