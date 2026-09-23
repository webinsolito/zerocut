from __future__ import annotations

import hashlib
import importlib.machinery
import importlib.util
import py_compile
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = ROOT / "src" / "ZeroCut_Run101_Candidate_MediaReliability.pyw"


def load_candidate():
    name = "zerocut_run101_media_reliability"
    loader = importlib.machinery.SourceFileLoader(name, str(CANDIDATE))
    spec = importlib.util.spec_from_loader(name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    loader.exec_module(module)
    return module


def run(cmd, timeout=60):
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise AssertionError(f"command failed ({proc.returncode}): {proc.stderr[-1200:]}")
    return proc


def main() -> None:
    py_compile.compile(str(CANDIDATE), doraise=True)
    module = load_candidate()

    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    assert ffmpeg and ffprobe, "GitHub runner must expose FFmpeg and FFprobe for this integration gate"
    module._refresh_media_tools(ffmpeg, ffprobe)
    assert Path(module._active_media_tool("ffmpeg")).resolve() == Path(ffmpeg).resolve()
    assert Path(module._active_media_tool("ffprobe")).resolve() == Path(ffprobe).resolve()

    with tempfile.TemporaryDirectory(prefix="zerocut-run101-") as td:
        td = Path(td)
        source = td / "fixture.mp4"
        output = td / "export.mp4"
        corrupt = td / "corrupt.mp4"

        run([
            ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=30:duration=2",
            "-f", "lavfi", "-i", "sine=frequency=880:sample_rate=48000:duration=2",
            "-shortest", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "96k", str(source),
        ])

        meta = module.ffprobe(source, timeout=10)
        assert meta["video"]["codec"] == "h264"
        assert meta["audio"]["codec"] == "aac"
        assert 1.8 <= meta["duration"] <= 2.2
        assert Path(meta["probe_binary"]).resolve() == Path(ffprobe).resolve()

        corrupt.write_bytes(b"not-a-real-video")
        started = time.monotonic()
        try:
            module.ffprobe(corrupt, timeout=2)
        except RuntimeError as exc:
            assert "FFprobe" in str(exc)
        else:
            raise AssertionError("corrupt media unexpectedly probed successfully")
        assert time.monotonic() - started < 5.0

        with mock.patch.object(module.subprocess, "run", side_effect=subprocess.TimeoutExpired([ffprobe], 0.1)):
            try:
                module.ffprobe(source, timeout=1)
            except RuntimeError as exc:
                assert "timeout" in str(exc).lower()
            else:
                raise AssertionError("ffprobe timeout did not fail closed")

        segments = [{"start": 0.20, "end": 1.55}]
        cmd, expected = module.export_command(
            source, output, segments, True, meta["video"]["fps"],
            encoder_capability={"verified": False}, ffmpeg_bin=ffmpeg,
        )
        assert Path(cmd[0]).resolve() == Path(ffmpeg).resolve()
        run(cmd)
        verified = module.verify_render_output(
            output, expected, expect_audio=True, ffmpeg_bin=ffmpeg, ffprobe_bin=ffprobe,
        )
        assert verified["ok"] is True
        assert verified["metadata"]["video"]["codec"] == "h264"
        assert verified["metadata"]["audio"]["codec"] == "aac"
        assert verified["decode_smoke"]["ok"] is True

        proxy_out = td / "proxy.mp4"
        proxy_cmd, _ = module.proxy_command(source, proxy_out, meta["duration"], True, ffmpeg_bin=ffmpeg)
        assert Path(proxy_cmd[0]).resolve() == Path(ffmpeg).resolve()
        run(proxy_cmd)
        proxy_meta = module.ffprobe(proxy_out, ffprobe_bin=ffprobe, timeout=10)
        assert proxy_meta["video"] and proxy_meta["duration"] > 0

    digest = hashlib.sha256(CANDIDATE.read_bytes()).hexdigest()
    print(f"RUN101_SHA256={digest}")
    print("ZEROCUT_RUN101_MEDIA_RELIABILITY=PASS")


if __name__ == "__main__":
    main()
