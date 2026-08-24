# 芸熙烘焙平台 Monorepo 整合执行指南

**目标受众**：AI 开发助手  
**执行时间**：约 30 分钟  
**当前日期**：2026-08-17

---

## 🎯 任务目标

将 `YunxiBakeBot`（后端）和 `YunxiBakeMiniApp`（小程序）两个独立项目合并为一个统一的 Monorepo 仓库 `YunxiBakery`。

**重要提示**：
- ✅ 这是简化版整合，**不保留 Git 历史**
- ✅ 原仓库会备份到 `_archive_20260817/`
- ✅ 所有文件内容已预先准备好
- ✅ 你只需按步骤执行即可

---

## 📋 执行前检查清单

在开始前，确认以下条件：

- [ ] 你能访问 `D:\Project\YunxiBakeBot` 目录
- [ ] 你能访问 `D:\Project\YunxiBakeMiniApp` 目录
- [ ] 你有 Git 命令行工具
- [ ] 你有 PowerShell 执行权限
- [ ] 你已经阅读完本文档

---

## 🚀 执行步骤

### Step 0：理解任务（5 分钟）

**阅读以下文档**：
1. `项目重构与推进计划书.md` - 了解战略背景
2. 本文档 - 了解执行步骤

**核心原则**：
- 快速执行，不要犹豫
- 遇到错误立即停止并报告
- 每一步完成后报告进度

---

### Step 1：执行整合脚本（10 分钟）

**操作**：

```powershell
cd D:\Project\YunxiBakeBot
.\scripts\monorepo-merge.ps1
```

**脚本会自动完成**：
1. 备份原仓库
2. 创建新目录 `YunxiBakery`
3. 复制所有文件
4. 整理文档结构
5. 生成新的配置文件
6. 初始化 Git 仓库

**预期输出**：
```
=== 芸熙烘焙平台 Monorepo 整合脚本 ===
[✓] 步骤 1/8: 备份原仓库
[✓] 步骤 2/8: 创建新目录
[✓] 步骤 3/8: 复制后端文件
[✓] 步骤 4/8: 复制小程序文件
[✓] 步骤 5/8: 整理文档结构
[✓] 步骤 6/8: 生成配置文件
[✓] 步骤 7/8: 初始化 Git
[✓] 步骤 8/8: 第一次提交

✅ Monorepo 整合完成！
```

**如果出错**：
- 截图错误信息
- 立即停止，不要继续
- 报告给项目负责人

---

### Step 2：验收测试（10 分钟）

**2.1 检查目录结构**

```powershell
cd D:\Project\YunxiBakery
tree /F /A
```

**预期结构**：
```
YunxiBakery/
├── backend/
├── miniapp/
├── docs/
├── scripts/
├── README.md
├── LOGBOOK.md
├── AGENTS.md
├── .gitignore
└── 项目重构与推进计划书.md
```

**2.2 测试后端启动**

```powershell
cd D:\Project\YunxiBakery\backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 7001 --reload
```

**访问测试**：
- 浏览器打开 `http://127.0.0.1:7001/health`
- 应该返回 `{"status":"ok"}`

**测试通过后**：
- 按 `Ctrl+C` 停止服务器
- 执行 `deactivate` 退出虚拟环境

**2.3 测试小程序打开**

- 用微信开发者工具打开 `D:\Project\YunxiBakery\miniapp` 目录
- 应该能正常加载项目配置
- 不需要真正运行，能打开即可

**2.4 检查 Git 状态**

```powershell
cd D:\Project\YunxiBakery
git log --oneline
git status
```

**预期输出**：
```
abcd123 chore: 初始化Monorepo（合并YunxiBakeBot后端和YunxiBakeMiniApp小程序）
On branch main
nothing to commit, working tree clean
```

---

### Step 3：推送到 GitHub（5 分钟）

**重要**：执行前确认项目负责人已在 GitHub 创建 `yunxi-bakery` 仓库。

**操作**：

```powershell
cd D:\Project\YunxiBakery

# 添加 GitHub 远端
git remote add origin https://github.com/srafyhucl-cpu/yunxi-bakery.git

# 推送
git push -u origin main

# 添加生产服务器远端
git remote add server ssh://root@47.94.102.250/opt/apps/yunxibakebot/.git

# 验证远端配置
git remote -v
```

**预期输出**：
```
origin  https://github.com/srafyhucl-cpu/yunxi-bakery.git (fetch)
origin  https://github.com/srafyhucl-cpu/yunxi-bakery.git (push)
server  ssh://root@47.94.102.250/opt/apps/yunxibakebot/.git (fetch)
server  ssh://root@47.94.102.250/opt/apps/yunxibakebot/.git (push)
```

**如果 GitHub 推送失败**：
- 检查是否已创建仓库
- 检查 Git 凭据是否正确
- 报告错误信息

---

### Step 4：完成报告（5 分钟）

**填写验收检查清单**：

打开 `D:\Project\YunxiBakery\VERIFICATION-CHECKLIST.md`，逐项检查：

```markdown
## Monorepo 整合验收清单

### 基础检查
- [ ] 新仓库 `YunxiBakery` 已创建
- [ ] 原仓库已备份到 `_archive_20260817/`
- [ ] 目录结构符合预期（backend/ 和 miniapp/ 存在）

### 功能测试
- [ ] 后端能正常启动
- [ ] /health 端点返回 200
- [ ] 小程序能用微信开发者工具打开
- [ ] Git 历史干净（只有1个初始 commit）

### Git 配置
- [ ] origin 远端指向 GitHub
- [ ] server 远端指向生产服务器
- [ ] 已成功推送到 GitHub

### 文档检查
- [ ] README.md 存在且内容正确
- [ ] LOGBOOK.md 已合并
- [ ] AGENTS.md 已合并
- [ ] 项目重构与推进计划书.md 存在

### 问题记录
如有任何问题，在此记录：

（无问题请写"无"）
```

**生成执行报告**：

创建 `EXECUTION-REPORT.md`：

```markdown
# Monorepo 整合执行报告

**执行人**：AI 开发助手  
**执行时间**：2026-08-17  
**执行结果**：✅ 成功 / ❌ 失败

## 执行摘要

- 新仓库路径：D:\Project\YunxiBakery
- 备份路径：D:\Project\_archive_20260817
- GitHub 仓库：https://github.com/srafyhucl-cpu/yunxi-bakery
- Git commit：[填写 commit hash]

## 验收结果

[粘贴 VERIFICATION-CHECKLIST.md 的检查结果]

## 遇到的问题

[记录所有问题和解决方法，无问题则写"无"]

## 后续建议

1. 建议项目负责人验证 GitHub 仓库内容
2. 建议保留原仓库备份至少 1 个月
3. 可以开始 MVP 开发阶段
```

---

## 🎯 执行成功标准

**全部满足以下条件才算成功**：

- ✅ 新仓库 `YunxiBakery` 创建且推送到 GitHub
- ✅ 后端能正常启动，`/health` 返回 200
- ✅ 小程序能用微信开发者工具打开
- ✅ Git 只有 1 个初始 commit
- ✅ 原仓库已备份
- ✅ 没有文件丢失

---

## ❌ 常见问题处理

### 问题 1：PowerShell 脚本执行被阻止

**错误信息**：
```
无法加载文件 xxx.ps1，因为在此系统上禁止运行脚本。
```

**解决方法**：
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### 问题 2：Git 推送失败（权限问题）

**错误信息**：
```
remote: Permission denied
```

**解决方法**：
- 检查 GitHub 凭据
- 或先跳过推送步骤，让项目负责人手动推送

### 问题 3：后端启动失败（缺少依赖）

**错误信息**：
```
ModuleNotFoundError: No module named 'xxx'
```

**解决方法**：
```powershell
pip install -r requirements.txt --force-reinstall
```

### 问题 4：文件复制失败（路径太长）

**错误信息**：
```
路径名太长
```

**解决方法**：
- 先将 `YunxiBakeBot` 改名为 `Bot`
- 先将 `YunxiBakeMiniApp` 改名为 `App`
- 然后重新执行脚本

---

## 📞 需要帮助时

**遇到任何问题，立即停止并报告**：

1. 截图错误信息
2. 记录当前执行到哪一步
3. 复制完整的错误日志
4. 提供给项目负责人

**不要**：
- ❌ 不要自己尝试"修复"脚本
- ❌ 不要删除备份文件
- ❌ 不要跳过验收步骤
- ❌ 不要修改已生成的配置文件

---

## 🎉 执行完成后

**报告内容**：

```
Monorepo 整合已完成！

✅ 新仓库：D:\Project\YunxiBakery
✅ GitHub：https://github.com/srafyhucl-cpu/yunxi-bakery
✅ 备份：D:\Project\_archive_20260817
✅ 所有验收测试通过

已生成以下报告：
- EXECUTION-REPORT.md
- VERIFICATION-CHECKLIST.md

建议项目负责人：
1. 验证 GitHub 仓库内容
2. 阅读《项目重构与推进计划书.md》
3. 准备启动 MVP 开发阶段
```

---

## 📚 相关文档

- `项目重构与推进计划书.md` - 完整战略规划
- `scripts/monorepo-merge.ps1` - 整合脚本源码
- `VERIFICATION-CHECKLIST.md` - 验收检查清单
- `backend/README.md` - 后端说明
- `miniapp/README.md` - 小程序说明

---

**现在开始执行 Step 1！** 🚀
