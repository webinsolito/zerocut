from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "ZeroCut.cmd"
MANIFEST = ROOT / "runtime" / "active_runtime.txt"
REQUIRED = ROOT / "runtime" / "active_runtime.required.txt"
PROBE = ROOT / "tests" / "run119_launcher_probe.pyw"
text = LAUNCHER.read_text(encoding="utf-8")

assert 'cd /d "%~dp0"' in text
assert "runtime\\python\\python.exe" in text
assert "runtime\\python\\pythonw.exe" in text
assert "sys.version_info >= (3, 11)" in text
assert "runtime\\active_runtime.txt" in text
assert "active_runtime.required.txt" in text
assert "ZEROCUT_APP_OVERRIDE" in text
assert "ZEROCUT_LAUNCHER_WAIT" in text
assert "ZEROCUT_LAUNCHER_NO_PAUSE" in text
assert "ZEROCUT_LAUNCH_DIR" in text
assert "runtime\\ffmpeg\\bin" in text
assert "ZEROCUT_FFMPEG" in text and "ZEROCUT_FFPROBE" in text
assert 'set "PATH=%~dp0runtime\\ffmpeg\\bin;%PATH%"' in text
assert "zerocut-launcher.log" in text
assert "ZEROCUT_ROOT=%~dp0" in text
assert "ZEROCUT_APP_ABS" in text
assert "os.environ['ZEROCUT_ROOT']" in text
assert "os.environ['ZEROCUT_APP_ABS']" in text
assert "p.is_relative_to(root)" in text
assert 'start "ZeroCut"' in text
assert '"%ZC_APP_ABS%" %*' in text
for code in (0, 2, 3, 4, 5, 6, 7):
    assert f"exit /b {code}" in text

assert PROBE.is_file(), "Missing Windows process handoff probe"
assert MANIFEST.is_file(), "Missing active runtime manifest"
assert REQUIRED.is_file(), "Missing runtime dependency manifest"

rel = MANIFEST.read_text(encoding="utf-8").strip()
assert rel and not Path(rel).is_absolute(), "Runtime manifest must be package-relative"
target = (ROOT / Path(rel.replace("\\", "/"))).resolve()
assert target.is_relative_to(ROOT.resolve()), "Runtime manifest escapes package root"
assert target.is_file(), f"Configured runtime missing: {target}"
assert re.match(r"ZeroCut_Run\d+_Candidate_.*\.pyw$", target.name), target.name
assert target.name == "ZeroCut_Run119_Candidate_WindowsReadiness.pyw"

required_rows = [x.strip() for x in REQUIRED.read_text(encoding="utf-8").splitlines() if x.strip()]
assert required_rows[0].endswith("ZeroCut_Run119_Candidate_WindowsReadiness.pyw")
required_paths = [(ROOT / Path(x.replace("\\", "/"))).resolve() for x in required_rows]
assert len(required_paths) >= 5
assert all(p.is_relative_to(ROOT.resolve()) and p.is_file() and p.stat().st_size > 500 for p in required_paths)

runtime_text = target.read_text(encoding="utf-8")
assert "ZeroCut_Run118_Candidate_ExportQC.pyw" in runtime_text
assert "--ready-file" in runtime_text
assert '"/api/health"' in runtime_text
assert "os.replace(tmp, READY_FILE)" in runtime_text
chain_text = "\n".join(p.read_text(encoding="utf-8") for p in required_paths)
assert "zerocut-export-qc-run118" in chain_text, "Export QC wrapper missing"
assert "zerocut-transcript-editor-run117" in chain_text, "Transcript UI wrapper missing"
assert "install_whisper_runtime" in chain_text, "Local Whisper bootstrap missing"
assert "ZEROCUT_LAUNCH_DIR" in chain_text, "Launcher media-path contract not consumed"

print("ZEROCUT_RUN119_LAUNCHER_CONTRACT=PASS")
print("RUN119_ACTIVE_RUNTIME=", target.name, "CHAIN_FILES=", len(required_paths))
