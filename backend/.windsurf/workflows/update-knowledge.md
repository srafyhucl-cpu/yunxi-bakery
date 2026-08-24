---
description: 知识库更新工作流，用于将烘焙业务文档（Word/PDF/Excel/图片）导入芸熙知识库，或对已有知识条目进行增删改
---

# 知识库更新工作流

> 2026-05-25 起：**FAQ / 规则 / 话术优先通过后台 `知识配置` 页面维护**。  
> `knowledge/` 目录下的 Markdown 与 `scripts/seed_knowledge.py` 仅作为历史种子和外部资料导入兜底，不再是日常首选入口。

## 触发场景

- 新增 / 修改产品信息、价格、规格
- 更新服务规则、售后政策、配送规则
- 导入外部业务文档（Word/PDF/Excel）到 `knowledge/` 目录

## 步骤

### 1. 如有外部文档，先转换为 Markdown

**调用 `markitdown` skill**，将文档转换为 Markdown：

- Word / PDF / Excel / PowerPoint → 直接转换
- 图片（含文字） → OCR 提取
- 转换后保存到 `knowledge/` 目录下对应文件

### 2. 确认知识口径无冲突

对照以下现有文件，确认新内容是否与现有口径有冲突：

- `knowledge/芸熙烘焙产品服务全指南.md`
- `knowledge/芸熙烘焙常见问题FAQ.md`
- `knowledge/芸熙烘焙通用服务与售后指引.md`

**任何口径冲突必须先确认，不得自动覆盖。**

### 3. 选择更新入口

- **日常运营修改 FAQ / 规则 / 话术**：优先走后台 `知识配置` 页面
- **从外部文档批量整理资料**：先落到 `knowledge/` Markdown，再决定是否导入后台
- **商品信息**：禁止写入 Markdown，统一依赖有赞 Webhook 与运行时实时刷新

### 4. 如使用 Markdown 导入，再重新生成向量索引

```powershell
# 删除旧的嵌入缓存，触发重建
Remove-Item "data/embeddings.pkl" -ErrorAction SilentlyContinue

# 重新导入非商品知识库（本地）
python scripts/seed_knowledge.py
```

### 5. 验证结果

```powershell
# 检查知识条目数量
python scripts/validate_products.py
```

如通过后台 `知识配置` 页面维护，则应额外确认：
- 列表页状态是否已变为“已入向量”
- 抽屉中的“最近同步时间 / 失败原因 / 最近 5 条历史”是否正常显示

### 6. 更新 LOGBOOK.md

记录本次知识库变更内容和条目数量变化。

### 7. 必要时补 Harness 证据

如果本次知识变更影响生产口径、业务规则或长期记忆，补 `trace_id`，并在 `docs/harness-engineering/core/evidence-index.md` 或 `docs/harness-engineering/core/mistake-ledger.md` 留痕。
