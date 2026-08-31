# Harness Engineering

本目录是 Bakery Commerce Platform（YunxiBakery monorepo）的 AI 驾驭系统父目录；后端代码位于同仓 `backend/`，小程序位于同仓 `miniapp/`（2026-08-17 Monorepo 整合，旧仓 YunxiBakeBot 冻结只读）。后续只需要记住一个入口：

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

> 当前进度的最小阅读集是 `AGENTS.md` + `PROJECT-STATE.md`。`PROJECT-STATE.md` 的机器快照、主线任务总表、状态视图和分支登记是唯一动态开发总表；`LOGBOOK.md`、计划书和归档文档只用于历史证据或背景，不得重新定义当前状态。

______________________________________________________________________

## 快速入口

| 场景 | 先看 |
|---|---|
| 开始一个较大任务 | `AGENTS.md`、`LOGBOOK.md` 最新条目、本文件 |
| 需要给任务留追溯 | [core/traceability-model.md](core/traceability-model.md) |
| 不确定该跑哪些验证 | [core/verification-matrix.md](core/verification-matrix.md) |
| AI 或人工犯过一次值得记住的错 | [根目录 ERRORS.md](../../ERRORS.md) |
| 上下文要重置或换 Agent | [core/agent-handoff-template.md](core/agent-handoff-template.md) |
| 需要追溯架构决策 | [adr/README.md](adr/README.md) |
| 需要登记上线或交接证据 | [core/evidence-index.md](core/evidence-index.md) |
| 需要确认当前生产目录、静态入口或发布目标 | [../release/server-layout.md](../release/server-layout.md) |
| 需要更新或审计项目 Skill | `.agents/SKILL_AUDIT.md`、`.agents/skills/yunxi-harness-engineering/SKILL.md`、`docs/AGENTS/skill-reference.md` |
| 查看 Harness 全面评审与外部对标 | [HARNESS-MATURITY-REVIEW-20260830.md](HARNESS-MATURITY-REVIEW-20260830.md) |
| 查看 Harness P0 改进队列 | 评审报告第五节；P0 包含中文治理控制面、运行 manifest/episode、策略即代码、统一 CI 入口和受控临时产物清理 |
| 查看中文治理六维模型 | [core/chinese-governance-model.md](core/chinese-governance-model.md)；机器契约为 [core/chinese-governance.json](core/chinese-governance.json) |
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

脚本不放进文档目录；Monorepo 整合后统一位于 `backend/scripts/`：

- `backend/scripts/harness_snapshot.py`：生成交接快照。
- `scripts/cleanup-local-artifacts.ps1`：预览并在授权后递归批量清理白名单内的临时/可重建本地产物；保护业务数据、有效报告和生产路径。
- `backend/scripts/check_mistake_ledger.py`：检查防重犯账本结构。
- `backend/scripts/check_evidence_index.py`：检查证据索引结构和关键证据引用。
- `backend/scripts/check_project_development_register.py`：校验项目快照、任务总表、状态视图、分支和任务指令元数据。
- `backend/scripts/check_requirements_lock_alignment.py`：校验生产与开发依赖锁的共享包版本一致，并要求开发锁以生产锁为约束。
- `backend/scripts/check_chinese_governance.py`：检查中文权威入口、状态标签和高风险路径可读性。
- `docs/harness-engineering/core/chinese-governance.json`：声明文档、系统界面、协作沟通、流程规范、交付物、代码注释六维范围与优先级。
- `docs/harness-engineering/core/delivery-artifact-template.md`：统一中文交付字段和结果/策略/证据/回放四分法。
- `docs/AGENTS/communication-template.md`：统一 Issue、PR、会议纪要、交接和跨 Agent 沟通字段。
- `backend/scripts/harness_run_manifest.py` / `backend/scripts/check_harness_run_manifest.py`：生成并校验运行 manifest 与 episode。
- `backend/scripts/harness_policy.py` / `backend/scripts/check_harness_policy.py`：读取策略快照、校验敏感路径和高风险操作；CI 传入 `--base/--head` 按提交范围检查，避免干净工作区漏检。
- `backend/scripts/harness_p0_gate.py`：串联上述 P0 检查并输出不可覆盖的 JSON 门禁报告。
- `backend/scripts/harness_eval_regression.py`：运行八项 Harness 自评回归集并生成趋势基线。
- `backend/scripts/observe_harness_runs.py`：汇总运行 manifest 的失败分类、延迟、工具调用、回放和恢复点指标。
- `backend/scripts/check_doc_garden.py`：只读扫描文档断链、任务入口漂移和低风险中文覆盖；不作为 P0 阻断。

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

> 路径口径：下表脚本按旧仓时期书写为 `scripts/`；Monorepo 整合后统一位于 `backend/scripts/`（读取时加 `backend/` 前缀）。

| 资产 | 作用 |
|---|---|
| `AGENTS.md` | AI Agent 启动规范和红线 |
| `docs/AGENTS/multi-agent-coordination.md` | 多 Agent 权威源、状态快照、并行边界和清理规则 |
| `docs/AGENTS/` | 编码红线、提交收口、快速参考、skill 速查 |
| `LOGBOOK.md` | 项目演进唯一真实编年史 |
| `项目进度与配置清单.md` | 当前功能状态、生产同步清单和已知风险 |
| `.pre-commit-config.yaml` | 提交前质量门禁 |
| `backend/scripts/check_project.py` | 统一红线扫描 |
| `backend/scripts/preflight_production.py` | 生产同步前只读预检和 recovery plan |
| `backend/scripts/smoke_test.py` | 服务冒烟和 JSON 留档 |
| `backend/scripts/run_isolated_remediation_harness.py` | 用生产同构组件隔离验证主体删除与消息进程崩溃重领 |
| `backend/scripts/local_production_backup.py` | 拉取生产一致快照并在本地 D 盘创建、验证和保留加密备份 |
| `backend/scripts/install_local_backup_task.ps1` | 注册每天运行的 Windows 本地加密备份计划任务 |
| `backend/scripts/check_privacy_outbound_contract.py` | 自动发现模型入口并聚合检查脱敏、trace 和生产外发关闭态 |
| `backend/scripts/check_security_outbound_contract.py` | 聚合检查统一远程下载、SSRF 逐跳策略和员工 Agent 工具授权 |
| `docs/HarnessEngineering评估报告_20260604.md` | 既有 Harness 成熟度评估 |
| `docs/VibeCoding可持续性评估报告_20260604.md` | 既有 Vibe Coding 可持续性评估 |

______________________________________________________________________

## 新增 Harness 资产

| 文件 | 作用 |
|---|---|
| [core/traceability-model.md](core/traceability-model.md) | 统一 trace、证据链和报告字段 |
| [core/verification-matrix.md](core/verification-matrix.md) | 按变更类型选择最低验证和加强验证 |
| [根目录 ERRORS.md](../../ERRORS.md) | 记录错误、根因和新增防线（唯一正式账本） |
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
| [HARNESS-MATURITY-REVIEW-20260830.md](HARNESS-MATURITY-REVIEW-20260830.md) | 记录本次 Harness 全面评审、外部对标、成熟度评分和后续优先级 |

### P0 统一门禁

本地和 CI 使用同一入口：

```powershell
python -B backend/scripts/harness_p0_gate.py --summary --json-out backend/reports/harness/p0-gate.json
```

门禁包含依赖锁一致性、中文治理、策略即代码、运行 manifest、开发总表、错误账本、证据索引、文本编码和项目红线九项检查。根级 GitHub Actions 入口为 `.github/workflows/harness-p0.yml`；依赖安装前先输出锁一致性报告，随后 P0 门禁报告与其一并上传。P0 任务指令统一位于 `docs/tasks/20260831-P0-Harness*.md`。临时产物清理不另设门禁项，统一由白名单清理脚本和 `rebuildable_cleanup` 策略约束。

中文治理六维度中，文档、系统界面、协作沟通、流程规范和交付物属于 P0；代码注释是 P1 全仓基线，但本轮新增或修改的自然语言英文注释仍会阻断门禁。系统界面扫描覆盖 `miniapp/miniprogram/pages/**/*.wxml` 与 `backend/web/admin/src/**/*.vue`，代码注释扫描覆盖后端应用、脚本、测试以及小程序和后台前端源文件。

清理脚本必须先预览再执行：预览输出目标清单授权令牌，执行时使用 `-PreviewToken <令牌> -Execute`；目标路径或文件状态变化会导致令牌失效并拒绝删除。

______________________________________________________________________

## P1 机器辅助工具

| 命令 | 作用 |
|---|---|
| `python backend/scripts/harness_snapshot.py` | 生成 Markdown 交接快照，包含 trace、目标、最新 LOGBOOK、工作区状态和参考入口 |
| `python backend/scripts/harness_snapshot.py --json` | 输出机器可读快照，适合归档到 reports |
| `python backend/scripts/harness_snapshot.py --output reports/harness/handoff-{timestamp}.md` | 写入带 UTF-8 BOM 的快照文件，拒绝覆盖已有文件 |
| `python backend/scripts/check_mistake_ledger.py` | 检查根目录 `ERRORS.md` 是否有合法空账本标记、重复 ID，或每条错误是否字段完整、枚举合法 |
| `python backend/scripts/check_evidence_index.py` | 检查 [core/evidence-index.md](core/evidence-index.md) 的证据条目必填字段、结果枚举、重复 ID、预检业务合约引用和工件完整性；默认以 Monorepo 根目录为索引基准，并只读识别已登记旧仓的历史提交。摘要会区分当前仓、旧仓、外部未验证、格式错误、仓内缺失和哈希不一致 |
| `python -B backend/scripts/check_project_development_register.py` | 单独检查唯一开发总表、状态中英映射和中文展示；失败时输出具体任务、字段、版本、提交或分支问题 |
| `python -B backend/scripts/check_requirements_lock_alignment.py --summary` | 在安装前检查生产与开发依赖锁是否可共同解析 |
| `python -B backend/scripts/check_chinese_governance.py --summary` | 检查 Harness P0 中文治理控制面和覆盖率 |
| `python -B backend/scripts/check_harness_policy.py --git-diff --summary` | 检查当前变更路径与高风险操作策略 |
| `python -B backend/scripts/check_harness_run_manifest.py --summary` | 批量校验运行 manifest 与 episode |
| `python -B backend/scripts/harness_p0_gate.py --summary` | 执行仓库级 Harness P0 统一门禁 |
| `python -B backend/scripts/harness_eval_regression.py --summary` | 执行 Harness 八项自评回归并输出通过比例、失败分类和数据集版本 |
| `python -B backend/scripts/observe_harness_runs.py --summary` | 汇总运行 manifest 的趋势、回放、恢复点、延迟和工具调用指标 |
| `python -B backend/scripts/check_doc_garden.py --summary --fail-on error` | 扫描文档园艺问题；历史归档断链可降级为 warning，不阻断 P0 |
| `.\scripts\enable_utf8_console.ps1` | 修复当前 Windows PowerShell 会话的中文输入输出乱码 |

推荐在长任务交接、上下文重置、上线收口前执行：

```powershell
python backend/scripts/harness_snapshot.py --trace-id 20260611-example --goal "说明当前任务" --status in_progress
python backend/scripts/check_mistake_ledger.py
python backend/scripts/check_evidence_index.py --summary
```

生成需要归档的快照或生产报告后，在 [core/evidence-index.md](core/evidence-index.md) 追加索引条目；影响长期演进的决策写入 [adr/](adr/)。

`check_mistake_ledger.py` 和 `check_evidence_index.py` 已接入 `.pre-commit-config.yaml`，每次提交前都会自动检查防重犯账本和证据索引结构。若账本条目不完整、证据字段缺失或证据 ID 重复，提交会被阻断，直到补齐字段或恢复合法结构。

证据来源口径：新证据必须绑定 Monorepo 当前提交；历史证据保留原始提交并在检查结果中标记为 `legacy:YunxiBakeBot`，不得用当前 HEAD 覆盖。无法在当前仓或已登记旧仓读取的提交归为 `external_unverified`，不得伪造为通过。
