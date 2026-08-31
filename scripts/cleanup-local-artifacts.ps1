[CmdletBinding()]
param(
    [string]$Workspace = "",
    [switch]$Execute,
    [string[]]$TemporaryPath = @(),
    [switch]$OnlyTemporaryPath,
    [string]$PreviewToken = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($Workspace)) {
    $Workspace = Split-Path -Parent $PSScriptRoot
}
$workspacePath = (Resolve-Path -LiteralPath $Workspace).Path
$defaultTargets = @(
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
    (Join-Path $workspacePath "miniapp\.codex-tmp"),
    (Join-Path $workspacePath "backend\.ruff_cache"),
    (Join-Path $workspacePath "backend\.mypy_cache"),
    (Join-Path $workspacePath "backend\.pytest_cache"),
    (Join-Path $workspacePath "backend\htmlcov"),
    (Join-Path $workspacePath "backend\.venv"),
    (Join-Path $workspacePath "backend\web\admin\node_modules")
)
$targets = [System.Collections.Generic.List[string]]@()
if (-not $OnlyTemporaryPath) {
    $defaultTargets | ForEach-Object { [void]$targets.Add([string]$_) }
}
$fileTargets = @(
    (Join-Path $workspacePath ".coverage"),
    (Join-Path $workspacePath "coverage.xml"),
    (Join-Path $workspacePath "backend\.coverage"),
    (Join-Path $workspacePath "backend\coverage.xml"),
    (Join-Path $workspacePath "coverage.out")
)
$duplicateReport = Join-Path $workspacePath "miniapp\reports\miniprogram-ci\miniprogram-ci-readiness-20260826-010232.json"
$externalTemporaryRoots = @(
    "D:\Temp"
)
$protectedPathRoots = @(
    (Join-Path $workspacePath "backend\data"),
    (Join-Path $workspacePath "backend\reports"),
    (Join-Path $workspacePath "miniapp\reports"),
    (Join-Path $workspacePath ".git")
)
if ($OnlyTemporaryPath) {
    $fileTargets = @()
}

function Resolve-CleanupPath {
    param([string]$Path)

    if (Test-Path -LiteralPath $Path) {
        return [System.IO.Path]::GetFullPath((Resolve-Path -LiteralPath $Path).Path)
    }
    return [System.IO.Path]::GetFullPath($Path)
}

function Assert-WorkspacePath {
    param([string]$Path)

    $resolved = Resolve-CleanupPath -Path $Path
    $prefix = $workspacePath.TrimEnd([System.IO.Path]::DirectorySeparatorChar) + [System.IO.Path]::DirectorySeparatorChar
    if (-not $resolved.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "拒绝处理工作区外路径: $resolved"
    }
    if ($resolved.Equals($workspacePath, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "拒绝把工作区根目录作为清理目标: $resolved"
    }
}

function Test-SameOrChildPath {
    param(
        [string]$Path,
        [string]$Root
    )

    $resolvedPath = Resolve-CleanupPath -Path $Path
    $resolvedRoot = Resolve-CleanupPath -Path $Root
    if ($resolvedPath.Equals($resolvedRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        return $true
    }
    $prefix = $resolvedRoot.TrimEnd([System.IO.Path]::DirectorySeparatorChar) + [System.IO.Path]::DirectorySeparatorChar
    return $resolvedPath.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase)
}

function Assert-NotProtectedPath {
    param([string]$Path)

    $resolved = Resolve-CleanupPath -Path $Path
    $duplicateResolved = Resolve-CleanupPath -Path $duplicateReport
    for ($protectedRootIndex = 0; $protectedRootIndex -lt $protectedPathRoots.Count; $protectedRootIndex++) {
        $protectedRoot = [string]$protectedPathRoots[$protectedRootIndex]
        if (-not (Test-SameOrChildPath -Path $resolved -Root $protectedRoot)) {
            continue
        }
        if ($resolved.Equals($duplicateResolved, [System.StringComparison]::OrdinalIgnoreCase)) {
            continue
        }
        throw "拒绝处理受保护路径: $resolved"
    }
    $leaf = Split-Path -Leaf $resolved
    if ($leaf -like ".env*" -and $leaf -ne ".env.example") {
        throw "拒绝处理环境文件: $resolved"
    }
}

function Assert-CleanupTarget {
    param([string]$Path)

    $resolved = Resolve-CleanupPath -Path $Path
    $inWorkspace = Test-SameOrChildPath -Path $resolved -Root $workspacePath
    $inExternalTemporaryRoot = $false
    for ($temporaryRootIndex = 0; $temporaryRootIndex -lt $externalTemporaryRoots.Count; $temporaryRootIndex++) {
        $temporaryRoot = [string]$externalTemporaryRoots[$temporaryRootIndex]
        if (Test-SameOrChildPath -Path $resolved -Root $temporaryRoot) {
            $inExternalTemporaryRoot = $true
            break
        }
    }
    if (-not ($inWorkspace -or $inExternalTemporaryRoot)) {
        throw "清理目标必须位于工作区或 D:\Temp 下: $resolved"
    }
    Assert-NotProtectedPath -Path $resolved
}

function Assert-CustomTemporaryPath {
    param([string]$Path)

    $resolved = Resolve-CleanupPath -Path $Path
    $inWorkspace = Test-SameOrChildPath -Path $resolved -Root $workspacePath
    $inExternalTemporaryRoot = $false
    for ($temporaryRootIndex = 0; $temporaryRootIndex -lt $externalTemporaryRoots.Count; $temporaryRootIndex++) {
        $temporaryRoot = [string]$externalTemporaryRoots[$temporaryRootIndex]
        if (Test-SameOrChildPath -Path $resolved -Root $temporaryRoot) {
            $inExternalTemporaryRoot = $true
            break
        }
    }
    if (-not ($inWorkspace -or $inExternalTemporaryRoot)) {
        throw "自定义临时目录必须位于工作区或 D:\Temp 下: $resolved"
    }
    Assert-NotProtectedPath -Path $resolved
    $leaf = Split-Path -Leaf $resolved
    if ($leaf -notmatch "^(\.tmp-|pytest-)") {
        throw "自定义临时目录必须使用 .tmp- 或 pytest- 前缀: $resolved"
    }
}

# Python 运行时会在各级源码目录生成可重建的 __pycache__，纳入同一清理清单。
$pythonCacheDirectories = @()
if (-not $OnlyTemporaryPath) {
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
    $pythonCacheDirectories | ForEach-Object { [void]$targets.Add([string]$_) }
}
$customTargets = @()
if ($OnlyTemporaryPath -and $TemporaryPath.Count -eq 0) {
    throw "使用 -OnlyTemporaryPath 时必须至少提供一个 -TemporaryPath"
}
for ($temporaryPathIndex = 0; $temporaryPathIndex -lt $TemporaryPath.Count; $temporaryPathIndex++) {
    $temporaryPathValue = [string]($TemporaryPath[$temporaryPathIndex])
    if ([string]::IsNullOrWhiteSpace($temporaryPathValue)) {
        continue
    }
    $candidate = if ([System.IO.Path]::IsPathRooted($temporaryPathValue)) {
        $temporaryPathValue
    } else {
        Join-Path $workspacePath $temporaryPathValue
    }
    Assert-CustomTemporaryPath -Path $candidate
    $customTargets += $candidate
}
$customTargets | ForEach-Object { [void]$targets.Add([string]$_) }
$targets = @($targets | Sort-Object -Unique)

function Get-TargetFiles {
    param([string]$Root)

    if (-not (Test-Path -LiteralPath $Root)) {
        return @()
    }
    return @(Get-ChildItem -LiteralPath $Root -Force -File -Recurse -ErrorAction SilentlyContinue)
}

function Get-PreviewToken {
    param([string[]]$Records)

    $payload = [string]::Join("`n", $Records)
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($payload)
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        return ([System.BitConverter]::ToString($sha.ComputeHash($bytes))).Replace("-", "").ToLowerInvariant()
    } finally {
        $sha.Dispose()
    }
}

foreach ($target in $targets) {
    Assert-CleanupTarget -Path $target
}
foreach ($fileTarget in $fileTargets) {
    Assert-CleanupTarget -Path $fileTarget
}
if (-not $OnlyTemporaryPath) {
    Assert-WorkspacePath -Path $duplicateReport
}

$previewRecords = [System.Collections.Generic.List[string]]@()
foreach ($target in $targets) {
    $resolvedTarget = Resolve-CleanupPath -Path $target
    if (-not (Test-Path -LiteralPath $target)) {
        [void]$previewRecords.Add("TARGET|$resolvedTarget|missing")
        continue
    }
    [void]$previewRecords.Add("TARGET|$resolvedTarget|present")
    foreach ($file in @(Get-TargetFiles -Root $target)) {
        [void]$previewRecords.Add(
            ("FILE|{0}|{1}|{2}" -f $file.FullName, $file.Length, $file.LastWriteTimeUtc.Ticks)
        )
    }
}
foreach ($fileTarget in $fileTargets) {
    $resolvedFileTarget = Resolve-CleanupPath -Path $fileTarget
    if (Test-Path -LiteralPath $fileTarget -PathType Leaf) {
        $file = Get-Item -LiteralPath $fileTarget -Force
        [void]$previewRecords.Add(
            ("FILE_TARGET|{0}|{1}|{2}" -f $resolvedFileTarget, $file.Length, $file.LastWriteTimeUtc.Ticks)
        )
    } else {
        [void]$previewRecords.Add("FILE_TARGET|$resolvedFileTarget|missing")
    }
}
if (-not $OnlyTemporaryPath) {
    [void]$previewRecords.Add(
        ("DUPLICATE_REPORT|{0}|{1}" -f (Resolve-CleanupPath -Path $duplicateReport), (Test-Path -LiteralPath $duplicateReport))
    )
}
$expectedPreviewToken = Get-PreviewToken -Records @($previewRecords)

if (-not $Execute) {
    Write-Output "预览模式：不会删除文件。使用 -Execute 执行白名单内临时/可重建目录的递归批量清理。"
    if ($OnlyTemporaryPath) {
        Write-Output "范围模式：仅处理显式 -TemporaryPath 目录。"
    }
    Write-Output ("清理目标数: {0}" -f $targets.Count)
    Write-Output ("预览授权令牌: {0}" -f $expectedPreviewToken)
    foreach ($target in $targets) {
        $files = @(Get-TargetFiles -Root $target)
        Write-Output ("{0}: {1} 个文件" -f $target, $files.Count)
    }
    foreach ($fileTarget in $fileTargets) {
        Write-Output ("{0}: {1}" -f $fileTarget, (Test-Path -LiteralPath $fileTarget -PathType Leaf))
    }
    if (-not $OnlyTemporaryPath) {
        Write-Output ("重复报告存在: {0}" -f (Test-Path -LiteralPath $duplicateReport))
    }
    exit 0
}

if ([string]::IsNullOrWhiteSpace($PreviewToken)) {
    throw "执行递归清理必须携带预览授权令牌；请先运行预览模式并传入 -PreviewToken。"
}
if (-not [System.StringComparer]::OrdinalIgnoreCase.Equals($PreviewToken.Trim(), $expectedPreviewToken)) {
    throw "预览授权令牌不匹配；目标路径或文件状态可能已变化，请重新预览。"
}

$cleanupMode = "递归批量删除白名单目录及其可重建内容；不触碰白名单外路径。"
Write-Output ("清理模式: {0}" -f $cleanupMode)

$summary = @()
foreach ($target in $targets) {
    if (-not (Test-Path -LiteralPath $target)) {
        continue
    }
    $files = @(Get-TargetFiles -Root $target)
    foreach ($file in $files) {
        Assert-NotProtectedPath -Path $file.FullName
    }
    $count = $files.Count
    $bytes = [int64]0
    if ($files.Count -gt 0) {
        $bytes = [int64](($files | Measure-Object -Property Length -Sum).Sum)
    }
    if (Test-Path -LiteralPath $target -PathType Container) {
        Remove-Item -LiteralPath $target -Recurse -Force
    } else {
        Remove-Item -LiteralPath $target -Force
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

if (-not $OnlyTemporaryPath -and (Test-Path -LiteralPath $duplicateReport)) {
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
if (-not $OnlyTemporaryPath) {
    Write-Output ("{0} exists={1}" -f $duplicateReport, (Test-Path -LiteralPath $duplicateReport))
}
