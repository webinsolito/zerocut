from __future__ import annotations
import importlib.machinery, importlib.util, json, shutil, subprocess, sys, tempfile, uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "ZeroCut_Run118_Candidate_ExportQC.pyw"

def load():
    name = "zc118_product"
    loader = importlib.machinery.SourceFileLoader(name, str(SOURCE))
    spec = importlib.util.spec_from_loader(name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    loader.exec_module(module)
    return module

def run(cmd, timeout=180):
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if p.returncode:
        raise AssertionError((p.stderr or p.stdout)[-2000:])
    return p.stdout.strip()

def duration(path, ffprobe):
    out = run([ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)])
    return float(json.loads(out)["format"]["duration"])

def main():
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    espeak = shutil.which("espeak-ng") or shutil.which("espeak")
    assert ffmpeg and ffprobe and espeak

    m = load()
    m.base._refresh_media_tools(ffmpeg, ffprobe)

    html = (m.base.WEB / "index.html").read_text(encoding="utf-8")
    js = (m.base.WEB / "app.js").read_text(encoding="utf-8")
    css = (m.base.WEB / "styles.css").read_text(encoding="utf-8")
    assert "zerocut-export-qc-run118" in html
    assert "/api/export/qc/latest" in SOURCE.read_text(encoding="utf-8")
    assert 'id="refreshExportQc"' in html
    assert "actual_duration" in js and "expected_duration" in js
    assert ".zc-export-qc-metrics" in css

    m.base.RENDER.mkdir(parents=True, exist_ok=True)
    m.base.DIAGNOSTICS.mkdir(parents=True, exist_ok=True)
    m.EXPORT_QC_FILE.unlink(missing_ok=True)

    with tempfile.TemporaryDirectory(prefix="zc118-") as td:
        td = Path(td)
        speech = td / "speech.wav"
        src = td / "spoken.mp4"
        out = m.base.RENDER / f"run118-{uuid.uuid4().hex[:8]}.working.mp4"

        run([espeak, "-s", "135", "-w", str(speech),
             "Remove this section. Keep this section for the final video."])

        run([
            ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=30:duration=12",
            "-i", str(speech),
            "-filter_complex", "[1:a]adelay=1000|1000,apad=pad_dur=12[a]",
            "-map", "0:v:0", "-map", "[a]", "-t", "12",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-ar", "48000", "-movflags", "+faststart", str(src),
        ])

        # Persisted transcript-shaped state used by the verified Run113/117 editor path.
        state = {
            "media": {"metadata": {"duration": 12.0}},
            "segments": [{"id": "source0", "start": 0.0, "end": 12.0}],
            "last_transcript_full": {
                "segments": [
                    {"id": "cut-me", "start": 1.0, "end": 3.5, "text": "Remove this section."},
                    {"id": "keep-me", "start": 3.5, "end": 6.0, "text": "Keep this section for the final video."},
                ]
            },
        }
        persisted = td / "project-state.json"
        persisted.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        state = json.loads(persisted.read_text(encoding="utf-8"))

        # Preview.
        receipt = m.ui.core.prepare_transcript_edit(state, ["cut-me"], padding=0.0)
        assert receipt.get("ok") is True, receipt
        metrics = m.ui.core.transcript_edit_metrics(state, receipt)
        assert metrics["timeline_changed"] is True, metrics
        assert metrics["after_duration"] < metrics["before_duration"], metrics

        # Apply using the same optimistic timeline revision gate as the product.
        commit = m.base.commit_director_segment_transaction(
            state["segments"],
            receipt,
            expected_revision=str(receipt.get("expected_revision") or ""),
        )
        assert commit.get("ok") is True and commit.get("committed") is True, commit
        edited = commit.get("segments") or []
        assert edited and edited != state["segments"], commit

        # Export with ZeroCut's real product command, not a test-only FFmpeg graph.
        cmd, expected = m.base.export_command(
            src,
            out,
            edited,
            True,
            30.0,
            encoder_capability={"verified": False},
            ffmpeg_bin=ffmpeg,
        )
        run(cmd)

        # Product QC is patched by Run118 and must persist an auditable record.
        qc = m.base.verify_render_output(
            out,
            expected,
            expect_audio=True,
            ffmpeg_bin=ffmpeg,
            ffprobe_bin=ffprobe,
        )
        record = m.read_latest_export_qc()
        assert record and record.get("ok") is True, record
        assert record.get("av_sync_ok") is True, record
        assert record.get("decode_ok") is True, record

        input_d = duration(src, ffprobe)
        output_d = duration(out, ffprobe)
        assert output_d < input_d - 2.0, (input_d, output_d)
        assert abs(output_d - expected) <= 0.20, (output_d, expected, edited)
        assert abs(float(record["actual_duration"]) - output_d) <= 0.05, record
        assert abs(float(record["expected_duration"]) - expected) <= 0.01, record

        print("ZEROCUT_RUN118_EXPORT_QC=PASS")
        print(
            f"RUN118_INPUT={input_d:.3f} TIMELINE={expected:.3f} "
            f"EXPORT={output_d:.3f} REMOVED={input_d-output_d:.3f} "
            f"AV_SYNC={record['av_sync_ok']} DECODE={record['decode_ok']}"
        )
        out.unlink(missing_ok=True)

if __name__ == "__main__":
    main()
