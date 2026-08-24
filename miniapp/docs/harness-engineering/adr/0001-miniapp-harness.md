# ADR-0001 自研小程序采用轻量 Harness Engineering

- status: accepted
- date: 2026-06-16
- decision_owner: YunxiBakeMiniApp
- trace_id: 20260616-miniapp-harness
- related_docs:
  - AGENTS.md
  - LOGBOOK.md
  - docs/project-management.md
  - docs/harness-engineering/README.md
  - docs/harness-engineering/core/traceability-model.md
  - docs/harness-engineering/core/verification-matrix.md
  - docs/harness-engineering/core/evidence-index.md
  - docs/harness-engineering/core/agent-handoff-template.md
- review_trigger: 管理文档无法覆盖新工作流、发布门槛或跨 Agent 交接时回看

## 背景

YunxiBakeMiniApp 是从有赞迁出的自研微信小程序前台渠道仓，独立于 `YunxiBakeBot` 后端项目。项目刚完成骨架初始化，后续会逐步接入商品、购物车、下单、微信登录、微信支付、订单查询和 AI 客服。为了避免开发过程只依赖聊天记忆，需要在正式开发前维护一套轻量 Harness Engineering。

## 决策

采用推荐版轻量 Harness：

- 保留 `AGENTS.md` 作为 Agent 启动入口。
- 使用 `LOGBOOK.md` 记录关键推进。
- 在 `docs/harness-engineering/core/` 维护追溯模型、验证矩阵、证据索引、防重犯账本和交接模板。
- 在 `docs/harness-engineering/adr/` 记录长期技术决策。
- 暂不引入后端项目的脚本化快照、pre-commit 和生产预检复杂度，等小程序进入联调或发布阶段再补。

## 后果

收益：

- 每个任务都有 trace_id、验证和残余风险。
- API 契约变更会被显式追踪，降低前后端脱节概率。
- 长任务或换 Agent 时更容易交接。

代价：

- 每次较大任务需要更新 LOGBOOK 和必要证据。
- 初期缺少自动脚本检查，仍依赖执行者遵守文档。

## 替代方案

1. 只保留 `AGENTS.md`：更轻，但长期追溯能力不足。
2. 全量照搬 `YunxiBakeBot` Harness：更严格，但小程序起步阶段负担偏重。

## 验证与回看

当出现以下任一情况时回看本 ADR：

- 小程序进入支付/订单/发布联调阶段。
- 同类遗漏或验证不足问题出现第二次。
- 项目开始多人协作或频繁跨 Agent 交接。
