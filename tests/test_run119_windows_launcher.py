from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "ZeroCut.cmd"
MANIFEST = ROOT / "runtime" / "active_runtime.txt"
text = LAUNCHER.read_text(encoding="utf-8")

assert 'cd /d "%~dp0"' in text
assert "runtime\\python\\python.exe" in text
assert "runtime\\python\\pythonw.exe" in text
assert "runtime\\active_runtime.txt" in text
assert "ZEROCUT_APP_OVERRIDE" in text
assert "ZEROCUT_LAUNCHER_WAIT" in text
assert "ZEROCUT_LAUNCHER_NO_PAUSE" in text
assert "ZEROCUT_FFMPEG" in text and "ffmpeg.exe" in text
assert "ZEROCUT_FFPROBE" in text and "ffprobe.exe" in text
assert "ZEROCUT_WHISPER_HOME" in text
assert "zerocut-launcher.log" in text
assert "p.is_relative_to(root)" in text
assert 'start "ZeroCut"' in text
for code in (0, 2, 3, 4, 5, 6):
    assert f"exit /b {code}" in text

assert MANIFEST.is_file(), "Missing active runtime manifest"
rel = MANIFEST.read_text(encoding="utf-8").strip()
assert rel and not Path(rel).is_absolute(), "Runtime manifest must be package-relative"
target = (ROOT / Path(rel.replace("\\", "/"))).resolve()
assert target.is_relative_to(ROOT.resolve()), "Runtime manifest escapes package root"
assert target.is_file(), f"Configured runtime missing: {target}"
assert target.stat().st_size > 100_000, "Configured runtime is a thin slice, not the full app"
assert re.match(r"ZeroCut_Run\d+_Candidate_.*\.pyw$", target.name), target.name

print("ZEROCUT_RUN119_LAUNCHER_CONTRACT=PASS")
print("RUN119_ACTIVE_RUNTIME=", target.name, "BYTES=", target.stat().st_size)
