# MiniApp 页面 API 覆盖合约

> trace_id: `20260707-miniapp-page-api-coverage-contract`
> 状态：治理设计冻结；首版只补页面到 Platform API 的覆盖清单和静态验收，不改 MiniApp 运行时代码
> 日期：2026-07-07
> 适用范围：`Storefront MiniApp` 页面、Platform `/api/v1/miniapp/*` 公开接口、双仓协作边界
> 关联文档：
> - [GitHub 参考项目借鉴与可实施计划](./github-reference-benchmark-and-implementation-plan.md)
> - [Platform / Storefront MiniApp API Contract v1](./platform-miniapp-api-contract-v1.md)

______________________________________________________________________

## 一、设计结论

MiniApp 阶段 5 的第一步不是继续新增页面，而是把“页面依赖哪些 Platform API、哪些业务规则不得留在前端”冻结下来。

当前 `YunxiBakeMiniApp` 已有以下前台页面：

```text
pages/home/index
pages/products/index
pages/product-detail/index
pages/cart/index
pages/checkout/index
pages/policy/index
pages/address/index
pages/orders/index
pages/order-detail/index
pages/group-registration/index
pages/chat/index
pages/profile/index
```

这些页面已经覆盖首页、分类 / 商品列表、商品详情、购物车、结算、协议政策、地址、订单、客户群登记、客服入口和会员中心的基础用户路径。下一步要补的是契约化验收和真实体验验证，而不是让前端仓自行扩展业务真相。

______________________________________________________________________

## 二、页面覆盖清单

| 页面 | 用户路径 | 依赖 Platform API | 当前结论 |
|---|---|---|---|
| `pages/home/index` | 首页、装修、主推商品 | `GET /api/v1/miniapp/pages/home`、`GET /api/v1/miniapp/products?featured=true`、`GET /api/v1/miniapp/shop-settings` | 已有 API 契约 |
| `pages/products/index` | 分类 / 商品列表 | `GET /api/v1/miniapp/products`、`GET /api/v1/miniapp/product-categories` | 已有 API 契约 |
| `pages/product-detail/index` | 商品详情、规格选择、立即购买 | `GET /api/v1/miniapp/products/{product_id}`、`GET /api/v1/miniapp/products/{product_id}/image` | 已有 API 契约；规格和库存规则仍以 Platform 商品真相为准 |
| `pages/cart/index` | 购物车查看、数量调整、进入结算 | `GET /api/v1/miniapp/products?ids=...` | 购物车本地状态只保存用户临时选择，不保存价格、库存或商品真相 |
| `pages/checkout/index` | 收货信息、配送方式、下单、支付准备 | `GET /api/v1/miniapp/addresses`、`POST /api/v1/miniapp/orders`、`POST /api/v1/miniapp/orders/{order_id}/prepare-payment`、`GET /api/v1/miniapp/shop-settings` | 已有 API 契约 |
| `pages/policy/index` | 隐私、用户协议、售后政策 | `GET /api/v1/miniapp/shop-settings` | 已有 API 契约 |
| `pages/address/index` | 地址列表、新增、默认、删除 | `GET /api/v1/miniapp/addresses`、`POST /api/v1/miniapp/addresses`、`POST /api/v1/miniapp/addresses/{address_id}/default`、`DELETE /api/v1/miniapp/addresses/{address_id}` | 已有 API 契约 |
| `pages/orders/index` | 用户订单列表 | `GET /api/v1/miniapp/orders` | 已有 API 契约 |
| `pages/order-detail/index` | 订单详情、时间线、取消、支付 | `GET /api/v1/miniapp/orders/{order_id}`、`POST /api/v1/miniapp/orders/{order_id}/cancel`、`POST /api/v1/miniapp/orders/{order_id}/prepare-payment`、`POST /api/v1/miniapp/orders/{order_id}/mock-pay` | 已有 API 契约；`mock-pay` 仅保留开发和无微信支付配置场景 |
| `pages/group-registration/index` | 客户群团购 / 预订登记 | `POST /api/v1/miniapp/group-registrations`、`GET /api/v1/miniapp/group-registrations/me` | 已有 API 契约 |
| `pages/chat/index` | 客服消息、转人工 | `GET /api/v1/miniapp/chat/messages`、`POST /api/v1/miniapp/chat/messages`、`POST /api/v1/miniapp/chat/transfer` | 已有 API 契约 |
| `pages/profile/index` | 会员中心、订单入口、客服入口、登记记录入口 | `GET /api/v1/miniapp/shop-settings`、`GET /api/v1/miniapp/orders`、`GET /api/v1/miniapp/group-registrations/me` | 基础入口已有 API；会员权益、积分、储值、优惠券属于待补 Platform API |

______________________________________________________________________

## 三、明确待补 Platform API

当前阶段不在 MiniApp 仓直接实现以下业务真相；如要上线相关能力，先回 Platform 定义 API 契约：

| 待补能力 | Platform API 状态 | MiniApp 当前允许行为 |
|---|---|---|
| 会员权益 | 需由 Platform 补 `GET /api/v1/miniapp/member/benefits` 契约 | 只展示入口或静态说明，不计算权益 |
| 积分 | 需由 Platform 补 `GET /api/v1/miniapp/member/points` 契约 | 不在前端累加或扣减积分 |
| 储值余额 | 需由 Platform 补 `GET /api/v1/miniapp/member/balance` 契约 | 不在前端保存余额 |
| 优惠券 | 需由 Platform 补 `GET /api/v1/miniapp/coupons` 契约 | 不在前端生成或核销券 |
| 配送费 / 满减 / 活动价 | 需由 Platform 补订单预览或营销 API 契约 | 不在前端推导最终价格 |

这些能力可以先作为页面入口存在，但本地示例数据不能呈现为真实权益。

______________________________________________________________________

## 四、双仓边界

Platform 继续负责：

- 客户主档、地址、身份、会员权益。
- 商品、分类、价格、库存、上下架、图片安全代理。
- 订单创建、订单状态、支付状态、取消规则、履约时间线。
- 客服会话、转人工、AI 主链路。
- 店铺运营配置、协议政策、售后政策。

Storefront MiniApp 继续负责：

- 页面结构、组件交互、微信能力、API client。
- 登录态保存、请求头注入、本地购物车临时状态。
- 展示 Platform 返回的字段和错误提示。
- 真机验收、页面跳转、按钮可用性和支付唤起体验。

______________________________________________________________________

## 五、禁止规则

- MiniApp 不得新增客户主档模型。
- MiniApp 不得新增商品定价、库存、分类真相。
- MiniApp 不得实现订单状态流转规则。
- MiniApp 不得本地计算会员权益、积分、储值、优惠券、配送费、满减或活动价。
- MiniApp 不得把 `mock-pay` 当成正式支付能力。
- MiniApp 不得把本地 mock 数据覆盖真实 API 响应。
- 缺 API 时先回 Platform 定义契约，前端只保留入口、展示和错误提示。

______________________________________________________________________

## 六、发布与验证入口

Platform 侧：

- `python scripts/check_miniapp_page_api_contract.py --summary`
- `python scripts/check_project.py --skip-tests`
- `python scripts/preflight_production.py --json`
- `python scripts/check_preflight_business_contracts.py "<preflight-report.json>" --summary`

MiniApp 侧：

- `npm run check:miniapp`
- `npm run typecheck`
- `npm run release:readiness`
- 真机验收清单覆盖商品、购物车、结算、支付、客服入口。

双仓联动功能必须使用同一个 `trace_id`，分别记录 Platform API 验证和 MiniApp 真机验证证据。

______________________________________________________________________

## 七、静态验收

本计划由 `scripts/check_miniapp_page_api_contract.py` 验收，并接入 `scripts/check_project.py --skip-tests` 的业务合约检查。

静态验收必须覆盖：

- `pages/home/index`、`pages/products/index`、`pages/product-detail/index`、`pages/cart/index`、`pages/checkout/index`、`pages/policy/index`、`pages/address/index`、`pages/orders/index`、`pages/order-detail/index`、`pages/group-registration/index`、`pages/chat/index`、`pages/profile/index`。
- `/api/v1/miniapp/products`、`/api/v1/miniapp/product-categories`、`/api/v1/miniapp/orders`、`/api/v1/miniapp/chat/messages`、`/api/v1/miniapp/group-registrations`、`/api/v1/miniapp/shop-settings`。
- 会员权益、积分、储值余额、优惠券、配送费 / 满减 / 活动价必须标记为待补 Platform API。
- MiniApp 不得新增客户主档模型、商品定价、库存、分类真相、订单状态流转规则或本地会员营销规则。

______________________________________________________________________

## 八、当前结论

阶段 5 可以先在 Platform 仓建立页面/API 覆盖合约，作为 MiniApp 仓后续补 roadmap、真机验收和 miniprogram-ci 的输入。当前切片只补契约和静态验收，不改小程序页面、不改 Platform API 行为、不引入新的业务规则。
