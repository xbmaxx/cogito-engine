@echo off
REM Cogito Engine — Windows installer
REM Usage: install.bat [--update] [--platform <name>] [--dry-run]

setlocal

REM Check Python
python --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Python not found. Install Python 3.9+ from https://python.org
    exit /b 1
)

REM Install dependencies
pip install -r "%CD%\requirements.txt" >nul 2>&1

REM Run installer
python "%CD%\install.py" %*

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Installation encountered errors. See output above.
    exit /b 1
)

echo.
echo Done. Restart your agent to activate Cogito Engine.
