# Storefront MiniApp AI 接力计划书（历史过渡版）

> 说明：这是一份给历史阶段 MiniApp 侧 AI 使用的执行计划，主要服务于边界对齐过渡期。当前如果是理解系统职责，优先看 `docs/architecture/project-boundaries.md`。本文保留作历史过渡记录，不作为当前实施蓝图。

## 目标

这份计划书原本是给 `YunxiBakeMiniApp` 仓 AI 直接执行的。

当时的目标不是让 `MiniApp` 立刻重写业务，而是让它在不破坏现有前台流程的前提下，完成和 `Platform` 仓的边界对齐，并为后续双仓联动治理做好准备。

一句话目标：

- `YunxiBakeMiniApp` 当时继续承担 `Storefront MiniApp` 渠道仓职责。
- `Platform` 仓承担客户、商品、订单、支付、后台配置与 AI 会话等业务真相。
- `MiniApp` 只负责页面、交互、微信能力、API client 和前端适配，不再沉淀业务真相。

## 历史 Platform 状态摘录

在当时的 `Platform` 仓（仓库名仍为 `YunxiBakeBot`）内，以下 canonical 领域已经完成一轮真实收口：

- `catalog`
- `customer`
- `order`
- `conversation`
- `channels/storefront`
- `ops`

其中 `order` 域当前已经直接承接：

- 下单创建
- 支付准备
- mock 支付确认
- 微信支付通知入口
- 用户取消订单
- 后台状态流转
- 后台关闭未支付
- 批量扫描超时未支付

同时，`app/service` 目录下原有 `miniapp_*.py` 现在都只是兼容 facade，不再承载真实实现。

并且，微信支付签名、预下单、通知验签/解密等第三方支付适配已经开始往 `integrations` 域收口。

对当时的 `MiniApp` 来说，这意味着一件事：

- 订单、支付、地址、商品相关业务规则真相都应继续留在 `Platform`。
- `MiniApp` 只消费现有 API，不要再在前台复制规则。

如果当时要接手的是“客户迁移闭环”相关工作，先看这四段当前权威材料：

- [有赞客户迁移审计清单](./youzan-customer-migration-audit-checklist.md)
- [有赞客户正式迁移执行 Runbook](./youzan-customer-formal-import-runbook.md)
- `scripts/verify_youzan_customer_import.py`
- [有赞客户迁移交接与回滚 Runbook](./youzan-customer-import-handoff-and-rollback-runbook.md)

## MiniApp 侧历史任务边界摘录

### 当时在范围内

- README / 文档 / 架构口径统一
- API client 目录梳理
- 登录、商品、地址、订单、客服等前台调用层的边界对齐
- 明确哪些逻辑只是前端适配，哪些逻辑应回 `Platform`
- 为后续双仓联动准备命名映射和接口消费约定

### 当时不在范围内

- 不重写页面
- 不重做 UI
- 不改稳定的用户流程
- 不在前台新增客户主档逻辑
- 不在前台新增订单规则真相
- 不在前台新增商品规则真相
- 不把后台配置迁回前台仓

## 历史执行原则摘录

1. 先校正命名和边界，再动代码结构。
2. 先标记“哪些逻辑不该继续长在前台”，再决定是否迁移。
3. 能由 `Platform` 统一的规则，不要在 `MiniApp` 保留第二份。
4. 保持前台 API 契约和用户流程稳定，不做无收益大改。

## 历史执行模式摘录

当时推荐那边 AI 按这个节奏工作：

1. 先盘点
2. 再出边界结论
3. 再做最小改动
4. 最后产出清单和建议

当时不建议的做法：

- 一上来就重命名大量目录
- 一上来就改页面结构
- 一上来就删除看起来“像业务逻辑”的所有代码
- 在没有梳理 API client 之前，直接判断某段逻辑一定可以删

## 历史推荐执行顺序摘录

### 阶段 1：仓内定位对齐（历史摘录）

1. 更新 `README.md`
2. 新增或更新边界文档
3. 统一文档中的命名口径

完成定义（历史）：

- 打开仓库首页就能看出这是 `Storefront MiniApp`
- 文档中明确 `Yunxi` 是实例名，不是产品总名
- 文档中明确 `Platform` 是业务真相源

### 阶段 2：API client 与目录口径对齐（历史摘录）

1. 找到 API 请求目录
2. 给请求目录补说明文档或 README
3. 标记哪些是前端适配，哪些混入了业务规则
4. 把命名逐步改成 `storefront` / `platform api client` 语义

完成定义（历史）：

- API client 层只负责请求封装、参数组织、响应适配
- 不再把前台请求层当作业务真相落点

### 阶段 3：业务真相回流风险排查（历史摘录）

逐项检查以下模块中是否存在“前台自行定义业务规则”的情况：

- 商品列表 / 商品详情
- 购物车 / 价格计算展示
- 地址管理
- 订单状态展示
- 支付准备
- 客服入口
- 登录态 / 用户标识绑定

重点识别三类代码：

- 前台自己判断订单状态流转是否合法
- 前台自己维护商品可售、库存、分类规则
- 前台自己维护客户主档或 CRM 字段真相

处理原则：

- 能删的业务规则判断直接删，改为信任 `Platform` 返回
- 不能立刻删的，先打标记并在文档中列为后续迁移项

### 阶段 4：前台命名与封装收敛（历史摘录）

如果仓内存在类似命名，优先往下面的方向靠：

- `miniappAuth` → `storefrontAuth`
- `miniappChat` → `storefrontConversation`
- `miniappOrderApi` → `platformOrderApi`
- `miniappCatalogApi` → `platformCatalogApi`

注意：

- 这一步是“封装与命名收敛”，不是要求改所有历史目录名
- 可以先做 facade / alias，避免一次性大改

### 阶段 5：输出双仓联动准备物（历史摘录）

MiniApp 仓完成后，至少应补出两份东西：

1. `Platform API` 消费清单
2. 前台遗留业务规则清单

建议格式：

- 当前调用了哪些 `/api/v1/miniapp/*` 接口
- 每个接口被哪些页面或模块消费
- 哪些前台逻辑只是展示适配
- 哪些前台逻辑其实应迁回 `Platform`

## 历史建议落地文件摘录

如果想用最小改动完成这一轮，建议优先修改这些文件：

1. `README.md`
2. `docs/architecture/project-boundaries.md` 或同等边界文档
3. API client 所在目录说明文档
4. 开发规范文档中的“职责禁区”部分
5. 如有统一请求封装目录，补一份 `Platform API` 消费说明

## 历史建议先检查的文件或目录摘录

建议那边 AI 优先查看这些位置：

1. `README.md`
2. `package.json` 或项目入口配置
3. API 请求封装目录
4. 登录、订单、商品、地址、支付、客服相关页面或 hooks
5. 项目内已有 `docs/`、开发规范、目录说明

目的不是一次性重写，而是先确认：

- 当前仓是怎么组织 API client 的
- 哪些地方已经只是展示适配
- 哪些地方还混着规则判断
- 哪些命名仍把前台仓写成“主仓”

## 给 MiniApp 仓 AI 的历史示例要求摘录

可以直接把下面这段发给那边的 AI：

```md
请你在当前仓内执行一轮“Storefront MiniApp 边界对齐”，目标不是重写业务，而是把当前仓明确收敛为前台渠道仓。

要求：

1. 先阅读 README、项目结构和现有 API 请求目录。
2. 判断当前仓哪些部分属于：
   - 页面 / 组件 / 交互 / 微信能力
   - API 调用封装 / 响应适配
   - 错误混入的业务规则真相
3. 优先完成：
   - README 命名口径统一
   - 边界文档补齐
   - API client 角色说明补齐
   - 禁区清单补齐
4. 如果发现前台自行维护订单、商品、客户规则：
   - 不要直接大改业务
   - 先打标签、列迁移清单、必要时用 facade 收敛命名
5. 保持现有页面和用户流程稳定，不做无必要 UI 改造。

背景：

- Platform 仓已经把 catalog / customer / order 做了一轮真实收口。
- 订单域已经承接创建、支付准备、mock 支付、微信支付通知、取消、状态流转、未支付关闭等核心入口。
- MiniApp 应继续作为消费者前台渠道仓，只消费 Platform API，不新增业务真相。

交付物：

1. 改完的 README
2. 一份边界文档
3. 一份 API client 角色说明
4. 一份前台遗留业务规则清单
5. 一份四段闭环执行顺序
```

## 历史回传格式摘录

建议要求那边 AI 最后按这个格式回传：

1. 本轮修改了哪些文件
2. 哪些改动属于文档口径统一
3. 哪些改动属于 API client 边界对齐
4. 哪些前台逻辑被识别为“业务真相回流风险”
5. 哪些逻辑本轮不动，只登记为后续迁移项
6. 跑了哪些校验命令
7. 还剩哪些风险或待 Platform 配合项

如果它没有给出“遗留业务规则清单”和“待 Platform 配合项”，就说明这轮输出还不够完整。

## MiniApp 仓历史验收标准摘录

完成后用下面清单验收：

- README 是否明确这是 `Storefront MiniApp`
- 文档是否明确 `Platform` 是业务真相源
- API client 说明是否明确“这里只消费平台能力”
- 是否已经标出前台遗留业务规则，而不是继续把它们当正常代码
- 是否补出禁区清单，避免未来需求继续长回前台仓
- 是否没有破坏现有页面和用户流程

## 与 Platform 的历史接口协作约束摘录

MiniApp 仓本轮默认不要求改这些：

- `/api/v1/miniapp/catalog/*`
- `/api/v1/miniapp/addresses/*`
- `/api/v1/miniapp/orders/*`
- `/api/v1/miniapp/payments/*`
- `/api/v1/miniapp/auth/*`
- `/api/v1/miniapp/chat/*`

也就是说：

- 这一轮重点是“前台认边界”
- 不是“Platform 改接口、MiniApp 同步重写”

## 需要回传给 Platform 的历史配合信息摘录

如果那边 AI 在 MiniApp 仓里发现以下情况，需要单独列出来回传：

- 某个页面依赖了前台自算订单状态
- 某个页面依赖了前台自算商品可售或库存状态
- 某个 API 响应字段命名让前台不得不补第二份规则
- 某个登录态或用户标识绑定逻辑不够清晰
- 某个客服入口或支付准备流程仍存在双边职责不清

这些不是让 MiniApp 直接硬改，而是作为下一轮双仓联动的输入。

## 后续联动建议（历史摘录）

等 MiniApp 仓完成这轮后，再进入下一轮双仓联动：

1. 对齐 `auth` / `conversation` 的命名口径
2. 梳理 API 契约映射表
3. 评估哪些前台适配层需要进一步抽 facade
4. 再考虑仓库 rename、CI、部署链路和环境口径统一
