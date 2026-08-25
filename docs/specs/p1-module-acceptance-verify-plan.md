# P1 全模块承接验证任务包

> 依据：计划书附录D（v1.2）——P1 从"开发三大功能"改为"验证全部已有模块"。
> 原则：**只验证、只修 bug，不加新功能、不重构**。
> 预计周期：验证 2 周 + 修复按问题清单排期。

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

## Phase C：跨端链路验证（第 2 周）

后端 + 开发者工具联通后走完整链路：

```
登录 → 首页 → 商品浏览 → 加购 → 结算（mock 支付）
  → 订单列表 → 订单详情 → 取消订单
  → 我的页 → 券中心 / 积分明细 / 余额页 → 充值页(mock)
  → 客服对话（问迁移知识里的真实问题验证命中）
```

每个环节记录：通过 / 报错(截图) / 阻塞原因。

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
| 5 | P3 记录 | 环境 | 本机未安装微信开发者工具，Phase B 页面实机走查 BLOCKED；静态走查已替代完成（15/15 空态结构确认），实机走查待工具安装后补做 | ⛔ 阻塞实机走查 |
| 6 | P3 记录 | 小程序 | product-detail 对后端 200+data:null 已有三层友好空态处理（services 转 null → 页面"商品不存在"）；本地模式下异常路径另有 mock-catalog 兜底。P2 #2 对小程序端无用户可见危害 | 已核查（支撑 P2 定级复议） |

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
