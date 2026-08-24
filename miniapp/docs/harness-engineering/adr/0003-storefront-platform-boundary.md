# ADR-0003 将 YunxiBakeMiniApp 定位为 Storefront MiniApp 渠道仓

- status: accepted
- date: 2026-06-19
- decision_owner: YunxiBakeMiniApp
- trace_id: 20260619-storefront-boundary-alignment
- related_docs:
  - README.md
  - AGENTS.md
  - docs/project-management.md
  - docs/architecture/project-boundaries.md
  - docs/api-contract.md
  - docs/roadmap.md
  - miniprogram/services/README.md
- review_trigger: 出现后台配置迁入本仓、Platform 业务真相下沉、小程序客户群运营边界变化或双仓发布策略变化时回看

## 背景

`Bakery Commerce Platform` 是总体产品逻辑名。`YunxiBakeBot` 是 `Platform` 主仓，负责客户、商品、订单、AI 会话、后台配置和第三方集成等业务真相。`YunxiBakeMiniApp` 是面向消费者的微信小程序前台渠道仓。

历史推进中，本仓的 README、契约和服务层曾被写成“用户端 + 部分平台能力入口”的混合口径，容易让后续开发把后台配置、业务规则真相和前台体验代码混在一起。

本次需要把仓位和边界钉死在 `Storefront MiniApp`，同时保留当前过渡期的实际依赖关系。

## 决策

确认 `YunxiBakeMiniApp` 的长期定位为 `Storefront MiniApp` 渠道仓：

- 本仓只负责页面、组件、交互、微信能力、API client、登录态和本地缓存。
- 本仓通过 `miniprogram/services/` 消费 `YunxiBakeBot` 暴露的 `Platform` API。
- 本仓不承载客户主档、商品规则真相、订单规则真相、CRM、AI 会话主逻辑、店铺配置真相或第三方同步真相。
- `Yunxi` 仅作为首个实例 / 租户名，不作为产品总名。
- 当前后台配置嵌在 `YunxiBakeBot` 管理页中，属于过渡态，不代表长期架构。

## 后果

正面影响：

- 后续页面和 service 代码更容易判断责任边界。
- API 契约、服务适配和页面展示分层会更清晰。
- 当 `Platform` 主仓演进业务真相时，本仓只需跟随契约和展示适配，不需要复制一套规则中心。

代价：

- 需要持续维护边界文档和契约口径，避免历史混用再次回潮。
- 过渡期内仍要接受少量兜底和 mock，但它们必须被标记为体验兜底，不得升级为业务真相。

## 替代方案

1. 保持“用户端 + 平台部分能力混合仓”口径。短期省事，但会继续混淆职责，和当前目标冲突。
2. 把后台配置也迁到本仓。会破坏前台渠道仓定位，也会制造重复的配置真相。
3. 只做文档命名不做决策记录。短期可读性提升，但缺少长期可追溯的边界结论。

## 验证与回看

- README 已改为 `Bakery Storefront MiniApp` 并明确 `Platform` / `Storefront MiniApp` 关系。
- `docs/architecture/project-boundaries.md` 已写入职责边界、依赖关系、过渡态说明和禁区规则。
- `miniprogram/services/README.md` 已写明 service 层仅做请求封装、参数组织、响应适配和兜底。
- `npm run check:miniapp` 通过。
- `npm run typecheck` 通过。

后续若再出现把后台配置、商品规则真相或订单规则真相写入本仓的提议，应优先回看本 ADR。
