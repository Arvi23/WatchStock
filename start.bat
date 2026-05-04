@echo off
echo ============================================
echo   Sourcing Buyer Terminal - Starting All
echo ============================================

echo.
echo [1/3] Starting Elasticsearch...
start "Elasticsearch" cmd /c "C:\Users\Arvi23\Desktop\elasticsearch-8.17.0\bin\elasticsearch.bat"

echo [2/3] Starting Kibana...
start "Kibana" cmd /c "C:\Users\Arvi23\Desktop\kibana-8.17.0\bin\kibana.bat"

echo [3/3] Waiting for Elasticsearch to be ready...
:wait_es
timeout /t 3 /nobreak >nul
curl -s http://localhost:9200 >nul 2>&1
if errorlevel 1 (
    echo      Still waiting for ES...
    goto wait_es
)
echo      Elasticsearch is ready!

echo.
echo [3/3] Starting FastAPI server...
echo.
echo ============================================
echo   ES:     http://localhost:9200
echo   Kibana: http://localhost:5601
echo   App:    http://localhost:8000
echo ============================================
echo.

python main.py
