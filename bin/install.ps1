# VIKI CLI one-line install (Windows PowerShell)
# Usage: irm https://raw.githubusercontent.com/Orythix/viki/main/bin/install.ps1 | iex
# Or from repo: .\bin/install.ps1

$ErrorActionPreference = "Stop"
$repoDir = if ($PSScriptRoot) { $PSScriptRoot } else { Get-Location }
$repoRoot = (Get-Item "$repoDir\..").FullName
Set-Location $repoRoot
Write-Host "Installing VIKI from $repoRoot ..."
pip install -e .
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "Done. Run 'viki' from any directory (e.g. viki . or viki C:\path\to\project)."
