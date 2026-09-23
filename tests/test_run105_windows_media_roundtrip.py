from __future__ import annotations
import importlib.machinery, importlib.util, platform, py_compile, shutil, subprocess, sys, tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
CANDIDATE=ROOT/"src"/"ZeroCut_Run105_Candidate_WindowsMediaRoundtrip.pyw"
def load():
    name="zerocut_run105_windows_media"
    loader=importlib.machinery.SourceFileLoader(name,str(CANDIDATE))
    spec=importlib.util.spec_from_loader(name,loader); assert spec
    m=importlib.util.module_from_spec(spec); sys.modules[name]=m; loader.exec_module(m); return m
def run(cmd):
    p=subprocess.run(cmd,capture_output=True,text=True,timeout=120)
    if p.returncode: raise AssertionError((p.stderr or p.stdout)[-1200:])
def main():
    assert platform.system()=="Windows"
    py_compile.compile(str(CANDIDATE),doraise=True); m=load()
    ffmpeg=shutil.which("ffmpeg"); ffprobe=shutil.which("ffprobe")
    assert ffmpeg and ffprobe, "FFmpeg/FFprobe missing on Windows runner"
    m._refresh_media_tools(ffmpeg,ffprobe)
    with tempfile.TemporaryDirectory(prefix="zc105-win-") as td:
        td=Path(td); source=td/"gameplay_à_日本.mp4"
        run([ffmpeg,"-hide_banner","-loglevel","error","-y",
             "-f","lavfi","-i","testsrc2=size=640x360:rate=30:duration=3",
             "-f","lavfi","-i","sine=frequency=660:sample_rate=48000:duration=3",
             "-shortest","-c:v","libx264","-preset","ultrafast","-pix_fmt","yuv420p",
             "-c:a","aac","-b:a","96k",str(source)])
        result=m.media_roundtrip_selftest(source,td/"roundtrip",ffmpeg_bin=ffmpeg,ffprobe_bin=ffprobe)
        assert result["ok"] is True
        assert result["source"]["video"]["codec"]=="h264"
        assert result["source"]["audio"]["codec"]=="aac"
        assert result["proxy"]["ok"] is True and result["proxy"]["decode_smoke"]["ok"] is True
        assert result["export"]["ok"] is True and result["export"]["decode_smoke"]["ok"] is True
    print("ZEROCUT_RUN105_WINDOWS_MEDIA_ROUNDTRIP=PASS")
if __name__=="__main__": main()
