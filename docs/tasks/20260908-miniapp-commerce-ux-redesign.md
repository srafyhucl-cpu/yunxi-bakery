# 芸熙烘焙小程序商品优先型 UI/UX 与履约重构任务登记

> task_id: T-MINIAPP-COMMERCE-UX-REDESIGN
> owner: AI 员工
> status: active
> status_label: 进行中（active）
> as_of_commit: 855babb149be8d38ea46925c143448f535519fcc
> version: 0.133.0-p2trial.3
> branch: main
> allowed_paths: miniapp/, backend/app/api/channels/storefront/, backend/app/service/order/, backend/app/service/delivery/, backend/app/repository/, backend/app/models/, backend/app/migrations/, backend/tests/, docs/superpowers/, docs/tasks/
> forbidden_paths: backend/data/, backend/reports/, .env*, 生产目录
> source_of_truth: PROJECT-STATE.md

## 目标

完成商品优先型 MiniApp 体验重构，并建立北京闪送支付前报价、订单金额快照和配送状态闭环。

## 2026-09-09 清理收口

- 已删除结算页未使用的 `totalFen` 局部变量与摘要字段。
- 已删除商品目录未使用的 `ProductCategory` 类型导入和无调用方的 `productMatchesSearch` 函数。
- 已删除确认无引用的 constants/ui.ts、constants/user.ts，以及已经不再使用的 app.json 地理位置权限声明和 shop.ts 门店经纬度配置。
- 已核对页面、服务、配置和验收脚本引用；商品 mock 回退、页面装修回退、配送服务、业务常量和验收脚本仍有调用或证据职责，予以保留。
- 已删除 3 个无调用方导出符号：`getCategoriesByIds`、`getMiniappUserId` 和 `IS_LOCAL_BACKEND`；未删除任何页面、服务文件、商品回退、配送/支付能力或验收脚本。
- 可重建缓存按白名单清理；业务数据、有效报告、环境文件和历史证据保留。
- 已删除 `miniapp/scripts/phasec-step3.mjs`：该脚本没有 npm 入口或现行调用方，职责已由当前分页面 DevTools 验证脚本覆盖；历史记录保留，未删除报告或其他验收脚本。
- 已删除客服页仅转发公共 `formatMsgTime` 的本地包装函数，页面直接使用已覆盖 iOS 时间解析兼容性的 `utils/time-format.ts`；未改变消息展示结果或客服业务行为。

## 首发范围

- 北京闪送
- 门店自取
- 全国配送不进入首发，仅保留后续扩展位

## 已确认业务约束

- 商品预订为主，通常前一天预订、次日发货或取货。
- 当天订单需根据制作进度与门店能力确认。
- 每日发货时段为 09:00–19:30，常规当天订单截止时间约为 17:00。
- 商品按自提价定价，闪送费按收货地址和距离计算，由客户承担。
- 闪送费必须在支付前确定，并与商品金额一并支付。
- 有赞只作为迁移期商品/经营数据来源，不作为新小程序订单的配送报价、支付或闪送运单中间层。

## 前置门禁

在取得闪送开放平台开发者/商户能力、正式 API 文档、测试环境、鉴权和签名规则、报价字段、回调规范、错误码以及取消/退款规则前：

1. 不猜测闪送真实接口字段。
2. 不宣称真实报价、配送单创建或回调已完成。
3. 只允许先实现内部领域模型、稳定契约、mock Provider 和失败状态设计。
4. 真实平台联调与真实配送验收保持阻塞。

当前状态：内部报价绑定、订单金额快照与前端展示处于进行中（active）；真实闪送开放平台联调处于已阻塞（blocked）。阻塞原因是尚未取得可复核的闪送 API 资料或测试权限。

## 当前基线

- `as_of_commit`: `855babb149be8d38ea46925c143448f535519fcc`
- `version`: `0.133.0-p2trial.3`
- `branch`: `main`
- `workspace_state`: `clean`
- 当前代码快照包含 MiniApp UI 布局修复、会话提示修复和无用前端配置清理；后端会员资产、配送实现、有效报告和环境文件未被本轮删除或回退。

## 本任务已执行验证

| 命令 | 结果 | 说明 |
|---|---:|---|
| `git rev-parse HEAD` | 0 | 读取当前代码快照 |
| `git status --short` | 0 | 确认工作区已有 dirty 改动 |
| `Get-Content backend/VERSION` | 0 | 读取当前版本 `0.133.0-p2trial.3` |
| `pytest backend/tests/service/delivery/test_application.py -q --no-cov` | 0 | 4 个内部金额/状态断言通过 |
| `python -B backend/scripts/check_project.py --skip-tests` | 1 | 仅因任务登记文件元数据缺失，业务红线检查通过 |
| `cd miniapp && npm run typecheck` | 0 | TypeScript 类型检查通过 |
| `cd miniapp && npm run check:miniapp` | 0 | 15 页面、15 路由静态检查通过 |
| `cd miniapp && npm run devtools:verify-all-pages` | 0 | iPhone 12/13 模拟器 15/15 页面结构、导航、按钮尺寸及横向溢出检查通过 |
| `python -B backend/scripts/check_mistake_ledger.py` | 0 | 错误账本 35 条结构合法 |
| `cd miniapp && npm run walkthrough:phase-c` | 未通过 | DevTools 截图接口超时会残留请求并导致后续路由串扰；脚本已改为非零退出，完整视觉截图待该接口稳定后复验 |
| `pytest tests/api/test_miniapp_delivery_api.py tests/service/delivery/test_order_quote_binding.py tests/service/delivery/test_shansong.py -q --no-cov` | 0 | 9 项通过，覆盖无伪造报价、商品集合必填、报价归属、金额快照和库存预扣顺序 |
| `pytest tests/service/test_order.py tests/api/test_miniapp_order_api.py tests/service/test_coupon_payment.py tests/service/test_points_payment.py tests/service/test_points_service.py tests/service/test_stored_value.py tests/api/test_miniapp_points_api.py tests/api/test_miniapp_delivery_api.py tests/service/delivery -q --no-cov` | 0 | 120 项订单、支付、券、积分、储值与配送定向回归通过 |
| `cd miniapp && npm run typecheck && npm run check:miniapp` | 0 | 配送金额明细与履约方式展示的 TypeScript、15 页静态路由检查通过 |
| `cd miniapp && npm run devtools:verify-all-pages` | 0 | 修复导航后旧页面对象竞争，iPhone 12/13 模拟器 15/15 页面结构走查通过 |
| `cd miniapp && npm run devtools:commerce-states` | 0 | 注入可清理样本购物车后，商品行、数量控件与结算栏同时存在且不遮挡；商品卡进入详情语义与不可售详情状态通过 |
| `cd backend && pytest tests/api/test_shop_operations_api.py tests/api/test_miniapp_order_api.py tests/service/test_order.py -q --no-cov` | 0 | 48 项通过，默认运营时段与订单预约校验保持一致 |
| `cd backend/web/admin && npm run typecheck` | 未运行 | 本地缺少 `vue-tsc` 可执行依赖；本轮不安装依赖或写入 C 盘缓存，仅完成源码与后端契约验证 |

## 本轮前端收敛（2026-09-08）

- 首页运行态首块已固定为含真实商品的“今日推荐”，本地配置与运行时排序一致；品牌和履约说明后置，不遮挡首屏商品信号。
- 首页运营文案改为中文，缺失商品图使用统一占位，不保留大面积空白。
- 未登录结算页只保留“去登录”动作，不再展示联系人、地址、抵扣或提交订单控件。
- 北京闪送只有在返回 `status=quoted`、有效 `quoteId` 和配送金额后允许提交；地址、履约时间变更会重新请求报价。未报价、超范围和平台不可用不再以 0 元运费进入支付。
- 无商品 ID 或已不存在商品的详情页提供“返回选购”，不再显示不可用的购买按钮。
- DevTools 截图自动化已收紧：截图错误、页面路由错配或控制台 warning/error 均以非零退出，不能作为通过结论。

## 本轮报价绑定与金额快照收敛（2026-09-09）

- 配送报价摘要纳入门店地址、收货信息、预约时间、后端规范化商品 ID/数量和商品总额；同金额、同件数但不同商品不能复用报价。
- 北京闪送建单在库存预占前验证报价归属、可支付状态、有效期、报价总额自洽与请求摘要；前端伪造 `deliveryFeeFen` 不参与订单金额计算。
- 订单快照固定 `goodsTotalFen`、`deliveryFeeFen`、`payableFen`、`deliveryQuoteId` 与供应商标识，支付准备继续以最终订单金额为输入。
- 订单详情展示商品金额、闪送费与实付合计，并兼容旧 `delivery` 与新 `beijing_delivery` 履约值。
- 15 页 DevTools 走查脚本改为导航后重新获取并确认当前页，避免异步切页时读取被销毁的页面对象。

## 本轮商品优先与履约事实收敛（2026-09-09）

- 商品列表移除无实际筛选能力的“自提/闪送”切换和定位依赖，改为明确的“自提价 / 北京闪送运费实算”说明；商品卡的箭头只表达进入详情，避免把进入详情误解为直接加购。
- 商品详情将“当天现做现发”改为“当天订单请先咨询客服”；不可售商品不再显示购买操作。空购物车不再保留金额和结算栏。
- 首页运行态审计确认商品货架顶部为 `102px`、首张商品为 `141px`、品牌轮播为 `461px`，首屏首先服务选购。
- 店铺默认运营时段、后台默认表单、小程序回退、结算和群登记时间选择、公开 API 示例统一为 `09:00-19:30`；已保存的后台运营配置不会被代码静默改写，需在后台页面另行保存。
- DevTools 截图异步超时会产生迟到且页面错配的文件，已登记 `M-20260909-002`；本轮用页面路由、运行态数据、元素位置和状态审计代替该截图作为结构证据。
- 首页商品块为异步数据，15 页审计已改为等待货架内容就绪后再检查；避免路由已完成但商品尚未渲染时出现假阴性（`M-20260909-004`）。

## 当天预订边界收敛（2026-09-09）

- 小程序按北京时间计算日期：`17:00` 前可选择今天，`17:00` 起日期从明天开始。选择今天时，结算页和群登记页提示需客服确认，不承诺即时制作或配送。
- 后端订单服务拒绝早于当前北京时间的预约；`17:00` 及之后拒绝普通小程序当天预约，避免绕过前端选择器。
- 测试固定在 `2026-06-17 12:00`，覆盖过去时间、当天截止前允许、当天截止后拒绝，并保持历史订单夹具可复跑。
- 新增 `miniapp/scripts/verify-devtools-product-purchase-path.cjs`，从运行态选择真实在售商品，验证列表→详情→加入购物车→购物车金额和结算栏，结束后清理 `cartItems`。
- 新增 `miniapp/scripts/verify-devtools-same-day-scheduling.cjs`，按北京时间只读验证群登记页在 17:00 截止规则下的日期起点、当天状态和客服提示；当前运行态审计在北京时间 01:37 通过。
- 已检查认证路径：后端测试 JWT helper 仅用于测试，DevTools 真实登录路径需要 `wx.login` 和受控服务端会话；未获得授权测试条件前不伪造登录态，已登录结算保持未验证。

## 商品目录与结算空态收敛（2026-09-09）

- 商品目录从同时保留全部分类内容的隐藏滚动区，收敛为只渲染当前活动分类，首屏加载 12 款，按需“查看更多”；减少数百 SKU 目录的无效渲染并提升分类切换稳定性。
- 商品行改为紧凑横向清单：同时显示自提价、可预订/低库存/售罄状态、预订或现货提示，以及明确的“预订/查看”动作，避免只靠箭头让用户猜测下一步。
- 结算页无商品时仅展示引导选购空态，不再展示配送方式、地址、优惠资产、金额明细、协议或提交栏；存在商品但未同意协议时提交按钮禁用并明确提示。
- `order-summary.ts` 继续保证北京闪送缺少费用快照时显示“待确认”，不将未知运费误导为零元。
- DevTools 运行态审计确认商品目录存在活动分类清单、库存状态、预订提示和“预订/查看”动作；结算配送审计确认无有效报价不可提交、报价失效立即禁用。

## 下一步

## 无用前端配置与页面布局收口（2026-09-09）

- 删除 constants/ui.ts 和 constants/user.ts，两者在小程序源码、脚本和文档契约中均无调用方。
- 删除 app.json 中未被任何运行代码使用的 scope.userLocation / getLocation 权限声明，并同步删除 shop.ts 中仅服务于该权限的 storeLocation。
- 首页、商品目录、购物车、客服和会员中心根节点统一标记 page-shell--tabbar，滚动视口为自定义 TabBar 让出占用高度；会话提示动作改为可访问的自定义操作节点，避免原生按钮默认样式造成空白块。
- 本轮未删除商品 mock 回退、页面装修回退、配送服务、业务常量、测试脚本、验收报告、node_modules 或本地微信工具配置。
- 验证：npm run typecheck、npm run check:miniapp、npm run check:page-api-coverage、npm run audit:buttons、npm run audit:button-styles、npm exec -- tsc --noEmit --noUnusedLocals --noUnusedParameters 均退出码 0；git diff --check 通过。

## 展示语言与按钮审计收口（2026-09-09）

- 客服页移除聊天、厨师、配送、蛋糕、电话和定位 emoji，统一改为品牌与业务文字；订单加载失败状态改为“订单”文字标识。
- 商品目录、商品详情和结算页去除“测算”“底价”“当前接口返回”等开发/工程语境，统一为“门店在售商品”“北京闪送｜运费实算”“确认运费中”等顾客可理解文案。
- 全局按钮及首页、商品目录、商品详情、购物车、结算、订单、地址、会员、优惠券和充值页补齐按压反馈、长文案溢出保护和按钮文本保护。
- `npm run audit:button-styles` 从 41 个 warning 收敛为 96 controls、0 failures、0 warnings；`npm run audit:buttons` 继续保持 96 controls 通过。
- 当前 D 盘微信开发者工具安装结构异常，`code/package.nw` 只剩 `node_modules` 且 `core.wxvpkg` 不存在，9420/64787 端口无监听；本轮不形成最新 DevTools 运行态或像素级截图验收。

1. 申请并取得闪送开放平台资料和测试权限。
2. 将正式字段映射、错误码、创建运单与回调幂等规范补入配送领域实现与 API 契约。
3. 明确优惠券、积分和储值是否可抵扣闪送费，并按确认后的规则补金额测试。
4. 在真实受控测试完成前保持真实联调门禁，不得改写为已完成或已上线。
5. 修复或替换 DevTools 截图调用后，重新执行首页、详情、结算、订单详情的关键交易页视觉截图验收。
6. 在后台运营配置页明确保存 `09:00-19:30`，使已存在配置与新的默认值一致。

## 最新运行态复核（2026-09-09）

- iPhone 12/13（390px）中商品目录首个“预订”动作原为 `45x23px`，不满足常用 `44x44px` 最小触控目标；已调整为 `58x45px`，右边缘为 `375px`，无横向溢出。
- 商品卡最小高度同步由约 `89px` 增至 `111px`；长商品名、库存/预订提示、价格与操作区均保持独立可见，不互相遮挡。
- `verify-devtools-commerce-states.cjs` 已将商品动作最小 `44x44px` 纳入运行态断言，避免后续样式收缩只靠人工发现。
- 本轮串行重新执行 15 页 DevTools 审计，报告 `generatedAt=2026-09-08T20:34:37.582Z`、`15/15 PASS`；同时通过商品购买路径和闪送报价状态审计。
- 价格展示的负字距规则已清零，避免中文与金额在设备字体回退时产生拥挤。

## 商品目录快速预订与购物车推荐商品化收口（2026-09-09）

- 商品目录“预订”动作从仅进入详情改为直接加入预订单，并展示底部预订单金额、已选件数和“去结算”入口；售罄或下架商品仍进入详情页咨询。
- 购物车推荐从本地 mock 商品 ID 改为商品服务来源，优先使用精选商品，无精选时回退门店在售商品；推荐商品可直接加入预订单。
- 购物车本地项增加可选库存快照，商品目录、商品详情和购物车推荐加购都会写入库存；商品详情加号、详情加购和购物车加号提前阻止超过库存。
- `verify-devtools-commerce-states.cjs` 已补充商品目录快速预订写入购物车和预订单底栏断言；当前仅完成脚本语法检查，等待 DevTools 恢复后运行态复验。
- 最新静态门禁通过：TypeScript、15 页面静态检查、页面 API 覆盖、订单金额 4 项测试、101 个控件审计、按钮样式 0 失败 0 警告。
- 当前微信开发者工具仍无法启动 Automator 会话，`npm run scan:button-touch-targets` 报告无法启动 DevTools；本轮不构成最新运行态、像素级、真实认证、真实闪送或真实支付验收。

## 收口复核（2026-09-09，run_id: 20260909-miniapp-commerce-ux-redesign-r14）

- 工作区盘点确认配送领域、商品快速预订、订单金额适配、运行态审计脚本和对应测试均被源码、任务文档或证据索引引用；没有删除可证明无调用的正式代码。
- `commerce-states`、`product-purchase-path`、`checkout-delivery-states`、`same-day-scheduling` 四项 DevTools 审计串行通过；既有 `all-pages-devtools-audit.json` 回读结果为 15/15 PASS。
- `scan:button-touch-targets` 本轮再次出现 `timeout waiting for automator response`，报告为 0 pages / 0 selectors；按 M-20260909-060/M-20260909-062 作为工具会话失败处理，不替代触控验收。
- 静态、类型、页面 API 覆盖、金额测试、104 个控件审计、按钮样式审计和配送后端定向测试均通过；真实认证、真实闪送开放平台、真实支付、生产验收仍未验证。

## 无用前端代码清理（2026-09-09，run_id: 20260909-miniapp-cleanup-r3）

- 通过入口、引用和动态 class 复核，未发现可安全删除的业务 TypeScript 文件；商品回退、页面装修回退、配送、会员、订单和验收脚本均有实际调用或证据职责，继续保留。
- 删除 4 组确认无引用的 WXSS 规则：旧页面顶部占位间距、未使用的状态图标变体、首页旧销量文本、充值页旧日期类和政策页旧标题类；动态商品徽标和页面状态类未删除。
- `npm run typecheck`、`npm run check:miniapp`、`npm run check:page-api-coverage`、`npm run audit:buttons`、`npm run audit:button-styles`、`npm exec -- tsc --noEmit --noUnusedLocals --noUnusedParameters` 均通过。
- 当前清理提交为 `d06b0ba`；本轮不改变业务行为，也不替代微信开发者工具运行态、真实认证、真实闪送或真实支付验收。

## 无用前端代码清理补充（2026-09-09，run_id: 20260909-miniapp-cleanup-r16）

- 文件级、导出级和动态 class 复核未发现可安全删除的页面、服务文件、商品/页面 mock 回退、支付门禁或验收脚本。
- 删除 `utils/order-summary.ts` 中不需要对外暴露的 `OrderFulfillmentMethod` 导出；删除 `pages/order-detail/index.wxss` 中不会被模板生成的 `button.order-actions__button` 选择器，保留实际使用的 `.order-actions button` 规则。
- `npm run typecheck`、`npm run check:miniapp`、`npm run check:page-api-coverage`、`npm run audit:buttons`、`npm run audit:button-styles`、`npm exec -- tsc --noEmit --noUnusedLocals --noUnusedParameters` 和 `git diff --check` 均通过。
- 本轮不改变业务行为；未删除有效报告、业务数据、node_modules 或其他不确定用途的文件。
