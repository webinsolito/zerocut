from __future__ import annotations
import importlib,importlib.machinery,importlib.util,py_compile,shutil,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
CANDIDATE=ROOT/"src"/"ZeroCut_Run110_Candidate_OCRCertification.pyw"
def load():
 name="zc110";l=importlib.machinery.SourceFileLoader(name,str(CANDIDATE));s=importlib.util.spec_from_loader(name,l);assert s
 m=importlib.util.module_from_spec(s);sys.modules[name]=m;l.exec_module(m);return m
def main():
 py_compile.compile(str(CANDIDATE),doraise=True);m=load()
 # Fresh local runtime so this is an inference test, not package-presence theatre.
 vendor=ROOT/"tools"/"python"
 if vendor.exists(): shutil.rmtree(vendor)
 install=m.install_rapidocr_runtime(ROOT,timeout=300.0)
 assert install.get("ok") is True,install
 importlib.invalidate_caches()
 cap=m.discover_rapidocr()
 assert cap.get("available") is True,cap
 assert cap.get("providers"),cap
 generic=m.rapidocr_inference_selftest()
 assert generic.get("executed") and generic.get("passed"),generic
 cert=m.certify_rapidocr_inference()
 assert cert.get("certified") is True,cert
 r6=m.rapidocr_r6_semantic_selftest()
 assert r6.get("executed") and r6.get("passed"),r6
 assert "victory" in (r6.get("semantic") or {}).get("signals",[]),r6
 print("ZEROCUT_RUN110_OCR_CERTIFICATION=PASS")
 print("OCR_PROVIDERS="+",".join(cap.get("providers") or []))
if __name__=="__main__":main()
