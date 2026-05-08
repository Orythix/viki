# Registers a Windows Scheduled Task to run VIKI background evolution at user logon.
# Requires: Python on PATH, repo path below updated, optional VIKI_DATA_DIR.
#
# Run in PowerShell as the target user (Administrator not required for "on logon" user task):
#   Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
#   cd "D:\My Projects\VIKI"
#   .\scripts\Register-VikiBootTask.ps1
#
# Remove task: Unregister-ScheduledTask -TaskName "VIKI Boot Evolve" -Confirm:$false

$RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Python = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $Python) {
    Write-Error "python not on PATH"
    exit 1
}
$Script = Join-Path $RepoRoot "scripts\viki_headless_boot_evolve.py"
$Action = New-ScheduledTaskAction -Execute $Python -Argument "`"$Script`"" -WorkingDirectory $RepoRoot
$Trigger = New-ScheduledTaskTrigger -AtLogOn
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
$Principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive
Register-ScheduledTask -TaskName "VIKI Boot Evolve" -Action $Action -Trigger $Trigger -Settings $Settings -Principal $Principal -Force | Out-Null
Write-Host "Registered task 'VIKI Boot Evolve' (logon). Edit task to set VIKI_DATA_DIR in Environment if needed."
