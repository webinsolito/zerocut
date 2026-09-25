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
    $Launcher = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($Launcher) {
        & $Launcher.Source -3.13 -m venv $Venv
    } else {
        $SystemPython = (Get-Command python.exe -ErrorAction Stop).Source
        & $SystemPython -m venv $Venv
    }
}

if (!$SkipInstall) {
    & $Python -m pip install --disable-pip-version-check --upgrade pip
    & $Python -m pip install --disable-pip-version-check "pyinstaller==6.16.0"
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
