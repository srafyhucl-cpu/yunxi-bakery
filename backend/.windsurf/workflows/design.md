---
description: 功能设计工作流，任何新功能开发、新 API、新模块设计前使用，通过 brainstorming skill 探索需求后再进入编码
---

# 功能设计工作流

## 触发场景

在开始以下任一任务之前使用此工作流：

- 新增 API 接口 / 新增路由
- 新增 Service 类或核心业务方法
- 新增数据库表或字段
- 设计新的 LLM 集成逻辑（新意图类型、新 Function Tool）
- 任何会影响现有调用链的重构

## 步骤

### 1. 调用 brainstorming skill

在编写任何代码前，**必须先调用 `brainstorming` skill**，通过对话明确以下内容：

- 功能的输入/输出边界是什么？
- 与现有模块的调用关系如何（遵循 api → service → repository 分层）？
- 是否会引入新的依赖或改变现有接口？
- 有哪些边界条件和异常路径？
- 预计新文件/修改文件的行数是否会超警戒线？

### 2. 确认架构合规

brainstorming 完成后，调用 **`芸熙架构守卫`** 校验设计方案：

- 分层边界是否合规？
- Webhook 入口是否需要幂等设计？
- 数据库操作是否在正确层级？

### 3. 如涉及 LLM，额外调用 芸熙LLM守卫

- 是否需要新意图类型？
- 是否需要新 Function Calling 工具？
- 是否影响对话循环结构？

### 4. 开始编码

方案经 brainstorming 确认后，进入编码阶段。编码完成后走 `/check` → `/review` → `/commit` 标准流程。

### 5. 设计收口

设计完成后，如果本轮是较大任务或跨文件变更，先补 `trace_id`，并预留 `docs/harness-engineering/core/agent-handoff-template.md` 和 `docs/harness-engineering/core/evidence-index.md` 的记录位置。

## 🔗 联动 Skill

| 步骤 | Skill |
|------|-------|
| 步骤 1（必须） | `brainstorming` |
| 步骤 2（必须） | `芸熙架构守卫` |
| 步骤 3（LLM 相关时） | `芸熙LLM守卫` |
