# Storefront MiniApp API 契约

提供方：`YunxiBakeBot`，即 `Bakery Commerce Platform` 的 `Platform` 主仓。

消费方：`YunxiBakeMiniApp`，即 `Storefront MiniApp` 前台渠道仓。

默认域名：`https://yunxifood.cn`

本文件记录 `Storefront MiniApp` 通过 HTTP API 消费 `Platform` 能力时需要遵守的契约。客户、商品、订单、AI 会话、店铺配置和第三方集成的业务真相均属于 `Platform` 主仓；本仓只负责请求封装、参数组织、响应适配和前台展示。

历史上本文件同时收录了部分 admin API，用于说明后台发布配置后小程序如何读取同一份公开结果。admin API 的实现、权限、审计和业务规则真相仍归属 `Platform` 主仓，不代表本仓承担后台配置系统。

除特别说明外，后端响应统一使用：

```json
{
  "code": 0,
  "data": {}
}
```

## 页面装修

### GET `/api/v1/miniapp/pages/{pageId}`

返回已发布的小程序页面装修配置。MVP 首批 `pageId`：

- `home`
- `products`
- `profile`

```json
{
  "code": 0,
  "data": {
    "pageId": "home",
    "version": 1,
    "status": "published",
    "updatedAt": "2026-06-16T00:00:00+08:00",
    "theme": {
      "primaryColor": "#e94b4b",
      "accentColor": "#9bb879",
      "backgroundColor": "#f7f7f7"
    },
    "blocks": [
      {
        "id": "notice-1",
        "type": "noticeBar",
        "enabled": true,
        "props": {
          "text": "定制蛋糕 + 客服微信：13240240418"
        }
      },
      {
        "id": "shelf-1",
        "type": "productShelf",
        "enabled": true,
        "props": {
          "title": "12年招牌必吃榜",
          "source": "manual",
          "productIds": ["p_001", "p_002"]
        }
      }
    ]
  }
}
```

MVP block 类型：

| type | 用途 |
|---|---|
| `searchBar` | 搜索入口 |
| `heroCarousel` | 多图轮播主推位 |
| `noticeBar` | 公告条 |
| `categoryGrid` | 分类入口 |
| `quickLinks` | 快捷入口 |
| `membershipBanner` | 会员横幅 |
| `noticeList` | 订购须知列表 |
| `productShelf` | 商品货架 |
| `memberSummary` | 会员摘要 |
| `serviceGrid` | 服务入口宫格 |
| `richText` | 长说明内容 |

`memberSummary.props` 字段：

```json
{
  "greeting": "HI",
  "name": "微信用户",
  "levelText": "注册会员",
  "cardSubtitle": "单笔充值 1000 元升级",
  "cardValidity": "永久有效",
  "points": 160,
  "coupons": 0,
  "balanceFen": 0,
  "benefitCardCount": 0
}
```

### 会员资产（M5 修订）

- 我的页资产数字（余额/积分/可用券数）必须来自真实 API，不得从 `memberSummary` 装修配置读取：
  - 余额：`GET /api/v1/miniapp/balance` → `balanceFen`
  - 积分：`GET /api/v1/miniapp/points` → `pointsBalance`（含 `ledger` 明细，上限 50 条倒序）
  - 可用券数：`GET /api/v1/miniapp/coupons` → `coupons`，按 `status=TAKE` 且 `validFrom <= today <= validUntil` 计数
- `memberSummary` 装修配置只负责等级文案、会员卡副标题、有效期文案等展示字段；权益卡数量无数据源，不展示。
- 券中心：`GET /api/v1/miniapp/coupons`，tab 可用/已用/已退回/已过期由前端按 `status` + 有效期派生。
- 充值：`POST /api/v1/miniapp/recharges`（amountFen，100~50000）、`POST /api/v1/miniapp/recharges/{recharge_id}/mock-pay`、`POST /api/v1/miniapp/recharges/{recharge_id}/cancel`、`GET /api/v1/miniapp/recharges`。
- 结算扩展：`POST /api/v1/miniapp/orders/{order_id}/coupon-preview`、`POST /api/v1/miniapp/orders/{order_id}/apply-coupon`、`POST /api/v1/miniapp/orders/{order_id}/points-preview`、`POST /api/v1/miniapp/orders/{order_id}/apply-points`、`POST /api/v1/miniapp/orders/{order_id}/pay-with-balance`、`POST /api/v1/miniapp/orders/{order_id}/prepare-combined-payment`、`POST /api/v1/miniapp/orders/{order_id}/prepare-payment`、`POST /api/v1/miniapp/orders/{order_id}/mock-pay`。
- 支付能力边界：在线支付（mock/微信）仅本地后端可用（`IS_USING_LOCAL_API`）；生产 release 仅余额支付可用。

`searchBar.props` 字段：

```json
{
  "placeholder": "搜索商品"
}
```

小程序首页将 `searchBar` 作为轻量搜索入口展示，点击后进入商品页浏览/搜索；字段缺失时客户端可使用“搜索商品”兜底。

`heroCarousel.props` 字段：

```json
{
  "autoplay": true,
  "intervalMs": 3500,
  "items": [
    {
      "id": "hero_1",
      "imageUrl": "/api/v1/admin/assets/hero-1.jpg",
      "title": "匠心与艺术的结晶",
      "subtitle": "每日现制 / 手作奶油 / 礼赠场景",
      "eyebrow": "YUNXI BAKE",
      "badges": ["当日现做", "精选奶油", "生日礼赠"],
      "linkType": "product",
      "linkTarget": "p_001"
    }
  ]
}
```

`heroCarousel.props.items` 支持多张图片，后台装修需提供上传后的 `imageUrl`。小程序端只负责按顺序轮播展示，并在图片缺失时回退到本地烘焙插画兜底；`badges` 为可选卖点标签，建议最多 3 个，用于“当日现做、精选奶油、生日礼赠”等品牌信任表达；`linkType`、`linkTarget` 沿用通用跳转规则，可用于主推商品、活动页或无跳转宣传图。

`serviceGrid.props.items` 支持 `linkType=page` 与 `linkTarget=address`，小程序“我的”页点击后进入本地收货地址管理页。MVP 阶段地址簿为小程序本地存储能力，结账页从选中地址或默认地址回填联系人、手机号和配送地址；跨设备同步和后端地址持久化后续另行扩展 API。

### GET `/api/v1/miniapp/addresses`

返回当前微信用户的收货地址列表，按默认地址优先、更新时间倒序排序。

### POST `/api/v1/miniapp/addresses`

保存或更新收货地址。请求体：

```json
{
  "id": "addr_001",
  "receiverName": "大海",
  "receiverPhone": "18800000000",
  "address": "福建省厦门市湖里区",
  "isDefault": true
}
```

如果未传 `id`，后端创建新地址；如果是该用户首个地址，后端会自动设为默认地址。

### POST `/api/v1/miniapp/addresses/{addressId}/default`

将指定地址设为当前用户默认地址。

### DELETE `/api/v1/miniapp/addresses/{addressId}`

删除当前用户的指定地址。删除后如果用户还有剩余地址，后端会自动补一个默认地址。

## 后台顾客地址 API

后台项目：`YunxiBakeBot/web/admin`

### GET `/api/v1/admin/addresses`

查询小程序顾客地址列表。

Query：

- `page` 可选，页码。
- `keyword` 可选，搜索地址 ID、用户标识、联系人、手机号或地址。

```json
{
  "code": 0,
  "data": {
    "items": [
      {
        "id": "addr_001",
        "userId": "wx_openid",
        "receiverName": "大海",
        "receiverPhone": "18800000000",
        "address": "福建省厦门市湖里区",
        "isDefault": true,
        "createdAt": "2026-06-17T00:00:00+08:00",
        "updatedAt": "2026-06-17T00:00:00+08:00"
      }
    ],
    "total": 1,
    "page": 1,
    "pageSize": 30
  }
}
```

### GET `/api/v1/admin/addresses/{addressId}`

返回单个地址详情。

响应额外包含 `auditLogs`，最多返回最近 5 条后台操作记录：

```json
{
  "id": 1,
  "addressId": "addr_001",
  "userId": "wx_openid",
  "operator": "admin:abcdef12",
  "action": "update",
  "before": {},
  "after": {},
  "note": "后台编辑地址",
  "createdAt": "2026-06-17T00:00:00+08:00"
}
```

### POST `/api/v1/admin/addresses`

后台为指定小程序用户新增收货地址。请求体：

```json
{
  "userId": "wx_openid",
  "receiverName": "大海",
  "receiverPhone": "18800000000",
  "address": "福建省厦门市湖里区",
  "isDefault": true
}
```

如果是该用户首个地址，后端会自动设为默认地址；如果 `isDefault=true`，后端会清除该用户其他默认地址。

### PUT `/api/v1/admin/addresses/{addressId}`

后台编辑指定顾客地址。请求体字段同新增地址，`userId` 必填且不可跨用户更新地址。

### POST `/api/v1/admin/addresses/{addressId}/default`

后台把指定地址设为该顾客默认地址。

### DELETE `/api/v1/admin/addresses/{addressId}`

后台删除指定地址。删除默认地址后，如果该顾客还有其他地址，后端会自动补一个默认地址。

## 商品

### GET `/api/v1/miniapp/product-categories`

返回小程序商品页左侧分类列表。该接口由 `YunxiBakeBot` 从有赞商品同步落库字段生成，按后台排序返回。

分类来源优先级：

1. `youzan.item.base.search` 返回的 `classification_id` / `classification_ids`，落库为稳定分类字段，用于小程序主分类。
2. `youzan.item.classification.search` 返回的 `classification_id -> name` 映射，用于把稳定分类 ID 转成中文分类名。
3. 有赞商品 `tag_ids` 与 `youzan.itemcategories.tags.get` 分组名称，作为旧分组兼容。
4. 分类名暂未能从有赞名称接口解析时，后端使用“有赞分类 {id}”兜底；不得用商品名、规格、价格或推荐标签充当分类名。

```json
{
  "code": 0,
  "data": [
    {
      "id": "youzan-classification-40606522",
      "title": "生日蛋糕",
      "sort": 10,
      "productCount": 24
    }
  ]
}
```

`category.id` 使用稳定前缀，和商品响应中的 `categoryId` 保持一致：

- `youzan-classification-{classificationId}`：来自 ITEM_INFO 的 `classification_ids`，优先用于小程序分类。
- `youzan-tag-{tagId}`：来自旧有赞商品分组 `tag_ids`，仅用于兼容已有分组。

后端落库时应按商品 `item_id` / 商品编码关联 `youzan_products`，保存 `classification_ids_json`、`group_ids_json`、`second_group_ids_json`、`leaf_category_ids_json` 和 `tag_ids_json`；其中有赞实测 `ITEM_INFO` 会返回单数字段 `classification_id`、`leaf_category_id`，后端需统一标准化为数组 JSON。小程序接口只输出公开且有商品数量的分类。

### GET `/api/v1/miniapp/products`

返回商品列表，支持按分类、商品 ID 或推荐位过滤。

Query：

- `categoryId` 可选，分类 ID。
- `ids` 可选，逗号分隔商品 ID。
- `featured` 可选，是否只返回主推商品。
- `categoryId` 可传 `youzan-classification-{classificationId}`，后端按 `classification_ids_json` 精确过滤。
- `categoryId` 可传 `youzan-tag-{tagId}`，后端按有赞商品 `tag_ids_json` 精确过滤，用于旧分组兼容。
- 商品响应同时返回稳定 `categoryId` 与可展示的 `categoryName`；小程序左侧分类优先使用 `GET /product-categories` 驱动，分类接口不可用时才按商品字段兜底聚合。

```json
{
  "code": 0,
  "data": [
    {
      "id": "p_001",
      "title": "草莓奶油蛋糕",
      "subtitle": "适合生日和聚会",
      "imageUrl": "/api/v1/miniapp/products/p_001/image",
      "priceFen": 19800,
      "soldText": "近期热卖",
      "categoryId": "youzan-classification-40606522",
      "categoryName": "生日蛋糕",
      "stock": 20,
      "isActive": true,
      "tags": ["生日蛋糕"],
      "description": "适合生日与家庭聚会",
      "specs": ["6寸", "8寸"],
      "notices": ["需提前24小时预订"]
    }
  ]
}
```

`imageUrl` 有图时返回后端同域代理路径，缺图时返回空字符串。小程序客户端在商品 service 层将该路径补全为当前 `API_BASE_URL` 下的完整 URL，不在页面层拼接资源地址。小程序不直接依赖有赞或第三方图片域名，避免微信合法域名和热链策略影响页面渲染。

### GET `/api/v1/miniapp/products/{productId}`

返回商品详情。

```json
{
  "code": 0,
  "data": {
    "id": "p_001",
    "title": "草莓奶油蛋糕",
    "subtitle": "适合生日和聚会",
    "imageUrl": "/api/v1/miniapp/products/p_001/image",
    "priceFen": 19800,
    "soldText": "近期热卖",
    "categoryId": "birthday-cake",
    "categoryName": "生日蛋糕",
    "stock": 20,
    "isActive": true,
    "tags": ["生日蛋糕"],
    "description": "适合生日与家庭聚会",
    "specs": ["6寸", "8寸"],
    "notices": ["需提前24小时预订"]
  }
}
```

### GET `/api/v1/miniapp/products/{productId}/image`

返回商品图片二进制内容。后端按 `productId` 查询已上架商品，再代理抓取该商品在后台商品宽表中的图片 URL；不提供开放式 `url` 参数。

响应：

- `200`：图片内容，`Content-Type` 为原图图片类型。
- `404`：商品不存在、商品无图、图片地址协议不允许、原图抓取失败或原图不是图片。

## 订单

### POST `/api/v1/miniapp/orders`

创建订单草稿。支付能力接入后返回支付参数。

如果 `productId` 能匹配到后端商品宽表，后端必须以宽表中的实时价格、库存和上下架状态为准：

- 商品下架时拒绝创建订单。
- 商品库存为 0 时拒绝创建订单。
- 下单数量超过库存时拒绝创建订单。
- 前端传入价格只作为 Mock/未入库商品兜底；真实商品总价以后端商品宽表价格计算。
- 真实商品下单成功后立即预占库存；后台将订单取消回 `cancelled` 时释放已预占库存。
- Mock/未入库商品不参与库存预占与释放。
- `expectTime` 必填，格式固定为 `YYYY-MM-DD HH:mm`。
- 后端按店铺运营配置 `businessHours` 校验预约时间；MVP 阶段支持同日 `HH:mm-HH:mm`，预约时间必须落在营业时间内，非法配置回退默认营业时间。

请求：

```json
{
  "items": [
    {
      "productId": "p_001",
      "quantity": 1
    }
  ],
  "receiverName": "大海",
  "receiverPhone": "18800000000",
  "deliveryType": "pickup",
  "deliveryAddress": "",
  "expectTime": "2026-06-18 18:00",
  "remark": "少糖"
}
```

响应：

```json
{
  "code": 0,
  "data": {
    "orderId": "o_001",
    "status": "pending",
    "totalFen": 19800
  }
}
```

库存或商品状态不满足时返回 HTTP 400：

```json
{
  "detail": "商品库存不足: p_001"
}
```

预约时间不满足时同样返回 HTTP 400：

```json
{
  "detail": "预约时间不在营业时间内"
}
```

### GET `/api/v1/miniapp/orders`

返回当前微信用户的订单列表。

```json
{
  "code": 0,
  "data": [
    {
      "id": "o_001",
      "status": "pending",
      "paymentStatus": "unpaid",
      "paymentMethod": "",
      "paymentPaidAt": "",
      "paymentExpiredAt": "",
      "paymentExpiredReason": "",
      "totalFen": 19800,
      "createdAt": "2026-06-16T00:00:00+08:00",
      "updatedAt": "2026-06-16T00:00:00+08:00",
      "itemTitle": "草莓奶油蛋糕",
      "itemCount": 1,
      "receiverName": "大海",
      "receiverPhone": "18800000000",
      "deliveryType": "pickup",
      "deliveryAddress": "",
      "expectTime": "2026-06-18 18:00",
      "remark": "少糖"
    }
  ]
}
```

该接口要求携带服务端签发的 Bearer 会话：`Authorization: Bearer <accessToken>`。用户身份由 JWT `sub` 确定，不接受客户端提交的用户 ID 作为正式身份来源。

### GET `/api/v1/miniapp/orders/{orderId}`

返回当前微信用户的单个订单详情。后端必须校验订单属于当前用户；不存在或不属于当前用户时返回 404。

```json
{
  "code": 0,
  "data": {
    "id": "o_001",
    "status": "pending",
    "paymentStatus": "unpaid",
    "paymentMethod": "",
    "paymentPaidAt": "",
    "paymentExpiredAt": "",
    "paymentExpiredReason": "",
    "totalFen": 19800,
    "createdAt": "2026-06-16T00:00:00+08:00",
    "updatedAt": "2026-06-16T00:00:00+08:00",
    "itemTitle": "草莓奶油蛋糕",
    "itemCount": 1,
    "items": [
      {
        "product_id": "p_001",
        "title": "草莓奶油蛋糕",
        "price_fen": 19800,
        "quantity": 1
      }
    ],
    "receiverName": "大海",
    "receiverPhone": "18800000000",
    "deliveryType": "pickup",
    "deliveryAddress": "",
    "expectTime": "2026-06-18 18:00",
    "remark": "少糖",
    "timeline": [
      {
        "id": 1,
        "status": "pending",
        "operator": "miniapp:wx_openid",
        "note": "用户提交订单",
        "createdAt": "2026-06-16T00:00:00+08:00"
      }
    ]
  }
}
```

`timeline` 按状态事件时间顺序返回。小程序提交订单、后台确认订单、开始制作、配送/待取、完成或取消订单时都会追加事件。小程序订单详情页优先展示真实事件时间；历史订单没有事件记录时客户端可回退为状态推导时间线。

### POST `/api/v1/miniapp/orders/{orderId}/cancel`

当前微信用户取消自己的订单。MVP 阶段允许用户取消 `pending`、`confirmed` 状态订单；进入 `making`、`delivering`、`done` 后不允许用户自助取消，需要联系客服或后台处理。真实商品订单取消成功后，后端释放已预占库存；Mock/未入库商品不参与库存释放。

响应：

```json
{
  "code": 0,
  "data": {
    "id": "o_001",
    "status": "cancelled",
    "totalFen": 19800,
    "updatedAt": "2026-06-16T00:10:00+08:00"
  }
}
```

错误：

- `404`：订单不存在或不属于当前用户。
- `400`：当前订单状态不允许用户取消。

### POST `/api/v1/miniapp/orders/{orderId}/mock-pay`

MVP 预留的模拟支付确认接口。仅用于联调和开发阶段，真实微信支付接入后沿用同一支付状态字段。

响应字段与订单详情一致，至少会把 `paymentStatus` 更新为 `paid`，`paymentMethod` 置为 `mock`，并写入 `paymentPaidAt`。

### POST `/api/v1/miniapp/orders/{orderId}/prepare-payment`

为当前微信用户自己的订单准备支付会话。小程序点击“立即支付”时先调用该接口：

- `mode=wechat`：小程序使用 `paymentParams` 调用 `wx.requestPayment`。
- `mode=mock`：当前后端未启用或未配置完整微信支付商户参数，小程序调用 `/mock-pay` 作为开发兜底。

错误：

- `404`：订单不存在或不属于当前用户。
- `400`：订单已取消或支付已超时。

无微信商户配置时响应：

```json
{
  "code": 0,
  "data": {
    "mode": "mock",
    "orderId": "o_001",
    "paymentMethod": "mock",
    "paymentStatus": "unpaid",
    "paymentParams": {
      "action": "mock-pay",
      "message": "当前环境未启用微信支付，使用模拟支付兜底"
    }
  }
}
```

微信支付配置完整时响应字段形状：

```json
{
  "code": 0,
  "data": {
    "mode": "wechat",
    "orderId": "o_001",
    "paymentMethod": "wechat",
    "paymentStatus": "unpaid",
    "paymentParams": {
      "timeStamp": "1799999999",
      "nonceStr": "random-string",
      "package": "prepay_id=wx-prepay-id",
      "signType": "RSA",
      "paySign": "signed-pay-params"
    }
  }
}
```

当前 MVP 后端已预留微信支付 JSAPI 下单和 `wx.requestPayment` 参数签名骨架；真实上线前必须完成商户私钥/证书配置、支付通知验签、回调确认落库和沙箱或测试商户联调。

### POST `/api/v1/miniapp/payments/wechat/notify`

微信支付 JSAPI 支付结果通知回调。该接口由微信支付平台调用，不由小程序直接调用。

后端处理要求：

- 使用微信支付平台证书校验 `Wechatpay-*` 签名头。
- 使用 `WECHAT_PAY_API_V3_KEY` 按 API v3 通知规则解密 `resource`。
- 仅当解密后的 `trade_state=SUCCESS` 时，把对应 `out_trade_no` 小程序订单的 `paymentStatus` 置为 `paid`、`paymentMethod` 置为 `wechat`、写入 `paymentPaidAt` 和微信 `transactionId`。
- 重复通知必须幂等；已支付订单再次收到成功通知仍返回成功。
- 订单不存在、签名无效、解密失败、订单已取消或已超时均返回 HTTP 400。

成功响应：

```json
{
  "code": "SUCCESS",
  "message": "成功"
}
```

环境配置：

- `WECHAT_PAY_ENABLED=true`
- `WECHAT_MINIAPP_APP_ID`
- `WECHAT_PAY_MCH_ID`
- `WECHAT_PAY_NOTIFY_URL`
- `WECHAT_PAY_PRIVATE_KEY_PATH`
- `WECHAT_PAY_CERT_SERIAL_NO`
- `WECHAT_PAY_PLATFORM_CERT_PATH`
- `WECHAT_PAY_API_V3_KEY`

## 后台订单 API

后台项目：`YunxiBakeBot/web/admin`

### GET `/api/v1/admin/orders`

查询小程序订单列表。

Query：

- `page` 可选，页码。
- `keyword` 可选，搜索订单号、用户、商品、配送信息或备注。
- `status` 可选，订单状态。
- `boardFilter` 可选，后台订单经营看板筛选口径。取值：`all`、`unpaid`、`pending`、`fulfilling`、`done`、`closed`。`unpaid` 表示待支付且未取消，`fulfilling` 表示已确认/制作中/配送中，`closed` 表示已取消或支付超时。

```json
{
  "code": 0,
  "data": {
    "items": [
      {
        "id": "o_001",
        "status": "pending",
        "paymentStatus": "unpaid",
        "paymentMethod": "",
        "paymentPaidAt": "",
        "paymentExpiredAt": "",
        "paymentExpiredReason": "",
        "totalFen": 19800,
        "createdAt": "2026-06-16 12:00:00",
        "updatedAt": "2026-06-16 12:00:00",
        "itemTitle": "草莓奶油蛋糕",
        "itemCount": 1,
        "receiverName": "大海",
        "receiverPhone": "18800000000",
        "deliveryType": "pickup",
        "deliveryAddress": "",
        "expectTime": "2026-06-18 18:00",
        "remark": "少糖"
      }
    ],
    "total": 1,
    "page": 1,
    "pageSize": 30
  }
}
```

### GET `/api/v1/admin/orders/summary`

返回后台订单经营看板汇总。该接口按全量订单数据聚合，不受分页影响；可传 `keyword` 让看板与当前搜索词一致。

Query：

- `keyword` 可选，搜索订单号、用户、商品、配送信息或备注。

```json
{
  "code": 0,
  "data": {
    "cards": [
      {
        "key": "unpaid",
        "label": "待支付",
        "description": "需要跟进付款",
        "count": 2,
        "totalFen": 39600
      }
    ],
    "totalCount": 8,
    "totalFen": 158400,
    "keyword": ""
  }
}
```

### GET `/api/v1/admin/orders/{orderId}`

返回订单详情，字段与列表项一致，额外包含 `items` 明细和 `timeline` 状态事件。

### POST `/api/v1/admin/orders/{orderId}/status`

更新订单履约状态。

请求：

```json
{
  "status": "confirmed"
}
```

响应：

```json
{
  "code": 0,
  "data": {
    "id": "o_001",
    "status": "confirmed"
  }
}
```

### POST `/api/v1/admin/orders/{orderId}/expire-unpaid`

关闭超时未支付订单并释放已预占库存。该接口用于后台人工兜底，也可被定时任务复用。

成功后返回的订单数据会将 `paymentStatus` 更新为 `expired`，`paymentExpiredReason` 置为 `payment_timeout`，订单履约状态置为 `cancelled`。

### POST `/api/v1/admin/orders/expire-timeout-unpaid`

后台手动触发一次未支付超时扫描。接口扫描当前待支付订单，把超过 30 分钟未支付的订单批量关闭并释放库存。

响应：

```json
{
  "code": 0,
  "data": {
    "expiredCount": 1,
    "orders": []
  }
}
```

## 客服

## 客户群登记

客户群登记用于承接“企业微信客户群触达 -> 小程序结构化登记 -> Platform 后台汇总 -> 微信客服单聊承接”的流程。企业微信客户群本身不作为群内实时 AI 回复入口；小程序只负责打开登记页、校验表单、提交登记和展示结果。活动生成、群归因、后台汇总、客服跟进和后续状态流转属于 `YunxiBakeBot` / `Platform` 主仓。

### 登记页参数

小程序非 tab 页路径：

```text
/pages/group-registration/index?campaignId=campaign_001&groupName=VIP%E5%AE%A2%E6%88%B7%E7%BE%A4&title=%E7%BE%A4%E5%86%85%E7%A6%8F%E5%88%A9%E7%99%BB%E8%AE%B0&productName=%E8%8D%89%E8%8E%93%E5%A5%B6%E6%B2%B9%E8%9B%8B%E7%B3%95
```

Query：

- `campaignId` 必填，活动或客户群触达批次 ID，由 Platform 生成。
- `groupName` 可选，仅用于小程序页展示。
- `title` 可选，登记页标题，默认“群内福利登记”。
- `productName` 可选，预填登记商品名。

MVP 阶段通过 `campaignId` 完成客户群触达归因；`opengid_to_chatid` 或企业微信更细粒度群身份映射未接入前，不要求小程序在前端解析群身份。

### POST `/api/v1/miniapp/group-registrations`

提交当前微信用户的客户群活动登记。

请求：

```json
{
  "campaignId": "campaign_001",
  "customerName": "大海",
  "customerPhone": "18800000000",
  "productName": "草莓奶油蛋糕",
  "quantity": 1,
  "fulfillmentMethod": "pickup",
  "desiredTime": "2026-06-23 18:00",
  "address": "",
  "remark": "少糖"
}
```

字段规则：

| 字段 | 规则 |
|---|---|
| `campaignId` | 必填，不能为空 |
| `customerName` | 必填，联系人 |
| `customerPhone` | 必填，11 位手机号 |
| `productName` | 必填，登记商品或需求 |
| `quantity` | 必填，正整数 |
| `fulfillmentMethod` | `pickup` 或 `delivery` |
| `desiredTime` | 必填，建议格式 `YYYY-MM-DD HH:mm` |
| `address` | `delivery` 时必填，`pickup` 时可为空 |
| `remark` | 可选 |

响应：

```json
{
  "code": 0,
  "data": {
    "id": "gr_001",
    "campaignId": "campaign_001",
    "groupId": "group_001",
    "userId": "wx_openid",
    "customerName": "大海",
    "customerPhone": "18800000000",
    "productName": "草莓奶油蛋糕",
    "quantity": 1,
    "fulfillmentMethod": "pickup",
    "desiredTime": "2026-06-23 18:00",
    "address": "",
    "remark": "少糖",
    "status": "pending",
    "createdAt": "2026-06-22T12:00:00+08:00",
    "updatedAt": "2026-06-22T12:00:00+08:00"
  }
}
```

`status` 取值：

| status | 含义 |
|---|---|
| `pending` | 已提交，待后台或客服确认 |
| `confirmed` | 已确认 |
| `cancelled` | 已取消 |

### GET `/api/v1/miniapp/group-registrations/me`

返回当前 Bearer 会话用户提交过的客户群登记记录，按创建时间倒序返回。生产默认不接受 `x-miniapp-user-id`；该请求头仅在后端显式开启 `STOREFRONT_AUTH_ALLOW_LEGACY_HEADER=true` 时用于迁移兼容。

```json
{
  "code": 0,
  "data": [
    {
      "id": "gr_001",
      "campaignId": "campaign_001",
      "groupId": "group_001",
      "userId": "wx_openid",
      "customerName": "大海",
      "customerPhone": "18800000000",
      "productName": "草莓奶油蛋糕",
      "quantity": 1,
      "fulfillmentMethod": "pickup",
      "desiredTime": "2026-06-23 18:00",
      "address": "",
      "remark": "少糖",
      "status": "pending",
      "createdAt": "2026-06-22T12:00:00+08:00",
      "updatedAt": "2026-06-22T12:00:00+08:00"
    }
  ]
}
```

### POST `/api/v1/miniapp/chat/messages`

发送用户消息到 AI 客服。

请求：

```json
{
  "content": "我想定制一个生日蛋糕"
}
```

响应：

```json
{
  "code": 0,
  "data": {
    "sessionId": "s_001",
    "reply": "您好，可以告诉我预计人数、取货时间和口味偏好吗？",
    "status": {
      "sessionId": "s_001",
      "status": "active",
      "label": "AI 客服接待中",
      "description": "可继续咨询蛋糕、配送和定制问题。",
      "isHumanHandoff": false
    },
    "messages": [
      {
        "id": "m_001",
        "role": "user",
        "content": "我想定制一个生日蛋糕",
        "createdAt": "2026-06-16 12:00:00"
      },
      {
        "id": "m_002",
        "role": "assistant",
        "content": "您好，可以告诉我预计人数、取货时间和口味偏好吗？",
        "createdAt": "2026-06-16 12:00:01"
      }
    ]
  }
}
```

### GET `/api/v1/miniapp/chat/messages`

拉取当前会话消息。

响应：

```json
{
  "code": 0,
  "data": {
    "messages": [
      {
        "id": "m_001",
        "role": "user",
        "content": "我想定制一个生日蛋糕",
        "createdAt": "2026-06-16 12:00:00"
      }
    ],
    "status": {
      "sessionId": "s_001",
      "status": "transfer_pending",
      "label": "正在转接人工客服",
      "description": "我们已通知人工客服，请稍候。",
      "isHumanHandoff": true
    }
  }
}
```

该接口要求携带 `Authorization: Bearer <accessToken>`。缺少、过期或无效 token 返回 `401`，用户身份由服务端会话识别。

### POST `/api/v1/miniapp/chat/transfer`

小程序用户主动请求转人工客服。后端会复用当前小程序客服会话；如会话不存在则先创建会话，再创建后台待接单工单。后台客服台通过既有转人工队列接单。

请求：

```json
{
  "reason": "需要人工确认配送范围"
}
```

`reason` 可选；为空时后端统一使用“小程序用户主动请求人工客服”。

响应字段与 `GET /api/v1/miniapp/chat/messages` 一致，成功后 `status.status=transfer_pending`：

```json
{
  "code": 0,
  "data": {
    "messages": [],
    "status": {
      "sessionId": "s_001",
      "status": "transfer_pending",
      "label": "正在转接人工客服",
      "description": "我们已通知人工客服，请稍候。",
      "isHumanHandoff": true
    }
  }
}
```

`status.status` 取值：

| status | 含义 |
|---|---|
| `active` | AI 客服接待中 |
| `transfer_pending` | 已创建转人工工单，等待人工接单 |
| `human_service` | 人工客服接待中，AI 暂停自动回复 |
| `closed` | 会话已结束 |

## 认证

### POST `/api/v1/miniapp/auth/login`

使用 `wx.login` 的 code 换取后端会话。

请求：

```json
{
  "code": "wx-login-code"
}
```

响应：

```json
{
  "code": 0,
  "data": {
    "userId": "wx_openid_xxx",
    "openid": "openid_xxx",
    "sessionReady": true,
    "isDemo": false,
    "accessToken": "<access-token>",
    "tokenType": "Bearer",
    "expiresIn": 3600
  }
}
```

MVP 阶段如果后端未配置微信小程序 AppID/Secret，则可能无法换取真实会话；此时前端不应把失败结果伪装成已登录状态。

小程序客户端会把完整登录响应缓存为 `miniappSession`，包括 `accessToken`、`tokenType` 和 `expiresIn`，并兼容读取旧版 `miniappUserId` 存储键。旧缓存缺少 token 元数据时视为未登录。所有受保护业务请求携带服务端会话：

```http
Authorization: Bearer <miniappSession.accessToken>
```

首次收到 `401` 时，小程序清理仍匹配的旧 token、重新登录并最多重放原请求一次；第二次 `401` 或续登失败直接回到未登录态。个人中心展示当前会话状态，支持强制重新登录刷新 `miniappSession`。真实微信支付预下单依赖服务端会话；未登录或会话未就绪时，前端应提示用户重新登录，不应自动冒充已登录用户。

## 小程序店铺运营配置

### GET `/api/v1/miniapp/shop-settings`

返回小程序公开可展示的店铺运营配置。小程序读取失败时回退本地默认配置。

```json
{
  "code": 0,
  "data": {
    "shopName": "芸熙烘焙",
    "customerWechat": "13240240418",
    "customerPhone": "13240240418",
    "businessHours": "09:00-20:00",
    "pickupAddress": "北京市东城区南竹杆胡同2号银河SOHO",
    "deliveryNotice": "门店配送需提前预约，配送范围和费用以客服确认为准",
    "pickupNotice": "蛋糕建议提前 24 小时预订，到店自提前请确认取货时间",
    "paymentMode": "mock",
    "privacyPolicyTitle": "隐私政策",
    "privacyPolicyContent": "我们仅在下单、配送、客服和售后所必需的范围内收集联系人、手机号、地址、订单备注等信息，并用于完成蛋糕预订、履约通知和售后服务。",
    "userAgreementTitle": "用户协议",
    "userAgreementContent": "用户在芸熙烘焙小程序下单前，应确认商品规格、取货或配送时间、联系人和备注信息。",
    "afterSalesPolicyTitle": "售后说明",
    "afterSalesPolicyContent": "蛋糕属于即时制作食品，请在约定时间取货或收货。若出现配送破损、商品错漏或质量问题，请保留照片和订单信息并第一时间联系客服。"
  }
}
```

小程序必须从该接口读取用户协议、隐私政策和售后说明文案：

- 结账页提交前要求用户确认已阅读并同意用户协议与隐私政策。
- 我的页服务入口可跳转查看用户协议、隐私政策和售后说明。
- 接口不可用时客户端使用本地默认文案兜底，保证体验版和开发环境仍可运行。

`paymentMode` 取值：

| paymentMode | 含义 |
|---|---|
| `mock` | 默认值。当前未启用完整微信支付商户配置时，走模拟支付兜底 |
| `wechat` | 微信 JSAPI 支付，要求后端支付商户参数和通知回调完整可用 |
| `store_confirm` | 历史兼容值，仅用于旧配置兜底，不作为新公开配置默认值 |

小程序端必须把未知 `paymentMode` 当作配置错误处理；真实支付上线前不得把 `mock` 或 `store_confirm` 解释为微信支付已闭环。

## 后台装修 API

后台项目：`YunxiBakeBot/web/admin`

### GET `/api/v1/admin/shop-config/pages/{pageId}`

返回页面草稿和已发布配置。

### PUT `/api/v1/admin/shop-config/pages/{pageId}/draft`

保存页面装修草稿。请求体为完整页面装修 JSON。

### POST `/api/v1/admin/shop-config/pages/{pageId}/publish`

发布页面装修配置。发布后小程序 `GET /api/v1/miniapp/pages/{pageId}` 读取最新 `published` 版本。

### POST `/api/v1/admin/shop-config/assets`

上传后台装修素材，当前用于首页 `heroCarousel` 多图轮播主推位。请求必须携带后台管理员 Bearer Token。

请求：

- `Content-Type: multipart/form-data`
- 字段名：`file`
- 支持类型：`image/jpeg`、`image/png`、`image/webp`
- 单文件大小：最大 2MB

响应：

```json
{
  "code": 0,
  "data": {
    "imageUrl": "/static/uploads/decoration/decoration-20260617-abcdef.png"
  }
}
```

后台装修页上传成功后，应把 `data.imageUrl` 写入 `heroCarousel.props.items[].imageUrl`。小程序端会把 `/static/...` 这类相对路径补全为当前 `API_BASE_URL` 下的完整图片地址后轮播展示。

### 后台轮播图上传要求

首页轮播图上传属于后台装修能力，建议由 `YunxiBakeBot/web/admin` 在页面装修表单中提供图片上传控件：

- 支持一次添加多张轮播图，保存为 `heroCarousel.props.items`。
- 每张图上传成功后写入可被小程序合法域名访问的 `imageUrl`。
- 每张图可选配置 `title`、`subtitle`、`eyebrow`、`linkType` 和 `linkTarget`。
- 小程序端不直接负责选择本地相册并上传装修图；它只读取已发布配置并轮播展示。
- 推荐图片比例为宽屏横图，约 `690rpx x 220rpx`，上传前后台可裁切或提示尺寸。

## 后台店铺运营配置 API

### GET `/api/v1/admin/shop-config/operations`

读取店铺公开运营配置草案。

### PUT `/api/v1/admin/shop-config/operations`

保存店铺公开运营配置。字段同 `GET /api/v1/miniapp/shop-settings` 的 `data`，包括客服电话、营业时间、取货/配送说明、隐私政策、用户协议和售后说明。
