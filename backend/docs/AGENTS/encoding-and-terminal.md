# 中文编码与终端乱码处理

本项目默认使用 UTF-8。Windows PowerShell 5.1 的默认读取编码可能不是 UTF-8，因此直接执行 `Get-Content file.md` 时可能出现中文乱码。遇到乱码时，先判断是终端解码问题，不要急着改文件内容。

______________________________________________________________________

## 一次性修复当前终端

在项目根目录执行：

```powershell
.\scripts\enable_utf8_console.ps1
```

脚本会设置当前 PowerShell 会话的输入/输出编码为 UTF-8，并尝试切换控制台代码页到 `65001`。
同时会设置常用文本命令的默认编码：

```powershell
$PSDefaultParameterValues['Get-Content:Encoding'] = 'UTF8'
$PSDefaultParameterValues['Set-Content:Encoding'] = 'UTF8'
$PSDefaultParameterValues['Add-Content:Encoding'] = 'UTF8'
$PSDefaultParameterValues['Out-File:Encoding'] = 'UTF8'
$PSDefaultParameterValues['Select-String:Encoding'] = 'UTF8'
```

______________________________________________________________________

## 持久化修复新终端

已在当前用户 PowerShell profile 中加入带标记的 UTF-8 初始化片段。新开的 Windows PowerShell 会自动执行：

```powershell
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [Console]::OutputEncoding
chcp 65001
$PSDefaultParameterValues['Get-Content:Encoding'] = 'UTF8'
$PSDefaultParameterValues['Set-Content:Encoding'] = 'UTF8'
$PSDefaultParameterValues['Add-Content:Encoding'] = 'UTF8'
$PSDefaultParameterValues['Out-File:Encoding'] = 'UTF8'
$PSDefaultParameterValues['Select-String:Encoding'] = 'UTF8'
```

如果某些旧工具在 UTF-8 代码页下异常，可以临时执行：

```powershell
chcp 936
```

______________________________________________________________________

## 读取中文文件的稳妥命令

在 PowerShell 5.1 中读取 Markdown、Skill 和中文文档时，优先显式指定编码：

```powershell
Get-Content -Raw -Encoding UTF8 AGENTS.md
Get-Content -Raw -Encoding UTF8 docs/AGENTS/skill-reference.md
Get-Content -Raw -Encoding UTF8 .agents/skills/yunxi-harness-engineering/SKILL.md
```

报告 JSON 如果带 UTF-8 BOM，脚本读取建议使用：

```powershell
Get-Content reports/preflight-before-20260611-093000.json -Raw -Encoding UTF8 | ConvertFrom-Json
```

______________________________________________________________________

## 判断文件是否真的坏了

如果 `Get-Content -Encoding UTF8` 能正常显示中文，说明文件内容没坏，只是终端或默认编码读错了。

如果显式 UTF-8 读取仍出现 `U+FFFD replacement character`，或出现典型 UTF-8/GBK mojibake 字符串，才需要检查文件本身是否已经被错误编码写回。为避免检查器误判，本说明文档不直接内联乱码样本。

______________________________________________________________________

## 写文件约定

- Python 使用 `encoding="utf-8"` 读取文本文件。
- 需要给 Windows 用户双击或 PowerShell 默认读取的 JSON/Markdown 报告，可使用 UTF-8 BOM。
- 命令行工具输出中文时，脚本应优先执行 `sys.stdout.reconfigure(encoding="utf-8")`。
- 不要用 PowerShell 默认重定向生成中文文档；优先使用明确编码的脚本或编辑器。
