from pathlib import Path
import py_compile

ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / "packaging" / "windows" / "zerocut_onefile_entry.py"
SPEC = ROOT / "packaging" / "windows" / "ZeroCut.spec"
BUILD = ROOT / "packaging" / "windows" / "build_onefile.ps1"

for path in (ENTRY, SPEC, BUILD):
    assert path.is_file(), f"Missing packaging file: {path}"

py_compile.compile(str(ENTRY), doraise=True)
entry = ENTRY.read_text(encoding="utf-8")
spec = SPEC.read_text(encoding="utf-8")
build = BUILD.read_text(encoding="utf-8")

assert 'getattr(sys, "_MEIPASS", None)' in entry
assert 'runpy.run_path' in entry
assert 'ZeroCut_Run121_Candidate_GameplayDirector.pyw' in entry

for name in (
    "ZeroCut_Run121_Candidate_GameplayDirector.pyw",
    "ZeroCut_Run119_Candidate_WindowsReadiness.pyw",
    "ZeroCut_Run118_Candidate_ExportQC.pyw",
    "ZeroCut_Run117_Candidate_TranscriptUI.pyw",
    "ZeroCut_Run113_Candidate_TranscriptEdit.pyw",
    "ZeroCut_Run112_Candidate_WhisperUX.pyw",
):
    assert name in spec, name

assert 'name="ZeroCut"' in spec
assert "console=False" in spec
assert "upx=False" in spec
assert 'pyinstaller==6.16.0' in build
assert 'ZeroCut.exe' in build
assert '--ai-status' in build
assert 'Get-FileHash -Algorithm SHA256' in build
assert 'ZEROCUT_ONEFILE_BUILD=PASS' in build
print("ZEROCUT_RUN120_ONEFILE_CONTRACT=PASS")
