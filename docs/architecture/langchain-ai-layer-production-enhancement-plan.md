# LangChain AI 应用层生产增强计划书

> trace_id: `20260709-langchain-ai-layer-production-enhancement`
> 日期：2026-07-09
> 状态：持续执行中，P0-P14c 已完成；P12 样本池准入门禁、P13a 观测证据包、P13b 生产观测发布证据门禁、P14a 生产同步交接报告、P14b 生产运行时版本门禁、P14c callback 失败定位报告入口、P14c callback 稳定化本地修复与生产复验、P15a 真实 replay 样本池脱敏证明准入、P16a LangSmith 运行时配置预检、P17a 真实脱敏回放样本接入准备度报告、P17b-prep 真实 replay pool 条目草稿生成器、P17b-intake 外部接入操作包及可填写模板增强、P17b-candidate 真实 replay 候选样本准入审计、P18a LangSmith 生产灰度发布预检、P18b LangSmith 生产启用操作包、P19a RAG shadow 观测报告、P19b 真实 RAG shadow log 观测输入门禁、P19c 真实 RAG shadow log 外部交接包与来源证明、P21a LangChain AI 层容量门禁、P21b 生产只读资源观测门禁、P21c 生产观测 release gate 加强模式、P21d 生产观测发布证据容量校验、P22a LangChain 发布证据包、P5b/E6a 作品集证据真值清单、P23a 外部证据交接汇总包、P23b 动作分类、P23c 提交前自检摘要、P23d 交接合同静态门禁、P23e readiness 真值汇总、P23f Markdown 外部交接包和外部证据交接治理批量收口门禁已完成，下一步建议进入 P17b 首批真实脱敏样本接入；若生产 LangSmith 已完成人工外发合规和 key 注入，也可继续 P18c 小流量外发灰度。
> 前置成果：[LangChain 生态全面接管 AI 应用层计划书](./langchain-ecosystem-ai-layer-takeover-plan.md)
> 作品集入口：[LangChain AI 应用层作品集说明](./langchain-ai-layer-portfolio.md)

## 一、目标

当前项目已经完成 LangChain / LangGraph 对 AI 应用层的接管。下一阶段不再以“继续扩大框架覆盖率”为主要目标，而是把现有能力推进到可上线、可观测、可评估、可展示的工程状态。

本计划的核心目标是：

```text
把 LangChain / LangGraph 迁移成果转化为生产证据、持续评估体系、线上观测能力和作品集表达。
```

后续增强优先服务四件事：

1. 真实上线可验证。
2. 线上问题可追踪。
3. 效果改进可量化。
4. 面试展示可讲清。

## 二、当前基线

截至 2026-07-09，项目当前基线如下：

| 能力 | 当前状态 | 证据入口 |
|---|---|---|
| 客户机器人编排 | 已由 LangGraph 接管 | `app/service/agents/customer/graph.py` |
| 客户模型调用 | 已有 LangChain model adapter | `app/service/agents/customer/model.py` |
| 客户工具 | 已注册为 LangChain tools | `app/service/agents/tools/customer.py` |
| RAG adapter | 已接入 LangChain Retriever 形态 | `app/service/agents/rag/retriever.py` |
| RAG query plan / rerank | 已有离线 eval 路径 | `app/service/agents/rag/query.py`、`app/service/agents/rag/rerank.py` |
| 员工助手编排 | 已由 LangGraph 接管 | `app/service/agents/employee/graph.py` |
| 员工 planner | 已接入 LangChain structured output fallback | `app/service/agents/employee/structured_planner.py` |
| Agent Eval | 已有双机器人离线聚合报告 | `scripts/report_agent_eval.py` |
| 作品集说明 | 已有当前版架构说明 | `docs/architecture/langchain-ai-layer-portfolio.md` |

已验证的关键结果：

```text
agent_eval status=passed total=58 failed=0 pass_rate=1.0
真实 BGE embedding 路径下 hybrid / planned-hybrid / planned-hybrid+rerank 均达到 Recall@5=1.0、MRR=1.0
```

当前主要缺口：

1. 生产部署与回调探针证据尚未作为本轮 LangChain 接管的正式收口资产归档。
2. LangSmith / trace 观测入口已有配置基础，但缺少生产级运行报告闭环。
3. Eval 仍以 fixture 和离线脚本为主，真实业务回放样本不足。
4. planned-hybrid / rerank 尚未进入灰度热路径。
5. 面试材料已有文本说明，但缺少一套“一页讲清”的证据包。

## 三、边界原则

### 3.1 继续坚持的边界

LangChain / LangGraph 继续负责：

1. 模型调用。
2. 工具绑定。
3. Agent 节点编排。
4. Retriever adapter。
5. structured output。
6. tracing config。
7. eval 报告。

项目业务层继续负责：

1. 订单、商品、库存、退款、售后事实。
2. 客户主档和客户线索。
3. 知识发布状态。
4. SQLite repository 和 migration。
5. 有赞、企微、后台 API 的业务处理。

### 3.2 后续增强不做什么

本计划不把以下事项作为近期目标：

1. 不为了“更彻底”而让 LangChain 直接读写业务数据库。
2. 不把员工助手最终回复交给 LLM 自由润色。
3. 不在没有真实 eval 对照前打开 planned/rerank 热路径。
4. 不把观测、报告、作品集文档和业务逻辑混成一次大改。

## 四、阶段路线

### 阶段 P0：生产上线验证闭环

目标：确认当前 LangChain AI 应用层接管成果在生产服务器可运行，并形成可追溯证据。

改动范围：

- 原则上不改运行时代码。
- 必要时只补充探针脚本参数、报告输出和文档索引。
- 不引入新的 AI 行为。

执行步骤：

1. 确认本地工作区干净，记录当前 commit、VERSION 和依赖版本。
2. 推送 `origin/master` 和 `server/master`。
3. 在生产服务器确认 `/opt/yunxibakebot` fast-forward 到目标 commit。
4. 重启 `yunxibakebot` 服务。
5. 检查 `/health` 和 `/ready`。
6. 运行企微员工助手 callback probe。
7. 运行客户机器人最小 RAG 正向探针。
8. 运行员工助手订单查询正向探针。
9. 将生产验证输出登记到 evidence index 或 LOGBOOK。

验收命令：

```powershell
git status -sb
git rev-parse HEAD
git push origin master
git push server master
git ls-remote origin master
git ls-remote server master
python scripts/report_agent_eval.py --latest
python scripts/report_retrieval_eval_matrix.py --db data/bot.db --fixture tests/fixtures/customer_rag_golden_cases.json --k 5
python scripts/check_project.py --skip-tests
python scripts/check_evidence_index.py --summary
```

生产侧验收：

```powershell
curl.exe https://yunxifood.cn/health
curl.exe https://yunxifood.cn/ready
python scripts/check_wecom_employee_agent_callback.py --json --output reports/wecom-employee-agent/langchain-prod-callback.json
```

完成标准：

- 生产 `/health` 和 `/ready` 均通过。
- 企微 callback probe 有可读 JSON 证据。
- 至少一个客户机器人 RAG 正向问题和一个员工助手订单查询正向问题通过。
- LOGBOOK 或 evidence index 能追溯 commit、命令、结果和报告路径。

回滚策略：

- 若服务启动失败，回退到上一个已知健康 commit 并重启。
- 若 callback probe 失败但 `/health`、`/ready` 正常，先保留服务运行，定位企微入口或环境变量。
- 若客户 RAG 或员工助手行为失败，关闭相关 feature flag 或回退本次 commit。

### 阶段 P1：线上 Trace 与 LangSmith 观测

目标：让每次 AI 回复可以追踪模型、工具、RAG、耗时、失败回退和最终结果。

改动范围：

- `app/service/agents/observability.py`
- 客户 graph 节点 trace 输出。
- 员工 graph 节点 trace 输出。
- 本地 trace events 与 LangSmith 配置桥接。
- 运行报告脚本。

建议改动：

1. 明确统一 trace 字段：
   - `trace_id`
   - `conversation_id`
   - `channel`
   - `agent`
   - `node`
   - `model`
   - `tool_name`
   - `knowledge_entry_ids`
   - `latency_ms`
   - `fallback_reason`
   - `final_status`
2. 新增 LangSmith 开关：
   - 默认本地关闭。
   - 生产可通过环境变量打开。
   - 缺少 key 时不得影响主流程。
3. 为客户机器人补齐：
   - model 节点耗时。
   - tool 调用次数。
   - RAG 命中条目。
   - fallback 回复原因。
4. 为员工助手补齐：
   - rule-first 命中或 structured planner 命中。
   - 工具计划。
   - deterministic finalizer 状态。
5. 新增只读报告脚本：
   - 汇总最近一段 trace。
   - 输出失败率、平均耗时、工具调用分布、RAG 命中分布。

验收命令：

```powershell
python -m pytest tests/service/agents -q --no-cov
python scripts/report_agent_eval.py --latest
python scripts/check_project.py --skip-tests
```

建议新增验收：

```powershell
python scripts/report_agent_traces.py --latest --summary
python scripts/report_agent_traces.py --latest --json
```

完成标准：

- LangSmith 未配置时主流程不失败。
- 本地 trace 报告能看到客户机器人和员工助手的节点级摘要。
- 至少覆盖成功、工具失败、RAG 未命中、fallback 四类事件。
- 观测字段不包含手机号、地址、open_id 等未脱敏敏感信息。

### 阶段 P2：真实业务 Eval 数据集扩容

目标：把 eval 从工程 smoke 扩展为真实业务回归资产。

改动范围：

- `tests/fixtures/`
- `scripts/eval_customer_agent.py`
- `scripts/eval_employee_agent.py`
- `scripts/report_agent_eval.py`
- `docs/harness-engineering/core/evidence-index.md`

执行步骤：

1. 定义脱敏样本格式：
   - 用户问题。
   - 期望命中知识或工具。
   - 禁止出现的回复。
   - 必须出现的事实。
   - 允许转人工的条件。
2. 扩充客户机器人样本：
   - 商品咨询。
   - 库存咨询。
   - 配送时间。
   - 退款售后。
   - 转人工。
   - 知识未命中。
3. 扩充员工助手样本：
   - 查订单。
   - 查客户。
   - 查发货时间。
   - 弱关键词。
   - 不支持意图。
4. 给 eval 报告增加：
   - `--json-out`
   - `--fail-fast`
   - `--case-id`
   - `--agent customer|employee|all`
5. 把 eval 结果归档到 `reports/agent-eval/`，并在 evidence index 登记关键版本。

验收命令：

```powershell
python scripts/eval_customer_agent.py --summary
python scripts/eval_employee_agent.py --summary
python scripts/report_agent_eval.py --latest
python scripts/report_agent_eval.py --latest --json-out reports/agent-eval/latest.json
python scripts/check_evidence_index.py --summary
```

完成标准：

- 客户机器人 eval cases 从当前 9 项扩到至少 40 项。
- 员工助手 eval cases 保持或超过 60 项。
- 每个 case 有稳定 `case_id`。
- eval 失败能定位到 agent、case、断言和实际输出。
- 报告可作为作品集证据引用。

## 十五、P2a 落地记录

2026-07-09 已完成 P2 真实业务 Eval 数据集扩容的第一切片：

- `app/service/agents/evaluation.py` 新增通用 eval helper：
  - `filter_agent_eval_result()` 支持按稳定 `case_id` 过滤。
  - `apply_fail_fast()` 支持保留到首个失败 case。
  - `write_json_report()` 支持写入 UTF-8 JSON 报告，并自动创建父目录。
- `scripts/eval_customer_agent.py` 新增：
  - `--case-id`
  - `--fail-fast`
  - `--json-out`
- `scripts/eval_employee_agent.py` 新增：
  - `--case-id`
  - `--fail-fast`
  - `--json-out`
- `scripts/report_agent_eval.py` 新增：
  - `--agent customer|employee|all`
  - `--case-id`
  - `--fail-fast`
  - `--json-out`
- 本切片不扩真实样本数量，先补齐 runner 能力，避免后续客户 40+、员工 60+ 样本扩容后无法快速定位失败。

P2a 验收：

```powershell
python -m pytest tests/service/agents/test_evaluation.py tests/scripts/test_agent_eval_scripts.py -q --no-cov
python -m ruff check app/service/agents/evaluation.py scripts/eval_customer_agent.py scripts/eval_employee_agent.py scripts/report_agent_eval.py tests/service/agents/test_evaluation.py tests/scripts/test_agent_eval_scripts.py
python -m ruff format --check app/service/agents/evaluation.py scripts/eval_customer_agent.py scripts/eval_employee_agent.py scripts/report_agent_eval.py tests/service/agents/test_evaluation.py tests/scripts/test_agent_eval_scripts.py
python scripts/eval_customer_agent.py --summary
python scripts/eval_employee_agent.py --summary
python scripts/report_agent_eval.py --latest --json-out reports/agent-eval/latest.json
python scripts/report_agent_eval.py --agent customer --case-id customer-product-001 --summary
python scripts/report_agent_eval.py --agent employee --case-id employee.capability_contracts --json
```

P2a 验证结果：

```text
10 项 targeted tests 通过。
Ruff check 通过。
Ruff format --check 通过。
customer_agent_eval status=passed total=9 failed=0 pass_rate=1.0。
employee_agent_eval status=passed total=49 failed=0 pass_rate=1.0。
agent_eval JSON 归档到 reports/agent-eval/latest.json，summary 为 passed 58/58。
customer case filter 可收敛到 total=1。
employee case filter 可输出 employee.capability_contracts 单 case JSON。
```

P2 后续：

- P2c 扩充员工助手 eval 样本，目标保持或超过 60 项，并强化查订单、查客户、查发货时间、弱关键词和不支持意图。

## 十六、P2b 落地记录

2026-07-09 已完成 P2 真实业务 Eval 数据集扩容的第二切片：

- `tests/fixtures/customer_rag_golden_cases.json` 从 8 条业务 case 扩充到 40 条业务 case。
- 客户 eval 总数从 9 项提升到 41 项，其中 1 项为 fixture governance，40 项为客户业务样本。
- 样本覆盖：
  - 商品咨询：10 条。
  - 库存咨询：8 条。
  - 配送时间 / 配送范围 / 自提：7 条。
  - 退款售后 / 改单 / 配送异常：7 条。
  - 转人工 / 过敏 / 定制 / 查订单：4 条。
  - 知识未命中治理：4 条。
- 新增 `inventory` 和 `knowledge_no_match` 两个 required group；`knowledge_no_match` 不写成无 relevant 的假空样本，而是要求命中人工客服 / 转人工 / 食品安全等治理知识，避免破坏 retrieval eval 的可评估性。

P2b 验收：

```powershell
python -m pytest tests/scripts/test_check_customer_rag_golden_cases.py tests/scripts/test_agent_eval_scripts.py::test_customer_eval_result_uses_golden_cases -q --no-cov
python scripts/check_customer_rag_golden_cases.py --summary
python scripts/eval_customer_agent.py --summary
python scripts/report_agent_eval.py --agent customer --summary
python scripts/report_agent_eval.py --latest --json-out reports/agent-eval/latest.json
python scripts/report_retrieval_eval_matrix.py --db data/bot.db --fixture tests/fixtures/customer_rag_golden_cases.json --k 5
```

P2b 验证结果：

```text
客户 fixture 结构校验通过：customer_rag_golden_cases status=passed total=47 failed=0。
客户 eval 通过：customer_agent_eval status=passed total=41 failed=0 pass_rate=1.0。
双机器人聚合 eval 通过：agent_eval status=passed total=90 failed=0 pass_rate=1.0。
RAG 矩阵在 400 条启用知识、40 条客户标注样本下可跑通；best=hybrid，Recall@5=0.975，MRR=0.9437。
```

P2 后续：

- P2c 已完成员工助手 eval 样本扩容，员工 eval 从 49 项推进到 62 项，覆盖查订单、查客户、查发货时间、弱关键词和不支持意图。
- P2d 已把 expanded customer fixture、员工 planner 和双机器人聚合结果的分组统计加入 eval 报告，方便作品集展示。

## 十七、P2c 落地记录

2026-07-09 已完成 P2 真实业务 Eval 数据集扩容的第三切片：

- `scripts/wecom_employee_agent_probe_cases.py` 新增 13 条 P2c 员工助手自由问法样本。
- 员工助手 planner 探针从 48 条提升到 61 条。
- 员工助手 eval 总数从 49 项提升到 62 项，其中 1 项为 capability contracts 聚合治理 case，61 项为 planner 离线样本。
- 样本覆盖：
  - 查订单：交易成功、已关闭、待收货、待发货。
  - 查发货时间：上午、下午待处理订单。
  - 商品销量：草莓蛋糕当日销量。
  - 精确订单：订单详情、客户复购。
  - 查客户：李四客户线索、王女士地址线索。
  - 知识问答：退款规则。
  - 不支持意图：写诗。
- 本切片不改线上 planner、工具执行、业务 service 或 deterministic finalizer，只把现有可识别能力固化为回归样本。

P2c 验收：

```powershell
python scripts/check_wecom_employee_agent_plans.py --json
python scripts/eval_employee_agent.py --summary
python scripts/report_agent_eval.py --latest --json-out reports/agent-eval/latest.json
python -m pytest tests/scripts/test_agent_eval_scripts.py::test_employee_eval_result_includes_planner_and_contracts -q --no-cov
```

P2c 验证结果：

```text
员工助手规划探针通过：61 项失败 0。
员工助手 eval 通过：employee_agent_eval status=passed total=62 failed=0 pass_rate=1.0。
双机器人聚合 eval 通过：agent_eval status=passed total=103 failed=0 pass_rate=1.0。
聚焦测试通过：1 项失败 0。
```

P2 当前状态：

- 客户机器人 eval：41 项通过，其中 40 条业务样本。
- 员工助手 eval：62 项通过，其中 61 条 planner 样本。
- 双机器人聚合 eval 已提升到 103 项，`python scripts/report_agent_eval.py --latest --json-out reports/agent-eval/latest.json` 可归档当前报告摘要。
- P2d 已把 case group 统计、agent 分布和新增样本摘要加入 eval report metadata，方便作品集展示。

## 十八、P2d 落地记录

2026-07-09 已完成 P2 真实业务 Eval 数据集扩容的第四切片：

- `app/service/agents/evaluation.py` 新增 `summarize_agent_eval_results()` 和 `summarize_eval_cases_by_group()`。
- 单 agent eval JSON 新增 `case_groups`：
  - 客户机器人可直接展示商品咨询、库存、配送、退款售后、转人工和知识未命中治理覆盖。
  - 员工助手可直接展示 planner 与 capability contracts 覆盖。
- 双机器人聚合 eval JSON 新增：
  - `agent_totals`：customer 41 项、employee 62 项。
  - 顶层 `case_groups`：跨 agent 的统一覆盖矩阵。
- 本切片只扩离线 eval 报告结构，不改变客户/员工热路径、planner、RAG、工具执行或业务 service。

P2d 验收：

```powershell
python -m pytest tests/service/agents/test_evaluation.py tests/scripts/test_agent_eval_scripts.py -q --no-cov
python scripts/report_agent_eval.py --latest --json-out reports/agent-eval/latest.json
```

P2d 验证结果：

```text
Agent Eval 模型和脚本测试通过：10 项失败 0。
双机器人聚合 eval 通过：agent_eval status=passed total=103 failed=0 pass_rate=1.0。
JSON 抽查已包含 agent_totals、顶层 case_groups 和每个 agent 的 case_groups。
```

P2 当前状态：

- P2a eval runner 归档能力完成。
- P2b 客户机器人业务样本扩容完成。
- P2c 员工助手样本扩容完成。
- P2d eval report metadata 完成。
- 下一阶段建议进入 P3：RAG 热路径灰度增强，先做 feature flag 与 shadow compare，不直接改变线上回复。

### 阶段 P3：RAG 热路径灰度增强

目标：把 planned-hybrid / rerank 从离线评估能力推进到可灰度的线上候选能力。

改动范围：

- `app/service/agents/rag/retriever.py`
- `app/service/agents/rag/query.py`
- `app/service/agents/rag/rerank.py`
- 客户机器人 RAG 调用入口。
- retrieval logs。
- RAG eval matrix 脚本。

执行步骤：

1. 增加 feature flag：
   - `RAG_RETRIEVAL_MODE=hybrid`
   - `RAG_RETRIEVAL_MODE=planned-hybrid`
   - `RAG_RETRIEVAL_MODE=planned-hybrid-rerank`
2. 默认生产仍保持当前稳定模式。
3. 新增 shadow compare：
   - 主链路仍用稳定结果。
   - 后台并行计算 planned/rerank 候选。
   - 记录排序差异，不影响用户回复。
4. 增加检索日志字段：
   - query plan。
   - vector top-k。
   - BM25 top-k。
   - RRF 后 top-k。
   - rerank 后 top-k。
   - final injected context。
5. 连续收集真实问题差异报告后再决定是否灰度打开。

验收命令：

```powershell
python scripts/report_retrieval_eval_matrix.py --db data/bot.db --fixture tests/fixtures/customer_rag_golden_cases.json --k 5
python scripts/check_knowledge_retrieval_logs_smoke.py --json
python scripts/check_knowledge_audience_governance_smoke.py --json
python -m pytest tests/service/agents/test_rag_retriever.py tests/scripts/test_report_retrieval_eval_matrix.py -q --no-cov
```

建议新增验收：

```powershell
python scripts/report_retrieval_shadow_compare.py --db data/bot.db --fixture tests/fixtures/customer_rag_golden_cases.json --k 5 --json-out reports/retrieval-shadow/latest.json
```

完成标准：

- feature flag 默认值不改变现有生产行为。
- shadow compare 能输出稳定模式与候选模式的差异。
- planned/rerank 候选在真实样本上不低于稳定模式。
- RAG 日志能解释“为什么命中这条知识”。

## 十九、P3a 落地记录

2026-07-09 已完成 P3 RAG 热路径灰度增强的第一切片：

- 新增 `scripts/report_retrieval_shadow_compare.py`，默认以 `hybrid` 作为稳定 baseline，以 `planned-hybrid` 和 `planned-hybrid+rerank` 作为候选模式。
- shadow compare 复用 `scripts/report_retrieval_eval_matrix.py` 的索引构建与 searcher 组装，避免重复实现向量、BM25、planned query 和 rerank 包装逻辑。
- 报告输出：
  - baseline 指标。
  - candidate 指标。
  - `delta_recall_at_k` / `delta_mrr`。
  - 逐 case 的 baseline top-k、candidate top-k、title、changed 和 overlap_count。
- 本切片只做离线 shadow compare，不接入客户热路径，不改变线上回复，不启用 rerank。

P3a 验收：

```powershell
python -m pytest tests/scripts/test_report_retrieval_shadow_compare.py tests/scripts/test_report_retrieval_eval_matrix.py tests/scripts/test_eval_retrieval.py -q --no-cov
python scripts/report_retrieval_shadow_compare.py --db data/bot.db --fixture tests/fixtures/customer_rag_golden_cases.json --k 5 --json-out reports/retrieval-shadow/latest.json
```

P3a 验证结果：

```text
shadow compare / matrix / retrieval eval 测试通过：18 项失败 0。
真实 embedding 路径下，语料库 data\bot.db 400 条启用知识，客户 fixture 40 条可评估样本。
baseline hybrid: Recall@5=0.975, MRR=0.9437。
planned-hybrid: Recall@5=0.975, MRR=0.9437，delta_recall=0.0，delta_mrr=0.0。
planned-hybrid+rerank: Recall@5=0.95, MRR=0.9375，delta_recall=-0.025，delta_mrr=-0.0062。
```

P3 后续：

- P3b 已补 `RAG_RETRIEVAL_MODE` feature flag 的配置解析与默认值测试，生产默认仍保持 `hybrid`。
- P3c 再把 shadow compare 接入真实检索日志或显式运维探针，连续收集差异后再决定是否灰度打开 planned/rerank。
- 当前数据不支持热启 `planned-hybrid+rerank`，因为它低于 baseline。

## 二十、P3b 落地记录

2026-07-09 已完成 P3 RAG 热路径灰度增强的第二切片：

- `app/config.py` 新增 RAG 检索模式常量：
  - `hybrid`
  - `planned-hybrid`
  - `planned-hybrid-rerank`
- `Settings.RAG_RETRIEVAL_MODE` 默认值为 `hybrid`。
- `RAG_RETRIEVAL_MODE` 会在 Settings 初始化时做合法值校验：
  - 自动 `strip()` 和小写归一化。
  - 非法值直接抛出 pydantic validation error。
- 本切片不接入客户热路径，不改变线上回复，不启用 planned/rerank；配置字段只是为后续 P3c/P3d 灰度入口预留安全门禁。

P3b 验收：

```powershell
python -m pytest tests/test_config.py -q --no-cov
python -m ruff check app/config.py tests/test_config.py
python -m ruff format --check app/config.py tests/test_config.py
python -c "import sys; import app.config; print({name: (name in sys.modules) for name in ['langsmith','langchain_openai','langgraph']})"
```

P3b 验证结果：

```text
配置测试通过：7 项失败 0。
Ruff check 通过。
Ruff format --check 通过。
冷导入 app.config 不加载 langsmith、langchain_openai、langgraph。
```

P3 后续：

- P3c 已把 `RAG_RETRIEVAL_MODE` 接入只读 strategy/factory helper，生成对应的 LangChain retriever adapter 参数，但默认仍保持 `hybrid`。
- P3d 再考虑显式运维探针或 shadow logging，主链路继续使用稳定模式。

## 二十一、P3c 落地记录

2026-07-09 已完成 P3 RAG 热路径灰度增强的第三切片：

- 新增 `app/service/agents/rag/modes.py`。
- 新增 `RagRetrievalModeStrategy`：
  - `mode`
  - `query_planner`
  - `document_reranker`
  - `uses_query_planning`
  - `uses_rerank`
- 新增 `resolve_rag_retrieval_mode_strategy()`：
  - `hybrid` -> 不挂 query planner / reranker。
  - `planned-hybrid` -> 挂 `build_customer_rag_query_plan()`。
  - `planned-hybrid-rerank` -> 挂 `build_customer_rag_query_plan()` 和 `rerank_documents_by_query_rules()`。
- 新增 `build_langchain_knowledge_retriever_for_mode()`，把 mode strategy 转成 `LangChainKnowledgeRetriever` 参数。
- 本切片不接入客户 graph、context builder 或线上回复；只提供后续灰度入口需要的受控 helper。

P3c 验收：

```powershell
python -m pytest tests/service/agents/test_rag_retriever.py -q --no-cov
python -m ruff check app/service/agents/rag/modes.py tests/service/agents/test_rag_retriever.py
python -m ruff format --check app/service/agents/rag/modes.py tests/service/agents/test_rag_retriever.py
python -c "import sys; import app.service.agents.rag.modes; print({name: (name in sys.modules) for name in ['langsmith','langchain_openai','langgraph','langchain_core']})"
```

P3c 验证结果：

```text
RAG retriever adapter 测试通过：12 项失败 0。
Ruff check 通过。
Ruff format --check 通过。
冷导入 app.service.agents.rag.modes 不加载 langsmith、langchain_openai、langgraph、langchain_core。
```

P3 后续：

- P3d 已新增显式 shadow compare 运维探针，把当前稳定检索结果与候选策略并排输出，并把当前 `RAG_RETRIEVAL_MODE` 写入报告 metadata。
- P3e 再考虑将 `RAG_RETRIEVAL_MODE` 接入客户 RAG 热路径；默认仍保持 `hybrid`，且只有当 shadow compare 连续证明候选不低于 baseline，才考虑打开 planned/rerank。

## 二十二、P3d 落地记录

2026-07-10 已完成 P3 RAG 热路径灰度增强的第四切片：

- `scripts/report_retrieval_shadow_compare.py` 新增 `--baseline-mode`，可显式选择 baseline 检索模式。
- `scripts/report_retrieval_shadow_compare.py` 新增可重复的 `--candidate-mode`，支持只比较一个候选模式，也支持继续使用默认候选：
  - `planned-hybrid`
  - `planned-hybrid-rerank`
  - `planned-hybrid+rerank`
- shadow compare 报告 metadata 新增 `configured_rag_retrieval_mode`，用于并排展示当前运行配置与离线候选模式。
- Windows 控制台下 `--json` 输出改为 UTF-8 stdout，避免知识标题含特殊符号时触发 GBK 编码失败。
- 本切片仍不接入客户 graph、context builder 或线上回复；只增强显式运维探针和离线证据。

P3d 验收：

```powershell
python -m pytest tests\scripts\test_report_retrieval_shadow_compare.py tests\service\agents\test_rag_retriever.py -q --no-cov
python -m ruff check scripts\report_retrieval_shadow_compare.py tests\scripts\test_report_retrieval_shadow_compare.py
python -m ruff format --check scripts\report_retrieval_shadow_compare.py tests\scripts\test_report_retrieval_shadow_compare.py
python scripts\report_retrieval_shadow_compare.py --db data\bot.db --fixture tests\fixtures\customer_rag_golden_cases.json --k 5 --json-out reports\retrieval-shadow\latest.json
python scripts\report_retrieval_shadow_compare.py --db data\bot.db --fixture tests\fixtures\customer_rag_golden_cases.json --k 5 --candidate-mode planned-hybrid-rerank --json
```

P3d 验证结果：

```text
RAG shadow compare 与 mode strategy 测试通过：17 项失败 0。
Ruff check 通过。
Ruff format --check 通过。
真实 embedding 路径下，语料库 data\bot.db 400 条启用知识，客户 fixture 40 条可评估样本。
baseline hybrid: Recall@5=0.975, MRR=0.9437。
planned-hybrid: Recall@5=0.975, MRR=0.9437，delta_recall=0.0，delta_mrr=0.0。
planned-hybrid+rerank: Recall@5=0.95, MRR=0.9375，delta_recall=-0.025，delta_mrr=-0.0062。
显式单候选 `--candidate-mode planned-hybrid-rerank --json` 通过，不再因 Windows 控制台编码失败。
```

P3 后续：

- P3e 已把 `RAG_RETRIEVAL_MODE` 接入客户 RAG 热路径；默认 `hybrid` 仍保持原稳定路径，非默认模式才走 LangChain retriever adapter。
- 当前数据仍不支持热启 `planned-hybrid-rerank`。

## 二十三、P3e 落地记录

2026-07-10 已完成 P3 RAG 热路径灰度增强的第五切片：

- 客户 RAG 热路径现在读取 `settings.RAG_RETRIEVAL_MODE`。
- 默认 `hybrid` 模式继续直接调用 `KnowledgeRetriever.search()`，不额外进入 LangChain retriever，确保生产默认行为稳定。
- `planned-hybrid` 和 `planned-hybrid-rerank` 模式通过 `build_langchain_knowledge_retriever_for_mode()` 进入 LangChain retriever adapter：
  - `planned-hybrid` 启用 query planner。
  - `planned-hybrid-rerank` 启用 query planner + document reranker。
- 新增 `document_to_knowledge_entry()`，把 LangChain Document 还原成现有 `KnowledgeEntry`，让 prompt、context budget、guard source、知识 ID trace 继续复用原业务模型。
- 本切片不让 LangChain 直接读取数据库，不绕过 `KnowledgeRetriever` 的 audience 过滤、发布状态、有效期、实时价格/库存注入和检索日志。

P3e 验收：

```powershell
python -m pytest tests\service\test_chat_refactor.py tests\service\agents\test_rag_retriever.py -q --no-cov
python -m ruff check app\service\chat_context.py app\service\agents\rag\documents.py tests\service\test_chat_refactor.py
python -m ruff format --check app\service\chat_context.py app\service\agents\rag\documents.py tests\service\test_chat_refactor.py
python scripts\eval_customer_agent.py --summary
$env:RAG_RETRIEVAL_MODE='planned-hybrid'; python scripts\eval_customer_agent.py --summary; Remove-Item Env:\RAG_RETRIEVAL_MODE
python scripts\report_retrieval_eval_matrix.py --db data\bot.db --fixture tests\fixtures\customer_rag_golden_cases.json --k 5
```

P3e 验证结果：

```text
chat_context 与 RAG retriever 测试通过：37 项失败 0。
Ruff check 通过。
Ruff format --check 通过。
客户机器人默认模式 eval 通过：41 项失败 0。
客户机器人 planned-hybrid 环境变量模式 eval 通过：41 项失败 0。
RAG 矩阵保持：hybrid Recall@5=0.975、MRR=0.9437；planned-hybrid 持平；planned-hybrid+rerank Recall@5=0.95、MRR=0.9375。
```

P3 当前状态：

- P3a shadow compare 报告完成。
- P3b `RAG_RETRIEVAL_MODE` 配置门禁完成。
- P3c retrieval mode strategy/helper 完成。
- P3d 显式 shadow compare 运维探针完成。
- P3e 客户 RAG 热路径 feature flag 接入完成。
- 下一阶段建议进入 P4：事实敏感场景治理增强，继续强化订单、退款、售后、库存、价格和转人工等高风险场景。

### 阶段 P4：事实敏感场景治理增强

目标：强化订单、售后、退款、库存、转人工等高风险场景的可控性。

改动范围：

- 客户机器人 guard。
- RAG context builder。
- transfer / handoff 策略。
- golden cases。
- eval scripts。

执行步骤：

1. 定义事实敏感场景清单：
   - 订单状态。
   - 退款规则。
   - 售后承诺。
   - 实时库存。
   - 价格。
   - 转人工。
2. 为每类场景定义回复策略：
   - 必须来自工具。
   - 必须来自知识。
   - 必须转人工。
   - 可以一般性说明。
3. 增加禁止行为断言：
   - 不编造订单。
   - 不承诺未配置退款。
   - 不输出过期库存。
   - 不泄露客户隐私。
4. 对库存继续坚持动静分离：
   - embedding 文本保留静态语义。
   - 在线 context 注入实时库存。
5. 增加敏感场景 eval cases。

验收命令：

```powershell
python scripts/report_agent_eval.py --latest
python scripts/check_customer_rag_golden_cases.py --summary
python scripts/check_knowledge_audience_governance_smoke.py --json
python scripts/check_project.py --skip-tests
```

完成标准：

- 每类事实敏感场景至少 5 个 eval cases。
- 对订单、退款、库存、转人工有明确断言。
- 回复策略能在作品集里讲成“AI 客服治理能力”，而不是单纯 prompt 约束。

## 二十四、P4a 落地记录

2026-07-10 已完成 P4 事实敏感场景治理增强的第一切片：

- `tests/fixtures/customer_rag_golden_cases.json` 新增 `required_sensitive_scenarios`：
  - `order`
  - `refund`
  - `after_sales`
  - `inventory`
  - `price`
  - `human_transfer`
- 客户业务样本从 40 条扩展到 70 条，客户 eval 总数从 41 项提升到 71 项。
- 新增 30 条事实敏感样本，覆盖：
  - 订单状态、改地址、提前配送、忘记订单号。
  - 退款、已制作订单退款、退运费、退款到账。
  - 售后破损、漏发、投诉、名字写错、食品安全。
  - 实时库存、批量预订、预留、门店/小程序库存不一致、下架商品。
  - 商品价格、优惠价、定制报价、配送费、最低价。
  - 明确转人工、投诉、过敏、团购价格账期、订单退款复合场景。
- `scripts/check_customer_rag_golden_cases.py` 新增敏感场景覆盖检查，每类至少 5 条。
- `scripts/eval_customer_agent.py` 在 case metadata 中输出 `sensitive_scenarios`，后续作品集和报告可以直接展示治理覆盖。
- 本切片只扩展脱敏 eval 和机器检查，不改变客户热路径、prompt、工具执行或转人工策略。

P4a 验收：

```powershell
python scripts\check_customer_rag_golden_cases.py --summary
python scripts\eval_customer_agent.py --summary
python scripts\report_agent_eval.py --latest --json-out reports\agent-eval\latest.json
python -m pytest tests\scripts\test_check_customer_rag_golden_cases.py tests\scripts\test_agent_eval_scripts.py tests\scripts\test_report_retrieval_eval_matrix.py tests\scripts\test_eval_retrieval.py -q --no-cov
python -m ruff check scripts\check_customer_rag_golden_cases.py scripts\eval_customer_agent.py tests\scripts\test_check_customer_rag_golden_cases.py tests\scripts\test_agent_eval_scripts.py
python -m ruff format --check scripts\check_customer_rag_golden_cases.py scripts\eval_customer_agent.py tests\scripts\test_check_customer_rag_golden_cases.py tests\scripts\test_agent_eval_scripts.py
python scripts\report_retrieval_eval_matrix.py --db data\bot.db --fixture tests\fixtures\customer_rag_golden_cases.json --k 5
```

P4a 验证结果：

```text
客户 golden cases 结构与敏感场景覆盖检查通过：83 项失败 0。
客户机器人 eval 通过：71 项失败 0。
双机器人聚合 eval 通过：133 项失败 0。
相关脚本与 eval 测试通过：26 项失败 0。
Ruff check 通过。
Ruff format --check 通过。
RAG 矩阵在 400 条启用知识、70 条可评估客户样本下可跑通。
hybrid: Recall@5=0.9857, MRR=0.8881。
planned-hybrid: Recall@5=0.9857, MRR=0.8881。
planned-hybrid+rerank: Recall@5=0.9714, MRR=0.9136。
```

P4 后续：

- P4b 已把 `sensitive_scenarios` 接入更明确的 guardrail 策略契约断言，例如订单必须禁止编造或要求人工/确认，退款必须禁止承诺或要求按订单状态确认，库存必须强调实时/门店/人工确认。
- P4c 再考虑在 trace 中记录事实敏感场景分类，但不记录敏感明文。

## 二十五、P4b 落地记录

2026-07-10 已完成 P4 事实敏感场景治理增强的第二切片：

- `scripts/check_customer_rag_golden_cases.py` 新增 `SENSITIVE_SCENARIO_POLICY_KEYWORDS`，集中定义 6 类事实敏感场景的 guardrail 策略契约：
  - `order`
  - `refund`
  - `after_sales`
  - `inventory`
  - `price`
  - `human_transfer`
- 每个带 `sensitive_scenarios` 的客户样本都必须在 `guardrails` 中命中对应场景的策略关键词组。
- `scripts/eval_customer_agent.py` 复用同一套策略契约，为每条敏感 case 输出 `sensitive_policy.<scenario>` 断言。
- P4b 过程中机器检查抓出 4 个 guardrail 缺口，已补强 3 条事实敏感样本文案：
  - 订单提前配送必须落到订单/人工确认。
  - 退运费必须明确退款/退运费不能承诺。
  - 退款到账时间必须明确不能编造并转人工或按支付平台确认。
- 本切片仍只强化脱敏 eval、fixture governance 和报告断言，不改变线上回复热路径。

P4b 验收：

```powershell
python -m pytest tests\scripts\test_check_customer_rag_golden_cases.py tests\scripts\test_agent_eval_scripts.py -q --no-cov
python scripts\check_customer_rag_golden_cases.py --summary
python scripts\eval_customer_agent.py --summary
python scripts\report_agent_eval.py --latest --json-out reports\agent-eval\latest.json
python -m ruff check scripts\check_customer_rag_golden_cases.py scripts\eval_customer_agent.py tests\scripts\test_check_customer_rag_golden_cases.py tests\scripts\test_agent_eval_scripts.py
python -m ruff format --check scripts\check_customer_rag_golden_cases.py scripts\eval_customer_agent.py tests\scripts\test_check_customer_rag_golden_cases.py tests\scripts\test_agent_eval_scripts.py
python scripts\report_retrieval_eval_matrix.py --db data\bot.db --fixture tests\fixtures\customer_rag_golden_cases.json --k 5
```

P4b 验证结果：

```text
策略契约与 eval 脚本测试通过：12 项失败 0。
客户 golden cases 结构、覆盖与策略契约检查通过：130 项失败 0。
客户机器人 eval 通过：71 项失败 0。
双机器人聚合 eval 通过：133 项失败 0。
Ruff check 通过。
Ruff format --check 通过。
RAG 矩阵保持：hybrid Recall@5=0.9857、MRR=0.8881；planned-hybrid 持平；planned-hybrid+rerank Recall@5=0.9714、MRR=0.9136。
```

P4 后续：

- P4c 已在报告层记录事实敏感场景分类，只输出结构化标签、数量、失败数和通过率，不记录用户原文、订单号、手机号、地址或 open_id。
- P4d 可进一步增加“回复输出禁止行为”离线断言，例如订单场景不能出现编造状态、退款场景不能出现未验证承诺。

## 二十六、P4c 落地记录

2026-07-10 已完成 P4 事实敏感场景治理增强的第三切片：

- `app/service/agents/evaluation.py` 新增 `summarize_eval_cases_by_sensitive_scenario()`。
- 单 agent eval JSON 新增 `sensitive_scenarios`。
- 双机器人聚合 eval JSON 顶层新增 `sensitive_scenarios`。
- 汇总字段只包含：
  - `scenario`
  - `total`
  - `failed`
  - `passed`
  - `pass_rate`
- 本切片只记录结构化场景标签和统计，不记录用户原文、订单号、手机号、地址、open_id 或工具结果明文。

P4c 验收：

```powershell
python -m pytest tests\service\agents\test_evaluation.py tests\scripts\test_agent_eval_scripts.py -q --no-cov
python scripts\report_agent_eval.py --latest --json-out reports\agent-eval\latest.json
python -m ruff check app\service\agents\evaluation.py tests\service\agents\test_evaluation.py tests\scripts\test_agent_eval_scripts.py
python -m ruff format --check app\service\agents\evaluation.py tests\service\agents\test_evaluation.py tests\scripts\test_agent_eval_scripts.py
```

P4c 验证结果：

```text
Agent Eval 模型与脚本测试通过：10 项失败 0。
双机器人聚合 eval 通过：133 项失败 0。
Ruff check 通过。
Ruff format --check 通过。
JSON 抽查显示顶层与 customer agent 均包含：
after_sales 8、human_transfer 16、inventory 5、order 6、price 6、refund 6，失败数均为 0。
```

P4 后续：

- P4d 已增加“回复输出禁止行为”离线契约，订单、退款、售后、库存、价格和转人工场景均可派生 `forbidden_reply_patterns`，为后续真实回复回放断言做准备。
- P4e 再根据需要决定是否把事实敏感场景分类写入真实 trace，但必须保持脱敏，只写结构化标签。

## 二十七、P4d 落地记录

2026-07-10 已完成 P4 事实敏感场景治理增强的第四切片：

- `scripts/check_customer_rag_golden_cases.py` 新增 `SENSITIVE_SCENARIO_FORBIDDEN_REPLY_PATTERNS`。
- 禁止回复模式按 `sensitive_scenarios` 派生，不要求每条 fixture 重复维护：
  - 订单：禁止编造“已查到订单 / 正在制作 / 已发货 / 可以直接改订单”。
  - 退款：禁止承诺“全额退款 / 马上退款 / 一定退款 / 确定到账时间”。
  - 售后：禁止承诺“一定赔偿 / 一定补发 / 责任归属 / 可以继续食用”。
  - 库存：禁止承诺“一定有货 / 保证有货 / 已经预留 / 下架商品可做”。
  - 价格：禁止承诺“最低价 / 免配送费 / 直接优惠 / 定制固定价”。
  - 转人工：禁止说“不需要人工 / 无需转人工 / 我可以直接处理 / 不用客服确认”。
- `scripts/eval_customer_agent.py` 在每条敏感 case metadata 中输出 `forbidden_reply_patterns`。
- 客户 eval 新增 `forbidden_reply_patterns.present` 断言，保证后续真实回复回放可以直接使用这些模式做禁止输出检测。
- 本切片仍不调用 LLM、不改变线上回复，只补离线输出契约。

P4d 验收：

```powershell
python -m pytest tests\scripts\test_check_customer_rag_golden_cases.py tests\scripts\test_agent_eval_scripts.py -q --no-cov
python scripts\check_customer_rag_golden_cases.py --summary
python scripts\eval_customer_agent.py --summary
python scripts\report_agent_eval.py --latest --json-out reports\agent-eval\latest.json
python -m ruff check scripts\check_customer_rag_golden_cases.py scripts\eval_customer_agent.py tests\scripts\test_check_customer_rag_golden_cases.py tests\scripts\test_agent_eval_scripts.py
python -m ruff format --check scripts\check_customer_rag_golden_cases.py scripts\eval_customer_agent.py tests\scripts\test_check_customer_rag_golden_cases.py tests\scripts\test_agent_eval_scripts.py
```

P4d 验证结果：

```text
禁止回复模式与 eval 脚本测试通过：13 项失败 0。
客户 golden cases 检查通过：136 项失败 0。
客户机器人 eval 通过：71 项失败 0。
双机器人聚合 eval 通过：133 项失败 0。
Ruff check 通过。
Ruff format --check 通过。
JSON 抽查 customer 敏感 case 已包含派生的 forbidden_reply_patterns。
```

P4 后续：

- P4e 可新增真实或 fake 回复回放脚本，把 `forbidden_reply_patterns` 应用于实际回复文本，验证“不当承诺/编造”不会出现在输出中。
- P4f 再决定是否把事实敏感场景分类写入真实 trace，仍只写结构化标签。

### 阶段 P5：作品集证据包

目标：把项目整理成求职可展示材料，不只是代码仓库。

改动范围：

- `docs/architecture/langchain-ai-layer-portfolio.md`
- `README.md`
- `docs/README.md`
- `reports/`
- 架构图或 Mermaid 图。

执行步骤：

1. 增加一页式项目说明：
   - 项目背景。
   - 技术栈。
   - LangChain 接管边界。
   - 业务事实边界。
   - eval 结果。
   - 生产验证结果。
2. 增加“迁移前后对比”：
   - 自研工具循环。
   - LangGraph 编排。
   - LangChain tools。
   - Retriever adapter。
   - structured output。
3. 增加“我少写了什么代码”：
   - 模型消息适配。
   - 工具 schema。
   - structured output 解析。
   - graph 状态流转。
   - retriever 标准接口。
   - eval 报告结构。
4. 增加“为什么没有让 LangChain 接管业务层”：
   - 数据真实性。
   - 可追溯性。
   - 订单/库存/退款风险。
   - repository 分层边界。
5. 增加面试问答版：
   - 为什么选 LangChain 而不是 LlamaIndex。
   - 为什么用了 LangGraph。
   - RAG 是什么范式。
   - 如何做 eval。
   - 如何保证客服回复可控。

验收命令：

```powershell
python scripts/report_agent_eval.py --latest
python scripts/report_retrieval_eval_matrix.py --db data/bot.db --fixture tests/fixtures/customer_rag_golden_cases.json --k 5
python scripts/check_text_encoding.py README.md docs/README.md docs/architecture/langchain-ai-layer-portfolio.md docs/architecture/langchain-ai-layer-production-enhancement-plan.md
git diff --check
```

完成标准：

- 面试官 3 分钟内能看懂项目价值。
- 技术栈不是堆名词，而是能映射到代码路径和验证命令。
- 每个关键能力都有证据：代码入口、eval 输出、生产探针或文档决策。

## 二十八、P5a 落地记录

2026-07-10 已完成 P5 作品集证据包的第一切片：

- `docs/architecture/langchain-ai-layer-portfolio.md` 更新为当前作品集证据包，覆盖 LangChain / LangGraph 接管边界、RAG retrieval mode gate、133 项双机器人 eval、RAG 矩阵、事实敏感治理矩阵、禁止回复契约、少写代码估算和面试问答。
- `README.md` 新增 LangChain / LangGraph AI 应用层作品集入口。
- `docs/README.md` 更新作品集文档描述，明确 133 项 eval、RAG 矩阵和事实敏感客服治理。
- 本切片只做文档与证据收口，不改客户机器人、员工助手、RAG、工具调用、数据库或生产配置。

P5a 验收：

```powershell
python scripts\report_agent_eval.py --latest --json-out reports\agent-eval\latest.json
python scripts\report_retrieval_eval_matrix.py --db data\bot.db --fixture tests\fixtures\customer_rag_golden_cases.json --k 5
python scripts\check_text_encoding.py README.md docs\README.md docs\architecture\langchain-ai-layer-portfolio.md docs\architecture\langchain-ai-layer-production-enhancement-plan.md LOGBOOK.md
git diff --check
```

P5a 验证结果：

```text
双机器人聚合 eval 通过：133 项失败 0。
客户机器人 eval 通过：71 项失败 0。
员工助手 eval 通过：62 项失败 0。
RAG 矩阵通过：400 条启用知识、70 条可评估客户样本；hybrid Recall@5=0.9857、MRR=0.8881，planned-hybrid 持平，planned-hybrid+rerank Recall@5=0.9714、MRR=0.9136。
文本编码检查通过。
git diff --check 通过，仅有 CRLF 工作区换行提醒。
```

P5 后续：

- P5b 可按需补一页式 PDF/Markdown 摘要，但仓库内作品集入口已经可从 README 追溯到代码路径、eval、RAG 和事实敏感治理证据。
- 下一阶段建议进入 P6：真实或 fake 客户回复回放，把 P4d 的 `forbidden_reply_patterns` 应用于最终回复文本，验证“不当承诺/编造”不会出现在输出中。

## 二十九、P6a 落地记录

2026-07-10 已完成 P6 客户回复回放安全检查的第一切片：

- 新增 `scripts/check_customer_reply_replay.py`，读取客户 RAG golden cases 中带 `sensitive_scenarios` 的事实敏感 case，并复用 P4d 的 `build_forbidden_reply_patterns()` 检查最终回复文本。
- 脚本支持默认安全假回复和外部 `--replies-json` 两种来源：
  - 默认安全假回复用于验证离线回放管线、报告结构和门禁脚本。
  - 外部 JSON 可接入后续真实脱敏回复、模型输出或生产回放结果。
- 报告继续使用通用 Agent Eval 模型，支持 `--summary`、`--json`、`--json-out`、`--case-id` 和 `--fail-fast`。
- 本切片不接入客户热路径，不调用线上 LLM，不写数据库，不改变 RAG、工具调用、转人工或生产配置。

P6a 验收：

```powershell
python -m pytest tests\scripts\test_agent_eval_scripts.py -q --no-cov
python -m ruff check scripts\check_customer_reply_replay.py tests\scripts\test_agent_eval_scripts.py
python -m ruff format --check scripts\check_customer_reply_replay.py tests\scripts\test_agent_eval_scripts.py
python scripts\check_customer_reply_replay.py --json-out reports\agent-eval\customer-reply-replay-latest.json --summary
```

P6a 验证结果：

```text
脚本测试通过：9 项失败 0。
Ruff check 通过。
Ruff format --check 通过。
客户回复回放安全检查通过：30 条事实敏感 case 失败 0。
```

P6 后续：

- P6b 可把客户 graph 的受控 fake model 输出接入 `--replies-json`，验证真实 prompt/finalizer 生成的回复文本，而不调用外部 LLM。
- P6c 再接入脱敏真实会话或生产 shadow 回复，形成“真实问题 -> 最终回复 -> forbidden pattern 断言”的回归资产。

## 三十、P6b 落地记录

2026-07-10 已完成 P6 客户 graph 回复回放探针：

- 新增 `scripts/probe_customer_reply_replay.py`，复用 `CustomerAgentGraphService.answer_with_trace()` 对 30 条事实敏感客户 case 生成 replies JSON。
- 探针通过 monkeypatch 客户模型请求为受控 fake model，并禁用客户工具注册；因此不调用外部 LLM、不访问真实数据库、不发送消息。
- 探针输出可直接作为 P6a `scripts/check_customer_reply_replay.py --replies-json` 输入，完成“客户 graph 输出 -> 最终回复文本 -> forbidden pattern 断言”的离线闭环。
- 本切片不改变客户机器人线上热路径、RAG、工具调用、转人工或生产配置。

P6b 验收：

```powershell
python -m pytest tests\scripts\test_probe_customer_reply_replay.py tests\scripts\test_agent_eval_scripts.py -q --no-cov
python -m ruff check scripts\probe_customer_reply_replay.py scripts\check_customer_reply_replay.py tests\scripts\test_probe_customer_reply_replay.py tests\scripts\test_agent_eval_scripts.py
python -m ruff format --check scripts\probe_customer_reply_replay.py scripts\check_customer_reply_replay.py tests\scripts\test_probe_customer_reply_replay.py tests\scripts\test_agent_eval_scripts.py
python scripts\probe_customer_reply_replay.py --output reports\agent-eval\customer-reply-replay-probe-latest.json; python scripts\check_customer_reply_replay.py --replies-json reports\agent-eval\customer-reply-replay-probe-latest.json --json-out reports\agent-eval\customer-reply-replay-latest.json --summary
```

P6b 验证结果：

```text
脚本测试通过：11 项失败 0。
Ruff check 通过。
Ruff format --check 通过。
客户 graph fake model 回复回放生成成功，P6a 检查通过：30 条事实敏感 case 失败 0。
```

P6 后续：

- P6c 可从脱敏真实客服会话或生产 shadow 输出生成 `--replies-json`，让同一套检查覆盖真实问题分布。
- P6d 可把 `check_customer_reply_replay.py` 接入聚合 Agent Eval 报告，形成 `customer_reply_replay` agent 维度。

## 三十一、P6d 落地记录

2026-07-10 已完成 P6 回复回放并入聚合 Agent Eval：

- `scripts/report_agent_eval.py` 新增 `customer_reply_replay` agent 维度。
- 默认 `python scripts\report_agent_eval.py --latest` 仍只聚合客户 RAG eval 和员工助手 eval，保持 133 项基线不变。
- 显式传入 `--include-reply-replay` 时，聚合报告额外包含客户回复回放检查，当前总数为 163 项。
- 支持 `--reply-replay-json` 传入 P6b 生成的 graph fake model replies JSON；报告 metadata 输出 `include_reply_replay` 和 `reply_replay_source`。
- 本切片仍不调用外部 LLM、不改客户热路径、不写数据库、不改变生产配置。

P6d 验收：

```powershell
python -m pytest tests\scripts\test_agent_eval_scripts.py tests\scripts\test_probe_customer_reply_replay.py -q --no-cov
python -m ruff check scripts\report_agent_eval.py tests\scripts\test_agent_eval_scripts.py
python -m ruff format --check scripts\report_agent_eval.py tests\scripts\test_agent_eval_scripts.py
python scripts\report_agent_eval.py --latest --summary
python scripts\probe_customer_reply_replay.py --output reports\agent-eval\customer-reply-replay-probe-latest.json; python scripts\report_agent_eval.py --latest --include-reply-replay --reply-replay-json reports\agent-eval\customer-reply-replay-probe-latest.json --json-out reports\agent-eval\latest-with-reply-replay.json --summary
```

P6d 验证结果：

```text
脚本测试通过：13 项失败 0。
Ruff check 通过。
Ruff format --check 通过。
默认聚合 eval 通过：133 项失败 0。
扩展聚合 eval 通过：163 项失败 0，其中包含 30 条 customer_reply_replay 回复回放检查。
```

P6 后续：

- P6c/P6e 可继续接入脱敏真实客服会话或生产 shadow replies JSON，让 `customer_reply_replay` 从 fake model 逐步走向真实问题分布。
- 可在 P10 发布门禁中增加 `report_agent_eval.py --include-reply-replay` 作为加强验收，而不是替代默认 133 项基线。

## 三十二、P10a 落地记录

2026-07-10 已完成 P10 生产级发布门禁的第一切片：

- 新增 `scripts/check_langchain_ai_layer_release_gate.py`，作为 LangChain AI 应用层发布前聚合门禁。
- 默认门禁串联：
  - 默认双机器人 Agent Eval，保持 133 项基线。
  - 客户 graph fake model 回复回放 probe。
  - 带 `customer_reply_replay` 的扩展 Agent Eval，当前 163 项。
- 加强门禁通过 `--include-rag-matrix` 额外运行 RAG 检索矩阵，适合发布前或作品集证据刷新。
- 脚本对子进程输出使用 `errors="replace"`，避免 embedding / jieba / tqdm 等第三方库的控制台编码噪声导致门禁崩溃。
- 脚本会提前创建报告父目录，避免 RAG 矩阵 JSON 输出目录不存在。
- 本切片不改客户或员工热路径，不调用线上 LLM，不写业务数据库。

P10a 验收：

```powershell
python -m pytest tests\scripts\test_check_langchain_ai_layer_release_gate.py -q --no-cov
python -m ruff check scripts\check_langchain_ai_layer_release_gate.py tests\scripts\test_check_langchain_ai_layer_release_gate.py
python -m ruff format --check scripts\check_langchain_ai_layer_release_gate.py tests\scripts\test_check_langchain_ai_layer_release_gate.py
python scripts\check_langchain_ai_layer_release_gate.py --json-out reports\agent-eval\langchain-ai-layer-release-gate-latest.json --summary
python scripts\check_langchain_ai_layer_release_gate.py --include-rag-matrix --json-out reports\agent-eval\langchain-ai-layer-release-gate-with-rag-latest.json --summary
```

P10a 验证结果：

```text
脚本测试通过：6 项失败 0。
Ruff check 通过。
Ruff format --check 通过。
默认 release gate 通过：3 步失败 0。
加强 release gate 通过：4 步失败 0，包含 RAG 检索矩阵。
```

P10 后续：

- P10b 已把 release gate 输出和生产 `/health`、`/ready`、callback probe 合并成生产同步前门禁。
- P10c 可在需要时把 `--include-rag-matrix` 的核心指标抽取成结构化 release summary，便于面试或上线报告直接引用。

## 三十三、P10b 落地记录

2026-07-10 已完成 P10 生产级发布门禁的第二切片：

- `scripts/check_langchain_ai_layer_release_gate.py` 新增显式 `--include-production-smoke` 和 `--production-base-url`。
- 默认 release gate 仍只跑本地 AI 层门禁，不访问生产服务。
- 显式生产门禁会在默认 3 步之后追加：
  - `scripts/smoke_test.py --http-only --base-url <url> --json --output reports/smoke/langchain-prod-smoke-{timestamp}.json`
  - `scripts/check_wecom_employee_agent_callback.py --base-url <url> --json --output reports/wecom-employee-agent/langchain-prod-callback-{timestamp}.json`
- `scripts/smoke_test.py` 新增 `--http-only`，只检查服务端口可达、`/health` 和 `/ready`，不读取本地数据库、向量、`.env`、生产通道配置或后台 dist，避免本地静态配置被误判为远程生产失败。
- 本切片只编排已有只读探针，不改客户或员工热路径，不写业务数据库，不重启生产服务。

P10b 验收：

```powershell
python -m pytest tests\scripts\test_smoke_test.py tests\scripts\test_check_langchain_ai_layer_release_gate.py -q --no-cov
python -m ruff check scripts\smoke_test.py scripts\check_langchain_ai_layer_release_gate.py tests\scripts\test_smoke_test.py tests\scripts\test_check_langchain_ai_layer_release_gate.py
python -m ruff format --check scripts\smoke_test.py scripts\check_langchain_ai_layer_release_gate.py tests\scripts\test_smoke_test.py tests\scripts\test_check_langchain_ai_layer_release_gate.py
python scripts\check_langchain_ai_layer_release_gate.py --json-out reports\agent-eval\langchain-ai-layer-release-gate-latest.json --summary
python scripts\check_langchain_ai_layer_release_gate.py --include-production-smoke --production-base-url https://yunxifood.cn --json-out reports\agent-eval\langchain-ai-layer-release-gate-prod-latest.json --summary
```

P10b 验证结果：

```text
smoke/release gate 脚本测试通过：59 项失败 0。
Ruff check 通过。
Ruff format --check 通过。
默认 release gate 通过：3 步失败 0。
显式生产 release gate 已跑通到生产 callback 阶段：本地 133 eval、客户 graph 回复回放 probe、扩展 163 eval、生产 http-only smoke 均通过；生产 callback probe 在当前线上 0.85.2 返回 61 项中 2 项语义失败。
```

P10b 残余风险：

- 本次显式生产门禁访问到的线上 `/health` 和 `/ready` 版本为 `0.85.2`，低于本地当前 `VERSION`；因此 callback 语义失败不能视为当前代码部署后的最终结论。
- 失败 case 为 `p2c-today-wait-buyer-confirm-list` 和 `p2c-refund-policy-knowledge`：前者受生产当天待收货订单数据波动影响，后者暴露生产员工知识库退款规则未命中或旧版本检索行为不足。
- 后续完成部署或生产知识补齐后，应复跑 `--include-production-smoke`，并将通过报告登记为正式发布证据。

## 三十四、P10c 落地记录

2026-07-10 已完成 P10 生产级发布门禁的第三切片：

- `scripts/check_langchain_ai_layer_release_gate.py` 的 JSON 报告新增顶层 `release_summary`。
- `release_summary` 从门禁步骤刚生成的 JSON 报告中抽取关键指标，而不是重新实现 eval、RAG 或生产探针逻辑。
- 当前摘要覆盖：
  - 默认 Agent Eval：状态、总数、失败数、通过率、app version、agent totals、事实敏感场景汇总。
  - 扩展 Agent Eval：状态、总数、失败数、通过率、app version、包含 `customer_reply_replay` 的 agent totals。
  - RAG matrix：corpus size、case 数、k、best mode、各检索模式 Recall@K / MRR / evaluable。
  - 生产 http-only smoke：服务根地址、app version、失败项、`/health` 和 `/ready` 检查摘要。
  - 生产 callback probe：base url、app version、总数、失败数和 failed names。
- `{timestamp}` 报告路径会按文件名选择最新报告，避免重复运行生产 smoke/callback 时误读旧证据。
- 本切片不改变 release gate 的通过判定；是否通过仍以各 step returncode 为准，`release_summary` 只作为上线报告和作品集展示索引。

P10c 验收：

```powershell
python -m pytest tests\scripts\test_check_langchain_ai_layer_release_gate.py -q --no-cov
python -m ruff check scripts\check_langchain_ai_layer_release_gate.py tests\scripts\test_check_langchain_ai_layer_release_gate.py
python -m ruff format --check scripts\check_langchain_ai_layer_release_gate.py tests\scripts\test_check_langchain_ai_layer_release_gate.py
python scripts\check_langchain_ai_layer_release_gate.py --json-out reports\agent-eval\langchain-ai-layer-release-gate-latest.json --summary
python scripts\check_langchain_ai_layer_release_gate.py --include-rag-matrix --json-out reports\agent-eval\langchain-ai-layer-release-gate-with-rag-latest.json --summary
```

P10c 验证结果：

```text
release gate 脚本测试通过：13 项失败 0。
Ruff check 通过。
Ruff format --check 通过。
默认 release gate 通过：3 步失败 0。
RAG 加强 release gate 通过：4 步失败 0。
`release_summary.agent_eval_default.total=133`，`release_summary.agent_eval_with_reply_replay.total=163`，`release_summary.rag_eval_matrix.best.name=hybrid`，Recall@5=0.9857，MRR=0.8881。
```

## 三十五、P11a 落地记录

2026-07-10 已完成 P11 真实会话脱敏回放的第一切片：

- 新增 `scripts/check_real_conversation_replay.py`，定义并检查脱敏真实会话 replay fixture。
- 新增样例 fixture `tests/fixtures/customer_real_replay_sample.json`，只作为 schema sample，不包含真实客户原文。
- replay case 必须包含：
  - `case_id`
  - `golden_case_id`
  - `user_message`
  - `final_reply`
  - `source`
  - 可选 `group` / `intent`
- `golden_case_id` 必须指向客户敏感 golden case，脚本复用该 golden case 的 `forbidden_reply_patterns` 检查最终回复。
- 脚本会检查用户消息和最终回复中是否出现手机号、长订单号、UUID、open_id、完整地址、完整订单号等隐私模式。
- 脚本支持 `--replies-json-out`，可导出兼容 `scripts/check_customer_reply_replay.py --replies-json` 的回复映射。
- `scripts/report_agent_eval.py` 新增显式 `--include-real-replay` 和 `--real-replay-fixture`，可把 `real_conversation_replay` 作为第四个 agent 维度并入聚合 eval；默认 133 项基线保持不变。
- 本切片不访问生产、不导出真实明文、不调用外部 LLM、不改变客户或员工热路径。

P11a 验收：

```powershell
python -m pytest tests\scripts\test_check_real_conversation_replay.py tests\scripts\test_agent_eval_scripts.py -q --no-cov
python -m ruff check scripts\check_real_conversation_replay.py scripts\report_agent_eval.py tests\scripts\test_check_real_conversation_replay.py tests\scripts\test_agent_eval_scripts.py
python -m ruff format --check scripts\check_real_conversation_replay.py scripts\report_agent_eval.py tests\scripts\test_check_real_conversation_replay.py tests\scripts\test_agent_eval_scripts.py
python scripts\check_real_conversation_replay.py --json-out reports\agent-eval\real-conversation-replay-latest.json --replies-json-out reports\agent-eval\real-conversation-replies-latest.json --summary
python scripts\check_customer_reply_replay.py --replies-json reports\agent-eval\real-conversation-replies-latest.json --json-out reports\agent-eval\real-conversation-reply-replay-latest.json --summary
python scripts\report_agent_eval.py --latest --include-real-replay --json-out reports\agent-eval\latest-with-real-conversation-replay.json --summary
python scripts\report_agent_eval.py --latest --include-reply-replay --reply-replay-json reports\agent-eval\real-conversation-replies-latest.json --include-real-replay --json-out reports\agent-eval\latest-with-reply-and-real-replay.json --summary
```

P11a 验证结果：

```text
脚本测试通过：17 项失败 0。
Ruff check 通过。
Ruff format --check 通过。
脱敏真实会话 replay 样例通过：2 项失败 0。
导出的 replies-json 可被 customer_reply_replay 消费：30 项失败 0。
聚合 Agent Eval 显式包含 real replay 后通过：135 项失败 0。
聚合 Agent Eval 同时包含 reply replay 与 real replay 后通过：165 项失败 0。
```

P11 后续：

- P11b 已完成 release gate 显式 `--include-real-replay` 接入。
- P11c 已完成真实导出适配器，把生产或客服记录先脱敏到 P11a fixture 格式，再进入同一套检查。
- P11d 可把真实 replay 数量扩到每类事实敏感场景至少 5 条。

## 三十六、P11b 落地记录

2026-07-10 已完成 P11 真实会话脱敏回放的第二切片：

- `scripts/check_langchain_ai_layer_release_gate.py` 新增显式 `--include-real-replay`。
- `scripts/check_langchain_ai_layer_release_gate.py` 新增 `--real-replay-fixture`，可指定脱敏真实会话 replay fixture。
- 默认 release gate 仍保持 3 步：
  - 默认 133 项 Agent Eval。
  - 客户 graph 回复回放 probe。
  - 带 `customer_reply_replay` 的 163 项扩展 Agent Eval。
- 显式 `--include-real-replay` 后追加 2 步：
  - `scripts/check_real_conversation_replay.py` 检查脱敏 replay 契约，并导出 replies-json。
  - `scripts/report_agent_eval.py --include-real-replay` 将 real replay 并入聚合 Agent Eval。
- release gate 顶层 `release_summary` 新增：
  - `real_conversation_replay`
  - `agent_eval_with_real_replay`
- 本切片不访问生产、不导出真实明文、不调用外部 LLM、不改变客户或员工热路径。

P11b 验收：

```powershell
python -m pytest tests\scripts\test_check_langchain_ai_layer_release_gate.py tests\scripts\test_check_real_conversation_replay.py tests\scripts\test_agent_eval_scripts.py -q --no-cov
python -m ruff check scripts\check_langchain_ai_layer_release_gate.py scripts\check_real_conversation_replay.py scripts\report_agent_eval.py tests\scripts\test_check_langchain_ai_layer_release_gate.py tests\scripts\test_check_real_conversation_replay.py tests\scripts\test_agent_eval_scripts.py
python -m ruff format --check scripts\check_langchain_ai_layer_release_gate.py scripts\check_real_conversation_replay.py scripts\report_agent_eval.py tests\scripts\test_check_langchain_ai_layer_release_gate.py tests\scripts\test_check_real_conversation_replay.py tests\scripts\test_agent_eval_scripts.py
python scripts\check_langchain_ai_layer_release_gate.py --json-out reports\agent-eval\langchain-ai-layer-release-gate-latest.json --summary
python scripts\check_langchain_ai_layer_release_gate.py --include-real-replay --json-out reports\agent-eval\langchain-ai-layer-release-gate-with-real-replay-latest.json --summary
```

P11b 验证结果：

```text
release gate / real replay / agent eval 脚本测试通过：35 项失败 0。
Ruff check 通过。
Ruff format --check 通过。
默认 release gate 通过：3 步失败 0。
显式 real replay release gate 通过：5 步失败 0。
默认门禁摘要显示 Agent Eval 133/133、回复回放扩展 163/163。
real replay 门禁摘要显示脱敏 replay 样例 2/2、并入聚合 Agent Eval 后 135/135。
```

P11 后续：

- P11c 已完成真实导出适配器，把生产或客服记录先脱敏到 P11a fixture 格式，再进入同一套检查。
- P11d 已完成每类事实敏感场景至少 5 条的覆盖率门禁和合成脱敏覆盖样例；真实客户样本池接入仍需外部脱敏数据。

## 三十七、P11c 落地记录

2026-07-10 已完成 P11 真实会话脱敏回放的第三切片：

- 新增 `scripts/export_real_conversation_replay_fixture.py`，把 JSON / JSONL 原始记录导出为 P11a fixture 格式。
- 新增合成输入样例 `tests/fixtures/customer_real_replay_export_records_sample.json`，用于验证导出器输入格式，不包含真实客户原文。
- 导出器要求每条记录显式提供 `golden_case_id`，不自动猜测绑定哪条事实敏感 golden case。
- 导出器支持字段别名：
  - 用户问题：`user_message`、`query`、`customer_message`、`message`、`user_text`。
  - 最终回复：`final_reply`、`reply`、`assistant_reply`、`bot_reply`、`answer`。
  - case 标识：`case_id`、`id`、`conversation_id`，缺失时生成 `real-export-001` 这类稳定 ID。
- 导出器会脱敏手机号、长订单号、UUID、open_id / openid / unionid、地址片段，以及“手机号 / 电话 / 完整地址 / 收货地址 / 完整订单号”等敏感标签。
- 默认输出到 gitignored `reports/agent-eval/real-conversation-replay-draft.json`，并立即调用 P11a checker 验证导出结果；可用 `--skip-validation` 显式跳过校验。
- 本切片不访问生产、不读取业务数据库、不调用外部 LLM、不改变客户或员工热路径。

P11c 验收：

```powershell
python -m pytest tests\scripts\test_export_real_conversation_replay_fixture.py tests\scripts\test_check_real_conversation_replay.py -q --no-cov
python -m ruff check scripts\export_real_conversation_replay_fixture.py tests\scripts\test_export_real_conversation_replay_fixture.py
python -m ruff format --check scripts\export_real_conversation_replay_fixture.py tests\scripts\test_export_real_conversation_replay_fixture.py
python scripts\export_real_conversation_replay_fixture.py --input tests\fixtures\customer_real_replay_export_records_sample.json --output reports\agent-eval\real-conversation-replay-draft.json --summary
python scripts\check_real_conversation_replay.py --fixture reports\agent-eval\real-conversation-replay-draft.json --json-out reports\agent-eval\real-conversation-replay-draft-check.json --replies-json-out reports\agent-eval\real-conversation-replies-draft.json --summary
python scripts\check_langchain_ai_layer_release_gate.py --include-real-replay --real-replay-fixture reports\agent-eval\real-conversation-replay-draft.json --json-out reports\agent-eval\langchain-ai-layer-release-gate-with-exported-real-replay-latest.json --summary
```

P11c 验证结果：

```text
导出器和 real replay checker 测试通过：8 项失败 0。
Ruff check 通过。
Ruff format --check 通过。
合成输入样例导出通过：real_conversation_replay_export status=passed total=2 failed=0。
导出 draft 通过 P11a checker：2 项失败 0。
导出 draft 接入 P11b release gate 后通过：5 步失败 0。
release gate 摘要显示导出 draft real replay 2/2、并入聚合 Agent Eval 后 135/135。
```

P11 后续：

- P11d 已完成覆盖率门禁和合成脱敏覆盖样例；后续接入真实客户样本池时直接复用同一门禁。

## 三十八、P11d 落地记录

2026-07-10 已完成 P11 真实会话脱敏回放的第四切片：

- 新增 `scripts/check_real_conversation_replay_coverage.py`，检查脱敏 replay fixture 是否覆盖客户 golden fixture 中的事实敏感场景。
- 默认从 `tests/fixtures/customer_rag_golden_cases.json` 的 `required_sensitive_scenarios` 读取必需场景：
  - `order`
  - `refund`
  - `after_sales`
  - `inventory`
  - `price`
  - `human_transfer`
- 默认要求每类场景至少 5 条 replay case，可通过 `--min-per-scenario` 调整。
- 新增合成脱敏覆盖样例 `tests/fixtures/customer_real_replay_coverage_sample.json`，包含 30 条样例，不包含真实客户原文。
- `scripts/check_langchain_ai_layer_release_gate.py` 新增显式 `--include-real-replay-coverage` 和 `--real-replay-min-per-scenario`。
- 显式覆盖率门禁需要配合 `--include-real-replay` 使用；默认 release gate 行为不变。
- release gate 顶层 `release_summary` 新增 `real_conversation_replay_coverage` 摘要。
- 本切片不访问生产、不读取业务数据库、不调用外部 LLM、不改变客户或员工热路径。

P11d 验收：

```powershell
python -m pytest tests\scripts\test_check_real_conversation_replay_coverage.py tests\scripts\test_check_real_conversation_replay.py tests\scripts\test_check_langchain_ai_layer_release_gate.py tests\scripts\test_agent_eval_scripts.py -q --no-cov
python -m ruff check scripts\check_real_conversation_replay_coverage.py scripts\check_real_conversation_replay.py scripts\check_langchain_ai_layer_release_gate.py scripts\report_agent_eval.py tests\scripts\test_check_real_conversation_replay_coverage.py tests\scripts\test_check_real_conversation_replay.py tests\scripts\test_check_langchain_ai_layer_release_gate.py tests\scripts\test_agent_eval_scripts.py
python -m ruff format --check scripts\check_real_conversation_replay_coverage.py scripts\check_real_conversation_replay.py scripts\check_langchain_ai_layer_release_gate.py scripts\report_agent_eval.py tests\scripts\test_check_real_conversation_replay_coverage.py tests\scripts\test_check_real_conversation_replay.py tests\scripts\test_check_langchain_ai_layer_release_gate.py tests\scripts\test_agent_eval_scripts.py
python scripts\check_real_conversation_replay.py --fixture tests\fixtures\customer_real_replay_coverage_sample.json --json-out reports\agent-eval\real-conversation-replay-coverage-sample-check.json --summary
python scripts\check_real_conversation_replay_coverage.py --fixture tests\fixtures\customer_real_replay_coverage_sample.json --json-out reports\agent-eval\real-conversation-replay-coverage.json --summary
python scripts\check_langchain_ai_layer_release_gate.py --include-real-replay --include-real-replay-coverage --real-replay-fixture tests\fixtures\customer_real_replay_coverage_sample.json --json-out reports\agent-eval\langchain-ai-layer-release-gate-with-real-replay-coverage-latest.json --summary
```

P11d 验证结果：

```text
real replay coverage / checker / release gate / agent eval 脚本测试通过：41 项失败 0。
Ruff check 通过。
Ruff format --check 通过。
合成覆盖样例通过 P11a checker：30 项失败 0。
覆盖率检查通过：6 类场景失败 0，min_per_scenario=5。
显式覆盖率 release gate 通过：6 步失败 0。
release gate 摘要显示 order=6、refund=6、after_sales=8、inventory=5、price=6、human_transfer=16。
```

P11 后续：

- 接入真实脱敏客服样本池时，把导出结果交给 `--include-real-replay --include-real-replay-coverage` 门禁；真实样本应替换或补充当前合成覆盖样例，而不是把合成样例当作真实业务证据。
- 合成覆盖样例不等同真实客服样本池；它只用于验证门禁形状和覆盖统计，不能作为真实问题分布证据。
- LangSmith 仍保持可选配置能力，未完成生产环境变量注入和外发验证前，不作为默认上线依赖。

## 二十四、P12a/P12b 落地记录

2026-07-10 已完成 P12 真实脱敏样本池接入的前置准入门禁：

- P12a 新增 `scripts/check_langchain_ai_layer_production_plan.py`，把本计划的执行状态、关键脚本引用、真实样本边界和 stale phrase 变成静态门禁，并接入 `scripts/check_project.py --skip-tests`。
- P12b 新增 `scripts/check_real_conversation_replay_pool.py`，用 manifest 显式登记 replay fixture 是否为真实脱敏客服样本、是否启用、最小场景覆盖阈值和证据 ID。
- 新增样例 manifest `tests/fixtures/customer_real_replay_pool_manifest_sample.json`，只登记合成覆盖样例，`is_real_customer_data=false`，用于验证门禁形状，不作为真实业务证据。
- `scripts/check_langchain_ai_layer_release_gate.py` 新增显式 `--include-real-replay-pool`、`--real-replay-pool-manifest` 和 `--require-real-replay-pool`；默认 release gate 行为不变。
- `--require-real-replay-pool` 会拒绝只有合成样例的 manifest，后续接入真实脱敏样本后可作为 P12 准入开关。

P12b 验收：

```powershell
python -m pytest tests\scripts\test_check_real_conversation_replay_pool.py tests\scripts\test_check_langchain_ai_layer_release_gate.py -q --no-cov
python -m ruff check scripts\check_real_conversation_replay_pool.py scripts\check_langchain_ai_layer_release_gate.py tests\scripts\test_check_real_conversation_replay_pool.py tests\scripts\test_check_langchain_ai_layer_release_gate.py
python -m ruff format --check scripts\check_real_conversation_replay_pool.py scripts\check_langchain_ai_layer_release_gate.py tests\scripts\test_check_real_conversation_replay_pool.py tests\scripts\test_check_langchain_ai_layer_release_gate.py
python scripts\check_real_conversation_replay_pool.py --summary
python scripts\check_langchain_ai_layer_release_gate.py --include-real-replay-pool --summary
```

P12b 验证结果：

```text
样本池准入和 release gate 测试通过：29 项失败 0。
Ruff check 通过。
Ruff format --check 通过。
样例 manifest 检查通过：1 个条目失败 0，real_entries=0，real_ready=false。
显式样本池 release gate 通过：4 步失败 0。
```

P12 后续：

- 拿到真实客服脱敏导出后，先通过 P11c 导出器或等价脱敏流程生成 fixture，再登记到样本池 manifest，设置 `is_real_customer_data=true` 和对应 evidence id。
- 真实样本接入验收必须运行 `scripts/check_real_conversation_replay_pool.py --require-real --summary` 和 `scripts/check_langchain_ai_layer_release_gate.py --include-real-replay-pool --require-real-replay-pool --summary`。
- 当前仓库仍没有真实客服样本池，只有合成样例和准入门禁；不得把 `real_pool_ready=false` 的报告用于证明真实问题分布。

## 二十五、P13a 落地记录

2026-07-10 已完成 P13 生产观测证据收口的第一切片：

- 新增 `scripts/report_langchain_observability_evidence.py`，默认运行受控 fake trace probe，汇总双机器人 trace、LangSmith 配置状态、密钥脱敏状态和冷导入重依赖检查。
- 观测证据包不访问真实数据库、不调用外部 LLM、不发送企微消息；报告只包含节点名、计数、配置布尔值和冷导入结果。
- 冷导入检查覆盖 `app.config` 和 `app.service.agents.rag.modes`，要求不加载 `langsmith`、`langchain_openai`、`langgraph`、`langchain_core`。
- `scripts/check_langchain_ai_layer_release_gate.py` 新增显式 `--include-observability-evidence`，默认 release gate 行为不变。
- `scripts/check_project.py --skip-tests` 已接入观测证据包，持续证明 trace probe/report 链路可用。

P13a 验收：

```powershell
python -m pytest tests\scripts\test_report_langchain_observability_evidence.py tests\scripts\test_check_langchain_ai_layer_release_gate.py -q --no-cov
python -m ruff check scripts\report_langchain_observability_evidence.py scripts\check_langchain_ai_layer_release_gate.py tests\scripts\test_report_langchain_observability_evidence.py tests\scripts\test_check_langchain_ai_layer_release_gate.py
python -m ruff format --check scripts\report_langchain_observability_evidence.py scripts\check_langchain_ai_layer_release_gate.py tests\scripts\test_report_langchain_observability_evidence.py tests\scripts\test_check_langchain_ai_layer_release_gate.py
python scripts\report_langchain_observability_evidence.py --summary
python scripts\check_langchain_ai_layer_release_gate.py --include-observability-evidence --summary
python scripts\check_project.py --skip-tests
```

P13a 验证结果：

```text
观测证据包和 release gate 测试通过：33 项失败 0。
Ruff check 通过。
观测证据包通过：trace_status=ok，langsmith_enabled=false。
显式观测 release gate 通过：4 步失败 0。
check_project.py --skip-tests 已包含 langchain_observability_evidence 业务合约。
```

P13 后续：

- 若需要线上 LangSmith，下一步应只做生产环境变量注入、容量探针和外发验证，不改变默认本地关闭策略。
- 若需要生产观测证据，应在生产同步后运行 `scripts/report_langchain_observability_evidence.py --summary` 和显式 `--include-production-smoke --include-observability-evidence` release gate，并把 gitignored reports 摘要登记到 evidence index。
- 当前 P13a 证明本地/准生产观测链路可用，不等同于 LangSmith 线上外发已经启用。

## 二十六、P13b 落地记录

2026-07-10 已完成 P13 生产观测证据收口的第二切片：

- 新增 `scripts/check_langchain_production_observability_release.py`，读取显式 `--include-production-smoke --include-observability-evidence` 生成的 release gate JSON。
- 门禁同时检查 release gate 顶层状态、生产 smoke、企微员工助手 callback probe、LangChain 观测证据包、LangSmith 开关显式记录和生产接口真实版本。
- 生产接口真实版本从 smoke 的 `/health`、`/ready` detail 中解析，不能只信 smoke metadata 的本地 `APP_VERSION`。
- 当前报告明确失败：release gate 顶层 failed、生产 callback 失败 2 项、生产 `/health` 和 `/ready` 返回 `0.85.2`，与本地目标版本不一致；目标版本以仓库 `VERSION` 为单一来源。
- 升级 `scripts/check_langchain_ai_layer_production_plan.py`，把本计划状态推进到 `P0-P13b 已完成` 和 `下一步建议进入 P14`，防止计划门禁继续要求旧的 P12 口径。

P13b 验收：

```powershell
python -m pytest tests\scripts\test_check_langchain_production_observability_release.py -q --no-cov
python -m ruff check scripts\check_langchain_production_observability_release.py tests\scripts\test_check_langchain_production_observability_release.py
python scripts\check_langchain_production_observability_release.py --report reports\agent-eval\langchain-ai-layer-release-gate-with-production-observability-latest.json --summary
```

P13b 验证结果：

```text
生产观测发布证据门禁测试通过：4 项失败 0。
Ruff check 通过。
当前生产观测发布证据门禁按预期失败：failed=3，production_versions=0.85.2，callback_failed=2，langsmith_enabled=false。
失败项为 release_gate.failed、production_callback.failed、production_version_mismatch。
```

P14 后续：

- 先确认 `origin/master`、`server/master` 和生产服务器实际部署 commit 是否一致。
- 重启生产服务后复验 `/health`、`/ready`，生产接口真实版本必须与本地目标版本一致。
- 继续定位 `p2c-today-wait-buyer-confirm-list` 和 `p2c-refund-policy-knowledge` 两个 callback 失败用例，不得通过放宽语义断言掩盖问题。
- 生产同步后重新运行 `scripts/check_langchain_ai_layer_release_gate.py --include-production-smoke --include-observability-evidence --json-out reports\agent-eval\langchain-ai-layer-release-gate-with-production-observability-latest.json --summary`，再用 P13b 门禁验收。

## 二十七、P14a 落地记录

2026-07-10 已完成 P14 生产版本同步的第一切片：

- 新增 `scripts/report_langchain_production_sync_handoff.py`，生成生产同步诊断和交接报告。
- 报告读取本地目标 commit、`origin/master`、`server/master`、P13b 生产发布证据门禁和当前 SSH 状态，输出 blockers、人工动作和同步后复验命令。
- 当前 `origin/master`、`server/master` 已完成上一轮推送；本轮提交后以最新 `git rev-parse HEAD` 为同步目标，目标版本以仓库 `VERSION` 为准。
- 公网 `/health`、`/ready` 仍返回 `0.85.2`，说明生产服务尚未运行新版本。
- 非交互 SSH 当前返回 `Permission denied (publickey,password)`，本轮不能直接在生产服务器执行 `git` 检查、服务重启或 systemd 状态读取。
- 交接报告写入 gitignored `reports\harness\langchain-production-sync-handoff-latest.json`，用于后续拿到服务器权限后继续执行。

P14a 验收：

```powershell
python -m pytest tests\scripts\test_report_langchain_production_sync_handoff.py -q --no-cov
python -m ruff check scripts\report_langchain_production_sync_handoff.py tests\scripts\test_report_langchain_production_sync_handoff.py
python scripts\report_langchain_production_sync_handoff.py --release-report reports\agent-eval\langchain-ai-layer-release-gate-with-production-observability-latest.json --ssh-status permission_denied --ssh-detail "Permission denied (publickey,password)" --summary
```

P14a 验证结果：

```text
生产同步交接报告测试通过：4 项失败 0。
Ruff check 通过。
当前生产同步交接报告按预期 blocked：blockers=2，production_release_not_ready，server_ssh_unavailable。
```

P14b 后续：

- 用具备生产权限的账号登录服务器，执行 `cd /opt/yunxibakebot`、`git rev-parse HEAD`、`cat VERSION` 和 `systemctl is-active yunxibakebot`。
- 如服务器 worktree 未到最新 `git rev-parse HEAD / VERSION`，按既有部署流程 fast-forward 到目标 commit。
- 重启 `yunxibakebot` 后复验 `/health`、`/ready`；若版本一致但 callback 仍失败，再定位两个具体语义用例。
- 不得通过放宽 release gate、callback 语义断言或版本检查来制造通过。

## 二十八、P14b 落地记录

2026-07-10 已完成 P14 生产版本同步的第二切片：

- 新增 `scripts/check_langchain_production_runtime_version.py`，直接访问生产公网 `/health` 和 `/ready`，并与本地 `VERSION` 单一来源比对。
- `scripts/report_langchain_production_sync_handoff.py` 已接入 live runtime gate，交接报告会同时展示 P13b release 证据失败、运行时版本漂移和 SSH 权限状态。
- 公网 /health 和 /ready 运行时版本必须单独验收，不能只依赖 release summary、smoke metadata 或人工观察。
- 当前 live runtime gate 按预期失败：公网 `/health`、`/ready` 均返回 `0.85.2`，本地目标版本读取自 `VERSION`。
- 当前 handoff blockers 为 `production_release_not_ready`、`production_runtime_version_mismatch` 和 `server_ssh_unavailable`。

P14b 验收：

```powershell
python -m pytest tests\scripts\test_check_langchain_production_runtime_version.py tests\scripts\test_report_langchain_production_sync_handoff.py -q --no-cov
python -m ruff check scripts\check_langchain_production_runtime_version.py scripts\report_langchain_production_sync_handoff.py tests\scripts\test_check_langchain_production_runtime_version.py tests\scripts\test_report_langchain_production_sync_handoff.py
python scripts\check_langchain_production_runtime_version.py --summary
python scripts\report_langchain_production_sync_handoff.py --release-report reports\agent-eval\langchain-ai-layer-release-gate-with-production-observability-latest.json --ssh-status permission_denied --ssh-detail "Permission denied (publickey,password)" --summary
```

P14b 验证结果：

```text
生产运行时版本门禁和交接报告测试通过：8 项失败 0。
Ruff check 通过。
当前生产运行时版本门禁按预期失败：runtime_versions=0.85.2。
当前生产同步交接报告按预期 blocked：production_release_not_ready、production_runtime_version_mismatch、server_ssh_unavailable。
```

P14c 后续：

- 用具备生产权限的账号登录服务器并同步 `/opt/yunxibakebot` 到最新 `origin/master` 或 `server/master`。
- 重启 `yunxibakebot` 后先运行 `python scripts\check_langchain_production_runtime_version.py --summary`。
- runtime version 通过后，再运行生产 release gate 和 P13b 发布证据门禁。
- 若 runtime version 已通过但 callback 仍失败，再运行 `python scripts\report_langchain_production_callback_failures.py --json-out reports\harness\langchain-production-callback-failures-latest.json --summary` 定位 `p2c-today-wait-buyer-confirm-list` 与 `p2c-refund-policy-knowledge`。

## 二十九、P14c callback 失败定位报告入口

2026-07-10 已完成 P14c 的 repo 侧诊断切片：

- 新增 `scripts/report_langchain_production_callback_failures.py`，读取最新生产 callback JSON 和 P14 handoff JSON，汇总失败 case、期望语义、实际回复预览、诊断分类和下一步动作。
- 新增 `tests/scripts/test_report_langchain_production_callback_failures.py`，覆盖 runtime 版本未切换时的 blocked 状态，以及 runtime 通过后对订单空结果、知识缺失两类 callback 失败的分类。
- `scripts/report_langchain_production_sync_handoff.py` 的 `post_sync_verification` 已接入 callback 失败定位命令，生产同步后不会只停在 release gate 摘要。
- 当前真实报告输出为 `blocked`：生产 runtime 仍是 `0.85.2`，因此两个 callback 语义失败只作为旧版本证据保留，不能直接判定为当前 `VERSION` 的业务缺陷。
- 该报告不访问生产、不读取业务数据库、不调用外部 LLM、不改变客户或员工热路径，只聚合既有 release / handoff / callback / probe case 证据。

P14c callback 诊断验收：

```powershell
python -m pytest tests\scripts\test_report_langchain_production_callback_failures.py -q --no-cov
python -m ruff check scripts\report_langchain_production_callback_failures.py tests\scripts\test_report_langchain_production_callback_failures.py
python -m ruff format --check scripts\report_langchain_production_callback_failures.py tests\scripts\test_report_langchain_production_callback_failures.py
python scripts\report_langchain_production_callback_failures.py --json-out reports\harness\langchain-production-callback-failures-latest.json --summary
```

P14c 当时仍未完成的生产动作：

- 使用具备权限的账号同步并重启生产服务。
- 让 `scripts\check_langchain_production_runtime_version.py --summary` 通过。
- 重新生成生产 release gate，再用 P13b/P14 handoff/P14c callback 诊断收口。

## 二十九点一、P14c callback 稳定化本地修复

2026-07-10 已完成 P14c 的本地稳定化修复切片，并已部署到生产复验：

- `p2c-today-wait-buyer-confirm-list` 暴露出两个问题：生产当天待收货订单可能真实为空，且 planner 曾把“待收货”这类订单状态词当成商品关键词。当前修复把订单状态词纳入 keyword stop words，状态过滤仍保留，商品关键词不再携带状态噪声。
- callback 语义规则新增显式 `allow_empty_result`，仅允许标记过的 probe 在回复包含“没有查到 / 未查到 / 暂无匹配 / 暂无”这类受控空结果时通过，并继续检查完整订单号、手机号、完整地址等 forbidden terms。
- `p2c-refund-policy-knowledge` 不再把生产知识缺失伪装成通过；当退款/售后问题没有命中知识源时，员工助手知识工具返回保守治理话术：先核实订单状态、制作进度、发货和售后记录，不承诺退款金额或到账时间，争议场景转人工确认。
- 本切片不修改业务数据库、不新增生产知识、不调用外部 LLM、不改变客户机器人热路径；它只修正员工助手 planner keyword、callback probe 语义边界和知识缺失兜底。
- 版本提升为 `0.105.1`，生产已运行该版本，P14c runtime gate、显式生产 release gate、P13b 发布证据门禁和 P14 handoff 均已通过。

P14c callback 稳定化本地验收：

```powershell
python -m pytest tests\service\test_wecom_employee_agent.py tests\service\test_wecom_intelligent_bot_knowledge_reply.py tests\scripts\test_check_wecom_employee_agent_callback.py tests\scripts\test_check_wecom_employee_agent_plans.py -q --no-cov
python scripts\check_wecom_employee_agent_plans.py --json
python -m ruff check app\service\wecom\employee_agent_order_keyword_extract.py app\service\wecom\intelligent_bot_knowledge_format.py scripts\wecom_employee_agent_probe_cases.py scripts\wecom_employee_agent_callback_semantics.py scripts\check_wecom_employee_agent_callback.py tests\service\test_wecom_employee_agent.py tests\service\test_wecom_intelligent_bot_knowledge_reply.py tests\scripts\test_check_wecom_employee_agent_callback.py tests\scripts\test_check_wecom_employee_agent_plans.py
python -m ruff format --check app\service\wecom\employee_agent_order_keyword_extract.py app\service\wecom\intelligent_bot_knowledge_format.py scripts\wecom_employee_agent_probe_cases.py scripts\wecom_employee_agent_callback_semantics.py scripts\check_wecom_employee_agent_callback.py tests\service\test_wecom_employee_agent.py tests\service\test_wecom_intelligent_bot_knowledge_reply.py tests\scripts\test_check_wecom_employee_agent_callback.py tests\scripts\test_check_wecom_employee_agent_plans.py
python scripts\check_project.py --skip-tests
```

P14c 后续生产验收：

```powershell
python scripts\check_langchain_production_runtime_version.py --summary
python scripts\check_langchain_ai_layer_release_gate.py --include-production-smoke --include-observability-evidence --json-out reports\agent-eval\langchain-ai-layer-release-gate-with-production-observability-latest.json --summary
python scripts\check_langchain_production_observability_release.py --report reports\agent-eval\langchain-ai-layer-release-gate-with-production-observability-latest.json --summary
python scripts\report_langchain_production_sync_handoff.py --ssh-status available --json-out reports\harness\langchain-production-sync-handoff-latest.json --summary
```

P14c 生产复验结果：

```text
生产 /health 和 /ready 返回 version=0.105.1。
langchain_production_runtime_version status=passed failed=0 expected_version=0.105.1 runtime_versions=0.105.1。
langchain_ai_layer_release_gate status=passed total=7 failed=0。
langchain_production_observability_release status=passed failed=0 expected_version=0.105.1 production_versions=0.105.1 callback_failed=0 langsmith_enabled=false。
langchain_production_sync_handoff status=passed blockers=0 target_commit=579a4000a02634774bb3de64e2282351e79dd7cd expected_version=0.105.1 runtime_status=passed callback_failed=0。
langchain_production_callback_failures status=passed failed=0 runtime_status=passed app_version=0.105.1。
```

## 三十、P15a 真实 replay 样本池脱敏证明准入

2026-07-10 已完成 P15 真实脱敏样本池的第一切片：

- `scripts/check_real_conversation_replay_pool.py` 对 `is_real_customer_data=true` 的 manifest 条目新增真实来源和脱敏证明断言。
- 真实条目必须声明 `source_type=real_customer_conversation`、`redaction_method`、`redaction_reviewer`、`redaction_reviewed_at` 和 `raw_source_retention=not_committed`。
- 真实条目对应 fixture 的 metadata `source` 不能是 `synthetic`、`schema_sample` 或 `contract_shape_only`，且必须声明 `redaction`。
- 合成样例 manifest 的默认门禁行为不变：仍可验证门禁形状，但 `real_pool_ready=false`，不能作为真实问题分布证据。
- 当前仓库仍未接入真实客服样本；`--require-real` 失败是正确状态。

P15a 验收：

```powershell
python -m pytest tests\scripts\test_check_real_conversation_replay_pool.py tests\scripts\test_check_langchain_ai_layer_release_gate.py -q --no-cov
python -m ruff check scripts\check_real_conversation_replay_pool.py tests\scripts\test_check_real_conversation_replay_pool.py
python -m ruff format --check scripts\check_real_conversation_replay_pool.py tests\scripts\test_check_real_conversation_replay_pool.py
python scripts\check_real_conversation_replay_pool.py --summary
python scripts\check_real_conversation_replay_pool.py --require-real --summary
python scripts\check_langchain_ai_layer_release_gate.py --include-real-replay-pool --summary
python scripts\check_langchain_ai_layer_release_gate.py --include-real-replay-pool --require-real-replay-pool --summary
```

P15 后续：

- 接入真实脱敏样本时，manifest 必须补齐脱敏证明字段，并把原始客户会话留在仓库外。
- 真实池通过后，再把 release gate 的 `--require-real-replay-pool` 作为上线和作品集证据的一部分。

## 三十一、P16a LangSmith 运行时配置预检

2026-07-10 已完成 P16 LangSmith 线上观测准备的第一切片：

- 新增 `scripts/check_langsmith_runtime_config.py`，单独检查 LangSmith / LangChain tracing 运行时配置是否完整。
- 预检默认不要求启用 LangSmith：未配置时是安全关闭态，脚本通过；显式 `--require-enabled` 时会要求 tracing 开关、project 和 API key 都完整。
- 报告只输出 API key 是否配置的布尔值或 `configured` 标记，绝不打印 `LANGSMITH_API_KEY` 或 `LANGCHAIN_API_KEY` 的真实值。
- 预检会构造包含 API key、token、open_id、手机号、地址、用户消息、历史、客户画像和工具结果的样例 metadata，并通过现有 `AgentTracingConfig.to_runnable_config()` / `safe_trace_payload()` 检查脱敏结果。
- `scripts/check_langchain_ai_layer_release_gate.py --include-observability-evidence` 已先运行 `langsmith_runtime_config`，再运行原有观测证据包，避免 LangSmith 配置预检变成孤立脚本。
- 本切片不调用外部 LLM、不向 LangSmith 外发、不读取业务数据库、不改变客户或员工热路径。

P16a 验收：

```powershell
python -m pytest tests\scripts\test_check_langsmith_runtime_config.py tests\scripts\test_check_langchain_ai_layer_release_gate.py -q --no-cov
python -m ruff check scripts\check_langsmith_runtime_config.py scripts\check_langchain_ai_layer_release_gate.py tests\scripts\test_check_langsmith_runtime_config.py tests\scripts\test_check_langchain_ai_layer_release_gate.py
python -m ruff format --check scripts\check_langsmith_runtime_config.py scripts\check_langchain_ai_layer_release_gate.py tests\scripts\test_check_langsmith_runtime_config.py tests\scripts\test_check_langchain_ai_layer_release_gate.py
python scripts\check_langsmith_runtime_config.py --summary
python scripts\check_langsmith_runtime_config.py --require-enabled --summary
python scripts\check_langchain_ai_layer_release_gate.py --include-observability-evidence --summary
```

P16a 验证结果：

```text
LangSmith runtime config 和 release gate 相关测试通过：34 项失败 0。
Ruff check 通过。
Ruff format --check 通过。
默认关闭态预检通过：langsmith_runtime_config status=passed enabled=false safe_to_enable=false missing=0。
严格启用预检按预期失败：langsmith_runtime_config status=failed enabled=false safe_to_enable=false missing=2。
release gate 的 observability evidence 模式已包含 langsmith_runtime_config 步骤。
```

P16 后续：

- 若要真正打开线上 LangSmith，先在生产环境注入 key/project/tracing 开关，再运行 `python scripts\check_langsmith_runtime_config.py --require-enabled --summary`。
- 生产打开 LangSmith 前仍需额外确认外发合规、容量影响和采样策略；本切片只证明配置与 metadata 脱敏边界。

## 三十二、P17a 真实脱敏回放样本接入准备度报告

2026-07-10 已完成 P17 真实脱敏回放样本接入的第一切片：

- 新增 `scripts/check_real_conversation_replay_intake_readiness.py`，汇总真实 replay 接入前的机器准备度。
- readiness 报告检查导出器、replay checker、coverage checker、pool checker 和样本池 manifest 是否存在，并复用 `build_real_replay_pool_report()` 汇总当前池状态。
- 默认模式用于日常门禁：当前合成 contract pool 通过，报告明确 `real_sample_ready=false` 和后续动作，不把合成样例算作真实样本。
- 显式 `--require-real` 用于上线或作品集严格证据：当前仓库没有真实脱敏样本时按预期失败。
- release gate 新增显式 `--include-real-replay-intake-readiness`，默认发布门禁不变；`check_project.py --skip-tests` 已把 readiness 脚本纳入业务合约。
- 本切片不读取原始客户会话、不访问业务数据库、不调用外部 LLM、不提交真实客户数据，只把真实样本接入通道和缺口变成可追踪报告。

P17a 验收：

```powershell
python -m pytest tests\scripts\test_check_real_conversation_replay_intake_readiness.py tests\scripts\test_check_langchain_ai_layer_release_gate.py -q --no-cov
python -m ruff check scripts\check_real_conversation_replay_intake_readiness.py scripts\check_langchain_ai_layer_release_gate.py scripts\check_project.py tests\scripts\test_check_real_conversation_replay_intake_readiness.py tests\scripts\test_check_langchain_ai_layer_release_gate.py
python -m ruff format --check scripts\check_real_conversation_replay_intake_readiness.py scripts\check_langchain_ai_layer_release_gate.py scripts\check_project.py tests\scripts\test_check_real_conversation_replay_intake_readiness.py tests\scripts\test_check_langchain_ai_layer_release_gate.py
python scripts\check_real_conversation_replay_intake_readiness.py --summary
python scripts\check_real_conversation_replay_intake_readiness.py --require-real --summary
python scripts\check_langchain_ai_layer_release_gate.py --include-real-replay-intake-readiness --summary
```

P17a 验证结果：

```text
真实 replay intake readiness 和 release gate 相关测试通过。
Ruff check 通过。
Ruff format --check 通过。
默认 readiness 通过：real_conversation_replay_intake status=passed real_sample_ready=false。
严格真实样本模式按预期失败：当前仓库仍未接入真实脱敏客户会话。
显式 intake readiness release gate 通过。
```

P17 后续：

- P17b 需要由人工或具备权限的流程提供仓库外原始客服记录，先用 `scripts/export_real_conversation_replay_fixture.py` 脱敏导出到 gitignored reports，再审核后用 `scripts/prepare_real_conversation_replay_pool_entry.py` 生成 manifest 条目草稿，最后由人工确认后补 manifest 真实条目。
- 真实条目通过 `--require-real` 后，才能把 `real_sample_ready=true` 作为上线和作品集证据。

## 三十三、P17b-prep 真实 replay pool 条目草稿生成器

2026-07-10 已完成 P17 真实脱敏回放样本接入的第二个准备切片：

- 新增 `scripts/prepare_real_conversation_replay_pool_entry.py`，用于把已经脱敏并人工审核过的 replay fixture 转成真实样本池 manifest 条目草稿。
- 工具要求调用方显式提供样本名称、证据 ID、脱敏方法、脱敏审核人和脱敏审核日期，并默认写出 gitignored `reports/agent-eval/real-replay-pool-entry-draft.json`。
- 草稿生成前会复用 `build_real_replay_coverage_report()` 检查 order、refund、after_sales、inventory、price、human_transfer 六类事实敏感场景覆盖，不允许 coverage 未通过的 fixture 直接生成可用条目。
- 工具会拒绝 `synthetic`、`schema_sample`、`contract_shape_only` 等来源声明，要求 `metadata.contains_sensitive_data=false`、fixture metadata 带 redaction，且 manifest 草稿声明 `source_type=real_customer_conversation` 和 `raw_source_retention=not_committed`。
- CLI 已显式暴露 `--source-type` 和 `--raw-source-retention`；参数会进入条目草稿并继续受真实来源与原始来源不入仓断言保护。
- `scripts/check_real_conversation_replay_intake_readiness.py` 和 `scripts/check_langchain_ai_layer_production_plan.py` 已把该脚本列为真实样本接入通道必备 artifact。
- 本切片不读取原始客户会话、不修改样本池 manifest、不访问业务数据库、不调用外部 LLM、不提交真实客户数据；它只生成待人工确认的条目草稿。

P17b-prep 验收：

```powershell
python -m pytest tests\scripts\test_prepare_real_conversation_replay_pool_entry.py tests\scripts\test_check_real_conversation_replay_intake_readiness.py tests\scripts\test_check_langchain_ai_layer_production_plan.py -q --no-cov
python -m ruff check scripts\prepare_real_conversation_replay_pool_entry.py scripts\check_real_conversation_replay_intake_readiness.py scripts\check_langchain_ai_layer_production_plan.py tests\scripts\test_prepare_real_conversation_replay_pool_entry.py tests\scripts\test_check_real_conversation_replay_intake_readiness.py tests\scripts\test_check_langchain_ai_layer_production_plan.py
python -m ruff format --check scripts\prepare_real_conversation_replay_pool_entry.py scripts\check_real_conversation_replay_intake_readiness.py scripts\check_langchain_ai_layer_production_plan.py tests\scripts\test_prepare_real_conversation_replay_pool_entry.py tests\scripts\test_check_real_conversation_replay_intake_readiness.py tests\scripts\test_check_langchain_ai_layer_production_plan.py
python scripts\check_langchain_ai_layer_production_plan.py --summary
python scripts\check_real_conversation_replay_intake_readiness.py --summary
```

## 三十四、P17b-intake 外部真实 replay 接入操作包

2026-07-10 已完成 P17b 的外部接入操作包切片：

- 新增 `scripts/build_real_conversation_replay_intake_packet.py`，用于生成给真实客服记录持有人执行的接入包。
- 操作包列出原始记录必须包含的字段、六类事实敏感场景覆盖目标、脱敏要求、人工审核要求和完整命令链。
- 操作包已增加可填写 `handoff_template`，使用导出器真实支持的扁平 canonical 字段：`golden_case_id`、`user_message`、`final_reply`，并保留可选 `case_id`、`source`、`group`、`intent`；不再把未被导出器消费的 `messages[]` 误写成可执行输入合同。
- 命令链覆盖导出脱敏 fixture、检查 replay 契约、检查场景覆盖、候选准入审计及 JSON 留档、生成 pool entry 草稿、严格检查 pool manifest 和严格检查 intake readiness。
- 导出命令显式要求真实脱敏来源标识；候选审计和 entry 草稿命令显式携带 `source_type=real_customer_conversation` 与 `raw_source_retention=not_committed`，减少人工执行时漏填准入声明的风险。
- 操作包报告明确 `raw_customer_conversation_read=false`、`real_customer_data_committed=false`、`business_database_read=false` 和 `external_llm_called=false`；脚本不读取真实原始记录，只生成执行说明和门禁命令。
- `scripts/check_real_conversation_replay_intake_readiness.py`、`scripts/check_langchain_ai_layer_production_plan.py` 和 `scripts/check_project.py --skip-tests` 已接入该脚本，防止真实样本接入入口丢失。
- 当前仓库仍未接入真实客服样本，`real_sample_ready=false` 仍是正确状态；本切片不把合成样例算作真实样本。
- 2026-07-10 接入模板与命令链增强已部署到生产 `0.105.14 / 37bfc58`；运行时版本门禁、加强 release gate `8/8`、P13b 复核和严格发布证据包均通过，`packet_ready=true`。这只证明工具链已部署，不代表真实样本已到位。

P17b-intake 验收：

```powershell
python -m pytest tests\scripts\test_build_real_conversation_replay_intake_packet.py tests\scripts\test_prepare_real_conversation_replay_pool_entry.py tests\scripts\test_export_real_conversation_replay_fixture.py tests\scripts\test_check_real_conversation_replay_intake_readiness.py tests\scripts\test_check_langchain_ai_layer_production_plan.py -q --no-cov
python -m ruff check scripts\build_real_conversation_replay_intake_packet.py scripts\prepare_real_conversation_replay_pool_entry.py scripts\check_real_conversation_replay_intake_readiness.py scripts\check_langchain_ai_layer_production_plan.py scripts\check_project.py tests\scripts\test_build_real_conversation_replay_intake_packet.py tests\scripts\test_prepare_real_conversation_replay_pool_entry.py tests\scripts\test_export_real_conversation_replay_fixture.py tests\scripts\test_check_real_conversation_replay_intake_readiness.py tests\scripts\test_check_langchain_ai_layer_production_plan.py
python -m ruff format --check scripts\build_real_conversation_replay_intake_packet.py scripts\prepare_real_conversation_replay_pool_entry.py scripts\check_real_conversation_replay_intake_readiness.py scripts\check_langchain_ai_layer_production_plan.py scripts\check_project.py tests\scripts\test_build_real_conversation_replay_intake_packet.py tests\scripts\test_prepare_real_conversation_replay_pool_entry.py tests\scripts\test_export_real_conversation_replay_fixture.py tests\scripts\test_check_real_conversation_replay_intake_readiness.py tests\scripts\test_check_langchain_ai_layer_production_plan.py
python scripts\build_real_conversation_replay_intake_packet.py --summary
python scripts\check_real_conversation_replay_intake_readiness.py --summary
python scripts\check_langchain_ai_layer_production_plan.py --summary
```

## 三十四点二、P17b-intake-precheck 真实 replay 接入提交前自检清单

2026-07-10 已完成 P17b 外部接入包的提交前自检增强：

- `scripts/build_real_conversation_replay_intake_packet.py` 新增 `pre_submission_checklist`，列出外部记录持有人、脱敏审核人和仓库维护者在提交真实脱敏 replay 前必须确认的事项。
- 自检项覆盖真实客服会话来源、原始数据仓库外保存、手机号/地址/open_id/union_id/客户姓名/完整订单号脱敏、六类事实敏感场景覆盖目标和 evidence ID 登记。
- 自检清单只作为交接前置检查，不读取原始客服记录、不提交真实客户数据、不访问业务数据库、不调用外部 LLM，也不让 `candidate_ready`、`real_sample_ready` 或外部证据完整态变为 true。
- 文件职责评审结论为 `keep_cohesive_with_review`：自检清单属于真实 replay intake packet 的输出合同，和模板、命令链、边界声明同属一个交接包职责；拆成独立脚本会增加薄 helper 和交接跳转成本。

P17b-intake-precheck 验收：

```powershell
python -m pytest tests\scripts\test_build_real_conversation_replay_intake_packet.py -q --tb=short --no-cov
python -m ruff check scripts\build_real_conversation_replay_intake_packet.py tests\scripts\test_build_real_conversation_replay_intake_packet.py
python -m ruff format --check scripts\build_real_conversation_replay_intake_packet.py tests\scripts\test_build_real_conversation_replay_intake_packet.py
python scripts\build_real_conversation_replay_intake_packet.py --summary
```
## 三十四点一、P17b-candidate 真实 replay 候选样本准入审计

2026-07-10 已完成 P17b 的候选样本准入审计切片：

- 新增 `scripts/audit_real_conversation_replay_candidate.py`，用于在真实脱敏 replay fixture 写入样本池 manifest 前做只读审计。
- 默认无输入时报告通过但明确 `candidate_ready=false`，并输出 `provide_redacted_real_replay_candidate_fixture`；严格模式 `--require-fixture` 缺输入会失败，避免把没有真实候选样本误报为可接入。
- 有候选 fixture 时，审计会复用 `check_real_conversation_replay.py` 和 `check_real_conversation_replay_coverage.py`，同时检查 `metadata.contains_sensitive_data=false`、fixture 来源不是 `synthetic/schema_sample/contract_shape_only`、脱敏 metadata 存在。
- 真实候选必须显式提供 `source_type=real_customer_conversation`、脱敏方法、脱敏审核人、审核时间、`raw_source_retention=not_committed` 和 evidence ID。
- 报告会输出 `manifest_entry_draft` 供人工确认，但不会修改 manifest、不读取原始客户会话、不访问业务数据库、不调用外部 LLM、不提交真实客户数据。
- `scripts/check_langchain_ai_layer_production_plan.py` 和 `scripts/check_project.py --skip-tests` 已接入默认 readiness 报告，防止 P17b 候选准入审计入口丢失。

P17b-candidate 验收：

```powershell
python -m pytest tests\scripts\test_audit_real_conversation_replay_candidate.py tests\scripts\test_check_langchain_ai_layer_production_plan.py -q --no-cov
python -m ruff check scripts\audit_real_conversation_replay_candidate.py scripts\check_langchain_ai_layer_production_plan.py scripts\check_project.py tests\scripts\test_audit_real_conversation_replay_candidate.py tests\scripts\test_check_langchain_ai_layer_production_plan.py
python -m ruff format --check scripts\audit_real_conversation_replay_candidate.py scripts\check_langchain_ai_layer_production_plan.py scripts\check_project.py tests\scripts\test_audit_real_conversation_replay_candidate.py tests\scripts\test_check_langchain_ai_layer_production_plan.py
python scripts\audit_real_conversation_replay_candidate.py --summary
python scripts\audit_real_conversation_replay_candidate.py --require-fixture --summary
python scripts\check_langchain_ai_layer_production_plan.py --summary
python scripts\check_project.py --skip-tests
```

## 三十五、P18a LangSmith 生产灰度发布预检

2026-07-10 已完成 P18 的第一个生产灰度预检切片：

- 新增 `scripts/check_langsmith_production_rollout.py`，用于在真正打开 LangSmith 外发前生成发布预检报告。
- 默认模式不要求启用 LangSmith，采样率为 `0.0`，用于证明当前关闭态安全、metadata 脱敏、冷导入不拉重依赖、回滚命令明确。
- 严格模式 `--require-enabled` 要求 LangSmith runtime config 已满足 `safe_to_enable`，且调用方显式传入 `--external-export-approved`，避免在没有人工外发合规确认时把生产 trace 发出去。
- 预检固定默认安全采样率上限 `0.1`；超过上限会失败并输出 `lower_langsmith_sample_rate_to_safe_default`。
- 报告明确 `production_env_changed=false`、`langsmith_external_export=false`、`external_llm_called=false`、`business_database_read=false`，本脚本只读配置和冷导入状态，不修改生产环境。
- `scripts/check_langchain_ai_layer_production_plan.py` 和 `scripts/check_project.py --skip-tests` 已接入该预检，防止 P18 入口丢失。

P18a 验收：

```powershell
python -m pytest tests\scripts\test_check_langsmith_production_rollout.py tests\scripts\test_check_langchain_ai_layer_production_plan.py -q --no-cov
python -m ruff check scripts\check_langsmith_production_rollout.py scripts\check_langchain_ai_layer_production_plan.py scripts\check_project.py tests\scripts\test_check_langsmith_production_rollout.py tests\scripts\test_check_langchain_ai_layer_production_plan.py
python -m ruff format --check scripts\check_langsmith_production_rollout.py scripts\check_langchain_ai_layer_production_plan.py scripts\check_project.py tests\scripts\test_check_langsmith_production_rollout.py tests\scripts\test_check_langchain_ai_layer_production_plan.py
python scripts\check_langsmith_production_rollout.py --summary
python scripts\check_langsmith_runtime_config.py --summary
python scripts\check_langchain_ai_layer_production_plan.py --summary
```

## 三十六、P18b LangSmith 生产启用操作包

2026-07-10 已完成 P18 的第二个生产启用准备切片：

- 新增 `scripts/build_langsmith_production_enablement_packet.py`，用于生成 LangSmith 生产启用操作包。
- 操作包列出生产启用需要的环境变量：`LANGCHAIN_TRACING_ENABLED=true`、`LANGCHAIN_TRACING_V2=true`、`LANGSMITH_TRACING=true`、`LANGCHAIN_PROJECT=<project>` 和 `LANGSMITH_API_KEY=<configured outside repo>`。
- 操作包固定启用前门禁命令、启用后观测命令、人工合规确认项和回滚命令；默认采样率为 `0.05`，必须高于 0 且不超过 P18a 安全上限 `0.1`。
- 报告明确 `production_env_changed=false`、`langsmith_external_export=false`、`api_key_printed=false`、`business_database_read=false` 和 `external_llm_called=false`；本脚本不读取生产环境、不打印 API key、不修改服务配置。
- `scripts/check_langchain_ai_layer_production_plan.py` 和 `scripts/check_project.py --skip-tests` 已接入该操作包，防止 P18b 启用流程从生产增强计划中丢失。
- 当前 P18b 只证明启用流程、边界和回滚包齐全；真正打开生产外发仍需要仓库外注入 key/project/tracing 开关，并运行 P18a 严格模式。

P18b 验收：

```powershell
python -m pytest tests\scripts\test_build_langsmith_production_enablement_packet.py tests\scripts\test_check_langchain_ai_layer_production_plan.py -q --no-cov
python -m ruff check scripts\build_langsmith_production_enablement_packet.py scripts\check_langchain_ai_layer_production_plan.py scripts\check_project.py tests\scripts\test_build_langsmith_production_enablement_packet.py tests\scripts\test_check_langchain_ai_layer_production_plan.py
python -m ruff format --check scripts\build_langsmith_production_enablement_packet.py scripts\check_langchain_ai_layer_production_plan.py scripts\check_project.py tests\scripts\test_build_langsmith_production_enablement_packet.py tests\scripts\test_check_langchain_ai_layer_production_plan.py
python scripts\build_langsmith_production_enablement_packet.py --summary
python scripts\check_langsmith_production_rollout.py --summary
python scripts\check_langchain_ai_layer_production_plan.py --summary
```

## 三十七、P21a LangChain AI 层容量门禁

2026-07-10 已完成 P21 的第一个容量与成本治理切片：

- 新增 `scripts/check_langchain_ai_layer_capacity.py`，用于回答“当前服务器是否支撑得住 LangChain AI 应用层”的工程问题。
- 门禁默认运行受控 fake trace probe，不访问真实业务库、不调用外部 LLM、不发送企微消息、不压测生产。
- 报告统计 trace probe 耗时、trace JSON payload 大小、trace run 数、event 数、单 run 最大 event 数、冷导入是否拉起重依赖，以及 LangSmith 默认关闭态和采样率边界。
- 默认阈值为 trace probe `5000ms`、trace payload `200000 bytes`、单 run event 数 `20`，LangSmith 采样率继续沿用 P18a 的 `0.1` 安全上限。
- `scripts/check_langchain_ai_layer_production_plan.py` 和 `scripts/check_project.py --skip-tests` 已接入该门禁，防止容量治理从生产增强计划中丢失。
- 当前本地默认报告通过：受控 trace probe 耗时约 3.1 秒，payload 约 2.2KB；这不是生产压测结论，而是发布前轻量容量和成本边界门禁。

P21a 验收：

```powershell
python -m pytest tests\scripts\test_check_langchain_ai_layer_capacity.py tests\scripts\test_check_langchain_ai_layer_production_plan.py -q --no-cov
python -m ruff check scripts\check_langchain_ai_layer_capacity.py scripts\check_langchain_ai_layer_production_plan.py scripts\check_project.py tests\scripts\test_check_langchain_ai_layer_capacity.py tests\scripts\test_check_langchain_ai_layer_production_plan.py
python -m ruff format --check scripts\check_langchain_ai_layer_capacity.py scripts\check_langchain_ai_layer_production_plan.py scripts\check_project.py tests\scripts\test_check_langchain_ai_layer_capacity.py tests\scripts\test_check_langchain_ai_layer_production_plan.py
python scripts\check_langchain_ai_layer_capacity.py --summary
python scripts\check_langsmith_production_rollout.py --summary
python scripts\check_langchain_ai_layer_production_plan.py --summary
```

## 三十七点一、P21b 生产只读资源观测门禁

2026-07-10 已完成 P21 的第二个容量与成本治理切片：

- 扩展 `scripts/check_langchain_ai_layer_capacity.py`，新增 `--include-production-runtime` 显式开关。
- 默认容量门禁仍只运行本地受控 fake trace probe、冷导入检查和 LangSmith 默认关闭态检查，不访问生产。
- 显式打开生产只读观测时，通过 SSH 读取 `systemctl`、生产 `VERSION`、本机 `/health` / `/ready` 版本、服务进程 RSS、线程数、`MemAvailable` 和 `load1`。
- 生产观测不做压测、不读取业务数据库、不调用外部 LLM、不向 LangSmith 外发、不发送企微消息。
- 默认阈值为进程 RSS 不超过 `512MB`、系统可用内存不低于 `128MB`、`load1` 不超过 `4.0`；版本必须同时匹配本地 `VERSION`、生产 `VERSION`、`/health` 和 `/ready`。
- 报告默认 summary 会标出 `production_runtime=skipped|ok|failed`，避免把未执行生产观测误读为已验证。

P21b 验收：

```powershell
python -m pytest tests\scripts\test_check_langchain_ai_layer_capacity.py -q --no-cov
python -m ruff check scripts\check_langchain_ai_layer_capacity.py tests\scripts\test_check_langchain_ai_layer_capacity.py
python -m ruff format --check scripts\check_langchain_ai_layer_capacity.py tests\scripts\test_check_langchain_ai_layer_capacity.py
python scripts\check_langchain_ai_layer_capacity.py --summary
python scripts\check_langchain_ai_layer_capacity.py --include-production-runtime --summary
```

## 三十七点二、P21c 生产资源观测 release gate 加强模式

2026-07-10 已完成 P21 的第三个容量与发布治理切片：

- 扩展 `scripts/check_langchain_ai_layer_release_gate.py`，新增显式 `--include-production-runtime-capacity`。
- 默认 release gate 行为不变，仍只运行双机器人 eval、客户回复回放 probe 和扩展 eval。
- 开启该参数时，release gate 会追加运行 `scripts/check_langchain_ai_layer_capacity.py --include-production-runtime --json-out reports\agent-traces\langchain-ai-layer-capacity.json --summary`。
- release gate JSON 顶层新增 `include_production_runtime_capacity`，`release_summary.langchain_ai_layer_capacity` 会汇总 trace latency、payload bytes、生产版本、服务状态、RSS、可用内存和 load1。
- 该加强模式只读生产资源，不做压测、不读取业务数据库、不调用外部 LLM、不向 LangSmith 外发。

P21c 验收：

```powershell
python -m pytest tests\scripts\test_check_langchain_ai_layer_release_gate.py -q --no-cov
python -m ruff check scripts\check_langchain_ai_layer_release_gate.py tests\scripts\test_check_langchain_ai_layer_release_gate.py
python -m ruff format --check scripts\check_langchain_ai_layer_release_gate.py tests\scripts\test_check_langchain_ai_layer_release_gate.py
python scripts\check_langchain_ai_layer_release_gate.py --include-production-smoke --include-observability-evidence --include-production-runtime-capacity --json-out reports\agent-eval\langchain-ai-layer-release-gate-with-production-observability-latest.json --summary
```

## 三十七点三、P21d 生产观测发布证据容量校验

2026-07-10 已完成 P21 的第四个容量与发布治理切片：

- 扩展 `scripts/check_langchain_production_observability_release.py`，把 `release_summary.langchain_ai_layer_capacity` 作为显式生产发布证据。
- P13b 门禁现在会阻断缺少 capacity summary、capacity gate 失败、生产只读资源观测未通过、服务非 active、capacity 报告版本与本地目标版本不一致等情况。
- summary 输出新增 `capacity_runtime=ok|missing|failed`，便于上线收口时一眼判断生产资源证据是否在报告里。
- 本切片不改 release gate 的执行步骤，只加强 release gate JSON 的证据复核；仍不做压测、不读取业务数据库、不调用外部 LLM、不向 LangSmith 外发。

P21d 验收：

```powershell
python -m pytest tests\scripts\test_check_langchain_production_observability_release.py -q --no-cov
python -m ruff check scripts\check_langchain_production_observability_release.py tests\scripts\test_check_langchain_production_observability_release.py
python -m ruff format --check scripts\check_langchain_production_observability_release.py tests\scripts\test_check_langchain_production_observability_release.py
python scripts\check_langchain_ai_layer_release_gate.py --include-production-smoke --include-observability-evidence --include-production-runtime-capacity --json-out reports\agent-eval\langchain-ai-layer-release-gate-with-production-observability-latest.json --summary
python scripts\check_langchain_production_observability_release.py --report reports\agent-eval\langchain-ai-layer-release-gate-with-production-observability-latest.json --summary
```

## 三十七点四、P22a LangChain 发布证据包

2026-07-10 已完成 E7 发布证据一键收口的第一切片：

- 新增 `scripts/build_langchain_release_evidence_packet.py`，把 release gate JSON、P13b 生产观测发布复核、git refs、LangSmith 状态、RAG 模式、真实 replay readiness 和回滚命令汇总为固定发布证据包。
- 默认模式是轻量 readiness：如果没有 release gate JSON，不阻断普通项目检查，但明确 `packet_ready=false` 并输出 `run_langchain_release_gate_with_production_evidence`。
- 严格模式 `--require-production-evidence` 要求已有生产 release gate 和 P13b 生产观测发布证据均通过；如果 release gate 失败或生产证据缺失，证据包总状态失败。
- 证据包只读已有报告和本地 git refs，不重启生产、不读取业务数据库、不调用外部 LLM、不提交真实客户数据。
- `scripts/check_langchain_ai_layer_production_plan.py` 和 `scripts/check_project.py --skip-tests` 已接入默认 readiness，防止发布证据包入口丢失。

P22a 验收：

```powershell
python -m pytest tests\scripts\test_build_langchain_release_evidence_packet.py tests\scripts\test_check_langchain_ai_layer_production_plan.py -q --no-cov
python -m ruff check scripts\build_langchain_release_evidence_packet.py scripts\check_langchain_ai_layer_production_plan.py scripts\check_project.py tests\scripts\test_build_langchain_release_evidence_packet.py tests\scripts\test_check_langchain_ai_layer_production_plan.py
python -m ruff format --check scripts\build_langchain_release_evidence_packet.py scripts\check_langchain_ai_layer_production_plan.py scripts\check_project.py tests\scripts\test_build_langchain_release_evidence_packet.py tests\scripts\test_check_langchain_ai_layer_production_plan.py
python scripts\build_langchain_release_evidence_packet.py --summary
python scripts\build_langchain_release_evidence_packet.py --require-production-evidence --summary
python scripts\check_langchain_ai_layer_production_plan.py --summary
python scripts\check_project.py --skip-tests
```

## 三十八、P19a RAG shadow 观测报告

2026-07-10 已完成 P19 的第一个 RAG 生产增强观测切片：

- 新增 `scripts/report_rag_shadow_observability.py`，复用既有 `report_retrieval_shadow_compare.run_shadow_compare()` 生成发布/运维视角的 RAG shadow 观测报告。
- 默认使用 `data/bot.db` 和 `tests/fixtures/customer_rag_golden_cases.json`，避免旧 `retrieval_eval_set.json` 让结论偏乐观。
- 报告默认不输出 case query 原文，只输出 baseline、候选模式指标、delta、changed case 数、按 group 汇总和热路径建议；需要排障时才用 `--include-case-diffs` 显式输出完整 case diff。
- 当前真实 BGE 路径下，`hybrid` baseline 为 Recall@5 `0.9857`、MRR `0.8881`；`planned-hybrid` 与 baseline 持平，标记为 `eligible_for_controlled_gray_release`；`planned-hybrid+rerank` Recall@5 下降 `-0.0143`，继续标记为 `keep_shadow_only`。
- 本切片不改变 `RAG_RETRIEVAL_MODE`，不改客户热路径，不写业务数据库，不调用外部 LLM；它只把 shadow compare 结论固化成项目门禁和发布证据。
- `scripts/check_langchain_ai_layer_production_plan.py` 和 `scripts/check_project.py --skip-tests` 已接入该报告，防止 RAG 灰度观测从生产增强计划中丢失。

P19a 验收：

```powershell
python -m pytest tests\scripts\test_report_rag_shadow_observability.py tests\scripts\test_check_langchain_ai_layer_production_plan.py -q --no-cov
python -m ruff check scripts\report_rag_shadow_observability.py scripts\check_langchain_ai_layer_production_plan.py scripts\check_project.py tests\scripts\test_report_rag_shadow_observability.py tests\scripts\test_check_langchain_ai_layer_production_plan.py
python -m ruff format --check scripts\report_rag_shadow_observability.py scripts\check_langchain_ai_layer_production_plan.py scripts\check_project.py tests\scripts\test_report_rag_shadow_observability.py tests\scripts\test_check_langchain_ai_layer_production_plan.py
python scripts\report_rag_shadow_observability.py --summary
python scripts\report_retrieval_shadow_compare.py --db data\bot.db --fixture tests\fixtures\customer_rag_golden_cases.json --k 5 --json-out reports\retrieval-shadow\latest.json
python scripts\check_langchain_ai_layer_production_plan.py --summary
```

## 三十九、P19b 真实 RAG shadow log 观测输入门禁

2026-07-10 已完成 P19 的第二个 RAG 生产增强观测切片：

- 新增 `scripts/report_rag_shadow_log_observability.py`，用于接入仓库外导出的脱敏真实 RAG 检索日志，并复算 planned-hybrid / planned-hybrid+rerank 候选结果。
- 输入合同固定为 `metadata.source_type`、`metadata.contains_sensitive_data=false` 和 records 内的 `id`、`query`、`baseline_top_keys`；可选 `group` 用于按业务场景汇总差异。
- 默认没有输入时报告通过但明确 `shadow_log_ready=false`，并输出 `provide_redacted_rag_shadow_log_input`；严格模式 `--require-input` 会失败，避免把“没有真实日志”误报为已准备好。
- 默认报告只输出 `query_hash`，不输出 query 原文；只有显式 `--include-queries` 才输出已脱敏 query 文本。
- 本切片不改变 `RAG_RETRIEVAL_MODE`，不改客户热路径，不写业务数据库，不调用外部 LLM，不向 LangSmith 外发；它只把真实 shadow log 的输入合同、脱敏边界和 strict gate 固化为工程门禁。
- `scripts/check_langchain_ai_layer_production_plan.py` 和 `scripts/check_project.py --skip-tests` 已接入默认 readiness 报告，防止 P19b 从生产增强计划中丢失。

P19b 验收：

```powershell
python -m pytest tests\scripts\test_report_rag_shadow_log_observability.py tests\scripts\test_check_langchain_ai_layer_production_plan.py -q --no-cov
python -m ruff check scripts\report_rag_shadow_log_observability.py scripts\check_langchain_ai_layer_production_plan.py scripts\check_project.py tests\scripts\test_report_rag_shadow_log_observability.py tests\scripts\test_check_langchain_ai_layer_production_plan.py
python -m ruff format --check scripts\report_rag_shadow_log_observability.py scripts\check_langchain_ai_layer_production_plan.py scripts\check_project.py tests\scripts\test_report_rag_shadow_log_observability.py tests\scripts\test_check_langchain_ai_layer_production_plan.py
python scripts\report_rag_shadow_log_observability.py --summary
python scripts\report_rag_shadow_log_observability.py --require-input --summary
python scripts\check_langchain_ai_layer_production_plan.py --summary
```

## 三十九点一、P19c 真实 RAG shadow log 外部交接包与来源证明

2026-07-10 已完成 E2 输入准备的第三个切片：

- 新增 `scripts/build_rag_shadow_log_intake_packet.py`，输出仓库外日志持有人可填写的 metadata/records 模板、脱敏要求、推荐记录数和严格验证命令链。
- 交接 metadata 固定要求 `source_type=real_customer_rag_shadow_log`、`contains_sensitive_data=false`、脱敏方法、审核人、ISO 审核日期、`raw_source_retention=not_committed` 和 evidence ID。
- `scripts/report_rag_shadow_log_observability.py` 已把上述来源证明纳入 `shadow_log_ready` 判定；未填写审核字段、错误日期、损坏 JSON、非对象 metadata、非数组 records 或 query 中明显的手机号/长数字/open_id 形态都会返回结构化失败和修复动作。
- 交接包只生成模板，不读取原始生产日志、不访问业务数据库、不调用外部 LLM、不改变生产热路径或 `RAG_RETRIEVAL_MODE`。
- 当前仍没有真实脱敏 RAG shadow log，`shadow_log_ready=false` 保持不变；只有外部输入通过严格合同和候选复算后，E2 才能完成并评估 E3。
- `scripts/check_langchain_ai_layer_production_plan.py`、`scripts/check_project.py --skip-tests` 和作品集代码路径检查已接入新入口。

P19c 验收：

```powershell
python -m pytest tests\scripts\test_report_rag_shadow_log_observability.py tests\scripts\test_build_rag_shadow_log_intake_packet.py tests\scripts\test_check_langchain_ai_layer_production_plan.py -q --tb=short --no-cov
python -m ruff check scripts\report_rag_shadow_log_observability.py scripts\build_rag_shadow_log_intake_packet.py scripts\check_langchain_ai_layer_production_plan.py scripts\check_project.py scripts\build_langchain_portfolio_evidence_packet.py tests\scripts\test_report_rag_shadow_log_observability.py tests\scripts\test_build_rag_shadow_log_intake_packet.py tests\scripts\test_check_langchain_ai_layer_production_plan.py
python -m ruff format --check scripts\report_rag_shadow_log_observability.py scripts\build_rag_shadow_log_intake_packet.py scripts\check_langchain_ai_layer_production_plan.py scripts\check_project.py scripts\build_langchain_portfolio_evidence_packet.py tests\scripts\test_report_rag_shadow_log_observability.py tests\scripts\test_build_rag_shadow_log_intake_packet.py tests\scripts\test_check_langchain_ai_layer_production_plan.py
python scripts\build_rag_shadow_log_intake_packet.py --summary
python scripts\report_rag_shadow_log_observability.py --summary
python scripts\check_langchain_ai_layer_production_plan.py --summary
python scripts\check_project.py --skip-tests
```

## 三十九点二、P19c-intake-precheck RAG shadow log 接入提交前自检清单

2026-07-10 已完成 P19c 外部接入包的提交前自检增强：

- `scripts/build_rag_shadow_log_intake_packet.py` 新增 `pre_submission_checklist`，要求外部日志持有人/脱敏审核人/仓库维护者在真实 shadow log 提交前确认真实来源、原始日志不入仓、query 文本脱敏、metadata 证明字段齐全和 evidence ID 已登记。
- `scripts/build_langchain_external_evidence_handoff_packet.py` 汇总 E2 接入包时透传该自检清单，让 P23 外部证据交接汇总同时覆盖 P17b 真实 replay 和 P19c RAG shadow log 的提交前检查。
- `boundaries.readiness_changed=false` 明确该清单只增强人工提交前置检查，不读取真实 shadow log、不复算候选、不改变 RAG 模式，也不把缺失外部输入视为 ready。
- 文件职责评审结论为 `keep_cohesive_with_review`：该清单是 RAG shadow log intake packet 输出合同的一部分，与模板、命令链和 readiness 边界同属“外部提交前交接”职责；若仅为了体量阈值拆成独立 helper，会增加薄转发和跨文件跳转，不符合 ADR 0004 的责任优先治理。
- 本切片不读取真实 query、不访问业务数据库、不调用外部 LLM、不修改生产服务，也不让 `shadow_log_ready`、`external_evidence_complete` 或 `portfolio_complete` 变为 true。

P19c-intake-precheck 验收：

```powershell
python -m pytest tests\scripts\test_build_rag_shadow_log_intake_packet.py tests\scripts\test_build_langchain_external_evidence_handoff_packet.py -q --tb=short --no-cov
python -m ruff check scripts\build_rag_shadow_log_intake_packet.py tests\scripts\test_build_rag_shadow_log_intake_packet.py scripts\build_langchain_external_evidence_handoff_packet.py tests\scripts\test_build_langchain_external_evidence_handoff_packet.py
python -m ruff format --check scripts\build_rag_shadow_log_intake_packet.py tests\scripts\test_build_rag_shadow_log_intake_packet.py scripts\build_langchain_external_evidence_handoff_packet.py tests\scripts\test_build_langchain_external_evidence_handoff_packet.py
python scripts\build_rag_shadow_log_intake_packet.py --summary
python scripts\build_langchain_external_evidence_handoff_packet.py --summary
```

## 四十、P5b / E6a 作品集证据清单

2026-07-10 已完成 E6 作品集证据包升级的机器可复核切片：

- 新增 `scripts/build_langchain_portfolio_evidence_packet.py`，只读聚合 Agent Eval、RAG shadow、真实 shadow log readiness、trace 观测、真实 replay coverage 和 P22a 严格发布证据包。
- 清单固定输出 `verified_evidence_ready`、`external_evidence_complete` 和 `portfolio_complete`，把“现有工程证据可展示”与“E1-E5 外部增强阶段完成”分开。
- 默认模式允许缺少外部输入但明确输出未完成动作；`--require-verified-evidence` 要求当前版本 eval、RAG shadow、trace 和生产 release packet 可复核；`--require-complete` 还要求 E1-E5 全部完成。
- E4 只有在 LangSmith 开关已启用且存在同版本、人工批准、受控采样率和实际 trace 已验证的生产外发报告时才会 ready，不能只靠本地 key 或开关制造完成。
- E5 必须同时满足真实样本池 ready 和非 `tests/fixtures` 合成来源的事实敏感 coverage 报告，不能复用 P11d 的合成覆盖样例制造完成。
- 当前严格工程证据通过，但真实 replay、真实 RAG shadow log、planned-hybrid 灰度、LangSmith 外发和真实事实敏感覆盖仍未完成，因此 `portfolio_complete=false`，完整性严格门禁按预期失败。
- `scripts/check_langchain_ai_layer_production_plan.py` 和 `scripts/check_project.py --skip-tests` 已接入默认清单，防止作品集证据入口与生产增强计划脱节。

P5b / E6a 验收：

```powershell
python -m pytest tests\scripts\test_build_langchain_portfolio_evidence_packet.py tests\scripts\test_check_langchain_ai_layer_production_plan.py -q --tb=short --no-cov
python -m ruff check scripts\build_langchain_portfolio_evidence_packet.py scripts\check_langchain_ai_layer_production_plan.py scripts\check_project.py tests\scripts\test_build_langchain_portfolio_evidence_packet.py tests\scripts\test_check_langchain_ai_layer_production_plan.py
python -m ruff format --check scripts\build_langchain_portfolio_evidence_packet.py scripts\check_langchain_ai_layer_production_plan.py scripts\check_project.py tests\scripts\test_build_langchain_portfolio_evidence_packet.py tests\scripts\test_check_langchain_ai_layer_production_plan.py
python scripts\build_langchain_portfolio_evidence_packet.py --require-verified-evidence --summary
python scripts\build_langchain_portfolio_evidence_packet.py --require-complete --summary
python scripts\check_langchain_ai_layer_production_plan.py --summary
python scripts\check_project.py --skip-tests
```

## 四十一、P23a 外部证据交接汇总包

2026-07-10 已完成 E1/E2/E6 外部证据交接汇总的机器可复核切片：

- 新增 `scripts/build_langchain_external_evidence_handoff_packet.py`，只读聚合真实 replay 接入包、真实 RAG shadow log 接入包和作品集证据清单的 E1-E5 缺口。
- 汇总包输出 `required_external_inputs`、`missing_actions`、E1/E2 可填写模板、命令链和统一交接顺序，方便仓库外真实记录持有人或人工审核人按一份清单准备输入。
- 职责评审结论为 `split_by_responsibility`：交接汇总的使用者是外部记录持有人/审核人，变化原因是“如何一次性准备 E1/E2/E6 外部证据”，不同于真实 replay 导出、RAG shadow log 复算和作品集严格门禁本身；新脚本只协调已有构建器，不吸收下游业务逻辑，也不是为了满足体量阈值而机械拆文件。
- 汇总包固定声明 `raw_customer_conversation_read=false`、`raw_rag_shadow_log_read=false`、`real_customer_data_committed=false`、`business_database_read=false`、`external_llm_called=false`、`production_service_changed=false` 和 `readiness_changed=false`。
- 本切片不读取真实客服记录、不读取真实 RAG shadow log、不写业务数据库、不调用外部 LLM、不改变生产热路径、不让 `candidate_ready`、`real_sample_ready`、`shadow_log_ready`、`external_evidence_complete` 或 `portfolio_complete` 变为 true。
- `scripts/check_langchain_ai_layer_production_plan.py` 已把该脚本列为生产增强计划必备 artifact，防止外部证据交接入口从计划中丢失。

P23a 验收：

```powershell
python -m pytest tests\scripts\test_build_langchain_external_evidence_handoff_packet.py tests\scripts\test_check_langchain_ai_layer_production_plan.py -q --tb=short --no-cov
python -m ruff check scripts\build_langchain_external_evidence_handoff_packet.py scripts\check_langchain_ai_layer_production_plan.py tests\scripts\test_build_langchain_external_evidence_handoff_packet.py tests\scripts\test_check_langchain_ai_layer_production_plan.py
python -m ruff format --check scripts\build_langchain_external_evidence_handoff_packet.py scripts\check_langchain_ai_layer_production_plan.py tests\scripts\test_build_langchain_external_evidence_handoff_packet.py tests\scripts\test_check_langchain_ai_layer_production_plan.py
python scripts\build_langchain_external_evidence_handoff_packet.py --summary
python scripts\check_langchain_ai_layer_production_plan.py --summary
```

## 四十二、P23b 外部证据交接动作分类

2026-07-10 已完成 P23a 交接汇总包的可执行性增强：

- `scripts/build_langchain_external_evidence_handoff_packet.py` 在保留 `missing_actions` 兼容字段的同时，新增 `action_groups.local_evidence_refresh_actions`、`action_groups.external_handoff_actions` 和带 owner / human_input_required 的 `action_group_details`。
- 本地刷新动作仅用于提示维护者重新生成当前版本 Agent Eval、RAG shadow、trace 或 release 证据；外部交接动作才需要真实记录持有人、人工审核人或合规流程提供输入。
- 该分类和摘要动作计数只改变交接清单可读性，不读取真实客服记录、不读取真实 RAG shadow log、不访问业务数据库、不调用外部 LLM、不修改生产服务，也不让 `candidate_ready`、`real_sample_ready`、`shadow_log_ready`、`external_evidence_complete` 或 `portfolio_complete` 变为 true。
- 职责评审结论为 `keep_cohesive_with_review`：动作分类是交接汇总包输出合同的一部分，与 P23a 汇总职责高度内聚，拆成单独文件只会制造薄 helper 和跨文件跳转。

P23b 验收：

```powershell
python -m pytest tests\scripts\test_build_langchain_external_evidence_handoff_packet.py -q --tb=short --no-cov
python -m ruff check scripts\build_langchain_external_evidence_handoff_packet.py tests\scripts\test_build_langchain_external_evidence_handoff_packet.py
python -m ruff format --check scripts\build_langchain_external_evidence_handoff_packet.py tests\scripts\test_build_langchain_external_evidence_handoff_packet.py
python scripts\build_langchain_external_evidence_handoff_packet.py --summary
```

## 四十三、P23c 外部证据提交前自检摘要

2026-07-10 已完成 P23 交接汇总包的提交前自检摘要增强：

- `scripts/build_langchain_external_evidence_handoff_packet.py` 顶层新增 `pre_submission_checklist_summary`，聚合 P17b 真实 replay 和 P19c RAG shadow log 的提交前自检项。
- 摘要按 `real_replay`、`rag_shadow_log` 来源列出 `item_count`、`owners`、`item_ids` 和原始 items，并输出 `total_items`、`human_input_required_items` 与 `automation_safe_items`，避免把可由仓库维护者本地确认的动作误说成人工外部输入。
- `--summary` 新增 `precheck_items=10`，让外部记录持有人在一行摘要中看到提交前自检项总数；JSON 内继续区分需要外部人工输入的 9 项和可由仓库维护者本地确认的 1 项。
- 职责评审结论为 `keep_cohesive_with_review`：该摘要是 P23 外部证据交接汇总包的展示层合同，复用子包 checklist，不吸收 replay 导出、RAG shadow log 复算或作品集严格门禁逻辑；若拆出独立文件会增加薄 helper 和状态跳转成本。
- 本切片只提升交接清单可读性，不读取真实客服记录、不读取真实 RAG shadow log、不访问业务数据库、不调用外部 LLM、不修改生产服务，也不让任何外部 readiness 变为 true。

P23c 验收：

```powershell
python -m pytest tests\scripts\test_build_langchain_external_evidence_handoff_packet.py -q --tb=short --no-cov
python -m ruff check scripts\build_langchain_external_evidence_handoff_packet.py tests\scripts\test_build_langchain_external_evidence_handoff_packet.py
python -m ruff format --check scripts\build_langchain_external_evidence_handoff_packet.py tests\scripts\test_build_langchain_external_evidence_handoff_packet.py
python scripts\build_langchain_external_evidence_handoff_packet.py --summary
```

## 四十四、P23d 外部证据交接合同静态门禁

2026-07-10 已完成 P23 交接合同的计划层防回退门禁：

- `scripts/check_langchain_ai_layer_production_plan.py` 新增 `REQUIRED_EXTERNAL_HANDOFF_CONTRACTS`，要求生产增强计划继续包含 `action_groups`、`action_group_details`、`pre_submission_checklist_summary` 和 `precheck_items=10`。
- 该门禁只检查计划文本中的交接合同描述，不执行交接包生成器、不访问生产、不读取业务数据库、不调用外部 LLM，保持计划检查器的轻量静态验收定位。
- 职责评审结论为 `keep_cohesive_with_review`：外部交接合同检查属于生产增强计划静态验收，与既有 status / artifact / boundary / stale phrase 检查同一职责；拆成独立脚本会制造薄 wrapper 和额外维护点。
- 本切片只防止 P23b/P23c 的交接合同从计划中回退，不改变任何外部 readiness，也不让 `external_evidence_complete` 或 `portfolio_complete` 变为 true。

P23d 验收：

```powershell
python -m pytest tests\scripts\test_check_langchain_ai_layer_production_plan.py -q --tb=short --no-cov
python -m ruff check scripts\check_langchain_ai_layer_production_plan.py tests\scripts\test_check_langchain_ai_layer_production_plan.py
python -m ruff format --check scripts\check_langchain_ai_layer_production_plan.py tests\scripts\test_check_langchain_ai_layer_production_plan.py
python scripts\check_langchain_ai_layer_production_plan.py --summary
```

## 四十五、P23e 外部证据 readiness 真值汇总

2026-07-10 已完成 P23 外部证据交接汇总包的 readiness 真值增强：

- `scripts/build_langchain_external_evidence_handoff_packet.py` 顶层新增 `readiness_truth`，集中输出 `candidate_ready`、`real_sample_ready`、`shadow_log_ready`、`external_evidence_complete` 和 `portfolio_complete`。
- `readiness_truth.stage_readiness` 保留 E1-E5 的 `ready/action` 快照；`false_readiness_reasons` 同时列出顶层 false readiness 与未完成阶段动作，避免阅读者在多个子包之间跳转后误判完整态。
- `readiness_truth.readiness_changed=false` 明确该摘要只复述当前真值，不引入新的完成判定，也不把缺失外部证据视为 ready。
- 职责评审结论为 `keep_cohesive_with_review`：readiness 真值汇总属于 P23 外部证据交接汇总包展示合同，复用已有真实 replay、RAG shadow log 和 portfolio readiness，不吸收下游评估逻辑，不为体量阈值机械拆分。
- 本切片不读取真实客服记录、不读取真实 RAG shadow log、不访问业务数据库、不调用外部 LLM、不修改生产服务，也不让任何外部 readiness 变为 true。

P23e 验收：

```powershell
python -m pytest tests\scripts\test_build_langchain_external_evidence_handoff_packet.py -q --tb=short --no-cov
python -m ruff check scripts\build_langchain_external_evidence_handoff_packet.py tests\scripts\test_build_langchain_external_evidence_handoff_packet.py
python -m ruff format --check scripts\build_langchain_external_evidence_handoff_packet.py tests\scripts\test_build_langchain_external_evidence_handoff_packet.py
python scripts\build_langchain_external_evidence_handoff_packet.py --summary
```

## 四十六、P23f Markdown 外部证据交接包

2026-07-10 已完成 P23 外部证据交接汇总包的可发送 Markdown 导出增强：

- `scripts/build_langchain_external_evidence_handoff_packet.py` 新增 `--markdown-out`，可在继续写出 JSON 汇总包的同时生成 `LangChain 外部证据交接包` Markdown 文档。
- Markdown 文档面向外部记录持有人、脱敏审核人和仓库维护者，集中展示 readiness 真值、待办动作分组、P17b/P19c 提交前自检摘要、真实 replay/RAG shadow log 交接命令、边界声明和下一道完整性门禁。
- `scripts/check_langchain_ai_layer_production_plan.py` 已把 `--markdown-out` 和 `LangChain 外部证据交接包` 纳入外部交接合同静态门禁，防止可发送交接物能力从计划中回退。
- 职责评审结论为 `keep_cohesive_with_review`：Markdown 导出是 P23 外部证据交接汇总包的展示格式，与 JSON 汇总、动作分组、自检摘要和 readiness 真值属于同一交接职责；拆成独立脚本会造成薄封装和重复字段映射。
- 本切片不读取真实客服记录、不读取真实 RAG shadow log、不访问业务数据库、不调用外部 LLM、不修改生产服务，也不让任何外部 readiness 变为 true。

P23f 验收：

```powershell
python -m pytest tests\scripts\test_build_langchain_external_evidence_handoff_packet.py tests\scripts\test_check_langchain_ai_layer_production_plan.py -q --tb=short --no-cov
python -m ruff check scripts\build_langchain_external_evidence_handoff_packet.py scripts\check_langchain_ai_layer_production_plan.py tests\scripts\test_build_langchain_external_evidence_handoff_packet.py tests\scripts\test_check_langchain_ai_layer_production_plan.py
python -m ruff format --check scripts\build_langchain_external_evidence_handoff_packet.py scripts\check_langchain_ai_layer_production_plan.py tests\scripts\test_build_langchain_external_evidence_handoff_packet.py tests\scripts\test_check_langchain_ai_layer_production_plan.py
python scripts\build_langchain_external_evidence_handoff_packet.py --markdown-out reports\harness\langchain-external-evidence-handoff.md --summary
python scripts\check_langchain_ai_layer_production_plan.py --summary
```

## 五、推荐执行顺序

推荐顺序如下：

```text
P0 生产上线验证闭环
  -> P1 线上 Trace 与 LangSmith 观测
  -> P2 真实业务 Eval 数据集扩容
  -> P3 RAG 热路径灰度增强
  -> P4 事实敏感场景治理增强
  -> P5 作品集证据包
```

理由：

1. 先证明能在线上跑，再继续增强。
2. 先有 trace，后面才能解释线上问题。
3. 先有真实 eval，再灰度 RAG 高级能力。
4. 先治理事实敏感场景，再包装作品集，避免只有表面材料。

## 六、验收矩阵

| 阶段 | 最低验收 | 加强验收 | 是否改热路径 |
|---|---|---|---|
| P0 | `/health`、`/ready`、callback probe | 客户 RAG 与员工助手正向探针 | 否 |
| P1 | trace 报告可生成 | LangSmith 可选接入且不影响主流程 | 低风险 |
| P2 | eval cases 扩容并可定位失败 | report 支持 JSON 归档和 case filter | 否 |
| P3 | shadow compare 可运行 | planned/rerank 灰度优于稳定模式 | 是，需 feature flag |
| P4 | 敏感场景断言通过 | 每类场景至少 5 个真实脱敏 cases | 是，需回滚策略 |
| P5 | 作品集文档完整 | 有生产证据、eval 证据和架构图 | 否 |

## 七、风险与控制

| 风险 | 控制方式 |
|---|---|
| LangChain / LangSmith 依赖增加生产内存压力 | 继续保持懒加载；每次生产前运行 capacity probe |
| RAG 高级模式影响线上回复 | 默认关闭；先 shadow compare，再灰度 |
| Eval 样本过少导致虚高 | 引入真实脱敏问题，按业务场景扩容 |
| Trace 泄露敏感信息 | 统一脱敏字段；报告默认不输出手机号、地址、open_id |
| 作品集只像包装 | 每个亮点必须对应代码路径和验收命令 |

## 八、每阶段收口格式

每个阶段完成后按固定格式追加到 LOGBOOK：

```text
## [日期] - feat/docs/ops(...): 阶段名称
- trace_id:
- 背景:
- 决策:
- 改动:
- 验证结果:
- 证据路径:
- 后续:
```

需要生产证据时，同时登记到：

```text
docs/harness-engineering/core/evidence-index.md
```

## 九、下一步建议

下一步建议进入 P17b：

```text
目标：接入首批真实脱敏客服会话 replay 样本，让真实样本准备度从 real_sample_ready=false 推进到 strict gate 可通过。
```

P14c 已通过生产 runtime gate、显式生产 release gate、P13b 发布证据门禁和 P14 handoff。后续不再围绕生产版本漂移收口，而是推进真实脱敏样本和线上观测：真实样本应替换或补充当前合成覆盖样例；LangSmith 线上外发仍需先确认合规、采样率和容量影响。

## 十、P0 落地记录

2026-07-09 已完成 P0 生产上线验证闭环首轮：

- 本地 commit `0fa3f18431c30620b58cd3e0e48251aa32b72a52` 已推送到 `origin/master` 和 `server/master`。
- 生产服务器 `/opt/yunxibakebot` 已位于 `0fa3f18431 fix: stabilize employee callback stock probes`。
- `systemctl restart yunxibakebot` 后服务为 `active`。
- `https://yunxifood.cn/health` 返回 `status=ok, version=0.85.2`。
- `https://yunxifood.cn/ready` 返回 `status=ready, version=0.85.2`，企微、智能机器人、handoff staff、后台前端和数据库等 readiness 检查均为 true。
- `python scripts/check_wecom_employee_agent_callback.py --base-url https://yunxifood.cn --json --output reports/wecom-employee-agent/langchain-prod-callback-20260709-2210.json` 通过，48 项失败 0。
- 首次 callback 失败集中在商品库存语义探针：生产实时库存已从本地固定样本变化，且 `招牌牛奶吐司` 在生产已下架。已将探针从固定库存数字 `72` 调整为动态库存治理口径，并允许“在售零库存”和“已下架未命中”两种安全结果。

P0 后续：

- 当前 P0 已证明生产运行版本和员工助手回调探针通过。
- 下一阶段应进入 P1：线上 Trace 与 LangSmith 观测。

## 十一、P1a 落地记录

2026-07-09 已完成 P1 线上 Trace 与 LangSmith 观测的第一切片：

- 新增 `app/service/agents/trace_report.py`，把本地 `trace_events` 聚合为双机器人 Agent trace 报告，统计 agent、node、event、fallback、tool call、knowledge hit 和平均耗时。
- 扩展 `app/service/agents/observability.py`，新增递归脱敏函数 `safe_trace_payload()`，统一过滤 `open_id`、`phone`、`mobile`、`address`、token、密钥、消息原文、历史记录、客户画像和工具结果等敏感字段。
- 新增 `scripts/report_agent_traces.py`，支持 `--input` 读取指定 trace JSON、`--latest` 读取 `reports/agent-traces/` 最新 JSON、`--summary` 和 `--json` 两种输出。
- 新增 `tests/service/agents/test_trace_report.py` 和 `tests/scripts/test_report_agent_traces.py`，覆盖客户机器人和员工助手双 agent 摘要、fallback 计数、工具调用计数、RAG 命中计数、敏感字段脱敏和 CLI 输出。
- 本切片不改客户/员工 graph 热路径，不写业务表，不引入 LangSmith 外发，不导入 `langchain_openai`、`langgraph` 或 `langsmith`。

P1a 验收：

```powershell
python -m pytest tests/service/agents/test_observability.py tests/service/agents/test_trace_report.py tests/scripts/test_report_agent_traces.py -q --no-cov
python -m ruff check app/service/agents/observability.py app/service/agents/trace_report.py scripts/report_agent_traces.py tests/service/agents/test_observability.py tests/service/agents/test_trace_report.py tests/scripts/test_report_agent_traces.py
python -m ruff format --check app/service/agents/observability.py app/service/agents/trace_report.py scripts/report_agent_traces.py tests/service/agents/test_observability.py tests/service/agents/test_trace_report.py tests/scripts/test_report_agent_traces.py
python scripts/report_agent_traces.py --latest --summary
```

P1a 验证结果：

```text
18 项 targeted tests 通过。
Ruff check 通过。
Ruff format --check 通过。
当前本地 reports/agent-traces/ 暂无 trace JSON 时，脚本稳定输出：agent_traces status=no_traces total_runs=0 agents=0。
```

P1 后续：

- P1b 应把真实 graph 运行后的 `trace_events` 显式导出为可序列化的 `AgentTraceRun`，使 eval、运维脚本或手动探针可以安全写入 `reports/agent-traces/`。
- P1c 再补客户和员工节点字段完整度：`trace_id`、`model`、`tool_name`、`knowledge_entry_ids`、`latency_ms`、`fallback_reason`。
- LangSmith 仍保持可选开关，未配置 key 时不得影响主流程。

## 十二、P1b 落地记录

2026-07-09 已完成 P1 线上 Trace 与 LangSmith 观测的第二切片：

- `CustomerAgentGraphService` 新增 `answer_with_trace()`，返回 `(reply, AgentTraceRun)`；原 `answer()` 保持只返回字符串，外部调用方行为不变。
- `EmployeeAgentGraphService` 新增 `answer_with_trace()`，返回 `(reply, AgentTraceRun)`；原 `answer()` 保持只返回确定性回复。
- `AgentTraceRun` 新增 `to_dict()`，序列化时自动通过 `safe_trace_payload()` 过滤敏感字段，后续 eval 或运维探针可直接写入 JSON。
- 客户 trace run 写入 `agent=customer`、`conversation_id=session.id`、`channel=session.channel`、`final_status` 和节点事件。
- 员工 trace run 写入 `agent=employee`、`channel=wecom_employee`、`final_status` 和节点事件。
- 本切片不默认写 `reports/agent-traces/`，避免生产热路径每条消息产生文件；真实落盘应由显式探针、eval 或后续结构化日志配置触发。

P1b 验收：

```powershell
python -m pytest tests/service/agents/test_customer_graph.py tests/service/agents/test_employee_graph.py tests/service/agents/test_trace_report.py tests/scripts/test_report_agent_traces.py tests/service/agents/test_observability.py -q --no-cov
python -m ruff check app/service/agents/customer/service.py app/service/agents/employee/service.py app/service/agents/trace_report.py app/service/agents/observability.py scripts/report_agent_traces.py tests/service/agents/test_customer_graph.py tests/service/agents/test_employee_graph.py tests/service/agents/test_trace_report.py tests/scripts/test_report_agent_traces.py tests/service/agents/test_observability.py
python -m ruff format --check app/service/agents/customer/service.py app/service/agents/employee/service.py app/service/agents/trace_report.py app/service/agents/observability.py scripts/report_agent_traces.py tests/service/agents/test_customer_graph.py tests/service/agents/test_employee_graph.py tests/service/agents/test_trace_report.py tests/scripts/test_report_agent_traces.py tests/service/agents/test_observability.py
```

P1b 验证结果：

```text
33 项 targeted tests 通过。
Ruff check 通过。
Ruff format --check 通过。
```

P1 后续：

- P1d 再决定是否增加显式探针脚本，把一次客户机器人和一次员工助手运行写入 `reports/agent-traces/` 后用 `scripts/report_agent_traces.py --latest --summary` 汇总。

## 十三、P1c 落地记录

2026-07-09 已完成 P1 线上 Trace 与 LangSmith 观测的第三切片：

- 客户模型 adapter 的 `CustomerModelResult` 新增 `model_name`，模型节点 trace 可记录实际使用模型。
- 客户 `load_session_context` trace 新增 `latency_ms`、`knowledge_entry_ids`、`knowledge_hit_count`，字段来自 RAG 上下文构造结果，不包含知识正文或用户原文。
- 客户 `model_with_tools` trace 新增 `model`、`latency_ms`、`tool_call_count`，fallback 时额外记录 `fallback_reason`。
- 客户 `execute_tools` trace 新增 `tool_name`、`tool_names`、`tool_call_count`。
- 员工 `select_tools` 和 `execute_tools` trace 新增 `tool_name`、`tool_call_count`，`deterministic_finalizer` trace 新增 `final_status=success`。
- `ChatContext` 新增 `knowledge_entry_ids`，只把知识 ID 写入 timing，不把知识正文、客户画像或历史消息写入 trace。

P1c 验收：

```powershell
python -m pytest tests/service/agents/test_customer_model.py tests/service/agents/test_customer_graph.py tests/service/agents/test_employee_graph.py tests/service/agents/test_trace_report.py tests/service/test_chat_refactor.py -q --no-cov
python -m ruff check app/service/agents/customer/model.py app/service/chat_context.py app/service/agents/customer/nodes.py app/service/agents/employee/nodes.py tests/service/agents/test_customer_model.py tests/service/agents/test_customer_graph.py tests/service/agents/test_employee_graph.py
python -m ruff format --check app/service/agents/customer/model.py app/service/chat_context.py app/service/agents/customer/nodes.py app/service/agents/employee/nodes.py tests/service/agents/test_customer_model.py tests/service/agents/test_customer_graph.py tests/service/agents/test_employee_graph.py
```

P1c 验证结果：

```text
46 项 targeted tests 通过。
Ruff check 通过。
Ruff format --check 通过。
```

P1 后续：

- P1e 若需要线上 LangSmith，单独处理环境变量注入和生产容量探针，仍保持缺 key 不影响主流程。

## 十四、P1d 落地记录

2026-07-09 已完成 P1 线上 Trace 与 LangSmith 观测的第四切片：

- 新增 `scripts/probe_agent_traces.py`，使用受控 fake 依赖运行一次客户机器人 graph 和一次员工助手 graph，不访问真实数据库、不调用外部 LLM、不发送企微消息。
- probe 通过 `answer_with_trace()` 收集 `AgentTraceRun`，写入 `reports/agent-traces/agent-traces-{timestamp}.json`。
- `scripts/report_agent_traces.py --latest --summary` 现在可以读取最新 probe 输出，并展示客户机器人和员工助手节点级摘要。
- 新增 `tests/scripts/test_probe_agent_traces.py`，覆盖 probe 输出 JSON 结构和 report 脚本读取链路。

P1d 验收：

```powershell
python -m pytest tests/scripts/test_probe_agent_traces.py tests/scripts/test_report_agent_traces.py -q --no-cov
python -m ruff check scripts/probe_agent_traces.py tests/scripts/test_probe_agent_traces.py scripts/report_agent_traces.py tests/scripts/test_report_agent_traces.py
python -m ruff format --check scripts/probe_agent_traces.py tests/scripts/test_probe_agent_traces.py scripts/report_agent_traces.py tests/scripts/test_report_agent_traces.py
python scripts/probe_agent_traces.py
python scripts/report_agent_traces.py --latest --summary
python scripts/report_agent_traces.py --latest --json
```

P1d 验证结果：

```text
5 项 targeted tests 通过。
Ruff check 通过。
Ruff format --check 通过。
probe 输出 reports/agent-traces/agent-traces-20260709-224837.json。
summary 输出：agent_traces status=ok total_runs=2 agents=2。
json 输出包含 customer 4 个节点、employee 7 个节点，未包含敏感明文字段。
```

P1 当前状态：

- P1 的本地 trace 报告、显式 trace 导出、节点字段补齐和本地 probe 闭环已完成。
- LangSmith 仍是可选配置能力，当前未做生产环境变量注入和外发验证；这部分应在需要线上 LangSmith 时单独做容量探针和生产配置确认。
