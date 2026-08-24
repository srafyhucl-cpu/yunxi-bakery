# 小程序 Bearer 鉴权闭环设计

- 状态：已批准，P0 鉴权切片实现完成；DevTools 运行时证据 blocked
- trace_id：`20260805-storefront-auth-contract`
- 来源：2026-08-05 全局风险复盘，P0 小程序登录契约断裂
- 范围：`YunxiBakeBot` 与 `YunxiBakeMiniApp` 的小程序前台鉴权、测试、发布 smoke 和当前接口文档

## 目标与边界

本切片让小程序在安全默认配置
`STOREFRONT_AUTH_ALLOW_LEGACY_HEADER=false` 下完成以下闭环：

```text
wx.login
-> POST /api/v1/miniapp/auth/login
-> 持久化服务端签发的 Bearer token
-> Authorization: Bearer <token>
-> 访问订单、地址、聊天、隐私和客户群登记等受保护接口
```

收到未授权响应后，客户端必须丢弃失效会话、重新执行一次微信登录并仅重试原请求一次。重试失败应把明确的未登录错误交给页面处理，不得无限重试。

本切片不新增 refresh-token API，不更改 JWT 载荷、有效期或外部
`/api/v1/miniapp/*` 路径，不删除后端保留的 legacy 兼容开关，也不包含支付取消、库存一致性、客户订单归属或会员数据改造。

## 方案比较

### 方案 A：Bearer-only 小程序客户端，legacy 仅保留为后端显式迁移开关

小程序只发送 `Authorization: Bearer <accessToken>`。生产默认关闭 legacy
身份头；测试默认同样关闭，再由少数兼容测试显式开启。401 时进行一次受控续登。

优点是生产、小程序和测试的安全口径一致，旧头无法继续掩盖 token 回归。缺点是需要迁移现有五个仍使用 legacy 头的小程序 API 测试文件。

### 方案 B：小程序同时发送 Bearer 和 legacy 身份头

迁移期看似兼容，但任一 token 持久化或注入回归都会被 legacy 头掩盖。它不能证明安全默认配置可用，因此不采用。

### 方案 C：由业务请求体继续携带用户 ID

这会重新把客户端声明当作身份事实，与服务端签发会话的设计冲突，也会扩大越权面，不采用。

采用方案 A。

## 小程序设计

### 会话模型和存储

`MiniappSession` 扩展以下字段：

- `accessToken`：服务端签发的访问令牌。
- `tokenType`：当前契约固定为 `Bearer`。
- `expiresIn`：后端返回的有效秒数。
- `expiresAt`：客户端在收到响应时用 `expiresIn` 计算的绝对过期时间。

会话读写、判断、清理迁移至聚焦的 session store。旧存储对象没有完整 token 字段时视为未登录；清理时同时移除 `miniappSession` 与历史 `miniappUserId`，不得把 token 写入页面数据、日志或 smoke 报告。

会话在过期前 60 秒视为不可用，避免临界时刻的请求使用已过期 JWT。客户端时钟误差或服务端提前失效仍由后续 401 续登路径兜底。

### 无循环依赖的请求路径

现有 `auth.ts` 与 `http.ts` 已相互引用。自动续登若继续依赖该循环，初始化次序会变成运行时风险。

因此新增一个只负责 `wx.request` Promise 封装、状态码与错误解析的无认证传输模块：

```text
auth.ts -> transport.ts
http.ts -> transport.ts + auth.ts + session store
```

`auth.ts` 用无认证传输调用登录接口并维护单一 in-flight 登录 Promise，多个并发 401 只会触发一次 `wx.login`。`http.ts` 从 session store 获取有效 token 后注入标准 Authorization 头，不再发送 `x-miniapp-user-id`。

### 401 续登和重试规则

1. 登录接口与明确标记为不需要认证的请求不会触发自动续登。
2. 普通请求首次收到 401 时，只在当前存储 token 与本次请求快照一致时清理会话，避免旧请求清掉已续登的新会话。
3. 调用强制刷新登录，获取新 token 后以新 Authorization 头重发原请求一次。
4. 第二次 401、登录失败或网络失败直接返回 `ApiError`，页面沿用现有错误展示和登录态刷新逻辑。

## 后端、测试和文档设计

后端运行时代码已经具备 JWT 签发和 Bearer 校验，本切片不改变其身份语义。测试必须调整为生产安全默认：

1. `tests/conftest.py` 不再默认启用 `STOREFRONT_AUTH_ALLOW_LEGACY_HEADER`。
2. 新增 helper 统一签发测试 Bearer token，迁移当前五个使用
   `x-miniapp-user-id` 的小程序 API 测试文件。
3. 新增路由级合同测试：模拟微信 session 交换，调用登录接口得到 token，在 legacy 关闭时访问真实受保护订单接口成功；没有 Bearer token 或只传 legacy 头时返回 401。
4. 更新 `docs/architecture/platform-miniapp-api-contract-v1.md` 和当前领域迁移清单：Bearer 是正式身份来源，legacy 头只在显式配置时用于过渡。历史 evidence/index 保留原始历史描述，不回写。

## 发布 smoke 与门禁

现有 MiniApp DevTools service smoke 直接发送 `x-miniapp-user-id`，它本身会绕开客户端实际鉴权路径。改造后它应：

1. 在 DevTools runtime 调用真实 `wx.login`。
2. 调用线上或显式配置的 `/api/v1/miniapp/auth/login`。
3. 校验响应的 `accessToken`、`tokenType` 和 `expiresIn`。
4. 仅携带 Bearer token 访问订单、地址和聊天等只读受保护接口。
5. 报告只保留状态码、接口名、token 是否存在和脱敏摘要；不得落 token、openid、userId、订单内容或地址。

`npm run check:miniapp` 扩展静态契约检查，覆盖 token 字段、持久化、Bearer 注入、legacy 头禁用和 401 单次续登。后端 pytest 覆盖服务端真实路由合同。发布时，DevTools smoke 是 L5 运行时证据；无已授权 DevTools 或微信合法域名条件时必须明确标记为未执行，不得以静态检查替代。

## 验收标准

- 安全默认配置下，小程序登录响应中的 token 被完整存储并用于受保护请求。
- MiniApp 运行时代码不再发送 `x-miniapp-user-id`。
- 过期、撤销或无效 token 导致的首次 401 最多触发一次重新登录和一次请求重放。
- 后端合同测试在 legacy 关闭时验证“登录到受保护接口”的完整路径，并拒绝 legacy-only 请求。
- MiniApp 静态门禁、类型检查和 DevTools release smoke 都覆盖新协议；smoke 报告不泄露凭证或客户数据。
- 当前接口文档不再将 legacy 头描述为正式身份方案。

## 验证矩阵和剩余风险

最低验证包括目标 pytest、`npm run typecheck`、`npm run check:miniapp`、
`npm run check:page-api-coverage`、`git diff --check`、文档链接与关键词检查。加强验证包括相关后端 API 测试集、DevTools 真实运行 smoke、`python scripts/check_project.py` 和两仓工作区复核。

真实微信 code 与微信合法域名由已授权测试账号和 DevTools 提供，不能在纯后端单元测试中伪造为生产证据。支付取消与库存原子性仍为独立 P0，必须在本切片完成后进入下一份设计与实施计划。
