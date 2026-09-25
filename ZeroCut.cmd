@echo off
setlocal EnableExtensions
cd /d "%~dp0"

rem ZeroCut one-click Windows launcher. Prefer fully local/bundled runtimes.
set "ZC_LOG=%~dp0zerocut-launcher.log"
set "ZC_PYTHON="
set "ZC_PYTHONW="
set "ZC_APP="
set "ZC_APP_ABS="
set "ZEROCUT_ROOT=%~dp0"

rem Prefer bundled Python so the final Windows package does not depend on user PATH.
if exist "%~dp0runtime\python\python.exe" set "ZC_PYTHON=%~dp0runtime\python\python.exe"
if exist "%~dp0runtime\python\pythonw.exe" set "ZC_PYTHONW=%~dp0runtime\python\pythonw.exe"
if not defined ZC_PYTHON for /f "delims=" %%I in ('where python.exe 2^>nul') do if not defined ZC_PYTHON set "ZC_PYTHON=%%I"
if not defined ZC_PYTHONW for /f "delims=" %%I in ('where pythonw.exe 2^>nul') do if not defined ZC_PYTHONW set "ZC_PYTHONW=%%I"
if not defined ZC_PYTHON if defined ZC_PYTHONW set "ZC_PYTHON=%ZC_PYTHONW%"
if not defined ZC_PYTHONW if defined ZC_PYTHON set "ZC_PYTHONW=%ZC_PYTHON%"
if not defined ZC_PYTHON goto :no_python
"%ZC_PYTHON%" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>>"%ZC_LOG%"
if errorlevel 1 goto :python_version

rem Source of truth: explicit full-runtime manifest. Test override is isolated and opt-in.
if defined ZEROCUT_APP_OVERRIDE (
  set "ZC_APP=%ZEROCUT_APP_OVERRIDE%"
) else (
  if not exist "%~dp0runtime\active_runtime.txt" goto :no_manifest
  set /p ZC_APP=<"%~dp0runtime\active_runtime.txt"
)
if not defined ZC_APP goto :no_app
for %%F in ("%ZC_APP%") do set "ZC_APP_ABS=%%~fF"
set "ZEROCUT_APP_ABS=%ZC_APP_ABS%"

rem Integrate bundled FFmpeg with the contract consumed by the active ZeroCut runtime.
if exist "%~dp0runtime\ffmpeg\bin\ffmpeg.exe" if exist "%~dp0runtime\ffmpeg\bin\ffprobe.exe" (
  set "ZEROCUT_LAUNCH_DIR=%~dp0runtime\ffmpeg\bin"
  set "ZEROCUT_FFMPEG=%~dp0runtime\ffmpeg\bin\ffmpeg.exe"
  set "ZEROCUT_FFPROBE=%~dp0runtime\ffmpeg\bin\ffprobe.exe"
  set "PATH=%~dp0runtime\ffmpeg\bin;%PATH%"
)

rem Preflight: entrypoint and every declared runtime dependency must exist inside the package.
"%ZC_PYTHON%" -c "import os; from pathlib import Path; root=Path(os.environ['ZEROCUT_ROOT']).resolve(); p=Path(os.environ['ZEROCUT_APP_ABS']).resolve(); assert p.is_relative_to(root) and p.is_file(); req=root/'runtime'/'active_runtime.required.txt'; rows=[x.strip() for x in req.read_text(encoding='utf-8').splitlines() if x.strip()] if req.is_file() and not os.environ.get('ZEROCUT_APP_OVERRIDE') else []; deps=[(root/Path(x.replace('\\','/'))).resolve() for x in rows]; assert all(x.is_relative_to(root) and x.is_file() and x.stat().st_size>500 for x in deps)" >nul 2>>"%ZC_LOG%"
if errorlevel 1 goto :runtime_error

rem CI can wait for a short probe; normal user launch returns immediately with no terminal left open.
if defined ZEROCUT_LAUNCHER_WAIT (
  start "ZeroCut" /wait /d "%~dp0" "%ZC_PYTHONW%" "%ZC_APP_ABS%" %*
) else (
  start "ZeroCut" /d "%~dp0" "%ZC_PYTHONW%" "%ZC_APP_ABS%" %*
)
if errorlevel 1 goto :launch_error
exit /b 0

:no_python
>>"%ZC_LOG%" echo [%date% %time%] Python runtime non trovato.
echo ZeroCut non trova il runtime Python. Ripristina il pacchetto Windows completo.
if not defined ZEROCUT_LAUNCHER_NO_PAUSE pause
exit /b 2

:python_version
>>"%ZC_LOG%" echo [%date% %time%] Versione Python non supportata.
echo ZeroCut richiede Python 3.11 o superiore. Ripristina il pacchetto Windows completo.
if not defined ZEROCUT_LAUNCHER_NO_PAUSE pause
exit /b 7

:no_manifest
>>"%ZC_LOG%" echo [%date% %time%] Manifest runtime mancante.
echo Configurazione ZeroCut incompleta: runtime\active_runtime.txt mancante.
if not defined ZEROCUT_LAUNCHER_NO_PAUSE pause
exit /b 6

:no_app
>>"%ZC_LOG%" echo [%date% %time%] Runtime ZeroCut non configurato.
echo File principale ZeroCut non configurato.
if not defined ZEROCUT_LAUNCHER_NO_PAUSE pause
exit /b 3

:runtime_error
>>"%ZC_LOG%" echo [%date% %time%] Preflight runtime fallito: %ZC_APP_ABS%
echo ZeroCut non puo avviarsi: controllo runtime fallito. Dettagli in zerocut-launcher.log.
if not defined ZEROCUT_LAUNCHER_NO_PAUSE pause
exit /b 4

:launch_error
>>"%ZC_LOG%" echo [%date% %time%] Avvio fallito: %ZC_APP_ABS%
echo ZeroCut non e riuscito ad avviarsi. Dettagli in zerocut-launcher.log.
if not defined ZEROCUT_LAUNCHER_NO_PAUSE pause
exit /b 5
