# 芸熙烘焙平台 - Monorepo 整合脚本
# 版本: 1.0
# 日期: 2026-08-17
# 用途: 将 YunxiBakeBot 和 YunxiBakeMiniApp 合并为 YunxiBakery

# 设置编码
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

# 设置错误处理
$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "=====================================================" -ForegroundColor Cyan
Write-Host "  芸熙烘焙平台 Monorepo 整合脚本" -ForegroundColor Cyan
Write-Host "=====================================================" -ForegroundColor Cyan
Write-Host ""

# 定义路径
$ProjectRoot = "D:\Project"
$BackendPath = "$ProjectRoot\YunxiBakeBot"
$MiniappPath = "$ProjectRoot\YunxiBakeMiniApp"
$NewRepoPath = "$ProjectRoot\YunxiBakery"
$BackupPath = "$ProjectRoot\_archive_20260817"

# MVP 基线来源：mvp-2027-june 分支的 git worktree（基于 master b30b2066）
# 依据架构评审 R1：MVP 必须基于 master 基线，不得从 D1 审阅分支复制
$BackendWorktreePath = "C:\Users\srafy\AppData\Local\Temp\opencode\master-export"

# ============================================
# 隐私数据与运行时产物排除清单（依据架构评审 A1）
# backend\data 含 24,726 条真实客户主档，绝对不能进入新仓库
# ============================================
$BackendExclusions = @(
    "data",              # 客户数据库 bot.db（隐私红线）
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".pytest-tmp-*",
    "htmlcov",
    "coverage.xml",
    ".coverage",
    "ngrok.exe",         # 二进制工具不应入库
    ".venv"
)
$MiniappExclusions = @(
    "node_modules",
    ".codex-tmp",
    "reports"
)

# ============================================
# Step 1: 检查前置条件
# ============================================
Write-Host "[Step 0/8] 检查前置条件..." -ForegroundColor Yellow

if (-not (Test-Path $BackendPath)) {
    Write-Host "错误: 找不到后端目录 $BackendPath" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path $MiniappPath)) {
    Write-Host "错误: 找不到小程序目录 $MiniappPath" -ForegroundColor Red
    exit 1
}

if (Test-Path $NewRepoPath) {
    Write-Host "警告: 目标目录 $NewRepoPath 已存在" -ForegroundColor Yellow
    $confirm = Read-Host "是否删除并重新创建? (yes/no)"
    if ($confirm -eq "yes") {
        Remove-Item -Path $NewRepoPath -Recurse -Force
        Write-Host "已删除现有目录" -ForegroundColor Green
    } else {
        Write-Host "操作已取消" -ForegroundColor Red
        exit 0
    }
}

Write-Host "[✓] 前置条件检查通过" -ForegroundColor Green
Write-Host ""

# ============================================
# Step 1: 备份原仓库
# ============================================
Write-Host "[Step 1/8] 备份原仓库..." -ForegroundColor Yellow

if (-not (Test-Path $BackupPath)) {
    New-Item -ItemType Directory -Path $BackupPath | Out-Null
}

Write-Host "  备份后端到 $BackupPath\YunxiBakeBot_backup" -ForegroundColor Gray
Copy-Item -Path $BackendPath -Destination "$BackupPath\YunxiBakeBot_backup" -Recurse -Force

Write-Host "  备份小程序到 $BackupPath\YunxiBakeMiniApp_backup" -ForegroundColor Gray
Copy-Item -Path $MiniappPath -Destination "$BackupPath\YunxiBakeMiniApp_backup" -Recurse -Force

Write-Host "[✓] Step 1/8: 备份完成" -ForegroundColor Green
Write-Host ""

# ============================================
# Step 2: 创建新目录结构
# ============================================
Write-Host "[Step 2/8] 创建新目录结构..." -ForegroundColor Yellow

New-Item -ItemType Directory -Path $NewRepoPath | Out-Null
New-Item -ItemType Directory -Path "$NewRepoPath\backend" | Out-Null
New-Item -ItemType Directory -Path "$NewRepoPath\miniapp" | Out-Null
New-Item -ItemType Directory -Path "$NewRepoPath\docs" | Out-Null
New-Item -ItemType Directory -Path "$NewRepoPath\scripts" | Out-Null

Write-Host "[✓] Step 2/8: 目录结构创建完成" -ForegroundColor Green
Write-Host ""

# ============================================
# Step 3: 复制后端文件（从 mvp-2027-june worktree）
# ============================================
Write-Host "[Step 3/8] 复制后端文件（master 基线）..." -ForegroundColor Yellow

if (-not (Test-Path "$BackendWorktreePath\app")) {
    Write-Host "错误: 找不到 MVP worktree $BackendWorktreePath" -ForegroundColor Red
    Write-Host "请先执行: git worktree add <路径> mvp-2027-june" -ForegroundColor Red
    exit 1
}

$worktreeVersion = Get-Content "$BackendWorktreePath\VERSION" -Raw -ErrorAction SilentlyContinue
Write-Host "  基线版本: $($worktreeVersion.Trim())（应为 0.132.9，B3.5 冻结基线）" -ForegroundColor Gray

# 复制所有文件
Copy-Item -Path "$BackendWorktreePath\*" -Destination "$NewRepoPath\backend\" -Recurse -Force -Exclude ".git"

# 删除 backend 下的 .git 指针文件/目录（如果存在）
if (Test-Path "$NewRepoPath\backend\.git") {
    Remove-Item -Path "$NewRepoPath\backend\.git" -Recurse -Force
    Write-Host "  已删除 backend\.git" -ForegroundColor Gray
}

# 应用隐私数据与运行时产物排除清单（A1）
foreach ($item in $BackendExclusions) {
    $target = Join-Path "$NewRepoPath\backend" $item
    if (Test-Path $target) {
        Remove-Item -Path $target -Recurse -Force
        Write-Host "  已排除 backend\$item（隐私/运行时产物）" -ForegroundColor Gray
    }
}

Write-Host "[✓] Step 3/8: 后端文件复制完成" -ForegroundColor Green
Write-Host ""

# ============================================
# Step 4: 复制小程序文件
# ============================================
Write-Host "[Step 4/8] 复制小程序文件..." -ForegroundColor Yellow

# 复制所有文件
Copy-Item -Path "$MiniappPath\*" -Destination "$NewRepoPath\miniapp\" -Recurse -Force -Exclude ".git"

# 删除 miniapp 下的 .git 目录（如果存在）
if (Test-Path "$NewRepoPath\miniapp\.git") {
    Remove-Item -Path "$NewRepoPath\miniapp\.git" -Recurse -Force
    Write-Host "  已删除 miniapp\.git" -ForegroundColor Gray
}

# 应用运行时产物排除清单（A1）
foreach ($item in $MiniappExclusions) {
    $target = Join-Path "$NewRepoPath\miniapp" $item
    if (Test-Path $target) {
        Remove-Item -Path $target -Recurse -Force
        Write-Host "  已排除 miniapp\$item（运行时产物）" -ForegroundColor Gray
    }
}

Write-Host "[✓] Step 4/8: 小程序文件复制完成" -ForegroundColor Green
Write-Host ""

# ============================================
# Step 5: 整理文档结构
# ============================================
Write-Host "[Step 5/8] 整理文档结构..." -ForegroundColor Yellow

# 移动后端 docs 到根目录
if (Test-Path "$NewRepoPath\backend\docs") {
    Copy-Item -Path "$NewRepoPath\backend\docs\*" -Destination "$NewRepoPath\docs\" -Recurse -Force
    Write-Host "  已移动后端文档到根 docs/" -ForegroundColor Gray
}

# 合并 LOGBOOK.md
Write-Host "  合并 LOGBOOK.md..." -ForegroundColor Gray
$logbookContent = @()
if (Test-Path "$NewRepoPath\backend\LOGBOOK.md") {
    $logbookContent += Get-Content "$NewRepoPath\backend\LOGBOOK.md" -Raw -Encoding UTF8
}
$logbookContent += "`n`n## 小程序变更记录`n"
if (Test-Path "$NewRepoPath\miniapp\LOGBOOK.md") {
    $logbookContent += Get-Content "$NewRepoPath\miniapp\LOGBOOK.md" -Raw -Encoding UTF8
}
$logbookContent -join "" | Out-File -FilePath "$NewRepoPath\LOGBOOK.md" -Encoding UTF8

# 合并 AGENTS.md
Write-Host "  合并 AGENTS.md..." -ForegroundColor Gray
$agentsContent = @()
if (Test-Path "$NewRepoPath\backend\AGENTS.md") {
    $agentsContent += Get-Content "$NewRepoPath\backend\AGENTS.md" -Raw -Encoding UTF8
}
if (Test-Path "$NewRepoPath\miniapp\AGENTS.md") {
    $agentsContent += "`n`n## 小程序开发规范`n"
    $agentsContent += Get-Content "$NewRepoPath\miniapp\AGENTS.md" -Raw -Encoding UTF8
}
$agentsContent -join "" | Out-File -FilePath "$NewRepoPath\AGENTS.md" -Encoding UTF8

# 复制进度清单
if (Test-Path "$NewRepoPath\backend\项目进度与配置清单.md") {
    Copy-Item -Path "$NewRepoPath\backend\项目进度与配置清单.md" -Destination "$NewRepoPath\" -Force
    Write-Host "  已复制项目进度清单" -ForegroundColor Gray
}

Write-Host "[✓] Step 5/8: 文档结构整理完成" -ForegroundColor Green
Write-Host ""

# ============================================
# Step 6: 生成新的配置文件
# ============================================
Write-Host "[Step 6/8] 生成新的配置文件..." -ForegroundColor Yellow

# 6.1 生成统一 README.md
Write-Host "  生成 README.md..." -ForegroundColor Gray
$readmeContent = @"
# 芸熙烘焙智能经营平台

一个基于 AI 的烘焙店智能客服与经营系统。

## 项目结构

- **backend/** - FastAPI 后端服务（Python 3.11+）
- **miniapp/** - 微信小程序前端（TypeScript）
- **docs/** - 统一文档中心
- **scripts/** - 跨项目脚本和工具

## 快速开始

### 环境要求

- Python 3.11+
- Node.js 18+
- Git

### 后端开发

``````bash
cd backend
python -m venv .venv
.venv\Scripts\activate  # Windows
pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 7001 --reload
``````

访问：http://127.0.0.1:7001/docs

### 小程序开发

``````bash
cd miniapp
npm install
# 用微信开发者工具打开 miniapp 目录
``````

## 文档导航

- [架构说明](docs/architecture/) - 系统架构和设计决策
- [API 契约](docs/api-contracts/) - 前后端接口规范
- [开发规范](AGENTS.md) - AI 协作和编码规范
- [变更日志](LOGBOOK.md) - 项目演进记录
- [进度清单](项目进度与配置清单.md) - 当前版本和待办事项

## 重要文档

- [项目重构与推进计划书](项目重构与推进计划书.md) - 战略规划和路线图
- [执行指南](EXECUTION-GUIDE.md) - Monorepo 整合说明

## 部署

生产部署见 [scripts/deploy.sh](scripts/deploy.sh)

## 技术栈

**后端**：
- FastAPI - Web 框架
- SQLite - 数据库
- LangChain - AI 应用框架
- Pydantic - 数据验证

**前端**：
- 微信小程序原生框架
- TypeScript
- 微信开放能力

## 项目状态

- 当前版本：v0.1.0（MVP 开发阶段）
- 目标上线：2027 年 6 月
- 商业状态：单店铺试用，未来可能扩展多租户

## Monorepo 整合说明

本仓库由以下两个项目合并而成：
- YunxiBakeBot（后端 Platform）
- YunxiBakeMiniApp（小程序 Storefront）

整合日期：2026-08-17
"@
$readmeContent | Out-File -FilePath "$NewRepoPath\README.md" -Encoding UTF8

# 6.2 生成合并后的 .gitignore
Write-Host "  生成 .gitignore..." -ForegroundColor Gray
$gitignoreContent = @"
# Python
__pycache__/
*.py[cod]
*`$py.class
*.so
.Python
.venv/
venv/
ENV/
env/

# 测试和覆盖率
.pytest_cache/
.coverage
htmlcov/
coverage.xml
*.cover

# 数据库
*.db
*.sqlite
*.sqlite3

# 日志
*.log
logs/

# 环境变量
.env
.env.local

# IDE
.vscode/
.idea/
*.swp
*.swo

# Node.js（小程序）
node_modules/
npm-debug.log*

# 微信小程序
miniapp/miniprogram/node_modules/
miniapp/miniprogram/.tea/

# 构建产物
dist/
build/
*.egg-info/

# 备份和临时文件
*.bak
*.tmp
_archive*/
reports/harness/*.md

# 系统文件
.DS_Store
Thumbs.db

# Ruff cache
.ruff_cache/

# Coverage
.coverage.*
"@
$gitignoreContent | Out-File -FilePath "$NewRepoPath\.gitignore" -Encoding UTF8

# 6.3 生成环境搭建脚本
Write-Host "  生成 scripts/setup.ps1..." -ForegroundColor Gray
$setupScript = @"
# 芸熙烘焙平台 - 开发环境一键搭建脚本
# 适用于 Windows

Write-Host "=== 芸熙烘焙平台环境搭建 ===" -ForegroundColor Green

# 检查 Python
Write-Host "``n[1/4] 检查 Python 版本..." -ForegroundColor Cyan
python --version
if (`$LASTEXITCODE -ne 0) {
    Write-Host "错误: 未找到 Python，请先安装 Python 3.11+" -ForegroundColor Red
    exit 1
}

# 设置后端
Write-Host "``n[2/4] 设置后端环境..." -ForegroundColor Cyan
cd backend
if (-not (Test-Path .venv)) {
    python -m venv .venv
}
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 检查 .env
if (-not (Test-Path .env)) {
    Write-Host "警告: 未找到 .env 文件，请复制 .env.example 并填写配置" -ForegroundColor Yellow
    if (Test-Path .env.example) {
        Copy-Item .env.example .env
    }
}

cd ..

# 设置小程序
Write-Host "``n[3/4] 设置小程序环境..." -ForegroundColor Cyan
cd miniapp
npm install
cd ..

# 完成
Write-Host "``n[4/4] 环境搭建完成！" -ForegroundColor Green
Write-Host "后端启动: cd backend && .venv\Scripts\Activate.ps1 && python -m uvicorn app.main:app --reload"
Write-Host "小程序: 用微信开发者工具打开 miniapp 目录"
"@
$setupScript | Out-File -FilePath "$NewRepoPath\scripts\setup.ps1" -Encoding UTF8

# 6.4 复制本脚本到新仓库
Copy-Item -Path $PSCommandPath -Destination "$NewRepoPath\scripts\" -Force

Write-Host "[✓] Step 6/8: 配置文件生成完成" -ForegroundColor Green
Write-Host ""

# ============================================
# Step 7: 初始化 Git 仓库
# ============================================
Write-Host "[Step 7/8] 初始化 Git 仓库..." -ForegroundColor Yellow

cd $NewRepoPath
git init
git branch -m main

Write-Host "[✓] Step 7/8: Git 仓库初始化完成" -ForegroundColor Green
Write-Host ""

# ============================================
# Step 8: 第一次提交（前置隐私断言）
# ============================================
Write-Host "[Step 8/8] 创建第一次提交..." -ForegroundColor Yellow

# 隐私数据硬门禁（A1）：任何数据库文件/二进制工具不得入库
$privacyViolations = @()
foreach ($pattern in @("backend\data", "backend\*.db", "backend\*.sqlite*", "backend\ngrok.exe")) {
    $matches2 = Get-ChildItem -Path "$NewRepoPath\$pattern" -ErrorAction SilentlyContinue
    if ($matches2) {
        $privacyViolations += $matches2.FullName
    }
}
if ($privacyViolations.Count -gt 0) {
    Write-Host "错误: 检测到隐私数据或违禁文件，禁止提交！" -ForegroundColor Red
    $privacyViolations | ForEach-Object { Write-Host "  - $_" -ForegroundColor Red }
    exit 1
}

# 确认 Git 跟踪清单中无数据库文件
$trackedDb = git -C $NewRepoPath ls-files | Select-String -Pattern "\.db$|\.sqlite|ngrok\.exe"
if ($trackedDb) {
    Write-Host "错误: Git 跟踪清单中检测到数据库/二进制文件，禁止提交！" -ForegroundColor Red
    $trackedDb | ForEach-Object { Write-Host "  - $_" -ForegroundColor Red }
    exit 1
}

Write-Host "[✓] 隐私断言通过：无数据库文件入库" -ForegroundColor Green

git add .
git commit -m "chore: 初始化Monorepo（合并YunxiBakeBot后端和YunxiBakeMiniApp小程序）

- 后端：FastAPI + SQLite + LangChain（基于 master b30b2066 B3.5 冻结基线 v0.132.9）
- 小程序：微信小程序前端
- 文档：统一架构和API契约文档
- 整合日期：2026-08-17（按架构评审修正版执行：排除隐私数据与运行时产物）
- 基线版本：backend v0.132.9, miniapp v0.1.0"

Write-Host "[✓] Step 8/8: 第一次提交完成" -ForegroundColor Green
Write-Host ""

# ============================================
# 完成提示
# ============================================
Write-Host "=====================================================" -ForegroundColor Green
Write-Host "  ✅ Monorepo 整合完成！" -ForegroundColor Green
Write-Host "=====================================================" -ForegroundColor Green
Write-Host ""
Write-Host "新仓库路径: $NewRepoPath" -ForegroundColor Cyan
Write-Host "备份路径: $BackupPath" -ForegroundColor Cyan
Write-Host ""
Write-Host "下一步操作:" -ForegroundColor Yellow
Write-Host "  1. 验证后端能否启动" -ForegroundColor White
Write-Host "     cd $NewRepoPath\backend" -ForegroundColor Gray
Write-Host "     python -m venv .venv" -ForegroundColor Gray
Write-Host "     .\.venv\Scripts\Activate.ps1" -ForegroundColor Gray
Write-Host "     pip install -r requirements.txt" -ForegroundColor Gray
Write-Host "     python -m uvicorn app.main:app --host 127.0.0.1 --port 7001 --reload" -ForegroundColor Gray
Write-Host ""
Write-Host "  2. 推送到 GitHub" -ForegroundColor White
Write-Host "     cd $NewRepoPath" -ForegroundColor Gray
Write-Host "     git remote add origin https://github.com/srafyhucl-cpu/yunxi-bakery.git" -ForegroundColor Gray
Write-Host "     git push -u origin main" -ForegroundColor Gray
Write-Host ""
Write-Host "  3. 添加生产服务器远端" -ForegroundColor White
Write-Host "     git remote add server ssh://root@47.94.102.250/opt/apps/yunxibakebot/.git" -ForegroundColor Gray
Write-Host ""
Write-Host "详细说明见: $NewRepoPath\EXECUTION-GUIDE.md" -ForegroundColor Cyan
Write-Host ""
