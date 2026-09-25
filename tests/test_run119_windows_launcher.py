from pathlib import Path
import py_compile
import re

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "ZeroCut.cmd"
MANIFEST = ROOT / "runtime" / "active_runtime.txt"
REQUIRED = ROOT / "runtime" / "active_runtime.required.txt"
READY_CHECK = ROOT / "runtime" / "verify_ready.py"
PROBE = ROOT / "tests" / "run119_launcher_probe.pyw"
text = LAUNCHER.read_text(encoding="utf-8")

assert 'cd /d "%~dp0"' in text
assert "runtime\\python\\python.exe" in text
assert "runtime\\python\\pythonw.exe" in text
assert "sys.version_info >= (3, 11)" in text
assert "runtime\\active_runtime.txt" in text
assert "active_runtime.required.txt" in text
assert "dependency_manifest_missing" in text
assert "dependency_manifest_empty" in text
assert "runtime_dependency_invalid:" in text
assert "ZEROCUT_APP_OVERRIDE" in text
assert "ZEROCUT_LAUNCHER_WAIT" in text
assert "ZEROCUT_LAUNCHER_VERIFY_READY" in text
assert "ZEROCUT_READY_FILE" in text
assert "runtime\\verify_ready.py" in text
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
for code in (0, 2, 3, 4, 5, 6, 7, 8):
    assert f"exit /b {code}" in text

assert PROBE.is_file(), "Missing Windows process handoff probe"
assert READY_CHECK.is_file(), "Missing same-step readiness verifier"
py_compile.compile(str(READY_CHECK), doraise=True)
assert MANIFEST.is_file(), "Missing active runtime manifest"
assert REQUIRED.is_file(), "Missing runtime dependency manifest"

rel = MANIFEST.read_text(encoding="utf-8").strip()
assert rel and not Path(rel).is_absolute(), "Runtime manifest must be package-relative"
target = (ROOT / Path(rel.replace("\\", "/"))).resolve()
assert target.is_relative_to(ROOT.resolve()), "Runtime manifest escapes package root"
assert target.is_file(), f"Configured runtime missing: {target}"
assert re.match(r"ZeroCut_Run\d+_Candidate_.*\.pyw$", target.name), target.name
assert target.name == "ZeroCut_Run121_Candidate_GameplayDirector.pyw"

required_rows = [x.strip() for x in REQUIRED.read_text(encoding="utf-8").splitlines() if x.strip()]
assert required_rows[0].endswith("ZeroCut_Run121_Candidate_GameplayDirector.pyw")
assert any(x.endswith("ZeroCut_Run119_Candidate_WindowsReadiness.pyw") for x in required_rows)
assert any(x.endswith("runtime\\verify_ready.py") for x in required_rows)
required_paths = [(ROOT / Path(x.replace("\\", "/"))).resolve() for x in required_rows]
assert len(required_paths) >= 7
assert all(p.is_relative_to(ROOT.resolve()) and p.is_file() and p.stat().st_size > 500 for p in required_paths)

runtime_text = target.read_text(encoding="utf-8")
assert "ZeroCut_Run119_Candidate_WindowsReadiness.pyw" in runtime_text
assert "/api/gameplay/autoedit/preview" in runtime_text
chain_text = "\n".join(p.read_text(encoding="utf-8") for p in required_paths)
assert "--ready-file" in chain_text
assert '"/api/health"' in chain_text
assert "os.replace(tmp, READY_FILE)" in chain_text
ready_text = READY_CHECK.read_text(encoding="utf-8")
assert 'url + "/api/health"' in ready_text
assert 'url + "/"' in ready_text
assert "ZEROCUT_READY_CHECK=PASS" in ready_text
assert "zerocut-export-qc-run118" in chain_text, "Export QC wrapper missing"
assert "zerocut-transcript-editor-run117" in chain_text, "Transcript UI wrapper missing"
assert "install_whisper_runtime" in chain_text, "Local Whisper bootstrap missing"
assert "ZEROCUT_LAUNCH_DIR" in chain_text, "Launcher media-path contract not consumed"

print("ZEROCUT_RUN119_LAUNCHER_CONTRACT=PASS")
print("RUN119_ACTIVE_RUNTIME=", target.name, "CHAIN_FILES=", len(required_paths))
