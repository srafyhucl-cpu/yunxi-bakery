# Harness Engineering

本目录是 Bakery Commerce Platform 当前 `Platform` 主仓的 AI 驾驭系统父目录；对应代码仓路径仍为 `YunxiBakeBot`。后续只需要记住一个入口：

```text
docs/harness-engineering/README.md
```

目标不是多写流程，而是让 Vibe Coding 的每次推进都有证据、能交接、能复盘，并且把犯过的错转成下一次会自动提醒或阻断的防线。

当前使用时优先按下面顺序进入：

1. `AGENTS.md`
2. `LOGBOOK.md`
3. `docs/harness-engineering/README.md`
4. `docs/harness-engineering/core/traceability-model.md`
5. `docs/harness-engineering/core/verification-matrix.md`
6. `docs/harness-engineering/core/evidence-index.md`

______________________________________________________________________

## 快速入口

| 场景 | 先看 |
|---|---|
| 开始一个较大任务 | `AGENTS.md`、`LOGBOOK.md` 最新条目、本文件 |
| 需要给任务留追溯 | [core/traceability-model.md](core/traceability-model.md) |
| 不确定该跑哪些验证 | [core/verification-matrix.md](core/verification-matrix.md) |
| AI 或人工犯过一次值得记住的错 | [core/mistake-ledger.md](core/mistake-ledger.md) |
| 上下文要重置或换 Agent | [core/agent-handoff-template.md](core/agent-handoff-template.md) |
| 需要追溯架构决策 | [adr/README.md](adr/README.md) |
| 需要登记上线或交接证据 | [core/evidence-index.md](core/evidence-index.md) |
| 需要确认当前生产目录、静态入口或发布目标 | [../release/server-layout.md](../release/server-layout.md) |
| 需要更新或审计项目 Skill | `.agents/SKILL_AUDIT.md`、`.agents/skills/yunxi-harness-engineering/SKILL.md`、`docs/AGENTS/skill-reference.md` |
| 终端或文件中文乱码 | [../AGENTS/encoding-and-terminal.md](../AGENTS/encoding-and-terminal.md) |
| 了解完整设计 | [specs/2026-06-11-vibe-coding-harness-engineering-design.md](specs/2026-06-11-vibe-coding-harness-engineering-design.md) |
| 想看这次整理前后对比 | [before-after.html](before-after.html) |

______________________________________________________________________

## 目录地图

| 目录 | 放什么 | 读者心智 |
|---|---|---|
| `core/` | 日常运行规则：追溯、验证、防重犯、交接、证据索引 | 每次做事会用到 |
| `adr/` | 长期架构决策记录 | 为什么这么设计 |
| `specs/` | 设计规格和路线图 | 大图和演进计划 |
| `before-after.html` | 本轮整理前后的可视化对比 | 快速理解为什么这样收纳 |

脚本不放进文档目录，仍保留在 `scripts/`：

- `scripts/harness_snapshot.py`：生成交接快照。
- `scripts/check_mistake_ledger.py`：检查防重犯账本结构。
- `scripts/check_evidence_index.py`：检查证据索引结构和关键证据引用。

______________________________________________________________________

## 工作原则

1. 聊天不是记忆，仓库里的规则、测试、脚本、文档和报告才是长期记忆。
2. “我已经提醒过 AI”不是防线；能自动检查、自动测试或自动留档才算防线。
3. 每次上线前后都要能拿出证据链，而不是靠口头确认。
4. 同一类问题第二次出现时，优先修 Harness，而不是只修当次 bug。

______________________________________________________________________

## 标准闭环

```text
需求或故障
→ 分配 trace_id
→ 设计或记录决策
→ 实施变更
→ 按验证矩阵执行检查
→ 保存证据
→ 更新 LOGBOOK
→ 如有失误，写入 mistake ledger 并补防线
→ 必要时输出 handoff
```

______________________________________________________________________

## 现有 Harness 资产

| 资产 | 作用 |
|---|---|
| `AGENTS.md` | AI Agent 启动规范和红线 |
| `docs/AGENTS/` | 编码红线、提交收口、快速参考、skill 速查 |
| `LOGBOOK.md` | 项目演进唯一真实编年史 |
| `项目进度与配置清单.md` | 当前功能状态、生产同步清单和已知风险 |
| `.pre-commit-config.yaml` | 提交前质量门禁 |
| `scripts/check_project.py` | 统一红线扫描 |
| `scripts/preflight_production.py` | 生产同步前只读预检和 recovery plan |
| `scripts/smoke_test.py` | 服务冒烟和 JSON 留档 |
| `scripts/run_isolated_remediation_harness.py` | 用生产同构组件隔离验证主体删除与消息进程崩溃重领 |
| `scripts/local_production_backup.py` | 拉取生产一致快照并在本地 D 盘创建、验证和保留加密备份 |
| `scripts/install_local_backup_task.ps1` | 注册每天运行的 Windows 本地加密备份计划任务 |
| `scripts/check_privacy_outbound_contract.py` | 自动发现模型入口并聚合检查脱敏、trace 和生产外发关闭态 |
| `scripts/check_security_outbound_contract.py` | 聚合检查统一远程下载、SSRF 逐跳策略和员工 Agent 工具授权 |
| `docs/HarnessEngineering评估报告_20260604.md` | 既有 Harness 成熟度评估 |
| `docs/VibeCoding可持续性评估报告_20260604.md` | 既有 Vibe Coding 可持续性评估 |

______________________________________________________________________

## 新增 Harness 资产

| 文件 | 作用 |
|---|---|
| [core/traceability-model.md](core/traceability-model.md) | 统一 trace、证据链和报告字段 |
| [core/verification-matrix.md](core/verification-matrix.md) | 按变更类型选择最低验证和加强验证 |
| [core/mistake-ledger.md](core/mistake-ledger.md) | 记录错误、根因和新增防线 |
| [core/agent-handoff-template.md](core/agent-handoff-template.md) | 长任务续跑和换 Agent 交接模板 |
| [specs/2026-07-12-isolated-remediation-harness-design.md](specs/2026-07-12-isolated-remediation-harness-design.md) | 隔离主体删除与消息崩溃恢复的生产同构设计 |
| [specs/2026-07-12-local-production-backup-job-design.md](specs/2026-07-12-local-production-backup-job-design.md) | 无生产独立磁盘时的本地主动加密备份设计 |
| [specs/2026-07-12-production-privacy-outbound-audit-design.md](specs/2026-07-12-production-privacy-outbound-audit-design.md) | 模型、trace 和生产开关的完整隐私出站审计设计 |
| [specs/2026-07-12-r3b-security-outbound-audit-design.md](specs/2026-07-12-r3b-security-outbound-audit-design.md) | 统一远程下载和员工 Agent 权限的 R3-B 安全出站审计设计 |
| [specs/2026-07-12-production-synthetic-subject-deletion-design.md](specs/2026-07-12-production-synthetic-subject-deletion-design.md) | 使用生产真实 JWT/API 和合成主体安全验证隐私导出删除闭环 |
| [specs/2026-07-12-production-synthetic-inbox-crash-design.md](specs/2026-07-12-production-synthetic-inbox-crash-design.md) | 使用生产真实 InboxRepo 和隔离合成队列验证崩溃后 lease 重领 |
| [specs/2026-07-13-production-container-verification-design.md](specs/2026-07-13-production-container-verification-design.md) | 生产隔离 Docker build、非 root/单 worker smoke、漏洞扫描和资源边界 |
| [core/evidence-index.md](core/evidence-index.md) | 登记上线、交接、预检、冒烟、迁移等证据包索引 |
| [adr/README.md](adr/README.md) | 记录会影响长期演进的架构决策 |

______________________________________________________________________

## P1 机器辅助工具

| 命令 | 作用 |
|---|---|
| `python scripts/harness_snapshot.py` | 生成 Markdown 交接快照，包含 trace、目标、最新 LOGBOOK、工作区状态和参考入口 |
| `python scripts/harness_snapshot.py --json` | 输出机器可读快照，适合归档到 reports |
| `python scripts/harness_snapshot.py --output reports/harness/handoff-{timestamp}.md` | 写入带 UTF-8 BOM 的快照文件，拒绝覆盖已有文件 |
| `python scripts/check_mistake_ledger.py` | 检查 [core/mistake-ledger.md](core/mistake-ledger.md) 是否有合法空账本标记，或每条 mistake 是否字段完整、枚举合法 |
| `python scripts/check_evidence_index.py` | 检查 [core/evidence-index.md](core/evidence-index.md) 的证据条目必填字段、结果枚举、重复 ID、预检业务合约引用和本地证据文件存在性；JSON 报告同时输出本地文件 SHA-256，生产路径保留为外部未验证引用 |
| `.\scripts\enable_utf8_console.ps1` | 修复当前 Windows PowerShell 会话的中文输入输出乱码 |

推荐在长任务交接、上下文重置、上线收口前执行：

```powershell
python scripts/harness_snapshot.py --trace-id 20260611-example --goal "说明当前任务" --status in_progress
python scripts/check_mistake_ledger.py
python scripts/check_evidence_index.py --summary
```

生成需要归档的快照或生产报告后，在 [core/evidence-index.md](core/evidence-index.md) 追加索引条目；影响长期演进的决策写入 [adr/](adr/)。

`check_mistake_ledger.py` 和 `check_evidence_index.py` 已接入 `.pre-commit-config.yaml`，每次提交前都会自动检查防重犯账本和证据索引结构。若账本条目不完整、证据字段缺失或证据 ID 重复，提交会被阻断，直到补齐字段或恢复合法结构。
