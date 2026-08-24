# Bakery Storefront MiniApp

本仓是 `Bakery Commerce Platform` 的消费者前台渠道仓，定位为 `Storefront MiniApp`。

`Platform` 主仓由 `YunxiBakeBot` 承担，负责客户、商品、订单、AI 会话、后台配置、第三方集成等业务真相。本仓只消费这些能力并呈现微信小程序用户体验。

`Yunxi` 是首个落地实例 / 租户名，不是产品总名。当前仓库 slug、部署路径、线上 API 契约和页面业务行为在本阶段保持不变。

## 职责边界

本仓负责：

- 微信小程序页面、组件、交互和本地 UI 状态。
- 微信能力接入，例如登录、支付唤起、路由、缓存和本地会话。
- `miniprogram/services/` 中的 API client、参数组织、响应适配和错误呈现。
- 购物车、地址选择、页面兜底配置等仅用于前台体验的本地缓存。

本仓不负责：

- 客户主档、商品规则真相、订单规则真相、CRM 逻辑。
- AI 会话主逻辑、客服编排、知识库和人工客服后台。
- 店铺配置真相、后台配置系统、第三方同步真相。
- 后端持久化、支付回调、库存扣减、商品同步和数据迁移。

更完整的边界说明见 [docs/architecture/project-boundaries.md](docs/architecture/project-boundaries.md)。

## 依赖关系

本仓通过 HTTP API 消费 `Platform` 能力，当前接口契约记录在 [docs/api-contract.md](docs/api-contract.md)。API 提供方是 `YunxiBakeBot`，本仓不得通过前端逻辑沉淀客户、商品、订单或配置的业务真相。

当前后台配置仍嵌在 `YunxiBakeBot` 管理页中，这是过渡态，不代表长期架构。本仓只读取已发布给小程序的公开配置。

## 技术栈

- 微信原生小程序
- TypeScript
- MVP 阶段采用默认 WebView 渲染，Skyline / glass-easel 预留为后续性能专项
- 无第三方 UI 依赖起步

## 当前前台体验口径

- 客服页采用微信风格气泡会话：用户消息右侧、客服消息左侧，发送中使用临时“正在输入”状态，真实回复落地后移除该状态。
- 个人中心采用会员中心样式：头像、会员资产、会员卡、订单入口和服务列表都从本地会话、页面装修和店铺公开配置组合展示。
- 订单、客服、结算、地址、客户群登记等用户归属路径必须先通过真实会话门槛；demo 或未就绪会话不得伪装为已登录。
- 小程序 WXML 中自定义组件使用显式双标签，例如 `<session-notice></session-notice>`；真机预览编译路径不把自闭合组件标签视为安全写法。

## 目录

```text
miniprogram/
  pages/        页面
  components/   业务组件
  services/     Platform API client
  utils/        通用工具
docs/
  architecture/project-boundaries.md
  api-contract.md
  observability-contract.md
  page-api-coverage.md
  harness-engineering/README.md
  release/miniprogram-ci-readiness.md
  release/manual-acceptance-checklist.md
  roadmap.md
```

## 项目管理体系

本仓使用轻量 Harness Engineering 管理需求、变更、验证、证据和交接。入口见 [docs/harness-engineering/README.md](docs/harness-engineering/README.md)。

常用文档：

- [AGENTS.md](AGENTS.md)：Agent 启动规范、项目边界、文件操作红线。
- [LOGBOOK.md](LOGBOOK.md)：按时间倒序记录关键推进、验证和残余风险。
- [docs/project-management.md](docs/project-management.md)：项目管理体系总览。
- [docs/roadmap.md](docs/roadmap.md)：MVP 与客户群运营闭环路线图。
- [docs/api-contract.md](docs/api-contract.md)：小程序消费 Platform API 的权威契约。
- [docs/observability-contract.md](docs/observability-contract.md)：页面、商品、购物车、支付、客服和会话门槛的可观测指标契约。
- [docs/page-api-coverage.md](docs/page-api-coverage.md)：页面、服务、Platform API 和业务边界覆盖合约。
- [docs/architecture/project-boundaries.md](docs/architecture/project-boundaries.md)：Storefront MiniApp / Platform 职责边界。
- [docs/release/miniprogram-ci-readiness.md](docs/release/miniprogram-ci-readiness.md)：小程序 CI 上传前的密钥、依赖和环境变量准备合约。
- [docs/release/manual-acceptance-checklist.md](docs/release/manual-acceptance-checklist.md)：自动化检查之后的微信平台、真机、支付和审核手工验收清单。

管理闭环：

```text
需求或故障
-> 分配 trace_id
-> 更新契约、设计、ADR 或路线图
-> 实施变更
-> 运行验证矩阵
-> 登记证据
-> 更新 LOGBOOK
-> 必要时写交接或防重犯记录
```

## 本地打开

1. 使用微信开发者工具打开本目录。
2. 将 `project.config.json` 中的 `appid` 替换为正式小程序 AppID。
3. 在开发者工具中开启 TypeScript 编译。
4. 后端接口由 `miniprogram/services/config.ts` 决定，默认消费 `YunxiBakeBot` 提供的 Platform API。

## 本地真实商品联调

1. 在 `D:\Project\YunxiBakeBot` 准备脱敏商品库 `data/prod_snapshot/eval.db`。
2. 启动本地后端：

```powershell
$env:DB_PATH="data/prod_snapshot/eval.db"
python -m uvicorn app.main:app --host 127.0.0.1 --port 7001
```

3. 在本仓库验证本地商品 API：

```powershell
npm run check:local-miniapp-products
```

4. 如需本地后端联调，按 `miniprogram/services/config.ts` 当前规则切换到本地 API；体验版和正式版仍请求线上域名。

## 第一阶段目标

- 商品浏览
- 商品详情
- 购物车
- 结算信息收集
- 订单列表
- AI 客服入口
- 我的页面

更多阶段目标见 [docs/roadmap.md](docs/roadmap.md)。
