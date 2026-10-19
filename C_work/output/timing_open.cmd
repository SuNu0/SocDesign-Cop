@echo off
where pythonw.exe >nul 2>nul
if not errorlevel 1 (
    start "" pythonw.exe "%~dp0timing_server.py"
    exit /b
)
where python.exe >nul 2>nul
if not errorlevel 1 (
    start "" /min python.exe "%~dp0timing_server.py"
    exit /b
)
echo Python was not found. Open timing_fixed.html in Chrome or Edge.
pause
