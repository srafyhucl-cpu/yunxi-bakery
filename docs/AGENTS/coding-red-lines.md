# 编码红线详解

> 以下规则由 `pre-commit` 自动检查（`scripts/check_project.py`），违反会导致 commit 失败。
> 所有红线均不允许例外。

______________________________________________________________________

## 类型标注规范

| 红线 | 说明 |
|------|------|
| 禁止 `Optional[X]` / `Union[X, Y]` | 使用 `X \| None` / `X \| Y`（Python 3.10+ 联合类型语法） |

**违规示例**：
```python
from typing import Optional, Union

def get_name(user_id: Optional[int]) -> Optional[str]: ...  # ❌
def parse(value: Union[str, int]) -> str: ...                # ❌
```

**合规示例**：
```python
def get_name(user_id: int | None) -> str | None: ...  # ✓
def parse(value: str | int) -> str: ...                # ✓
```

---

## 占位符与代码规范

| 红线 | 说明 |
|------|------|
| 禁止 `# TODO` 占位符 | 要么实现，要么删除。TODO 会在代码库中积累，导致无人跟进 |
| 禁止 `print()` 调试 | 使用 `logger.debug()` 替代。裸 print 污染 stdout 并绕过日志系统 |

---

## SQL 规范

| 红线 | 说明 |
|------|------|
| 禁止 `SELECT *` | 必须明确列出字段。`SELECT *` 在表结构变更时静默引入 bug |
| 禁止 SQL f-string 拼接 | 必须使用 `?` 参数化绑定。f-string 拼接存在 SQL 注入风险 |

**违规示例**：
```python
await db.execute(f"SELECT * FROM messages WHERE id = {msg_id}")    # ❌ 多项违规
```

**合规示例**：
```python
await db.execute("SELECT id, content, created_at FROM messages WHERE id = ?", (msg_id,))  # ✓
```

---

## 架构分层约束

| 红线 | 说明 |
|------|------|
| 禁止 `api/` 直接导入 `repository/` | 必须经过 `service/` 层 |
| 禁止根 API 兼容文件承载真实 Router | `app/api/miniapp_*.py`、`admin_*.py`、`webhook.py`、`wecom.py`、`channel_router.py` 只做兼容入口，真实实现放在 canonical 子目录 |
| 禁止 `service/` 直接调用 `aiosqlite` | 必须经过 `repository/` 层 |
| 禁止 `models/` 引用上层模块 | `models/` 只依赖标准库和 pydantic |

**分层调用链**：
```
api/ → service/ → repository/ → models/
```

任何层级不得向上穿透调用。依赖方向永远是单向向下的。

**违规示例**：
```python
# app/api/webhook.py
from app.repository.message_repo import MessageRepo  # ❌ 穿透 service 层

# app/api/admin_products.py
from fastapi import APIRouter  # ❌ 兼容入口不承载真实 Router

# app/models/session.py
from app.repository.database import db  # ❌ models 引用上层
```

**合规示例**：
```python
# app/api/admin_products.py
import sys

from app.api.admin import products as _module

sys.modules[__name__] = _module
```

---

## 异常处理

| 红线 | 说明 |
|------|------|
| 禁止静默吞异常（`except: pass`） | 至少记录 `logger.error`。静默吞异常会掩盖生产环境致命错误 |

**违规示例**：
```python
try:
    await risky_operation()
except:
    pass  # ❌ 异常被彻底丢弃
```

**合规示例**：
```python
try:
    await risky_operation()
except Exception as e:
    logger.error("risky_operation 执行失败: %s", e)  # ✓ 至少记录日志
```

---

## 安全规范

| 红线 | 说明 |
|------|------|
| 禁止硬编码密钥/Token | 通过 `app/config.py` 的 `get_settings()` 获取 |

**违规示例**：
```python
api_key = "sk-xxxxxxxxxxxx"  # ❌ 密钥进代码仓库
```

**合规示例**：
```python
from app.config import settings
api_key = settings.DEEPSEEK_API_KEY  # ✓ 从环境变量/.env读取
```

---

## 代码注释规范

| 红线 | 说明 |
|------|------|
| 禁止英文注释 | Python / JS / TS / HTML / CSS 注释统一使用中文；仅保留必要注释，避免无意义注释 |

**违规示例**：
```python
# Get user by ID
# This function fetches user data from database
async def get_user(user_id: int): ...  # ❌ 英文注释
```

**合规示例**：
```python
# 根据 ID 查询用户信息
async def get_user(user_id: int): ...  # ✓ 中文注释
```

---

## 文件体量与职责评审

文件体量门禁用于发现上帝类风险，不把行数当作重构完成标准：

- 警戒线和阻断线只触发职责评审。
- 超过阻断线且没有评审记录的新文件会阻断提交。
- 职责混杂时，按可命名、可独立测试的稳定边界拆分。
- 职责高度内聚时，可以记录理由后保留超线实现。
- 禁止为了压行数制造 `part1.py`、碎片 helper、薄转发层、循环依赖或大量状态穿透。

完整决策见 [ADR 0004](../harness-engineering/adr/0004-responsibility-first-file-size-governance.md) 和 `.agents/skills/yunxi-file-size-guard/SKILL.md`。

这是一项职责评审门禁，不改变本文件前述安全、分层和数据访问红线的强制性。

---

## 代码风格工具

| 红线 | 说明 |
|------|------|
| 使用 `ruff` 做代码风格检查 | 提交前自动运行 `ruff check --fix`，避免手动排版 |
| 使用 `mypy` 做渐进式类型检查 | 新增函数建议加类型注解，`mypy --ignore-missing-imports` 不阻断提交 |
