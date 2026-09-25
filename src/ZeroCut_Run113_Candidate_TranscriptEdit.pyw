#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,json,sys
from pathlib import Path
from urllib.parse import urlparse
BASE_PATH=Path(__file__).with_name("ZeroCut_Run112_Candidate_WhisperUX.pyw")
spec=importlib.util.spec_from_file_location("zerocut_run112",BASE_PATH)
if spec is None or spec.loader is None: raise RuntimeError("RUN112_BASE_NOT_LOADABLE")
base=importlib.util.module_from_spec(spec);sys.modules[spec.name]=base;spec.loader.exec_module(base)

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
    payload=self._body_json();state=base.load_state();selected=payload.get("selected_ids") or []
    if not isinstance(selected,list): raise ValueError("selected_ids deve essere una lista")
    receipt=prepare_transcript_edit(state,selected,float(payload.get("padding",0.04)))
    if not receipt.get("ok"): base.json_response(self,{"ok":False,"error":receipt.get("error"),"transaction":receipt},422);return
    state["transcript_edit_proposal"]={"transaction":receipt};base.save_state(state);base.json_response(self,{"ok":True,"transaction":receipt});return
   if path=="/api/transcript/edit/apply":
    self._body_json();state=base.load_state();receipt=((state.get("transcript_edit_proposal") or {}).get("transaction") or {});current=state.get("segments") or []
    commit=base.commit_director_segment_transaction(current,receipt,expected_revision=str(receipt.get("expected_revision") or ""))
    if not commit.get("ok"): base.json_response(self,{"ok":False,"error":commit.get("error")},409);return
    state["segments"]=commit.get("segments") or [];state["selected_segment"]=state["segments"][0]["id"] if state["segments"] else None;state["transcript_edit_proposal"]=None;base.save_state(state);base.json_response(self,{"ok":True,"project":state,"commit":commit});return
   if path in {"/api/transcript/edit/cancel","/api/autoedit/cancel"}:
    payload=self._body_json();state=base.load_state();state["transcript_edit_proposal" if path.startswith("/api/transcript") else "auto_edit_proposal"]=None;expected=payload.get("project_revision");base.save_state(state,expected_revision=str(expected) if expected else None);base.json_response(self,{"ok":True,"project":state});return
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
