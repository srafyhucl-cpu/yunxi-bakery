# ADR 0004：文件体量采用责任优先治理

- status: accepted
- date: 2026-07-10
- trace_id: 20260710-responsibility-first-file-size-governance
- decision_owner: project owner / AI (Codex)
- related_docs:
  - `.agents/skills/yunxi-file-size-guard/SKILL.md`
  - `scripts/check_file_sizes.py`
  - `docs/AGENTS/coding-red-lines.md`
  - `docs/AGENTS/skill-reference.md`

## Context

项目设置文件和函数体量阈值，原始目的，是尽早发现职责不断堆积、依赖失控和难以测试的上帝类。现有规则虽然写过“阈值不是拆分目标”，但 Skill 描述、上帝类判定、验收清单和 pre-commit 提示仍带有“超线就拆”的含义。

只按行数拆分会制造另一类维护问题：薄转发文件、无业务含义的 helper、跨文件状态传递、循环依赖，以及阅读一条调用链需要频繁跳转。文件变短不等于设计变好，也不能证明职责更清晰。

## Decision

采用责任优先的文件体量治理：

1. 行数阈值是评审触发器，不是拆分目标；公开类/方法数量和函数长度也不单独构成上帝类判定。
2. 超过阻断线且没有评审记录的新文件继续阻断提交，阻断原因是“未经评审”，不是“必须拆到线下”。
3. 职责评审必须关注独立变化原因、业务所有权、依赖方向、测试隔离成本和候选接口稳定性。
4. 只有存在可命名、可独立测试、依赖清晰的职责边界时才拆分。
5. 高度内聚的单一职责可以保留超线实现，但要记录保留理由、允许职责和禁止继续追加的范围。
6. 暂时无法安全拆分的存量代码要记录候选边界；禁止为了让门禁变绿而按行数切块、增加薄转发层或搬运代码。
7. `scripts/check_file_sizes.py` 的 `OVERSIZE_REVIEW_NOTES` 是存量超线评审说明的唯一机器入口；每次修改仍需复核说明是否有效。

职责评审输出使用三种结论：

- `split_by_responsibility`
- `keep_cohesive_with_review`
- `defer_with_boundary_plan`

## Alternatives

- 继续把行数当硬拆分目标：规则简单，但容易优化错误指标，产生碎片化和胶水代码。
- 完全取消体量门禁：避免误拆，但失去对职责膨胀的早期提醒，新上帝类更容易无审查进入主干。
- 只依赖人工 code review：判断更灵活，但长任务和多 Agent 续跑时容易遗失上下文，缺少稳定机械入口。

## Consequences

- 正向影响：保留体量预警能力，同时让拆分以职责、测试和依赖改善为验收标准。
- 正向影响：单一职责的长文件不再被迫碎片化，跨文件认知成本会进入设计比较。
- 正向影响：存量超线文件必须有可读评审说明，而不是只有路径白名单。
- 代价：机器无法自动判断职责内聚性，评审仍需要工程判断和可追溯说明。
- 代价：`OVERSIZE_REVIEW_NOTES` 需要随架构变化维护，不能成为永久豁免列表。

## Verification

- `python -m pytest tests/scripts/test_check_file_sizes.py -q --no-cov`
- `python scripts/check_file_sizes.py`
- `python scripts/check_project.py --skip-tests`
- `python scripts/check_evidence_index.py --summary`
