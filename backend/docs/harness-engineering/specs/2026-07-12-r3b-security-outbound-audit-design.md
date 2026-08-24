# R3-B 安全出站聚合审计设计

> trace_id: `20260711-global-risk-remediation`
> 约束来源: 全局风险整改计划 R3-B、ADR 0005

## 目标

关闭远程图片下载和企微员工授权的生产出站缺口，确保所有任意 URL 下载都经过同一 SSRF 策略，所有员工工具调用都由服务端身份和权限配置控制。

## 远程下载单一路径

- 商品目录图片代理和微信客服商品卡片统一调用 `fetch_limited_remote_image`。
- 底层使用 `httpx.AsyncClient.stream()`，禁用自动重定向；每一跳重新执行 scheme、host allowlist 和 DNS 地址检查。
- 声明长度和实际流式字节均受上限约束，响应 MIME 必须为 `image/*`。
- 客服卡片模块不得访问客户端私有 HTTP transport，日志不得记录带 query 的原始 URL。

## 员工授权单一路径

- callback 入口始终构造 `EmployeeActorAuthorizer`，按服务端 user/corp 校验 actor。
- `chattype=group` 时必须配置并命中 chat allowlist；单聊不要求虚构 chat ID。
- 运营权限由 `WECOM_EMPLOYEE_OPS_USERS` 服务端用户白名单决定，不信任回调 payload 中的 `role`。
- Dispatcher 把当前 actor 的允许工具集合传入 LangGraph state；节点在工具执行前阻断未授权工具，禁止 Agent 模式绕过角色检查。

## 聚合门禁

`scripts/check_security_outbound_contract.py` 默认做无网络静态合同检查并接入 `check_project.py`。生产模式通过 SSH 只回传 auth、allowlist 和 host 的布尔/计数，不回传员工、群、企业或域名内容。

## 验收

- 下载与员工授权定向套件通过，覆盖逐跳重定向、私网、MIME、声明大小、实际大小、客服降级、actor scope 和 Agent 未授权工具不执行。
- 生产 auth required、员工用户、企业 ID、ops 用户和远程图片 host 全部配置就绪。
- 聚合生产门禁通过，报告不含 allowlist 值、密钥或业务数据。
