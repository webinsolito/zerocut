from __future__ import annotations
import importlib.machinery, importlib.util, math, py_compile, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
CANDIDATE=ROOT/"src"/"ZeroCut_Run106_Candidate_TimelineReliability.pyw"
def load():
    name="zc106"; loader=importlib.machinery.SourceFileLoader(name,str(CANDIDATE))
    spec=importlib.util.spec_from_loader(name,loader); assert spec
    m=importlib.util.module_from_spec(spec); sys.modules[name]=m; loader.exec_module(m); return m
def expect(m,segments,code):
    try: m.normalize_project_timeline(segments,10.0)
    except ValueError as e: assert code in str(e),str(e)
    else: raise AssertionError(code)
def main():
    py_compile.compile(str(CANDIDATE),doraise=True); m=load()
    ok=m.normalize_project_timeline([{"id":"a","start":0.0,"end":3.0},{"id":"b","start":5.0,"end":9.0}],10.0)
    assert [x["id"] for x in ok]==["a","b"]
    expect(m,[],"TIMELINE_EMPTY")
    expect(m,[{"id":"a","start":0,"end":1},{"id":"a","start":2,"end":3}],"TIMELINE_DUPLICATE_ID")
    expect(m,[{"id":"a","start":float("nan"),"end":1}],"TIMELINE_SEGMENT_TIME_INVALID")
    expect(m,[{"id":"a","start":2,"end":1}],"TIMELINE_SEGMENT_RANGE_INVALID")
    expect(m,[{"id":"a","start":0,"end":10.1}],"TIMELINE_SEGMENT_RANGE_INVALID")
    expect(m,[{"id":"a","start":0,"end":0.01}],"TIMELINE_SEGMENT_TOO_SHORT")
    try: m.normalize_project_timeline([{"id":str(i),"start":0,"end":1} for i in range(501)],10)
    except ValueError as e: assert "TIMELINE_TOO_MANY_SEGMENTS" in str(e)
    else: raise AssertionError("segment cap")
    print("ZEROCUT_RUN106_TIMELINE_RELIABILITY=PASS")
if __name__=="__main__": main()
