from __future__ import annotations
import importlib.machinery, importlib.util, json, py_compile, shutil, subprocess, sys, tempfile, uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "ZeroCut_Run121_Candidate_GameplayDirector.pyw"

def load():
    name = "zc121_product"
    loader = importlib.machinery.SourceFileLoader(name, str(SOURCE))
    spec = importlib.util.spec_from_loader(name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    loader.exec_module(module)
    return module

def run(cmd, timeout=240):
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if p.returncode:
        raise AssertionError((p.stderr or p.stdout)[-3000:])
    return p.stdout.strip()

def probe_duration(path, ffprobe):
    out = run([ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)])
    return float(json.loads(out)["format"]["duration"])

def main():
    py_compile.compile(str(SOURCE), doraise=True)
    m = load()
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    espeak = shutil.which("espeak-ng") or shutil.which("espeak")
    assert ffmpeg and ffprobe and espeak
    m.base._refresh_media_tools(ffmpeg, ffprobe)

    # PASS 1 prerequisites: the prior certified local AI runtimes must remain usable.
    whisper = m.base.discover_whisper()
    ocr = m.base.certify_rapidocr_inference()
    assert whisper.get("available") is True, whisper
    assert ocr.get("certified") is True, ocr

    html = (m.base.WEB / "index.html").read_text(encoding="utf-8")
    js = (m.base.WEB / "app.js").read_text(encoding="utf-8")
    assert "zerocut-gameplay-director-run121" in html
    assert "/api/gameplay/autoedit/preview" in js
    assert "/api/gameplay/autoedit/apply" in js
    assert "/api/gameplay/autoedit/cancel" in js

    with tempfile.TemporaryDirectory(prefix="zc121-") as td:
        td = Path(td)
        speech = td / "speech.wav"
        src = td / "gameplay-like.mp4"
        run([espeak, "-s", "135", "-w", str(speech),
             "Zero Cut gaming highlight. Round won. Nice kill. Keep this highlight."])

        font = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
        assert font.is_file(), font
        vf = (
            "color=c=black:size=640x360:rate=30:duration=18,"
            f"drawtext=fontfile='{font}':text='ROUND WON':fontcolor=white:fontsize=72:"
            "x=(w-text_w)/2:y=(h-text_h)/2"
        )
        run([
            ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", vf,
            "-i", str(speech),
            "-filter_complex", "[1:a]adelay=400|400,apad=pad_dur=18[a]",
            "-map", "0:v:0", "-map", "[a]", "-t", "18",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-ar", "48000", "-movflags", "+faststart", str(src),
        ])

        state = {
            "media": {"metadata": {"duration": 18.0, "audio": {"codec": "aac"}}},
            "segments": [{"id": "source0", "start": 0.0, "end": 18.0}],
        }
        events = [{
            "type": "Kill", "video_time": 10.0, "username": "recording-player",
            "target": "opponent", "recording_player_action": True,
            "recording_pov_action": True, "recording_player_kill_shot_correlated": True,
        }]

        # Real encoded video -> structural analysis + real local Whisper + real local OCR
        # -> conservative R6 evidence -> Director transaction. Preview MUST NOT mutate state.
        plan = m.plan_gameplay_autoedit(
            state, src, r6_events=events, language="en", run_whisper=True, run_ocr=True
        )
        assert plan.get("ok") is True, plan
        assert plan.get("mode") == "r6_replay_evidence", plan
        assert plan["metrics"]["timeline_changed"] is True, plan["metrics"]
        assert plan["metrics"]["after_duration"] < plan["metrics"]["before_duration"], plan["metrics"]
        assert plan["analysis_summary"]["speech_generated"] is True, plan["analysis_summary"]
        assert plan["analysis_summary"]["speech_segment_count"] > 0, plan["analysis_summary"]
        assert plan["ocr"]["executed"] is True, plan["ocr"]
        assert "victory" in (plan["ocr"].get("semantic") or {}).get("signals", []), plan["ocr"]
        assert plan["semantic"]["accepted_count"] == 1, plan["semantic"]
        assert state["segments"] == [{"id": "source0", "start": 0.0, "end": 18.0}]

        # PASS 2 behavior: cancel is non-destructive; apply commits the exact reviewed receipt.
        cancelled = m.cancel_gameplay_proposal(state, plan)
        assert cancelled.get("ok") is True
        assert cancelled["state"]["segments"] == state["segments"]

        applied = m.apply_gameplay_proposal(state, plan)
        assert applied.get("ok") is True, applied
        edited = applied["state"]["segments"]
        assert edited != state["segments"]
        edited_duration = sum(float(x["end"]) - float(x["start"]) for x in edited)
        assert edited_duration < 18.0 - 2.0, edited

        # Executor -> real FFmpeg export -> Run118 QC (duration, A/V timing, decode).
        m.base.RENDER.mkdir(parents=True, exist_ok=True)
        m.runtime.qc.EXPORT_QC_FILE.unlink(missing_ok=True)
        out = m.base.RENDER / f"run121-{uuid.uuid4().hex[:8]}.working.mp4"
        cmd, expected = m.base.export_command(
            src, out, edited, True, 30.0,
            encoder_capability={"verified": False}, ffmpeg_bin=ffmpeg,
        )
        run(cmd)
        qc = m.base.verify_render_output(
            out, expected, expect_audio=True, ffmpeg_bin=ffmpeg, ffprobe_bin=ffprobe
        )
        record = m.runtime.qc.read_latest_export_qc()
        assert qc.get("ok") is True, qc
        assert record and record.get("ok") is True, record
        assert record.get("av_sync_ok") is True, record
        assert record.get("decode_ok") is True, record

        input_duration = probe_duration(src, ffprobe)
        output_duration = probe_duration(out, ffprobe)
        assert output_duration < input_duration - 2.0, (input_duration, output_duration)
        assert abs(output_duration - expected) <= 0.25, (output_duration, expected)
        out.unlink(missing_ok=True)

        print("ZEROCUT_RUN121_GAMEPLAY_DIRECTOR=PASS")
        print(
            f"RUN121_INPUT={input_duration:.3f} PREVIEW={plan['metrics']['after_duration']:.3f} "
            f"EXPORT={output_duration:.3f} WHISPER_SEGMENTS={plan['analysis_summary']['speech_segment_count']} "
            f"OCR_SIGNALS={','.join(plan['analysis_summary']['ocr_signals']) or 'none'} "
            f"R6_ACCEPTED={plan['semantic']['accepted_count']}"
        )

if __name__ == "__main__":
    main()
