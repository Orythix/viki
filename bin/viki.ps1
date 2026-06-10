$py = "$PSScriptRoot\..\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    $py = "python"
}
# src/viki/cli.py is the entry point (need src in path)
& $py "$PSScriptRoot\..\src\viki\cli.py" $args

