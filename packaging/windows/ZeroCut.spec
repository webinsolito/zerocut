from pathlib import Path

ROOT = Path(SPECPATH).parents[1]
SRC = ROOT / "src"
CHAIN = [
    "ZeroCut_Run121_Candidate_GameplayDirector.pyw",
    "ZeroCut_Run119_Candidate_WindowsReadiness.pyw",
    "ZeroCut_Run118_Candidate_ExportQC.pyw",
    "ZeroCut_Run117_Candidate_TranscriptUI.pyw",
    "ZeroCut_Run113_Candidate_TranscriptEdit.pyw",
    "ZeroCut_Run112_Candidate_WhisperUX.pyw",
]

missing = [name for name in CHAIN if not (SRC / name).is_file()]
if missing:
    raise SystemExit("ZEROCUT_PACKAGE_CHAIN_MISSING:" + ",".join(missing))

datas = [(str(SRC / name), "src") for name in CHAIN]
hiddenimports = [
    "argparse","base64","concurrent.futures","ctypes","dataclasses","hashlib",
    "http.server","importlib","importlib.machinery","importlib.util","json","math",
    "mimetypes","os","platform","re","shutil","statistics","subprocess","tarfile",
    "tempfile","threading","time","urllib.error","urllib.parse","urllib.request",
    "uuid","webbrowser","zipfile","zlib",
]

a = Analysis(
    [str(ROOT / "packaging" / "windows" / "zerocut_onefile_entry.py")],
    pathex=[str(ROOT), str(SRC)], binaries=[], datas=datas, hiddenimports=hiddenimports,
    hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[], noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [], name="ZeroCut", debug=False,
    bootloader_ignore_signals=False, strip=False, upx=False, console=False,
    disable_windowed_traceback=False,
)
