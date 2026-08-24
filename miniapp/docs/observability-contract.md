# Storefront MiniApp 可观测合约

trace_id: `20260707-miniapp-observability-contract`

本合约对应 `GitHub 参考项目借鉴与可实施计划` 阶段 6 的 MiniApp 指标部分。当前只冻结指标、事件字段、隐私边界和降级规则，不新增埋点 SDK，不发送生产日志，不改变页面运行时代码。

## 目标

Storefront MiniApp 的可观测能力服务于三个问题：

- 用户是否能顺利打开关键页面和调用 Platform API。
- 商品、购物车、结算、支付和客服入口是否形成完整消费者路径。
- 失败是否能回到 Platform API、微信平台配置、真实登录、支付商户或页面交互证据，而不是靠主观体验判断。

## 核心指标

| 指标 | 含义 | 最小事件来源 |
|---|---|---|
| `page_api_failure_rate` | 页面依赖 Platform API 的失败比例 | 页面加载、服务请求结果 |
| `product_detail_open_success_rate` | 商品详情打开并拿到有效商品数据的比例 | 商品列表点击、详情页加载结果 |
| `cart_checkout_start_success_rate` | 购物车进入结算并带入有效商品的比例 | 购物车点击结算、结算页初始化 |
| `order_create_success_rate` | 结算页创建订单成功比例 | 下单请求结果 |
| `payment_prepare_success_rate` | `prepare-payment` 返回可处理支付模式的比例 | 支付准备请求结果 |
| `payment_invoke_success_rate` | 微信支付或 mock 支付唤起成功比例 | 支付按钮、`wx.requestPayment` 或 mock-pay 结果 |
| `chat_entry_click_rate` | 用户进入客服页或点击联系客服入口的比例 | 动态入口、订单详情、群登记和底部导航 |
| `manual_handoff_click_rate` | 用户主动请求转人工的比例 | 客服页转人工按钮 |
| `session_gate_block_rate` | 未真实登录导致订单、客服、结算、地址、群登记被拦截的比例 | 页面会话门槛判断 |
| `group_registration_submit_success_rate` | 客户群登记提交成功比例 | 群登记提交请求结果 |

## 事件字段

未来新增运行时事件时，至少要保留以下字段；当前阶段只作为契约，不要求立即实现：

| 字段 | 说明 |
|---|---|
| `trace_id` | 与 Platform 或发布验证共享的追踪号 |
| `event_name` | 稳定事件名，例如 `product_detail_open`、`order_create`、`payment_prepare` |
| `page_path` | 小程序页面路径 |
| `route_source` | 入口来源，例如 tab、home、product_list、order_detail、group_registration |
| `api_path` | 去除 query 和敏感参数后的 Platform API 路径 |
| `api_result` | success、fail、timeout、blocked |
| `error_code` | 规范化错误码，不能直接记录完整后端错误体 |
| `payment_mode` | mock、wechat、unknown |
| `session_state` | ready、not_ready、demo、blocked |
| `duration_ms` | 请求或交互耗时 |
| `network_type` | 微信运行环境可安全获得时记录 |
| `platform` | iOS、Android、DevTools 或 unknown |

## 隐私边界

MiniApp 观测事件不得记录以下内容：

- 完整手机号。
- 完整收货地址。
- 完整订单号。
- 完整微信 openid / unionid / session key。
- 完整支付交易号。
- 订单备注全文。
- 真实 AppID、密钥、Token、Cookie、证书或商户私钥。

如需关联问题，只能使用 Platform 返回的脱敏标识、短 hash、枚举化错误码或 trace_id。观测事件不能成为新的客户主档、订单账本、营销规则或支付对账来源。

## 降级规则

- 观测失败不得阻断页面加载、下单、支付唤起、客服发送或客户群登记。
- 观测失败只允许进入本地调试日志或后续安全的失败缓冲，不向用户展示无关错误。
- 未拿到真实登录态时，可以记录 `session_state=blocked` 的聚合事件，但不得上传完整用户标识。
- 支付相关事件只能记录 `payment_mode`、规范化结果和 trace_id，不能记录支付签名参数。
- 客服和群登记事件不得记录用户消息全文、备注全文、完整手机号或完整地址。

## 与 Platform 的关系

MiniApp 只记录前台路径和请求结果。业务解释仍回到 Platform：

- 商品、库存、价格、分类、规格真相来自 Platform。
- 订单状态、支付状态、履约状态来自 Platform。
- 客服会话、转人工队列和 AI 回复来自 Platform。
- 会员权益、积分、储值余额、优惠券、配送费、满减和活动价需要先由 Platform 定义 API 契约。

## 验证

运行：

```powershell
npm run check:observability-contract
```

该检查会验证核心指标、事件字段、隐私边界、降级规则和 Platform 边界都已写入本合约。
