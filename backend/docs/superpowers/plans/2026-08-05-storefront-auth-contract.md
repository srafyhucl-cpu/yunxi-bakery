# 小程序 Bearer 鉴权闭环实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use inline execution with task-by-task checkpoints. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 `YunxiBakeMiniApp` 在 Bot 的安全默认配置下完成微信登录、Bearer token 持久化、受保护请求、401 单次续登重试和发布 smoke 闭环。

**Architecture:** Bot 保持现有 JWT 签发与 Bearer 校验语义；测试默认关闭 legacy 身份头并使用真实签发 token。MiniApp 将无认证的 `wx.request` 传输抽到独立模块，`auth.ts` 只负责微信登录和会话生命周期，`http.ts` 负责 Bearer 注入、401 续登与单次重试，避免循环依赖。

**Tech Stack:** Python 3.13、FastAPI、pytest、httpx、TypeScript、微信小程序 `wx.login` / `wx.request`、Node.js 静态合同脚本、`miniprogram-automator` DevTools smoke。

## Global Constraints

- 保持外部路径 `/api/v1/miniapp/*` 不变。
- MiniApp 运行时只发送 `Authorization: Bearer <accessToken>`，不发送 `x-miniapp-user-id`。
- 保持 `STOREFRONT_AUTH_ALLOW_LEGACY_HEADER=false` 为生产默认；legacy 头只允许显式迁移测试使用。
- 不新增 refresh-token API，不修改 JWT 载荷、支付逻辑、数据库 schema 或订单业务状态。
- Python 代码遵守 `api -> service -> repository -> models`，SQL 必须参数化且禁止 `SELECT *`。
- 新增或修改代码注释使用中文；不添加占位注释、`print()`、硬编码密钥或硬编码生产凭证。
- 不使用批量删除或递归删除命令；不把下载物、缓存、构建产物写入 C 盘。
- DevTools smoke 报告不得写入 access token、openid、userId、订单内容、地址或聊天原文。

---

## File Map

Bot 仓：`tests/conftest.py`、`tests/helpers/storefront_auth.py`、`tests/api/test_miniapp_storefront_auth_contract.py`、现有五个小程序 API 测试、`test_customer_group_api.py`、两个当前 MiniApp 架构文档、`LOGBOOK.md` 和 `项目进度与配置清单.md`。

MiniApp 仓：`miniprogram/types/index.d.ts`、`miniprogram/services/session-store.ts`、`miniprogram/services/transport.ts`、`miniprogram/services/auth.ts`、`miniprogram/services/http.ts`、`miniprogram/utils/session.ts`、`app.ts`、`scripts/check-miniapp.mjs`、`scripts/check-devtools-service-smoke.mjs` 和 `docs/api-contract.md`。

## Task 1: 后端测试切换到安全默认并建立跨路由合同

**Files:**
- Modify: `D:\Project\YunxiBakeBot\tests\conftest.py`
- Create: `D:\Project\YunxiBakeBot\tests\helpers\storefront_auth.py`
- Create: `D:\Project\YunxiBakeBot\tests\api\test_miniapp_storefront_auth_contract.py`
- Modify: `D:\Project\YunxiBakeBot\tests\api\test_miniapp_auth_api.py`
- Modify: `D:\Project\YunxiBakeBot\tests\api\test_miniapp_address_api.py`
- Modify: `D:\Project\YunxiBakeBot\tests\api\test_miniapp_chat_api.py`
- Modify: `D:\Project\YunxiBakeBot\tests\api\test_miniapp_order_api.py`
- Modify: `D:\Project\YunxiBakeBot\tests\api\test_miniapp_privacy_api.py`
- Modify: `D:\Project\YunxiBakeBot\tests\api\test_customer_group_api.py`

**Interfaces:** `storefront_auth_headers(user_id: str) -> dict[str, str]` 统一签发测试 Bearer 头；合同测试复用 `StorefrontAuthService.issue_access_token()`、`create_miniapp_auth_router()` 和 `create_miniapp_orders_router()`。

- [x] **Step 1: 写 helper 和合同测试。** Helper 必须签发 token 并返回以下结构：

```python
from app.service.channels.storefront.auth import StorefrontAuthService


def storefront_auth_headers(user_id: str) -> dict[str, str]:
    token = StorefrontAuthService().issue_access_token(user_id)
    return {"Authorization": f"Bearer {token}"}
```

合同测试模拟 `_request_wechat_session()` 返回固定 openid，调用登录后访问真实 `GET /api/v1/miniapp/orders`；无 header 和只有 `x-miniapp-user-id` 均断言 `401`。
- [x] **Step 2: 先运行合同测试。** Run: `python -m pytest tests/api/test_miniapp_storefront_auth_contract.py -q --no-cov`。Expected: 当前实现或测试 fixture 未完成时失败，锁定目标。
- [x] **Step 3: 关闭测试默认 legacy。** 将 `tests/conftest.py` 的 `STOREFRONT_AUTH_ALLOW_LEGACY_HEADER` 默认值从 `"1"` 改为 `"0"`。
- [x] **Step 4: 迁移请求头。** 把五个小程序 API 测试文件和客户群测试中的 `x-miniapp-user-id` 替换为 `storefront_auth_headers("...")`，保留 user id 用于资源归属断言。
- [x] **Step 5: 运行目标测试。** Run: `python -m pytest tests/api/test_miniapp_auth_api.py tests/api/test_miniapp_storefront_auth_contract.py tests/api/test_miniapp_address_api.py tests/api/test_miniapp_chat_api.py tests/api/test_miniapp_order_api.py tests/api/test_miniapp_privacy_api.py tests/api/test_customer_group_api.py -q --no-cov`。Expected: 全部通过，Bearer-only 合同和 legacy-only `401` 成立。

## Task 2: 拆出 MiniApp 无认证传输层和统一会话模型

**Files:**
- Create: `D:\Project\YunxiBakeMiniApp\miniprogram\services\transport.ts`
- Create: `D:\Project\YunxiBakeMiniApp\miniprogram\services\session-store.ts`
- Modify: `D:\Project\YunxiBakeMiniApp\miniprogram\types\index.d.ts`

**Interfaces:** `sendTransportRequest<TData, TBody>(options): Promise<TransportResponse<TData>>` 只封装 `wx.request`；session store 提供 `getMiniappSession()`、`persistSession()`、`clearMiniappSession()`、`clearMiniappSessionIfToken()`、`isUsableMiniappSession()` 和 `buildAnonymousSession()`。

- [x] **Step 1: 扩展会话类型。** `MiniappSession` 增加 `accessToken`、`tokenType`、`expiresIn`、`expiresAt`；匿名和 demo 会话使用空 token、`Bearer`、`0`、`0`。
- [x] **Step 2: 实现过期判断。** 定义 `SESSION_EXPIRY_SKEW_MS = 60_000`；可用会话必须满足真实 session、userId、非 demo、Bearer token，且 `expiresAt - Date.now()` 大于该窗口。旧对象缺少 token 元数据时返回匿名会话。
- [x] **Step 3: 实现清理竞态保护。** 清理同时移除 `miniappSession` 与历史 `miniappUserId`；`clearMiniappSessionIfToken(token)` 仅在当前 token 相等时清理。
- [x] **Step 4: 抽出 `wx.request`。** `transport.ts` 负责 JSON content type、`REQUEST_TIMEOUT_MS=12000`、HTTP 状态和网络错误；不得导入 `auth.ts` 或读取 storage。
- [x] **Step 5: 验证。** Run from `D:\Project\YunxiBakeMiniApp`: `npm run typecheck`。Expected: 迁移期间字段错误全部在后续任务清零，不提交半迁移状态。

## Task 3: 实现微信登录、token 持久化和并发单飞

**Files:**
- Modify: `D:\Project\YunxiBakeMiniApp\miniprogram\services\auth.ts`
- Modify: `D:\Project\YunxiBakeMiniApp\miniprogram\app.ts`

**Interfaces:** 保持 `ensureMiniappSession(options?: { forceRefresh?: boolean }): Promise<MiniappSession>` 和 `persistDemoMiniappSession(): MiniappSession`；auth 只能通过 `transport.ts` 调登录 API。

- [x] **Step 1: 校验登录响应。** 必须校验 userId、openid、sessionReady、isDemo、accessToken、`tokenType=Bearer` 和正数 expiresIn；失败不得持久化半成品会话。
- [x] **Step 2: 实现 `performMiniappLogin()`。** 用 `wx.login` 获取 code，POST `/api/v1/miniapp/auth/login`，计算 `expiresAt = Date.now() + expiresIn * 1000`，再调用 `persistSession()`；失败保留匿名会话，不创建 demo 会话。
- [x] **Step 3: 实现单飞登录。** 使用 `let activeLoginPromise: Promise<MiniappSession> | null = null`；有效会话直接复用，并发登录复用同一个 Promise，结束时在 `finally` 清空。
- [x] **Step 4: 修改 `app.ts`。** 登录失败时调用 `getMiniappSession()`，不再手写缺 token 字段的旧结构。
- [x] **Step 5: 验证。** Run: `npm run typecheck`。Expected: `tsc --noEmit` 通过。

## Task 4: 实现 Bearer 注入和 401 单次续登重试

**Files:**
- Modify: `D:\Project\YunxiBakeMiniApp\miniprogram\services\http.ts`

**Interfaces:** 保持 `request<TData, TBody>(options): Promise<TData>`；内部增加 `retryOnUnauthorized?: boolean`，默认 true，重放请求时固定 false。

- [x] **Step 1: 实现唯一 header 构造。** 只有可用会话才加入 `Authorization`，值为 `${session.tokenType} ${session.accessToken}`；不得保留 `x-miniapp-user-id`。
- [x] **Step 2: 保持错误语义。** 非 2xx 继续转换为 `ApiError`，使用 `detail` / `message`；transport 只返回 HTTP 状态。
- [x] **Step 3: 实现有界 401。** 首次 401 保存 token 快照，调用 `clearMiniappSessionIfToken(snapshot)`，执行 `ensureMiniappSession({ forceRefresh: true })`，再以新 Bearer 头重发一次；第二次 401 或续登失败直接抛出，不递归重试。
- [x] **Step 4: 验证。** Run: `npm run typecheck`、`npm run check:miniapp`、`npm run check:page-api-coverage`。Expected: 全部通过。

## Task 5: 加强静态契约和 DevTools release smoke

**Files:**
- Modify: `D:\Project\YunxiBakeMiniApp\scripts\check-miniapp.mjs`
- Modify: `D:\Project\YunxiBakeMiniApp\scripts\check-devtools-service-smoke.mjs`

**Interfaces:** 保持 `npm run check:miniapp` 和 `npm run devtools:service-smoke` 命令入口不变；smoke 报告只输出脱敏摘要。

- [x] **Step 1: 更新静态检查路径。** timeout 检查移到 `services/transport.ts`；http 检查 Authorization Bearer、401 分支、`forceRefresh` 和单次重试标记。
- [x] **Step 2: 增加静态失败条件。** 缺 token 字段、transport 分离失败、runtime 出现 `x-miniapp-user-id`、auth 通过 http 调自己、或缺少 401 有界重试时必须失败；保留 demo session 检查。
- [x] **Step 3: 改造 DevTools smoke。** 在 `evaluate()` 中真实调用 `wx.login`，POST auth login，校验 token 字段，再只携带 Bearer 访问订单、地址、聊天只读接口。
- [x] **Step 4: 脱敏报告。** 只允许接口名、HTTP 状态、业务 code、响应结构摘要、`hasAccessToken`、`tokenType`、`expiresIn` 和整体状态；不得落 accessToken、openid、userId、订单内容、地址或聊天文本。
- [x] **Step 5: 验证。** Run: `npm run check:miniapp`、`npm run typecheck`、`npm run check:page-api-coverage`，然后执行 `rg -n "x-miniapp-user-id" miniprogram scripts/check-devtools-service-smoke.mjs`。Expected: 前三个通过，最后一条零输出。

## Task 6: 更新当前接口文档并记录实施状态

**Files:**
- Modify: `D:\Project\YunxiBakeBot\docs\architecture\platform-miniapp-api-contract-v1.md`
- Modify: `D:\Project\YunxiBakeBot\docs\architecture\platform-domain-migration-inventory.md`
- Modify: `D:\Project\YunxiBakeBot\LOGBOOK.md`
- Modify: `D:\Project\YunxiBakeBot\项目进度与配置清单.md`
- Modify: `D:\Project\YunxiBakeMiniApp\docs/api-contract.md`

- [x] **Step 1: 更新正式契约。** 将“用户隔离头”改为 Bearer 会话，说明身份来自 JWT `sub`；补充缺 token、过期 token 的 401 与身份不一致的 403。
- [x] **Step 2: 更新迁移盘点。** 把 `x-miniapp-user-id` 标为仅在 `STOREFRONT_AUTH_ALLOW_LEGACY_HEADER=true` 时可用的历史兼容头，保留路径和数据库历史命名。
- [x] **Step 3: 写入追溯摘要。** LOGBOOK 记录 trace `20260805-storefront-auth-contract`、changed files、测试结果、MiniApp 门禁、DevTools 条件和剩余风险；同步进度清单。
- [x] **Step 4: 验证文档。** Run: `python scripts/check_logbook.py`、`git diff --check`，并用 `Select-String` 检查两个当前架构文档中的 `Authorization`、`Bearer`、`legacy` 和 `x-miniapp-user-id`。

## Task 7: 双仓完整验证和生产级收口

**Files:** Verify Tasks 1-6 的明确变更文件；仅在需要时生成 `D:\Project\YunxiBakeBot\reports\harness\` 下的证据文件。

- [x] **Step 1: 后端目标测试。** Run: `python -m pytest tests/api/test_miniapp_auth_api.py tests/api/test_miniapp_storefront_auth_contract.py tests/api/test_miniapp_address_api.py tests/api/test_miniapp_chat_api.py tests/api/test_miniapp_order_api.py tests/api/test_miniapp_privacy_api.py tests/api/test_customer_group_api.py -q --no-cov`。Expected: login -> Bearer -> protected、missing token、legacy-only、invalid token 全覆盖并通过。
- [x] **Step 2: 后端质量和 Harness。** Run `python scripts/check_project.py --skip-tests`、`python scripts/check_mistake_ledger.py`、`python scripts/check_evidence_index.py --summary`。
- [x] **Step 3: MiniApp 门禁。** Run `npm run typecheck`、`npm run check:miniapp`、`npm run check:page-api-coverage`、`npm run check:observability-contract`。
- [x] **Step 4: 条件允许时运行 `npm run devtools:service-smoke`。** 当前未具备已连接 DevTools、测试微信账号和合法域名条件，已明确记录 blocked；不安装工具、不伪造运行时证据。

实际结论（2026-08-10 补闭环）：操作者完成微信开发者工具登录（`islogin --port 48465` 返回 `{"login":true}`）后，在 automator 实例（`MINIAPP_AUTOMATOR_WS=ws://127.0.0.1:9421`）上运行 `npm run devtools:service-smoke` 通过：`DevTools storefront auth smoke pass: 4 checks`（`reports/button-runtime/devtools-service-smoke-20260810-090319.json`）。`wx.login` → 后端 login 返回 accessToken/tokenType/expiresIn，订单/地址/聊天受保护端点仅携带 `Authorization: Bearer` 全部 200 code=0。证据 `E-20260810-006`，报告不含 accessToken/openid/订单/地址/聊天原文。
- [x] **Step 5: 双仓审计。** Bot 使用 `rg -n "x-miniapp-user-id" app tests scripts docs --glob '!docs/harness-engineering/core/evidence-index.md'`；MiniApp 使用 `rg -n "x-miniapp-user-id" miniprogram scripts`。MiniApp runtime 和三个 DevTools 探针零命中；新增报告和日志不得出现 token、openid、userId。
- [x] **Step 6: 分仓提交。** 两仓均只暂存明确文件并完成独立提交：Bot 后端测试 `85764a7`，MiniApp `33fdd92`；不推送生产、不重启服务。

## Self-Review Checklist

- [x] 规格中的 token 字段、Bearer-only、单次 401 重试、无循环依赖、测试默认关闭 legacy、DevTools 脱敏报告和当前文档更新均有对应任务。
- [x] 计划没有新增 refresh-token API、数据库迁移或支付/订单业务改动。
- [x] `auth.ts` 使用 `transport.ts`，不存在 `auth.ts -> http.ts -> auth.ts` 循环。
- [x] `clearMiniappSessionIfToken()` 防止并发旧请求清理新会话。
- [x] 所有测试命令都指向现有或本计划明确新增的文件。
- [x] DevTools 授权、合法域名和真实微信 code 均作为外部条件记录；已登录后 DevTools service smoke 通过（2026-08-10，证据 `E-20260810-006`）。
