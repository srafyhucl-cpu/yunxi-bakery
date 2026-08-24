---
description: 代码规范化检查工作流，用于芸熙烘焙 AI 客服项目的红线审查和分层约束验证
---

# 代码规范化检查工作流

## 触发场景

在每次代码提交前、任务完成时或需要验证代码规范时使用此工作流。

## 检查流程

### 0. 调用相关 Skill（在一切检查前执行）

根据本次检查涉及的文件范围，先调用对应 Skill 深读规范细则：

- 涉及 `app/api/` / `app/service/` / `app/repository/` 的变更 → 调用 **芸熙架构守卫**
- 涉及 `app/service/llm/` 的变更 → 调用 **芸熙LLM守卫**
- 发现函数过长 / 硬编码 / 命名问题 → 调用 **芸熙洁净代码守卫**
- 任何文件行数接近或超过警戒线 → 调用 **芸熙文件体量守卫**

### 0.5 先对齐 Harness 口径

- 较大任务或跨文件检查，先看 `docs/harness-engineering/core/traceability-model.md`
- 如果本轮会留下证据，先确认 `docs/harness-engineering/core/evidence-index.md`
- 需要复盘或交接时，先准备 `scripts/harness_snapshot.py` 的输出

### 1. 语法红线检查

```powershell
# 检查 Optional/Union（必须零输出，违反则阻断）
rg "Optional\[|Union\[" app --include="*.py"

# 检查 TODO 占位符（必须零输出，违反则阻断）
rg "# TODO" app --include="*.py"

# 检查 SELECT *（必须零输出，违反则阻断）
rg "SELECT \*" app --include="*.py"
```

### 2. 架构分层检查

```powershell
# api/ 层不得直接导入 repository（必须零输出）
rg "from app\.repository" app/api --include="*.py"

# service/ 层不得直接调用 aiosqlite（必须零输出）
rg "import aiosqlite|aiosqlite\." app/service --include="*.py"

# models/ 层不得引用其他模块（必须零输出）
rg "from app\.(service|repository|api)" app/models --include="*.py"
```

### 3. 安全约束检查

```powershell
# 检查 SQL 拼接（f-string 或 + 拼 SQL，必须零输出）
rg 'f"SELECT|f"INSERT|f"UPDATE|f"DELETE' app --include="*.py"

# 检查静默吞异常（必须零输出）
rg "except.*:\s*pass" app --include="*.py"

# 检查硬编码密钥关键词（必须零输出）
rg "api_key\s*=\s*['\"]sk-|secret\s*=\s*['\"]" app --include="*.py"
```

### 4. 异步规范检查

```powershell
# 检查 service/ 和 repository/ 中未加 async 的函数定义（人工核查）
rg "^\s+def " app/service app/repository --include="*.py"
```

### 5. 日志规范检查

```powershell
# 检查直接 print 调用（必须零输出）
rg "^\s+print\(" app --include="*.py"

# 验证 service 层日志是否携带上下文字段（人工抽查）
rg 'logger\.(info|warning|error)' app/service --include="*.py" -l
```

### 6. 导入顺序检查（人工检查）

对修改的 `.py` 文件抽查导入顺序是否符合规范：标准库 → 第三方 → 项目本地，各组之间空一行。

## 常见违规与修复

### Optional/Union 违规

```python
# 错误
from typing import Optional
def get(session_id: Optional[str]) -> Optional[Session]:

# 正确
def get(session_id: str | None) -> Session | None:
```

### 层级穿透违规

```python
# 错误（api/ 直接调用 repository）
from app.repository.session_repo import SessionRepo
sessions = await session_repo.get_all()

# 正确（api/ 只调用 service）
reply = await chat_service.handle_message(...)
```

### SQL 拼接违规

```python
# 错误
await db.execute(f"SELECT id FROM sessions WHERE user_id = '{user_id}'")

# 正确
await db.execute("SELECT id FROM sessions WHERE user_id = ?", (user_id,))
```

### 静默吞异常违规

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

## 验收标准

- [ ] Optional/Union 零输出
- [ ] TODO 占位符零输出
- [ ] SELECT * 零输出
- [ ] api/ 层无直接 repository 导入
- [ ] service/ 层无直接 aiosqlite 调用
- [ ] SQL 无拼接（f-string / + 拼参数）
- [ ] 无静默吞异常
- [ ] 无硬编码密钥
- [ ] 无裸 `print()` 调用
- [ ] 若是较大任务，已记录 `trace_id` 或说明不需要
- [ ] 若本轮有可复用教训，已更新 `core/mistake-ledger.md`

## 🔗 联动 Skill

| 场景 | Skill |
|------|-------|
| 架构分层 / Webhook 幂等 | `芸熙架构守卫` |
| LLM / 意图识别 / Function Calling | `芸熙LLM守卫` |
| 代码风格 / 硬编码 / 命名质量 | `芸熙洁净代码守卫` |
| 文件超过警戒线 | `芸熙文件体量守卫` → `/large-file-refactor-review` |
