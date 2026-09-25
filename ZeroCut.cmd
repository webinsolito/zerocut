@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

rem ZeroCut one-click Windows launcher. Prefer fully local/bundled runtimes.
set "ZC_LOG=%~dp0zerocut-launcher.log"
set "ZC_PYTHONW="
set "ZC_APP="

rem PASS 1: bundled Python first, then system Python as a compatibility fallback.
for %%P in ("%~dp0runtime\python\pythonw.exe" "%~dp0runtime\python\python.exe") do if not defined ZC_PYTHONW if exist "%%~P" set "ZC_PYTHONW=%%~P"
if not defined ZC_PYTHONW for %%P in (pythonw.exe python.exe) do if not defined ZC_PYTHONW for /f "delims=" %%I in ('where %%P 2^>nul') do if not defined ZC_PYTHONW set "ZC_PYTHONW=%%I"
if not defined ZC_PYTHONW goto :no_python

rem Select newest candidate runtime without hard-coding a run number.
for /f "delims=" %%F in ('dir /b /o-n "src\ZeroCut_Run*_Candidate_*.pyw" 2^>nul') do if not defined ZC_APP set "ZC_APP=src\%%F"
if not defined ZC_APP goto :no_app

rem PASS 2: prefer private media/AI tools, but preserve PATH fallback inside the app.
if exist "%~dp0runtime\ffmpeg\bin\ffmpeg.exe" set "ZEROCUT_FFMPEG=%~dp0runtime\ffmpeg\bin\ffmpeg.exe"
if exist "%~dp0runtime\ffmpeg\bin\ffprobe.exe" set "ZEROCUT_FFPROBE=%~dp0runtime\ffmpeg\bin\ffprobe.exe"
if exist "%~dp0runtime\whisper" set "ZEROCUT_WHISPER_HOME=%~dp0runtime\whisper"

rem Preflight selected runtime so a broken package fails visibly instead of silently.
"%ZC_PYTHONW%" -c "import pathlib; p=pathlib.Path(r'%~dp0%ZC_APP%'); assert p.is_file() and p.stat().st_size > 100000" >nul 2>>"%ZC_LOG%"
if errorlevel 1 goto :runtime_error

start "ZeroCut" /d "%~dp0" "%ZC_PYTHONW%" "%~dp0%ZC_APP%"
if errorlevel 1 goto :launch_error
exit /b 0

:no_python
>"%ZC_LOG%" echo [%date% %time%] Python runtime non trovato.
echo ZeroCut non trova il runtime Python. Il pacchetto Windows completo deve includere runtime\python.
pause
exit /b 2

:no_app
>"%ZC_LOG%" echo [%date% %time%] Runtime ZeroCut non trovato.
echo File principale ZeroCut non trovato. Ripristina il pacchetto completo.
pause
exit /b 3

:runtime_error
>>"%ZC_LOG%" echo [%date% %time%] Preflight runtime fallito: %ZC_APP%
echo ZeroCut non puo avviarsi: controllo runtime fallito. Dettagli in zerocut-launcher.log.
pause
exit /b 4

:launch_error
>>"%ZC_LOG%" echo [%date% %time%] Avvio fallito: %ZC_APP%
echo ZeroCut non e riuscito ad avviarsi. Dettagli in zerocut-launcher.log.
pause
exit /b 5
