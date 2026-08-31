# Bakery Commerce Platform 项目边界

> updated_at: 2026-08-29
> as_of_commit: `77f9346`
> version: `0.133.0-p2trial.3`
> status: current
> 当前代码唯一位于 `D:\Project\YunxiBakery` Monorepo；`backend/` 是 Platform 经营中枢，`miniapp/` 是 Storefront MiniApp 前台渠道。
> 旧仓名只在历史路径、兼容层或迁移证据中保留，不作为当前执行入口。

相关长期决策见：[ADR 0002：采用逻辑总项目 + 双仓边界，并将 Yunxi 降级为实例名](../harness-engineering/adr/0002-platform-storefront-boundaries-and-instance-naming.md)。该 ADR 记录的是角色边界；当前实现已落地为同一 Monorepo 内的 `backend/` 与 `miniapp/` 目录边界。

## 定位

- `Bakery Commerce Platform`
  - 通用产品级逻辑总项目。
  - 当前实现位于本 Monorepo，不新建第三个代码仓；统一命名、边界和文档口径。
- `backend/`（Platform 经营中枢）
  - 当前唯一后端代码目录，承担业务真相源、后台与第三方集成职责。
- `miniapp/`（Storefront MiniApp 前台渠道）
  - 当前唯一小程序代码目录，承担消费者前台页面、微信能力和 API client。
  - `Platform` / `Storefront MiniApp` 是角色口径，不是仓库 slug；历史仓名只保留在迁移和兼容上下文。
- `Yunxi`
  - 首个真实落地实例、配置集合、迁移来源和样板客户名。
  - 不是产品名，也不是长期能力命名。

## backend/（Platform）职责

- 客户主档、客户迁移、企微绑定、CRM
- 商品主档、分类、同步消费
- 订单主档、支付、履约、退款、事件流
- AI 会话、人工接管、运营规则
- 店铺配置、装修配置、管理后台
- 有赞、企微、支付通知、Webhook 集成

## miniapp/（Storefront MiniApp）职责

- 页面、组件、交互、微信能力
- 购物车、下单页、用户订单页、地址页
- API client、登录态、本地缓存
- 用户侧客服入口展示

## backend/ 内部 canonical 领域

- `customer`
- `order`
- `catalog`
- `conversation`
- `ops`
- `integrations`
- `channels/storefront`

第一阶段保留既有 `miniapp_*` 路径作为兼容 facade，但新代码默认依赖以上 canonical 领域命名。

有赞客户迁移的完整入口见：

- [有赞客户正式迁移执行 Runbook](./youzan-customer-formal-import-runbook.md)
- [有赞客户迁移后核对脚本](../../backend/scripts/verify_youzan_customer_import.py)
- [有赞客户迁移交接与回滚 Runbook](./youzan-customer-import-handoff-and-rollback-runbook.md)
- [有赞客户迁移审计清单](./youzan-customer-migration-audit-checklist.md)

### 现状收口

- `app/service/miniapp_*.py` 已全部降级为兼容 facade。
- `customer / catalog / order / conversation / channels/storefront / ops` 已有对应 canonical 实现承接真实逻辑。
- `order` 域已直接承接下单、支付准备、mock 支付确认、微信支付通知、用户取消、后台状态流转、未支付关闭与超时扫描。
- `integrations/wechat_pay.py` 已开始承接微信支付签名、预下单、通知验签与通知解密等第三方适配细节。
- `customer/group_operations.py` 已承接客户群绑定、团购批次、结构化登记和汇总文案生成，后台与前台登记页只是围绕同一份 customer 群运营真相做投影。

更细的内部迁移盘点见：[Platform 领域迁移盘点](./platform-domain-migration-inventory.md)。当前判断是服务层 facade 已基本完成，后续优先迁测试和内部依赖；地址域仍保留 `miniapp_addresses` 等数据库表名，不在兼容期做表重命名。

客户群运营一期的边界也按同样原则处理：

- 运营工作台和 MiniApp 登记页都只消费 `customer` 域的同一份群运营真相。
- `group_registrations` 只作为前台渠道公开入口，不把登记规则留在前台仓。
- 后续如果要补 `opengid_to_chatid` 归因，优先放入 `customer` / `integrations` 的 canonical 边界内，不在页面层临时拼接。

## 当前推进顺序

当前阶段、阻塞项和决策状态只看 [`PROJECT-STATE.md`](../../PROJECT-STATE.md)，不要从本边界文档推导里程碑。当前基线为：

1. P0 Monorepo 整合与 P0.5 资产迁移已完成。
2. P1 全模块承接验证技术工作已完成，阶段关闭待项目负责人确认。
3. P2 准备段已完成，真人执行段尚未启动；未获批准不得开展实测。
4. 旧双仓推进材料统一从 [`docs/README.md`](../README.md) 的历史方案区进入，不得作为当前执行计划。

## 命名约束

- `Platform` / `Storefront MiniApp` 是产品角色，不是仓库 slug。
- `YunxiBakeBot` / `YunxiBakeMiniApp` 只用于仓库路径、历史过渡材料或明确的迁移引用。
- 新文档默认使用通用名，除非在讲历史仓、文件路径或兼容层命名。

如需回看双仓推进与 MiniApp 对齐的历史过渡材料，请统一从 [docs/README.md](../README.md) 的“已归档方向”区进入，避免把这些历史文档当作当前实施依据。
