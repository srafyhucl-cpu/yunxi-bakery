# 提交收口规范

> 每次提交前必须按顺序完成以下步骤，不可跳过或乱序。

______________________________________________________________________

## 提交前清单（9 步）

1. **调用相关 Guard Skill** 确认代码符合规范
2. **更新 `LOGBOOK.md`**（可使用 `python backend/scripts/append_logbook.py` 自动追加，或手动在顶部追加条目）
3. **更新 `项目进度与配置清单.md`**（修改"最后更新"日期 + 已完成功能 + 已知问题状态）
3.5 **如本轮是中大型任务或需要交接**：先读 `docs/AGENTS/multi-agent-coordination.md`，再按 `docs/harness-engineering/core/traceability-model.md` 补 `trace_id` 和验证摘要，最后按 `docs/harness-engineering/core/evidence-index.md` 归档证据
4. **检查代码注释语言**：凡本轮新增或修改的代码注释，必须统一为中文注释；英文注释需改写后再提交
5. **检查工作区临时产物**：先执行 `git status --short`，确认不存在 `.tmp-*.log`、`.codex-server*.log`、`.superpowers/`、`.workbuddy/` 或缓存目录；如需清理，先运行 `.\scripts\cleanup-local-artifacts.ps1` 预览，获负责人授权后再逐文件执行 `-Execute`
6. **运行验证**：按 `docs/harness-engineering/core/verification-matrix.md` 选择最低验证；文档变更至少完成 `Test-Path` / `Select-String` 之类的链接与关键词检查，代码变更再运行对应测试
7. **git add + commit**（pre-commit 会自动执行以下操作）：
   - **版本号自动递增**：根据提交信息自动递增 `backend/VERSION`，同步项目进度表头，并把两个文件加入同一次提交；未知表头会阻断（feat→minor, fix→patch, feat!→major）
   - **文档同步检查**：校验 LOGBOOK.md 和项目进度与配置清单.md 已暂存
   - **质量门禁**：密钥扫描 + 文件体量 + 红线规则自测 + 全套测试
8. **推送代码到版本远端**：仅在项目负责人批准后执行 `git push origin <branch>`。这一步只同步 Git，不代表生产发布完成；当前克隆默认只有 `origin`，不得凭空使用 `server` 远端。
   - **推送后必须回读验证（强制，2026-08-24 起生效）**：push 后执行 `git ls-remote origin <branch>` 并核对返回 SHA 与本地 `git rev-parse HEAD` 一致，才能在汇报中声明"已推送"。禁止用 `$?` 判断 native command 管道成败作为是否执行推送的依据——必须显式检查 `$LASTEXITCODE`；push 失败或被跳过时必须在汇报中显式报告，不允许静默。未推送 = 未备份，本地工作区不是可靠副本。
9. **如本轮涉及生产同步**，且已取得明确批准，执行 `bash backend/scripts/deploy.sh`。该脚本通过 SSH Git Bundle 发布到 `/opt/apps/yunxibakebot`，由服务器端脚本执行安全预检、服务重启和 loopback 健康检查；完成后再验证 `https://yunxifood.cn/health`。

---

## 版本号自动递增规则

| 提交类型 | 版本递增 | 示例 |
|---------|---------|------|
| `feat!` / `BREAKING CHANGE` | 主版本号 (major) | 0.2.0 → 1.0.0 |
| `feat` / `perf` / `refactor` | 次版本号 (minor) | 0.2.0 → 0.3.0 |
| `fix` / `docs` / `style` / `chore` | 修订号 (patch) | 0.2.0 → 0.2.1 |

- 版本号唯一来源：`backend/VERSION` 文件
- `backend/app/config.py` 中的 `APP_VERSION` 从 `backend/VERSION` 自动读取，无需手动同步
- `backend/app/main.py` 中的 `version` 和 `/health` 端点均引用 `APP_VERSION`
- **VERSION 变更必须与 `项目进度与配置清单.md` 表头同步**：每次改动 `VERSION`（含手动 bump 与 pre-commit 自动递增），须同步更新根目录与 `backend/` 下的 `项目进度与配置清单.md` 第 3 行 `当前本地代码版本为 \`<version>\``，否则 `test_repository_progress_header_matches_version_file` 会红（2026-08-26 教训：手动 bump 漏同步导致基线非空零）

---

## 环境变量快速跳过

| 场景 | 命令 |
|------|------|
| 跳过版本递增 | `SKIP_VERSION_BUMP=1 git commit -m "..."` |
| 强制指定递增类型 | `VERSION_BUMP=minor git commit -m "..."` |
| 跳过文档同步检查 | `SKIP_LOGBOOK_CHECK=1 git commit -m "..."` |

> 中大型任务的证据归档和换手说明，优先使用 `docs/harness-engineering/core/agent-handoff-template.md` 与 `backend/scripts/harness_snapshot.py`，不要只留在聊天记录里。

> 📄 完整格式参见 `docs/AGENTS/sync-docs.md`
