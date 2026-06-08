$py = "$PSScriptRoot\..\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    $py = "python"
}
& $py "$PSScriptRoot\..\bootstrap.py" $args

