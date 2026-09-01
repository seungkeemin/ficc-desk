@echo off
REM ficc-desk launcher.
REM
REM This file is deliberately pure ASCII. cmd.exe reads batch files by byte
REM offset, so switching the code page mid-file (chcp) makes it resume at the
REM wrong position and execute fragments of comments as commands. Keep every
REM byte here in ASCII; all logic and all Korean text live in start.ps1.
powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%~dp0start.ps1"
exit /b %errorlevel%
