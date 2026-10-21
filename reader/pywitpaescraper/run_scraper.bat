@echo off
setlocal EnableExtensions

cd /d "%~dp0"

call "%~dp0bootstrap_scraper.bat"
if errorlevel 1 (
    echo [run_scraper] ERROR: bootstrap failed.
    exit /b 1
)

".venv32\Scripts\python.exe" pywitpaescraper.py %*
exit /b %errorlevel%
