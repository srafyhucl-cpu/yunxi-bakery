# 后续工作包 FP-1：会员数据正式导入

- status: pending
- parent_trace_id: `20260812-member-loyalty-storedvalue`
- 执行时须生成独立 trace_id（如 `2026MMDD-member-loyalty-import`），不得复用父计划 trace
- 所属计划：[2026-08-12-member-loyalty-storedvalue-plan.md](./2026-08-12-member-loyalty-storedvalue-plan.md)（M1 数据底座）
- 阻塞依赖：真实有赞店铺 API / Webhook 契约
- 拆分来源：2026-08-14 M1–M6 完整评审（方案 B 分阶段结项）；2026-08-14 深度复核修正

## 背景

M1 已完成 v021 三表迁移与 Webhook 会员路由部署（生产 v0.111.0，ecffa3b）。`scripts/import_member_loyalty.py` 已具备 dry-run / apply / limit / JSON 报告能力，但生产正式全量导入尚未执行，真实店铺 API / Webhook 契约未联调。

## 当前实现事实（复核修正）

- 脚本**不存在** `--dry-run` 参数；**不传 `--apply` 即只查询不写入**（dry-run）。
- 实际写入目标：`member_balance`（积分余额快照、会员卡）、`coupon_inventory`（券库存）、`coupon_templates`（券模板）；**不写** `points_ledger`（由 Webhook 增量维护）。
- 脚本缺陷：单客户失败仅计入 `failed`，最终仍返回退出码 `0`，部分失败可能被误判为成功。**执行 apply 前必须先完成脚本增强（阶段一）。**

## 阶段一：脚本增强（先于任何 apply）

1. `failed > 0` 时进程以非 0 退出码结束，并把 failed 明细写入 JSON 报告。
2. apply 阶段强制生成 JSON 报告（`--json --output`），报告元数据含 `batch_id`（时间戳 + 随机后缀），禁止只打控制台。
3. 限流退避：有赞 API 429 / 限流时按 Retry-After 退避重试，配置重试上限。
4. 断点续跑：以 customer 主档为断点（记录已处理游标），中断后可续跑，不重复处理已成功客户。
5. 失败重试：单客户失败进入 retry 队列，收尾统一重试（上限 N 次）。
6. 备份与恢复：apply 前先做 SQLite 备份并校验；执行备份恢复 round-trip 演练，通过后视为可恢复。
7. 回归：上述增强配合同级单元 / 脚本测试，`ruff` / `check_project --skip-tests` 门禁通过。

## 阶段二：真实店铺契约联调

1. 受控小批 dry-run：`python scripts/import_member_loyalty.py --limit 20`（不传 `--apply`），核对积分 / 券 / 会员卡字段契约。
2. 真实券字段解析：核对 `parse_youzan_template` / `extract_template_fields` 对真实有赞响应的折扣、券类型、有效期字段；修复**非数值折扣解析健壮性**（承接 M4 评审遗留 #4）。
3. 契约核对通过后，方进入全量 apply。

## 阶段三：生产全量导入与核对

1. 全量执行：`python scripts/import_member_loyalty.py --apply --json --output "reports/import/member-loyalty-{timestamp}.json"`。
2. eligible population 界定：以 `customer_master` 中具备 `primary_phone` 的主档为导入范围（含授权测试账号），报告中明确 `total_eligible / 已导入 / 无手机号跳过 / 豁免`，作为验收基线。
3. 核对：导入数量与 eligible population 一致、幂等无重复、余额快照正确、`failed=0` 且退出码为 0。
4. Webhook 起止双水位：导入开始前记录 `start_watermark`，结束后记录 `end_watermark`；`(start, end]` 窗口内到达的真实 `POINTS` / `COUPON_CUSTOMER_PROMOTION` / `SCRM_CUSTOMER_CARD` / `SCRM_CUSTOMER_EVENT` 事件必须回放或补拉核对，防止旧快照覆盖新事件。
5. 导入期间若增量处理暂停，恢复时必须先回放水位线窗口内事件再继续（禁止无回放的直接续跑）。
6. 四类事件验收：`POINTS`（余额/流水一致）、`COUPON_CUSTOMER_PROMOTION`（券库存/状态一致）、`SCRM_CUSTOMER_CARD`（会员卡状态）、`SCRM_CUSTOMER_EVENT`（身份归属）各自核对通过。

## 验收标准

- 脚本增强通过（`failed>0` 非 0 退出、JSON 报告必带 `batch_id`、限流退避 / 断点续跑 / 失败重试有测试）。
- dry-run 与全量 apply 报告 `failed=0`，导入数量与 eligible population 一致，幂等无重复，四类事件验收全部通过。
- eligible population 界定明确；起止双水位校验通过，水位线窗口内事件回放无漏单、无重复。
- coupon_templates 同步校验：模板数量、字段（折扣 / 类型 / 有效期）与 `coupon_inventory.template_id` 关联一致。
- 备份与恢复 round-trip 演练通过。
- LOGBOOK / 证据索引收口，使用独立 trace_id。

## 导入批次持久化与回放设计（I1，B1.6 + B1.7 + B1.8 定稿：独立投影重建器）

> 设计裁决，关联 [ADR 0008](../harness-engineering/adr/0008-accounting-core-consistency.md)。实施阶段落地，前置于正式全量导入。B1.6 固定 inbox 回放为唯一方案；B1.7 复核修正：**回放不得复用正式 Webhook 处理函数**，改为独立的投影重建器（投影重建 / checkpoint 控制 / 按资产定义快照版本合同），否则既有积分 / 券业务幂等会直接跳过、`process_youzan_webhook` 也不检查 `message_key`，无法修复"旧快照覆盖新投影"。B1.8 复核修正：**`inbox_events.id` 是到达顺序而非上游因果顺序**，`occurred_at > snapshot_time` 不足以处理迟到 / 同时间 / 乱序事件；引入按聚合的上游版本合同与对账队列，并强制投影更新、物化记录与 checkpoint 推进同一 UoW。

- 新增 `import_batch` 表：`batch_id`、`queue_name`（固定 `'youzan_webhook'`）、`start_event_id`、`end_event_id`、`cursor`、`snapshot_version`、`projection_checkpoint`（JSON）、`stats`（JSON）、`failed_detail`（JSON）、`status`。
- 规范回放源：以持有原始 payload 的 **`inbox_events.id` 为唯一水位**（AUTOINCREMENT 不可变）；`youzan_webhook_events` 仅作关联观测、不参与回放游标；**禁止时间戳水位**。
- **投影重建器（B1.7 定稿，不调 `process_youzan_webhook`）**：读取原始 `payload_json.body` 后**直接按资产规则重建投影**，不走入站 `message_key` 去重、不走审计回调、不走业务幂等短路；以 `import_batch.projection_checkpoint`（每资产已重建到的事件 id）控制重建进度，中断后从 checkpoint 续跑。
- **事件版本合同（B1.8 + B1.9）**：`inbox_events.id` 只作回放游标，**不充当上游因果顺序**。每个入站事件按 **`provider / event_id / event_version / ordering_kind / payload_hash`** 建档：`ordering_kind=monotonic`（供应商保证 `event_version` 单调递增）时以 `event_version` 判定新旧；`ordering_kind=unordered` 或无可比单调版本时**不判定新旧**，冲突一律进入对账队列（`import_reconcile_queue`，含负责人与处置结果），不静默覆盖；`unique_id` / `origin_event_id` 仅作事件标识去重，**不承担可比较性**。重建按聚合的版本合同胜出：
  - 事件 `event_version`（monotonic）严格更新 → 覆盖投影；
  - 同一事件（`event_id` + `payload_hash` 一致）→ 幂等跳过；
  - 无可靠单调版本或版本冲突 → 进入对账队列，批次收尾统一上报。
- **重建原子性（B1.8）**：**投影更新 + 物化记录 + checkpoint 推进必须在同一 UoW**：新增物化表 `import_rebuild_log` 以 **`UNIQUE(batch_id, asset, inbox_event_id)`** 幂等——同一事件重复重建被唯一键拒绝，不重复叠加；UoW 提交前 checkpoint 不前进，崩溃恢复不会重复应用。
- **按资产的快照版本与重建规则（B1.7 + B1.8）**：

  | 资产 | 快照版本来源 / 上游版本 | 重建规则 |
  |---|---|---|
  | 积分余额 `member_balance.points` | `points_snapshot_version`（导入时固化）/ 事件 `event_version`（monotonic） | 按事件版本合同：`event_version` 更新则覆盖投影；`unique_id` 仅作标识去重不判新旧；无法比较进对账队列；积分流水由 Webhook 增量维护，重建不写流水。**投影目标为稳定会员账户键（`member_balance_id`）与账户级版本（B3.1）——单条事件 ID 不是账户聚合键，旧余额快照覆盖以账户级版本裁决** |
  | 优惠券 `coupon_events` / `coupon_current_state` / `coupon_observation` | `coupon_snapshot_version` / `event_version` + `origin_event_id` + `transition_key` | 迁移行 `business_ref=legacy:<coupon_inventory.id>`（统一 transition_key 公式）后，按 `transition_key` 追加窗口内事件并重算投影；外部 `CONSUME/BACK/TAKE` **只写 `coupon_observation` 事实与 `coupon_reconcile_case` 案件，绝不直接写当前态**（B3 + B3.2 全仓统一：观察只建案件、本地命令才改当前态——`reconcile_hold` / `TAKE` 由本地裁决 / 摄取命令 CAS 写入；**B3.3：券写入语义唯一源 = ADR 0008 D1-B，本节仅引用**）；新旧判定走事件版本合同，禁止 `(occurred_at, id)` 因果 |
  | 会员身份 `customer_identity_links` | `identity_snapshot_version` / `event_version` | `event_version` 更新才覆盖归属，冲突进对账队列 |
  | 会员卡 `member_balance` 卡字段 | `card_snapshot_version` / `event_version` | `event_version` 更新才覆盖卡状态，冲突进对账队列 |

- **队列过滤**：仅回放 `queue_name = 'youzan_webhook'`；`inbox_events` 同时承载企微队列，严禁混入导入回放。
- **起止边界（B1.7 统一为半开区间）**：`(start_event_id, end_event_id]`（导入开始前记录 `start_watermark`，结束后记录 `end_watermark`）；`end_event_id` 缺省取当前最大 `id`。窗口表述全文统一为 `(start, end]`，不再使用 `[start, end]`。
- **快照冲突胜出规则**：以事件版本合同（monotonic `event_version`）判定——事件版本更新则覆盖投影 / 追加事件，同版本或更旧则跳过（旧事件不覆盖新快照）；不可比冲突进入对账队列；重建器不做入站幂等短路，覆盖判定完全由事件版本合同驱动。
- **乱序处理**：重建按 `id ASC` 单调推进（游标维度）；聚合内乱序 / 迟到以 `event_version`（monotonic）裁决，同版本事件以 `event_id + payload_hash` 消歧；无单调版本进对账队列。
- **故障恢复测试矩阵（实施阶段必测，B1.7 补"旧快照覆盖后重建恢复"，B1.8 补"物化幂等 / 对账队列"）**：

  | 场景 | 预期 |
  |---|---|
  | 中断后按 `projection_checkpoint` 续跑 | 无重复、无遗漏，断点续跑 |
  | `queue_name` 混入企微事件 | 被过滤，不影响导入回放 |
  | 窗口内事件重复重建 | `UNIQUE(batch_id, asset, inbox_event_id)` 幂等，不重复叠加 |
  | 新事件已处理后旧快照覆盖投影 | **重建器运行后投影恢复**（不依赖 Webhook 幂等短路） |
  | 迟到 / 同时间 / 乱序事件 | 按事件版本合同（monotonic `event_version`）胜出；不可比冲突进对账队列，不静默覆盖 |
  | 旧快照（`snapshot_version` 早于事件）被回放 | 不覆盖新事件 / 新快照 |
  | 重建处理中抛异常 | 记录 `failed_detail`，`failed > 0` 以非 0 退出 |
  | 进程重启恢复 | 从 `import_batch.projection_checkpoint` 继续；投影 / 物化 / checkpoint 同 UoW，无重复应用 |

- **入站 envelope 与 epoch（B2.0）**：回放与导入均按 FP-2 D2 协议携带 `authority_epoch`；切换围栏（暂停 claim → 排空 / 接管水位前事件 → 持久化 epoch → 恢复）期间到达的事件按记录 epoch 处理，禁止按进程级环境变量路由。
- **四类有赞事件映射 / 聚合键 / 版本来源 / 对账闭环（B2.0 + B3 逐类补全）**：**B3 强制逐类列明 provider 字段路径、是否单调、快照版本来源；缺少可靠版本时禁止自动覆盖，只能进入对账和保守重放**。**起止双水位（`inbox_events.id`）只界定回放窗口，不承担因果版本**——事件新旧一律按本表版本合同判定，双水位不能替代因果版本。

  | 事件 | provider 字段路径（必需） | 单调性 / 版本字段来源 | 聚合键 | 无单调版本时的对账闭环 |
  |---|---|---|---|---|
  | `POINTS` | `amount / total / event_type / unique_id / mobile`（`amount.total` 或 `total` 依真实响应核验） | `ordering_kind=monotonic`：版本来源 = 有赞事件 `update_time` / 业务单号序列（实施联调时以真实响应字段固化；**不可比则视为 unordered**） | **事件身份 `(provider, unique_id)`（B3.1：仅作事件去重，不再是账户聚合键）；投影目标 = 稳定会员账户键（`member_balance_id`，账户级 `points_snapshot_version`）** | 冲突进 `import_reconcile_queue`，核对有赞 `total` 与本地投影；无可靠版本禁止覆盖 |
  | `COUPON_CUSTOMER_PROMOTION` | `id / status / mobile / coupon_group_id / order_no`（`coupon_group_id` 映射 `coupon_templates`） | `ordering_kind=unordered`（有赞券事件无单调版本保证）：版本来源 = `event_id + payload_hash` 消歧，**无单调版本时禁止自动覆盖** | `coupon_id + mobile + origin_event_id` | 外部 `CONSUME/BACK/TAKE` **只写 `coupon_observation` 事实与 `coupon_reconcile_case` 案件，不改变 `coupon_current_state`**（B3.2 全仓统一：观察只建案件、本地命令才改当前态）；未决案件使券不可用；`reconcile_hold` 由本地裁决命令写入（**B3.3：券写入语义唯一源 = ADR 0008 D1-B**） |
  | `SCRM_CUSTOMER_CARD` | `card_alias / card_no / mobile / status` | `ordering_kind=monotonic`：版本来源 = 事件 `update_time`（联调固化；不可比则 unordered） | `mobile + card_no` | 冲突进对账队列，核对会员卡状态；无可靠版本禁止覆盖 |
  | `SCRM_CUSTOMER_EVENT` | `mobile / name / is_member / status`（身份归属字段路径） | `ordering_kind=unordered`：以 `event_id + payload_hash` 消歧，冲突进对账队列 | `mobile + 事件主键` | 冲突进对账队列，核对身份归属；无可靠版本禁止覆盖 |

- 导入批次与水位关联：记录导入起止事件游标，`(start, end]` 窗口内事件必须重建核对；批次失败明细持久化，`failed > 0` 以非 0 退出。

## 边界

- 不导入积分明细流水（由 Webhook 增量维护），只落余额快照、券库存与券模板（`member_balance` / `coupon_inventory` / `coupon_templates`），避免导入快照污染明细。
- 导入涉及生产数据：未完成阶段一脚本增强、未通过备份恢复演练前，禁止执行 apply。
