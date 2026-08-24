# Platform API Client

`miniprogram/services/` 是 `Storefront MiniApp` 消费 `Platform` 能力的 API client 层。

这里负责：

- 封装 `wx.request`、请求头、API base URL 和错误信息。
- 组织小程序请求参数，例如商品筛选、订单提交、登录 code、客服消息内容。
- 适配 `Platform` 响应，例如解包 `code/data`、补全图片 URL、转换成页面可直接使用的数据形状。
- 在开发或接口不可用时提供前台体验兜底，并保证兜底不会覆盖真实 API 响应。

这里不负责：

- 沉淀客户主档、商品规则真相或订单规则真相。
- 决定商品分类、价格、库存、上下架、订单状态、支付状态或履约规则。
- 实现 CRM、AI 会话主逻辑、后台配置系统或第三方同步真相。

如果 service 层需要承载新的业务判断，先检查它是否只是请求/响应适配。只要判断会改变客户、商品、订单、AI、店铺配置或第三方同步的事实来源，就应回到 `Platform` 主仓和 `docs/api-contract.md` 处理。

当前支付模式口径：

- 店铺公开配置 `paymentMode` 的默认兜底为 `mock`。
- `wechat` 仅在 Platform 返回完整微信支付配置并完成商户联调后使用。
- `store_confirm` 只作为历史兼容值，不作为新配置或前台本地兜底默认值。
