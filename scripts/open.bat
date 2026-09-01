@echo off
REM Open the dashboard in Chrome app mode. Assumes the server is already up.
REM To start the server as well, use start.bat (or the desktop shortcut).
REM
REM App mode removes the tabs, address bar and bookmarks. Without that the
REM 940px vertical budget does not hold (SPEC 4-5a). F11 fullscreen works too.
REM
REM Start the server separately:
REM   .venv\Scripts\python -m uvicorn ficc.app:app --port 8787
REM
REM Pure ASCII on purpose: cmd.exe reads batch files by byte offset, so any
REM code page mismatch garbles output and, with chcp, can split lines mid-word
REM and execute comment fragments as commands. Korean text lives in .ps1 files.

REM 127.0.0.1, not localhost: uvicorn listens on IPv4 only, and on Windows
REM localhost resolves to ::1 first, so every request burns ~2s falling back.

setlocal
set URL=http://127.0.0.1:8787/

set CHROME=%ProgramFiles%\Google\Chrome\Application\chrome.exe
if not exist "%CHROME%" set CHROME=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe
if not exist "%CHROME%" set CHROME=%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe
if not exist "%CHROME%" (
  echo Chrome not found. Opening the default browser instead.
  echo Press F11 for fullscreen, otherwise the page will scroll.
  start "" "%URL%"
  exit /b 0
)

start "" "%CHROME%" --app=%URL% --window-size=1920,1080 --window-position=0,0
endlocal
