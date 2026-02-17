# VIKI CLI one-line install (Windows PowerShell)
# Usage: irm https://raw.githubusercontent.com/toozuuu/viki/main/install.ps1 | iex
# Or from repo: .\install.ps1

$ErrorActionPreference = "Stop"
$repoRoot = if ($PSScriptRoot) { $PSScriptRoot } else { Get-Location }
Set-Location $repoRoot
Write-Host "Installing VIKI from $repoRoot ..."
pip install -e .
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "Done. Run 'viki' from any directory (e.g. viki . or viki C:\path\to\project)."
