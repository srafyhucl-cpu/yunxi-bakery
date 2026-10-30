# 本地试点手册（Local Trial Runbook）

> 面向对象：新加入的同事，在一台 Windows 开发机上用**合成数据 + Mock 打印 + Mock 支付**跑通芸熙烘焙后台与小程序的主要操作。
>
> 本手册只覆盖「本地试点」。任何真实上线动作（真实有赞导出、真实微信支付商户号、真实打印机、真机与审核、对账与回滚）都不在本手册范围内，必须另做并取得项目负责人批准。

---

## 1. 目标与非目标

### 1.1 目标

在一台开发机上完成以下闭环，全部使用本地合成数据：

1. 后端服务启动，`/health`、`/ready`、`/docs` 可访问；
2. 管理后台（桌面 / 手机页面）可登录，能进 `/admin/daily-stock`、`/admin/print-jobs`、`/admin/quick-order`；
3. 微信开发者工具能打开小程序并连到本地 API；
4. 创建店员账号、导入 30 条 FAQ 种子、导入合成储值余额；
5. 打印队列走完 Mock 流程（`MOCKED`），人工确认后为 `PRINTED`；
6. 快捷开单走通「储值直扣」与「微信分享待付」两种支付方式。

### 1.2 非目标（试点红线）

| 红线 | 说明 |
|---|---|
| 不接触真实会员 | 只用 `1380000000x` 这类合成手机号与合成姓名 |
| 不接触真实支付 | `ALLOW_MOCK_PAYMENT=true`，不接微信支付商户号，不产生真实收款 |
| 不接触真实打印机 | `PRINT_PROVIDER=mock`，Mock 网关只记 `MOCKED`，绝不伪造 `PRINTED` |
| 不接触生产库 | 只读写本地 `backend/data/bot.db`；禁止把生产 `.env`、生产库文件拷到开发机 |
| 不接触真实第三方 | `YOUZAN_MOCK_MODE=true`、企业微信回调保持空配置，不调用真实有赞 / 企微接口 |
| 不做生产部署 | 本手册不涉及 `scripts/deploy.sh`、systemd、Nginx、生产服务器 |
| 真实上线需批准 | 真实用户开放、真实支付、真实有赞数据迁移都必须先经项目负责人书面批准 |

仓库红线（见根 `AGENTS.md`）：截至 2027-05-31（含）小程序仅用于开发、调试和测试，不向真实用户开放；**编译通过、跑通本地流程都不等于已经向真实用户上线**。

---

## 2. 前置条件

| 依赖 | 版本 | 校验命令 |
|---|---|---|
| Python | 3.11+ | `python --version` |
| Node.js | 18+ | `node --version` |
| 微信开发者工具 | 稳定版 | 安装后能导入项目目录 |
| 磁盘 | C 盘建议留 5 GB+ | 依赖与 SQLite 都在本地 |

不需要：有赞账号、微信小程序 AppID/Secret、微信支付商户号、实体打印机、Redis。

---

## 3. 一键初始化

在**仓库根目录**执行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup.ps1
```

脚本行为（幂等，可重复执行）：

1. 检查 Python（找不到 `python` 时回退 `py -3`）；
2. 创建 `backend/data`（本地 SQLite 与向量索引目录）；
3. 创建 `backend/.venv` 并安装 `requirements.txt` + `requirements-dev.txt`；
4. 若 `backend/.env` **不存在**：复制 `backend/.env.example`，并自动写入 4 个随机密钥
   （`ADMIN_API_TOKEN`、`ADMIN_SESSION_SECRET`、`STAFF_SESSION_SECRET`、`STOREFRONT_AUTH_SECRET`），
   **脚本不打印密钥明文**；
   若 `backend/.env` **已存在**：不覆盖，只提示哪些密钥还没配置；
5. 安装 `miniapp` 依赖（`npm install`）；
6. 安装 `backend/web/admin` 依赖（有 `package-lock.json` 时用 `npm ci`，否则 `npm install`）；
7. 打印后续全部命令（后端启动、管理后台、小程序、店员创建、FAQ 导入、储值导入）。

> 脚本只准备本地环境：**不执行生产部署、不连接生产库、不写入任何真实数据**。

查看生成的密钥（管理员登录要用）：

```powershell
Get-Content backend\.env | Select-String '^ADMIN_API_TOKEN='
```

---

## 4. 启动后端

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --host 127.0.0.1 --port 7001 --reload
```

### 4.1 健康检查 `/health`

```powershell
Invoke-RestMethod http://127.0.0.1:7001/health
# {"status":"ok","version":"<backend/VERSION 的值>"}
```

### 4.2 就绪检查 `/ready`

```powershell
try { Invoke-RestMethod http://127.0.0.1:7001/ready } catch { "HTTP " + $_.Exception.Response.StatusCode.value__ }
```

**本地返回 503（`status=degraded`）属预期**。`/ready` 是按**生产口径**评估的就绪门禁，要求真实有赞凭据、企微凭据、微信支付商户号、向量索引、生产构建产物，并且 `mock_payment_disabled=true`；本地试点这些条件都不满足。
**本地存活判据一律用 `/health`**，不要用 `/ready` 判活。

### 4.3 接口文档 `/docs`

本地 `.env` 里 `ENABLE_API_DOCS=true`，因此 Swagger 可用：

- Swagger UI：http://127.0.0.1:7001/docs
- ReDoc：http://127.0.0.1:7001/redoc

> 生产必须把 `ENABLE_API_DOCS` 置回 `false`。

---

## 5. 管理后台（桌面 + 手机页面）

### 5.1 开发模式

```powershell
cd backend\web\admin
npm run dev
```

- 访问：http://127.0.0.1:5173/admin/
- 路由基准来自 `backend/web/admin/.env.development`（`VITE_ROUTER_BASE=/admin/`）
- `/api` 由 Vite 代理转发到 `http://127.0.0.1:7001`

登录页要求输入**管理员 Token**，即 `backend/.env` 里的 `ADMIN_API_TOKEN`。

### 5.2 生产构建（可选，本地验证用）

```powershell
cd backend\web\admin
npm run build
```

构建产物在 `backend/web/admin/dist`，后端会直接挂载：

- http://127.0.0.1:7001/admin/

### 5.3 试点要看的页面

| 页面 | 用途 |
|---|---|
| `/admin/` | 后台首页（概览） |
| `/admin/daily-stock` | 每日现烤库存录入（下单前置条件） |
| `/admin/print-jobs` | 打印队列：看 `MOCKED`、人工「确认出纸」、补打 |
| `/admin/quick-order` | 店员快捷开单（储值直扣 / 微信分享待付） |

> 手机页面：后台内置移动端导航（底部标签栏，见 `src/constants/adminNavigation.ts` 的 `mobilePrimary`），
> 把浏览器窗口缩到手机宽度即可看到移动布局；也可用手机浏览器访问
> `http://<本机局域网 IP>:5173/admin/`（仅限公司内网试用，勿暴露到公网）。

---

## 6. 小程序（微信开发者工具）

1. 打开「微信开发者工具」→ 导入项目 → 目录选择仓库里的 `miniapp/`；
2. 详情 → 本地设置 → 勾选「不校验合法域名…」（本地 `http://127.0.0.1:7001` 需要）；
3. API 地址逻辑在 `miniapp/miniprogram/services/config.ts`：
   - 开发版（`develop`）默认连 `http://127.0.0.1:7001`；
   - 体验版 / 正式版连 `https://yunxifood.cn`，**试点阶段不要切体验版**；
   - 需要强制本地时，可在开发者工具控制台执行
     `wx.setStorageSync('yunxiUseLocalApi', true)`。

### 6.1 没有微信 AppID / Secret 会怎样

- `WECHAT_MINIAPP_APP_ID` / `WECHAT_MINIAPP_APP_SECRET` 留空时，`wx.login` 换不了会话，
  后端 `POST /api/v1/miniapp/auth/login` 返回 400「微信小程序 AppID/Secret 未配置，无法换取真实会话」，
  小程序首页的登录 / 会员相关操作会失败；
- 这不影响本手册其余步骤（后台、店员、FAQ、储值、打印、快捷开单都不依赖真实微信登录）；
- 若要跑通小程序登录：填自己的**测试号** AppID/Secret 到本地 `backend/.env`（不要提交回仓库），
  体验版与真机验收仍需负责人批准。

### 6.2 会员「认领」是本地打通会员的唯一办法

`backend/tests/fixtures/youzan_stored_value_synthetic.csv` 导入后只有**手机号身份**，
没有小程序 openid 身份；店员快捷开单查会员时要求会员已绑定小程序 openid，否则报「会员尚未绑定小程序」。

本地用合成 openid 认领（不涉及任何真实微信用户）：

```powershell
$body = '{"phone":"13800000002","userId":"wx_local_trial_openid_001"}'
Invoke-RestMethod http://127.0.0.1:7001/api/v1/miniapp/auth/claim -Method Post -ContentType "application/json" -Body $body
```

成功后返回 `isMember=true` 与储值余额，`staff_session` 登录后即可查到该会员。

---

## 7. 店员账号

```powershell
# 仓库根目录执行；PIN 交互输入两次，不回显
backend\.venv\Scripts\python.exe backend\scripts\manage_staff.py create --name 店员A --phone 13800000001 --role cashier
```

- 角色：`cashier`（店员）/ `manager`（店长）；
- 手机号必须是 11 位、1 开头；**只用合成手机号**；
- 试点为了自动化可以用 `--pin 1234` 直接指定 PIN（生产必须交互输入）；
- 其他子命令：`list`（列出启用账号）、`disable --phone <手机号>`、`reset-pin --phone <手机号>`。

### 7.1 店员登录已修复：不再需要本地签发 JWT 绕过

原先店员登录 500（`sqlite3.OperationalError: database is locked`）是业务代码的并发缺陷：
登录成功后在同一次请求里写「最后登录时间 + 登录审计」，此时请求连接还没提交、一直占着
SQLite 写锁；紧接着的登录失败计数清理又用**另一条连接**写同一个库文件，
两条连接互等到 `busy_timeout` 耗尽就报 `database is locked`，登录接口退化成 500。

**该缺陷已修复**：登录状态与登录审计会先提交落库（释放写锁），再清理限流计数。
现在 `POST /api/v1/staff/auth/login` 登录成功直接返回 200 并下发 `staff_session` Cookie，
**不再需要本地签发 JWT 绕过**。

如果本地仍然遇到 500 且日志是 `database is locked`，按下面几项排查（这些都是环境与并发问题）：

| 检查项 | 怎么看 | 处理 |
|---|---|---|
| 是否有多个后端进程同时写同一个库文件 | `Get-Process python` 确认只有一个 uvicorn | 只保留一个进程；SQLite 库文件同一时刻只允许一个写者 |
| 库文件是否被别的工具长期占用 | 关闭 DB Browser、导入脚本等正连着 `backend/data/bot.db` 的工具 | 关掉占用方再重试 |
| `busy_timeout` 是否被改小 | `backend/app/migrations/schema.py` 的 `PRAGMA_STATEMENTS` | 保持 5000 毫秒，不要改成 0 |
| 单个请求是否长时间持有写事务 | 后端日志按请求时间对齐，定位长事务请求 | 避免在一次请求里串行做多次大写入 |

> 定位口诀：SQLite 的写锁是**库文件级**的，一条连接只要还有未提交事务就一直占着写锁。
> 本地试点只有一个后端进程、也没有别的工具写库时，不应再出现 `database is locked`。

---

## 8. 30 条 FAQ 种子导入

```powershell
# 干跑（只校验，不写库）
backend\.venv\Scripts\python.exe backend\scripts\seed_bakery_faq.py --dry-run

# 实际写入
backend\.venv\Scripts\python.exe backend\scripts\seed_bakery_faq.py --apply
```

- 夹具：`backend/tests/fixtures/bakery_faq_30.json`（只读，不访问有赞 API）；
- **首次 `--dry-run` 退出码是 1**，输出 `action=run the seed with --apply to initialize the target database`，
  因为本地库还没建表，属预期；
- `--apply` 会初始化 / 迁移本地库并写入 30 条，输出 `inserted_count=30`、退出码 0；
- 重复执行幂等：`skipped_count=30`，不会重复插入；
- 想留 JSON 报告：`--json --output reports/bakery-faq-{timestamp}.json`（目标已存在时拒绝覆盖）。

---

## 9. 合成储值余额导入

### 9.1 先看脏数据拦截（预期失败）

```powershell
backend\.venv\Scripts\python.exe backend\scripts\import_youzan_stored_value.py --source backend/tests/fixtures/youzan_stored_value_synthetic.csv --dry-run
```

这份合成夹具**故意包含 5 行脏数据**，实测输出：

```
total_rows=16
valid_rows=11
invalid_rows=5
status=failed
```

脏数据分别是：手机号只有 10 位、文件内手机号重复（2 行）、本金为负数、本金+赠送金与上报总额不一致。
因此 `--dry-run` 与 `--apply` **都会以退出码 1 结束**，`--apply` 报「批次未通过校验或存在冲突，拒绝入账」。
这正是要演示的效果：**有脏数据就整批拒绝入账**。

### 9.2 用干净数据跑通入账

```powershell
# 1) 造一份只含合法行的合成 CSV（放在临时目录，不入库）
@"
mobile,display_name,principal_fen,bonus_fen,reported_total_fen,yz_open_id,card_no,card_alias
13800000002,李四,20000,2000,22000,o_ysv_002,CARD002,金卡
13800000009,赵六,30000,3000,33000,o_ysv_009,CARD009,黑卡
13800000011,孙八,12000,0,12000,o_ysv_011,,银卡
"@ | Set-Content -Encoding UTF8 "$env:TEMP\yunxi-stored-value-clean.csv"

# 2) 干跑
backend\.venv\Scripts\python.exe backend\scripts\import_youzan_stored_value.py --source "$env:TEMP\yunxi-stored-value-clean.csv" --dry-run

# 3) 入账
backend\.venv\Scripts\python.exe backend\scripts\import_youzan_stored_value.py --source "$env:TEMP\yunxi-stored-value-clean.csv" --apply
```

- 干跑输出 `status=validated`、退出码 0；入账输出 `status=applied`、`applied_rows=3`、退出码 0；
- 入账后本地 `member_balance` 出现这 3 个会员（`is_member=1`），并自动创建**客户主档 + 手机号身份**；
- 入账语义是「期初导入」，只写本地账本，**不调用任何真实有赞 API**；
- 回滚（仅限导入后没有后续流水的干净批次）：
  `--rollback-batch <batch_id>`。

---

## 10. Mock 打印流程

链路：**订单支付成功 / 快捷开单储值直扣** → 打印调度（每 5 秒扫描已支付订单，幂等入队）
→ 打印 worker（每 2 秒消费 `PENDING`）→ Mock 网关 → 状态 `MOCKED`。

本地配置（`backend/.env`）：

```
PRINT_PROVIDER=mock
PRINT_DISPATCH_ENABLED=true
PRINT_DISPATCH_INTERVAL_SECONDS=5
PRINT_WORKER_ENABLED=true
PRINT_WORKER_INTERVAL_SECONDS=2
```

验证步骤：

1. 在 `/admin/quick-order` 完成一笔**储值直扣**（或第 11 节的 API 调用）；
2. 等待 5～10 秒；
3. 打开 `/admin/print-jobs`，能看到 `status = MOCKED`（页面标签「已 Mock」），`provider = mock`；
4. 也可以直接查接口（先登录后台拿会话 Cookie）：

```powershell
# 后台登录并保存会话
$admin = New-Object Microsoft.PowerShell.Commands.WebRequestSession
Invoke-RestMethod http://127.0.0.1:7001/api/v1/admin/auth/login -Method Post -ContentType "application/json" -Body '{"token":"<ADMIN_API_TOKEN>"}' -WebSession $admin
Invoke-RestMethod "http://127.0.0.1:7001/api/v1/admin/print-jobs?limit=10" -WebSession $admin
```

### 10.1 `MOCKED` 与 `PRINTED` 的区别

| 状态 | 含义 | 谁写入 |
|---|---|---|
| `MOCKED` | Mock 网关已受理，内容已生成，但**没有真正出纸** | Mock 打印网关自动写入 |
| `PRINTED` | **人工确认**确实出纸 | 只能由人在 `/admin/print-jobs` 点「确认出纸」，或真实打印机回调 |

系统在任何情况下都不会自动把作业写成 `PRINTED`（飞鹅网关成功也只到 `SUBMITTED`）。
试点时如果要演示 `PRINTED`，就在 `/admin/print-jobs` 手动点一次「确认出纸」。

### 10.2 补打

`/admin/print-jobs` 的「补打」会复制原小票内容新建一条待打印作业，不会改动原作业。

---

## 11. 快捷开单（储值直扣 / 微信分享待付）

前置条件全部满足才能开单：

1. 店员已登录（`/admin/quick-order` 用**店员手机号 + PIN** 登录，与管理员 Token 无关）；
2. 会员已在本地库中存在，且完成过**认领**（见 6.2），否则报「会员尚未绑定小程序」；
3. 当天的**每日库存**已录入（见第 12 节），否则报「商品今日未配置每日库存，请先在后台录入」；
4. `expectTime` 落在**营业时间内**（默认 09:00-19:30，北京时间）。
   快捷开单默认取「当前时间 + 30 分钟」，深夜或清晨会自动落到营业时间外并报「预约时间不在营业时间内」。

### 11.1 页面操作

`/admin/quick-order` → 店员登录 → 查会员（手机号）→ 选商品 → 选支付方式：

| 支付方式 | 后端 mode | 行为 |
|---|---|---|
| 储值直扣 | `stored_value_direct` | 建单 + 扣储值 + 置为已支付，返回回执与剩余余额 |
| 微信分享待付 | `wechat_share_card` | 只建待支付订单，返回分享路径 / 文案，由客户本人在小程序支付（门店不代付） |

### 11.2 等价的接口调用（便于脚本化演示）

```powershell
# 复用 /api/v1/staff/auth/login 拿到的 staff_session Cookie（见第 7 节）
$items = '[{"productId":"900001","quantity":2,"fulfillmentType":"DAILY_READY","customization":{}}]'
$body = '{"requestId":"trial-req-1001","mode":"stored_value_direct","phone":"13800000002","items":' + $items + ',"fulfillmentMethod":"pickup","expectTime":"2026-10-20 10:00"}'
Invoke-RestMethod http://127.0.0.1:7001/api/v1/staff/quick-order/create -Method Post -ContentType "application/json" -Body $body -WebSession $staffSession
```

实测返回：`orderId=mp_...`、`paymentStatus=paid`、`balanceFen` 为扣款后的剩余储值。

### 11.3 幂等与失败重试

- `requestId` 必须 8～64 位字母 / 数字 / 下划线 / 连字符；
- 同一个 `requestId` 重复提交会被幂等回放（不会重复扣款）；
- **上一次开单失败后必须换新的 `requestId`**，否则报「上次开单失败，请重新发起」（后台页面会自动换新）。

---

## 12. 每日库存

- 页面：`/admin/daily-stock`；
- 日常现烤（`DAILY_READY`）按「北京时间日期 + 商品」独立管理，**只写本地 `product_daily_stock`，不改有赞库存**；
- 定制蛋糕（`PREORDER_CAKE`）继续用 `youzan_products.stock`；
- **必须先录入当天数量**，否则下单报「商品今日未配置每日库存，请先在后台录入」。

接口（需后台会话）：

```powershell
# 查看
Invoke-RestMethod "http://127.0.0.1:7001/api/v1/admin/daily-stock" -WebSession $admin
# 录入
Invoke-RestMethod "http://127.0.0.1:7001/api/v1/admin/daily-stock/900001" -Method Put -ContentType "application/json" -Body '{"date":"2026-10-20","totalQty":20}' -WebSession $admin
```

> 本地商品目录来自 `youzan_products` 表；试点不连真实有赞，需要先造合成商品才能选到商品。
> 造数据只写本地库，且必须是合成商品（例如「全麦吐司（试点合成）」）。

---

## 13. 验证命令

```powershell
# 后端：核心业务定向测试（与 pre-commit 核心测试集一致）
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_health_ready.py backend/tests/test_config.py -q --tb=short --no-cov

# 后端：储值 / 订单 / 打印相关定向测试
backend\.venv\Scripts\python.exe -m pytest backend/tests/service/test_stored_value.py backend/tests/service/order backend/tests/scripts/test_import_youzan_stored_value.py -q --no-cov

# 管理后台：类型检查
cd backend\web\admin
npm run typecheck
npx vue-tsc --noEmit

# 小程序：类型检查 + 结构自检
cd miniapp
npm run typecheck
npm run check:miniapp
```

---

## 14. 常见问题

| 现象 | 原因 | 处理 |
|---|---|---|
| 后端启动即退出，日志「ADMIN_API_TOKEN 仍为默认值」 | `.env` 里 `ADMIN_API_TOKEN` 还是保留占位值 | 跑 `scripts/setup.ps1` 生成随机值，或手工填一个随机强口令 |
| 后端启动即退出，日志「ADMIN_SESSION_SECRET 未设置」 | `.env` 里该键为空 | 同上；本地不允许留空 |
| 店员登录 503「店员会话密钥未配置」 | 缺 `STAFF_SESSION_SECRET` | 跑 `scripts/setup.ps1` 补齐该键并重启后端 |
| 店员登录 500「服务器内部错误」/ 日志 `database is locked` | 已知并发缺陷已修复；仍出现说明有并发写或库文件被占用 | 按 7.1 的排查表逐项检查（多进程、占用工具、busy_timeout、长事务） |
| 店员登录 429「登录尝试过于频繁」 | 5 分钟窗口内失败次数超限（`ADMIN_LOGIN_MAX_ATTEMPTS`） | 等 5 分钟，或本地清表：`DELETE FROM admin_login_attempts;` |
| 后台登录后接口 401「未授权」 | 本地 `ADMIN_COOKIE_SECURE=true` 时 http 下的 Cookie 不会回传 | 确认 `backend/.env` 里 `ADMIN_COOKIE_SECURE=false`（本地示例已是 false），重启后端 |
| 后台登录提示「Token 无效」 | 填的不是 `ADMIN_API_TOKEN` | `Get-Content backend\.env \| Select-String '^ADMIN_API_TOKEN='` |
| AI 客服不可用 / 启动告警「MIMO_API_KEY 未设置」 | 没配大模型 Key | 本地试点可不管；要用 AI 对话就填自己的 `MIMO_API_KEY`（不要提交回仓库） |
| 小程序登录报「微信小程序 AppID/Secret 未配置」 | 没配微信小程序凭据 | 本地可先不跑小程序登录；或填自己的测试号 |
| 快捷开单报「会员尚未绑定小程序」 | 会员没认领 openid | 先调 `POST /api/v1/miniapp/auth/claim`（见 6.2） |
| 快捷开单报「商品今日未配置每日库存」 | 当天每日库存没录 | 先在 `/admin/daily-stock` 录入当天数量 |
| 快捷开单报「预约时间不在营业时间内」 | 预约时间落在 09:00-19:30 之外 | 手动选营业时间内的时段（格式 `yyyy-MM-dd HH:mm`） |
| 快捷开单报「上次开单失败，请重新发起」 | 复用了上一次失败的 `requestId` | 换新 `requestId` |
| FAQ 干跑退出码 1 | 本地库还没建表 | 直接跑 `--apply`（它会先初始化 / 迁移库） |
| 储值干跑 / 入账退出码 1，提示「批次未通过校验或存在冲突」 | 合成夹具里故意有 5 行脏数据 | 属预期拦截；换干净 CSV（见 9.2） |
| `/ready` 返回 503 | `/ready` 是生产口径就绪门禁 | 本地一律用 `/health` 判活 |
| 打印作业一直 `PENDING` | 打印调度 / worker 没开 | 确认 `PRINT_DISPATCH_ENABLED` / `PRINT_WORKER_ENABLED` 为 true 并重启后端 |
| 打印作业是 `MOCKED` 不是 `PRINTED` | Mock 网关只记录受理 | 需要人工在 `/admin/print-jobs` 点「确认出纸」 |

---

## 15. 上线前必须另做（不在本手册范围）

本地试点全部通过，**不等于**可以上线。以下每一项都要单独做、单独留证，并取得项目负责人批准：

1. **真实有赞数据**：用真实有赞导出替换合成夹具，按客户正式迁移 runbook 执行，含核对与回滚；
2. **真实微信支付**：申请商户号、配置 `WECHAT_PAY_*`、关闭 `ALLOW_MOCK_PAYMENT`，做小额可核对交易与退款验证；
3. **真实打印机**：飞鹅等打印机接入、真实出纸验证、`SUBMITTED → PRINTED` 的打印机回调链路；
4. **真机与审核**：体验版上传、微信审核、真机自提 / 同城配送全链路；
5. **对账与回滚**：储值期初导入对账、储值扣减流水核对、异常回滚预案与演练；
6. **凭据治理**：生产 `.env` 独立生成与保管，`ADMIN_API_TOKEN` 等不得复用本地值，`ENABLE_API_DOCS=false`、`ADMIN_COOKIE_SECURE=true`、`PRINT_PROVIDER=feieyun`；
7. **负责人批准**：按 `AGENTS.md` 与 `PROJECT-STATE.md` 的红线，真实用户开放必须由项目负责人明确批准。

---

## 附：相关文件

| 文件 | 用途 |
|---|---|
| `scripts/setup.ps1` | 本地一键初始化（唯一入口） |
| `backend/.env.example` | 本地环境变量示例（非生产配置） |
| `backend/app/config.py` | 配置字段唯一来源 |
| `backend/scripts/manage_staff.py` | 店员账号 CLI |
| `backend/scripts/seed_bakery_faq.py` | 30 条 FAQ 种子导入（dry-run / apply） |
| `backend/scripts/import_youzan_stored_value.py` | 储值期初导入（dry-run / apply / rollback） |
| `backend/tests/fixtures/youzan_stored_value_synthetic.csv` | 合成储值夹具（含故意脏数据） |
| `backend/web/admin/` | 管理后台前端（Vue 3 + Vite） |
| `miniapp/` | 微信小程序前端 |
