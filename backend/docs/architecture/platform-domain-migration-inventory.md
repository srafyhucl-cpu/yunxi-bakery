# Platform 领域迁移盘点

本文件记录 `Platform` 仓内部从历史 `miniapp_*` 命名继续收口到 canonical 领域的当前盘点结果。它不是新的接口契约；外部路径仍以 `docs/architecture/platform-miniapp-api-contract-v1.md` 为准。

## 结论

- `app/service/miniapp_*.py` 当前已经退化为兼容 facade，只做旧类名、常量或函数名导出。
- 真实服务实现已主要落在 `customer / order / catalog / conversation / channels/storefront / integrations / ops`。
- 订单域、前台认证服务和 MiniApp API 内部默认用户已经改为依赖 `app.constants.storefront`，`app.constants.miniapp` 只保留兼容导出。
- 服务测试文件名和商品测试 helper 已切到 canonical 语义；API 测试继续保留 `test_miniapp_*`，因为它们验证 `/api/v1/miniapp/*` 外部契约。
- `app/api/channels/storefront/*` 已承载前台 API 真实实现，`app/api/miniapp_*.py` 退为兼容导出；外部 `/api/v1/miniapp/*` 路径保持不变，正式身份头为 Bearer，`x-miniapp-user-id` 仅保留为显式 legacy 兼容头。
- 后端主仓 API 目录已按职责统一为 `admin/`、`channels/storefront/`、`integrations/`；根目录旧 API 文件仅保留兼容模块别名，不再承载真实 Router。
- 下一阶段不应优先改 HTTP 路径、数据库表名或 MiniApp API 契约，而应继续压缩内部引用和文档入口里的历史命名。

## 当前分层现状

| 历史入口 | 当前 canonical 归属 | 现状判断 | 下一步 |
|---|---|---|---|
| `app/service/miniapp_auth.py` | `channels/storefront` | 纯 facade，导出 `StorefrontAuthService as MiniappAuthService` | 暂保留，禁止新代码依赖 |
| `app/service/miniapp_catalog.py` | `catalog` | 纯 facade，导出 `CatalogApplicationService` | 暂保留，测试逐步改用 `catalog` |
| `app/service/miniapp_order.py` | `order` | 纯 facade，导出 `OrderApplicationService` | 暂保留，测试逐步改用 `order` |
| `app/service/miniapp_payment.py` | `order` + `integrations` | facade，但仍集中导出较多支付常量 | 先把测试改到 `order.payment_state` / `order.payment_runtime` |
| `app/service/miniapp_address.py` | `customer` | 纯 facade，导出 `CustomerAddressService` | 暂保留，地址仓储和模型另行迁移 |
| `app/service/miniapp_chat.py` | `conversation` + `channels/storefront` | facade，保留 `MINIAPP_CHAT_CHANNEL` 兼容常量 | 暂保留，测试逐步改用 `StorefrontConversationService` |
| `app/service/miniapp_order_inventory.py` | `order` | 纯 facade | 测试改用 `app.service.order.inventory` |
| `app/service/miniapp_order_schedule.py` | `order` | 纯 facade | 测试改用 `app.service.order.schedule` |
| `app/service/miniapp_order_serialization.py` | `order` | 纯 facade | 测试改用 `app.service.order.serialization` |
| `app/service/miniapp_order_timeout.py` | `ops` | 纯 facade | 测试改用 `app.service.ops.order_timeout_scheduler` |

## 仍需收口的遗留点

### P0：保持稳定，不在下一步改

- `YunxiBakeBot` / `YunxiBakeMiniApp` 仓库路径名。
- 第三个总仓或 monorepo。
- `/api/v1/miniapp/*` HTTP 路径。
- `x-miniapp-user-id` 历史兼容请求头（仅当 `STOREFRONT_AUTH_ALLOW_LEGACY_HEADER=true` 时接受）。
- `miniapp_addresses`、`miniapp_address_audit` 数据库表名。
- 历史迁移文件名，例如 `v008_miniapp_addresses.sql`。
- `WECHAT_MINIAPP_*` 微信平台配置名。
- `app/service/miniapp_*.py` 兼容 facade。

这些名字承担兼容契约或历史迁移语义，贸然改动会增加联调、数据迁移和回滚风险。

### P1：内部依赖去 `miniapp` 化

- 已完成订单域默认用户和渠道常量切换到 `STOREFRONT_DEMO_USER_ID` / `STOREFRONT_CHANNEL`。
- 已完成 `miniapp_chat.py`、`miniapp_orders.py`、`miniapp_addresses.py` 内部默认用户切换到 `STOREFRONT_DEMO_USER_ID`。
- 已完成 `StorefrontAuthService` demo 用户前缀切换到 storefront 常量。
- 继续保持 `scripts/check_project.py` 的红线：`app` 内禁止导入 `app.service.miniapp_*`。

### P2：测试与 helper 命名收口

- 已新增 `tests/helpers/catalog_seed.py`，作为商品目录测试 canonical 造数入口。
- `tests/helpers/miniapp_catalog_seed.py` 保留为 API 契约测试兼容入口。
- 服务测试已从 `test_miniapp_*` 分批重命名为 `test_customer_address.py`、`test_catalog.py`、`test_catalog_item_base_category.py`、`test_storefront_conversation.py`、`test_order.py`。
- API 测试文件名继续保留 `test_miniapp_*`。

### P3：压缩 `app/service/miniapp_*.py` facade

- 已审计 `app/service/miniapp_*.py`，当前均为薄兼容导出。
- `lifespan` 真实装配继续优先使用 canonical service/repo key，旧 key 只通过集中 alias map 保留兼容。
- 新代码仍不得新增 `app.service.miniapp_*` 依赖。

### P4：API 文件夹切换

已引入：

```text
app/api/
  admin/
    root.py
    addresses.py
    assets.py
    config.py
    dialog.py
    frontend.py
    knowledge.py
    observability.py
    orders.py
    products.py
    shop_pages.py
    transfer.py
  channels/
    storefront/
      auth.py
      addresses.py
      catalog.py
      chat.py
      orders.py
      payments.py
    router.py
  integrations/
    youzan_webhook.py
    webhook_helpers.py
    wecom.py
  admin_*.py
  channel_router.py
  miniapp_auth.py
  miniapp_addresses.py
  miniapp_catalog.py
  miniapp_chat.py
  miniapp_orders.py
  miniapp_payments.py
  webhook.py
  webhook_helpers.py
  wecom.py
```

- `channels/storefront/*` 已承载真实前台 API 实现。
- `miniapp_*.py` 已退为兼容 wrapper，只 re-export 旧函数名。
- `admin/*` 已承载后台 API 真实实现，旧 `admin_*.py` 根文件只作为兼容模块别名。
- `integrations/*` 已承载有赞 Webhook、Webhook helper 和企微回调真实实现，旧 `webhook.py`、`webhook_helpers.py`、`wecom.py` 只作为兼容模块别名。
- `channels/router.py` 已承载渠道聚合路由，旧 `channel_router.py` 只作为兼容模块别名。
- `lifespan_routes.py` 已优先导入 canonical API router。
- `scripts/check_project.py` 已新增红线：`根 API 兼容文件仅作为兼容入口`。
- 在明确 H5 或多渠道前台需求前，仍不新增 `/api/v1/storefront/*`。

### P5：SaaS / 多租户阶段再评估

- 是否把 `/api/v1/miniapp/*` 对外路径另起 `/api/v1/storefront/*`。
- 是否改仓库 slug。
- 是否彻底移除 `x-miniapp-user-id` legacy 兼容头，并统一到多渠道 Bearer 身份模型。
- 是否引入租户级配置目录，或把 `Yunxi` 全部降级为 seed data / tenant config。
- 是否新增更多 `tenant_id` 隔离策略。
- 是否将前台渠道从微信小程序扩展到 H5、抖音、小红书或其他入口。

这些属于渠道产品化阶段，不应混入当前内部领域治理。

## 建议执行批次

1. **已完成：订单域前台渠道常量收口**
   - `order` 域不再直接导入 `app.constants.miniapp`。

2. **已完成：MiniApp API 内部默认用户常量收口**
   - 文件名、路由路径、请求头不变，默认用户值来自 storefront 常量。

3. **已完成：商品测试 helper canonical 命名**
   - 服务测试使用 `tests.helpers.catalog_seed`，API 测试保留旧兼容 helper。

4. **已完成：服务测试文件命名迁移**
   - 服务测试文件名表达 `customer / catalog / storefront / order` 领域。

5. **已完成：miniapp service facade 审计**
   - 未发现仍承载真实逻辑的 facade。

6. **已完成：后端 API 目录统一**
   - 真实 API 实现已迁入 `admin/`、`channels/storefront/`、`integrations/` canonical 目录，根目录历史 API 文件保留为兼容导出。

## 验证要求

- 架构红线：
  - `rg "from app\.repository" app/api --include="*.py"` 必须零输出。
  - `rg "import aiosqlite|\.execute\(|\.fetchone\(|\.fetchall\(" app/service --include="*.py"` 必须零输出或只剩已知合规封装。
  - `rg "from app\.(service|repository|api)" app/models --include="*.py"` 必须零输出。
  - `python scripts/check_project.py` 必须通过。
- 回归测试：
  - 地址：`tests/service/test_customer_address.py`、`tests/api/test_miniapp_address_api.py`、`tests/api/test_admin_address_api.py`。
  - 商品：`tests/service/test_catalog.py`、`tests/service/test_catalog_item_base_category.py`、`tests/api/test_miniapp_catalog_api.py`。
  - 订单与支付：`tests/service/test_order.py`、`tests/api/test_miniapp_order_api.py`、`tests/api/test_miniapp_payment_api.py`。
  - 会话：`tests/service/test_storefront_conversation.py`、`tests/api/test_miniapp_chat_api.py`。
  - 路由装配：`tests/test_lifespan_routes_services.py`。

## 当前判断

`Platform` 的服务层、服务测试和后端 API 真实实现目录已经完成本轮收口。短期只应继续压内部新增依赖和文档入口，不应改仓库名、外部 MiniApp API、请求头、历史表名、迁移文件或微信平台配置名。`/api/v1/storefront/*` 属于多渠道产品化阶段，需要单独设计和验收。
