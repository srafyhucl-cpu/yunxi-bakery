# Vibe Coding Harness Engineering 生产级设计

> 日期：2026-06-11
> 适用范围：Bakery Commerce Platform 当前 `Platform` 仓（仓库名仍为 `YunxiBakeBot`）的 AI Coding、Vibe Coding、上线前验证、生产值守与复盘沉淀。
> 目标：让每次 AI 协作都可追溯、可验证、可交接、可复盘；同一类问题不能靠“提醒 AI”避免第二次，而要沉淀为机械化 Harness。

______________________________________________________________________

## 1. 背景

项目已经具备较强的基础 Harness：

- `AGENTS.md`、Guard Skill、红线规则和 pre-commit 负责前馈约束。
- `LOGBOOK.md`、项目进度清单和版本同步负责变更编年史。
- pytest、ruff、mypy、`check_project.py`、`check_file_sizes.py` 负责质量门禁。
- `/ready`、`preflight_production.py`、`smoke_test.py`、迁移、知识种子、向量重建脚本负责上线前验证和 JSON 留档。

当前主要缺口不是“没有检查”，而是这些资产还没有形成统一的记忆闭环：

- 需求、决策、验证结果、失败复盘缺少统一 trace 口径。
- AI 犯错后的经验多散落在聊天、LOGBOOK 或测试中，没有专门的 mistake ledger。
- 新会话或新 Agent 进入项目时，需要从多个文档拼上下文，容易遗漏最近风险。
- 上线证据已有 JSON 能力，但缺少统一 reports 目录规范和发布证据包说明。
- 架构决策缺少 ADR，容易在后续 Vibe Coding 中反复横跳。

______________________________________________________________________

## 2. 设计目标

### 2.1 必达目标

1. **处处有追溯**：每个较大任务都能定位到需求来源、设计文档、改动文件、验证命令、证据报告和 LOGBOOK 条目。
2. **增强记忆**：将跨会话记忆沉淀到仓库内的文档、规则、测试、脚本和报告，而不是依赖某一次聊天上下文。
3. **避免重复犯错**：每次严重返工、线上风险或 AI 误操作，都必须进入 `mistake-ledger`，并至少补一类机械防线。
4. **适配 Vibe Coding**：允许快速推进，但每次推进都被 Harness 捕获、验证和复盘，避免“感觉对了但无法证明”。
5. **生产级可审计**：上线前后能形成可归档证据包，证明配置、数据库、知识、向量、服务、后台和关键接口状态。

### 2.2 非目标

- 不在第一阶段引入复杂多 Agent 平台。
- 不把所有流程都变成阻断式门禁，避免拖慢日常开发。
- 不替代现有 `AGENTS.md`、Guard Skill、pre-commit、preflight 和 smoke，而是把它们编排成闭环。

______________________________________________________________________

## 3. 总体架构

Harness 分为 7 层：

| 层级 | 名称 | 职责 | 当前资产 | 补强方向 |
|---|---|---|---|---|
| H1 | Instruction Harness | 告诉 AI 什么能做、什么不能做 | `AGENTS.md`、skills | 按场景提供短入口和索引 |
| H2 | Context Harness | 让 AI 快速恢复项目状态 | `LOGBOOK.md`、进度清单 | 增加 handoff snapshot |
| H3 | Memory Harness | 把错误和经验沉淀为长期记忆 | 历史评估报告 | 增加 mistake ledger |
| H4 | Verification Harness | 把“做完了”变成可证明 | pytest、ruff、mypy、pre-commit | 增加验证矩阵 |
| H5 | Runtime Harness | 上线前后证明系统可服务 | `/ready`、preflight、smoke | 统一 reports 留档规范 |
| H6 | Review Harness | 让 AI 自审和架构审查有结构 | Guard Skill、红线自测 | 增加 ADR 和 review checklist |
| H7 | Evolution Harness | 让 Harness 随错误持续进化 | LOGBOOK | 增加“复盘到防线”闭环 |

核心闭环：

```text
需求/故障
→ 设计与 trace
→ 代码或文档变更
→ 验证矩阵选择命令
→ 证据报告归档
→ LOGBOOK 记录
→ 如有返工，写入 mistake ledger
→ 补测试/脚本/规则/skill/文档
→ 下一次由 Harness 自动提醒或阻断
```

______________________________________________________________________

## 4. 核心制品

### 4.1 Harness 入口

新增 `docs/harness-engineering/README.md`，作为 AI 和人工开发者进入 Harness 系统的统一父入口。

它负责回答：

- 本项目 Harness 是什么。
- 开始任务前读什么。
- 变更完成后如何证明。
- 犯错后如何沉淀。
- 上线前如何归档证据。

### 4.2 Traceability Model

新增 `docs/harness-engineering/core/traceability-model.md`。

定义统一追溯字段：

- `trace_id`：任务级追踪号，推荐格式 `YYYYMMDD-topic`。
- `source`：需求来源或故障来源。
- `decision_refs`：关联设计文档、ADR 或讨论结论。
- `changed_files`：核心改动文件。
- `verification`：验证命令和结果。
- `evidence`：JSON 报告、截图、日志、测试输出等证据。
- `logbook_entry`：LOGBOOK 对应条目。
- `residual_risks`：仍未解决或需人工确认的风险。

### 4.3 Mistake Ledger

新增 `docs/harness-engineering/core/mistake-ledger.md`。

记录“系统不能再重复犯”的错误：

- 错误现象。
- 根因。
- 影响范围。
- 修复方式。
- 新增防线。
- 关联测试或检查命令。
- 下一次如何被自动发现。

原则：只记录值得系统学习的问题，不记录普通临时探索。

### 4.4 Verification Matrix

新增 `docs/harness-engineering/core/verification-matrix.md`。

把变更类型映射到验证命令，降低 AI 随意选择测试范围的概率。

示例：

| 变更类型 | 最低验证 | 加强验证 |
|---|---|---|
| API 路由 | `pytest tests/api -q` | `python scripts/check_project.py` |
| Service 逻辑 | 对应 `tests/service` | 全量 pytest |
| Repository/数据库 | `tests/repository` + migration tests | preflight dry-run |
| 上线脚本 | `tests/scripts` | 生成 JSON 报告样例 |
| 文档/流程 | 链接和关键词检查 | LOGBOOK 同步检查 |

### 4.5 Agent Handoff Template

新增 `docs/harness-engineering/core/agent-handoff-template.md`。

用于上下文重置、换 Agent、长任务续跑：

- 当前目标。
- 当前状态。
- 已改文件。
- 已验证内容。
- 未验证内容。
- 风险和下一步。

### 4.6 Reports 规范

约定生产证据优先写入：

```text
reports/harness/
reports/preflight-*.json
reports/smoke-*.json
reports/migration-*.json
reports/baseline-seed-*.json
reports/rebuild-embeddings-*.json
```

JSON 报告必须满足：

- 包含 `metadata.generated_at` 或等价字段。
- 记录项目根、目标数据库、目标向量路径、服务地址和版本号。
- 拒绝覆盖已有文件。
- 写库动作必须有 dry-run 和 apply 两类证据。

证据文件生成后，应在 `docs/harness-engineering/core/evidence-index.md` 登记索引，记录 `trace_id`、报告类型、生成命令、结果、关联 LOGBOOK 和敏感数据状态。

### 4.7 ADR 规范

关键架构决策写入 `docs/harness-engineering/adr/`：

- `docs/harness-engineering/adr/README.md` 定义模板、状态和触发条件。
- `docs/harness-engineering/adr/0001-traceable-memory-harness.md` 记录采用 Traceable Memory Harness 作为 Vibe Coding 驾驭框架的首条决策。
- 后续改变分层边界、上线流程、Harness 机制、关键依赖或生产恢复策略时，应新增 ADR。

______________________________________________________________________

## 5. 错误防重犯机制

当出现以下情况时，必须更新 `mistake-ledger`：

- 同一问题第二次出现。
- AI 违反项目红线或删除/覆盖风险。
- 上线前检查发现本可提前发现的问题。
- 修复后没有测试覆盖的缺陷。
- 需要人工反复提醒的流程遗漏。

每条 mistake 必须至少选择一种防线：

| 防线类型 | 优先级 | 示例 |
---|---:|---|
| 自动测试 | 1 | 新增回归测试 |
| 静态检查脚本 | 2 | 扩展 `check_project.py` |
| pre-commit/CI 门禁 | 3 | 接入阻断或非阻断检查 |
| Guard Skill / AGENTS 规则 | 4 | 强制启动前读取 |
| Runbook / 文档 | 5 | 补操作步骤和恢复口径 |

如果只能补文档，必须在 ledger 中说明为什么暂时不能机械化。

______________________________________________________________________

## 6. Vibe Coding 工作流

### 6.1 开始任务

1. 读取 `AGENTS.md`。
2. 读取 `LOGBOOK.md` 最新条目。
3. 按任务类型调用相关 skill。
4. 若任务有设计或行为变化，先生成或更新 spec。
5. 为任务分配 `trace_id`。

### 6.2 实施中

1. 保持改动聚焦，不跨越不必要架构边界。
2. 重要决策写入 spec 或 ADR。
3. 不确定项写入 residual risks，不靠聊天记忆兜底。

### 6.3 收口时

1. 根据 verification matrix 选择验证命令。
2. 生成必要 JSON 报告或记录命令结果。
3. 更新 LOGBOOK 和项目进度清单。
4. 若出现失误，更新 mistake ledger。
5. 需要交接时填写 handoff template。

______________________________________________________________________

## 7. 分阶段路线图

### P0：文档闭环，立即落地

- 新增 `docs/harness-engineering/README.md`。
- 新增 `traceability-model.md`。
- 新增 `mistake-ledger.md`。
- 新增 `verification-matrix.md`。
- 新增 `agent-handoff-template.md`。
- 在 LOGBOOK 记录本轮 Harness 规划落地。

验收信号：

- 新 Agent 能从 `docs/harness-engineering/README.md` 找到所有入口。
- 任意一次复杂任务都能按模板产出 trace。
- 变更收口时能按矩阵选择验证命令。

### P1：脚本辅助，减少人工遗漏

- 新增 `scripts/harness_snapshot.py`，输出当前任务快照。（已落地）
- 新增 `scripts/check_mistake_ledger.py`，检查 mistake ledger 结构是否可机器读取。（已落地）
- 在 pre-commit 中以非阻断方式提示 Harness 缺口。
- 增加 `docs/harness-engineering/adr/` 模板。（已落地）

验收信号：

- 可一键生成 handoff snapshot。
- 重大修复没有 ledger 或测试时会被提示。
- 架构变化有 ADR 可追溯。

### P2：验证编排，提升生产证据质量

- 根据文件变更自动推荐 verification matrix 命令。
- 汇总 pytest、ruff、mypy、preflight、smoke 结果为统一 evidence report。
- 规范 `reports/harness/` 的命名、保留和索引。（索引文档和目录已落地）

验收信号：

- 上线前能生成一个完整证据包。
- 证据包可证明配置、数据库、知识、向量、后台和接口状态。

### P3：多 Agent 协作

- Builder Agent 负责实现。
- Reviewer Agent 负责风险和测试审查。
- Release Captain Agent 负责上线证据包。
- Memory Curator Agent 负责 mistake ledger 和规则演进。

验收信号：

- 长任务可以分工并行。
- 复盘结论能自动建议新增哪类 Harness。

______________________________________________________________________

## 8. 风险与约束

- Harness 不能过度阻断，否则 Vibe Coding 会变慢；第一阶段以文档和轻量检查为主。
- mistake ledger 不能变成流水账，只收录会导致重复损失的问题。
- JSON 报告不要提交敏感信息，生产证据包要避免泄露 Token、客户隐私和订单敏感字段。
- 当前工作区已有大量生产化补强改动，本设计只新增文档，不改动业务代码。

______________________________________________________________________

## 9. 验收清单

- [ ] `docs/harness-engineering/README.md` 存在并能作为入口。
- [ ] `traceability-model.md` 定义 trace 字段和证据链。
- [ ] `mistake-ledger.md` 定义防重犯流程。
- [ ] `verification-matrix.md` 覆盖主要变更类型。
- [ ] `agent-handoff-template.md` 支持上下文重置交接。
- [ ] LOGBOOK 记录本轮 Harness 设计落地。
- [ ] 所有新增文档无未完成占位。
