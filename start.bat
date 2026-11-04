@echo off
setlocal
cd /d "%~dp0"
title WatchStock

rem ---------------------------------------------------------------------------
rem  WatchStock launcher. Double-click to start. Close the window to stop.
rem  First run installs "uv" (a small Python manager), which then downloads the
rem  right Python version and libraries into this folder. Later runs are fast.
rem ---------------------------------------------------------------------------

where uv >nul 2>&1
if errorlevel 1 (
    if not exist "%USERPROFILE%\.local\bin\uv.exe" (
        echo First run: installing uv...
        powershell -NoProfile -ExecutionPolicy ByPass -Command "irm https://astral.sh/uv/install.ps1 | iex"
    )
    set "PATH=%USERPROFILE%\.local\bin;%PATH%"
)

where uv >nul 2>&1
if errorlevel 1 (
    echo.
    echo [ERROR] Could not install uv. Check the internet connection and try again.
    echo         Manual install: https://docs.astral.sh/uv/getting-started/installation/
    pause
    exit /b 1
)

rem First run only: put a WatchStock shortcut on the Desktop. The marker file means
rem a shortcut the user deleted on purpose doesn't come back. Delete the marker to redo.
if not exist "data\.shortcut-created" call :make_shortcut

echo Starting WatchStock... (the first start can take a few minutes)
uv run --frozen --no-dev python -m watchstock
if errorlevel 1 (
    echo.
    echo [ERROR] WatchStock stopped with an error.
    echo         Details are in data\watchstock.log
    pause
)
exit /b

:make_shortcut
if not exist "data" mkdir "data"
set "APPDIR=%CD%"
powershell -NoProfile -ExecutionPolicy ByPass -Command "$s = (New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop') + '\WatchStock.lnk'); $s.TargetPath = $env:APPDIR + '\start.bat'; $s.WorkingDirectory = $env:APPDIR; $s.Description = 'Start WatchStock'; $s.Save()" >nul 2>&1
if not errorlevel 1 (
    type nul > "data\.shortcut-created"
    echo Created a WatchStock shortcut on your Desktop.
)
exit /b 0
