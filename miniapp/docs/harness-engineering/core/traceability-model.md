# Traceability Model

本文件定义 YunxiBakeMiniApp 的任务级追溯模型。目标是让每次小程序变更都能回答：为什么改、改了什么、怎么证明、还剩什么风险。

## Trace ID

推荐格式：

```text
YYYYMMDD-topic
```

示例：

```text
20260616-miniapp-harness
20260617-product-list
20260618-checkout-order-draft
20260620-wechat-login
```

## 任务追溯字段

| 字段 | 必填 | 说明 |
|---|---|---|
| `trace_id` | 是 | 任务级追踪号 |
| `source` | 是 | 用户请求、故障、设计文档或上线需求 |
| `goal` | 是 | 本轮要达成的结果 |
| `decision_refs` | 否 | 设计文档、ADR、关键讨论或接口契约 |
| `changed_files` | 是 | 核心改动文件 |
| `api_contract_impact` | 是 | 是否影响 `docs/api-contract.md`；若影响，必须先更新契约 |
| `verification` | 是 | 执行过的检查命令、微信开发者工具验证或人工验收 |
| `evidence` | 否 | 截图、报告、日志、审核材料、测试输出 |
| `release_or_platform_impact` | 否 | 是否影响体验版、真机、合法域名、微信支付、审核或 Platform 后端协作 |
| `logbook_entry` | 是 | `LOGBOOK.md` 对应条目标题 |
| `residual_risks` | 否 | 未解决风险、人工确认项或未验证范围 |

## 推荐记录模板

```markdown
### Trace: 20260617-product-list

- source: 自研小程序 M1 商品浏览
- goal: 商品列表从后端 API 拉取并展示加载、空态、错误态
- decision_refs:
  - docs/api-contract.md
  - docs/harness-engineering/adr/0001-miniapp-harness.md
- changed_files:
  - miniprogram/pages/products/index.ts
  - miniprogram/pages/products/index.wxml
  - miniprogram/services/products.ts
- api_contract_impact: 无字段变更
- release_or_platform_impact: 需要微信开发者工具打开商品页；不涉及后端实现变更
- verification:
  - npm run typecheck 通过
  - 微信开发者工具手工打开商品页，加载态和错误态可见
- evidence:
  - docs/harness-engineering/core/evidence-index.md 对应条目
- residual_risks:
  - 后端真实图片 CDN 域名需加入微信 request/download 合法域名
```

## 证据等级

| 等级 | 证据 | 说明 |
|---|---|---|
| L1 | 口头说明 | 只能作为线索 |
| L2 | 文档记录 | 可追溯，但不能证明行为正确 |
| L3 | 命令输出 | 能证明本地某次检查结果 |
| L4 | 截图/录屏/JSON 报告 | 适合页面验收、接口验收和审核材料 |
| L5 | CI、生产监控、微信审核记录 | 发布和事故复盘首选 |

代码行为变更至少达到 L3；页面交互变更尽量达到 L4；发布相关任务尽量达到 L5。

## 工作区归属

如果开始任务时已有未提交改动，LOGBOOK 或 handoff 中必须区分：

- 本轮新增或修改的文件。
- 开始前已存在、但本轮没有接管的文件。
- 本轮验证覆盖了哪些改动，哪些改动只是共存于工作区。

不得把未验证的既有改动写成“本轮已完成”；也不得为了收口回滚用户或其他 Agent 的改动。

## 高风险影响标记

以下任一场景需要在 `release_or_platform_impact` 或 residual risks 中显式说明：

- 微信登录、openid/session、用户归属。
- 下单、支付、库存、取消、超时关闭。
- 客服消息、转人工、客户群登记和后续跟进。
- 发布、体验版、审核、合法域名、隐私协议。
- 需要 `YunxiBakeBot` 同步实现或配置的后端能力。
