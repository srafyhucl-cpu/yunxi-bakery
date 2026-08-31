# Harness Engineering

本目录是 `Storefront MiniApp` 渠道仓的 AI 开发驾驭系统入口。它的目标不是制造流程，而是让“从有赞迁到自研小程序前台渠道”的每一步都能追溯、验证、交接和复盘。

当前逻辑总项目名是 `Bakery Commerce Platform`；`YunxiBakeMiniApp` 只是当前仓库路径，职责是消费者前台渠道。`YunxiBakeBot` 是 `Platform` 主仓，承载客户、商品、订单、AI 会话、店铺配置和第三方集成等业务真相。

## 快速入口

| 场景 | 先看 |
|---|---|
| 开始一个任务 | `AGENTS.md`、`LOGBOOK.md` 最新条目、本文件 |
| 需要理解项目管理体系 | [../project-management.md](../project-management.md) |
| 需要给任务留追溯 | [core/traceability-model.md](core/traceability-model.md) |
| 不确定该跑哪些验证 | [core/verification-matrix.md](core/verification-matrix.md) |
| 开发页面前避免重复和魔法值 | [core/reuse-and-configuration-rules.md](core/reuse-and-configuration-rules.md) |
| 需要登记截图、报告、审核材料 | [core/evidence-index.md](core/evidence-index.md) |
| 犯过一次值得记住的错 | [根目录 ERRORS.md](../../ERRORS.md) |
| 上下文要重置或换 Agent | [core/agent-handoff-template.md](core/agent-handoff-template.md) |
| 需要记录长期技术决策 | [adr/README.md](adr/README.md) |
| 需要确认双仓职责边界 | [../architecture/project-boundaries.md](../architecture/project-boundaries.md) |
| 需要确认页面/API 覆盖和本仓业务边界 | [../page-api-coverage.md](../page-api-coverage.md) |
| 需要确认 MiniApp 可观测指标和隐私边界 | [../observability-contract.md](../observability-contract.md) |
| 需要确认小程序 CI 上传密钥和环境变量边界 | [../release/miniprogram-ci-readiness.md](../release/miniprogram-ci-readiness.md) |
| 准备发布、体验版、真机或支付验收 | [../release/manual-acceptance-checklist.md](../release/manual-acceptance-checklist.md) |
| 需要确认阶段目标和后续闭环 | [../roadmap.md](../roadmap.md) |

## 目录地图

| 目录 | 放什么 |
|---|---|
| `core/` | 日常运行规则：追溯、验证、防重犯、交接、证据索引 |
| `adr/` | 长期架构决策记录 |
| `specs/` | 需求设计、迁移方案、阶段实施规格 |
| `../release/` | 发布、体验版、真机、支付和审核验收材料 |
| `../architecture/` | 仓库边界、职责归属和跨仓协作口径 |

## 工作原则

1. `Storefront MiniApp` 和 `Platform` 主仓保持项目边界，靠 API 契约对接。
2. API 字段变更先改 `docs/api-contract.md`，再改页面和服务调用。
3. 任何“已完成”都要对应验证证据；没跑的验证必须写明原因。
4. 微信登录、支付、订单、客服、审核发布属于高风险路径，至少保留命令输出、截图或检查记录。
5. 同类错误第二次出现时，优先补 Harness 规则或验证清单，而不是只修当前代码。
6. 生产、体验版、真机、合法域名、微信支付和审核动作不得只靠本地自动化结论，需要在发布清单或证据索引中留下平台侧证据。
7. 客户群运营走“小程序结构化登记 + Platform 后台汇总 + 微信客服单聊承接”，不把企业微信群内实时 AI 自动回复写成本仓能力。

## 标准闭环

```text
需求或故障
→ 分配 trace_id
→ 更新 API 契约或设计文档
→ 实施变更
→ 按验证矩阵执行检查
→ 登记证据
→ 更新 LOGBOOK
→ 必要时写 ADR 或 handoff
```

## 管理文档分层

| 层级 | 文档 | 维护时机 |
|---|---|---|
| 启动规范 | `AGENTS.md`、`README.md` | 项目边界、工具红线、启动步骤或管理入口变化 |
| 计划和边界 | `docs/roadmap.md`、`docs/architecture/project-boundaries.md` | 阶段目标、跨仓职责、能力归属变化 |
| 契约 | `docs/api-contract.md` | API 路径、字段、状态、错误或调用口径变化 |
| 执行规则 | `core/traceability-model.md`、`core/verification-matrix.md`、`core/reuse-and-configuration-rules.md` | 任务追溯、验证门槛、复用规则变化 |
| 证据和复盘 | `core/evidence-index.md`、根目录 `ERRORS.md`、`LOGBOOK.md` | 验证完成、风险登记、错误防重犯 |
| 发布验收 | `docs/release/manual-acceptance-checklist.md` | 体验版、真机、支付、合法域名、审核材料变化 |
| 长期决策 | `adr/` | 渲染基线、仓库边界、支付归属、发布策略等不可轻易反复的决策 |
| 交接 | `core/agent-handoff-template.md` | 长任务暂停、上下文重置、换 Agent 或跨仓继续 |

## 当前 Harness 资产

| 文件 | 作用 |
|---|---|
| `AGENTS.md` | Agent 启动规范、项目边界和红线 |
| `LOGBOOK.md` | 项目演进编年史 |
| `docs/project-management.md` | 项目管理体系总览 |
| `docs/api-contract.md` | 小程序调用后端的接口契约 |
| `docs/observability-contract.md` | 小程序页面、商品、购物车、支付、客服和会话门槛的可观测指标契约 |
| `docs/page-api-coverage.md` | 页面、服务、Platform API 和业务边界覆盖合约 |
| `docs/architecture/project-boundaries.md` | Storefront MiniApp / Platform 职责边界 |
| `docs/roadmap.md` | MVP 里程碑 |
| `docs/release/miniprogram-ci-readiness.md` | 小程序 CI 上传前的密钥、依赖和环境变量准备合约 |
| `docs/release/manual-acceptance-checklist.md` | 发布、真机、体验版、微信支付和审核手工验收清单 |
| [core/traceability-model.md](core/traceability-model.md) | 任务追溯字段和 trace_id 规则 |
| [core/verification-matrix.md](core/verification-matrix.md) | 按变更类型选择验证 |
| [core/reuse-and-configuration-rules.md](core/reuse-and-configuration-rules.md) | 页面开发的复用、配置和禁止魔法值规则 |
| [core/evidence-index.md](core/evidence-index.md) | 证据索引 |
| [根目录 ERRORS.md](../../ERRORS.md) | 防重犯账本（唯一正式入口） |
| [core/agent-handoff-template.md](core/agent-handoff-template.md) | 交接模板 |
| [adr/README.md](adr/README.md) | 架构决策入口 |
