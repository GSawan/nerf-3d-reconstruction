@echo off
echo Starting NeRF Neural Reconstruction Studio...
echo.

:: Start Backend in a new window
echo Starting FastAPI Backend on port 8001...
start "NeRF Backend" cmd /c "cd backend && python -m uvicorn api.main:app --host 127.0.0.1 --port 8001"

:: Start Frontend in a new window
echo Starting Next.js Frontend on port 3001...
start "NeRF Frontend" cmd /c "cd frontend && npm run dev -- -p 3001"

:: Wait a few seconds for servers to initialize
echo Waiting for servers to initialize...
timeout /t 5 /nobreak > nul

:: Open the default web browser
echo Opening website...
start http://localhost:3001

echo Done!
