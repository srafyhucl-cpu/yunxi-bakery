[CmdletBinding()]
param(
    [string]$Workspace = "",
    [switch]$Execute
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($Workspace)) {
    $Workspace = Split-Path -Parent $PSScriptRoot
}
$workspacePath = (Resolve-Path -LiteralPath $Workspace).Path
$targets = @(
    (Join-Path $workspacePath ".workbuddy"),
    (Join-Path $workspacePath ".venv"),
    (Join-Path $workspacePath "venv"),
    (Join-Path $workspacePath "env"),
    (Join-Path $workspacePath "ENV"),
    (Join-Path $workspacePath ".ruff_cache"),
    (Join-Path $workspacePath ".mypy_cache"),
    (Join-Path $workspacePath ".pytest_cache"),
    (Join-Path $workspacePath "htmlcov"),
    (Join-Path $workspacePath "node_modules"),
    (Join-Path $workspacePath "miniapp\.ruff_cache"),
    (Join-Path $workspacePath "miniapp\.mypy_cache"),
    (Join-Path $workspacePath "miniapp\.pytest_cache"),
    (Join-Path $workspacePath "miniapp\htmlcov"),
    (Join-Path $workspacePath "miniapp\node_modules"),
    (Join-Path $workspacePath "miniapp\miniprogram\node_modules"),
    (Join-Path $workspacePath "miniapp\miniprogram\.tea"),
    (Join-Path $workspacePath "miniapp\.codex-tmp"),
    (Join-Path $workspacePath "backend\.ruff_cache"),
    (Join-Path $workspacePath "backend\.mypy_cache"),
    (Join-Path $workspacePath "backend\.pytest_cache"),
    (Join-Path $workspacePath "backend\htmlcov"),
    (Join-Path $workspacePath "backend\.venv"),
    (Join-Path $workspacePath "backend\web\admin\node_modules")
)
$fileTargets = @(
    (Join-Path $workspacePath ".coverage"),
    (Join-Path $workspacePath "coverage.xml"),
    (Join-Path $workspacePath "backend\.coverage"),
    (Join-Path $workspacePath "backend\coverage.xml"),
    (Join-Path $workspacePath "coverage.out")
)
$duplicateReport = Join-Path $workspacePath "miniapp\reports\miniprogram-ci\miniprogram-ci-readiness-20260826-010232.json"

# Python 运行时会在各级源码目录生成可重建的 __pycache__，纳入同一清理清单。
$pythonCacheDirectories = @(
    @(
        $workspacePath,
        (Join-Path $workspacePath "backend"),
        (Join-Path $workspacePath "miniapp"),
        (Join-Path $workspacePath "scripts")
    ) |
        Where-Object { Test-Path -LiteralPath $_ -PathType Container } |
        ForEach-Object {
            Get-ChildItem -LiteralPath $_ -Force -Directory -Recurse -Filter "__pycache__" -ErrorAction SilentlyContinue |
                Select-Object -ExpandProperty FullName
        }
)
$targets += $pythonCacheDirectories
$targets = @($targets | Sort-Object -Unique)

function Assert-WorkspacePath {
    param([string]$Path)

    $resolved = [System.IO.Path]::GetFullPath($Path)
    $prefix = $workspacePath.TrimEnd([System.IO.Path]::DirectorySeparatorChar) + [System.IO.Path]::DirectorySeparatorChar
    if (-not $resolved.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "拒绝处理工作区外路径: $resolved"
    }
}

function Get-TargetFiles {
    param([string]$Root)

    if (-not (Test-Path -LiteralPath $Root)) {
        return @()
    }
    return @(Get-ChildItem -LiteralPath $Root -Force -File -Recurse -ErrorAction SilentlyContinue)
}

foreach ($target in $targets) {
    Assert-WorkspacePath -Path $target
}
foreach ($fileTarget in $fileTargets) {
    Assert-WorkspacePath -Path $fileTarget
}
Assert-WorkspacePath -Path $duplicateReport

if (-not $Execute) {
    Write-Output "预览模式：不会删除文件。使用 -Execute 执行逐文件清理。"
    foreach ($target in $targets) {
        $files = @(Get-TargetFiles -Root $target)
        Write-Output ("{0}: {1} 个文件" -f $target, $files.Count)
    }
    foreach ($fileTarget in $fileTargets) {
        Write-Output ("{0}: {1}" -f $fileTarget, (Test-Path -LiteralPath $fileTarget -PathType Leaf))
    }
    Write-Output ("重复报告存在: {0}" -f (Test-Path -LiteralPath $duplicateReport))
    exit 0
}

$summary = @()
foreach ($target in $targets) {
    $files = @(Get-TargetFiles -Root $target)
    $count = 0
    $bytes = [int64]0
    foreach ($file in $files) {
        Remove-Item -LiteralPath $file.FullName -Force
        $count++
        $bytes += [int64]$file.Length
    }
    $summary += [pscustomobject]@{
        Root = $target
        FilesRemoved = $count
        BytesRemoved = $bytes
    }
}

foreach ($fileTarget in $fileTargets) {
    if (Test-Path -LiteralPath $fileTarget -PathType Leaf) {
        $file = Get-Item -LiteralPath $fileTarget -Force
        $length = [int64]$file.Length
        Remove-Item -LiteralPath $fileTarget -Force
        $summary += [pscustomobject]@{
            Root = $fileTarget
            FilesRemoved = 1
            BytesRemoved = $length
        }
    }
}

if (Test-Path -LiteralPath $duplicateReport) {
    Remove-Item -LiteralPath $duplicateReport -Force
    Write-Output ("已删除重复报告: {0}" -f $duplicateReport)
}

$summary | Format-Table -AutoSize
Write-Output "清理后路径状态:"
foreach ($target in $targets) {
    Write-Output ("{0} exists={1}" -f $target, (Test-Path -LiteralPath $target))
}
foreach ($fileTarget in $fileTargets) {
    Write-Output ("{0} exists={1}" -f $fileTarget, (Test-Path -LiteralPath $fileTarget))
}
Write-Output ("{0} exists={1}" -f $duplicateReport, (Test-Path -LiteralPath $duplicateReport))
