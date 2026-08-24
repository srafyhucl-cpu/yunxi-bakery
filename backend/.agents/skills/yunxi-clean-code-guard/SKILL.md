---
name: 芸熙洁净代码守卫
version: 1.0.0
description: "【代码 Review 和修复时调用】芸熙烘焙 AI 客服洁净代码深度核查手册。在 code review、发现魔法数字、命名模糊（data/res/tmp）、函数超长（>50行）、重复逻辑、硬编码字符串/URL时必须调用，获取修复示例、命名对照表和可复用模式指引，再进行修复。"
---

# 芸熙烘焙洁净代码守卫

## Harness 联动

如果同类洁净代码问题第二次出现，或本次修复暴露了命名、硬编码、重复逻辑、函数过长等系统性问题，先联动 `yunxi-harness-engineering`：

- 能机器检查的规则优先沉淀为测试、脚本或 pre-commit。
- 只能靠 Agent 记忆的流程约束，沉淀到 `AGENTS.md` 或项目 Skill。
- 值得防重犯的错误写入 `docs/harness-engineering/core/mistake-ledger.md`。

## 🚫 零硬编码原则

### 禁止魔法数字

所有有业务含义的数字必须定义为命名常量：

```python
# 错误
if len(history) > 20:
    ...
await asyncio.sleep(3)
if token_count > 16000:
    ...

# 正确（集中定义在对应模块顶部或 config）
MAX_HISTORY_MESSAGES = 20
WECOM_REPLY_DELAY_SECONDS = 3
CONVERSATION_TOKEN_BUDGET = 16_000

if len(history) > MAX_HISTORY_MESSAGES:
    ...
await asyncio.sleep(WECOM_REPLY_DELAY_SECONDS)
```

### 禁止魔法字符串

渠道名、状态值、意图 ID 等必须使用枚举或常量：

```python
# 错误
if channel == "youzan":
    ...
if session.status == "human":
    ...

# 正确
class Channel(str, Enum):
    YOUZAN = "youzan"
    WECOM_SINGLE = "wecom_single"
    WECOM_GROUP = "wecom_group"

class SessionStatus(str, Enum):
    AI = "ai"
    HUMAN = "human"
    CLOSED = "closed"

if channel == Channel.YOUZAN:
    ...
if session.status == SessionStatus.HUMAN:
    ...
```

### 禁止硬编码 URL 和域名

所有 URL、域名、端点路径必须走 `app/config.py`：

```python
# 错误
url = "https://open.weixin.qq.com/connect/oauth2/authorize"
api_base = "https://api.deepseek.com"

# 正确（在 config.py 中定义，通过依赖注入获取）
settings = get_settings()
api_base = settings.deepseek_base_url
```

## 📐 函数设计规范

### 单函数职责单一，超过 50 行触发职责评审

50 行是复杂度信号，不是机械拆分目标。先判断函数是否混合 I/O、业务决策、格式转换或多个独立变化原因；只有能提取出稳定、可独立测试的职责时才拆。单一算法、协议映射或状态转换若保持内聚，可以记录理由后保留。

```python
# 错误：一个函数既解析又处理又回复（超 50 行的上帝函数）
async def handle_webhook(request: Request):
    # 验签 10 行
    # 解析消息 15 行
    # 调 AI 20 行
    # 发送回复 10 行
    # 记录日志 5 行

# 正确：拆分为职责单一的小函数
async def handle_webhook(request: Request):
    payload = await _parse_and_verify(request)
    asyncio.ensure_future(_process_message(payload))
    return {"status": "ok"}

async def _parse_and_verify(request: Request) -> dict:
    ...  # ≤ 20 行

async def _process_message(payload: dict) -> None:
    ...  # ≤ 30 行
```

### 函数参数 ≤ 5 个，超出则封装为数据类

```python
# 错误
async def save_message(db, session_id, user_id, channel, role, content, msg_id, created_at):
    ...

# 正确
@dataclass
class MessageCreate:
    session_id: str
    user_id: str
    channel: str
    role: str
    content: str
    channel_msg_id: str | None = None

async def save_message(db, msg: MessageCreate) -> None:
    ...
```

## 🔤 命名质量规范

### 禁止无意义命名

```python
# 错误
data = await get_data()
res = await call_api()
tmp = process(x)
info = session.get_info()

# 正确
session = await session_repo.get_by_id(db, session_id)
wecom_response = await wecom_client.send_text(user_id, reply)
rewritten_query = await rewrite_query(raw_query, history)
transfer_info = await transfer_repo.get_pending(db, session_id)
```

### 布尔值命名以 is\_/has\_/needs\_ 开头

```python
# 错误
manual = session.status == SessionStatus.HUMAN
soothe = needs_soothe(user_msg)

# 正确
is_in_manual_mode = session.status == SessionStatus.HUMAN
needs_soothing = needs_soothe(user_msg)
```

## ♻️ 可复用性设计

### 提取公共逻辑，消灭重复

```python
# 错误：webhook.py 和 wecom.py 各自实现相似的消息去重逻辑
# webhook.py
if await message_repo.get_by_channel_msg_id(db, msg_id):
    return {"status": "ok"}

# wecom.py（重复实现）
existing = await message_repo.get_by_channel_msg_id(db, msg_id)
if existing is not None:
    return

# 正确：抽取到 chat_service 或公共函数
async def is_duplicate_message(db, channel_msg_id: str) -> bool:
    return await message_repo.get_by_channel_msg_id(db, channel_msg_id) is not None
```

### 配置集中管理，单一来源

所有配置通过 `app/config.py` 的 `Settings` 类管理，通过 `get_settings()` 获取，不散落在各模块：

```python
# 错误：在 chat.py 里写死
MAX_TOOL_ROUNDS = 3
FALLBACK_REPLY = "非常抱歉..."

# 正确：在 constants.py 或 config 中统一定义
# app/constants.py
MAX_TOOL_ROUNDS = 3
CONVERSATION_TOKEN_BUDGET = 16_000
FALLBACK_REPLY = "非常抱歉，AI 客服暂时无法响应，请联系人工客服。"
SOOTHE_PREFIX = "非常抱歉给您带来不好的体验，"
```

## 🧹 代码整洁要求

- **禁止注释掉的代码**：不用的代码直接删除，版本历史由 Git 管理
- **禁止 `print()` 调试**：一律使用 `logger.debug()`
- **禁止 `pass` 空实现**：占位时必须写明原因注释或抛出 `NotImplementedError`
- **禁止不必要的嵌套**：超过 3 层嵌套必须提取函数或使用 Early Return
- **禁止冗余注释**：只注释 WHY，不注释 WHAT（代码本身就是文档）

### Early Return 代替深嵌套

```python
# 错误（深嵌套）
async def handle_message(...):
    if not is_duplicate:
        if session:
            if not is_manual_mode:
                # 真正的逻辑在第 4 层

# 正确（Early Return）
async def handle_message(...):
    if is_duplicate:
        return None
    if not session:
        session = await _create_session(...)
    if is_manual_mode:
        return None
    # 真正的逻辑在第 1 层
```

## 🔍 检查方法

```powershell
# 检查魔法数字（单独出现的数字字面量）
rg "=\s*[0-9]{2,}" app --include="*.py" | grep -v "\.py:#"

# 检查 print 调用
rg "^\s+print\(" app --include="*.py"

# 检查注释掉的代码
rg "^\s+#\s+(await|return|if|for|def|class|import)" app --include="*.py"

# 检查函数参数超 5 个
rg "def \w+\(.*,.*,.*,.*,.*,.*\)" app --include="*.py"
```

## 验收清单

- [ ] 无魔法数字（业务含义数字已提取为命名常量）
- [ ] 渠道名、状态值使用枚举
- [ ] URL/域名/端点路径走 config，不散落在业务代码中
- [ ] 超过 50 行的函数已完成职责评审；若拆分，边界可独立测试且没有增加状态穿透
- [ ] 函数参数 ≤ 5 个（超出已封装数据类）
- [ ] 无无意义变量名（`data`/`res`/`tmp`/`x`）
- [ ] 无重复逻辑块（DRY 原则）
- [ ] 无注释掉的代码
- [ ] 无 `print()` 调试语句
- [ ] 嵌套层数 ≤ 3（超出已 Early Return 或提函数）
