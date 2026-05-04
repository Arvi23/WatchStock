@echo off
echo ============================================
echo   WatchStock - Setup
echo   Run this once before first launch.
echo ============================================
echo.

REM ---- Step 1: Check Python ----
echo [1/4] Checking Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo  [ERROR] Python was not found.
    echo.
    echo  Please install Python 3.10 or newer from:
    echo    https://www.python.org/downloads/
    echo.
    echo  IMPORTANT: On the installer, check the box that says
    echo  "Add Python to PATH" before clicking Install.
    echo.
    echo  After installing, run this setup again.
    echo.
    pause
    exit /b 1
)
for /f "tokens=*" %%i in ('python --version') do echo   Found: %%i
echo.

REM ---- Step 2: Create virtual environment ----
echo [2/4] Setting up virtual environment...
if not exist ".venv" (
    python -m venv .venv
    echo   Created.
) else (
    echo   Already exists, skipping.
)
echo.

call .venv\Scripts\activate.bat

REM ---- Step 3: Install dependencies ----
echo [3/4] Installing dependencies...
echo   This may take a few minutes on the first run.
echo.
python -m pip install --upgrade pip --quiet
pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo  [ERROR] Dependency installation failed.
    echo  Check that you have an internet connection and try again.
    echo.
    pause
    exit /b 1
)
echo.

REM ---- Step 4: Pre-download NLP model ----
echo [4/4] Downloading AI model (one-time, ~90MB)...
echo   Please wait, this may take a minute...
echo.
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2'); print('  Model ready.')"
if errorlevel 1 (
    echo.
    echo  [WARNING] Model download failed. The app will try again on first launch.
    echo  Make sure you have an internet connection.
    echo.
)

echo.
echo ============================================
echo   Setup complete!
echo.
echo   - To set your API keys: launch the app and
echo     open Settings from the main screen.
echo.
echo   - To start the app: run start.bat
echo ============================================
echo.
pause
