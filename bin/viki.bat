@echo off
if exist "%~dp0..\.venv\Scripts\python.exe" (
    "%~dp0..\.venv\Scripts\python.exe" "%~dp0..\bootstrap.py" %*
) else (
    python "%~dp0..\bootstrap.py" %*
)

