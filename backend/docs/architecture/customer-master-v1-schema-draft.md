# Customer Master v1 Schema Draft

## 文档目的

这份文档把 `docs/architecture/customer-master-v1.md` 里的主档思路进一步收口成可落库的表结构草案。

它服务两个直接目标：

- 让后续 `app/migrations/schema.py` 落地时有一份明确底稿
- 让有赞客户迁移脚本、企微绑定和后续人工复核流程围绕同一套表结构推进

这仍然不是完整 CRM schema。

这份草案只定义 `customer master v1` 的最小闭环：

- 主档怎么存
- 多身份怎么挂
- 来源快照怎么留
- `pending_review` 怎么进入人工复核闭环

## 适用范围

- 当前 `Platform` 代码仓路径：`YunxiBakeBot`
- 当前 customer 域阶段：迁移底盘优先
- 当前数据库：SQLite
- 当前首个实例：`Yunxi`

## 设计结论

`customer master v1` 采用 4 张表闭环，而不是 3 张极简表，也不是更重的导入任务模型：

1. `customer_master`
2. `customer_identity_links`
3. `customer_source_snapshots`
4. `customer_merge_reviews`

这样做的原因很直接：

- 3 张表不够承接 `pending_review` 的人工决策留痕
- 5 张及以上会过早引入导入任务编排复杂度
- 4 张表刚好覆盖“主档真相、身份绑定、来源留痕、人工复核”四个核心职责

## 总体关系

```text
customer_master
  1 ── N customer_identity_links
  1 ── N customer_source_snapshots
  1 ── N customer_merge_reviews

customer_identity_links
  1 ── N customer_source_snapshots

customer_merge_reviews
  可同时引用:
  - source_customer_id
  - target_customer_id
  - primary_identity_link_id
```

## 统一约束原则

后续正式落库时，4 张表建议统一遵守下面的规则：

1. 主键优先使用 `TEXT`
   - 与现有仓内 `sessions`、`customer_profiles` 等主键风格保持一致
   - 便于后续从脚本或服务层生成稳定 ID

2. 时间统一存 `TEXT`
   - 与现有 SQLite schema 风格一致
   - 建议保存 ISO 8601 或当前项目已使用的统一时间字符串

3. JSON 字段统一存 `TEXT`
   - 默认值明确写成 `'{}'` 或 `'[]'`
   - 由 service 层负责序列化和反序列化

4. 首版所有租户数据都带 `tenant_id`
   - 即使当前只有 `Yunxi` 一个实例，也不省略
   - 这样后面扩成 SaaS 时不用回头补列

5. 首版尽量不用数据库触发器做复杂业务判断
   - 约束放在唯一索引、`CHECK` 和 service 层编排里
   - 保持迁移和排障可解释

## 表 1：`customer_master`

### 职责

这张表代表“一个逻辑客户”。

它只保存低争议、跨渠道、可稳定解释的主档字段，不直接承接有赞会员运营宽字段。

### 建议字段

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `id` | `TEXT` | 是 | 主档主键，建议命名为 `customer_id` 风格值 |
| `tenant_id` | `TEXT` | 是 | 租户 ID，当前 `Yunxi` 也必须显式保存 |
| `status` | `TEXT` | 是 | `active / merged / archived` |
| `merge_into_customer_id` | `TEXT` | 否 | 若本主档已被合并，指向最终保留的主档 |
| `primary_phone` | `TEXT` | 否 | 标准化手机号 |
| `phone_verified` | `INTEGER` | 是 | `0 / 1`，首版只表达真假 |
| `display_name` | `TEXT` | 否 | 主称呼，优先使用客户姓名，其次昵称 |
| `gender` | `TEXT` | 否 | `unknown / male / female / other` |
| `birthday` | `TEXT` | 否 | 保留文本时间，避免首版过早压死格式 |
| `wechat_region` | `TEXT` | 否 | 微信地域 |
| `first_seen_at` | `TEXT` | 否 | 首次成为客户时间或可确认的首次出现时间 |
| `last_seen_at` | `TEXT` | 否 | 最近活跃或最近消费时间 |
| `first_source` | `TEXT` | 否 | `youzan / miniapp / wecom / import / manual` |
| `identity_confidence` | `TEXT` | 是 | `high / medium / low` |
| `has_youzan_identity` | `INTEGER` | 是 | `0 / 1` |
| `has_miniapp_identity` | `INTEGER` | 是 | `0 / 1` |
| `has_wecom_identity` | `INTEGER` | 是 | `0 / 1` |
| `created_at` | `TEXT` | 是 | 创建时间 |
| `updated_at` | `TEXT` | 是 | 更新时间 |

### 主键与外键

- 主键：`PRIMARY KEY (id)`
- 自关联外键：`merge_into_customer_id -> customer_master.id`

### 必要约束

- `status` 只能取：
  - `active`
  - `merged`
  - `archived`
- `identity_confidence` 只能取：
  - `high`
  - `medium`
  - `low`
- `phone_verified` 只能取：
  - `0`
  - `1`
- `has_youzan_identity / has_miniapp_identity / has_wecom_identity` 只能取：
  - `0`
  - `1`

### 建议索引

| 索引名 | 字段 | 用途 |
| --- | --- | --- |
| `idx_cm_tenant_status` | `(tenant_id, status)` | 按租户查活跃主档 |
| `idx_cm_tenant_phone` | `(tenant_id, primary_phone)` | 按手机号命中主档 |
| `idx_cm_tenant_first_seen` | `(tenant_id, first_seen_at)` | 迁移审计和时间分布分析 |
| `idx_cm_tenant_last_seen` | `(tenant_id, last_seen_at)` | 活跃客户检索 |
| `idx_cm_merge_into` | `(merge_into_customer_id)` | 查询被合并链路 |

### 首版不做的唯一性约束

首版不建议在 `customer_master.primary_phone` 上直接加唯一索引。

原因：

- 合并过程里可能暂时存在多个弱身份主档
- `pending_review` 阶段可能会先建档再决策
- 真正的一致性应由 `customer_identity_links` 的身份唯一约束和 service 编排共同保证

## 表 2：`customer_identity_links`

### 职责

这张表代表“这个逻辑客户挂了哪些身份”。

它是 `customer master v1` 最关键的桥接层：

- 有赞内部客户 ID 挂这里
- 小程序 `openid` 挂这里
- 企微外部联系人 ID 挂这里
- 手机号身份也挂这里

### 建议字段

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `id` | `TEXT` | 是 | 身份链接主键 |
| `tenant_id` | `TEXT` | 是 | 租户 ID |
| `customer_id` | `TEXT` | 是 | 关联 `customer_master.id` |
| `identity_type` | `TEXT` | 是 | `phone / youzan_customer / miniapp_openid / wecom_external_user / wecom_union / manual` |
| `identity_value` | `TEXT` | 是 | 原始身份值 |
| `identity_value_normalized` | `TEXT` | 否 | 标准化身份值，手机号优先使用这一列做命中 |
| `source_system` | `TEXT` | 是 | `youzan / miniapp / wecom / import / manual` |
| `source_record_id` | `TEXT` | 否 | 来源系统记录 ID，例如有赞客户 ID |
| `source_label` | `TEXT` | 否 | 方便人工识别的来源备注 |
| `link_status` | `TEXT` | 是 | `active / pending_review / rejected / merged` |
| `verification_status` | `TEXT` | 是 | `unverified / inferred / verified / manual_confirmed` |
| `confidence_score` | `INTEGER` | 是 | `0-100` |
| `first_seen_at` | `TEXT` | 否 | 首次发现该身份的时间 |
| `last_seen_at` | `TEXT` | 否 | 最近一次看到该身份的时间 |
| `created_at` | `TEXT` | 是 | 创建时间 |
| `updated_at` | `TEXT` | 是 | 更新时间 |

### 主键与外键

- 主键：`PRIMARY KEY (id)`
- 外键：`customer_id -> customer_master.id`

### 必要约束

- `identity_type` 只能取：
  - `phone`
  - `youzan_customer`
  - `miniapp_openid`
  - `wecom_external_user`
  - `wecom_union`
  - `manual`
- `source_system` 只能取：
  - `youzan`
  - `miniapp`
  - `wecom`
  - `import`
  - `manual`
- `link_status` 只能取：
  - `active`
  - `pending_review`
  - `rejected`
  - `merged`
- `verification_status` 只能取：
  - `unverified`
  - `inferred`
  - `verified`
  - `manual_confirmed`
- `confidence_score` 限制在 `0` 到 `100`

### 建议唯一约束

首版建议把唯一性收在身份链接层，而不是主档层。

建议唯一约束如下：

1. `(tenant_id, identity_type, identity_value_normalized)`
   - 仅当 `identity_value_normalized` 非空时生效
   - 首要服务手机号和可标准化身份

2. `(tenant_id, identity_type, identity_value)`
   - 用于无法标准化但必须避免重复挂接的身份

如果后续正式落库时 SQLite 对部分唯一索引表达方式有限制，可以退化为：

- 保留 `(tenant_id, identity_type, identity_value)` 全量唯一
- 在 service 层优先写入标准化值，并把手机号原值与标准化值保持一致

### 建议索引

| 索引名 | 字段 | 用途 |
| --- | --- | --- |
| `idx_cil_customer` | `(customer_id)` | 查询某客户全部身份 |
| `idx_cil_tenant_type_norm` | `(tenant_id, identity_type, identity_value_normalized)` | 身份命中 |
| `idx_cil_tenant_status` | `(tenant_id, link_status)` | 查询待复核身份 |
| `idx_cil_source_record` | `(source_system, source_record_id)` | 从来源记录反查身份链接 |
| `idx_cil_seen_at` | `(tenant_id, last_seen_at)` | 按身份活跃时间筛选 |

## 表 3：`customer_source_snapshots`

### 职责

这张表保存来源系统原始真相和标准化真相。

它不是主档层，不参与自动并人，只负责：

- 留原始证据
- 支撑迁移审计
- 为后续字段补强和纠错提供回溯依据

### 建议字段

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `id` | `TEXT` | 是 | 快照主键 |
| `tenant_id` | `TEXT` | 是 | 租户 ID |
| `customer_id` | `TEXT` | 否 | 若已归档到主档则保存，否则允许为空 |
| `identity_link_id` | `TEXT` | 否 | 若已命中身份链接则保存，否则允许为空 |
| `source_system` | `TEXT` | 是 | `youzan / miniapp / wecom / import / manual` |
| `source_object_type` | `TEXT` | 是 | `customer / order_buyer / member / contact` |
| `source_record_id` | `TEXT` | 是 | 来源记录主键或导出主键 |
| `source_batch_id` | `TEXT` | 是 | 同一轮导入批次 ID |
| `snapshot_json` | `TEXT` | 是 | 原始来源记录 JSON |
| `normalized_json` | `TEXT` | 是 | 标准化结果 JSON |
| `field_hash` | `TEXT` | 是 | 便于判断同一记录是否变更 |
| `captured_at` | `TEXT` | 是 | 快照采集时间 |
| `created_at` | `TEXT` | 是 | 入库时间 |

### 主键与外键

- 主键：`PRIMARY KEY (id)`
- 外键：`customer_id -> customer_master.id`
- 外键：`identity_link_id -> customer_identity_links.id`

### 必要约束

- `source_system` 只能取：
  - `youzan`
  - `miniapp`
  - `wecom`
  - `import`
  - `manual`
- `source_object_type` 只能取：
  - `customer`
  - `order_buyer`
  - `member`
  - `contact`

### 建议唯一约束

- `(tenant_id, source_system, source_object_type, source_record_id, source_batch_id)`

这样可以允许：

- 同一来源记录多次进入不同导入批次

同时避免：

- 同一批次里把同一来源记录重复写入多次

### 建议索引

| 索引名 | 字段 | 用途 |
| --- | --- | --- |
| `idx_css_customer` | `(customer_id)` | 从主档回看全部来源快照 |
| `idx_css_identity_link` | `(identity_link_id)` | 查看某身份链接的来源证据 |
| `idx_css_source_record` | `(source_system, source_record_id)` | 来源记录追踪 |
| `idx_css_batch` | `(source_batch_id)` | 一次迁移批次回溯 |
| `idx_css_captured_at` | `(captured_at)` | 时间序列追踪 |
| `idx_css_field_hash` | `(field_hash)` | 判断快照是否变化 |

## 表 4：`customer_merge_reviews`

### 职责

这张表专门承接 `pending_review`。

它的存在，是为了避免把人工复核这件事只留在聊天、备注或临时 CSV 里。

它应该记录：

- 为什么进入复核
- 复核时看了哪些证据
- 最终决定是合并、拆开、忽略还是保持待定

### 建议字段

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `id` | `TEXT` | 是 | 复核单主键 |
| `tenant_id` | `TEXT` | 是 | 租户 ID |
| `review_type` | `TEXT` | 是 | `identity_conflict / candidate_merge / weak_identity_enrichment` |
| `review_status` | `TEXT` | 是 | `open / in_progress / approved_merge / rejected_merge / needs_more_evidence` |
| `source_customer_id` | `TEXT` | 否 | 待处理主档 |
| `target_customer_id` | `TEXT` | 否 | 候选合并目标主档 |
| `primary_identity_link_id` | `TEXT` | 否 | 本次复核主身份线索 |
| `review_reason` | `TEXT` | 是 | 简述触发原因 |
| `conflict_summary_json` | `TEXT` | 是 | 冲突摘要 |
| `evidence_snapshot_ids_json` | `TEXT` | 是 | 参与复核的快照 ID 列表 |
| `decision` | `TEXT` | 否 | `merge / keep_separate / reject_identity / wait` |
| `decision_notes` | `TEXT` | 否 | 人工说明 |
| `reviewed_by` | `TEXT` | 否 | 操作人 |
| `reviewed_at` | `TEXT` | 否 | 决策时间 |
| `created_at` | `TEXT` | 是 | 创建时间 |
| `updated_at` | `TEXT` | 是 | 更新时间 |

### 主键与外键

- 主键：`PRIMARY KEY (id)`
- 外键：`source_customer_id -> customer_master.id`
- 外键：`target_customer_id -> customer_master.id`
- 外键：`primary_identity_link_id -> customer_identity_links.id`

### 必要约束

- `review_type` 只能取：
  - `identity_conflict`
  - `candidate_merge`
  - `weak_identity_enrichment`
- `review_status` 只能取：
  - `open`
  - `in_progress`
  - `approved_merge`
  - `rejected_merge`
  - `needs_more_evidence`
- `decision` 只能取：
  - `merge`
  - `keep_separate`
  - `reject_identity`
  - `wait`

### 建议索引

| 索引名 | 字段 | 用途 |
| --- | --- | --- |
| `idx_cmr_tenant_status` | `(tenant_id, review_status)` | 查未处理复核单 |
| `idx_cmr_source_customer` | `(source_customer_id)` | 查某客户的复核历史 |
| `idx_cmr_target_customer` | `(target_customer_id)` | 查被并入目标的复核历史 |
| `idx_cmr_identity_link` | `(primary_identity_link_id)` | 查某身份引发的复核 |
| `idx_cmr_reviewed_at` | `(reviewed_at)` | 审核时间排序 |

## `pending_review` 闭环

### 进入条件

首版建议只有下面几类情况进入 `customer_merge_reviews`：

1. 同手机号命中多个主档
2. 同一个来源身份试图挂到两个不同主档
3. 无手机号客户需要借订单或企微身份补强，但证据还不够唯一

### 落库动作

当脚本或 service 判定进入 `pending_review` 时，建议同时做 3 件事：

1. `customer_identity_links.link_status = pending_review`
2. 写入一条 `customer_merge_reviews`
3. 将相关来源记录落到 `customer_source_snapshots`

### 处理结果

#### 人工判定可合并

- `customer_merge_reviews.review_status = approved_merge`
- `customer_merge_reviews.decision = merge`
- 源主档 `customer_master.status = merged`
- 源主档 `merge_into_customer_id` 指向目标主档
- 身份链接重挂到目标主档

#### 人工判定不可合并

- `customer_merge_reviews.review_status = rejected_merge`
- `customer_merge_reviews.decision = keep_separate` 或 `reject_identity`
- 相关 `customer_identity_links.link_status` 改回 `active` 或 `rejected`

#### 证据不足

- `customer_merge_reviews.review_status = needs_more_evidence`
- `customer_merge_reviews.decision = wait`
- 等下一轮企微绑定、订单补强或人工补录后再处理

## 与有赞迁移审计脚本的映射

当前已有的审计脚本输出：

- `auto_merge`
- `new_master`
- `pending_review`

后续正式导入时，三类输出建议映射如下：

### `auto_merge`

- 命中已有主档：新增或更新 `customer_identity_links`
- 没有命中主档：创建 `customer_master` + `customer_identity_links`
- 同时保留 `customer_source_snapshots`

### `new_master`

- 创建一个弱身份 `customer_master`
- 若有手机号则补 `phone` 身份链接
- 若无手机号则先只保留来源快照，等待后续身份补强

### `pending_review`

- 不自动合并
- 创建或保留必要主档
- 写入 `customer_merge_reviews`
- 所有证据以快照和身份链接形式保留

## 首版明确不进入主档真相的字段

下面这些字段首版仍然只留在 `customer_source_snapshots.normalized_json` 或 `snapshot_json`：

- 会员状态
- 成长值
- 免费等级
- 付费等级
- 权益卡
- 客户积分
- 客户储值余额
- 消费次数
- 消费金额
- 累计退款金额
- 累计退款订单数
- 标签原文
- 导购员
- 分销员
- 来源方式
- 公众号关注信息
- 最近浏览时间

原因不变：

- 来源口径强依赖有赞
- 与未来企微或其他渠道语义不一致
- 过早放进主档会造成解释混乱

## 首版有意推迟的能力

这份 schema 草案故意不做下面这些内容：

1. 不做完整 CRM 标签宽表
2. 不做统一会员权益真相表
3. 不做积分与储值余额总账
4. 不做导入任务编排表、任务日志表、失败重试表
5. 不做复杂规则引擎式自动并人

这些都应该在 `customer master v1` 真正跑通后，再按真实业务压力判断是否加。

## 落库顺序建议

后续如果进入 `app/migrations/schema.py` 实现，建议按下面顺序推进：

1. 先建 `customer_master`
2. 再建 `customer_identity_links`
3. 再建 `customer_source_snapshots`
4. 最后建 `customer_merge_reviews`
5. 再补索引

原因：

- 主档是其他三张表的锚点
- 身份链接依赖主档
- 快照和复核都可能依赖前两层

## 实施顺序建议

代码层建议分两步，而不是一次性全部上生产：

### 第一步：只落 schema 与 repository

- 先建 4 张表
- 先补最小 repository 读写能力
- 不直接切现有客户流量

### 第二步：接入迁移脚本和绑定流程

- 先让有赞客户导入脚本写入这 4 张表
- 再让企微或小程序身份挂接使用同一套身份链接表
- 最后再讨论 CRM 页面或运营台展示

## 与现有 `customer_profiles` 的边界

最后再强调一次：

- `customer_master*` 这组表是经营主档层
- `customer_profiles` 仍是 AI 画像层

两者可以互相引用，但不能互相替代。

更直白地说：

- `customer_master` 解决“这个客户是谁”
- `customer_profiles` 解决“AI 该记住这个客户什么偏好”

## 当前权威入口

这份文档确认后，直接按下面四个入口执行：

不要再回双仓历史过渡方案或 MiniApp 旧执行清单里补迁移步骤，正式执行以这四段闭环为准。

1. 继续以 [有赞客户迁移审计清单](./youzan-customer-migration-audit-checklist.md) 作为迁移前审计入口
2. 以 [有赞客户正式迁移执行 Runbook](./youzan-customer-formal-import-runbook.md) 作为 dry-run / apply 标准执行入口
3. 以 `scripts/verify_youzan_customer_import.py` 作为迁移后批次核对与 apply 报告对账入口
4. 以 [有赞客户迁移交接与回滚 Runbook](./youzan-customer-import-handoff-and-rollback-runbook.md) 作为迁移后异常处理入口
