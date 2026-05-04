@echo off
echo ============================================
echo   WatchStock - Starting
echo ============================================
echo.

if not exist ".venv\Scripts\activate.bat" (
    echo [!] Virtual environment not found.
    echo     Please run setup.bat first.
    echo.
    pause
    exit /b 1
)

call .venv\Scripts\activate.bat

echo Starting server...
echo.
echo   Open your browser at: http://localhost:8000
echo.
echo   Press Ctrl+C to stop.
echo.

REM Open browser after server has had time to start
start "" /B cmd /c "timeout /t 5 /nobreak >nul && start http://localhost:8000"

python main.py
