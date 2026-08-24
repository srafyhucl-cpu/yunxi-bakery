# Platform repo (YunxiBakeBot) PowerShell UTF-8 bootstrap.
# Use this in Windows PowerShell 5.1 before reading Chinese Markdown or Skill files.

[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [Console]::OutputEncoding
$PSDefaultParameterValues['Get-Content:Encoding'] = 'UTF8'
$PSDefaultParameterValues['Set-Content:Encoding'] = 'UTF8'
$PSDefaultParameterValues['Add-Content:Encoding'] = 'UTF8'
$PSDefaultParameterValues['Out-File:Encoding'] = 'UTF8'
$PSDefaultParameterValues['Select-String:Encoding'] = 'UTF8'

try {
    chcp 65001 | Out-Null
} catch {
    Write-Warning "Unable to switch console code page to UTF-8: $($_.Exception.Message)"
}

Write-Host "PowerShell UTF-8 console enabled. Current code page should be 65001." -ForegroundColor Green
