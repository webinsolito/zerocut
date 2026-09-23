from __future__ import annotations
import importlib.machinery,importlib.util,py_compile,shutil,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
CANDIDATE=ROOT/"src"/"ZeroCut_Run107_Candidate_AVIntegrity.pyw"
def load():
    name="zc107"; l=importlib.machinery.SourceFileLoader(name,str(CANDIDATE)); s=importlib.util.spec_from_loader(name,l); assert s
    m=importlib.util.module_from_spec(s);sys.modules[name]=m;l.exec_module(m);return m
def run(cmd):
    p=subprocess.run(cmd,capture_output=True,text=True,timeout=120)
    if p.returncode: raise AssertionError((p.stderr or p.stdout)[-1000:])
def main():
    py_compile.compile(str(CANDIDATE),doraise=True);m=load()
    ffmpeg=shutil.which("ffmpeg");ffprobe=shutil.which("ffprobe");assert ffmpeg and ffprobe
    m._refresh_media_tools(ffmpeg,ffprobe)
    with tempfile.TemporaryDirectory(prefix="zc107-") as td:
        td=Path(td);good=td/"good.mp4";bad=td/"bad-offset.mp4"
        run([ffmpeg,"-hide_banner","-loglevel","error","-y",
             "-f","lavfi","-i","testsrc2=size=320x180:rate=30:duration=3",
             "-f","lavfi","-i","sine=frequency=440:sample_rate=48000:duration=3",
             "-shortest","-c:v","libx264","-preset","ultrafast","-pix_fmt","yuv420p","-c:a","aac",str(good)])
        g=m.probe_av_timing(good,ffprobe_bin=ffprobe); assert g["ok"] is True and g["start_delta"] <= .25
        verified=m.verify_render_output(good,3.0,expect_audio=True,ffmpeg_bin=ffmpeg,ffprobe_bin=ffprobe)
        assert verified["av_timing"]["ok"] is True
        # Delay only audio timestamps: detector must reject a material offset.
        run([ffmpeg,"-hide_banner","-loglevel","error","-y","-i",str(good),
             "-filter_complex","[0:a]asetpts=PTS+0.8/TB[a]","-map","0:v:0","-map","[a]",
             "-c:v","copy","-c:a","aac",str(bad)])
        b=m.probe_av_timing(bad,ffprobe_bin=ffprobe,start_tolerance=.25); assert b["ok"] is False
        assert b["start_delta"] > .25
    print("ZEROCUT_RUN107_AV_INTEGRITY=PASS")
if __name__=="__main__":main()
