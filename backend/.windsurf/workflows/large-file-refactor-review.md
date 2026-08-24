---
description: 职责过载评估与拆分 Review 工作流，每次修改 ≥ 警戒线的 .py 文件、新增公开类、或拆分 service/api 模块时强制前后各走一遍
---

# 职责过载评估与拆分 Review 工作流

> 本工作流的目的是「**保护开发规范**」，不是「让文件变短」。抽出与否取决于职责是否真实混杂，不取决于行数是否超线。

## ⚠️ 核心原则

行数阈值是「职责可能过载」的早期信号，不是拆分目标。走完本流程后可能的正当结论：

- ✅ 职责真实混杂 → 按职责拆分
- ✅ 职责本来就紧密内聚 → **保留 warning 不动**也是合法结论

## 📏 阈值速查

| 层级 | 警戒线 | 硬上限 | |------|--------|--------| | `app/api/*.py` | 250 行 | 350 行 | |
`app/service/*.py` | 220 行 | 320 行 | | `app/service/llm/*.py` | 120 行 | 180 行 | |
`app/service/wecom/*.py` / `youzan/*.py` | 150 行 | 250 行 | | `app/repository/*.py` | 150 行 | 250 行 |
| `app/models/*.py` | 80 行 | 120 行 |

## 🎯 触发条件（任一命中即必须走完本工作流）

- 即将修改的 `.py` 文件当前行数 **≥ 警戒线**
- 计划在已有文件中新增公开类，使单文件公开类数 > 3
- 计划将一个文件拆为多个文件
- 单个函数已超 50 行，计划在其中追加逻辑

## 1️⃣ 预检（开始 coding 之前）

### 1.1 行数与公开类基线

```powershell
# 目标文件行数
@(Get-Content -LiteralPath "app/service/chat.py").Count

# 公开类数量（不以 _ 开头的 class 定义）
Select-String -LiteralPath "app/service/chat.py" -Pattern "^class [A-Z]" |
  Measure-Object | Select-Object -ExpandProperty Count

# 全局文件行数排行
Get-ChildItem -Recurse -Filter "*.py" -Path "app" |
  ForEach-Object { [PSCustomObject]@{File=$_.Name; Lines=@(Get-Content $_.FullName).Count} } |
  Sort-Object Lines -Descending | Format-Table -AutoSize
```

### 1.2 与阈值比对

- 行数 < 警戒线 → ✅ 绿灯，可继续，但**不得追加与现有职责无关的新职责**
- 行数 ≥ 警戒线 → ⚠️ 黄灯，**必须先走职责混杂度评估（见 1.3）**
- 行数 ≥ 硬上限 或 公开类 > 3 或 函数体 > 50 行 → 🔴 红灯，**禁止追加业务变更，先做拆分 PR**

### 1.3 职责混杂度评估（超警戒线必走）

列出该文件**当前承担的所有职责**，对每项职责问 3 个问题：

1. 这个职责能否用 3 句话独立描述其输入/输出/副作用？
1. 抽出后能否被独立 mock 测试，不需要构造完整的 service 依赖树？
1. 抽出是否会引入循环依赖或破坏现有调用链？

**3 种合法结论：**

- **拆**：职责 1-2 满足，问题 3 = No → 按职责拆，进入后续步骤
- **不拆**：职责紧密内聚（如意图识别 + query 改写在同一上下文中强耦合）→ 保留 warning，**在 LOGBOOK 记录不拆的论证**
- **部分拆**：部分职责能拆，部分不能，先拆能拆的，多轮 PR

### 1.4 先对齐 Harness 口径

- 如果这次拆分或重构会产生可追溯结果，先准备 `trace_id`
- 如果会留下可复用教训，先看 `docs/harness-engineering/core/mistake-ledger.md`
- 如果会产生交接或证据，先看 `docs/harness-engineering/core/agent-handoff-template.md` 和 `docs/harness-engineering/core/evidence-index.md`

## 2️⃣ 拆分原则（编码阶段）

### Python 四象限拆分法

| 象限 | 内容 | 目标文件 | |------|------|----------| | 接口/协议 | 抽象基类、Protocol |
`<module>/<topic>_protocol.py` | | 数据结构 | Pydantic 模型、枚举、常量 | `<module>/<topic>_types.py` | | 外部适配 |
第三方 API 桥接、加解密 | `<module>/<topic>_adapter.py` | | 业务编排 | 核心逻辑 | 保留在原文件或 `<topic>_service.py` |

### 向后兼容策略

拆分后若其他模块已 import 旧路径，在原文件顶部做 re-export：

```python
# app/service/chat.py（拆分后保留兼容）
from app.service.chat_pipeline import run_ai_pipeline  # noqa: F401
```

## 3️⃣ 中检（拆分代码完成时）

```powershell
# 重新确认行数
@(Get-Content -LiteralPath "app/service/chat.py").Count
@(Get-Content -LiteralPath "app/service/chat_pipeline.py").Count

# 验证服务可正常启动
uvicorn app.main:app --host 127.0.0.1 --port 7001 --reload

# 运行测试
python scripts/test_scenarios.py
```

通过条件：

- 服务正常启动，健康检查通过
- 主文件行数下降且低于警戒线
- 新文件均低于对应层级警戒线
- 相关测试通过

## 4️⃣ 后检（提交前）

```powershell
# 确认全部文件阈值合规
Get-ChildItem -Recurse -Filter "*.py" -Path "app" |
  ForEach-Object { [PSCustomObject]@{File=$_.Name; Lines=@(Get-Content $_.FullName).Count} } |
  Sort-Object Lines -Descending | Format-Table -AutoSize
```

- [ ] 主文件行数明显下降，低于警戒线
- [ ] 所有新文件低于对应层级警戒线
- [ ] 单文件公开类 ≤ 3，单函数体 ≤ 50 行
- [ ] 无循环依赖（`api → service → repository → models` 方向保持）
- [ ] 原 import 路径无需修改（或已做 re-export）
- [ ] 测试通过
- [ ] `LOGBOOK.md` 已更新（含拆分动机论证）
- [ ] 如有交接或证据留档，已补 `trace_id` / handoff / evidence index

## 5️⃣ 失败处理

- **行数仍超阈值**：拆为更细的 PR，按「数据结构 → 适配器 → 核心」分批
- **引入循环依赖**：回滚，改为先抽接口再迁移实现的两步方案
- **测试失败**：确认是 import 路径问题还是语义变更，语义变更拆为独立 PR

## 🔗 联动

- 本工作流开始前：**必须先调用 `芸熙文件体量守卫`**，深读当前文件的阈值和分拆方向指引
- 拆分完成后：`/review` 对拆分后的文件进行 Review
- 收口提交：`/commit`（commit 工作流会进一步调用 `/sync-skills` 同步 Skill 文档）
