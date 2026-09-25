from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "ZeroCut.cmd"
MANIFEST = ROOT / "runtime" / "active_runtime.txt"
PROBE = ROOT / "tests" / "run119_launcher_probe.pyw"
text = LAUNCHER.read_text(encoding="utf-8")

assert 'cd /d "%~dp0"' in text
assert "runtime\\python\\python.exe" in text
assert "runtime\\python\\pythonw.exe" in text
assert "sys.version_info >= (3, 11)" in text
assert "runtime\\active_runtime.txt" in text
assert "ZEROCUT_APP_OVERRIDE" in text
assert "ZEROCUT_LAUNCHER_WAIT" in text
assert "ZEROCUT_LAUNCHER_NO_PAUSE" in text
assert "ZEROCUT_LAUNCH_DIR" in text
assert "runtime\\ffmpeg\\bin" in text
assert "ZEROCUT_FFMPEG" in text and "ZEROCUT_FFPROBE" in text
assert "set \"PATH=%~dp0runtime\\ffmpeg\\bin;%PATH%\"" in text
assert "zerocut-launcher.log" in text
assert "p.is_relative_to(root)" in text
assert 'start "ZeroCut"' in text
for code in (0, 2, 3, 4, 5, 6, 7):
    assert f"exit /b {code}" in text

assert PROBE.is_file(), "Missing Windows process handoff probe"
assert MANIFEST.is_file(), "Missing active runtime manifest"
rel = MANIFEST.read_text(encoding="utf-8").strip()
assert rel and not Path(rel).is_absolute(), "Runtime manifest must be package-relative"
target = (ROOT / Path(rel.replace("\\", "/"))).resolve()
assert target.is_relative_to(ROOT.resolve()), "Runtime manifest escapes package root"
assert target.is_file(), f"Configured runtime missing: {target}"
assert target.stat().st_size > 100_000, "Configured runtime is a thin slice, not the full app"
assert re.match(r"ZeroCut_Run\d+_Candidate_.*\.pyw$", target.name), target.name

runtime_text = target.read_text(encoding="utf-8")
assert "ZEROCUT_LAUNCH_DIR" in runtime_text, "Launcher media-path contract is not consumed by active runtime"
assert "install_whisper_runtime" in runtime_text, "Active runtime lacks local Whisper bootstrap"

print("ZEROCUT_RUN119_LAUNCHER_CONTRACT=PASS")
print("RUN119_ACTIVE_RUNTIME=", target.name, "BYTES=", target.stat().st_size)
