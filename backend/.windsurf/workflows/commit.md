---
description: 开发任务收口工作流，用于芸熙烘焙 AI 客服项目的任务完成检查、LOGBOOK 更新和代码提交
---


# 开发任务收口工作流

## 触发场景

当一次开发任务进入收尾阶段时使用此工作流，确保交付闭环符合项目规范。

## 收口检查清单

### 1. 代码红线自查

在提交前逐项检查：

```powershell
# 检查 Optional/Union（必须零输出）
git diff --cached -- "*.py" | Select-String "Optional\[|Union\["

# 检查 TODO 占位符（必须零输出）
git diff --cached -- "*.py" | Select-String "# TODO"

# 检查单引号字符串（人工判断，SQL 和 f-string 内部除外）
git diff --cached -- "*.py" | Select-String "= '"
```

- **任意一项有输出 → 立即修复，不得提交**
- **检查本轮新增/修改的代码注释语言**：Python / JS / TS / HTML / CSS 注释统一使用中文；若发现英文注释，先改写后再提交

### 2. 验证与留痕

根据修改范围按 `docs/harness-engineering/core/verification-matrix.md` 选择验证：

```powershell
# 当前代码基线测试（默认必跑，防止本地代码落后于 CI 或遗漏依赖）
python -m pytest tests/ -q

# 场景测试（覆盖意图识别、对话流）
python scripts/test_scenarios.py

# 意图识别测试
python scripts/test_intents.py

# 商品数据校验（修改了知识库时运行）
python scripts/validate_products.py
```

- 文档变更至少完成 `Test-Path` / `Select-String` 链接与关键词检查。
- 需要交接时，优先补 `trace_id` 与 `scripts/harness_snapshot.py` 快照。
- 如果 GitHub Actions / CI 处于失败状态，先对齐本地代码与 CI 入口；记录失败 job、失败命令和差异原因，再提交修复。

### 2.5 工作区整洁检查

提交前必须先确认工作区没有混入本地临时产物：

```powershell
# 查看工作区未跟踪文件与残留修改
git status --short

# 重点确认以下模式不会进入提交
# .tmp-*.log
# .codex-server*.log
# .superpowers/
```

- 若发现上述临时产物，先清理后再 `git add`
- 若临时日志文件无法删除，先定位并停止残留的本地 `uvicorn` / `pytest` / 预览进程，再重试删除
- 只有在 `git status --short` 不再出现无关临时文件时，才允许进入暂存与提交步骤

### 3. 服务启动验证

确认服务能正常启动：

```powershell
# 启动服务
uvicorn app.main:app --host 127.0.0.1 --port 7001 --reload

# 健康检查
curl http://127.0.0.1:7001/health
```

- 预期响应：`{"status": "ok", "version": "0.1.0"}`

### 4. 项目文档强制更新（pre-commit 自动拦截）

> **本步骤已有 pre-commit hook 自动检查**（`scripts/check_logbook.py`）。  
> 凡暂存区含 `.py / .html / .css / .js` 文件，以下两份文档必须同时在暂存区，否则 commit 被拦截。  
> 纯配置/格式修正时可用 `SKIP_LOGBOOK_CHECK=1 git commit ...` 临时跳过。

> 如果本轮是“现有代码已经变了，但文档还没同步”的场景，先跑 `/sync-docs`（见 `docs/AGENTS/sync-docs.md`），再继续 `/commit`。

#### 4.1 LOGBOOK.md（开发日志）

在 `LOGBOOK.md` **顶部**（第一个分隔线后）追加本轮变更记录：

```markdown
## [YYYY-MM-DD] - 一句话标题

- **操作人**: AI (Codex) / 开发者
- **trace_id**: YYYYMMDD-topic，较大任务建议填写
- **背景**: 一句话描述为什么改
- **变更范围**:
  - `path/to/file` - 说明
- **验证结果**:
  - `command` 通过 / 失败
- **结论**:
  - 一句话说明是否收口
```

#### 4.2 项目进度与配置清单.md（项目状态）

同步更新以下内容（按实际变更勾选）：

- **"最后更新"日期**：改为今天
- **已完成功能**：新增 `[x]` 条目描述本次功能
- **待开发功能 / 风险**：将已修复的问题状态改为已解决，新增新风险条目
- **测试脚本清单**：如新增测试脚本，补充到表格

> 以下文档仅在涉及核心业务流程/架构变更时才需更新：  
> `1-业务方案.md` / `2-工作流设计.md` / `3-技术架构.md` / `4-上线检查清单.md`

### 4.5 Skill 同步检查（本次变更涉及新增文件 / 类 / 调用关系时）

若本次变更涉及以下任一情况，必须先运行 `/sync-skills` 工作流：

- 新增 / 删除 `.py` 文件
- 新增 / 删除公开类或核心函数
- 改变模块间调用关系
- 修改 LLM 相关逻辑

### 5. Harness 留痕与交接

较大任务、跨文件修改、上线收口或需要换手时，先补 `trace_id`，再用 `scripts/harness_snapshot.py` 生成快照，必要时登记到 `docs/harness-engineering/core/evidence-index.md`。

### 6. Git 提交

```powershell
git add .
git status

# 提交（中文 Conventional Commits 格式）
git commit -m "feat(chat): 新增功能描述"
git push origin master
git push server master
```

## 提交类型速查

| type | 说明 | 示例 | |------|------|------| | `feat` | 新增功能 | `feat(chat): 新增运费关键词前置匹配` | | `fix` | 修复
bug | `fix(wecom): 修复企微消息解密失败问题` | | `docs` | 文档更新 | `docs(logbook): 更新项目演进记录` | | `refactor` | 重构 |
`refactor(repo): 提取公共查询方法` | | `perf` | 性能优化 | `perf(vector): 优化 TF-IDF 构建速度` | | `test` | 测试 |
`test(intent): 补充闲聊意图测试用例` | | `chore` | 构建/工具 | `chore(deps): 升级 openai 至最新版` |

## 验收标准

- [ ] 代码红线自查通过（Optional/Union/TODO 零输出）
- [ ] 本轮新增或修改的代码注释已统一为中文
- [ ] 相关测试通过
- [ ] `git status --short` 已确认无无关临时产物（如 `.tmp-*.log`、`.codex-server*.log`、`.superpowers/`）
- [ ] 服务健康检查通过
- [ ] `LOGBOOK.md` 已更新
- [ ] 项目进度与配置清单等相关文档已同步更新
- [ ] Git 提交信息符合 Conventional Commits 格式
- [ ] 已推送到远程分支

## 收口顺序

代码改动 → 测试验证 → LOGBOOK 与文档更新 → 提交 → 推送

严格按此顺序执行，不可跳过任何步骤。

> `git push server master` 仅同步 Git 远端，不会自动发布到生产。需要生产同步时，提交和双远端推送成功后执行 `bash scripts/deploy.sh`；该脚本将 Git Bundle 发布到 `/opt/apps/yunxibakebot`，重启 `yunxibakebot` 并验证 loopback `/health` 与 `/ready`，再用 `curl https://yunxifood.cn/health` 验证公网 API。
