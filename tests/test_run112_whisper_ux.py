from __future__ import annotations
import importlib.machinery, importlib.util, py_compile, shutil, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = ROOT / "src" / "ZeroCut_Run112_Candidate_WhisperUX.pyw"

def load():
    name = "zc112"
    loader = importlib.machinery.SourceFileLoader(name, str(CANDIDATE))
    spec = importlib.util.spec_from_loader(name, loader)
    assert spec
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    loader.exec_module(module)
    return module

def main():
    py_compile.compile(str(CANDIDATE), doraise=True)
    m = load()

    html = (m.WEB / "index.html").read_text(encoding="utf-8")
    js = (m.WEB / "app.js").read_text(encoding="utf-8")
    css = (m.WEB / "styles.css").read_text(encoding="utf-8")
    assert "zerocut-whisper-run112" in html
    assert "runWhisperTranscript" in html
    assert "/api/analyze/transcript" in js
    assert ".zc-whisper-card" in css

    bad = m.transcript_user_summary({"ok": True, "executed": True, "segments": []})
    assert bad["usable"] is False
    assert bad["word_count"] == 0 and bad["segment_count"] == 0

    ffmpeg = shutil.which("ffmpeg")
    espeak = shutil.which("espeak-ng") or shutil.which("espeak")
    assert ffmpeg and espeak
    cap = m.discover_whisper()
    assert cap.get("available") is True, cap

    with tempfile.TemporaryDirectory(prefix="zc112-") as td:
        wav = Path(td) / "spoken.wav"
        p = subprocess.run(
            [espeak, "-s", "135", "-w", str(wav), "Zero cut gaming. Keep the useful action."],
            capture_output=True, text=True, timeout=30
        )
        assert p.returncode == 0 and wav.exists() and wav.stat().st_size > 1000, (p.returncode, p.stderr)
        real = m.transcribe_media_whisper(wav, language="en", ffmpeg_bin=ffmpeg, timeout=180.0)
        assert real.get("ok") is True, real
        summary = m.transcript_user_summary(real)
        assert summary["usable"] is True, summary
        assert summary["segment_count"] >= 1
        assert summary["word_count"] >= 3
        assert summary["text_preview"].strip()
        assert len(summary["model_sha256"]) == 64
        assert len(summary["source_sha256"]) == 64

    print("ZEROCUT_RUN112_WHISPER_UX=PASS")

if __name__ == "__main__":
    main()
