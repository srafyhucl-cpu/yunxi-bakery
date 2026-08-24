# Monorepo 整合验收检查清单

**执行日期**：2026-08-17  
**执行人**：AI 开发助手  
**检查时间**：_____________

---

## 📋 基础检查

### 目录结构
- [ ] 新仓库 `D:\Project\YunxiBakery` 已创建
- [ ] 原仓库已备份到 `D:\Project\_archive_20260817\YunxiBakeBot_backup`
- [ ] 原仓库已备份到 `D:\Project\_archive_20260817\YunxiBakeMiniApp_backup`
- [ ] `backend/` 目录存在且包含完整后端代码
- [ ] `miniapp/` 目录存在且包含完整小程序代码
- [ ] `docs/` 目录存在且包含文档
- [ ] `scripts/` 目录存在且包含脚本

### 关键文件
- [ ] `README.md` 存在（统一入口文档）
- [ ] `LOGBOOK.md` 存在（已合并）
- [ ] `AGENTS.md` 存在（已合并）
- [ ] `.gitignore` 存在（合并后的忽略规则）
- [ ] `项目重构与推进计划书.md` 存在
- [ ] `EXECUTION-GUIDE.md` 存在
- [ ] `scripts/monorepo-merge.ps1` 存在
- [ ] `scripts/setup.ps1` 存在

### 后端文件完整性
- [ ] `backend/app/` 目录存在
- [ ] `backend/tests/` 目录存在
- [ ] `backend/scripts/` 目录存在
- [ ] `backend/requirements.txt` 存在
- [ ] `backend/.env.example` 存在
- [ ] `backend/README.md` 存在

### 小程序文件完整性
- [ ] `miniapp/miniprogram/` 目录存在
- [ ] `miniapp/package.json` 存在
- [ ] `miniapp/project.config.json` 存在
- [ ] `miniapp/scripts/` 目录存在

---

## 🧪 功能测试

### 后端启动测试
```powershell
cd D:\Project\YunxiBakery\backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 7001 --reload
```

- [ ] 虚拟环境创建成功
- [ ] 依赖安装成功（无错误）
- [ ] 服务器启动成功
- [ ] 访问 `http://127.0.0.1:7001/health` 返回 200
- [ ] 访问 `http://127.0.0.1:7001/docs` 能看到 API 文档
- [ ] 按 Ctrl+C 能正常停止

**测试结果**：✅ 通过 / ❌ 失败

**如果失败，记录错误信息**：
```
（粘贴错误日志）
```

---

### 小程序打开测试

- [ ] 用微信开发者工具能打开 `miniapp` 目录
- [ ] 项目配置加载正常
- [ ] 没有明显的编译错误

**测试结果**：✅ 通过 / ❌ 失败

**如果失败，记录错误信息**：
```
（粘贴错误日志）
```

---

## 🔧 Git 配置检查

### Git 初始化
```powershell
cd D:\Project\YunxiBakery
git log --oneline
git status
```

- [ ] Git 仓库已初始化
- [ ] 只有 1 个初始 commit
- [ ] Commit 信息包含 "chore: 初始化Monorepo"
- [ ] `git status` 显示 working tree clean

**Commit Hash**：_______________

---

### Git 远端配置
```powershell
git remote -v
```

- [ ] `origin` 远端已添加（指向 GitHub）
- [ ] `server` 远端已添加（指向生产服务器）

**预期输出**：
```
origin  https://github.com/srafyhucl-cpu/yunxi-bakery.git (fetch)
origin  https://github.com/srafyhucl-cpu/yunxi-bakery.git (push)
server  ssh://root@47.94.102.250/opt/apps/yunxibakebot/.git (fetch)
server  ssh://root@47.94.102.250/opt/apps/yunxibakebot/.git (push)
```

**实际输出**：
```
（粘贴实际输出）
```

---

### GitHub 推送测试

- [ ] 成功推送到 GitHub
- [ ] 在 GitHub 网页能看到新仓库
- [ ] 文件结构正确（backend/ 和 miniapp/ 可见）

**GitHub 仓库 URL**：https://github.com/srafyhucl-cpu/yunxi-bakery

---

## 📄 文档检查

### README.md
- [ ] 包含项目简介
- [ ] 包含快速开始指南
- [ ] 包含文档导航链接
- [ ] 包含技术栈说明

### LOGBOOK.md
- [ ] 包含后端历史记录
- [ ] 包含小程序历史记录标题
- [ ] 格式正确（Markdown）

### AGENTS.md
- [ ] 包含后端开发规范
- [ ] 如果小程序有规范，已合并
- [ ] 格式正确（Markdown）

---

## ⚠️ 问题记录

### 遇到的问题

**问题 1**：
- 描述：
- 严重程度：🔴 严重 / 🟡 中等 / 🟢 轻微
- 解决方法：
- 状态：✅ 已解决 / ⏳ 待解决

**问题 2**：
- 描述：
- 严重程度：
- 解决方法：
- 状态：

**问题 3**：
- 描述：
- 严重程度：
- 解决方法：
- 状态：

**如无问题，请写**：无

---

## 📊 总体评估

### 完成度统计

- 基础检查：___/20 项通过
- 功能测试：___/2 项通过
- Git 配置：___/3 项通过
- 文档检查：___/4 项通过

**总计**：___/29 项通过

### 最终结论

- [ ] ✅ 全部通过，整合成功
- [ ] ⚠️ 大部分通过，有小问题需修复
- [ ] ❌ 多项失败，需要重新执行

---

## 🎯 后续建议

### 立即执行
- [ ] 通知项目负责人验证 GitHub 仓库
- [ ] 保留备份文件至少 1 个月
- [ ] 阅读《项目重构与推进计划书.md》

### 下一阶段准备
- [ ] 准备启动 MVP 开发
- [ ] 和店家对齐 MVP 范围
- [ ] 给 AI 下达 MVP 开发指令

---

## ✍️ 签名确认

**检查人**：_________________  
**检查日期**：2026-08-17  
**检查结果**：✅ 通过 / ❌ 失败

**备注**：
```
（任何额外说明）
```

---

**检查清单填写完成后，请将此文件保存并提交给项目负责人审核。**
