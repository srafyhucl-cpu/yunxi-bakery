# 芸熙烘焙平台 - 本地开发环境一键搭建脚本（Windows）
#
# 试点红线：本脚本只准备「本地开发环境」，不会：
#   - 执行任何生产部署 / 生产发布命令
#   - 连接生产库、真实有赞、真实微信支付、实体打印机
#   - 写入任何真实会员 / 真实交易数据
#
# 用法（仓库根目录执行）：
#     powershell -ExecutionPolicy Bypass -File scripts/setup.ps1
#
# 幂等：可重复执行。已存在的 backend/.env 不会被覆盖。

[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$BackendDir = Join-Path $RepoRoot "backend"
$MiniappDir = Join-Path $RepoRoot "miniapp"
$AdminWebDir = Join-Path $BackendDir "web\admin"
$DataDir = Join-Path $BackendDir "data"
$VenvDir = Join-Path $BackendDir ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$EnvFile = Join-Path $BackendDir ".env"
$EnvExample = Join-Path $BackendDir ".env.example"

# setup.ps1 自动写入随机值的四个密钥（不打印明文）
$GeneratedKeys = @(
    "ADMIN_API_TOKEN",
    "ADMIN_SESSION_SECRET",
    "STAFF_SESSION_SECRET",
    "STOREFRONT_AUTH_SECRET"
)

function Write-Step {
    param([string]$Text)
    Write-Host $Text -ForegroundColor Cyan
}

function Write-Ok {
    param([string]$Text)
    Write-Host $Text -ForegroundColor Green
}

function Write-Warn {
    param([string]$Text)
    Write-Host $Text -ForegroundColor Yellow
}

function Write-Fail {
    param([string]$Text)
    Write-Host $Text -ForegroundColor Red
}

function New-RandomSecret {
    <#
    .SYNOPSIS
    生成密码学安全的随机字符串，用于本地开发密钥。
    .DESCRIPTION
    使用 RandomNumberGenerator 生成随机字节并转 Base64，去掉 + / = 字符，
    保证可直接写入 .env 而不引入转义问题。
    #>
    param([int]$ByteLength = 48)

    $bytes = New-Object byte[] $ByteLength
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $rng.GetBytes($bytes)
    }
    finally {
        $rng.Dispose()
    }
    $text = [System.Convert]::ToBase64String($bytes)
    return $text.Replace("+", "").Replace("/", "").Replace("=", "")
}

function Get-EnvFileValue {
    <#
    .SYNOPSIS
    读取 .env 中某个键的当前值（找不到时返回空字符串）。
    #>
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Key
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        return ""
    }
    $pattern = "(?m)^" + [regex]::Escape($Key) + "=(.*)$"
    $content = [System.IO.File]::ReadAllText($Path)
    $match = [regex]::Match($content, $pattern)
    if (-not $match.Success) {
        return ""
    }
    return $match.Groups[1].Value.Trim()
}

function Set-EnvFileValue {
    <#
    .SYNOPSIS
    就地更新 .env 中某个键的值，保持其余内容与注释不变。
    .DESCRIPTION
    文件始终以 UTF-8（无 BOM）写回，避免 pydantic-settings 读取时首行被 BOM 污染。
    #>
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Key,
        [Parameter(Mandatory = $true)][string]$Value
    )

    $lines = [System.IO.File]::ReadAllLines($Path)
    $pattern = "^" + [regex]::Escape($Key) + "="
    $found = $false
    for ($index = 0; $index -lt $lines.Length; $index++) {
        if ($lines[$index] -match $pattern) {
            $lines[$index] = $Key + "=" + $Value
            $found = $true
        }
    }
    if (-not $found) {
        $lines = $lines + ($Key + "=" + $Value)
    }
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllLines($Path, $lines, $utf8NoBom)
}

function Initialize-NpmCache {
    <#
    .SYNOPSIS
    把 npm 缓存放到非 C 盘（若存在 D 盘），避免污染系统盘。
    #>
    $configured = [System.Environment]::GetEnvironmentVariable("npm_config_cache")
    if (-not [string]::IsNullOrWhiteSpace($configured)) {
        return
    }
    if (Test-Path -LiteralPath "D:\") {
        $cacheDir = "D:\Project\.npm-cache"
        if (-not (Test-Path -LiteralPath $cacheDir)) {
            New-Item -ItemType Directory -Path $cacheDir -Force | Out-Null
        }
        $env:npm_config_cache = $cacheDir
        Write-Host "npm 缓存目录: $cacheDir" -ForegroundColor DarkGray
    }
}

function Invoke-CheckedCommand {
    <#
    .SYNOPSIS
    执行外部命令并检查退出码；失败时只告警不中断整个搭建流程。
    #>
    param(
        [Parameter(Mandatory = $true)][string]$Exe,
        [string[]]$Arguments = @(),
        [Parameter(Mandatory = $true)][string]$What
    )

    & $Exe @Arguments
    if ($LASTEXITCODE -ne 0) {
        Write-Warn "$What 执行失败（退出码 $LASTEXITCODE），请手动重试该步骤。"
    }
}

Write-Host "=== 芸熙烘焙平台 本地开发环境搭建 ===" -ForegroundColor Green
Write-Host "仓库根目录: $RepoRoot" -ForegroundColor DarkGray
Write-Host "本脚本只准备本地环境，不做生产部署、不连生产库、不写真实数据。" -ForegroundColor DarkGray

# ── 1. Python ───────────────────────────────────────────────────────────────
Write-Step "`n[1/6] 检查 Python ..."
$pythonExe = "python"
$pythonPrefix = @()
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        $pythonExe = "py"
        $pythonPrefix = @("-3")
    }
    else {
        Write-Fail "错误: 未找到 Python，请先安装 Python 3.11+"
        exit 1
    }
}
& $pythonExe @pythonPrefix --version
if ($LASTEXITCODE -ne 0) {
    Write-Fail "错误: Python 无法执行，请检查 PATH"
    exit 1
}

# ── 2. 本地数据目录 ─────────────────────────────────────────────────────────
Write-Step "`n[2/6] 准备本地数据目录 backend\data ..."
if (-not (Test-Path -LiteralPath $DataDir)) {
    New-Item -ItemType Directory -Path $DataDir -Force | Out-Null
    Write-Ok "已创建 backend\data（本地 SQLite 库与向量索引都放这里）"
}
else {
    Write-Ok "backend\data 已存在，跳过"
}

# ── 3. 后端虚拟环境与依赖 ───────────────────────────────────────────────────
Write-Step "`n[3/6] 安装后端依赖（backend\.venv）..."
if (-not (Test-Path -LiteralPath $VenvPython)) {
    Write-Host "创建虚拟环境 backend\.venv ..."
    & $pythonExe @pythonPrefix -m venv $VenvDir
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "错误: 创建虚拟环境失败"
        exit 1
    }
}
else {
    Write-Host "虚拟环境已存在，跳过创建"
}
Invoke-CheckedCommand -Exe $VenvPython -Arguments @("-m", "pip", "install", "--upgrade", "pip") -What "pip 升级"
Invoke-CheckedCommand -Exe $VenvPython -Arguments @("-m", "pip", "install", "-r", (Join-Path $BackendDir "requirements.txt")) -What "后端运行时依赖安装"
Invoke-CheckedCommand -Exe $VenvPython -Arguments @("-m", "pip", "install", "-r", (Join-Path $BackendDir "requirements-dev.txt")) -What "后端开发依赖安装（pytest / ruff / mypy）"

# ── 4. 环境变量文件 ─────────────────────────────────────────────────────────
Write-Step "`n[4/6] 准备 backend\.env ..."
if (-not (Test-Path -LiteralPath $EnvExample)) {
    Write-Fail "错误: 缺少 backend\.env.example，无法生成 .env"
    exit 1
}
if (Test-Path -LiteralPath $EnvFile) {
    Write-Warn "backend\.env 已存在，按约定不覆盖。请自行确认下面 4 个密钥是否已配置："
    $pending = @()
    foreach ($key in $GeneratedKeys) {
        $current = Get-EnvFileValue -Path $EnvFile -Key $key
        if ([string]::IsNullOrWhiteSpace($current) -or $current -eq "CHANGE_ME_IN_PRODUCTION_ENV") {
            $pending += $key
        }
    }
    if ($pending.Count -gt 0) {
        Write-Warn ("  待配置: " + ($pending -join ", "))
        Write-Warn "  未配置时后端会拒绝启动 / 店员登录会返回 503，请手工填入随机值。"
    }
    else {
        Write-Ok "  4 个密钥均已配置"
    }
}
else {
    Copy-Item -LiteralPath $EnvExample -Destination $EnvFile
    Set-EnvFileValue -Path $EnvFile -Key "ADMIN_API_TOKEN" -Value (New-RandomSecret -ByteLength 32)
    Set-EnvFileValue -Path $EnvFile -Key "ADMIN_SESSION_SECRET" -Value (New-RandomSecret -ByteLength 48)
    Set-EnvFileValue -Path $EnvFile -Key "STAFF_SESSION_SECRET" -Value (New-RandomSecret -ByteLength 48)
    Set-EnvFileValue -Path $EnvFile -Key "STOREFRONT_AUTH_SECRET" -Value (New-RandomSecret -ByteLength 48)
    Write-Ok "已由 .env.example 生成 backend\.env，并写入 4 个随机密钥（不在此打印明文）"
    Write-Host "  查看方式: Get-Content backend\.env | Select-String '^ADMIN_API_TOKEN='" -ForegroundColor DarkGray
}

# ── 5. 小程序依赖 ───────────────────────────────────────────────────────────
Write-Step "`n[5/6] 安装小程序依赖（miniapp）..."
Initialize-NpmCache
if (Test-Path -LiteralPath (Join-Path $MiniappDir "package.json")) {
    Push-Location -LiteralPath $MiniappDir
    try {
        Invoke-CheckedCommand -Exe "npm" -Arguments @("install") -What "小程序依赖安装"
    }
    finally {
        Pop-Location
    }
}
else {
    Write-Warn "未找到 miniapp\package.json，跳过"
}

# ── 6. 管理后台依赖 ─────────────────────────────────────────────────────────
Write-Step "`n[6/6] 安装管理后台依赖（backend\web\admin）..."
if (Test-Path -LiteralPath (Join-Path $AdminWebDir "package.json")) {
    Push-Location -LiteralPath $AdminWebDir
    try {
        if (Test-Path -LiteralPath (Join-Path $AdminWebDir "package-lock.json")) {
            Invoke-CheckedCommand -Exe "npm" -Arguments @("ci") -What "管理后台依赖安装(npm ci)"
        }
        else {
            Invoke-CheckedCommand -Exe "npm" -Arguments @("install") -What "管理后台依赖安装(npm install)"
        }
    }
    finally {
        Pop-Location
    }
}
else {
    Write-Warn "未找到 backend\web\admin\package.json，跳过"
}

# ── 后续步骤提示 ────────────────────────────────────────────────────────────
$py = "backend\.venv\Scripts\python.exe"

Write-Host ""
Write-Host "=== 环境搭建完成，接下来的步骤 ===" -ForegroundColor Green
Write-Host ""
Write-Host "[1] 启动后端（新开一个 PowerShell 窗口，仓库根目录）:" -ForegroundColor Cyan
Write-Host "    cd backend"
Write-Host "    .\.venv\Scripts\Activate.ps1"
Write-Host "    python -m uvicorn app.main:app --host 127.0.0.1 --port 7001 --reload"
Write-Host "    验证: Invoke-RestMethod http://127.0.0.1:7001/health"
Write-Host "    接口文档(本地 ENABLE_API_DOCS=true): http://127.0.0.1:7001/docs"
Write-Host ""
Write-Host "[2] 启动管理后台（另开一个窗口，仓库根目录）:" -ForegroundColor Cyan
Write-Host "    cd backend\web\admin"
Write-Host "    npm run dev"
Write-Host "    访问: http://127.0.0.1:5173/admin/"
Write-Host "    登录密码 = backend\.env 里的 ADMIN_API_TOKEN（登录页输入该 token）"
Write-Host "    常用页面: /admin/daily-stock、/admin/print-jobs、/admin/quick-order"
Write-Host ""
Write-Host "[3] 打开小程序（微信开发者工具）:" -ForegroundColor Cyan
Write-Host "    用「微信开发者工具」导入目录: $MiniappDir"
Write-Host "    开发版默认连本地后端 http://127.0.0.1:7001（小程序 services/config.ts）"
Write-Host ""
Write-Host "[4] 创建店员账号（仓库根目录执行，PIN 交互输入，不回显）:" -ForegroundColor Cyan
Write-Host "    $py backend\scripts\manage_staff.py create --name 店员A --phone 13800000001 --role cashier"
Write-Host ""
Write-Host "[5] 导入 30 条 FAQ 种子（先干跑再入库）:" -ForegroundColor Cyan
Write-Host "    $py backend\scripts\seed_bakery_faq.py --dry-run"
Write-Host "    $py backend\scripts\seed_bakery_faq.py --apply"
Write-Host ""
Write-Host "[6] 导入合成储值余额（先干跑再入账）:" -ForegroundColor Cyan
Write-Host "    $py backend\scripts\import_youzan_stored_value.py --source backend/tests/fixtures/youzan_stored_value_synthetic.csv --dry-run"
Write-Host "    $py backend\scripts\import_youzan_stored_value.py --source backend/tests/fixtures/youzan_stored_value_synthetic.csv --apply"
Write-Host "    注意: 该合成夹具故意含 4 行脏数据，dry-run/apply 都会以退出码 1 拒绝入账（预期行为）"
Write-Host ""
Write-Host "完整试点手册（含 Mock 打印、快捷开单、常见问题）:" -ForegroundColor Green
Write-Host "    backend\docs\release\local-trial-runbook.md" -ForegroundColor Green
Write-Host ""
Write-Host "红线提醒: 只用合成数据；不接真实会员、真实支付、实体打印机、生产库。" -ForegroundColor Yellow
Write-Host ""
