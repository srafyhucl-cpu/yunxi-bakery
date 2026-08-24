# Bakery Commerce Platform 项目边界

相关长期决策见：[ADR 0002：采用逻辑总项目 + 双仓边界，并将 Yunxi 降级为实例名](../harness-engineering/adr/0002-platform-storefront-boundaries-and-instance-naming.md)

## 定位

- `Bakery Commerce Platform`
  - 通用产品级逻辑总项目。
  - 当前不新建第三个代码仓，只用来统一命名、边界和文档口径。
- `Platform` 仓
  - 当前代码仓：`YunxiBakeBot`
  - 承担经营中枢、业务真相源、后台与集成主仓职责。
- `Storefront MiniApp` 仓
  - 当前代码仓：`YunxiBakeMiniApp`
  - 承担消费者前台渠道职责。
  - 这里的名称是角色口径，不是产品名；仓库路径名只是历史实现载体。
- `Yunxi`
  - 首个真实落地实例、配置集合、迁移来源和样板客户名。
  - 不是产品名，也不是长期能力命名。

## Platform 仓职责

- 客户主档、客户迁移、企微绑定、CRM
- 商品主档、分类、同步消费
- 订单主档、支付、履约、退款、事件流
- AI 会话、人工接管、运营规则
- 店铺配置、装修配置、管理后台
- 有赞、企微、支付通知、Webhook 集成

## Storefront MiniApp 仓职责

- 页面、组件、交互、微信能力
- 购物车、下单页、用户订单页、地址页
- API client、登录态、本地缓存
- 用户侧客服入口展示

## Platform 内部 canonical 领域

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
- [有赞客户迁移后核对脚本](../../scripts/verify_youzan_customer_import.py)
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

## 推进顺序

> 说明：下面的“推进顺序”描述的是历史上的分阶段路线，不等于当前仍在执行的最新方案。当前真实现状以 `Platform` 已完成 canonical 收口、`MiniApp` 保留前台渠道与兼容边界为准。

- `Platform` 可以先继续做第二阶段内部收口，不依赖 `MiniApp` 先完成大改。
- `MiniApp` 历史上曾需要补一轮轻量第一阶段对齐，用来校正边界认知；如果当前仍有旧文档引用它，应按过渡态理解。
- 双仓联动治理、仓库改名和接口统一，属于后续评估项，不应被误读为已经开始的实施动作。

## 命名约束

- `Platform` / `Storefront MiniApp` 是产品角色，不是仓库 slug。
- `YunxiBakeBot` / `YunxiBakeMiniApp` 只用于仓库路径、历史过渡材料或明确的迁移引用。
- 新文档默认使用通用名，除非在讲历史仓、文件路径或兼容层命名。

如需回看双仓推进与 MiniApp 对齐的历史过渡材料，请统一从 [docs/README.md](../README.md) 的“历史方案”区进入，避免把这些历史文档当作当前实施依据。
