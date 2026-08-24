# 知识库治理兼容迁移计划

> trace_id: `20260706-knowledge-governance-migration-plan`
> 状态：迁移设计冻结；v015 字段、字段级门禁、repository 过滤和入口 audience 分流已实现
> 日期：2026-07-06
> 适用范围：`knowledge_base` 的 audience、有效期、审核状态和检索过滤治理
> 关联文档：
> - [GitHub 参考项目借鉴与可实施计划](./github-reference-benchmark-and-implementation-plan.md)
> - [双机器人能力目录](./bot-capability-matrix.md)
> - [客户会话摘要设计](./customer-session-summary-design.md)

______________________________________________________________________

## 一、设计结论

知识库治理应继续复用现有 `knowledge_base` 主表，不新建独立内容主表，不引入 LangChain loader 直接发布知识。下一步迁移只补“发布治理字段”，并保持对既有客户机器人、员工助手、后台知识配置、商品同步和向量重建链路的兼容。

首批目标字段：

| 字段 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `audience` | TEXT | `all` | 知识可见范围：客户、员工或共同可见 |
| `review_status` | TEXT | `published` | 审核状态：草稿、已发布、已归档 |
| `valid_from` | TEXT | 空字符串 | 生效开始时间，空表示立即生效 |
| `valid_until` | TEXT | 空字符串 | 生效截止时间，空表示长期有效 |
| `reviewed_by` | TEXT | 空字符串 | 最近审核人 |
| `reviewed_at` | TEXT | 空字符串 | 最近审核时间 |

字段语义必须保守：老数据默认 `audience='all'`、`review_status='published'`，保证迁移后线上检索结果不突然消失。

______________________________________________________________________

## 二、当前基础

当前项目已经具备：

- `knowledge_base` 主表和 `v001_knowledge_base_extended.sql` 扩展字段。
- `v015_knowledge_governance_fields.sql`：已追加 audience、审核状态、有效期和审核人字段。
- `KnowledgeEntry`、`KnowledgeRepo`、`KnowledgeAdminRepo`、`KnowledgeRetriever`。
- `/ready`、preflight 和 `apply_migrations.py` 已能检查 `knowledge_base` 发布治理字段缺失。
- 后台知识配置、变更历史、向量同步状态。
- 客户 RAG golden cases：`tests/fixtures/customer_rag_golden_cases.json`。
- 离线评估入口：`scripts/eval_retrieval.py --fixture tests/fixtures/customer_rag_golden_cases.json`。
- audience / 有效期治理 smoke：`scripts/check_knowledge_audience_governance_smoke.py --json`。
- 知识命中日志 smoke：`scripts/check_knowledge_retrieval_logs_smoke.py --json`。
- 知识命中日志只读趋势报表：`scripts/report_knowledge_retrieval_logs.py --db <db> --limit 100 --json`。
- 知识命中日志后台只读 API：`GET /api/v1/admin/knowledge-retrieval-report/summary?limit=100`。
- 知识命中日志后台只读页面：`web/admin` 的 `/knowledge-retrieval-report`。

当前缺口：

- 客户机器人和员工助手已通过不同 `KnowledgeRetriever` 实例显式接入 `audience='customer' / 'employee'`。
- 后台知识配置已支持展示和编辑 audience、有效期、审核状态。
- audience 和有效期隔离已具备脚本级 smoke 证明。
- `knowledge_retrieval_logs` 已记录客户/员工检索命中和 no_match fallback，并已有只读趋势报表脚本、后台只读 API 和后台只读页面。

______________________________________________________________________

## 三、迁移边界

首版只做兼容新增列和只读过滤，不做结构重构。

允许做：

- 为 `knowledge_base` 追加字段。
- 在 model/repository 中读取这些字段。
- 在检索入口增加默认过滤：仅返回已发布、当前有效、目标 audience 匹配的启用知识。
- 在后台列表展示和筛选这些字段。
- 补迁移测试、repository 测试、RAG golden cases 和离线评估。

禁止做：

- 不拆分 `knowledge_base` 为多张主表。
- 不让 LangChain loader/splitter 直接写入已发布知识。
- 不让客户热路径读取草稿或过期知识。
- 不让员工助手最终回复交给 LLM 自由改写。
- 不一次性改动 MiniApp 页面体验。

______________________________________________________________________

## 四、字段枚举

`audience` 允许值：

- `all`：客户机器人和员工助手都可用。
- `customer`：仅客户机器人可用。
- `employee`：仅员工助手可用。

`review_status` 允许值：

- `draft`：草稿，不进入客户或员工检索。
- `published`：已发布，可以按 audience 和有效期检索。
- `archived`：已归档，不进入客户或员工检索。

时间字段口径：

- 使用 ISO-like 文本时间，沿用当前 SQLite 文本时间风格。
- 空字符串表示不限制。
- `valid_from <= now` 且 `valid_until >= now` 才算当前有效。

______________________________________________________________________

## 五、实施顺序

1. 新增迁移 `v015_knowledge_governance_fields.sql`。（已完成）
   - 只使用 `ALTER TABLE ... ADD COLUMN`。
   - 默认 `audience='all'`、`review_status='published'`。
   - 增加适合检索过滤的索引。

2. 更新 schema、readiness、preflight 和 apply_migrations 字段级门禁。（已完成）
   - 新库创建时直接包含治理字段。
   - `apply_migrations` 和 readiness 需要能识别缺字段。

3. 更新 `KnowledgeEntry` 和 repository。（已完成）
   - 增加字段默认值。
   - 保持旧测试构造最小 `KnowledgeEntry()` 不破。
   - repository 查询默认只返回 `is_active=1`、`review_status='published'`、有效期内、audience 匹配的知识。

4. 更新检索与评估。（已完成基础隔离证明）
   - 客户机器人检索传入 `audience='customer'`。（已完成）
   - 员工助手知识工具传入 `audience='employee'`。（已完成）
   - 新增 `check_knowledge_audience_governance_smoke.py`，用内存库和真实 `KnowledgeRetriever` 证明默认、客户、员工视角下的 audience / 有效期过滤。

5. 更新后台知识配置。（已完成）
   - 列表展示 audience、review_status、valid_from、valid_until。
   - 保存时默认已发布和共同可见，后续再补审核流。

______________________________________________________________________

## 六、验收标准

迁移实现完成后必须证明：

- 老库迁移后已有知识仍可被检索。
- `draft` 和 `archived` 不进入默认检索。
- 过期知识不进入检索。
- `customer` 知识不进入默认共同知识检索。
- `employee` 知识不进入默认共同知识检索。
- 指定 `audience='customer' / 'employee'` 时同时返回 `all` 和目标 audience。
- RAG golden cases 仍通过。
- `scripts/check_knowledge_audience_governance_smoke.py --json` 证明默认视角只返回 `all`，客户视角返回 `all + customer`，员工视角返回 `all + employee`，草稿、归档、过期和未生效条目不返回。
- `scripts/check_knowledge_retrieval_logs_smoke.py --json` 证明客户、员工和 no_match 检索都会写入 `knowledge_retrieval_logs`。
- `scripts/eval_retrieval.py --fixture tests/fixtures/customer_rag_golden_cases.json` 仍输出可用 Recall@K / MRR。

______________________________________________________________________

## 七、残余风险

| 风险 | 缓解 |
|---|---|
| 老数据默认发布导致历史脏知识继续可见 | 先保持兼容，后续通过后台审核批次逐步归档 |
| audience 过滤误伤客户回复 | 迁移后先跑 golden cases，再灰度上生产 |
| 有效期时间口径不一致 | 首版统一使用 SQLite 文本时间和空字符串无限制 |
| 后台审核流过重 | 首版只做字段和过滤，审核工作流延后 |

______________________________________________________________________

## 八、当前结论

阶段 3 已推进到后台治理字段可运营、隔离 smoke 证明、首版知识命中日志、只读趋势报表、后台只读 API 和后台只读页面：`knowledge_base` 已具备发布治理字段，老数据默认共同可见且已发布，字段缺失会在 `/ready`、preflight 和 `apply_migrations.py` 暴露；客户机器人使用 `customer` 视角，员工助手使用 `employee` 视角；后台知识配置可展示并保存 audience、review_status、valid_from、valid_until；`check_knowledge_audience_governance_smoke.py` 已证明默认、客户、员工三种视角不会混入草稿、归档、过期或未生效知识；`check_knowledge_retrieval_logs_smoke.py` 已证明客户、员工和 no_match 检索都会写入日志；`report_knowledge_retrieval_logs.py` 可在目标库完成 v016 后只读输出命中、兜底聚合和按天趋势；`/api/v1/admin/knowledge-retrieval-report/summary` 已提供同口径后台 API，后台 `/knowledge-retrieval-report` 已展示命中率、no_match 趋势、高频未命中和最近日志。下一片不应跳过 golden cases 直接发布更强过滤，可基于真实 no_match 数据补知识库。
