@echo off
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

echo ============================================
echo   NeRF 3D Reconstruction Studio
echo   Upload -> COLMAP -> 3D Viewer (Three.js)
echo ============================================
echo.

:: Start Backend in a new window
echo [1/2] Starting FastAPI Backend on port 8001...
start "NeRF Backend" cmd /k "chcp 65001 && set PYTHONUTF8=1 && cd /d %~dp0backend && python -m uvicorn api.main:app --host 127.0.0.1 --port 8001 --reload"

:: Wait a moment for backend to start
timeout /t 4 /nobreak >nul

:: Start Frontend in a new window  
echo [2/2] Starting Next.js Frontend on port 3001...
start "NeRF Frontend" cmd /k "cd /d %~dp0frontend && npm run dev -- -p 3001"

:: Wait for frontend to initialize
echo Waiting for servers to initialize...
timeout /t 10 /nobreak >nul

:: Open browser
echo Opening your website...
start http://localhost:3001

echo.
echo Both servers are now running!
echo   Backend:  http://localhost:8001
echo   Frontend: http://localhost:3001
echo.
echo WORKFLOW:
echo   1. Go to http://localhost:3001
echo   2. Click "Neo3D iT !" to go to Upload page
echo   3. Upload your 20+ photos of an object
echo   4. Click "Start Reconstruction"
echo   5. Wait for COLMAP to build the 3D model
echo   6. View the 3D model directly IN THE WEBSITE!
echo.
echo To stop: Close the two cmd windows (NeRF Backend, NeRF Frontend)
