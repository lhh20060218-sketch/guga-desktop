param([string]$Backup = 'dsh-personal-20261102-130836')
$ErrorActionPreference = 'Stop'
$petRoot = Split-Path $PSScriptRoot -Parent
$backupRoot = [System.IO.Path]::GetFullPath((Join-Path $petRoot ('runtime\upgrades\' + $Backup)))
$allowedRoot = [System.IO.Path]::GetFullPath((Join-Path $petRoot 'runtime\upgrades')) + '\'
if (-not $backupRoot.StartsWith($allowedRoot,[System.StringComparison]::OrdinalIgnoreCase)) { throw '备份路径必须在项目 runtime/upgrades 内' }
$restoreFiles = @('core\dsh_worker.py','core\mcp_contract.py','ui\mcp_bridge.py','tools\guga_mcp_server.py','ui\agent_chat.py','ui\agent_runtime.py','core\self_agent.py','core\agent_memory.py','core\fast_commands.py','tools\frozen_entry.py','README.md','.gitignore')
foreach ($restoreFile in $restoreFiles) {
    $restoreSource = Join-Path $backupRoot $restoreFile
    if (-not (Test-Path -LiteralPath $restoreSource -PathType Leaf)) { throw "备份不完整：$restoreFile" }
}
foreach ($restoreFile in $restoreFiles) { Copy-Item -LiteralPath (Join-Path $backupRoot $restoreFile) -Destination (Join-Path $petRoot $restoreFile) -Force }
$sidecarDoc = Join-Path $backupRoot 'docs-dsh-sidecar.md'
if (Test-Path -LiteralPath $sidecarDoc) { Copy-Item -LiteralPath $sidecarDoc -Destination (Join-Path $petRoot 'docs\dsh-sidecar.md') -Force }
Write-Output '已恢复升级前源码；配置、任务数据和新增研究资料保留。重新打开咕嘎后生效。'
