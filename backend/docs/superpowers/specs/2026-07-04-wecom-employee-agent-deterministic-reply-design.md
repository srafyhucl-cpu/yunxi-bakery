# 企微员工助手确定性回复收口设计

- trace_id: 20260704-wecom-employee-agent-deterministic-reply
- source: 用户要求按 `docs/architecture/wecom-employee-agent-development-plan.md` 收口当前已跑偏的员工助手实现，并确认采用方案 A
- goal: 去掉员工助手回复期 LLM 润色，统一改为确定性回复直出，删除事实保真 guard 主链路与对应死代码
- decision_refs:
  - `docs/architecture/wecom-employee-agent-development-plan.md`
  - `docs/architecture/wecom-intelligent-bot-tools.md`
- changed_files:
  - `app/service/wecom/employee_agent_service.py`
  - `app/service/wecom/employee_agent_reply_guard.py`
  - `app/service/wecom/employee_agent_order_list_guard.py`
  - `tests/service/test_wecom_employee_agent.py`
  - `tests/service/test_wecom_employee_privacy_format.py`
  - `docs/architecture/wecom-intelligent-bot-tools.md`
  - `docs/harness-engineering/core/evidence-index.md`
  - `LOGBOOK.md`
  - `项目进度与配置清单.md`
- verification:
  - `python -m pytest tests/service/test_wecom_employee_agent.py tests/service/test_wecom_employee_privacy_format.py -q --no-cov`
  - `python -m pytest tests/service/test_wecom_employee_agent.py tests/scripts/test_check_wecom_employee_agent_callback.py tests/api/test_wecom_intelligent_bot_plugin_api.py -o addopts="" --no-cov`
  - `python scripts/check_wecom_employee_agent_plans.py --json`
  - `python -m pytest tests/ -q`
  - `python -m ruff check app/service/wecom/employee_agent_service.py tests/service/test_wecom_employee_agent.py tests/scripts/test_check_wecom_employee_agent_callback.py tests/api/test_wecom_intelligent_bot_plugin_api.py`
  - `python -m ruff format --check app/service/wecom/employee_agent_service.py tests/service/test_wecom_employee_agent.py tests/scripts/test_check_wecom_employee_agent_callback.py tests/api/test_wecom_intelligent_bot_plugin_api.py`
  - `python scripts/check_file_sizes.py`
  - `python scripts/check_project.py --skip-tests`
  - `python scripts/check_text_encoding.py`
  - `python scripts/check_mistake_ledger.py`
  - `rg "from app\.repository" app/api -g "*.py"`
  - `rg "import aiosqlite|\.execute\(|\.fetchone\(|\.fetchall\(" app/service -g "*.py"`
  - `rg "from app\.(service|repository|api)" app/models -g "*.py"`
  - `git diff --check`
- evidence:
  - `LOGBOOK.md` 顶部条目
  - 生产 `/health`：`status=ok,version=0.74.32`
  - 生产 `/ready`：`status=ready,version=0.74.32`，企微智能机器人回调配置检查通过
  - 45 问加密回调探针报告：`reports/wecom-employee-agent/callback-20260705-151936.json`，`status=passed,total=45,failed=0,app_version=0.74.32`
- residual_risks:
  - 已收口：生产 `/health`、`/ready` 和 45 问回调探针均已在 `0.74.32` 同步后补证据

## 设计

### 1. 主链路

员工助手回复链路收敛为：

`query -> planner -> execute tools -> deterministic reply -> clean_plain_text_reply -> return`

`EmployeeAgentPlanner` 的 LLM 兜底仅保留在结构化 `AgentPlan` 规划阶段，不再生成员工可见文本。

### 2. 删除范围

- 删除 `EmployeeAgentService` 中回复期的 `llm_chat` 调用和 `_polish_reply` 方法。
- 删除 `employee_agent_reply_guard.py`，因为它只服务于“润色后回退”的旧链路。
- 删除 `employee_agent_order_list_guard.py`，因为它只被 reply guard 引用。

### 3. 测试策略

- 删除 `test_preserve_tool_facts_*` 和 `test_employee_agent_polish_*` 系列测试。
- 保留并补充员工助手服务测试，直接断言确定性输出中的关键事实仍然存在：
  - 无库存保护语
  - 商品未命中不等于缺货
  - 客户可复制回复
  - 发货压力/优先级
  - 履约风险列表与已过约送时间
  - 普通待发货列表结构
  - 销量并列提示

### 4. 文档收口

- 更新 `wecom-intelligent-bot-tools.md`，明确员工助手回复文本已改为确定性直出。
- 更新 `LOGBOOK.md` 和 `项目进度与配置清单.md`，把“继续补 guard”的方向收口为“移除回复期润色”。

## 自检

- 无 TBD / TODO / 占位字段
- 设计只覆盖员工助手回复期，不触碰客户客服链路
- 结构化规划 LLM 保留、回复期 LLM 删除，边界明确
