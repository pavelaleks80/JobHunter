@echo off
rem JobHunter: daily run for Windows Task Scheduler (see docs/scheduling.md)
chcp 65001 >nul
cd /d "%~dp0.."
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -m jobhunter run
) else (
    python -m jobhunter run
)
