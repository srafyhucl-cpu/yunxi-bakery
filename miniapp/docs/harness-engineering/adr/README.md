# ADR

本目录记录会影响长期演进的架构决策。普通页面细节不需要写 ADR；涉及项目边界、技术栈、发布策略、支付/订单归属、跨项目 API 契约等，需要写。

## ADR 模板

```markdown
# ADR-000X 标题

- status: proposed | accepted | superseded
- date:
- decision_owner:
- trace_id:
- related_docs:
- review_trigger:

## 背景

## 决策

## 后果

## 替代方案

## 验证与回看
```

## 写入规则

- ADR 只记录长期难以随手反复的决策，不记录普通页面微调。
- 决策影响 API、发布、支付、订单、客户群运营或仓库边界时，必须在 `related_docs` 写明需要同步的契约、路线图、发布清单或边界文档。
- `review_trigger` 要写清楚何时回看，例如“真实微信支付上线前”“客户群后台闭环接入前”“Skyline 页面级试点前”。
- ADR 被新决策替代时，不删除旧文件，新增 ADR 并把旧 ADR 状态改为 `superseded`。

## 索引

| ADR | 状态 | 标题 |
|---|---|---|
| [0001](0001-miniapp-harness.md) | accepted | 自研小程序采用轻量 Harness Engineering |
| [0002](0002-miniapp-rendering-baseline.md) | accepted | MVP 阶段采用默认 WebView 渲染基线 |
| [0003](0003-storefront-platform-boundary.md) | accepted | 将 YunxiBakeMiniApp 定位为 Storefront MiniApp 渠道仓 |
