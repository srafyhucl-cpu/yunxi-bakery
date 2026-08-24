# 提交收口规范

> 每次提交前必须按顺序完成以下步骤，不可跳过或乱序。

______________________________________________________________________

## 提交前清单（9 步）

1. **调用相关 Guard Skill** 确认代码符合规范
2. **更新 `LOGBOOK.md`**（可使用 `python scripts/append_logbook.py` 自动追加，或手动在顶部追加条目）
3. **更新 `项目进度与配置清单.md`**（修改"最后更新"日期 + 已完成功能 + 已知问题状态）
3.5 **如本轮是中大型任务或需要交接**：先按 `docs/harness-engineering/core/traceability-model.md` 补 `trace_id` 和验证摘要，再按 `docs/harness-engineering/core/evidence-index.md` 归档证据
4. **检查代码注释语言**：凡本轮新增或修改的代码注释，必须统一为中文注释；英文注释需改写后再提交
5. **检查工作区临时产物**：先执行 `git status --short`，确认不存在 `.tmp-*.log`、`.codex-server*.log`、`.superpowers/` 等本地临时文件；如存在，必须先清理
6. **运行验证**：按 `docs/harness-engineering/core/verification-matrix.md` 选择最低验证；文档变更至少完成 `Test-Path` / `Select-String` 之类的链接与关键词检查，代码变更再运行对应测试
7. **git add + commit**（pre-commit 会自动执行以下操作）：
   - **版本号自动递增**：根据提交信息自动递增 `VERSION`，同步项目进度表头，并把两个文件加入同一次提交；未知表头会阻断（feat→minor, fix→patch, feat!→major）
   - **文档同步检查**：校验 LOGBOOK.md 和项目进度与配置清单.md 已暂存
   - **质量门禁**：密钥扫描 + 文件体量 + 红线规则自测 + 全套测试
8. **推送代码到版本远端**：`git push origin master && git push server master`。这一步只同步 Git，不代表生产发布完成。
9. **如本轮涉及生产同步**，执行 `bash scripts/deploy.sh`。该脚本通过 SSH Git Bundle 发布到 `/opt/apps/yunxibakebot`，由服务器端脚本执行安全预检、服务重启和 loopback 健康检查；完成后再验证 `https://yunxifood.cn/health`。

---

## 版本号自动递增规则

| 提交类型 | 版本递增 | 示例 |
|---------|---------|------|
| `feat!` / `BREAKING CHANGE` | 主版本号 (major) | 0.2.0 → 1.0.0 |
| `feat` / `perf` / `refactor` | 次版本号 (minor) | 0.2.0 → 0.3.0 |
| `fix` / `docs` / `style` / `chore` | 修订号 (patch) | 0.2.0 → 0.2.1 |

- 版本号唯一来源：根目录 `VERSION` 文件
- `app/config.py` 中的 `APP_VERSION` 从 `VERSION` 文件自动读取，无需手动同步
- `app/main.py` 中的 `version` 和 `/health` 端点均引用 `APP_VERSION`

---

## 环境变量快速跳过

| 场景 | 命令 |
|------|------|
| 跳过版本递增 | `SKIP_VERSION_BUMP=1 git commit -m "..."` |
| 强制指定递增类型 | `VERSION_BUMP=minor git commit -m "..."` |
| 跳过文档同步检查 | `SKIP_LOGBOOK_CHECK=1 git commit -m "..."` |

> 中大型任务的证据归档和换手说明，优先使用 `docs/harness-engineering/core/agent-handoff-template.md` 与 `scripts/harness_snapshot.py`，不要只留在聊天记录里。

> 📄 完整格式参见 `docs/AGENTS/sync-docs.md`
