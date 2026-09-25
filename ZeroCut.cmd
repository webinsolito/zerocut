@echo off
setlocal EnableExtensions
cd /d "%~dp0"

rem ZeroCut one-click Windows launcher. No console is kept open after handoff.
set "ZC_PYTHONW="
for %%P in (pythonw.exe python.exe) do (
  if not defined ZC_PYTHONW for /f "delims=" %%I in ('where %%P 2^>nul') do if not defined ZC_PYTHONW set "ZC_PYTHONW=%%I"
)
if not defined ZC_PYTHONW (
  echo ZeroCut non trova Python. Installa Python 3.11+ una sola volta e riapri ZeroCut.
  pause
  exit /b 2
)

set "ZC_APP="
for /f "delims=" %%F in ('dir /b /o-n "src\ZeroCut_Run*_Candidate_*.pyw" 2^>nul') do if not defined ZC_APP set "ZC_APP=src\%%F"
if not defined ZC_APP (
  echo File principale ZeroCut non trovato.
  pause
  exit /b 3
)

rem Prefer private/bundled media tools without requiring PATH changes.
if exist "%~dp0runtime\ffmpeg\bin\ffmpeg.exe" set "ZEROCUT_FFMPEG=%~dp0runtime\ffmpeg\bin\ffmpeg.exe"
if exist "%~dp0runtime\ffmpeg\bin\ffprobe.exe" set "ZEROCUT_FFPROBE=%~dp0runtime\ffmpeg\bin\ffprobe.exe"
if exist "%~dp0runtime\whisper" set "ZEROCUT_WHISPER_HOME=%~dp0runtime\whisper"

start "ZeroCut" /d "%~dp0" "%ZC_PYTHONW%" "%~dp0%ZC_APP%"
exit /b 0
