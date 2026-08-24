---
name: 芸熙架构守卫
version: 1.0.0
description: "【必须在动代码前调用】芸熙烘焙 AI 客服分层架构守卫。只要涉及 api/、service/、repository/、models/ 任意一层的新增或修改，或涉及数据库操作、Webhook 处理、跨层调用，必须先调用本 Skill 确认分层边界和约束，再开始实现。"
---

# 芸熙烘焙架构守卫

## Harness 联动

如果本次架构问题来自返工、误操作、跨层穿透或重复踩坑，先联动 `yunxi-harness-engineering`：

- 用 `docs/harness-engineering/core/traceability-model.md` 记录 trace。
- 用 `docs/harness-engineering/core/verification-matrix.md` 选择架构验证。
- 需要长期记忆时，写入 `docs/harness-engineering/core/mistake-ledger.md`，并补测试、脚本、pre-commit、AGENTS 或 Skill 中至少一类防线。

## 分层边界（核心约束）

```
api/ → service/ → repository/ → models/
```

| 层级 | 允许调用 | 禁止调用 | |------|----------|----------| | `api/` | `service/` |
`repository/`、`aiosqlite` | | `service/` | `repository/`、`models/` | `aiosqlite` 直接操作 | |
`repository/` | `aiosqlite`、`models/` | 业务判断、外部 API | | `models/` | 标准库、`pydantic` | 其他任何模块 |

## 检查方法

```powershell
# api/ 层穿透检测（必须零输出）
rg "from app\.repository" app/api --include="*.py"

# service/ 层直连数据库检测（必须零输出）
rg "import aiosqlite|\.execute\(|\.fetchone\(|\.fetchall\(" app/service --include="*.py"

# models/ 层外引检测（必须零输出）
rg "from app\.(service|repository|api)" app/models --include="*.py"
```

## 数据库操作规范

### 参数化查询（强制）

```python
# 错误：f-string 拼接
await db.execute(f"SELECT id FROM sessions WHERE user_id = '{uid}'")

# 正确：? 参数化绑定
await db.execute("SELECT id, channel, status FROM sessions WHERE user_id = ?", (uid,))
```

### 字段明确列出（禁止 SELECT \*）

```python
# 错误
await db.execute("SELECT * FROM messages WHERE session_id = ?", (sid,))

# 正确
await db.execute(
    "SELECT id, session_id, role, content, created_at FROM messages WHERE session_id = ?",
    (sid,),
)
```

### 事务边界（由 service 层管理）

```python
# repository 层：只提供原子操作
async def insert_message(self, db, msg: Message) -> None:
    await db.execute("INSERT INTO messages (...) VALUES (...)", (...))

# service 层：管理事务边界
async with db.execute("BEGIN"):
    await msg_repo.insert_message(db, user_msg)
    await msg_repo.insert_message(db, ai_msg)
    await db.commit()
```

## Webhook 幂等性规范

每个入站消息必须通过 `channel_msg_id` 去重，防止重复处理：

```python
# 正确：先查重再处理
existing = await message_repo.get_by_channel_msg_id(db, channel_msg_id)
if existing:
    return  # 已处理，直接返回

# 立即返回 200，后台异步处理
asyncio.ensure_future(_process(channel, user_id, content, channel_msg_id))
return {"status": "ok"}
```

## 常见违规模式

### 层级穿透

```python
# 错误：api/ 直接调 repository
@router.get("/sessions")
async def list_sessions(session_repo: SessionRepo = Depends(...)):
    return await session_repo.get_all(db)  # 违反！

# 正确：api/ 只调 service
@router.get("/sessions")
async def list_sessions(chat_service: ChatService = Depends(...)):
    return await chat_service.list_sessions()
```

### 静默吞异常

```python
# 错误
try:
    await wecom_client.send_text(user_id, reply)
except Exception:
    pass

# 正确
try:
    await wecom_client.send_text(user_id, reply)
except Exception as exc:
    logger.error("企微消息发送失败 user=%s err=%s", user_id, exc)
```

## 验收清单

- [ ] `api/` 无直接 `repository/` 导入
- [ ] `service/` 无直接 `aiosqlite` 操作
- [ ] 所有查询使用 `?` 参数化，无 f-string 拼 SQL
- [ ] 无 `SELECT *`，字段明确列出
- [ ] 多表写入有显式事务，由 service 层管理
- [ ] Webhook 入口有 `channel_msg_id` 去重
- [ ] 无静默吞异常（`except: pass`）
