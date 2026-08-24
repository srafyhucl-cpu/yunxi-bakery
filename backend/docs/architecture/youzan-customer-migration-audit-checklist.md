# 有赞客户迁移审计清单

## 文档目的

这份文档用于定义 `customer master v1` 落地前的第一轮有赞客户迁移审计清单。

它不是正式迁移脚本说明，也不是 CRM 经营报表方案，而是一份可执行的审计 runbook，用来先判断：

- 当前有赞客户数据能不能安全进入 `customer master v1`
- 哪些客户可以自动归并
- 哪些客户只能先建弱身份主档
- 哪些客户必须人工确认

## 适用范围

- 当前 `Platform` 代码仓路径：`YunxiBakeBot`
- 当前主档方案：`docs/architecture/customer-master-v1.md`
- 当前已拿到的输入：
  - `docs/有赞导出/客户数据_0002000408539943.csv`
  - `docs/有赞导出/订单数据.csv`
- 当前首个实例：`Yunxi`

## 审计原则

1. 先审计，再迁移
2. 先识别高风险，再讨论自动归并规模
3. 先服务 `customer master v1`，不把这一步扩成完整 CRM 分析
4. 订单数据首版只做补强证据，不直接反写客户主档
5. 宁可多出 `pending_review`，也不要误合并两个不同客户

## 审计目标

这轮审计只服务 4 个目标：

1. 判断当前有赞客户表的手机号是否足以支撑首版自动归并
2. 判断当前客户导出中哪些字段适合作为主档候选，哪些只能作为来源快照
3. 判断订单表能否为无手机号或弱身份客户提供补强证据
4. 产出后续 schema、导入脚本和人工复核都能直接消费的输出结构

## 输入范围

### 必需输入

#### 客户表

- 文件：`docs/有赞导出/客户数据_0002000408539943.csv`
- 当前已知关键字段：
  - `客户姓名`
  - `客户昵称`
  - `客户手机号`
  - `客户生日`
  - `客户性别`
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
  - `上次消费时间`
  - `来源渠道`
  - `来源方式`
  - `成为客户时间`
  - `微信地域`

#### 订单表

- 文件：`docs/有赞导出/订单数据.csv`
- 当前已知关键字段：
  - `订单号`
  - `订单创建时间`
  - `买家昵称`
  - `买家是否会员`
  - `买家手机号`
  - `交易成功时间`
  - `订单实收金额`
  - `销售渠道`
  - `订单来源`

### 增量输入

如果后续拿到更多有赞字段或企微客户字段：

- 允许作为增量输入补充审计
- 不推翻本轮主档口径
- 默认新增字段先进入“来源快照候选”，不直接升级为主档字段

## 标准化规则

审计前必须先统一标准化规则，否则统计结果不可比。

### 手机号标准化

生成字段：`normalized_phone`

处理规则：

1. 去掉前后空格
2. 去掉中间无意义空格
3. 只接受中国大陆 11 位手机号作为有效值
4. 以下视为无效手机号：
   - 空值
   - 掩码值，例如 `186******05`
   - 含明显非数字主体
   - 长度不正确

### 称呼候选标准化

生成字段：`display_name_candidate`

规则：

1. 优先 `客户姓名`
2. 其次 `客户昵称`
3. 两者都为空则留空
4. 不允许为缺失值强造默认姓名

### 时间候选标准化

生成字段：

- `first_seen_at_candidate`
- `last_seen_at_candidate`

规则：

1. `first_seen_at_candidate`
   - 优先取 `成为客户时间`
2. `last_seen_at_candidate`
   - 优先取 `上次消费时间`
3. 不可解析时间统一保留为空，并在问题表中暴露

### 来源字段标准化

生成字段：

- `source_channel_normalized`
- `source_method_normalized`

规则：

1. 保留原始值
2. 同时做轻量归一化，用于分布统计
3. 不在首版擅自合并业务语义接近但不完全相同的来源值

## 审计优先级

### `P0` 必查

这些项直接决定 `customer master v1` 是否可以开始。

#### `P0-1` 客户基础规模

指标：

- `total_customers`
- `customers_with_phone`
- `customers_without_phone`
- `valid_phone_rate`

计算方法：

- `total_customers`
  - 客户表总行数
- `customers_with_phone`
  - `normalized_phone` 非空的客户数
- `customers_without_phone`
  - `normalized_phone` 为空的客户数
- `valid_phone_rate`
  - `customers_with_phone / total_customers`

风险含义：

- 有效手机号占比越低，首版自动归并空间越小

#### `P0-2` 手机号可归并性

指标：

- `unique_phone_count`
- `duplicate_phone_customer_count`
- `duplicate_phone_group_count`
- `invalid_phone_count`

计算方法：

- `unique_phone_count`
  - 去重后的有效手机号数量
- `duplicate_phone_customer_count`
  - 落在重复手机号集合内的客户数
- `duplicate_phone_group_count`
  - 重复手机号组数
- `invalid_phone_count`
  - 原始手机号非空但标准化失败的客户数

风险含义：

- 重复手机号越多，`pending_review` 规模越大
- 异常手机号越多，手机号作为自动并人主键的稳定性越差

#### `P0-3` 自动归并可行性

指标：

- `auto_merge_customer_count`
- `new_master_customer_count`
- `pending_review_customer_count`

分流定义：

- `auto_merge`
  - 有有效手机号
  - 且该手机号在当前租户下唯一
  - 且没有明显冲突标记
- `new_master`
  - 无有效手机号
  - 或没有足够证据命中已有主档
- `pending_review`
  - 同手机号对应多个客户
  - 或存在明显冲突特征

风险含义：

- 这是后续导入脚本最核心的分流结果

#### `P0-4` 订单补强能力

指标：

- `orders_with_buyer_phone`
- `orders_phone_match_customer`
- `customers_missing_phone_but_order_matchable`

计算方法：

- `orders_with_buyer_phone`
  - 订单表中 `买家手机号` 标准化成功的订单数
- `orders_phone_match_customer`
  - 订单手机号能够命中客户表 `normalized_phone` 的订单数
- `customers_missing_phone_but_order_matchable`
  - 客户表无手机号，但后续人工复核时可参考订单侧手机号的潜在候选数

风险含义：

- 订单数据可作为补强证据，但首版不应直接自动回写主档

### `P1` 应查

这些项不阻断首版主档设计，但会影响迁移质量。

#### `P1-1` 主档候选字段质量

指标：

- `display_name_available_rate`
- `birthday_available_rate`
- `gender_available_rate`
- `wechat_region_available_rate`
- `first_seen_at_available_rate`
- `last_seen_at_available_rate`

风险含义：

- 这些字段缺失不阻断 v1
- 但会决定主档字段是否必须可空

#### `P1-2` 来源快照复杂度

指标：

- `tag_non_empty_rate`
- `member_flag_non_empty_rate`
- `growth_value_non_empty_rate`
- `balance_non_empty_rate`
- `source_channel_distribution`
- `source_method_distribution`

风险含义：

- 复杂度越高，越说明这些字段应保留在 `source_snapshots`
- 不应急于进入统一主档真相

#### `P1-3` 来源冲突风险

指标：

- `same_phone_name_conflict_count`
- `same_phone_membership_conflict_count`
- `same_phone_source_conflict_count`

风险含义：

- 这些冲突项不一定代表错误
- 但首版必须进入人工复核范围，而不是自动归并

### `P2` 可后查

这些项更偏后续 CRM 和运营，不影响首版迁移底盘。

#### `P2-1` 高价值客户结构

指标：

- 高消费客户数
- 有储值余额客户数
- 会员客户数

#### `P2-2` 运营参考项

指标：

- 标签模式
- 来源渠道结构
- 最近活跃分布

## 输出物定义

审计至少要产出两张结果表和一组汇总指标。

### 输出物 1：汇总指标表

建议表头：

- `metric_key`
- `metric_name`
- `metric_value`
- `risk_level`
- `notes`

用途：

- 快速看迁移可行性
- 作为后续方案评审和脚本验收的摘要输入

### 输出物 2：客户级问题表

建议表头：

- `source_record_id`
- `customer_name`
- `customer_nickname`
- `raw_phone`
- `normalized_phone`
- `issue_type`
- `risk_level`
- `suggested_action`
- `matched_order_phone`
- `notes`

用途：

- 人工复核
- 迁移前清洗
- 脚本落地后的抽样检查

### 输出物 3：客户分流结果表

建议表头：

- `source_record_id`
- `normalized_phone`
- `proposed_bucket`
- `confidence_level`
- `conflict_flags`
- `recommended_customer_action`

其中：

- `proposed_bucket`
  - `auto_merge / new_master / pending_review`
- `confidence_level`
  - `high / medium / low`

## 风险等级定义

建议只分 3 级，避免过度复杂。

### `high`

直接影响主档自动归并安全性：

- 手机号缺失率过高
- 手机号重复率高
- 异常手机号多
- 同手机号客户冲突严重

### `medium`

不阻断主档，但会影响迁移质量：

- 称呼字段质量差
- 时间字段缺失多
- 来源字段分布复杂
- 会员 / 标签 / 积分字段不稳定

### `low`

更偏经营分析，不影响首版迁移底盘：

- 高价值客户分布
- 运营标签模式
- 活跃分布

## 建议动作

### 当手机号缺失率高

- 不做激进自动归并
- 允许更多客户进入 `new_master`
- 后续通过企微或小程序身份补强

### 当重复手机号多

- 统一进入 `pending_review`
- 先出人工核对清单
- 暂不批量自动并人

### 当异常手机号多

- 先修标准化规则
- 重跑审计
- 不要把异常值当身份主键

### 当主档候选字段缺失高

- 不阻断 v1
- 但 `display_name`、`birthday`、`wechat_region` 等字段应明确允许为空

### 当会员 / 积分 / 储值字段复杂

- 不进入 `customer_master`
- 全量保留在 `customer_source_snapshots`
- 后续单独做经营字段治理

## 审计通过标准

满足以下条件时，可以进入正式迁移执行与后验核对闭环：

1. 手机号标准化规则已经稳定
2. `auto_merge / new_master / pending_review` 三类能够稳定分流
3. 高风险重复手机号客户能够被识别出来
4. 汇总表、问题表和分流表的结构已足够支撑人工复核和脚本实现
5. 团队已经明确哪些字段属于主档真相，哪些字段只属于来源快照

## 暂不通过标准

出现以下情况时，不建议直接进入正式迁移实现：

1. 手机号标准化结果明显不稳定
2. 重复手机号无法稳定识别
3. 客户表和订单表的核心手机号字段大面积不可用
4. 还分不清主档字段和来源快照字段
5. `pending_review` 识别规则仍然模糊

## 与 `customer master v1` 的直接映射

审计结论最终应落回 `customer master v1`：

- 唯一手机号客户
  - 可以进入 `auto_merge`
- 无手机号客户
  - 可以进入 `new_master`
- 同手机号冲突客户
  - 进入 `pending_review`
- 会员 / 积分 / 储值 / 标签
  - 进入 `customer_source_snapshots`
  - 暂不进入 `customer_master`

## 当前闭环入口

在这份审计清单之后，直接按当前闭环继续执行：

1. [有赞客户正式迁移执行 Runbook](./youzan-customer-formal-import-runbook.md)
   - 继续完成 dry-run、`--apply`、批次号约定和报告留档
2. `scripts/verify_youzan_customer_import.py`
   - 继续完成迁移后批次核对与 apply 报告对账
3. [有赞客户迁移交接与回滚 Runbook](./youzan-customer-import-handoff-and-rollback-runbook.md)
   - 继续处理 apply 后异常中止、交接证据和恢复优先级

## 与正式迁移入口的关系

审计清单不是正式写库脚本，但它直接服务正式入口 `scripts/import_youzan_customers.py`：

- 审计清单负责定义数据是否可迁、哪些字段能自动归并、哪些必须待复核。
- 正式入口负责把已经确认的分流结果写入 `customer master v1`。
- 如果审计结果还不稳定，先停在审计清单，不要直接跑 `--apply`。

正式迁移建议统一遵循：

1. 先审计
2. 再 dry-run
3. 最后 `--apply`
