# Architecture Decision Records

本目录记录会影响项目长期演进的架构决策。ADR 的作用不是写长论文，而是让后续 AI Agent 和人工开发者能快速知道：为什么当时这么选、替代方案是什么、后续什么条件下可以重新评估。

______________________________________________________________________

## 何时需要 ADR

- 改变分层边界、数据流、部署方式、上线流程或 Harness 机制。
- 引入或移除关键依赖。
- 修改会影响多个模块的运行时行为。
- 用户或 AI 已经围绕同一问题反复讨论，后续容易“重走一遍”。
- 决策会影响生产同步、数据安全、可观测性或恢复流程。

______________________________________________________________________

## 命名规则

```text
NNNN-short-title.md
```

示例：

```text
0001-traceable-memory-harness.md
```

______________________________________________________________________

## 状态

| 状态 | 说明 |
|---|---|
| proposed | 已提出，尚未执行 |
| accepted | 当前采用 |
| superseded | 已被后续 ADR 替代 |
| rejected | 明确不采用 |

______________________________________________________________________

## 当前决策

| ADR | 状态 | 决策 |
|-----|------|------|
| [0001](0001-traceable-memory-harness.md) | accepted | 建立可追溯、可交接、可防重犯的 Harness |
| [0002](0002-platform-storefront-boundaries-and-instance-naming.md) | accepted | 统一 Platform、storefront 边界与实例命名 |
| [0003](0003-langchain-ai-layer-boundary.md) | accepted | LangChain 接管 AI 应用层但不接管业务领域层 |
| [0004](0004-responsibility-first-file-size-governance.md) | accepted | 文件体量只触发职责评审，禁止为压行数机械拆分 |
| [0005](0005-framework-first-single-path.md) | accepted | 通用能力框架优先，AI 应用层保持单一生产路径 |
| [0006](0006-sqlite-inbox-outbox-exception.md) | accepted | 单机 SQLite 持久 inbox 的窄例外与退出条件 |
| [0007](0007-local-authority-cutover.md) | accepted | 2027-06 为会员账务本地权威切换最早候选窗口，真实开放须项目负责人批准 |
| [0008](0008-accounting-core-consistency.md) | proposed | 账务核心一致性：单一 Unit of Work、券命令模型（transition_key 含类型+支付尝试/RESERVED 预占/投影 CAS/事件版本合同/券事件三类分离）、持久退款聚合（B1.6–B3.2 补齐 UoW/outbox/退款额度泛化与逐腿额度/分派状态机/payment_attempt 状态机/资金腿与预占持久化（member_balance_id 账户绑定）/支付提供方事件 inbox 与租约 CAS/prepay_unknown 固定映射/差分分摊与短缺债务表/authority epoch 围栏与单指针/券观察与对账案件合同/D1-0 唯一事实迁移、B3.2 收敛（回调以快照微信腿对照+三类事件键/查询代次受控 rearm+支付状态命令表/债务绑定账户与剩余金额 min 部分收回/券摄取裁决同 UoW 关案/epoch 仅入队端读指针+enqueue fence+删除 identity_mode/CT-1A 围栏前置 FP-4A），批准后进入代码实施） |

______________________________________________________________________

## 模板

```markdown
# ADR NNNN：标题

- status: proposed | accepted | superseded | rejected
- date: YYYY-MM-DD
- trace_id:
- decision_owner:
- related_docs:

## Context

背景、约束、现有问题。

## Decision

明确采用的方案。

## Alternatives

- 方案 A：优点 / 缺点
- 方案 B：优点 / 缺点

## Consequences

- 正向影响
- 负向影响
- 后续需要补的 Harness、测试或文档

## Verification

- 如何证明该决策被正确落地
```
