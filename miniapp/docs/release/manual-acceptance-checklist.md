# Storefront MiniApp MVP 手工验收清单

本清单用于 `npm run release:readiness` 通过后，补齐自动化无法替代的微信开发者工具、真机、体验版、支付和审核材料证据。

## 正式开放红线

- 截至 **2027 年 5 月 31 日（含）**，本清单只用于开发测试和上线准备，不得据此向真实用户开放小程序。
- **2027 年 6 月只是最早候选上线窗口**。所有自动化与人工验收通过后，仍须由项目负责人明确批准正式开放。
- 截至 **2026 年 8 月 14 日**，项目不具备受控真实微信支付 / 退款及真实有赞券测试条件。未来条件具备后，只允许授权测试账号开展经事前批准的小额测试，并完成退款、对账、数据清理和证据归档。
- 体验版二维码、审核通过、上传成功、真实登录或受控支付测试均属于上线准备证据，不等于正式上线。

截至 2026-07-07，`release:readiness` 已自动覆盖 MiniApp 静态检查、页面 API 覆盖合约、MiniApp 可观测合约、miniprogram-ci 准备合约、生产域名、生产小程序只读 API、微信登录配置探针、生产后台静态资源、生产后台鉴权 API、生产后台浏览器只读导航、本地后台关键 smoke、后端目标测试、截图证据检查和按钮触达扫描。生产 `WECHAT_MINIAPP_APP_ID` 与 `WECHAT_MINIAPP_APP_SECRET` 已写入服务器 `/opt/yunxibakebot/.env` 并重启验证，最新 `release:readiness` 报告 `reports\release-readiness\readiness-20260707-130413.json` 为 27/27 通过。本清单只保留仍需要微信平台、真机、体验版、客户群实际入口或真实支付环境证明的项目。

## 使用方式

1. 先运行 `npm run release:readiness`，确认自动检查通过。
2. 按本文件逐项验收。
3. 将截图、二维码、支付回调记录或审核记录登记到 `docs/harness-engineering/core/evidence-index.md`。
4. 若任一必选项未完成，不标记 MVP 已可正式发布。

## 微信开发者工具

自动检测：先运行 `npm run devtools:check`。该命令只检测 CLI 是否存在和可响应，不会上传小程序。若 CLI 可用但项目 open/preview 卡住，手工打开微信开发者工具确认登录、项目信任和自动化端口。

预览二维码：运行 `npm run devtools:preview-check`。该命令不会上传正式版本，只会尝试调用微信开发者工具 `preview` 并把二维码写到 `reports/devtools/preview-latest.png`；若 IDE 自动化端口未响应，会在 `reports/devtools/preview-latest.json` 写明阻塞原因。

小程序 CI 上传准备：运行 `npm run check:miniprogram-ci-readiness`。该命令只读检查 `project.config.json`、`miniprogram-ci` 依赖声明、上传私钥路径、上传机器人号、版本号和说明，不会上传体验版；无密钥或未安装依赖时报告 `needs_configuration`，表示还不能执行真实上传。配置要求见 [miniprogram-ci 发布准备合约](./miniprogram-ci-readiness.md)。

| 项目 | 验收标准 | 证据 |
|---|---|---|
| 项目导入 | 使用 `D:\Project\YunxiBakeMiniApp` 导入，开发者工具识别 `miniprogramRoot=miniprogram/` | 开发者工具项目截图 |
| 编译 | 普通编译无阻断错误，控制台无页面注册、WXML、TS 编译错误 | 编译成功截图 |
| 首页 | `Storefront MiniApp` 首页装修配置、轮播/公告/分类/货架渲染正常 | 首页截图 |
| 商品 | 商品列表、详情、图片兜底或代理图展示正常 | 商品页和详情页截图 |
| 购物车与结算 | 加入购物车、改数量、选择地址、选择期望时间、勾选协议可提交 | 结算页截图或录屏 |
| 订单 | 订单列表、详情、状态时间线、取消/支付入口展示正常 | 订单页截图 |
| 客服 | AI 消息发送、转人工按钮、等待/刷新人工回复提示正常 | 客服页截图 |
| 客户群登记 | 通过带 `campaignId` 的小程序链接打开登记页，提交后展示成功摘要，并可进入客服 | 登记页截图或录屏 |
| 我的 | 登录状态、会员摘要、地址/协议/售后入口正常 | 我的页截图 |

### 已发现的 DevTools 门槛

2026-06-17 手工打开开发者工具时，`pages/home/index` 已能渲染首页首屏；当时旧默认域名为 `https://hclstudio.cn`，控制台提示：

- `https://hclstudio.cn 不在以下 request 合法域名列表中`
- 当前白名单仅显示 `https://tcb-api.tencentcloudapi.com`

处理要求：

1. 登录微信公众平台，进入小程序「开发管理」/「开发设置」/「服务器域名」。
2. 当前生产默认域名为 `https://yunxifood.cn`，在 `request` 合法域名中加入 `https://yunxifood.cn`。
3. 若商品图片、文件下载或客服素材后续走独立域名，也要按用途补到 `downloadFile` 或对应合法域名。
4. 回到微信开发者工具，按提示刷新项目配置并重新编译。
5. 重新检查首页、商品、订单、客服页面；控制台不得再出现 `yunxifood.cn` request 合法域名错误。

临时本地调试可以在开发者工具里勾选“不校验合法域名”，但这不能作为体验版、真机或发布验收通过证据。项目配置保持 `urlCheck=true`。

2026-06-17 自动预览尝试记录：

- `npm run devtools:preview-check` 已新增并执行。
- 报告：`D:\Project\YunxiBakeMiniApp\reports\devtools\devtools-preview-20260617-052153.json`。
- 当时状态：`needs_manual_confirmation`，原因是微信开发者工具已有进程但 IDE HTTP 端口 `9420` 等待超时，未生成二维码。
- 后续已在 2026-06-22 调整为区分 IDE HTTP 口和自动化端口；历史 `9420` 阻塞不代表当前默认使用方式。

2026-06-21 自动预览复验记录：

- `npm run devtools:preview-check` 已通过。
- 报告：`D:\Project\YunxiBakeMiniApp\reports\devtools\devtools-preview-20260621-015540.json`。
- 二维码：`D:\Project\YunxiBakeMiniApp\reports\devtools\devtools-preview-20260621-015540.png`，同时已更新 `reports\devtools\preview-latest.png`。
- DevTools 已登录，使用 AppID `wx4b59baadd9187a2e`，预览包大小约 187.8 KB。
- 仍需真机扫码验证页面、合法域名请求、图片加载、下单和客服交互。

2026-06-22 DevTools 端口和发布门槛复验记录：

- `npm run devtools:check` 通过。
- `cli.bat open --project D:\Project\YunxiBakeMiniApp --port 10701` 成功，IDE server listening on `http://127.0.0.1:10701`。
- `npm run scan:button-touch-targets` 通过，报告 `reports\button-visual\button-touch-targets-20260622-014732.json`，`status=pass`、`failures=0`。
- `npm run release:readiness` 通过，报告 `reports\release-readiness\readiness-20260622-094854.json`，24/24。
- 当前脚本区分 `MINIAPP_DEVTOOLS_HTTP_PORT=10701` 和自动化端口；不要把历史固定 `9420` 当作当前连接口径。

## 真机或体验版

| 项目 | 验收标准 | 证据 |
|---|---|---|
| 体验版二维码 | 成功上传体验版，并能扫码打开 | 体验版二维码截图 |
| iOS 真机 | 首页、商品、下单、客服、我的核心路径可用 | 机型和截图 |
| Android 真机 | 首页、商品、下单、客服、我的核心路径可用 | 机型和截图 |
| 微信内置环境 | 图片、网络请求、跳转、picker 和 textarea 交互正常 | 截图或录屏 |
| 客户群入口 | 从企业微信客户群、小程序码或带参链接打开 `pages/group-registration/index`，`campaignId` 保留且页面可提交 | 群内入口截图或录屏 |
| 后台手机端 | `release:readiness` 已自动覆盖生产后台桌面浏览器只读导航；仍需真机或手机浏览器确认手机视口可进入概览、订单、商品、转人工、设置 | 截图或录屏 |

## 支付与订单

| 项目 | 验收标准 | 证据 |
|---|---|---|
| Mock 支付 | 未配置真实微信支付时，订单可走 mock 支付兜底并更新为已支付 | 订单详情截图 |
| 微信支付配置 | 真实上线前配置 AppID、商户号、私钥、证书序列号、平台证书、API v3 key、notify URL | 配置状态截图，不能提交密钥 |
| 预下单 | `prepare-payment` 返回 `mode=wechat` 和完整 `wx.requestPayment` 参数 | 接口联调记录 |
| 支付通知 | 微信支付成功通知验签、解密、回写订单支付状态成功且幂等 | 回调日志或测试商户记录 |
| 超时关闭 | 未支付订单超时关闭并释放库存 | 后台订单截图或接口记录 |

## 生产配置与审核材料

| 项目 | 验收标准 | 证据 |
|---|---|---|
| 合法域名 | 小程序后台配置 `https://yunxifood.cn` 等生产 request/download 合法域名 | 微信公众平台截图 |
| 隐私协议 | 小程序内隐私政策、用户协议、售后说明与公众平台材料一致 | 页面截图 |
| 服务类目 | 服务类目覆盖烘焙食品销售、配送/自提相关描述 | 微信公众平台截图 |
| 客服联系方式 | 客服电话、客服微信、营业时间、配送/自提说明为正式值 | 后台店铺配置截图 |
| 数据安全 | 仓库不含真实密钥、商户私钥、Token、证书内容 | `git status` 与配置截图 |
| 回滚说明 | 保留上一版体验版/线上版本、后端配置回滚方式和联系人 | 文档或记录 |
| 审核提交 | 提交审核后记录版本号、提交时间、审核备注和截图 | 审核记录截图 |

## 已自动化的生产证据

| 项目 | 自动检查 | 证据 |
|---|---|---|
| 生产域名 | `npm run check:production-domain` | `reports/domain-check/latest.json` |
| 页面 API 覆盖合约 | `npm run check:page-api-coverage` | local command output |
| MiniApp 可观测合约 | `npm run check:observability-contract` | local command output |
| miniprogram-ci 发布准备 | `npm run check:miniprogram-ci-readiness` | `reports/miniprogram-ci/latest.json` |
| 小程序只读 API 与微信登录配置 | `npm run check:production-miniapp-api` | `reports/production-api-check/latest.json` |
| 后台前端资源 | `npm run check:production-admin` | `reports/production-admin-check/latest.json` |
| 后台鉴权 API | `npm run check:production-admin-api` | `reports/production-admin-api-check/latest.json` |
| 后台浏览器导航 | `npm run check:production-admin-browser` | `D:\Project\YunxiBakeBot\reports\ui\production-admin-browser-smoke.json` / `.png` |
| 微信开发者工具预览 | `npm run devtools:preview-check` | `reports/devtools/preview-latest.json`，通过后生成 `reports/devtools/preview-latest.png` |
| 发布总门槛 | `npm run release:readiness` | `reports/release-readiness/latest.json` |

2026-06-21 自动验收补充：

- `npm run release:readiness` 通过，报告 `reports\release-readiness\readiness-20260621-095347.json`，22/22。
- `npm run devtools:preview-check` 通过，报告 `reports\devtools\devtools-preview-20260621-015540.json`，二维码 `reports\devtools\preview-latest.png`。
- `npm run check:production-domain`、`npm run check:production-admin`、`npm run check:production-miniapp-api` 均通过。
- `npm run check:miniapp`、`npm run typecheck` 通过。
- Bot 侧 `python -m pytest tests\api\test_miniapp_order_api.py tests\api\test_miniapp_payment_api.py tests\api\test_admin_order_api.py -q --tb=short --no-cov` 通过，17 项。
- 生产 `/ready` 返回 `ready`，版本 `0.62.4`。
- 2026-06-21 当时公开店铺配置仍为 `paymentMode=store_confirm`；2026-06-22 后默认支付模式已收紧为 `mock`，`store_confirm` 仅作为历史兼容值。真实微信支付仍需商户配置和真机/测试商户联调，不能用自动化结果替代。

2026-06-22 自动验收补充：

- `npm run release:readiness` 通过，报告 `reports\release-readiness\readiness-20260622-094854.json`，24/24。
- `npm run scan:button-touch-targets` 通过，报告 `reports\button-visual\button-touch-targets-20260622-014732.json`。
- `npm run devtools:check` 通过；DevTools IDE HTTP 口按 `10701` 记录，自动化端口由脚本启动/协商。
- `npm run check:miniapp` 和 `npm run typecheck` 在客户群登记页入口轮次通过，页面数已扩展到 12。
- 这些自动化证据仍不能替代真机/体验版打开客户群登记链接、真实支付商户联调和审核材料截图。

2026-07-07 自动验收补充：

- `release:readiness` 已纳入 `npm run check:page-api-coverage` 和 `npm run check:observability-contract`。
- `npm run release:readiness` 已生成 `reports\release-readiness\readiness-20260707-130413.json`，结果 27/27。
- 新增的 `miniapp page API coverage contract` 和 `miniapp observability contract` 均通过。
- `secret hygiene check` 已通过，仍扫描 miniapp / backend 两仓。
- `scan-miniapp-button-touch-targets.mjs` 已补充 `MINIAPP_AUTOMATOR_WS` / `MINIAPP_AUTOMATOR_WS_ENDPOINT` 显式连接模式，报告会记录 `connectionMode` 和 `wsEndpoint`。
- 生产微信登录配置已补齐：`npm run check:production-miniapp-api` 报告 `reports\production-api-check\production-miniapp-api-20260707-045652.json` 通过，登录配置探针返回微信侧 `invalid code`，不再是 AppID/Secret 未配置。
- DevTools 当前 IDE HTTP 口为 `35072`，带 `$env:MINIAPP_DEVTOOLS_HTTP_PORT='35072'` 复跑按钮触达扫描通过，报告 `reports\button-visual\button-touch-targets-20260707-050113.json`，9 pages / 42 selectors / 0 failures。
- 如微信开发者工具已在前台重新登录并打开自动化端口，可用 `$env:MINIAPP_AUTOMATOR_WS="ws://127.0.0.1:9420"; npm run scan:button-touch-targets` 复验；没有自动化端口时继续使用默认 `npm run scan:button-touch-targets`。
- `npm run check:miniprogram-ci-readiness` 已新增为只读发布准备探针；当前无上传私钥和未安装 `miniprogram-ci` 时只报告 `needs_configuration`，不上传体验版，不替代真机二维码验收。
- 这些自动化证据仍不能替代真机/体验版打开客户群登记链接、真实微信登录、真实微信支付商户联调、合法域名配置和审核材料截图。

## 未完成项记录

| 日期 | 项目 | 阻塞原因 | 下一步 |
|---|---|---|---|
| 2026-06-17 | 微信公众平台合法域名 | 小程序 request 合法域名仍需在公众平台完成最终配置与前台复验 | 登录微信公众平台，把 `https://yunxifood.cn` 加入 request/download 合法域名，并在开发者工具复验 |
| 2026-06-17 | 微信开发者工具页面复验 | `npm run devtools:open-check` 可发起打开项目，但 CLI 仍提示 IDE 初始化/端口等待，尚未形成模拟器编译、页面视觉和合法域名请求通过截图 | 前台打开开发者工具，刷新项目配置，逐页检查首页、商品、购物车、订单、客服、我的并保存截图 |
| 2026-06-17 | 微信开发者工具预览二维码 | 当时 `npm run devtools:preview-check` 状态为 `needs_manual_confirmation`，IDE HTTP 端口 `9420` 等待超时，未生成二维码 | 已在后续轮次通过预览和 10701 端口复验；保留为历史阻塞记录 |
| 2026-06-21 | 微信开发者工具预览二维码 | 已通过，二维码已生成到 `reports\devtools\preview-latest.png` | 用 iOS/Android 真机扫码，保存首页、商品、结算、订单、客服和我的页截图 |
| 2026-06-21 | 真实微信支付 | 当时生产公开配置仍为 `paymentMode=store_confirm`，自动测试只覆盖 mock/订单支付状态和非法通知拒绝 | 配置微信支付商户参数后，用测试商户或小额真实订单验证 `prepare-payment -> wx.requestPayment -> notify -> 订单 paid` |
| 2026-06-22 | 支付默认模式 | 默认支付模式已收紧为 `mock`，`store_confirm` 仅作为历史兼容值；仍未完成真实微信支付商户联调 | 配置商户参数后，验证公开配置切到 `wechat`，再完成 `prepare-payment -> wx.requestPayment -> notify -> 订单 paid` |
| 2026-06-22 | 客户群登记真机入口 | 小程序页和契约已补，但群内链接生成、Platform 后台汇总和体验版/真机打开尚未补证 | 由 Platform 生成带 `campaignId` 的链接或小程序码后，在客户群/体验版真机打开并提交，保存截图或录屏 |
| 2026-07-07 | 生产微信登录配置 | 已写入服务器 `/opt/yunxibakebot/.env`，备份 `/opt/yunxibakebot/.env.codex-backup-20260707045600`；重启后生产配置探针通过，返回微信侧 `invalid code` | 自动探针已证明后端能请求微信 jscode2session；仍需 DevTools 或体验版手工点击登录，保存真实 openid 会话成功截图 |
| 2026-07-07 | DevTools 按钮触达扫描 | 使用当前 IDE HTTP 口 `35072` 复跑通过，报告 `reports\button-visual\button-touch-targets-20260707-050113.json`，完整 `release:readiness` 27/27 | 若后续 DevTools 端口变化，需要重新按最新 `devtools:open-check` 报告里的 IDE HTTP 口设置 `MINIAPP_DEVTOOLS_HTTP_PORT` |
| 2026-07-07 | miniprogram-ci 真实上传 | 当前只新增准备合约和只读探针，未配置上传私钥，未安装 `miniprogram-ci`，未生成体验版二维码 | 按 `docs/release/miniprogram-ci-readiness.md` 配置仓库外私钥、机器人号、版本号和说明后，再补真实预览 / 上传脚本与二维码证据 |

### M5 会员资产前端（2026-08-14）

- [ ] 展示类（任意环境）：我的页余额/积分/可用券与后端一致；积分明细列表与来源文案正确；券中心四个 tab 分组正确。
- [ ] 交易类（必须 IS_USING_LOCAL_API=1 连本地后端）：充值建单→确认→mock 到账→余额刷新；结算页选券/开积分/余额抵扣→提交→确认弹窗金额与后端一致→支付成功跳订单详情。
- [ ] release 过渡：充值入口隐藏；结算差额按钮提示「在线支付即将上线」；余额支付可用。
- [ ] 真实微信支付（商户号到位后）：翻开关 `payment-gate.ts`，差额/充值走真实 JSAPI 验收。
