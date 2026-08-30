# Storefront MiniApp 第一阶段最小改造执行清单（历史过渡版）

> 说明：这是一份历史上的最小改造执行清单，主要用于解释早期如何把 MiniApp 从“混合承担业务真相”收敛为前台渠道仓。当前若要判断项目边界，请优先参考 `docs/architecture/project-boundaries.md`。本文只保留历史过渡记录。

## 目标

这份清单原本不是让 `YunxiBakeMiniApp` 立刻做业务重写，而是帮助它完成第一阶段边界对齐，让双仓后续可以在清晰职责下继续推进。

一句话定义：

- `YunxiBakeMiniApp` 是 `Storefront MiniApp` 渠道仓。
- 它负责前台页面和微信端交互。
- 它不再承载客户、订单、商品、CRM、配置的业务真相。

如果 MiniApp 侧当前任务与有赞客户迁移相关，请优先参考：

- [有赞客户迁移审计清单](./youzan-customer-migration-audit-checklist.md)
- [有赞客户正式迁移执行 Runbook](./youzan-customer-formal-import-runbook.md)
- `scripts/verify_youzan_customer_import.py`
- [有赞客户迁移交接与回滚 Runbook](./youzan-customer-import-handoff-and-rollback-runbook.md)

## 本阶段的完成定义摘录（历史）

当以下四件事完成时，就可以认为 `MiniApp` 的第一阶段已完成：

1. 项目命名口径改对。
2. 项目文档边界写清。
3. API client 角色说明补全。
4. 新增禁区规则，避免职责回流。

本阶段不要求页面改版，也不要求前台重构。

## 必做项摘录（历史）

### 1. README 改造摘录（历史）

目标：

- 让任何第一次打开仓库的人，第一眼就知道它是 `Storefront MiniApp`，不是平台主仓。

建议修改点：

1. README 标题改成 `Storefront MiniApp` 或 `Bakery Storefront MiniApp`。
2. 开头增加一句定位说明：
   - 当前仓是消费者前台渠道仓。
   - 平台主仓是 `Platform`。
   - `Yunxi` 是首个实例名，不是产品总名。
3. 增加“职责边界”小节，写清楚：
   - 本仓负责页面、组件、交互、微信能力、API client、登录态、本地缓存。
   - 本仓不负责客户主档、订单规则、商品规则、AI 会话真相、后台配置真相。
4. 增加“依赖关系”小节，说明：
   - 前台商品、订单、地址、客服入口能力来自 `Platform` 提供的接口。

建议示例文案：

```md
本仓是 Storefront MiniApp 渠道仓，负责消费者前台页面与微信端交互。
Platform 仓负责客户、商品、订单、AI 会话、后台配置与第三方集成等业务真相。
Yunxi 仅是首个落地实例名，不作为产品总名使用。
```

### 2. 新增边界说明文档摘录（历史）

目标：

- 把“哪些事情归 MiniApp，哪些事情归 Platform”写成仓内共识。

建议新增文档：

- `docs/architecture/project-boundaries.md`
  或
- `docs/project-boundaries.md`

建议至少包含以下内容：

- 当前仓定位：`Storefront MiniApp`
- Platform 仓定位：业务真相源
- 当前仓职责：
  - 页面
  - 组件
  - 前台交互
  - 微信能力
  - API 调用封装
  - 本地缓存
- 不属于当前仓的职责：
  - 客户主档
  - 商品主档与商品规则
  - 订单规则与履约规则
  - CRM
  - AI 会话主逻辑
  - 店铺配置真相
  - 第三方集成真相
- 当前过渡态说明：
  - 后台配置仍嵌在 `YunxiBakeBot` 管理页中。
  - 这是过渡方案，不是长期目标架构。

### 3. API client 口径整理摘录（历史）

目标：

- 明确前台只消费平台能力，不在前台重新发明业务规则。

建议动作：

1. 找到现有 API 请求目录，例如：
   - `api/`
   - `services/`
   - `utils/request`
   - `network/`
2. 在目录说明或 README 中明确：
   - 本目录只负责接口调用封装、请求参数组织、响应数据适配。
   - 不负责沉淀客户/商品/订单业务规则真相。
3. 如果已有混杂逻辑，先不急着重写，但至少打标签：
   - 哪些属于前台适配逻辑。
   - 哪些其实是平台规则，后续应迁回 `Platform`。

建议加一条简单原则：

- 能在 `Platform` 统一的规则，不要在 `MiniApp` 再实现一份。

### 4. 禁区清单摘录（历史）

目标：

- 避免后续新需求又顺手长回前台仓。

建议把以下内容明确列为禁区：

- 禁止在 `MiniApp` 新增客户主档逻辑。
- 禁止在 `MiniApp` 新增商品规则真相。
- 禁止在 `MiniApp` 新增订单规则真相。
- 禁止在 `MiniApp` 新增 CRM 逻辑。
- 禁止在 `MiniApp` 直接承接第三方平台同步真相。
- 禁止把后台配置系统继续长在前台仓。

推荐团队判断句：

- 如果一个能力会影响多个前台渠道，默认先判断是不是该落 `Platform`。

### 5. 历史命名处理摘录（历史）

目标：

- 先统一口径，再处理仓库 slug。

本阶段建议：

- 可以保留仓库名 `YunxiBakeMiniApp` 不变。
- 文档标题、说明文案、架构描述先改成通用口径。
- `Yunxi` 只保留在：
  - 实例配置
  - 环境命名
  - 历史迁移说明
  - 样板客户说明

本阶段不建议：

- 立刻改 Git 仓库名。
- 立刻改部署路径。
- 立刻改所有历史目录名。

## 推荐文件落点摘录（历史）

如果希望用最小改动完成第一阶段，建议只改这些文件：

1. `README.md`
2. `docs/architecture/project-boundaries.md` 或同等边界文档
3. API client 所在目录的说明文档
4. 如果仓内已有开发规范文档，则补一条“职责禁区”

## 验收清单摘录（历史）

执行完成后，用下面清单验收：

- 打开 README，是否能一眼看出这是 `Storefront MiniApp` 渠道仓。
- 打开边界文档，是否能清楚区分 `Platform` 和 `MiniApp` 职责。
- 打开 API client 说明，是否明确“这里只消费平台能力”。
- 团队是否已经接受 `Yunxi` 是实例名，不是产品总名。
- 新需求评审时，是否能先判断归属 `Platform` 还是 `MiniApp`。

## 第二阶段前的前置条件摘录（历史）

在进入真正的双仓联动治理前，建议先满足以下条件：

1. `Platform` 已完成一轮 `customer / order / catalog` 真实收口。
2. `MiniApp` 已完成这份清单中的第一阶段最小改造。
3. 双仓准备开始整理 API 契约表和命名映射表。

满足以上条件后，再进入接口统一、仓库改名评估和部署链路调整，会更稳。
