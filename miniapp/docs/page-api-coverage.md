# Storefront MiniApp 页面 API 覆盖合约

> updated_at: 2026-08-29
> as_of_commit: `77f9346`
> version: `0.133.0-p2trial.3`
> status: current local mirror / project status source remains `PROJECT-STATE.md`

trace_id: `20260707-miniapp-page-api-coverage-local-contract`

本合约是同一 Monorepo 根目录 `docs/architecture/miniapp-page-api-coverage-contract.md` 的 MiniApp 本地镜像。`backend/` 提供 Platform 业务 API，`miniapp/` 只负责前台页面、微信能力和 API client；目标是固定页面、前端服务、后端 API 与目录边界，避免把会员、营销、商品、订单或支付的业务真相误写进小程序。

## 覆盖范围

| 页面 | 主要后端能力 | 本仓职责 |
|---|---|---|
| `pages/home/index` | `GET /api/v1/miniapp/pages/home`、`GET /api/v1/miniapp/shop-settings`、`GET /api/v1/miniapp/products`、`GET /api/v1/miniapp/product-categories` | 展示首页装修、公告、分类和货架入口 |
| `pages/products/index` | `GET /api/v1/miniapp/pages/products`、`GET /api/v1/miniapp/products`、`GET /api/v1/miniapp/product-categories` | 展示商品列表和分类筛选 |
| `pages/product-detail/index` | `GET /api/v1/miniapp/products/{productId}` | 展示商品详情、加入购物车、立即购买入口 |
| `pages/cart/index` | `GET /api/v1/miniapp/products/{productId}` | 展示本地购物车，并在结算前重新校验商品有效性 |
| `pages/checkout/index` | `POST /api/v1/miniapp/orders`、`POST /api/v1/miniapp/orders/{orderId}/apply-coupon`、`POST /api/v1/miniapp/orders/{orderId}/apply-points`、`POST /api/v1/miniapp/orders/{orderId}/pay-with-balance`、`POST /api/v1/miniapp/orders/{orderId}/prepare-combined-payment`、`GET /api/v1/miniapp/products/{productId}`、`GET /api/v1/miniapp/addresses`、`GET /api/v1/miniapp/shop-settings` | 组织下单参数、协议确认、收货信息；结算扩展（券/积分/余额/组合支付）为 Phase 2 契约 |
| `pages/policy/index` | `GET /api/v1/miniapp/shop-settings` | 展示隐私政策、用户协议和售后说明 |
| `pages/address/index` | `GET /api/v1/miniapp/addresses`、`POST /api/v1/miniapp/addresses`、`POST /api/v1/miniapp/addresses/{addressId}/default`、`DELETE /api/v1/miniapp/addresses/{addressId}` | 管理当前用户收货地址 UI |
| `pages/orders/index` | `GET /api/v1/miniapp/orders` | 展示当前用户订单列表 |
| `pages/order-detail/index` | `GET /api/v1/miniapp/orders/{orderId}`、`POST /api/v1/miniapp/orders/{orderId}/cancel`、`POST /api/v1/miniapp/orders/{orderId}/prepare-payment`、`POST /api/v1/miniapp/orders/{orderId}/mock-pay` | 展示订单详情、取消和支付入口 |
| `pages/group-registration/index` | `POST /api/v1/miniapp/group-registrations`、`GET /api/v1/miniapp/group-registrations/me` | 承接客户群结构化登记，不解析企业微信群身份 |
| `pages/chat/index` | `GET /api/v1/miniapp/chat/messages`、`POST /api/v1/miniapp/chat/messages`、`POST /api/v1/miniapp/chat/transfer` | 展示客服气泡消息、发送消息、临时输入态和请求转人工；真实会话未就绪时只展示登录引导 |
| `pages/profile/index` | `GET /api/v1/miniapp/pages/profile`、`GET /api/v1/miniapp/balance`、`GET /api/v1/miniapp/points`、`GET /api/v1/miniapp/coupons`、`GET /api/v1/miniapp/shop-settings`、`POST /api/v1/miniapp/auth/login` | 展示会员中心装修、会员资产（余额/积分/可用券）、订单入口、店铺服务配置和登录刷新入口 |
| `pages/points/index` | 积分余额与明细 | `GET /api/v1/miniapp/points` | 已有 API 契约 |
| `pages/coupons/index` | 我的优惠券（tab 分组） | `GET /api/v1/miniapp/coupons` | 已有 API 契约 |
| `pages/recharge/index` | 充值（档位/自定义/mock 确认/记录） | `POST /api/v1/miniapp/recharges`、`POST /api/v1/miniapp/recharges/{recharge_id}/mock-pay`、`GET /api/v1/miniapp/recharges` | 已有 API 契约；入口受 `RECHARGE_READY` 控制 |

## 当前必须存在的 Platform API

- `GET /api/v1/miniapp/pages/{pageId}`
- `GET /api/v1/miniapp/pages/home`
- `GET /api/v1/miniapp/pages/products`
- `GET /api/v1/miniapp/pages/profile`
- `GET /api/v1/miniapp/products`
- `GET /api/v1/miniapp/products/{productId}`
- `GET /api/v1/miniapp/product-categories`
- `GET /api/v1/miniapp/addresses`
- `POST /api/v1/miniapp/addresses`
- `POST /api/v1/miniapp/addresses/{addressId}/default`
- `DELETE /api/v1/miniapp/addresses/{addressId}`
- `POST /api/v1/miniapp/orders`
- `GET /api/v1/miniapp/orders`
- `GET /api/v1/miniapp/orders/{orderId}`
- `POST /api/v1/miniapp/orders/{orderId}/cancel`
- `POST /api/v1/miniapp/orders/{orderId}/prepare-payment`
- `POST /api/v1/miniapp/orders/{orderId}/mock-pay`
- `GET /api/v1/miniapp/chat/messages`
- `POST /api/v1/miniapp/chat/messages`
- `POST /api/v1/miniapp/chat/transfer`
- `POST /api/v1/miniapp/group-registrations`
- `GET /api/v1/miniapp/group-registrations/me`
- `GET /api/v1/miniapp/shop-settings`
- `POST /api/v1/miniapp/auth/login`

## 待补能力边界

以下能力可以在页面上展示入口或后端返回值，但不能在本仓本地实现业务真相：

- 会员权益：不在本仓实现会员权益计算。
- 积分、储值余额、优惠券：不在本仓实现积分、储值余额或优惠券账本。
- 配送费、满减、活动价：不在本仓实现配送费、满减或活动价规则。
- 商品价格、库存、分类：不在本仓实现商品价格、库存或分类真相。
- 订单状态：不在本仓实现订单状态机。
- 支付闭环：不把 mock-pay 当作正式微信支付闭环。
- 客户群归因：不在本仓解析企业微信群身份或生成活动归因真相。

如果页面需要新增上述能力，先回 `backend/`（Platform）定义 API 契约、数据来源和验证方式，再更新 `miniapp/` 服务调用和展示逻辑。接口缺口先回 Platform 定义 API 契约。

## 静态门禁

运行：

```powershell
npm run check:page-api-coverage
```

该检查会验证：

- `miniprogram/app.json` 的 15 个页面均在本合约中出现。
- 本合约包含当前页面依赖的关键 API。
- `docs/api-contract.md` 仍覆盖当前小程序服务调用的核心 API。
- 本合约明确保留会员、营销、商品、订单、支付和客户群归因边界。
