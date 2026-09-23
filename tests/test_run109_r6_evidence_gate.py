from __future__ import annotations
import importlib.machinery,importlib.util,py_compile,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
CANDIDATE=ROOT/"src"/"ZeroCut_Run109_Candidate_R6EvidenceGate.pyw"
def load():
 name="zc109";l=importlib.machinery.SourceFileLoader(name,str(CANDIDATE));s=importlib.util.spec_from_loader(name,l);assert s
 m=importlib.util.module_from_spec(s);sys.modules[name]=m;l.exec_module(m);return m
def main():
 py_compile.compile(str(CANDIDATE),doraise=True);m=load()
 events=[
  {"type":"Kill","video_time":10.0,"username":"me","target":"p2","recording_player_action":True,"recording_pov_action":True},
  {"type":"Kill","video_time":10.05,"username":"me","target":"p2","recording_player_action":True,"recording_pov_action":True},
  {"type":"Kill","video_time":20.0,"username":"other","target":"p3","recording_player_action":False,"recording_pov_action":False},
  {"type":"Headshot","video_time":30.0,"username":"me","target":"p4","recording_player_action":True,"recording_pov_action":True,"headshot":True},
  {"type":"DefuserPlant","video_time":40.0,"username":"me"},
  {"type":"AudioSpike","video_time":50.0},
  {"type":"Kill","video_time":None,"username":"me","target":"p5","recording_player_action":True},
 ]
 result=m.certify_r6_semantic_events(events,min_kill_score=.50,duplicate_window=.2)
 kinds=[x["semantic_kind"] for x in result["accepted"]]
 assert kinds==["kill","headshot","defuser"],(kinds,result)
 reasons=[x["reason"] for x in result["rejected"]]
 assert "DUPLICATE_EVENT" in reasons
 assert "INSUFFICIENT_REPLAY_EVIDENCE" in reasons
 assert "UNSUPPORTED_KIND" in reasons
 assert "VIDEO_TIME_REQUIRED" in reasons
 assert result["gameplay_visual_accuracy_certified"] is False
 clips=m.build_r6_automatic_clips(events,video_duration=60)
 assert len(clips)>=2
 assert all(c["duration"]<=30.0 for c in clips)
 # Signal-only event must never be promoted to a semantic clip.
 assert all(all(m._r6_event_kind(e)!="audio spike" for e in c["events"]) for c in clips)
 print("ZEROCUT_RUN109_R6_EVIDENCE_GATE=PASS")
if __name__=="__main__":main()
