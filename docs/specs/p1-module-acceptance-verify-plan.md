# P1 全模块承接验证任务包

> 依据：计划书附录D（v1.2）——P1 从"开发三大功能"改为"验证全部已有模块"。
> 原则：**只验证、只修 bug，不加新功能、不重构**。
> 预计周期：验证 2 周 + 修复按问题清单排期。

> **⚠️ 优先级调整（2026-08-25，项目负责人决策，见 PROJECT-STATE v1.3）**
>
> - **MiniApp 承接优先**：Phase C（跨端链路）提升为当前焦点，Phase B 实机走查与 Phase C 共用「微信开发者工具」前置
> - **知识缺口回填（Phase D 附带的 5 条 knowledge_gaps + FAQ 补充）降级**：转人工链路已验证兜底可用，回填排入 P2 试运行前（非阻塞）
> - Phase A 已完成 ✅；Phase B 静态检查已完成 ✅，实机走查 BLOCKED→并入真机周

> **✅ 状态校准（v1.4，2026-08-25，项目负责人三条件核实）**
>
> 1. **微信开发者工具已安装并登录**（Phase B 的 BLOCKED 为探测路径误报，仅扫了 Program Files；见问题区 #7）→ Phase B 实机 + Phase C 阻塞全部解除
> 2. **数据策略 = 真实有赞数据**（出口 IP `10.161.106.143` 已加白名单；同步遇 60020 时回读实际出口 IP 核对 NAT）
> 3. **微信支付商户号：申请流转中** → 支付环节一律 mock（本地 ALLOW_MOCK_PAYMENT 已开启）；商户号通过后真实支付/退款按既有受控门禁执行，本阶段不涉及

---

## 🎯 阶段目标：MiniApp 承接验证（2026-08-25 → 2026-09-08，两周）

> 本阶段的目标陈述（项目负责人定制，替代 v1.0 的"三大功能"表述）：

**让自研小程序在真实商品数据下，从登录一路跑到订单闭环，证明它具备替代有赞电商核心的能力。**

### 达成标准（全部为硬指标）

1. **商品真实化**：有赞 614 商品同步落地；首页/商品列表/详情展示真实商品与价格
2. **15 页面实机走查**：微信开发者工具 + 真机逐页打开，记录渲染与交互；**无白屏、无 console 报错、无空态崩溃**（10 个本地商品 mock 兜底仅作静态参考，不复用闭环）
3. **跨端全链路闭环**：登录→浏览真实商品→加购→结算（券/积分/余额抵扣分支各走一次）→下单（mock 支付）→订单列表/详情→取消/超时链路
4. **会员资产真机复验**：积分明细/券中心/余额/充值页（mock 入账）真机可交互
5. **缺陷清零**：链路中发现并修复全部 P0/P1 缺陷；P2/P3 登记定级

### 明确不属于本阶段（边界重申）

- ❌ 真实微信支付/退款（商户号流转中，通过后走受控门禁）
- ❌ 知识缺口回填（转人工兜底已足够）
- ❌ 企微客户群运营增强、D1 账务核心

---

## 前置条件（开工前确认）

- [x] 资产迁移完成（24 条知识 + 全套凭证）— 2026-08-24
- [ ] 确认 `YOUZAN_MOCK_MODE` 当前值：若为 True，商品相关验证走 mock 数据属预期，记录即可不修

---

## Phase A：后端全域 API 冒烟（第 1 周）

启动服务后逐一验证，**每项记录实际 HTTP 状态码**，禁止只写"通过"：

| 域 | 端点要点 | 验收标准 |
|----|---------|---------|
| 会话登录 | storefront 登录/token 签发 | 200，token 可用 |
| 商品 | 商品列表/详情/分类 | 200（空列表属预期） |
| 订单 | 创建(mock)→列表→详情→取消→超时关闭 | 全链路状态流转正确 |
| 积分 | 余额查询/流水/试算 | 200；**新抵扣因围栏拒绝属预期**（POINTS_DEDUCTION_FENCE=True） |
| 券 | 列表/详情/核销路径 | 200；无券时空列表属预期 |
| 储值 | 充值(mock)/余额/流水 | 200 |
| 客服会话 | 发消息（含知识命中）/会话列表 | 200；命中迁移知识 |
| 企微 | 回调验签拒绝（已验） | 403 保持 |
| **数据隔离** | 用户 A 的 token 查用户 B 的订单 | **403/404，绝不 200**——此项失败为最高优先级 bug |

## Phase B：小程序静态检查 + 页面走查（第 1 周并行）

- [x] `npm run typecheck` 零错误 — tsc --noEmit 退出码 0（2026-08-25）
- [x] `npm run check:miniapp` 全过 — 15 pages / 15 routes（2026-08-25）
- [x] `npm run check:page-api-coverage` 全过 — 15 pages / 33 API terms / 8 boundaries（2026-08-25）
- [x] `npm run test:member-assets` 全过 — 11/11 pass（2026-08-25）
- [ ] ⛔ **BLOCKED**：15 个页面在微信开发者工具中逐一打开 — 本机未安装微信开发者工具（Program Files 下 Tencent 目录无该工具）；已用静态走查替代（见下），实机走查待工具安装后补做
- [x] 商品类页面空库表现（静态走查替代）：15/15 页面 wxml 均含空态区块（empty/暂无/加载失败类标记），无白屏风险结构；products 页以 `filter(products.length)` 过滤空分类并有"暂时没有匹配商品"搜索空态；cart 页以 hasItems 标志驱动空购物车条件渲染

### product-detail 对后端 200+data:null 的处理方式核查（为 P2 决策收集）

三层链路均为友好空态，无崩溃路径：

1. services/products.ts `fetchProductDetail`：`isWrappedCatalogProduct(response)` 通过后 `response.data ? normalize : null` —— 后端 200+data:null 正确转为 null 返回
2. 异常路径（后端不可达/500）：`IS_USING_LOCAL_API=True` 时走本地 mock-catalog 兜底（10 个本地商品，含 birthday-cake 等），假 id 查无返回 null；生产模式直接抛错
3. 页面层 index.ts L63-66：null → setData product:null + unavailableText="商品不存在" + toast

**结论**：P2 #2（后端 200+null 非 404）对小程序客户端实际无用户可见危害——客户端已按缺失语义处理。维持 RESTful 语义改进建议，定级可讨论下调。

## Phase C：跨端链路验证（第 1 周—第 2 周，当前焦点）

**前置（全部已满足）**：微信开发者工具已装并登录 ✅；真实有赞数据（白名单已加）✅；mock 支付本地开启 ✅。

**步骤**：

1. **商品真实同步**：跑 `scripts/sync_real_products_from_youzan.py`（真实凭证），确认 614 条商品入 catalog；
   - ⚠️ 若报 60020：回读实际公网出口 IP（`curl ifconfig.me`），与有赞白名单核对（`10.x` 为内网段，需确认 NAT 出口）
2. **实机走查**（15 页面逐页：开发者工具模拟器 + 真机预览）：渲染/交互/console 报错逐项记录；mock-catalog 仅作静态兜底，不复用于闭环
3. **全链路闭环**（真实商品 + mock 支付，不触发任何有赞真实交易——本系统订单均存在本地 orders 表）：

```
登录 → 首页 → 商品浏览(真实商品) → 加购 → 结算(券/积分/余额抵扣各走一次)
  → 下单(ALLOW_MOCK_PAYMENT) → 订单列表 → 订单详情 → 取消订单
  → 我的页 → 券中心 / 积分明细 / 余额页 → 充值页(mock 入账) → 客服对话(迁移知识命中)
```

每个环节记录：通过 / 报错(截图) / 阻塞原因。

**支付边界（本项目红线重申）**：mock 支付只作用于本地订单体系，与有赞无真实资金交互；真实微信支付/退款必须等商户号到位后，按受控门禁（授权测试账号 + 小额 + 对账 + 清理）执行，本阶段不涉及。

## Phase D：问题清单规则

所有发现的问题按此分级登记（登记到本文件末尾）：

- **P0 阻断**：数据隔离失效 / 数据丢失 / 崩溃 → 立即修
- **P1 严重**：核心链路走不通 → 本周修
- **P2 一般**：显示错误/体验问题 → 排队修
- **P3 记录**：不影响使用 → 上线前评估

## 边界约束（不变）

- 真实微信支付/真实用户开放/客户群运营增强：仍受既有门禁约束
- 小程序 2027-05-31 前仅开发调试测试（项目红线）
- 修复只修 bug，禁止借机重构或"优化"

## 收口要求

每完成一个 Phase：LOGBOOK 登记（trace 前缀 `2026xxxx-p1-verify-`）→ 钩子链 → push → ls-remote 回读。全部完成后出《P1 验证报告》交架构师评审。

---

## 问题登记区

（Phase A-D 执行中填写）

| # | 级别 | 域 | 描述 | 状态 |
|---|------|-----|------|------|
| 1 | P1 严重 | 知识同步 | BM25-only 模式下 KnowledgeSyncService 收到 vs=None，知识写入时后台向量同步全部报 `'NoneType' object has no attribute '_get_model'`（24 条迁移知识 vector_sync_status=FAILED） | ✅ 已修复（sync_admin_entry 增加 None 守卫，重试后 24/24 SUCCESS） |
| 2 | P2 一般 | 商品 | GET /api/v1/miniapp/products/{不存在id} 返回 200 `{"code":0,"data":null}`，任务包预期 404；客户端需判 data null 才能感知缺失 | 待修 |
| 3 | P3 记录 | 环境 | YOUZAN_MOCK_MODE=False（.env 显式覆盖默认 True）：商品/订单域走真实有赞路径，本机 IP 未在白名单时相关调用将失败，属预期不修 | 已记录 |
| 4 | P3 记录 | 环境 | ALLOW_MOCK_PAYMENT 默认 False（fail-closed 正确），本地验证储值链路需在 .env 开启；已开启并跑通 unpaid→paid→入账 | 已解决 |
| 5 | P3 记录 | 环境 | ~~本机未安装微信开发者工具，Phase B 页面实机走查 BLOCKED~~ **已更正（#7）：工具已安装，详见 #7** | ⛔→✅ 误报更正 |
| 8 | **P1 严重** | 环境/走查 | devtools CLI 打开项目报 code 10 "需要重新登录"（islogin=true 与 open 行为矛盾，CLI 会话票据过期）；`cli login` 挂起等待人工扫码。AppID 配置已确认（wx4b59baadd9187a2e / YunxiBakeMiniApp / srcMiniprogramRoot=miniprogram/）| ✅ 已解决（项目负责人扫码重登后 `cli open √`、`cli auto --auto-port 9420 √`）|
| 9 | **P2 一般** | 小程序/chat | chat 页 `formatMsgTime` 使用 `new Date("yyyy-MM-dd HH:mm:ss")` 格式，iOS 不支持（仅支持 yyyy/MM/dd）——开发者工具中为 warn，iOS 真机上消息时间将显示 Invalid Date | 待修（真机前必修） |
| 10 | **P2 一般** | 商品目录 | 目录可见范围受限：库内 309 条在售商品（knowledge_base product is_active=1 共 309）但 products 页 allProducts 仅 **39**——catalog 服务 `DEFAULT_PRODUCT_LIMIT=50`（application.py:20）叠加筛选条件所致；需产品决策（分页加载/全量/分类导航）| 待产品决策 |
| 11 | P3 记录 | 环境 | automator screenshot 接口在本 IDE 版本全部超时不可用，页面截图留档改由人工截图补充 | 已记录 |
| 12 | P3 记录 | 会员资产 UX | points/coupons 页对非会员身份显示 loadFailed=true（400 "未识别为会员"属身份前置设计）——真实客户有档案不受影响，但新访客引导注册的 UX 表达待议 | 记录待议 |

## Phase C 第二步：15 页面实机走查实测记录（2026-08-25，automator ws://127.0.0.1:9420）

前置：项目负责人扫码重登开发者工具；`cli auto --auto-port 9420` 开启自动化；本地后端 Start-Job 方式运行；小程序 Storage 开关 yunxiUseLocalApi=true 指向本地 API；负责人真实微信身份已登录。

| 页面 | 导航 | 渲染与数据要点 | 问题 |
|------|------|---------------|------|
| home | ✓ | blocks(3)、登录提示"已使用真实微信身份" | 首页商品采样字段空，blocks 结构待人工目验 |
| products | ✓ | **allProducts=39**、categorySections=35、店铺"芸熙烘焙（银河SOHO店）"、营业时间 09:00-20:00 | #10 可见范围受限 |
| product-detail | ✓ | 无参数直达 →"商品不存在"空态 ✓ | 带真实 id 详情验证归入全链路步骤 |
| cart | ✓ | hasItems=false 空态 + 推荐商品 array(2) | — |
| checkout | ✓ | 完整结算表单（自提/配送、日期窗、门店提示） | — |
| policy | ✓ | 隐私政策正文渲染 | — |
| address | ✓ | "已使用真实登录态加载地址"，空地址列表 | — |
| orders | ✓ | allOrders=1（此前夹具订单）、5 个筛选 tab | — |
| order-detail | ✓ | 无参数 canLoadOrder=false 合理提示 | 归入全链路带参验证 |
| group-registration | ✓ | 群登记表单完整（日期/时段选项） | — |
| chat | ✓ | 13 条历史消息、在线客服连接正常 | #9 iOS Date 警告 |
| profile | ✓ | "已使用真实登录态进入个人中心"、服务入口 array(5) | — |
| points | ✓ 渲染 | **loadFailed=true** | #12 身份前置（合成会员在 Phase A 为 200） |
| coupons | ✓ 渲染 | **loadFailed=true** | #12 同上 |
| recharge | ✓ | 充值档位 tiers(4)、余额 0 展示 | — |

console 采集：100 条警告，全部为 chat 页 iOS Date 格式同类警告（#9）。screenshot 接口超时不可用（#11）。
| 7 | P3 记录 | 环境 | ~~本机未安装微信开发者工具~~ 探测方法缺陷更正：工具实际安装于 `D:\微信web开发者工具\`（非 Program Files 标准路径），CLI（cli.bat）与 IDE server（127.0.0.1:54080）均在位 | ✅ 已更正 |
| 8 | **P1 严重** | 环境/走查 | devtools CLI 打开项目报 code 10 "需要重新登录"（islogin=true 与 open 行为矛盾，CLI 会话票据过期）；`cli login` 挂起等待人工扫码。AppID 配置已确认（wx4b59baadd9187a2e / YunxiBakeMiniApp / srcMiniprogramRoot=miniprogram/）| ⏳ **待项目负责人在开发者工具界面重新登录**，登录完成后实机走查立即可续 |
| 7 | P3 记录 | 流程 | Phase B 实机走查 BLOCKED 为**探测方法缺陷**：仅扫描 Program Files 下 Tencent 目录，未扫描其他盘符/自定义安装路径；实际微信开发者工具早已安装并登录。建议日后工具探测覆盖 `(Get-Command)` 与注册表/AppData 卸载列表 | ⛔→✅ 已核实更正（2026-08-25）：实机走查解除，并入 Phase C |

## Phase A 冒烟实测记录（2026-08-25）

前置：YOUZAN_MOCK_MODE=False（运行时实际值）；服务 v0.132.9；BM25 索引 31 条。

| 域 | 端点 | 方法 | 实际状态码 | 判定 |
|----|------|------|-----------|------|
| 基线 | /health | GET | 200 version=0.132.9 | ✓ |
| 登录 | /auth/login 空 code | POST | 400 明确报错 | ✓ |
| 登录 | token 可用性 | - | 各受保护端点 200 隐证 | ✓ |
| 商品 | /products | GET | 200 空列表 | ✓ |
| 商品 | /product-categories | GET | 200 空列表 | ✓ |
| 商品 | /products/{假id} | GET | **200 data:null** | ⚠️ 问题#2 |
| 订单 | /orders 创建（无真实商品） | POST | 400 参数校验 | ✓ |
| 订单 | /orders 列表含自有夹具单 | GET | 200 YES | ✓ |
| 订单 | /orders/{id} 详情 | GET | 200 | ✓ |
| 订单 | /orders/{id}/cancel | POST | 200 status→cancelled | ✓ |
| 订单 | /orders/{不存在} | GET | 404 | ✓ |
| **数据隔离** | B 查 A 的订单 | GET | **404** | ✓ 最高优先级通过 |
| **数据隔离** | B 列表不含 A 单 | GET | CLEAN | ✓ |
| **数据隔离** | B 取消 A 的订单 | POST | 404 | ✓ |
| **数据隔离** | 无效 token | GET | 401 | ✓ |
| 积分 | /points（合成会员） | GET | 200 pointsBalance=0 | ✓（未绑定 openid/非会员为 400 属身份前置设计） |
| 积分 | /orders/{id}/points-preview | POST | 400 围栏拒绝属预期 | ✓ |
| 券 | /coupons（合成会员） | GET | 200 coupons=[] | ✓ |
| 储值 | /recharges 创建 amountFen=50000 | POST | 200 rechargeId status=unpaid | ✓ |
| 储值 | /recharges/{id}/mock-pay | POST | 200 status→paid | ✓ |
| 储值 | /balance 入账 | GET | 200 balanceFen=50000 + ledger 流水 | ✓ |
| 储值 | /recharges 流水 | GET | 200 含记录 | ✓ |
| 客服会话 | /chat/messages 发消息 | POST | 200 命中迁移知识 | ✓ |
| 客服会话 | /chat/messages 会话列表 | GET | 200 | ✓ |
| 企微 | /wecom/callback 无效签名 | GET | 403 保持 | ✓ |

数据隔离说明：合成会员夹具（customer_master p1-test-customer-001 + identity_links miniapp_openid=p1probe001，手机号 19900000001 为明显合成号段）仅存在于本地开发库；旧库 2.4 万真实客户数据零触碰。
