# 企微智能机器人接入说明

## 定位

企业微信只作为员工入口。知识库、商品、订单、客户、客户群、转人工、观察台与离线复盘的业务真相仍在 `YunxiBakeBot` / `Bakery Commerce Platform`。

当前主方向是 **API 模式 + URL 回调**：企微把员工消息加密回调到后端，后端调用内部 skills 后直接返回加密回复。普通模式工具接口保留为调试、冒烟和单项验收入口，不再要求在企微后台手工维护 9 个工具参数。

## API 模式 URL 回调

- 回调 URL：`https://yunxifood.cn/api/v1/wecom/intelligent-bot/callback`
- 请求方式：`GET` 用于保存时校验 URL；`POST` 用于接收员工消息并被动回复。
- 企微后台模式：智能机器人 → API 模式 → 设置接收消息回调地址。
- Token：优先读取 `.env` 的 `WECOM_INTELLIGENT_BOT_TOKEN`；未配置时回退 `WECOM_TOKEN`。
- EncodingAESKey：优先读取 `.env` 的 `WECOM_INTELLIGENT_BOT_ENCODING_AES_KEY`；未配置时回退 `WECOM_ENCODING_AES_KEY`。
- ReceiveId：企业内部智能机器人场景固定为空字符串。

### 当前回复方式

当前先实现非流式文本回复：

1. 员工在单聊或群内 @机器人提问。
2. 企微 `POST /callback`，body 为 `{"encrypt":"..."}`。
3. 后端验签并解密为智能机器人 JSON 明文，例如 `msgtype=text`。
4. 后端把文本路由到内部只读 skills。
5. 后端构造 `{"msgtype":"stream","stream":{"id":"...","finish":true,"content":"..."}}`，加密后返回 `encrypt/msgsignature/timestamp/nonce`。

后续如果需要“正在查询...”和打字机刷新，再扩展为 `stream` 回复与流式刷新回调。

### 内部 Agent 编排

当前回调消息优先进入员工助手 Agent，而不是直接按关键词分发：

1. `EmployeeAgentCapabilityRegistry` 召回订单、商品、知识库、运营状态、待人工、客户线索、客户群活动和离线复盘等能力卡。
2. `EmployeeAgentPlanner` 生成结构化 `AgentPlan`，必要时使用 LLM 辅助规划，但只允许输出查询计划，不允许输出 SQL。
3. `EmployeeAgentService` 按计划调用订单、商品、知识库、运营状态、客户线索、客户群活动和离线复盘等只读工具。
4. 订单类问题由 `OrderQueryPlan` 驱动仓库层白名单参数化 SQL，支持统计、列表、状态筛选、商品关键词、销量排行和订单+库存混合问法。
5. 工具结果先形成确定性文本，并直接经过 `clean_plain_text_reply()` 返回；LLM 只保留在结构化规划兜底阶段，不再生成员工可见回复。

未注入员工 Agent 的测试或调试场景仍保留旧 dispatcher 作为兜底。

## 普通模式工具调试入口

- 基础 URL：`https://yunxifood.cn/api/v1/wecom/intelligent-bot`
- 请求方法：`POST`
- 授权方式：`Service token / API key`
- 位置：`Header`
- Parameter name：`X-Yunxi-Bot-Key`
- Service token/API key：使用 `.env` 中的 `WECOM_BOT_PLUGIN_API_KEY`
- 禁止把密钥放在 URL query 参数中；普通模式工具路由只接受 Header 或 Bearer Token。

## 普通模式工具配置步骤

1. 在企业微信智能机器人后台创建 API 工具。
2. 基础 URL 填 `https://yunxifood.cn/api/v1/wecom/intelligent-bot`。
3. 每个工具路径按下方工具列表单独填写，例如 `order-lookup` 填 `/tools/order-lookup`。
4. 鉴权方式选择 Header，Header 名固定为 `X-Yunxi-Bot-Key`。
5. 密钥从安全位置复制 `WECOM_BOT_PLUGIN_API_KEY`，不要贴到聊天、截图或文档正文。
6. 输出参数优先映射 `result`，参数类型为 `String`，参数描述为“工具返回给模型和员工看的结果文本”。需要排查时再额外映射 `ordersText`、`productsText`、`answer`、`addressesText`、`summaryText`、`transfersText`、`webhooksText`。
7. 发布前先用企微后台“测试工具”逐个测试，再拉进内部群做员工真实问法验收。

如果已经启用 API 模式 URL 回调，这一段不再是上线必需步骤。

## 工具列表

| 优先级 | 工具名 | 路径 | 入参 | 用途 |
|---|---|---|---|---|
| P0 | `ping` | `/plugins/ping` | `text` | 连通性验证 |
| P1 | `order-lookup` | `/tools/order-lookup` | `query`, `limit` | 按订单号、手机号、客户名、商品关键词查订单 |
| P1 | `product-lookup` | `/tools/product-lookup` | `query`, `limit` | 查商品价格、库存、分类和可售状态 |
| P1 | `knowledge-answer` | `/tools/knowledge-answer` | `question`, `limit` | 查配送、退款、售后、话术等知识库内容 |
| P2 | `customer-lookup` | `/tools/customer-lookup` | `query` | 查客户地址簿线索 |
| P2 | `group-campaign-summary` | `/tools/group-campaign-summary` | `campaignId` | 查客户群团购/预订批次汇总文案 |
| P2 | `handoff-pending` | `/tools/handoff-pending` | `limit` | 查当前待人工处理工单 |
| P3 | `ops-summary` | `/tools/ops-summary` | `query` | 查观察台值守摘要 |
| P3 | `integration-status` | `/tools/integration-status` | `query`, `limit` | 查失败 webhook / 同步排障线索 |
| P3 | `offline-review-summary` | `/tools/offline-review-summary` | `query` | 查最近一轮离线复盘摘要 |

## 建议先配置

1. `order-lookup`
2. `product-lookup`
3. `knowledge-answer`
4. `customer-lookup`
5. `group-campaign-summary`
6. `handoff-pending`
7. `ops-summary`
8. `integration-status`
9. `offline-review-summary`

## 输出约定

所有工具都返回扁平可映射字段：

- `ok`
- `tool`
- `query`
- `summary`
- `suggestedReply`
- `result`
- `resultText`
- `nextAction`

`result` 与 `resultText` 是统一可读结果字段，便于企微后台只配置一个输出参数。不同工具还会额外返回 `ordersText`、`productsText`、`answer`、`addressesText`、`summaryText`、`transfersText`、`webhooksText` 等明细字段，用于调试或精细映射。

## 安全边界

- 当前工具全部只读。
- 不在企微工具里修改订单、客户、知识库或群登记状态。
- 订单、客户地址、客户群待跟进和转人工摘要只返回脱敏字段或预览字段。
- 客户查询当前是地址簿线索，不等同于完整 CRM 主档；重要操作仍需进入后台核对。
- `integration-status` 只返回 webhook 白名单摘要，不返回原始 payload、details 或完整错误上下文。
- `/ready` 会暴露 `wecom_bot_plugin_api_key_configured` 布尔值，用于检查后端是否已配置插件密钥，不暴露密钥内容。

## 生产验证命令

```powershell
python scripts/check_wecom_intelligent_bot_contract.py --json --output reports/wecom-intelligent-bot-contract-{timestamp}.json
python scripts/check_wecom_employee_agent_plans.py --json --output reports/wecom-employee-agent-plans-{timestamp}.json
python scripts/wecom_intelligent_bot_smoke.py --json --base-url https://yunxifood.cn --output reports/wecom-intelligent-bot-smoke-{timestamp}.json
python scripts/check_wecom_employee_agent_callback.py --json --base-url https://yunxifood.cn --output reports/wecom-employee-agent-callback-{timestamp}.json
python -m pytest tests/api/test_wecom_intelligent_bot_plugin_api.py tests/scripts/test_wecom_intelligent_bot_smoke.py tests/scripts/test_check_wecom_intelligent_bot_contract.py tests/scripts/test_check_wecom_employee_agent_plans.py tests/scripts/test_check_wecom_employee_agent_callback.py -q --no-cov
```

报告不记录 `X-Yunxi-Bot-Key`、`Authorization`、`WECOM_BOT_PLUGIN_API_KEY`、企微回调 Token、EncodingAESKey、密文或签名的真实值。`check_wecom_employee_agent_plans.py` 不访问生产服务和数据库，只检查 13 个员工自由问法是否能生成预期 `AgentPlan`，并确认订单查询计划不会带上“多少 / 还有 / 哪个商品”等无意义关键词。`check_wecom_employee_agent_callback.py` 会真实打生产回调 URL，校验加密 POST、回复签名、`stream` 内容非空、隐私泄漏模式和按问法定义的语义规则。

## 员工验收样例

| 工具 | 可用问法 | 验收信号 |
|---|---|---|
| `order-lookup` | “帮我查张三的订单” | 返回订单摘要，手机号只显示脱敏值 |
| `product-lookup` | “草莓蛋糕还有库存吗” | 返回价格、库存、分类；无具体匹配时不返回无关商品 |
| `knowledge-answer` | “配送范围怎么说” | 返回知识库答案和来源摘要 |
| `customer-lookup` | “查一下张三地址线索” | 返回地址预览，不返回完整地址 |
| `group-campaign-summary` | “汇总这个 campaignId” | 返回群活动商品数量和待跟进脱敏列表 |
| `handoff-pending` | “现在有哪些待人工” | 返回工单 ID 和原因，不返回完整会话 |
| `ops-summary` | “现在系统值守状态” | 返回观察台状态和计数 |
| `integration-status` | “最近同步失败有哪些” | 返回失败摘要，不返回 raw payload |
| `offline-review-summary` | “昨晚离线复盘结果” | 返回最近一轮复盘统计或跳过原因 |

## 仍需人工确认

- 在企微后台逐个创建并发布工具。
- 确认哪些员工或群可以使用订单、客户地址、排障和离线复盘工具。
- 提供一个真实有效的 `campaignId` 做客户群汇总正向验收；默认 smoke 使用不存在的批次验证业务未命中路径。
- 用企微客户端保留不含密钥的测试截图或记录。
