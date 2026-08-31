# Project Management System

本文件说明 `YunxiBakeMiniApp` 的项目管理体系。它不替代 Harness 规则，而是把需求、路线图、契约、验证、证据、发布和交接串成一个统一工作流。

## 目标

- 让每次变更都能追溯：为什么做、谁来承接、改了什么、怎么证明。
- 让前后台边界稳定：本仓保持 `Storefront MiniApp` 渠道定位，业务真相回到 `YunxiBakeBot` / `Platform`。
- 让发布风险可见：微信登录、支付、订单、客服、客户群登记、审核和真机验证都有明确证据。
- 让长任务可交接：上下文重置、跨 Agent 或跨仓推进时不依赖聊天记忆。

## 文档体系

| 类别 | 权威文档 | 用途 |
|---|---|---|
| 启动规范 | `AGENTS.md` | Agent 开始任务前必须遵守的边界、红线和启动检查 |
| 项目入口 | `README.md` | 仓库定位、本地打开、目录和管理体系入口 |
| 项目编年史 | `LOGBOOK.md` | 关键推进、验证、风险和本轮变更记录 |
| 路线图 | `docs/roadmap.md` | 阶段目标、MVP 范围和客户群运营闭环 |
| 边界 | `docs/architecture/project-boundaries.md` | Storefront MiniApp / Platform 职责分界 |
| API 契约 | `docs/api-contract.md` | 小程序调用 Platform API 的路径、字段和状态口径 |
| Harness 入口 | `docs/harness-engineering/README.md` | 追溯、验证、证据、ADR、交接的入口 |
| 验证矩阵 | `docs/harness-engineering/core/verification-matrix.md` | 按变更类型选择最低验证和加强验证 |
| 证据索引 | `docs/harness-engineering/core/evidence-index.md` | 截图、报告、命令输出、发布记录的索引 |
| 防重犯 | 根目录 `ERRORS.md` | 记录复发风险高的错误和新增防线（唯一正式账本） |
| 交接 | `docs/harness-engineering/core/agent-handoff-template.md` | 长任务暂停或换 Agent 时的交接模板 |
| 长期决策 | `docs/harness-engineering/adr/` | 项目边界、渲染基线、发布策略等长期决策 |
| 发布验收 | `docs/release/manual-acceptance-checklist.md` | 自动化之外的体验版、真机、支付和审核材料 |

## 工作节奏

```text
需求、故障或上线动作
-> 读取 AGENTS / LOGBOOK / Harness 入口
-> 分配 trace_id
-> 判断是否需要更新路线图、ADR、契约或发布清单
-> 实施变更
-> 按验证矩阵跑最低验证
-> 把报告、截图或命令输出登记到证据索引
-> 在 LOGBOOK 顶部追加条目
-> 如任务未完，写 handoff
```

## Trace ID

格式使用：

```text
YYYYMMDD-topic
```

示例：

- `20260622-project-management-system`
- `20260622-customer-group-registration-page`
- `20260622-payment-flow-regression`

同一轮跨多个文件或跨仓推进时使用同一个 trace_id；如果后续另起独立目标，创建新的 trace_id。

## 文档更新规则

- 改 API 字段、状态或路径：先更新 `docs/api-contract.md`。
- 改阶段目标、延期项或新闭环：更新 `docs/roadmap.md`。
- 改仓库职责或跨仓归属：更新 `docs/architecture/project-boundaries.md`，必要时写 ADR。
- 改发布、真机、支付、审核要求：更新 `docs/release/manual-acceptance-checklist.md`。
- 改验证标准：更新 `docs/harness-engineering/core/verification-matrix.md`。
- 改交接要求：更新 `docs/harness-engineering/core/agent-handoff-template.md`。
- 发生值得记住的错误：更新根目录 `ERRORS.md`，不得创建副本。
- 每个较大任务收口：更新 `LOGBOOK.md` 和证据索引。

## 验证分级

| 场景 | 最低证据 |
|---|---|
| 纯文档更新 | `Test-Path`、关键 `rg` 搜索、`git diff --check` |
| 小程序页面或 TS 逻辑 | `npm run check:miniapp`、`npm run typecheck` |
| API client 或契约 | 契约对照、typecheck，必要时后端测试环境联调 |
| 发布准备 | `npm run release:readiness`、DevTools preview、发布清单 |
| 真机/体验版 | 截图、录屏、二维码、平台配置截图 |
| 真实微信支付 | 测试商户或小额真实支付链路证据 |

没有执行的验证必须写明原因，不能用“应该没问题”替代证据。

## 高风险路径

以下路径不得只靠本地静态检查宣布完成：

- 微信登录和用户归属。
- 下单、支付、取消、超时关闭和库存释放。
- 客服消息、转人工、客户群登记和后台跟进。
- 体验版、真机、合法域名、隐私协议、服务类目和审核提交。
- 需要 `YunxiBakeBot` 实现、配置或发布的后端能力。

## 当前关键口径

- 本仓是 `Storefront MiniApp` 渠道仓，不实现 Platform 业务真相。
- API 提供方是 `YunxiBakeBot`。
- MVP 阶段默认 WebView 渲染，Skyline / glass-easel 只作为后续页面级性能专项。
- 支付默认模式为 `mock`；`store_confirm` 仅作为历史兼容值；真实支付必须切到 `wechat` 并完成商户联调。
- 客户群运营采用“小程序结构化登记 + Platform 后台汇总 + 微信客服单聊承接”，不在企业微信群内做实时 AI 自动回复。

## 完成定义

一个较大任务只有在以下条件满足时才算完成：

- 需求范围内的代码或文档已经更新。
- 涉及的契约、路线图、边界、发布清单和 ADR 已同步。
- 验证矩阵要求的最低验证已执行，或未执行原因明确记录。
- 证据索引有对应证据，或 LOGBOOK 中说明为什么没有持久证据。
- LOGBOOK 顶部有本轮条目，并列出残余风险。
- 如果还有未完成事项，已写入 residual risks 或 handoff，而不是口头遗留。
