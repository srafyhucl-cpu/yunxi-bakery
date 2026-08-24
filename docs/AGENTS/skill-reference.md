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
| 防重犯账本 | [docs/harness-engineering/core/mistake-ledger.md](../harness-engineering/core/mistake-ledger.md) |
| 证据索引 | [docs/harness-engineering/core/evidence-index.md](../harness-engineering/core/evidence-index.md) |
| 中文乱码处理 | [docs/AGENTS/encoding-and-terminal.md](encoding-and-terminal.md) |

---

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
- 证据、复盘和长期记忆分别落到 `core/evidence-index.md`、`LOGBOOK.md`、`core/mistake-ledger.md`。
