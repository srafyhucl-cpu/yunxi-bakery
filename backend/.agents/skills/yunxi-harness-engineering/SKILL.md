---
name: 芸熙Harness工程守卫
version: 1.2.1
description: "【较大任务、跨文件变更、上线收口、复盘或发现重复错误时调用】芸熙烘焙 AI 客服 Harness Engineering 守卫。用于把需求、决策、改动、验证、证据、LOGBOOK、mistake ledger 和交接快照串成可追溯闭环；当用户提到 harness、追溯、记忆、防重犯、复盘、证据、交接、生产级治理、文档统一管理、Skill 是否过时时必须调用。"
---

# 芸熙 Harness Engineering 守卫

本 Skill 是项目级 AI 驾驭入口。它不替代 `AGENTS.md`、Guard Skill、pre-commit 或测试，而是负责把它们组织成一条可追溯链路。

当前成熟度基线与外部对标见：

```text
docs/harness-engineering/HARNESS-MATURITY-REVIEW-20260830.md
```

统一父入口：

```text
docs/harness-engineering/README.md
```

## 触发场景

只要命中以下任一情况，就先使用本 Skill：

- 用户提到 Harness、Vibe Coding、追溯、记忆、防重犯、复盘、证据、交接、Skill 过时、文档散乱。
- 任务预计修改超过 2 个文件，或需要跨文档、脚本、测试、配置同步。
- 任务涉及生产同步、上线前后验证、报告留档、恢复计划、冒烟或预检。
- 发生返工、误解、误操作、重复 bug、遗漏验证、上下文丢失。
- 需要判断“这次经验应该沉淀到哪里”：测试、脚本、pre-commit、AGENTS、Skill、runbook、ADR 或 mistake ledger。

## 启动顺序

1. 读取 `AGENTS.md`，确认本轮还需要哪些 Guard Skill。
2. 读取 `PROJECT-STATE.md` 当前状态，确认阶段和阻塞项。
3. 读取 `LOGBOOK.md` 最新条目，避免重复踩坑。
4. 读取 `docs/harness-engineering/README.md`，只按场景继续打开子文档。
5. 读取 `docs/AGENTS/multi-agent-coordination.md`，确认权威源和并行边界。
6. 为中大型任务分配 `trace_id`，格式参考 `docs/harness-engineering/core/traceability-model.md`。
7. 按 `docs/harness-engineering/core/verification-matrix.md` 选择最低验证和加强验证。

## 记忆落点决策

不要把经验只留在聊天里。按下面优先级沉淀：

| 情况 | 首选落点 |
|---|---|
| 可被机器检查的格式或规则 | 测试、脚本、pre-commit |
| 操作流程或 Agent 启动约束 | `AGENTS.md` 或项目 Skill |
| 某类错误已发生且值得防重犯 | 根目录 `ERRORS.md`（唯一正式账本） |
| 长期架构取舍 | `docs/harness-engineering/adr/` |
| 上线、迁移、冒烟、交接证据 | `reports/harness/` + `core/evidence-index.md` |
| 上下文要换人或续跑 | `backend/scripts/harness_snapshot.py` + `core/agent-handoff-template.md` |

## 中文优先状态展示约束

- 面向人阅读的项目状态、任务状态、阻塞说明和交接结论必须先写中文。
- `status` 保留稳定的 ASCII 机器枚举；所有任务同时填写 `status_label`，格式必须为“中文状态（机器码）”。
- 统一映射：`已完成（completed）`、`进行中（active）`、`已阻塞（blocked）`、`待处理（pending）`、`已暂缓（deferred）`、`历史（historical）`。
- `PROJECT-STATE.md` 主线任务表必须同时有 `status` 和“状态说明”列；中文叙述中禁止裸写上述机器状态码。
- 每次新增或修改任务状态后，必须运行 `python -B backend/scripts/check_project_development_register.py`；失败时不得继续收口。

### 中文治理的 P0 控制面定位

中文治理是 Harness 的项目管理与驾驭工程能力，不是独立的翻译项目。P0 必须优先保证：

- 权威状态、责任、阻塞、证据和交接内容可由中文读者直接理解；
- 生产开关、支付/退款、数据处理、批准/阻断、API 错误和 CLI 状态等高风险路径具备中文状态映射；
- 任务、评审、验收和证据摘要同时保留中文人类可读内容与稳定 ASCII 机器字段；
- 中文治理检查器能发现权威源漂移、裸机器状态码、关键模板缺字段和高风险路径中文缺失。

六维范围固定为：文档、系统界面、协作沟通、流程规范、交付物、代码注释。模型与检查入口位于 `docs/harness-engineering/core/chinese-governance.json` 和 `backend/scripts/check_chinese_governance.py`；涉及后台 Vue、小程序 WXML/TS/WXSS 或脚本/测试注释时，任务的 `allowed_paths` 必须明确登记，不能继续沿用只允许文档的旧快照。

全仓注释翻译、低风险文案优化和历史文档清理属于 P1/P2，不能替代上述 P0 控制面，也不应阻塞运行契约、策略即代码和发布前置工作。

## 管理文件单一入口约束

- 同一职能尽可能只保留一个正式文件：当前状态用 `PROJECT-STATE.md`，历史证据用 `LOGBOOK.md`，错误账本用根目录 `ERRORS.md`。
- 旧仓镜像或兼容页只能指向正式文件，不得复制条目、并行维护或作为新 Agent 的默认入口。
- 发现同职能多份文件时，先登记差异并统一权威源，再继续实现功能。

## 测试节奏与耗时约束

- 功能开发、缺陷修复和模块迭代期间，默认只运行与改动直接相关的定向测试，不因每次编辑重复运行全量测试。
- 每个功能或模块进入上线候选版本时，执行一次全量测试作为收口门禁；同一候选版本不得无目标重复执行。
- 若全量测试失败，先用定向测试定位和修复；修复后允许一次最终全量复跑，并在同一收口记录中说明失败原因和复跑原因。
- 全量测试必须记录命令、退出码、测试数量、开始/结束时间和总耗时。单次超过 10 分钟，或较最近基线增加 20% 以上，必须登记测试优化评估。
- 测试优化优先采用分片、并行、夹具隔离、缓存和慢测标记；不得通过删减覆盖范围或静默跳过失败来缩短耗时。
- 仅文档、规范或 Harness 配置变更，未触及代码行为时，不要求重复全量测试，必须在验证记录中写明未运行原因。

## 运行契约与回放约束

- 中大型任务必须声明 `trace_id`、`task_id`、`as_of_commit`、`version`、`allowed_paths` 和 `forbidden_paths`。
- 中大型 Agent 运行必须生成唯一 `run_id`；续跑或重试使用新的 `run_id`，并通过 `parent_run_id` 关联，禁止覆盖失败运行。
- 运行摘要至少记录模型/执行者、工具策略摘要、输入/输出工件哈希、验证命令、失败分类、耗时、成本、人工介入和 `replayable`。
- 最终状态不得只写“通过”；必须分别说明结果、策略、证据和回放四项是否满足。
- 任务执行时优先消费 `PROJECT-STATE.md`、任务包和最近 episode，不把无关的历史大文件作为默认上下文。

## 策略即代码方向

- `allowed_paths`、`forbidden_paths`、外部网络、真实客户数据、生产开关和高风险工具必须在运行摘要中留下策略快照标识。
- 发现越权、过期快照、缺证据宣称完成、状态冲突或重复全量测试时，按 `scope_drift`、`stale_snapshot`、`policy_violation`、`verification_failure` 归因并阻断收口。
- 任意路径递归删除继续由 `recursive_delete` 策略默认阻断；仅允许通过 `scripts/cleanup-local-artifacts.ps1` 清理白名单内临时/可重建产物。
- 白名单清理必须先预览、核对目标和保护边界，再以 `rebuildable_cleanup` 操作记录人工批准；自定义仓内临时目录须使用 `.tmp-` 前缀并在任务 manifest 中登记。

## P0 统一门禁命令

本地与根级 CI 使用同一门禁入口：

```powershell
python -B backend/scripts/harness_p0_gate.py --summary --json-out backend/reports/harness/p0-gate.json
```

门禁固定执行依赖锁一致性、中文治理、策略即代码、运行 manifest、开发总表、错误账本、证据索引、文本编码和项目红线九项检查。单项调试命令如下：

```powershell
python -B backend/scripts/check_requirements_lock_alignment.py --summary
python -B backend/scripts/check_chinese_governance.py --summary
python -B backend/scripts/check_harness_policy.py --git-diff --summary
python -B backend/scripts/check_harness_run_manifest.py --summary
```

报告不得覆盖已有文件；中大型运行仍须单独生成 `run_id` 和 episode，不能以门禁摘要代替运行契约。

## Harness 自评与持续园艺

- 除业务 Agent eval 外，项目使用 `backend/scripts/harness_eval_regression.py` 运行 Harness 自评集，固定记录 dataset_version、evaluator_version、threshold、失败分类和与 baseline 的差异；当前最小集覆盖方向一致性、权限边界、运行契约、证据完整性、中文治理、门禁一致性、恢复能力和策略稳定性。
- 使用 `backend/scripts/observe_harness_runs.py` 周期汇总运行 manifest 的成本/延迟、工具调用、失败分类、人工介入、父子运行关联、回放和恢复点覆盖率；恢复点不足时只标记 P1 观测失败，不绕过 P0 高风险门禁。
- 使用 `backend/scripts/check_doc_garden.py` 周期检查断链、重复入口、过期提交、孤立任务、未登记报告和低风险中文覆盖；历史归档问题可降级为 warning，P2 扫描不作为当前生产、支付或客户数据操作的前置阻断。

## 防重犯闭环

当发现一次值得记住的错误时，不要只修当次问题。至少补一类防线：

1. 新增或更新测试。
2. 新增或更新检查脚本。
3. 接入 pre-commit 或 CI。
4. 更新 AGENTS 或项目 Skill。
5. 更新 runbook、ADR 或验证矩阵。

然后运行：

```powershell
python backend/scripts/check_mistake_ledger.py
```

## 证据留档

长任务、上下文切换或上线收口时运行：

```powershell
python backend/scripts/harness_snapshot.py --trace-id <trace_id> --goal "<任务目标>" --status in_progress
```

需要归档时：

```powershell
python backend/scripts/harness_snapshot.py --trace-id <trace_id> --goal "<任务目标>" --status completed --output backend/reports/harness/handoff-{timestamp}.md
```

归档后在 `docs/harness-engineering/core/evidence-index.md` 登记报告路径、命令、结果、关联 LOGBOOK 和敏感数据状态。新证据显式写 `repository_origin: monorepo`；冻结旧仓历史保留原始提交，由检查器标记 `legacy:YunxiBakeBot`，不得用当前 HEAD 重写。

## Skill 维护规则

- 项目规则优先写入 `.agents/skills/`，不要污染全局 Skill。
- 全局 Skill 只保留通用能力，例如 `brainstorming`、`skill-creator`、`using-superpowers`。
- 如果某个项目 Skill 的路径、阈值、文件清单或流程入口变了，必须同步 `docs/AGENTS/skill-reference.md`。
- 如果 Skill 中的约束来自一次错误或返工，把来源写入根目录 `ERRORS.md` 或 LOGBOOK，避免规则变成无根命令；不得新建同职能错误账本。

## 收口清单

- [ ] 本轮是否有 `trace_id`，或明确说明为什么不需要。
- [ ] 相关验证是否按 verification matrix 执行。
- [ ] 证据文件是否已归档或说明无需归档。
- [ ] LOGBOOK 和项目进度清单是否同步。
- [ ] 如果出现错误，是否进入 mistake ledger 并补了机械防线。
- [ ] 如果更新了 Skill，是否同步 `docs/AGENTS/skill-reference.md`。
- [ ] 状态展示是否符合中文状态 + 机器码约束，且开发总表守卫已通过。
- [ ] 中大型运行是否有独立 `run_id`，且失败/重试未覆盖旧运行。
- [ ] 是否记录策略快照、失败分类、耗时/成本和 `replayable` 结论。
