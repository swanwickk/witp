@echo off
setlocal EnableExtensions

cd /d "%~dp0"

rem Check that a 32-bit Python 3 launcher tag is available.
py -3-32 --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo [bootstrap_scraper] ERROR: 32-bit Python 3 was not found.
    echo [bootstrap_scraper] The scraper requires 32-bit Python 3 to access game save files.
    echo [bootstrap_scraper] 32-bit Python cannot be installed automatically via winget on all systems.
    echo [bootstrap_scraper] Please download and install it manually:
    echo.
    echo [bootstrap_scraper]   1. Go to: https://www.python.org/downloads/windows/
    echo [bootstrap_scraper]   2. Choose a Python 3 release and download the "Windows installer (32-bit)" package.
    echo [bootstrap_scraper]   3. Run the installer. On the first screen, check "Add Python to PATH" and
    echo [bootstrap_scraper]      ensure "Install launcher for all users" is selected.
    echo [bootstrap_scraper]   4. After installation restart this script.
    echo.
    pause
    exit /b 1
)

if not exist ".venv32\Scripts\python.exe" (
    echo [bootstrap_scraper] Creating 32-bit virtual environment...
    py -3-32 -m venv ".venv32"
    if errorlevel 1 (
        echo [bootstrap_scraper] ERROR: Failed to create 32-bit venv.
        exit /b 1
    )
)

echo [bootstrap_scraper] Ensuring scraper dependencies are installed...
".venv32\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 (
    echo [bootstrap_scraper] ERROR: Failed to upgrade pip.
    exit /b 1
)
".venv32\Scripts\python.exe" -m pip install --quiet -r requirements.txt
if errorlevel 1 (
    echo [bootstrap_scraper] ERROR: Failed to install dependencies.
    exit /b 1
)

exit /b 0