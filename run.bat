@echo off
title NEXUS Launcher - Smart Attendance System
color 0A
cls
echo.
echo  ============================================
echo    Smart Attendance System - Starting...
echo  ============================================
echo.

cd /d "%~dp0"

REM ── Step 1: Launch backend in its OWN separate window ──
REM (This window stays alive independently. Closing launcher won't kill it.)
start "NEXUS Backend - DO NOT CLOSE" cmd /k "color 0A && echo. && echo  [NEXUS] Backend Running at http://127.0.0.1:5000 && echo  [NEXUS] Keep this window open! && echo. && python backend.py"

REM ── Step 2: Wait for Flask + BLE to fully initialize ──
echo  [1/3] Backend window launched...
timeout /t 2 /nobreak >nul
echo  [2/3] Waiting for server to initialize (8 sec)...
timeout /t 8 /nobreak >nul

REM ── Step 3: Open browser (server is ready now) ──
echo  [3/3] Opening dashboard in browser...
start "" "http://127.0.0.1:5000/"

echo.
echo  ============================================
echo   Dashboard opened! You can close THIS window.
echo   Keep the "NEXUS Backend" window open.
echo  ============================================
echo.
timeout /t 5 /nobreak >nul
exit
