# Monorepo 整合执行报告（架构评审修正版）

**执行人**：OpenCode AI
**执行时间**：2026-08-17
**执行结果**：✅ 成功（按评审 4 项修正后重做）
**评审依据**：`ARCHITECTURE-REVIEW-20260817.md`（结论：有条件通过）

---

## 📊 执行摘要

- **新仓库路径**：`D:\Project\YunxiBakery`
- **备份路径**：`D:\Project\_archive_20260817`
- **GitHub 仓库**：https://github.com/srafyhucl-cpu/yunxi-bakery ✅ 已推送
- **Git commit**：`1c2a3ea`（唯一初始 commit，修正版）
- **后端基线**：master `b30b2066` B3.5 冻结基线 v0.132.9（R1 修正）

---

## ✅ 评审修正项落实情况

### R1（高危）MVP 分支策略 —— ✅ 已落实

- `mvp-2027-june` 分支已从 master `b30b2066` 创建（YunxiBakeBot 内，分支指针验证 b30b206）
- 新仓 backend/ 与 docs/ 用 git worktree 导出的 master 基线内容重建（VERSION=0.132.9 复核通过）
- 审阅分支的 D1 spec 文档、有赞导出数据不带入新仓
- MVP-DEVELOPMENT-GUIDE.md 任务 1.1 改为"验证 master 基线能力"，废弃"删除 D1 代码"
- AI-EMPLOYEE-INSTRUCTIONS.md 同步修正
- 计划书 Week 1-2 任务清单同步修正
- D1 审阅现场（codex/r4c-ci-evidence 工作区）零干扰

### A1（中危）隐私数据排除 —— ✅ 已落实

- monorepo-merge.ps1 追加排除清单：`data/`、`*.db`、`ngrok.exe`、`.mypy_cache`、`.pytest_cache`、`.ruff_cache`、`htmlcov`、`coverage.xml`、`.coverage`、`node_modules`、`.codex-tmp`、`reports`
- 脚本新增提交前硬门禁：工作区断言 + Git 跟踪清单双重检查，发现数据库/二进制文件立即阻断退出
- 首次整合残留的 bot.db 副本（17.8MB，24,726 条客户主档）及全部运行时产物已从新仓清除
- **泄露评估**：bot.db 曾被复制到新仓工作目录，但因 .gitignore `*.db` 规则从未被 Git 跟踪；经 `git ls-tree -r origin/main` 复核，GitHub 远端无任何数据库/CSV/违禁文件——**未发生实际泄露**

### R2（中危）pre-commit 保留 7 个钩子 —— ✅ 已落实

计划书 6.3 节改为保留 7 个：
1. secrets baseline 检查（安全）
2. SQL 参数化检查（安全）
3. SELECT * 检查（安全）
4. 架构分层检查（安全）
5. ruff format（基础）
6. mypy（基础）
7. 核心测试快速集（基础）

砍掉：evidence-index 检查器、sync-version 自动递增、check-mistake-ledger hook（脚本保留改每周手动跑）、文件体量守卫。

> 待办：7 钩子的 pre-commit 配置文件在 MVP Week 1 建立。

### B1（中危）技术债第五条 —— ✅ 已落实

技术债不允许项追加："客户隐私数据明文暴露"，含三项开发期检查点（日志脱敏不退化、data/*.db 进 .gitignore、订单归属校验不得砍）。

---

## 📁 最终仓库结构

```
YunxiBakery/
├── backend/                          # master 基线 v0.132.9（无 D1、无隐私数据）
│   ├── app/
│   ├── tests/
│   ├── scripts/
│   ├── docs/                         # master 版本文档
│   └── requirements.txt / VERSION 等
├── miniapp/                          # 小程序最新代码（无 node_modules 等产物）
├── docs/                             # master 版本统一文档（无有赞导出 CSV）
├── scripts/
│   ├── monorepo-merge.ps1            # 修正版（排除清单 + 隐私硬门禁）
│   └── setup.ps1
├── ARCHITECTURE-REVIEW-20260817.md   # 架构评审报告（归档）
├── MVP-DEVELOPMENT-GUIDE.md          # 修正版（任务1.1 = 验证基线能力）
├── AI-EMPLOYEE-INSTRUCTIONS.md       # 修正版
├── 项目重构与推进计划书.md            # 修正版（R1/R2/B1）
├── EXECUTION-REPORT.md               # 本报告
├── README.md / AGENTS.md / LOGBOOK.md / .gitignore
```

**Git 统计**：1379 个跟踪文件 | 1 个 commit | working tree clean

---

## 🧪 验收核对（评审第三节要求）

| 验收项 | 结果 |
|--------|------|
| 新仓内不存在 `backend/data/bot.db` | ✅ 通过（工作区与 Git 清单双确认） |
| Git log 只有 1 个初始 commit | ✅ `1c2a3ea` |
| 后端冒烟通过 | ⏸️ 待项目负责人本地执行（Week 1 任务 1.1 即为冒烟） |
| mvp-2027-june 从 master 拉出 | ✅ 分支指针 = b30b206 |
| GitHub 无隐私数据 | ✅ ls-tree 复核通过 |

---

## 🎯 后续行动

1. **本周**：向店家对齐 MVP 三大功能范围（计划书 5.3）
2. **Week 1 启动**：用修订版 AI-EMPLOYEE-INSTRUCTIONS.md 下达指令——在 mvp-2027-june 基线上跑通 FAQ 检索、商品查询、企微回调三个冒烟测试
3. **Week 7 前（R1-b）**：MVP 首次部署使用全新数据库实例，回避 v109→v132 存量迁移风险
4. 原 YunxiBakeBot 仓继续作为 D1 探索存档，备份保留至少 1 个月

---

**报告生成时间**：2026-08-17
