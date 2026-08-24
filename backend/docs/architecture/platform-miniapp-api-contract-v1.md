# Platform ↔ Storefront MiniApp API Contract v1

## 文档目的

这份文档用于固定当前 `Platform` 仓与 `Storefront MiniApp` 仓之间的第一版接口契约，避免后续双仓继续靠口头理解对接。

本文件只回答 4 个问题：

- `MiniApp` 现在应该调用哪些公开接口
- 每组接口背后的 `Platform` canonical 归属域是什么
- 哪些字段和行为可以视为当前稳定契约
- 哪些 `miniapp_*` 命名只是兼容层，后续应继续收口

## 适用范围

- 当前 `Platform` 代码仓路径：`YunxiBakeBot`
- 当前 `Storefront MiniApp` 代码仓路径：`YunxiBakeMiniApp`
- 当前逻辑总项目名：`Bakery Commerce Platform`
- 当前首个实例名：`Yunxi`

## 契约原则

1. `MiniApp` 只消费 `Platform` 公开 API，不自建客户、商品、订单真相。
2. `Platform` 继续保留既有 `/api/v1/miniapp/*` 路径，作为渠道兼容 facade。
3. `Platform` 内部真实能力归 canonical 领域所有，`miniapp_*` 命名不再等于业务真相。
4. 第一阶段不修改外部 HTTP 路径、不修改数据库 schema、不修改线上已运行行为。

## 仓边界结论

### `Platform` 负责

- 小程序登录态换取与用户标识生成
- 客户地址簿真相
- 商品、分类、图片代理真相
- 订单创建、库存占用、取消、支付准备、支付通知
- AI 会话、转人工、会话状态
- 店铺运营配置与装修发布版内容

### `Storefront MiniApp` 负责

- 页面、组件、交互与微信能力接入
- API client、登录态保存、本地缓存
- 把 `Platform` 返回的数据渲染给用户
- 不在前台仓实现客户主档、订单规则、商品规则、CRM 规则

## Canonical 领域映射

| 对外接口分组 | 当前公开前缀 | canonical 归属域 | 备注 |
| --- | --- | --- | --- |
| 认证 | `/api/v1/miniapp/auth` | `channels/storefront` | 小程序渠道接入层 |
| 地址簿 | `/api/v1/miniapp/addresses` | `customer` | 客户地址真相 |
| 商品目录 | `/api/v1/miniapp/products` | `catalog` | 商品与分类真相 |
| 客服会话 | `/api/v1/miniapp/chat` | `conversation` + `channels/storefront` | 会话真相在 `conversation` |
| 用户订单 | `/api/v1/miniapp/orders` | `order` | 订单与库存真相 |
| 支付通知 | `/api/v1/miniapp/payments` | `order` + `integrations` | 第三方支付接入 |
| 装修页面 | `/api/v1/miniapp/pages` | `ops` | 发布版页面投影 |
| 店铺运营配置 | `/api/v1/miniapp/shop-settings` | `ops` | 发布给前台的运营配置 |

## 稳定性定义

- `stable`
  - `MiniApp` 可直接依赖，字段语义已在测试中固定。
- `compatibility`
  - 路径稳定，但命名明显带历史痕迹，后续只做内部收口，不立刻改外部路径。
- `projection`
  - 这是 `Platform` 某个后台真相的前台投影，不应被 `MiniApp` 当作编辑真相源。

## 统一约定

### 响应包裹

除图片代理和微信支付通知外，当前公开接口统一返回：

```json
{
  "code": 0,
  "data": {}
}
```

### Bearer 会话与用户隔离

以下接口要求使用服务端签发的 Bearer 会话，并按 JWT `sub` 做用户隔离：

- `/api/v1/miniapp/addresses/*`
- `/api/v1/miniapp/chat/*`
- `/api/v1/miniapp/orders/*`

请求头：

```http
Authorization: Bearer <accessToken>
```

当前兼容行为：

- `x-miniapp-user-id` 仅在 `STOREFRONT_AUTH_ALLOW_LEGACY_HEADER=true` 时作为历史迁移头接受。
- MiniApp 运行时不得发送 `x-miniapp-user-id`；生产默认关闭该兼容开关。
- 缺少、过期或无效 Bearer token 返回 `401`；token 身份与显式请求身份不一致返回 `403`。
- 资源不存在或不属于当前用户的订单、地址等资源继续按资源接口语义返回 `404`。

### 错误语义

- 参数错误、业务校验失败：`400`
- 非当前用户资源、资源不存在：`404`
- 管理端未授权：`401`

## 接口清单

### 1. 认证

| 方法 | 路径 | 稳定性 | MiniApp 用途 | 归属域 |
| --- | --- | --- | --- | --- |
| `POST` | `/api/v1/miniapp/auth/login` | `stable` | 登录时用 `code` 换取小程序用户标识 | `channels/storefront` |

请求关键字段：

- `code`

响应关键字段：

- `userId`
- `openid`
- `sessionReady`
- `isDemo`
- `accessToken`
- `tokenType`，当前固定为 `Bearer`
- `expiresIn`，单位为秒

当前行为约束：

- 未配置微信 `AppID/Secret` 时，后端应明确返回失败，不应伪装成已登录会话。
- 已配置时，后端按 `openid` 生成 `userId`，当前格式为 `wx_<openid>`。
- 客户端用 `expiresIn` 计算本地过期时间；服务端身份真相来自 Bearer token 的 JWT `sub`，不是客户端提交的 `userId`。

真相说明：

- `MiniApp` 只保存登录结果，不生成用户真相。
- 用户标识生成规则由 `Platform` 渠道层决定。

### 2. 地址簿

| 方法 | 路径 | 稳定性 | MiniApp 用途 | 归属域 |
| --- | --- | --- | --- | --- |
| `GET` | `/api/v1/miniapp/addresses` | `stable` | 读取当前用户地址列表 | `customer` |
| `POST` | `/api/v1/miniapp/addresses` | `stable` | 新增或保存地址 | `customer` |
| `POST` | `/api/v1/miniapp/addresses/{address_id}/default` | `stable` | 设置默认地址 | `customer` |
| `DELETE` | `/api/v1/miniapp/addresses/{address_id}` | `stable` | 删除地址 | `customer` |

稳定字段：

- `id`
- `receiverName`
- `receiverPhone`
- `address`
- `isDefault`

当前行为约束：

- 首个地址默认会成为默认地址。
- 返回列表默认把默认地址排前。
- 不允许跨用户读取或修改地址。
- 缺少联系人等校验错误返回 `400`。

真相说明：

- 地址主档只在 `Platform.customer`。
- `MiniApp` 只做录入与展示，不持有地址规则真相。

### 3. 商品目录

| 方法 | 路径 | 稳定性 | MiniApp 用途 | 归属域 |
| --- | --- | --- | --- | --- |
| `GET` | `/api/v1/miniapp/products` | `stable` | 商品列表、精选、分类过滤、装修定向货架 | `catalog` |
| `GET` | `/api/v1/miniapp/products/{product_id}` | `stable` | 商品详情页 | `catalog` |
| `GET` | `/api/v1/miniapp/products/{product_id}/image` | `compatibility` | 图片代理 | `catalog` |
| `GET` | `/api/v1/miniapp/product-categories` | `stable` | 分类页与筛选器 | `catalog` |

列表请求参数：

- `ids`
- `categoryId`
- `featured`

详情稳定字段：

- `id`
- `title`
- `imageUrl`
- `priceFen`
- `soldText`
- `categoryId`
- `categoryName`
- `tags`

分类稳定字段：

- `id`
- `title`
- `sort`
- `productCount`

当前行为约束：

- 商品列表只返回当前可售商品。
- `ids` 过滤会去重并忽略缺失商品。
- `featured=true` 返回后台配置的主推商品。
- `imageUrl` 当前固定指向 `Platform` 图片代理路径。
- 无图、下架、非安全协议图片地址一律 `404`，不透出源地址。

真相说明：

- 商品、分类、上下架状态真相在 `Platform.catalog`。
- `MiniApp` 不缓存商品规则，也不自行推导分类。

### 4. 客服会话

| 方法 | 路径 | 稳定性 | MiniApp 用途 | 归属域 |
| --- | --- | --- | --- | --- |
| `POST` | `/api/v1/miniapp/chat/messages` | `stable` | 发送用户消息并获得最新回复状态 | `conversation` + `channels/storefront` |
| `GET` | `/api/v1/miniapp/chat/messages` | `stable` | 拉取当前会话消息与状态 | `conversation` + `channels/storefront` |
| `POST` | `/api/v1/miniapp/chat/transfer` | `stable` | 请求转人工 | `conversation` + `channels/storefront` |

消息响应稳定字段：

- `messages`
- `status`

`messages[*]` 已验证字段：

- `id`
- `role`
- `content`
- `createdAt`

`status` 已验证字段：

- `sessionId`
- `status`
- `label`
- `description`
- `isHumanHandoff`

当前行为约束：

- 发送空消息返回 `400`。
- 未传用户头时回退 demo 用户。
- 未传转人工原因时，后端补默认原因：`小程序用户主动请求人工客服`。

真相说明：

- 会话状态与转人工工单真相在 `Platform.conversation`。
- `MiniApp` 只展示消息和状态，不自己维护“是否已转人工”的规则。

### 5. 用户订单

| 方法 | 路径 | 稳定性 | MiniApp 用途 | 归属域 |
| --- | --- | --- | --- | --- |
| `POST` | `/api/v1/miniapp/orders` | `stable` | 创建订单 | `order` |
| `GET` | `/api/v1/miniapp/orders` | `stable` | 用户订单列表 | `order` |
| `GET` | `/api/v1/miniapp/orders/{order_id}` | `stable` | 订单详情与时间线 | `order` |
| `POST` | `/api/v1/miniapp/orders/{order_id}/cancel` | `stable` | 用户取消订单 | `order` |
| `POST` | `/api/v1/miniapp/orders/{order_id}/mock-pay` | `compatibility` | 本地或无商户配置时的 mock 支付 | `order` |
| `POST` | `/api/v1/miniapp/orders/{order_id}/prepare-payment` | `stable` | 统一支付准备入口 | `order` |

下单请求关键字段：

- `items`
- `receiverName`
- `receiverPhone`
- `expectTime`

订单稳定字段：

- `orderId`
- `status`
- `totalFen`
- `paymentStatus`
- `paymentMethod`

详情补充稳定字段：

- `timeline`

`timeline[*]` 已验证字段：

- `status`
- `note`

支付准备稳定字段：

- `mode`
- `paymentMethod`
- `paymentParams`

当前行为约束：

- 下单使用 `Platform` 商品真相价格，不信任前端传入价格。
- 库存不足返回 `400`。
- `expectTime` 必须为 `YYYY-MM-DD HH:mm`。
- 超出营业时间返回 `400`。
- 订单、取消、支付准备、mock 支付都受当前用户隔离约束。
- 非本人订单统一返回 `404`，不暴露存在性。
- mock 支付目前仍保留，主要用于开发与无微信支付配置场景。

真相说明：

- 订单状态、库存占用、支付状态、订单事件流全在 `Platform.order`。
- `MiniApp` 不实现订单状态机。

### 6. 微信支付通知

| 方法 | 路径 | 稳定性 | MiniApp 用途 | 归属域 |
| --- | --- | --- | --- | --- |
| `POST` | `/api/v1/miniapp/payments/wechat/notify` | `compatibility` | 供微信支付平台回调，不由 `MiniApp` 主动调用 | `order` + `integrations` |

成功响应：

```json
{
  "code": "SUCCESS",
  "message": "成功"
}
```

当前行为约束：

- 签名无效返回 `400`。
- 支付成功后，订单会回写：
  - `paymentStatus = paid`
  - `paymentMethod = wechat`
  - `paymentPaidAt`

真相说明：

- 这是第三方支付系统到 `Platform` 的入站接口。
- `MiniApp` 只需调用 `prepare-payment` 获取前置支付参数，不直接对接通知落账逻辑。

### 7. 装修页面发布版

| 方法 | 路径 | 稳定性 | MiniApp 用途 | 归属域 |
| --- | --- | --- | --- | --- |
| `GET` | `/api/v1/miniapp/pages/{page_id}` | `projection` | 读取首页、商品页、我的页等发布版装修配置 | `ops` |

后台对应真相接口：

- `GET /api/v1/admin/shop-config/pages/{page_id}`
- `PUT /api/v1/admin/shop-config/pages/{page_id}/draft`
- `POST /api/v1/admin/shop-config/pages/{page_id}/publish`

当前行为约束：

- `MiniApp` 读到的永远是已发布版本，不是草稿。
- 后台保存草稿不会立即影响前台读取。
- 发布后，前台与后台 published 视图读取同一份配置。

当前已验证页面：

- `home`
- `products`
- `profile`

真相说明：

- 页面装修真相在 `Platform.ops`。
- `MiniApp` 不能把装修接口当成本地页面规则源去二次演化。

### 8. 店铺运营配置

| 方法 | 路径 | 稳定性 | MiniApp 用途 | 归属域 |
| --- | --- | --- | --- | --- |
| `GET` | `/api/v1/miniapp/shop-settings` | `projection` | 读取店铺基础信息、营业时间、售后与协议文案 | `ops` |

后台对应真相接口：

- `GET /api/v1/admin/shop-config/operations`
- `PUT /api/v1/admin/shop-config/operations`

当前已验证稳定字段：

- `shopName`
- `customerWechat`
- `customerPhone`
- `businessHours`
- `pickupAddress`
- `deliveryNotice`
- `pickupNotice`
- `paymentMode`
- `privacyPolicyTitle`
- `privacyPolicyContent`
- `userAgreementTitle`
- `userAgreementContent`
- `afterSalesPolicyTitle`
- `afterSalesPolicyContent`

当前行为约束：

- 后台更新后，前台公开接口读取同一份最新配置。
- 管理端保存空字段时，后端保留旧值。
- `businessHours` 格式必须为 `HH:mm-HH:mm`。

真相说明：

- 店铺运营配置只在 `Platform.ops`。
- `MiniApp` 不应复制营业时间、隐私政策、售后政策等业务文案规则。

### 9. 客户群结构化登记

| 方法 | 路径 | 稳定性 | MiniApp 用途 | 归属域 |
| --- | --- | --- | --- | --- |
| `POST` | `/api/v1/miniapp/group-registrations` | `stable` | 提交客户群团购或预订登记 | `customer` |
| `GET` | `/api/v1/miniapp/group-registrations/me` | `stable` | 查看当前用户的登记记录 | `customer` |

稳定字段：

- `id`
- `groupId`
- `campaignId`
- `status`
- `fulfillmentMode`
- `createdAt`

当前行为约束：

- 登记页必须携带团购批次上下文，不能脱离批次独立提交。
- `MiniApp` 只负责表单录入和个人记录展示，不保存群运营真相。
- 运营汇总与状态更新统一由 `Platform.customer` 承接。

真相说明：

- 客户群绑定、批次和登记汇总都在 `Platform.customer`。
- `group_registrations` 是前台渠道入口，不是新的业务真相源。

## 对 `Storefront MiniApp` 仓的接入要求

### 必须做

- 所有小程序前台能力统一走本文件列出的公开接口。
- 所有受保护请求统一注入 `Authorization: Bearer <accessToken>`；历史 `x-miniapp-user-id` 只允许显式迁移配置开启。
- 页面装修、店铺配置按“后端投影”使用，不在前台再造一套配置中心。
- 客户群登记页只调用 `/api/v1/miniapp/group-registrations`，不直连后台客户群 API。

### 不应再做

- 在 `MiniApp` 仓新增客户主档模型。
- 在 `MiniApp` 仓新增商品定价、库存、分类真相。
- 在 `MiniApp` 仓实现订单状态流转规则。
- 在 `MiniApp` 仓把“转人工”“支付完成”“订单可取消”等状态写死为本地业务规则。

## 当前残留的过渡态

- 外部路径仍沿用 `/api/v1/miniapp/*`，这是兼容命名，不代表业务真相仍属于 `miniapp_*`。
- 部分接口仍支持 demo 用户回退，这更适合联调阶段，不适合长期正式身份方案。
- `mock-pay` 仍保留，后续应只作为开发或测试兜底能力存在。
- `customer` 域的当前权威入口已经单独收束到四段闭环：
  - [有赞客户迁移审计清单](./youzan-customer-migration-audit-checklist.md)
  - [有赞客户正式迁移执行 Runbook](./youzan-customer-formal-import-runbook.md)
  - `scripts/verify_youzan_customer_import.py`
  - [有赞客户迁移交接与回滚 Runbook](./youzan-customer-import-handoff-and-rollback-runbook.md)

## v1 冻结建议

这一版建议先冻结以下内容，避免双仓继续相互猜测：

1. 路径层：现有 `/api/v1/miniapp/*` 路径全部保持不变。
2. 字段层：本文件列出的稳定字段视为当前前后台共享契约。
3. 权责层：客户、商品、订单、会话、装修、运营配置真相全部只在 `Platform`。
4. 组织层：`Yunxi` 只作为实例名存在，不再进入新增接口命名。
5. 迁移层：客户主档落地、正式迁移执行、迁移后核对和 apply 后交接回滚，优先看上面的四段闭环，而不是在 API 契约里继续追加迁移步骤。

## 当前协作入口

1. 让 `Storefront MiniApp` 仓按本文件补齐 API client 命名映射，明确每个页面依赖哪组接口。
2. 在 `Platform` 仓继续把 `customer` 域做成后续 CRM 与企微绑定入口，但不改当前外部契约。
3. 迁移相关执行与恢复，优先沿用四段闭环的 `customer` 文档。
4. 如需回看双仓历史过渡材料，统一从 `docs/README.md` 的“历史方案”区进入，不在本文件继续展开旧执行路线。
5. 等双仓都稳定消费这份 v1 契约后，再讨论是否推出 v2 命名收口，而不是现在提前改路径。
