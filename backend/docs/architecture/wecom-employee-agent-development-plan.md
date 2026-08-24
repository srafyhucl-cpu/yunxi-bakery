# 企微员工助手开发计划

> ⚠️ 本计划已完成（2026-07-05 确定性回复重构上线）。本文档保留为历史记录。书

> 状态：方案 A 已落地，本地验证通过；生产证据待补
> 创建日期：2026-07-04
> 适用范围：`app/service/wecom/employee_agent_*`、`app/api/wecom` 智能机器人插件、相关测试与探针脚本
> 关联文档：[wecom-intelligent-bot-tools.md](./wecom-intelligent-bot-tools.md)、[project-boundaries.md](./project-boundaries.md)

______________________________________________________________________

## 一、背景与问题定义

### 1.1 员工助手在项目中的定位

本项目并行承载两条对话线：

- **面向客户的智能客服**：有赞小程序 / 企微客服回调，AI 对话、RAG、情绪安抚、转人工。需要语气自然、会安抚。
- **面向员工的助手**（本计划书对象）：企微智能机器人插件，员工查订单、库存、待人工、观察台、客户线索、离线复盘等。需要**准确、可执行、事实保真**。

两条线的核心差异在于**对事实保真的容忍度**：客服可以润色措辞，员工助手不能容忍数值/结论被改写。

### 1.2 当前实现的问题

员工助手当前走的是「确定性回复 → LLM 润色 → 事后逐项体检回退」的链路：

1. `employee_agent_service.py:_deterministic_reply` 先用规则拼出正确回复；
2. `_polish_reply` 把它交给 LLM 润色（`temperature=0.2`）；
3. `employee_agent_reply_guard.py:preserve_tool_facts` 逐项检查润色结果是否篡改了事实，命中任一即回退到确定性回复。

**症状**：`preserve_tool_facts` 已堆叠 14 个 `_misses_* / _introduces_* / _distorts_*` 检查函数，且仍在持续增加。2026-07-04 当天 60+ 提交几乎全部是「加一个 guard + 记一条 evidence」的重复循环。

**根因**：把面向客户场景的「LLM 润色」做法错用到了员工场景。员工要的是确定性，润色带来的价值（语气自然）在员工场景几乎为零，却引入了无穷无尽的事实篡改风险面。每发现一种新的篡改方式，就要加一个硬编码中文标记词的 guard——这个列表没有尽头。

**具体技术债**：

- `preserve_tool_facts` 的 14 个 guard 全靠硬编码中文词匹配（如 `"暂无可售库存"`、`"未命中结果"`、`"缺货结论"`），文案一改即失效或误伤。
- 判定逻辑几乎都是「命中 → 回退到确定性回复」，说明确定性回复本身已经是期望输出，润色只是徒增风险。
- guard 与探针用例（`scripts/wecom_employee_agent_probe_cases.py`）、回调检查（`scripts/check_wecom_employee_agent_callback.py`）、单测三处同步维护，改一处要动三处。

______________________________________________________________________

## 二、目标与非目标

### 2.1 目标

1. **消除 guard 打地鼠循环**：让员工助手的事实敏感意图默认走确定性回复，不再依赖「润色 + 事后体检」。
2. **保留必要的自然语言能力**：仅在明确安全、无事实篡改风险的场景保留 LLM 参与（规划、弱关键词兜底）。
3. **降低维护面**：把 guard/探针/回调三处同步的负担收敛，减少硬编码中文词。
4. **不回退现有能力**：订单、商品、库存、待人工、客户线索、离线复盘、观察台等已实现的查询能力全部保留，输出质量不下降。

### 2.2 非目标

- 不改动面向客户的智能客服链路（那条线的润色是合理的）。
- 不新增员工助手业务能力（本轮是架构收口，不是功能扩张）。
- 不改动企微回调验签、消息队列等基础设施。
- 不引入新的 LLM 供应商或模型。

______________________________________________________________________

## 三、总体策略

核心决策：**员工助手按意图分级处理回复生成方式**，而不是统一走润色。

### 3.1 意图分级

| 意图 | 事实敏感度 | 回复策略 | LLM 参与 |
|------|-----------|---------|---------|
| `order_query`（订单/销量/营业额/履约） | 高 | 确定性回复直出 | 否 |
| `product_query`（库存/价格/上架） | 高 | 确定性回复直出 | 否 |
| `ops_query`（观察台/待人工/客户线索/离线复盘） | 高 | 确定性回复直出（现已跳过润色） | 否 |
| `knowledge_answer`（规则/话术/配送/退款） | 中 | 确定性回复直出（现已跳过润色） | 否 |
| `multi_tool`（商品+话术、订单+话术组合） | 高 | 模板化确定性回复（`mixed_reply` 已实现） | 否 |
| 弱关键词 / 无法规则命中的规划 | — | LLM 仅用于**规划**（产出结构化 plan，不产出面向用户文本） | 是（仅规划） |

**关键点**：LLM 只保留在 `EmployeeAgentPlanner._plan_with_llm`（规划兜底，`temperature=0`，输出结构化 plan 而非用户可见文本），**回复生成环节全部去掉 LLM 润色**。

### 3.2 为什么这样是安全的

- 规划环节的 LLM 输出会经过 `parse_llm_plan` 解析成结构化 `AgentPlan`，任何幻觉都被限制在「选错工具」而非「篡改数值」，且最终数据仍来自确定性工具调用。
- 回复文本 100% 由确定性逻辑（工具结果 + 模板）拼装，天然事实保真，不需要 `preserve_tool_facts` 事后兜底。
- `mixed_reply` 已经证明了模板化确定性回复能产出「像员工助手」的自然回复（含员工建议、下一步、给客户可复制话术）。

______________________________________________________________________

## 四、分阶段执行计划

### 阶段 0：基线固化（0.5 天）

**目标**：动手前锁定现状，确保重构前后行为可对比。

- [x] 运行全量员工助手相关测试，记录当前通过数与覆盖场景：
  - `python -m pytest tests/service/test_wecom_employee_agent.py -v`
  - `python -m pytest tests/api/test_wecom_intelligent_bot_plugin_api.py -v`
  - `python -m pytest tests/scripts/test_check_wecom_employee_agent_callback.py -v`
- [x] 运行探针脚本，导出当前所有探针用例的确定性回复快照，作为回归基线：
  - `python scripts/wecom_employee_agent_probe_cases.py`（确认导出方式，必要时补一个 dump 参数）
- [x] 把当前 `preserve_tool_facts` 的 14 个 guard 逐条登记成一张「场景 → guard → 是否可由确定性直出覆盖」对照表（见附录 A 模板），确认去掉润色后每个场景仍被覆盖。

**验收**：基线快照与对照表落档，测试全绿。

### 阶段 1：回复链路去润色（1 天）

**目标**：员工助手所有意图回复改为确定性直出，移除 `_polish_reply` 对事实敏感意图的调用。

- [x] 修改 `employee_agent_service.py:answer`：
  - 事实敏感意图（`order_query`、`product_query`、`multi_tool`）与已跳过的 `knowledge_answer`、`ops_query` 一致，直接返回 `clean_plain_text_reply(deterministic_reply)`。
  - 结果是 `_polish_reply` 不再被任何意图调用。
- [x] 保留 `_polish_reply` 方法体但标记为不再引用，或直接删除（取决于阶段 2 决策，见下）。
- [x] 逐个用探针基线验证：每个场景去润色后的输出 == 阶段 0 记录的确定性回复。
- [x] 修复因去润色导致断言变化的单测（预期：断言从「检查 guard 回退」变成「检查确定性直出」，语义等价）。

**验收**：全部探针场景确定性直出，输出与基线一致；测试全绿。

### 阶段 2：清理 guard 与死代码（0.5 天）

**目标**：删除因去润色而失去存在意义的 guard，收敛维护面。

- [x] 删除 `_polish_reply` 及 `employee_agent_service.py` 中对 `llm_chat`、`preserve_tool_facts` 的回复期引用。
- [x] 评估 `employee_agent_reply_guard.py`：
  - 若润色彻底移除，`preserve_tool_facts` 及其 14 个 guard 全部成为死代码 → 整文件删除。
  - 若阶段 3 决定保留「可选润色」作为特性开关，则将 guard 保留但移出主链路（见阶段 3）。
- [x] 同步删除 / 调整仅为验证 guard 而存在的单测（`test_preserve_tool_facts_*` 系列）。
- [x] 更新 `scripts/wecom_employee_agent_probe_cases.py` 与 `scripts/check_wecom_employee_agent_callback.py`：去掉「验证润色不篡改」类断言，保留「确定性输出正确」类断言。

**验收**：`grep -r preserve_tool_facts app/ tests/ scripts/` 无残留（或仅在被开关保护的路径下）；文件行数下降，pre-commit 通过。

### 阶段 3（可选）：润色能力的去留决策（0.5 天）

**目标**：明确 LLM 润色是否彻底移除，还是保留为可关闭特性。执行时二选一。

- **方案 A（推荐）彻底移除**：员工助手不需要润色，删除相关代码，维护面最小。
- **方案 B 保留为开关**：若未来确有「自然语气」需求，把润色收敛到单一开关 `WECOM_EMPLOYEE_AGENT_ENABLE_POLISH`（默认关闭），开启时才走 `_polish_reply + preserve_tool_facts`。好处是保留能力，坏处是 guard 债务仍在。

> 建议在执行阶段 2 前先拍板 A/B。默认按 A 执行；若选 B，则阶段 2 的 guard 删除改为「移到开关保护路径下」。

### 阶段 4：文档与证据收口（0.5 天）

- [x] 更新 [wecom-intelligent-bot-tools.md](./wecom-intelligent-bot-tools.md)，说明员工助手回复生成已改为确定性直出。
- [x] 在 `LOGBOOK.md` 记录本轮重构（背景、改动、验证、前后对比）。
- [x] 按 `yunxi-harness-engineering` 规范留档证据（测试结果、探针快照对比）。
- [x] README「企业微信集成」小节措辞如需调整则同步。

______________________________________________________________________

## 五、涉及文件清单

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `app/service/wecom/employee_agent_service.py` | 改 | `answer` 去掉事实敏感意图的润色分支，删除 `_polish_reply` |
| `app/service/wecom/employee_agent_reply_guard.py` | 删 / 改 | 方案 A 删除整文件；方案 B 保留于开关后 |
| `app/service/wecom/employee_agent_mixed_reply.py` | 保留 | 确定性模板回复，本轮核心保留资产 |
| `app/service/wecom/employee_agent_planner.py` | 保留 | 规划环节 LLM 保留，不动 |
| `tests/service/test_wecom_employee_agent.py` | 改 | 移除 `test_preserve_tool_facts_*`、`*polish*` 断言，改为确定性直出断言 |
| `tests/api/test_wecom_intelligent_bot_plugin_api.py` | 保留 / 微调 | API 层断言主要针对工具输出，基本不变 |
| `tests/scripts/test_check_wecom_employee_agent_callback.py` | 改 | 去掉润色篡改类断言 |
| `scripts/wecom_employee_agent_probe_cases.py` | 改 | 探针用例去掉润色相关 forbidden 断言，保留确定性断言 |
| `scripts/check_wecom_employee_agent_callback.py` | 改 | 回调语义检查同步调整 |
| `app/config.py` | 改（仅方案 B） | 新增 `WECOM_EMPLOYEE_AGENT_ENABLE_POLISH` |

______________________________________________________________________

## 六、风险与回滚

| 风险 | 影响 | 缓解 |
|------|------|------|
| 去润色后某些回复读起来偏「模板化」 | 员工体验 | 员工场景以准确为先；确需自然语气用 `mixed_reply` 模板增强，不回退到 LLM |
| 探针 / 回调断言大范围改动引入回归 | 测试可信度下降 | 阶段 0 先固化基线快照，逐场景比对，语义等价才改断言 |
| 规划环节 LLM 仍可能选错工具 | 答非所问 | 保留规则规划优先，LLM 仅兜底；错误限制在工具选择，不篡改数值 |
| 删除 guard 后未来又冒出篡改需求 | 债务复现 | 若真需要，走方案 B 开关，而非在主链路重新堆 guard |

**回滚**：本轮改动集中在员工助手链路，与客户客服、企微基础设施解耦。回滚只需 revert 对应提交，恢复 `_polish_reply` 调用即可。

______________________________________________________________________

## 七、验收标准（Definition of Done）

1. 员工助手所有意图回复由确定性逻辑直出，回复期链路无 LLM 调用。
2. `preserve_tool_facts` 及其 guard 从主链路移除（方案 A 删除 / 方案 B 收于默认关闭的开关后）。
3. 全量相关测试通过，且断言语义与阶段 0 基线等价或更强。
4. 探针快照对比：去润色后每个场景输出 == 基线确定性回复。
5. 文档与 LOGBOOK 证据收口完成。
6. pre-commit（含红线检查、ruff、mistake-ledger）全绿。

______________________________________________________________________

## 附录 A：guard 场景对照表（阶段 0 填写）

> 逐条登记 `preserve_tool_facts` 现有 guard，确认去润色后每个场景仍被确定性回复覆盖。

| # | guard 函数 | 拦截的篡改场景 | 对应确定性回复来源 | 去润色后是否天然覆盖 |
|---|-----------|--------------|------------------|-------------------|
| 1 | `_misses_stock_values` | 润色丢失库存数字 | 工具结果原文 | 是（不再润色即无丢失） |
| 2 | `_introduces_private_markers` | 润色引入手机号/地址等隐私 | 确定性回复本就脱敏 | 是 |
| 3 | `_misses_pressure_label` | 润色丢失发货压力标签 | 工具结果原文 | 是 |
| 4 | `_misses_action_insight_markers` | 润色丢失优先级/压力洞察 | 工具结果原文 | 是 |
| 5 | `_introduces_relative_delivery_date` | 润色把绝对日期改成"明天"等 | 工具结果绝对日期 | 是 |
| 6 | `_distorts_overdue_delivery_marker` | 润色扭曲"已过约送时间" | 工具结果原文 | 是 |
| 7 | `compresses_employee_order_list` | 润色压缩订单列表 | 确定性列表 | 是 |
| 8 | `_compresses_fulfillment_order_list` | 润色压缩履约风险列表 | 确定性列表 | 是 |
| 9 | `_misses_missing_logistics_marker` | 润色丢失"暂无物流" | 工具结果原文 | 是 |
| 10 | `_distorts_missing_logistics_closed_refund_scope` | 润色乱加"已剔除退款"口径 | 工具结果原文 | 是 |
| 11 | `_introduces_empty_order_detour` | 润色对具体空结果加泛化绕路话 | 确定性 next_action | 是 |
| 12 | `_misses_customer_reply` | 润色丢失给客户可复制回复 | `mixed_reply` 模板 | 是 |
| 13 | `_distorts_top_products_tie` | 润色把并列销量说成第一/爆款 | 工具结果原文 | 是 |
| 14 | `_introduces_top_products_stocking_advice` | 润色对排行擅自加"优先备货" | 工具结果原文 | 是 |
| 15 | `_misses_product_miss_guardrail`（未提交） | 润色把未命中说成缺货 | 工具结果原文 | 是 |
| 16 | `_introduces_no_stock_replacement_example`（未提交） | 润色对缺货编造替代品名 | `mixed_reply` 模板建议 | 是 |

> 说明：附录预填的「是」为初判，阶段 0 需用探针快照逐条实证后再确认。

## 附录 B：执行顺序速查

```
阶段0 基线固化 → 阶段1 去润色 → 阶段3 A/B 拍板 → 阶段2 清理 → 阶段4 收口
```

> 注：阶段 3 的 A/B 决策应在阶段 2 动手前完成，故执行顺序上 3 先于 2。
