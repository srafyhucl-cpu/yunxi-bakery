# 项目快速参考

> 以下命令默认从 Monorepo 根目录执行；后端代码、测试、数据和脚本统一使用 `backend/` 前缀。

______________________________________________________________________

## 关键路径速查

| 需求 | 文件 |
|------|------|
| AI 对话入口 | `backend/app/service/chat.py` |
| System Prompt 构建 | `backend/app/service/llm/prompt.py` |
| 客户 LangGraph 编排 | `backend/app/service/agents/customer/graph.py` |
| 客户 LangChain 工具 | `backend/app/service/agents/tools/customer.py` |
| 客户 OpenAI tool 消息 | `backend/app/service/agents/customer/tool_messages.py` |
| 客户 LangChain 模型适配 | `backend/app/service/agents/customer/model.py` |
| LangChain 聊天模型工厂 | `backend/app/service/agents/llm.py` |
| LangChain RAG Retriever adapter | `backend/app/service/agents/rag/retriever.py` |
| RAG query plan / rerank | `backend/app/service/agents/rag/query.py`、`backend/app/service/agents/rag/rerank.py` |
| 员工 LangGraph 编排 | `backend/app/service/agents/employee/graph.py` |
| 员工 structured planner | `backend/app/service/agents/employee/structured_planner.py` |
| Agent Eval 模型 | `backend/app/service/agents/evaluation.py` |
| 意图识别 | `backend/app/service/llm/intent.py` |
| RAG 检索 | `backend/app/service/knowledge_retriever.py` |
| 向量搜索 | `backend/app/service/embedding_search.py` |
| 有赞 Webhook 入口 | `backend/app/api/integrations/youzan_webhook.py` |
| 有赞事件分发 | `backend/app/service/youzan/event_handler.py` |
| 管理后台路由 | `backend/app/api/admin/root.py` |
| 新后台前端入口 | `backend/app/api/admin/frontend.py` |
| 新后台前端工程 | `backend/web/admin/` |
| 知识配置后台 | `backend/app/api/admin/knowledge.py` |
| 数据观察台后台 | `backend/app/api/admin/observability.py` |
| 数据库初始化 | `backend/app/database.py` |
| 商品实时刷新 | `backend/app/service/llm/function_tool_product_live.py` |
| 版本号（唯一来源） | `backend/VERSION` |
| 版本同步门禁 | `backend/scripts/sync_version.py` |
| LOGBOOK 自动追加 | `backend/scripts/append_logbook.py` |
| 企业微信告警 | `backend/app/service/alerting.py` |

---

## 测试与部署速查

```bash
# 全量测试
python -m pytest backend/tests/ -q

# 双机器人离线 Agent Eval
python backend/scripts/eval_customer_agent.py --summary
python backend/scripts/eval_employee_agent.py --summary
python backend/scripts/report_agent_eval.py --latest

# RAG Advanced 检索评测矩阵
python backend/scripts/report_retrieval_eval_matrix.py --db backend/data/bot.db --fixture backend/tests/fixtures/customer_rag_golden_cases.json --k 5

# 仅跑红线规则自测
python -m pytest backend/tests/test_red_line_rules.py -q --tb=short

# 生产同构、数据隔离的主体删除与消息崩溃整改 Harness
python backend/scripts/run_isolated_remediation_harness.py --work-dir D:\Temp\yunxi-remediation-harness --json

# 生产真实 API 合成主体删除专项（仅在生产主机 loopback 执行）
venv/bin/python /opt/apps/yunxibakebot/scripts/verify_production_subject_deletion.py --db /opt/apps/yunxibakebot/data/bot.db --base-url http://127.0.0.1:7001 --confirm-production-synthetic-subject --json

# 生产真实 InboxRepo 合成消息崩溃恢复专项（专用队列，不触发渠道发送）
venv/bin/python /opt/apps/yunxibakebot/scripts/verify_production_synthetic_inbox_crash.py --db /opt/apps/yunxibakebot/data/bot.db --confirm-production-synthetic-inbox-crash --json

# 完整隐私出站合同（本地静态/合成检查）
python backend/scripts/check_privacy_outbound_contract.py --summary

# 完整隐私出站合同（额外核验生产布尔开关，不输出密钥）
python backend/scripts/check_privacy_outbound_contract.py --production-runtime --ssh-key $env:USERPROFILE\.ssh\id_ed25519 --summary

# R3-B 下载与员工授权合同
python backend/scripts/check_security_outbound_contract.py --summary
python backend/scripts/check_security_outbound_contract.py --production-runtime --ssh-key $env:USERPROFILE\.ssh\id_ed25519 --summary

# 立即创建一份本地 D 盘生产加密备份
python backend/scripts/local_production_backup.py --backup-dir D:\Backups\YunxiBakeBot --key-file D:\Backups\YunxiBakeBot\keys\backup.key --ssh-key $env:USERPROFILE\.ssh\id_ed25519

# 安装或刷新每天 03:30 的 Windows 本地备份任务
.\backend\scripts\install_local_backup_task.ps1

# 本地启动
python -m uvicorn --app-dir backend app.main:app --host 127.0.0.1 --port 7001 --reload

# 健康检查
curl http://127.0.0.1:7001/health  # version 应与 Get-Content backend/VERSION 一致

# 知识种子导入（仅 FAQ / 规则 / 话术）
python backend/scripts/seed_baseline_knowledge.py
python backend/scripts/seed_baseline_knowledge.py --apply

# 远程服务状态与后端健康检查
ssh root@47.94.102.250 "cd /opt/apps/yunxibakebot && systemctl is-active yunxibakebot"
curl https://yunxifood.cn/health

# 代码发布：SSH Git Bundle 传输、服务器端合入并重启服务
bash backend/scripts/deploy.sh
```

---

## 架构分层

```
api/ → service/ → repository/ → models/
```

- `api/`：HTTP 路由层（FastAPI Router），接收请求、返回响应
- `service/`：业务逻辑层，编排 repository 和外部服务调用
- `repository/`：数据访问层，封装 SQL 操作和数据持久化
- `models/`：数据模型层，纯 Pydantic 模型，不依赖任何上层模块

禁止任何层级向上穿透调用。

---

## Harness 运行口径

- 当前进度只读 `PROJECT-STATE.md` 的机器快照和主线任务总表；最小阅读集为 `AGENTS.md` + `PROJECT-STATE.md`，具体任务再读对应任务指令。
- 开发总表守卫：`python -B backend/scripts/check_project_development_register.py`；项目总守卫 `python -B backend/scripts/check_project.py --skip-tests` 已包含该检查。

- 中大型任务先分配 `trace_id`，再按 `docs/harness-engineering/core/verification-matrix.md` 选验证。
- 并行任务先读 `docs/AGENTS/multi-agent-coordination.md`，统一 `PROJECT-STATE.md`、`backend/VERSION`、当前 Git HEAD 和任务路径边界。
- 需要交接时优先用 `backend/scripts/harness_snapshot.py`，不要只留聊天记录。
- 需要长期记忆的错误先写 `docs/harness-engineering/core/mistake-ledger.md`，再补测试、脚本、pre-commit、AGENTS 或 Skill 中至少一类防线。
- 清理本机临时产物先预览：`.\scripts\cleanup-local-artifacts.ps1`；只有负责人明确授权时才使用 `-Execute`。脚本兼容 Windows PowerShell 5.1，并覆盖根目录、backend、miniapp 和 scripts 下的可重建缓存；质量门禁临时文件固定写入 D 盘一次性目录。

---

## 工作流入口

| 场景 | 工作流 |
|------|-------|
| 全流程收口检查 | `/check` |
| 代码 Review | `/review` |
| 代码驱动文档同步 | `/sync-docs` |
| 提交 | `/commit` |
| Skill 同步更新 | `/sync-skills` |
