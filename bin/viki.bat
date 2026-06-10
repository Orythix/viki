@echo off
set "ENTRY=%~dp0..\src\viki\cli.py"
if exist "%~dp0..\.venv\Scripts\python.exe" (
    "%~dp0..\.venv\Scripts\python.exe" "%ENTRY%" %*
) else (
    python "%ENTRY%" %*
)

