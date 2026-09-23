from __future__ import annotations
import importlib.machinery,importlib.util,py_compile,shutil,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
CANDIDATE=ROOT/"src"/"ZeroCut_Run111_Candidate_WhisperCertification.pyw"
def load():
 name="zc111";l=importlib.machinery.SourceFileLoader(name,str(CANDIDATE));s=importlib.util.spec_from_loader(name,l);assert s
 m=importlib.util.module_from_spec(s);sys.modules[name]=m;l.exec_module(m);return m
def main():
 py_compile.compile(str(CANDIDATE),doraise=True);m=load()
 ffmpeg=shutil.which("ffmpeg"); espeak=shutil.which("espeak-ng") or shutil.which("espeak")
 assert ffmpeg and espeak
 # Install exact pinned whisper.cpp runtime/model into ZeroCut's portable root.
 runtime=m.ROOT/"tools"/"whisper"; model=m.ROOT/"project"/"models"/m.WHISPER_MODEL_NAME
 if runtime.exists(): shutil.rmtree(runtime)
 if model.exists(): model.unlink()
 install=m.install_whisper_runtime(m.ROOT,timeout=240.0)
 assert install.get("ok") is True,install
 cap=m.discover_whisper(); assert cap.get("available") is True,cap
 with tempfile.TemporaryDirectory(prefix="zc111-") as td:
  td=Path(td); wav=td/"spoken-zero-cut.wav"
  p=subprocess.run([espeak,"-s","135","-w",str(wav),"Zero cut. Zero cut. This is Zero Cut gaming."],
                   capture_output=True,text=True,timeout=30)
  assert p.returncode==0 and wav.exists() and wav.stat().st_size>1000,(p.returncode,p.stderr)
  cert=m.whisper_runtime_certification(wav,timeout=120.0)
  assert cert.get("certified") is True,cert
  assert len((cert.get("binary_fingerprint") or {}).get("sha256",""))==64
  assert len((cert.get("model_fingerprint") or {}).get("sha256",""))==64
  full=m.transcribe_media_whisper(wav,language="en",ffmpeg_bin=ffmpeg,timeout=180.0)
  assert full.get("ok") is True,full
  txt=str(full.get("text") or "").lower().replace("-"," ")
  assert "zero" in txt and "cut" in txt,txt
  again=m.transcribe_media_whisper(wav,language="en",ffmpeg_bin=ffmpeg,timeout=180.0)
  assert again.get("ok") is True and again.get("cache_hit") is True,again
 print("ZEROCUT_RUN111_WHISPER_CERTIFICATION=PASS")
if __name__=="__main__":main()
