---
description: 维护项目 Skill 文件与规则，使其与代码实现保持同步（任何代码变更后使用）
---

## 这个工作流解决什么问题

Skill 文件描述的是"代码应该长什么样"的规则。每当代码发生实质性变更，规则文件就可能滞后。此工作流用于系统性地评估并修复这种滞后。

---

## 步骤

### 1. 描述本次代码变更

用一句话回答：**这次改动的核心是什么？**

参考分类（可多选）：

- [ ] A — 新增/删除/移动了 `.py` 文件或目录
- [ ] B — 新增/删除/修改了公开类或核心函数
- [ ] C — 改变了模块间调用关系（谁调用谁）
- [ ] D — 修改了 LLM 相关逻辑（意图/Function Calling/Prompt/对话循环）
- [ ] E — 引入或修改了业务常量、枚举、配置
- [ ] F — 修复了代码风格问题（命名/嵌套/魔法数字等）
- [ ] G — 安全/架构规范层面的变更

---

### 2. 按变更类型定位需要检查的 Skill

| 变更类型 | 必须检查 | 按需检查 |
|---------|---------|---------|
| A（文件结构） | `yunxi-file-size-guard` | `yunxi-architecture-guard` |
| B（类/函数） | `yunxi-file-size-guard` | `yunxi-clean-code-guard` |
| C（调用关系） | `yunxi-architecture-guard` | — |
| D（LLM逻辑） | `yunxi-llm-guard` | `yunxi-file-size-guard` |
| E（常量/枚举） | `yunxi-clean-code-guard` | — |
| F（代码风格） | `yunxi-clean-code-guard` | — |
| G（安全/架构） | `yunxi-architecture-guard` | `yunxi-clean-code-guard` |

只修改上表中标记的 Skill，**不强制每次更新全部 4 个**。

---

### 3. 对每个需要检查的 Skill，逐一回答以下问题

打开对应的 `.agents/skills/<skill名>/SKILL.md`，检查：

**（a）代码示例是否过时？**
Skill 里的代码块是否仍能反映当前实现的函数签名、类名、模块路径？若不一致则更新。

**（b）文件/模块路径是否过时？**
Skill 里提到的文件路径（如 `app/service/chat.py`）是否还存在？有无遗漏的新文件？

**（c）验收清单是否完整？**
新的业务规则或约束是否已加入对应 Skill 的 `## 验收清单`？旧的已废弃项是否已删除？

**（d）存量监控表是否准确？**（仅 `yunxi-file-size-guard`）

// turbo

```powershell
Get-ChildItem -Recurse -Filter "*.py" -Path "app" |
  ForEach-Object { [PSCustomObject]@{File=$_.FullName.Replace((Get-Location).Path+"\",""); Lines=@(Get-Content $_.FullName).Count} } |
  Sort-Object Lines -Descending | Select-Object -First 20 | Format-Table -AutoSize
```

对照输出结果，在 `yunxi-file-size-guard` 的 `## ⚠️ 当前存量警戒文件` 表中：

- 删除已回归绿区的行
- 新增或更新超警戒线的文件行

---

### 4. 执行更新

对每个需要修改的 Skill 文件做最小化修改：

- **只改与本次变更直接相关的内容**，不扩展不相关章节
- 保持原有 Markdown 结构不变
- 代码示例必须可运行（函数签名、import 路径与实际代码一致）

若本次变更需要**新建** Skill（例如某个新子系统缺少对应守卫），**必须先调用 `skill-creator` skill** 进行 Skill 设计和评估，再落笔写 SKILL.md。

若对**现有 Skill 做较大改动**（description 重写、验收清单大幅调整、新增 eval 测试用例），同样调用 `skill-creator` 进行评估和迭代，确保触发精度不下降。小型修正（单行勘误、路径更新）无需调用。

---

### 5. 更新 LOGBOOK.md

在 `LOGBOOK.md` **顶部**追加今日条目（若已有今日条目则在其下方补充），记录：

```
### YYYY-MM-DD HH:MM — [一句话标题]
- 变更摘要：[一句话描述做了什么]
- Skill 更新：[修改了哪些 Skill 及原因，无变更则写"Skill 无需更新"]
```

---

### 6. 更新 SKILL_AUDIT.md（每月或重大 Skill 变动后）

打开 `.agents/SKILL_AUDIT.md`，核对状态列：

- 已引入且稳定 → 🟢
- 已引入但存在已知问题 → 🟡  
- 未引入、低优先级保留备用 → ⚪
- 已评估、明确不适用 → 🔴

更新"审计日期"字段，并在对应行补充"本项目引入状态"说明。

### 7. 同步 Harness 相关入口

若本次 Skill 调整影响 trace、验证、证据、交接或防重犯机制，同步检查 `docs/harness-engineering/README.md`、`docs/AGENTS/skill-reference.md`、`docs/harness-engineering/core/traceability-model.md` 和 `docs/harness-engineering/core/verification-matrix.md`。
