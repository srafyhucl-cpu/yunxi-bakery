# Customer Master v1

## 文档目的

这份文档用于定义 `Platform.customer` 域的第一版客户主档方案，服务当前最现实的目标：

- 先看清有赞客户结构是否可迁
- 先建立一套不会误合并的客户主档底盘
- 先为后续企微绑定、小程序身份挂接、CRM 演进留接口

本文件不是完整 CRM 设计，也不是会员体系重构设计。它只回答：

1. 首版客户主档为什么要新建而不是复用现有画像表
2. 主档、身份、来源快照三层应该怎么拆
3. 首版字段哪些进入主档，哪些只保留为来源快照
4. 自动合并为什么先只认手机号
5. 有赞客户迁移审计如何落到这套结构上

## 适用范围

- 当前 `Platform` 代码仓路径：`YunxiBakeBot`
- 当前逻辑总项目：`Bakery Commerce Platform`
- 当前首个实例：`Yunxi`
- 当前目标阶段：迁移底盘优先，不做完整 CRM 一步到位

## 设计结论

`customer master v1` 采用下面的组合：

- 目标形态：轻量迁移底盘型
- 身份策略：有主档表，但自动合并规则首版只认手机号
- 第一用途：迁移对账，而不是直接做经营运营面板

换句话说，这一版优先解决的是：

- 这个客户能不能稳定迁
- 这个客户在不同来源下是否大概率是同一个人
- 哪些数据可以自动归并，哪些必须待人工确认

而不是立刻解决：

- 完整会员运营
- 完整 CRM 标签体系
- 全渠道客户生命周期自动化

## 为什么不能直接复用 `customer_profiles`

当前仓内已经存在 `customer_profiles`，但它不适合作为 `customer master v1` 直接承接。

原因有 3 个：

1. 现有 `customer_profiles` 的定位是 AI 长期记忆画像
   - 主键是 `(channel, user_id)`
   - 本质是“某个渠道身份的会话画像”
   - 适合对话提示，不适合作为统一客户主档

2. 迁移主档的核心对象不是“某个渠道身份”，而是“一个逻辑客户”
   - 同一个人未来可能同时拥有
     - 有赞客户身份
     - 小程序 `openid`
     - 企微外部联系人
     - 线下订单手机号

3. 如果把画像表硬升级成主档，会把 AI 记忆和 CRM 身份真相混在一起
   - 后续难以审计
   - 难以解释字段覆盖规则
   - 更不利于后续 SaaS 化

所以结论很明确：

- `customer_profiles` 保留为 AI 画像层
- `customer master v1` 新建客户主档层

## 三层结构

`customer master v1` 建议拆成 3 层。

### 1. `customer_master`

作用：

- 表示一个逻辑客户
- 承载稳定主档字段
- 保存最终归并结果

约束：

- 一条逻辑客户一行
- 不直接承接来源系统大而杂的运营字段

### 2. `customer_identity_links`

作用：

- 表示这个逻辑客户挂接了哪些身份来源
- 为未来小程序、企微、订单、导入工具统一身份入口

约束：

- 首版允许一客多身份
- 首版自动并人只使用手机号
- 其他身份先挂接，不参与自动合并

### 3. `customer_source_snapshots`

作用：

- 保留来源系统的原始快照和标准化快照
- 为迁移审计、回溯、补字段和纠错提供依据

约束：

- 它是“来源留痕层”，不是主档真相层
- 有赞会员等级、积分、储值、标签等字段优先进这一层

## 三层职责边界

| 层 | 代表什么 | 是否是长期真相 | 典型来源 |
| --- | --- | --- | --- |
| `customer_master` | 一个逻辑客户 | 是 | Platform customer 域 |
| `customer_identity_links` | 客户与多来源身份的绑定关系 | 是 | 有赞 / MiniApp / 企微 / 导入 |
| `customer_source_snapshots` | 某次导入时来源系统长什么样 | 否 | CSV 导出、API 拉取、手工导入 |

## `customer_master` 首版字段建议

首版主档只放稳定、跨渠道、低争议的字段。

### 建议进入主档的字段

#### 身份与状态

- `customer_id`
- `tenant_id`
- `status`
  - `active / merged / archived`
- `merge_into_customer_id`

#### 主联系人

- `primary_phone`
- `phone_verified`
- `display_name`
- `gender`
- `birthday`
- `wechat_region`

#### 来源与时间

- `first_seen_at`
- `last_seen_at`
- `first_source`
  - `youzan / miniapp / wecom / import / manual`
- `created_at`
- `updated_at`

#### 迁移判断辅助

- `has_youzan_identity`
- `has_miniapp_identity`
- `has_wecom_identity`
- `identity_confidence`
  - `high / medium / low`

### 首版不建议直接进入主档的字段

下面这些字段当前更适合作为来源快照，而不是统一主档真相：

- 会员状态
- 成长值
- 免费等级 / 付费等级
- 权益卡
- 积分
- 储值余额
- 消费次数
- 消费金额
- 累计退款金额
- 累计退款订单数
- 标签原文
- 导购员 / 分销员
- 来源方式
- 公众号关注信息
- 最近浏览时间
- 指定时间消费次数 / 金额

原因：

1. 这些字段高度依赖来源系统口径
2. 不同来源间语义不统一
3. 过早进入主档会导致字段覆盖和解释困难

结论：

- `customer_master` 回答“这个人是谁”
- `customer_source_snapshots` 回答“这个人当时在有赞长什么样”

## `customer_identity_links` 设计建议

这张表是首版最关键的表，因为它决定未来是否能稳定承接多来源身份。

### 建议字段

#### 关联主键

- `id`
- `tenant_id`
- `customer_id`

#### 身份来源

- `identity_type`
  - `phone`
  - `youzan_customer`
  - `miniapp_openid`
  - `wecom_external_user`
  - `wecom_union`
  - `manual`
- `identity_value`
- `identity_value_normalized`

#### 来源信息

- `source_system`
  - `youzan / miniapp / wecom / import`
- `source_record_id`
- `source_label`

#### 可信度与绑定状态

- `link_status`
  - `active / pending_review / rejected / merged`
- `verification_status`
  - `unverified / inferred / verified / manual_confirmed`
- `confidence_score`

#### 时间与审计

- `first_seen_at`
- `last_seen_at`
- `created_at`
- `updated_at`

## 为什么首版自动合并只认手机号

结论先行：

- 首版自动并人规则只认标准化手机号
- `openid`、企微 `external_userid`、有赞内部客户 ID 先只做挂接，不参与自动并人

原因有 4 个：

1. 手机号是当前最可能横跨有赞、订单、企微导流的公共字段
2. `openid` 只代表小程序身份，不天然等于有赞客户身份
3. 企微 `external_userid` 只代表企微联系人身份，不应自动映射到有赞客户
4. 昵称、姓名、标签都太脏，误合并风险极高

## 首版自动合并规则

建议首版规则固定如下：

1. 同租户导入新来源记录时，先提取标准化手机号
2. 如果手机号为空，不自动合并
3. 如果手机号唯一命中一个主档，自动挂接到该 `customer_id`
4. 如果同手机号命中多个主档，标记 `pending_review`
5. 其他身份只挂接，不参与自动并人

### 设计原则

- 自动合并只做“明显正确”的事
- 只要有歧义，就停止自动归并
- 宁可多出待确认客户，也不要把两个不同的人并成一个人

## `customer_source_snapshots` 设计建议

这张表的作用不是再造客户主档，而是留存来源真相。

### 建议字段

#### 关联信息

- `id`
- `tenant_id`
- `customer_id`
- `identity_link_id`

#### 来源信息

- `source_system`
- `source_object_type`
  - `customer / order_buyer / member / contact`
- `source_record_id`
- `source_batch_id`

#### 快照内容

- `snapshot_json`
  - 原始来源记录整体保留
- `normalized_json`
  - 标准化字段快照
- `field_hash`

#### 审计信息

- `captured_at`
- `created_at`

## 与当前导出字段的映射原则

### 建议进主档的有赞字段

从当前客户导出里，首版优先提取这些字段进入主档：

- `客户手机号` → `primary_phone`
- `客户姓名` / `客户昵称` → `display_name`
- `客户生日` → `birthday`
- `客户性别` → `gender`
- `微信地域` → `wechat_region`
- `成为客户时间` → `first_seen_at`
- `上次消费时间` → `last_seen_at`
- `来源渠道` → `first_source`

### 建议只进快照层的有赞字段

- `标签`
- `是否会员`
- `成长值`
- `免费等级`
- `付费等级`
- `权益卡`
- `客户积分`
- `客户储值余额`
- `消费次数`
- `消费金额`
- `累计退款金额`
- `累计退款订单数`
- `笔单价`
- `来源方式`
- `导购员`
- `分销员`
- `公众号`
- `公众号关注时间`
- `最近浏览时间`

## 与当前订单数据的关系

客户迁移不能只看客户表，后续应结合订单表辅助判断。

订单表当前最有价值的辅助字段包括：

- `买家手机号`
- `买家昵称`
- `订单创建时间`
- `买家是否会员`
- `订单实收金额`
- `交易成功时间`

但在 `customer master v1` 阶段，这些字段的作用主要是：

- 辅助校验手机号是否稳定
- 辅助识别客户活跃度
- 为后续人工审计提供证据

而不是直接拿来覆盖主档。

## 首版迁移流程

首版不建议直接做“正式迁移”，建议先跑一轮“迁移审计 + 试归并”。

### 审计入口与正式入口分工

当前已经有两条脚本链路，职责不要混用：

- 审计入口：`python scripts/audit_youzan_customer_migration.py`
  - 负责读取有赞客户 / 订单导出，输出汇总、问题和分流结果。
  - 适合做结构审计、字段对齐和试导入实验。
- 正式入口：`python scripts/import_youzan_customers.py`
  - 负责把审计结果落到 `customer master v1` 四表。
  - 默认只做 `dry-run`，显式加 `--apply` 才写库。
  - 如果目标数据库不存在，只有在明确允许创建时才使用 `--allow-create`。

建议的执行顺序仍然是：

1. 先跑审计入口，确认手机号标准化、分流和风险样本。
2. 再跑正式入口的 `dry-run`，确认目标数据库、批次号和输出路径。
3. 最后显式 `--apply` 执行真实迁移。

### 第一步：导入来源快照

- 将有赞客户 CSV 每一行先落为 `customer_source_snapshots`
- 这一层先保真，不做复杂合并逻辑

### 第二步：提取标准化身份

- 从快照中提取手机号、昵称、姓名、生日、性别、来源时间
- 建立 `customer_identity_links`
- 对手机号做标准化处理

### 第三步：建立或命中主档

- 唯一手机号命中：自动挂到现有 `customer_id`
- 无手机号：新建弱身份客户或待人工确认
- 同手机号冲突：标记 `pending_review`

### 第四步：生成迁移审计结果

至少输出：

- 自动归并成功数
- 无手机号客户数
- 手机号冲突数
- 疑似一人多身份数
- 待人工确认数

### 第五步：再决定是否进入正式迁移

先拿到审计结果，再决定：

- 客户迁移先迁哪些
- 企微导流后如何绑定
- CRM 首批运营能力覆盖哪些客户

## 第一轮客户结构审计只回答什么

第一轮审计建议只回答下面 6 个问题：

1. 当前有赞客户总数是多少
2. 有手机号客户占比是多少
3. 手机号去重后的唯一客户数是多少
4. 无手机号客户数是多少
5. 同手机号对应多客户的数量是多少
6. 哪些字段只能保留为快照，不能直接进入主档真相

## 审计结果如何映射到主档

- 唯一手机号客户
  - 可以自动建主档并归并
- 无手机号客户
  - 只能先建弱身份客户，后续等企微或订单补强
- 同手机号多客户
  - 标记 `pending_review`
- 会员 / 积分 / 储值 / 标签
  - 进 `customer_source_snapshots`
  - 暂不进入 `customer_master`

## 与后续企微、小程序的衔接方式

这套结构的价值，在于后续可以自然扩展：

- 小程序登录后
  - 增加一个 `miniapp_openid` 身份链接
- 客户加企微后
  - 增加一个 `wecom_external_user` 身份链接
- 如果手机号与现有主档唯一命中
  - 挂到现有 `customer_id`
- 如果无法唯一命中
  - 先作为新身份待确认

所以后续不是再造客户，而是给同一个 `customer_id` 继续挂身份。

## v1 不做什么

为了避免过度设计，首版明确不做：

- 不做完整 CRM 页面
- 不做自动会员价值分层
- 不做复杂多条件自动并人
- 不做积分、储值、会员权益统一真相重算
- 不把 `customer_profiles` 直接改造成 CRM 主档

## 当前闭环顺序

当前按下面顺序执行：

1. 先做有赞客户迁移审计
2. 再跑正式迁移 dry-run / apply
3. 再做迁移后批次核对
4. 出现异常时按交接/回滚 runbook 处理
5. 最后再接企微绑定与 CRM 首版能力

## 当前权威入口

在本文件之后，直接按下面四个入口继续：

不要再回双仓历史过渡方案或 MiniApp 旧执行清单里寻找客户迁移步骤，迁移执行以这四段闭环为准。

1. [有赞客户迁移审计清单](./youzan-customer-migration-audit-checklist.md)
   - 明确统计口径、输出字段和风险分类
2. [有赞客户正式迁移执行 Runbook](./youzan-customer-formal-import-runbook.md)
   - 明确审计、dry-run、apply、报告留档和重跑语义
3. `scripts/verify_youzan_customer_import.py`
   - 明确迁移后批次核对和 apply 报告对账
4. [有赞客户迁移交接与回滚 Runbook](./youzan-customer-import-handoff-and-rollback-runbook.md)
   - 明确 apply 后异常中止、交接证据、同批次重跑和恢复优先级
