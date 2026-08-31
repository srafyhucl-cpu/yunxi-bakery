# Skill 调用速查

______________________________________________________________________

## 项目 Guard Skill（修改代码前必须调用）

| 场景 | 调用命令 |
|------|---------|
| 较大任务 / 追溯 / 复盘 / 证据留档 / Skill 更新 | `skill invoke yunxi-harness-engineering` |
| 修改任意分层代码 | `skill invoke yunxi-architecture-guard` |
| 修改 LLM/Prompt/意图 | `skill invoke yunxi-llm-guard` |
| 新增/修改 `.py` 文件 | `skill invoke yunxi-file-size-guard`，用体量信号触发职责评审 |
| 代码审查/发现质量问题 | `skill invoke yunxi-clean-code-guard` |

> ⚠️ **不允许跳过**：即使任务看起来很小，只要涉及上表中的文件范围，就必须先调用 Skill。

文件体量守卫的目标是防止上帝类，不是要求所有文件低于固定行数。超线后先判断职责、变化原因、依赖和测试边界：职责混杂才拆；高度内聚则记录评审理由后保留。禁止为了让门禁变绿机械切文件。长期决策见 [ADR 0004](../harness-engineering/adr/0004-responsibility-first-file-size-governance.md)。

---

## 全局 Skill（按场景引入）

| 场景 | Skill | 说明 |
|------|-------|------|
| **新功能 / 新需求设计** | `brainstorming` | 探索需求、提 2-3 方案、用户确认后再实现；禁止跳过 |
| **查阅外部 API 文档**（有赞、DeepSeek、微信） | `defuddle` | 清洁提取网页正文，去噪省 token，替代 WebFetch |
| **创建或改进 Guard Skill** | `skill-creator` | 草稿 → 测试 → 迭代，优化 description 触发精度 |
| **YunxiBakeBot 生产推送/发布** | `yunxibakebot-production-release` | 双远端推送后执行 Git Bundle 发布、systemd 和 HTTP 验证 |
| **向飞书发送开发通知**（部署结果、生产告警） | `lark-im` | 推送消息到开发群或个人 |
| **Skill 发现习惯建立** | `using-superpowers` | 任务开始前查找可用 skill 的元协议 |

---

## Harness Skill 与记忆落点

| 场景 | 统一入口 |
|------|---------|
| Harness 文档导航 | [docs/harness-engineering/README.md](../harness-engineering/README.md) |
| 任务追溯字段 | [docs/harness-engineering/core/traceability-model.md](../harness-engineering/core/traceability-model.md) |
| 验证选择 | [docs/harness-engineering/core/verification-matrix.md](../harness-engineering/core/verification-matrix.md) |
| 防重犯账本 | [ERRORS.md](../../ERRORS.md) |
| 证据索引 | [docs/harness-engineering/core/evidence-index.md](../harness-engineering/core/evidence-index.md) |
| 中文乱码处理 | [docs/AGENTS/encoding-and-terminal.md](encoding-and-terminal.md) |

---

## 中文优先与单一进度入口

- 当前进度、任务状态、主线/分支和阻塞只维护在 `PROJECT-STATE.md`；不要在新文档中另起动态进度表。
- 最小阅读集：`AGENTS.md` + `PROJECT-STATE.md`；具体任务再读 `docs/tasks/*.md`，专业文档按需读取。
- 新改动先登记 `task_id`，任务指令填写 `status` + `status_label`，收口前运行 `python -B backend/scripts/check_project_development_register.py`。
- 中文状态统一显示为“中文状态（机器码）”；禁止在中文叙述中裸写 `active`、`blocked`、`completed`、`pending`、`deferred`、`historical`。
- 中文治理属于 Harness P0 控制面：权威状态、责任、阻塞、证据、交接和高风险用户可见路径必须先提供中文人类可读说明；英文仅保留稳定机器字段、协议字段和命令原文。
- 当前 P0 任务包括 `T-HARNESS-CHINESE-GOVERNANCE`、`T-HARNESS-RUN-MANIFEST`、`T-HARNESS-POLICY-AS-CODE`、`T-HARNESS-CI-ENTRY`、`T-HARNESS-CLEANUP-POLICY` 和 `T-HARNESS-P0-HARDENING`；全仓注释翻译、低风险文案和历史文档清理属于 P1/P2。
- 当前项目 Harness Skill 版本：`1.2.1`，路径为 `backend/.agents/skills/yunxi-harness-engineering/SKILL.md`。
- P0 统一门禁：`python -B backend/scripts/harness_p0_gate.py --summary`，固定执行依赖锁一致性、中文治理、策略、manifest、开发总表、错误账本、证据、编码和项目红线九项检查；报告模式使用 `--json-out backend/reports/harness/p0-gate.json`，根级 CI 入口为 `.github/workflows/harness-p0.yml`。
- 临时产物清理：先运行 `.\scripts\cleanup-local-artifacts.ps1` 预览；仅对白名单或显式 `.tmp-`/`pytest-` 临时目录，在明确授权并携带预览令牌后使用 `-PreviewToken <令牌> -Execute` 递归批量清理，未知路径和受保护路径仍禁止处理。

Harness 全面评审与外部对标：

- [HARNESS-MATURITY-REVIEW-20260830.md](../harness-engineering/HARNESS-MATURITY-REVIEW-20260830.md)
- 评审结论已同步到 `traceability-model`、`verification-matrix` 和 `multi-agent-coordination`，不新增平行状态入口。

## 工作流

| 场景 | 工作流 |
|------|-------|
| 全流程收口检查 | `/check` |
| 代码 Review | `/review` |
| 提交 | `/commit` |
| Skill 同步更新 | `/sync-skills` |

---

## Harness 运行口径

- 任何较大任务先走 `AGENTS.md` → `docs/harness-engineering/README.md` → `traceability-model`。
- 交接时优先补 `scripts/harness_snapshot.py`，不要把上下文只留在聊天里。
- 证据、复盘和长期记忆分别落到 `core/evidence-index.md`、`LOGBOOK.md`、根目录 `ERRORS.md`。
- 新证据必须绑定当前 Monorepo 提交并声明 `repository_origin: monorepo`；旧仓历史只读核验，不改写原始提交。
