param(
    [string]$TaskName = "YunxiBakeBot-Local-Encrypted-Backup",
    [string]$BackupDir = "D:\Backups\YunxiBakeBot",
    [string]$KeyFile = "D:\Backups\YunxiBakeBot\keys\backup.key",
    [string]$SshKey = "$env:USERPROFILE\.ssh\id_ed25519",
    [string]$DailyAt = "03:30"
)

$ErrorActionPreference = "Stop"
$projectDir = Split-Path -Parent $PSScriptRoot
$python = (Get-Command python.exe -ErrorAction Stop).Source
$script = Join-Path $projectDir "scripts\local_production_backup.py"

if (-not (Test-Path -LiteralPath $KeyFile -PathType Leaf)) {
    throw "Backup key does not exist: $KeyFile"
}
if (-not (Test-Path -LiteralPath $SshKey -PathType Leaf)) {
    throw "SSH key does not exist: $SshKey"
}
if (-not ([System.IO.Path]::GetFullPath($BackupDir).StartsWith("D:\", [System.StringComparison]::OrdinalIgnoreCase))) {
    throw "Backup directory must be on drive D"
}

$arguments = @(
    ('"{0}"' -f $script),
    "--backup-dir", ('"{0}"' -f $BackupDir),
    "--key-file", ('"{0}"' -f $KeyFile),
    "--ssh-key", ('"{0}"' -f $SshKey)
) -join " "
$action = New-ScheduledTaskAction -Execute $python -Argument $arguments -WorkingDirectory $projectDir
$trigger = New-ScheduledTaskTrigger -Daily -At $DailyAt
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "Daily production SQLite snapshot encrypted with AES-256-GCM on drive D" `
    -Force | Out-Null

Get-ScheduledTask -TaskName $TaskName | Select-Object TaskName, State
