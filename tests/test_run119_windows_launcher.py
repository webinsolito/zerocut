from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "ZeroCut.cmd"
text = LAUNCHER.read_text(encoding="utf-8")

assert 'cd /d "%~dp0"' in text
assert "runtime\\python\\pythonw.exe" in text
assert "pythonw.exe" in text
assert 'src\\ZeroCut_Run*_Candidate_*.pyw' in text
assert "ZEROCUT_FFMPEG" in text and "ffmpeg.exe" in text
assert "ZEROCUT_FFPROBE" in text and "ffprobe.exe" in text
assert "ZEROCUT_WHISPER_HOME" in text
assert "zerocut-launcher.log" in text
assert "Preflight runtime" in text
assert 'start "ZeroCut"' in text
assert "exit /b 0" in text
assert "exit /b 2" in text and "exit /b 3" in text and "exit /b 4" in text and "exit /b 5" in text

candidates = sorted((ROOT / "src").glob("ZeroCut_Run*_Candidate_*.pyw"), reverse=True)
assert candidates, "No ZeroCut candidate runtime found"
assert candidates[0].stat().st_size > 100_000, "Selected runtime is unexpectedly small"
print("PASS Run119 launcher contract", candidates[0].name)
