from __future__ import annotations
import importlib.machinery,importlib.util,py_compile,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
CANDIDATE=ROOT/"src"/"ZeroCut_Run108_Candidate_HighlightCore.pyw"
def load():
 name="zc108";l=importlib.machinery.SourceFileLoader(name,str(CANDIDATE));s=importlib.util.spec_from_loader(name,l);assert s
 m=importlib.util.module_from_spec(s);sys.modules[name]=m;l.exec_module(m);return m
def main():
 py_compile.compile(str(CANDIDATE),doraise=True);m=load()
 structure=[
  {"id":"true","start":10,"end":14,"audio_activity_score":.82,"motion_score":.88,"scene_change":True,"smart_dead_air":False},
  {"id":"loud-static","start":20,"end":24,"audio_activity_score":.98,"motion_score":.02,"scene_change":False,"smart_dead_air":False},
  {"id":"motion-only","start":30,"end":34,"audio_activity_score":.05,"motion_score":.90,"scene_change":False,"smart_dead_air":False},
  {"id":"dead","start":40,"end":45,"audio_activity_score":.70,"motion_score":.70,"scene_change":True,"smart_dead_air":True},
  {"id":"mixed","start":50,"end":54,"audio_activity_score":.55,"motion_score":.55,"scene_change":False,"smart_dead_air":False},
 ]
 rows=m.rank_multisignal_highlights(structure,min_score=.20,max_results=10)
 ids=[x["id"] for x in rows]
 assert ids[0]=="true",rows
 assert "dead" not in ids
 true=next(x for x in rows if x["id"]=="true")
 loud=next(x for x in rows if x["id"]=="loud-static")
 motion=next(x for x in rows if x["id"]=="motion-only")
 assert true["signal_count"]==3 and true["confidence"]=="high"
 assert loud["score"]<true["score"] and motion["score"]<true["score"]
 assert loud["signal_count"]==1 and motion["signal_count"]==1
 assert len({(x["start"],x["end"]) for x in rows})==len(rows)
 print("ZEROCUT_RUN108_HIGHLIGHT_CORE=PASS")
if __name__=="__main__":main()
