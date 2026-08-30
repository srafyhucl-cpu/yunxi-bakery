# 双仓推进节奏与 MiniApp 第一阶段最小改造清单（历史摘录）

> 说明：这份文档记录的是早期双仓推进思路，当前已进入新一轮 canonical 收口阶段。文中“MiniApp 第一阶段”更多是历史过渡方案，不应直接当作现阶段必须执行的最新路线。本文只保留历史摘录。

## 历史目标

这份文档用于把 `Bakery Commerce Platform` 的双仓推进顺序固定下来，避免 `Platform` 和 `Storefront MiniApp` 在重组过程中再次出现职责回流。

当时原则只有三条：

- 继续保留两个代码仓，不新建第三个代码仓。
- `Platform` 先完成内部 canonical 领域收口，不等待 `MiniApp` 大改。
- `MiniApp` 先做轻量第一阶段对齐，只校正边界和命名口径，不抢先重写业务。

## 历史结论先行

早期观点里曾有一种说法：第二阶段不是必须先把 `YunxiBakeMiniApp` 做完，`Platform` 才能继续推进。

但在当时的判断里，如果不尽快给 `YunxiBakeMiniApp` 补一个轻量版第一阶段，后续双仓会继续在认知上混淆：

- `Platform` 一边尝试成为业务真相源。
- `MiniApp` 一边继续把自己当成业务逻辑落点。

所以正确节奏不是“先大改 MiniApp”，而是：

1. `Platform` 继续做内部领域收口。
2. `MiniApp` 补一轮轻量边界对齐。
3. 双仓再进入联动治理阶段。

## 历史三个阶段

### 阶段 A：Platform 内部收口先行（历史）

适用范围：

- `customer`
- `order`
- `catalog`
- `conversation`
- `ops`
- `integrations`
- `channels/storefront`

当时允许继续做的事：

- 把 `miniapp_*` 中的真实实现逐步搬到 canonical 领域。
- 保持现有 HTTP 路由、数据库 schema、MiniApp API 契约不变。
- 保留旧 service key 和旧 facade 作为兼容层。

当时已完成的代表性收口：

- `catalog`、`customer`、`order`、`conversation/storefront`、`channels/storefront`
- `order` 内部的库存、预约、序列化、支付真实实现
- `ops/order_timeout_scheduler`
- `integrations/wechat_pay`
- `app/service` 下既有 `miniapp_*.py` 已全部退为兼容层，不再承载真实实现

当时不要求：

- 不要求 `MiniApp` 同步改页面逻辑。
- 不要求立刻改仓库名。
- 不要求前台渠道一起重写接口。

### 阶段 B：MiniApp 轻量第一阶段对齐（历史）

`YunxiBakeMiniApp` 此时只做“边界澄清”，不做大规模业务重写。当前如需查看最新口径，请以 `docs/architecture/project-boundaries.md` 为准。

最小改造清单（历史）：

1. README 和项目标题改为 `Storefront MiniApp` 口径，明确它是消费者前台渠道仓。
2. 文档中把 `Yunxi` 改成首个实例名，而不是产品名。
3. 增加一份边界说明，写清楚客户主档、订单规则、商品规则、CRM、集成都归 `Platform`。
4. 梳理 API client 目录或调用约定，明确 `MiniApp` 只消费 `Platform` 能力。
5. 标记禁区：`MiniApp` 不再新增客户主档、商品规则、订单规则真相。
6. 把“后台配置嵌在 Bot 管理页里”的现状写成过渡态，而不是长期架构。

本阶段刻意不做的事（历史）：

- 不重写页面。
- 不重做前台状态管理。
- 不迁移复杂业务逻辑到前台。
- 不修改已稳定运行的前台用户流程。

执行细则见：[miniapp-phase1-execution-checklist.md](./miniapp-phase1-execution-checklist.md)
如果需要把具体执行要求交给 `YunxiBakeMiniApp` 仓的 AI，使用：[miniapp-ai-handoff-plan.md](./miniapp-ai-handoff-plan.md)

如果需要查看当前 `Platform` 仓的有赞客户迁移全链路，请优先看：

- [有赞客户迁移审计清单](./youzan-customer-migration-audit-checklist.md)
- [有赞客户正式迁移执行 Runbook](./youzan-customer-formal-import-runbook.md)
- [有赞客户迁移后核对脚本](../../scripts/verify_youzan_customer_import.py)
- [有赞客户迁移交接与回滚 Runbook](./youzan-customer-import-handoff-and-rollback-runbook.md)

### 阶段 C：双仓联动治理（历史）

只有在 A 和 B 都完成后，再进入这一阶段：

- 统一接口命名与字段语义。
- 明确前后台发布节奏。
- 收缩旧 `miniapp_*` 命名。
- 准备后续可能的仓库改名或 monorepo 评估。

## 为什么当时不是先改 MiniApp

原因很实际：

- 当前混乱的根源主要在 `Platform` 仓内部，`miniapp_*` 命名承载了过多平台真相。
- 如果先大改 `MiniApp`，但 `Platform` 还没把领域真相收口，前台只会跟着旧混乱再包一层。
- `MiniApp` 当前更像消费者渠道，最重要的是先认边界，而不是先重写实现。

所以 `MiniApp` 当前最该做的是“认清自己是谁”，不是“先把所有代码改漂亮”。

## 仓库改名时机（历史）

当前不建议立刻修改仓库名。

建议时机：

1. `Platform` 的 `customer / order / catalog` 至少完成一轮真实收口。
2. `MiniApp` 已完成轻量第一阶段边界对齐。
3. 部署脚本、环境变量、CI、文档引用、团队口径已经同步。

在这之前，先统一以下内容即可：

- README 标题
- 架构图
- 内部服务命名
- 文档口径
- 产品对内对外表述

推荐未来仓库名：

- `bakery-commerce-platform`
- `bakery-storefront-miniapp`

## 历史执行顺序

推荐按下面顺序推进：

1. 继续在 `Platform` 仓抽 `customer / order / catalog` 真正实现。
2. 给 `YunxiBakeMiniApp` 做轻量第一阶段文档与边界对齐。
3. 梳理双仓 API 契约和命名映射表。
4. 再考虑仓库改名、部署链路和外部引用迁移。

## 历史验收标准

当满足以下条件时，说明双仓节奏是健康的：

- `Platform` 可以持续抽领域实现，而不要求 `MiniApp` 每次同步大改。
- `MiniApp` 团队知道哪些逻辑不该继续长在前台仓。
- 新需求默认先判断归属 `Platform` 还是 `MiniApp`，而不是凭直觉落代码。
- 团队内部已经接受 `Yunxi` 是实例名，不再把它当产品总名。
