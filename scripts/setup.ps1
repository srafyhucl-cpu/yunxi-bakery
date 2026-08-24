# 芸熙烘焙平台 - 开发环境一键搭建脚本
# 适用于 Windows

Write-Host "=== 芸熙烘焙平台环境搭建 ===" -ForegroundColor Green

# 检查 Python
Write-Host "`n[1/4] 检查 Python 版本..." -ForegroundColor Cyan
python --version
if ($LASTEXITCODE -ne 0) {
    Write-Host "错误: 未找到 Python，请先安装 Python 3.11+" -ForegroundColor Red
    exit 1
}

# 设置后端
Write-Host "`n[2/4] 设置后端环境..." -ForegroundColor Cyan
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
Write-Host "`n[3/4] 设置小程序环境..." -ForegroundColor Cyan
cd miniapp
npm install
cd ..

# 完成
Write-Host "`n[4/4] 环境搭建完成！" -ForegroundColor Green
Write-Host "后端启动: cd backend && .venv\Scripts\Activate.ps1 && python -m uvicorn app.main:app --reload"
Write-Host "小程序: 用微信开发者工具打开 miniapp 目录"
