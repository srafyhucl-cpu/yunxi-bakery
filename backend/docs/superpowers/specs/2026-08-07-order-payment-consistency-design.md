# 订单支付、取消与库存一致性设计

- 状态：已批准并完成本地实现
- trace_id：`20260807-order-payment-consistency`
- 来源：全局风险复盘中发现已支付订单仍可被取消并释放库存

## 目标

保证订单不会进入以下非法状态：

```text
payment.status = paid
status = cancelled
库存已释放
```

支付通知、mock 支付、用户取消、后台取消和未支付超时关闭必须在同一套数据库条件迁移规则下运行。并发或重复请求只能有一个状态迁移成功，失败方读取最新状态并返回幂等结果或明确业务错误。

## 状态迁移合同

| 操作 | 数据库成功条件 | 成功结果 |
|---|---|---|
| 用户/后台取消 | `status in (pending, confirmed)` 且支付状态为 `unpaid` | `status -> cancelled` |
| mock/微信支付 | `status != cancelled` 且支付状态为 `unpaid` | 支付状态 `unpaid -> paid` |
| 未支付超时关闭 | `status != cancelled` 且支付状态为 `unpaid` | 同一条 SQL 写入 `expired` 与 `cancelled` |

条件不满足时禁止覆盖订单。取消和超时关闭只有在条件迁移成功后才能释放库存；重复取消、重复关闭和重复通知不得再次释放库存或追加重复状态事件。

## 分层与事务

- `app/repository/order_repo.py` 提供原子条件更新，不自行提交事务。
- `app/service/order/cancellation.py` 和 `status_flow.py` 负责归属、状态判定、冲突错误和事件编排。
- `app/service/order/payment_notification.py` 先执行支付条件写入，再认领唯一交易号；外层事务失败时整体回滚。
- `app/service/order/payment_runtime.py` 通过同一仓储合同处理 mock 支付和微信支付通知。
- `app/service/order/expiration.py` 负责未支付资格判断、条件关单、成功后的库存释放与时间线事件，竞争失败时不追加事件。
- `OrderApplicationService` 继续作为写链路 Unit of Work 边界，库存写入、订单写入和事件写入共同提交或回滚。

## 测试验收

必须覆盖：

1. 已支付订单不能被用户或后台取消，库存保持已预占状态。
2. 取消先发生时，后续 mock/微信支付不能写入 `paid`。
3. 支付先发生时，后续用户/后台取消不能写入 `cancelled`。
4. 微信重复通知保持单一支付事件和单一交易号认领。
5. 重复取消只释放一次库存并只追加一次取消事件。
6. 未支付超时关闭仍能原子写入 `expired + cancelled` 并释放一次库存。

本设计不包含真实微信支付、生产数据库操作、退款流程或支付后退款策略；已支付订单如需关闭，必须进入后续退款/售后流程。
