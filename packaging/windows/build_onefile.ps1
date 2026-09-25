param(
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$BuildRoot = Join-Path $Root ".build\windows-onefile"
$Venv = Join-Path $BuildRoot "venv"
$Python = Join-Path $Venv "Scripts\python.exe"
$Dist = Join-Path $Root "dist\windows"
$Work = Join-Path $BuildRoot "work"
$Spec = Join-Path $Root "packaging\windows\ZeroCut.spec"

New-Item -ItemType Directory -Force -Path $BuildRoot, $Dist, $Work | Out-Null

if (!(Test-Path $Python)) {
    $SystemPython = (Get-Command python.exe -ErrorAction SilentlyContinue).Source
    if ($SystemPython) {
        $VersionOk = & $SystemPython -c "import sys; print(int(sys.version_info >= (3, 11)))"
        if ($VersionOk -ne "1") { throw "Python 3.11+ required to build ZeroCut.exe" }
        & $SystemPython -m venv $Venv
    } else {
        $Launcher = Get-Command py.exe -ErrorAction Stop
        & $Launcher.Source -3.13 -m venv $Venv
    }
}
if (!(Test-Path $Python)) { throw "Build virtualenv was not created" }

if (!$SkipInstall) {
    & $Python -m pip install --disable-pip-version-check --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed" }
    & $Python -m pip install --disable-pip-version-check "pyinstaller==6.16.0"
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller install failed" }
}

Remove-Item -Recurse -Force $Dist -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $Dist | Out-Null

& $Python -m PyInstaller --noconfirm --clean --distpath $Dist --workpath $Work $Spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed with exit code $LASTEXITCODE" }

$Exe = Join-Path $Dist "ZeroCut.exe"
if (!(Test-Path $Exe)) { throw "ZeroCut.exe was not created" }
$Size = (Get-Item $Exe).Length
if ($Size -lt 5MB) { throw "ZeroCut.exe is unexpectedly small: $Size bytes" }

$Process = Start-Process -FilePath $Exe -ArgumentList "--ai-status" -Wait -PassThru
if ($Process.ExitCode -ne 0) { throw "Packaged ZeroCut --ai-status failed: $($Process.ExitCode)" }

$Hash = (Get-FileHash -Algorithm SHA256 $Exe).Hash.ToLowerInvariant()
Write-Host "ZEROCUT_ONEFILE_BUILD=PASS"
Write-Host "ZEROCUT_ONEFILE_PATH=$Exe"
Write-Host "ZEROCUT_ONEFILE_BYTES=$Size"
Write-Host "ZEROCUT_ONEFILE_SHA256=$Hash"
