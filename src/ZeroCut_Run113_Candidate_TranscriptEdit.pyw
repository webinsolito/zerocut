#!/usr/bin/env python3
from __future__ import annotations
import importlib.machinery,importlib.util,json,sys
from pathlib import Path
from urllib.parse import urlparse
BASE_PATH=Path(__file__).with_name("ZeroCut_Run112_Candidate_WhisperUX.pyw")
loader=importlib.machinery.SourceFileLoader("zerocut_run112",str(BASE_PATH))
spec=importlib.util.spec_from_loader("zerocut_run112",loader)
if spec is None: raise RuntimeError("RUN112_BASE_NOT_LOADABLE")
base=importlib.util.module_from_spec(spec);sys.modules[spec.name]=base;loader.exec_module(base)

def prepare_transcript_edit(state,selected_ids,padding=0.04):
 media=state.get("media") or {};duration=float((media.get("metadata") or {}).get("duration") or 0.0)
 transcript=state.get("last_transcript_full") or {};segments=transcript.get("segments") if isinstance(transcript,dict) else None
 if not isinstance(segments,list): return {"ok":False,"committed":False,"error":"FULL_TRANSCRIPT_NOT_AVAILABLE"}
 raw=base.prepare_transcript_removal_transaction(segments,selected_ids,media_duration=duration,padding=padding)
 if not raw.get("ok"): return raw
 analysis={"schema":"zerocut.universal-analysis.v1","duration":duration,"smart_dead_air_ranges":raw.get("transcript_ranges") or []}
 receipt=base.prepare_dead_air_director_transaction(analysis,media_duration=duration,base_segments=state.get("segments") or None)
 if receipt.get("ok"):
  receipt.update({"director_intent":"remove_selected_transcript","detector":"explicit_transcript_selection","selected_ids":raw.get("selected_ids") or [],"matched_ids":raw.get("matched_ids") or [],"transcript_ranges":raw.get("transcript_ranges") or [],"requires_preview":True})
 return receipt

def transcript_edit_metrics(state,receipt):
 before=state.get("segments") or []
 after=receipt.get("proposed_segments") or receipt.get("segments") or []
 def total(rows): return round(sum(max(0.0,float(x.get("end",0))-float(x.get("start",0))) for x in rows if isinstance(x,dict)),3)
 b=total(before);a=total(after)
 return {"before_duration":b,"after_duration":a,"removed_duration":round(max(0.0,b-a),3),"before_segments":len(before),"after_segments":len(after),"timeline_changed":bool(after and (a!=b or after!=before))}

class Handler(base.Handler):
 def do_POST(self):
  path=urlparse(self.path).path
  try:
   if path=="/api/analyze/transcript":
    payload=self._body_json();state=base.load_state();revision=base.project_state_revision(state);source=base.media_file(state)
    result=base.transcribe_media_whisper(source,language=str(payload.get("language") or "auto")[:16],timeout=1800.0);summary=base.transcript_user_summary(result)
    state["last_transcript"]=summary;state["last_transcript_full"]={"language":result.get("language"),"source_sha256":result.get("source_sha256"),"model_sha256":result.get("model_sha256"),"segments":result.get("segments") or []} if summary.get("usable") else None
    base.save_state(state,expected_revision=revision);body={"ok":bool(summary.get("usable")),"transcript":summary,"segments":result.get("segments") or []}
    base.json_response(self,body,200 if body["ok"] else 422);return
   if path=="/api/transcript/edit/preview":
    payload=self._body_json();state=base.load_state();revision=base.project_state_revision(state);selected=payload.get("selected_ids") or []
    if not isinstance(selected,list) or not selected: raise ValueError("Seleziona almeno un blocco della trascrizione")
    receipt=prepare_transcript_edit(state,selected,float(payload.get("padding",0.04)))
    if not receipt.get("ok"): base.json_response(self,{"ok":False,"error":receipt.get("error"),"transaction":receipt},422);return
    metrics=transcript_edit_metrics(state,receipt)
    if not metrics["timeline_changed"]: base.json_response(self,{"ok":False,"error":"TIMELINE_UNCHANGED","transaction":receipt,"metrics":metrics},422);return
    state["transcript_edit_proposal"]={"transaction":receipt,"metrics":metrics,"project_revision":revision};base.save_state(state,expected_revision=revision);base.json_response(self,{"ok":True,"transaction":receipt,"metrics":metrics,"project_revision":base.project_state_revision(state)});return
   if path=="/api/transcript/edit/apply":
    payload=self._body_json();state=base.load_state();revision=base.project_state_revision(state);proposal=state.get("transcript_edit_proposal") or {};receipt=proposal.get("transaction") or {};current=state.get("segments") or []
    expected=payload.get("project_revision") or proposal.get("project_revision")
    if expected and str(expected)!=revision: base.json_response(self,{"ok":False,"error":"PROJECT_REVISION_CONFLICT"},409);return
    commit=base.commit_director_segment_transaction(current,receipt,expected_revision=str(receipt.get("expected_revision") or ""))
    if not commit.get("ok"): base.json_response(self,{"ok":False,"error":commit.get("error")},409);return
    state["segments"]=commit.get("segments") or [];state["selected_segment"]=state["segments"][0]["id"] if state["segments"] else None;state["transcript_edit_proposal"]=None;base.save_state(state,expected_revision=revision);base.json_response(self,{"ok":True,"project":state,"commit":commit,"metrics":proposal.get("metrics") or {}});return
   if path in {"/api/transcript/edit/cancel","/api/autoedit/cancel"}:
    payload=self._body_json();state=base.load_state();revision=base.project_state_revision(state);state["transcript_edit_proposal" if path.startswith("/api/transcript") else "auto_edit_proposal"]=None;expected=payload.get("project_revision") or revision;base.save_state(state,expected_revision=str(expected));base.json_response(self,{"ok":True,"project":state});return
  except base.ProjectRevisionConflict as exc: base.json_response(self,{"error":str(exc),"code":"PROJECT_REVISION_CONFLICT"},409);return
  except (ValueError,json.JSONDecodeError) as exc: base.json_response(self,{"error":str(exc)},400);return
  return super().do_POST()

def main():
 original=base.ThreadingHTTPServer
 class PatchedServer(original):
  def __init__(self,address,_handler): super().__init__(address,Handler)
 base.ThreadingHTTPServer=PatchedServer
 try: base.main()
 finally: base.ThreadingHTTPServer=original
if __name__=="__main__": main()
