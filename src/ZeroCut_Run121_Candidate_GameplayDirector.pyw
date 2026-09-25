#!/usr/bin/env python3
from __future__ import annotations

import copy
import importlib.machinery
import importlib.util
import json
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse

BASE_PATH = Path(__file__).with_name("ZeroCut_Run119_Candidate_WindowsReadiness.pyw")
_loader = importlib.machinery.SourceFileLoader("zerocut_run119", str(BASE_PATH))
_spec = importlib.util.spec_from_loader("zerocut_run119", _loader)
if _spec is None:
    raise RuntimeError("RUN119_BASE_NOT_LOADABLE")
runtime = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = runtime
_loader.exec_module(runtime)

base = runtime.base
RUNTIME_NAME = "Run121_GameplayDirector"
UI_MARKER = "zerocut-gameplay-director-run121"


def _total_duration(rows: list[dict]) -> float:
    return round(sum(
        max(0.0, float(row.get("end", 0.0)) - float(row.get("start", 0.0)))
        for row in (rows or []) if isinstance(row, dict)
    ), 4)


def _merge_ranges(rows: list[dict], duration: float, *, gap: float = 0.20) -> list[dict]:
    duration = max(0.0, float(duration))
    clean = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        try:
            start = max(0.0, min(duration, float(row.get("start", 0.0))))
            end = max(start, min(duration, float(row.get("end", 0.0))))
        except (TypeError, ValueError):
            continue
        if end - start >= 0.08:
            clean.append({**row, "start": round(start, 4), "end": round(end, 4)})
    clean.sort(key=lambda x: (x["start"], x["end"]))
    merged = []
    for row in clean:
        if merged and row["start"] <= merged[-1]["end"] + max(0.0, float(gap)):
            merged[-1]["end"] = max(merged[-1]["end"], row["end"])
            merged[-1]["score"] = max(float(merged[-1].get("score", 0.0)), float(row.get("score", 0.0)))
            merged[-1]["reasons"] = list(dict.fromkeys(
                list(merged[-1].get("reasons") or []) + list(row.get("reasons") or [])
            ))
        else:
            merged.append(copy.deepcopy(row))
    return merged


def _complement_ranges(keep: list[dict], duration: float) -> list[dict]:
    duration = max(0.0, float(duration))
    cursor = 0.0
    dead = []
    for row in _merge_ranges(keep, duration, gap=0.0):
        start, end = float(row["start"]), float(row["end"])
        if start > cursor + 0.04:
            dead.append({"start": round(cursor, 4), "end": round(start, 4)})
        cursor = max(cursor, end)
    if cursor < duration - 0.04:
        dead.append({"start": round(cursor, 4), "end": round(duration, 4)})
    return dead


def _generic_keep_clips(analysis: dict, duration: float, *, max_clips: int = 4) -> list[dict]:
    rows = analysis.get("highlight_candidates") if isinstance(analysis, dict) else []
    chosen = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        try:
            score = float(row.get("score", 0.0))
        except (TypeError, ValueError):
            score = 0.0
        if score < 0.25:
            continue
        chosen.append({
            "start": row.get("start", 0.0),
            "end": row.get("end", 0.0),
            "score": score,
            "reasons": ["multisignal_highlight"],
            "evidence": list(row.get("evidence") or []),
        })
        if len(chosen) >= max(1, int(max_clips)):
            break
    if not chosen:
        for row in (analysis.get("important_segments") or []):
            if not isinstance(row, dict):
                continue
            chosen.append({
                "start": row.get("start", 0.0),
                "end": row.get("end", 0.0),
                "score": float(row.get("score", 0.0) or 0.0),
                "reasons": ["structural_importance"],
            })
            if len(chosen) >= max(1, int(max_clips)):
                break
    if not chosen:
        smart_keep = analysis.get("smart_dead_air_preview_segments") or []
        for row in smart_keep:
            if isinstance(row, dict):
                chosen.append({
                    "start": row.get("start", 0.0),
                    "end": row.get("end", 0.0),
                    "score": 0.20,
                    "reasons": ["smart_dead_air_fallback"],
                })
    return _merge_ranges(chosen, duration)


def _ocr_video_evidence(source: Path, times: list[float]) -> dict:
    cert = base.certify_rapidocr_inference()
    if not cert.get("certified"):
        return {
            "executed": False,
            "certified": False,
            "reason": cert.get("reason", "RAPIDOCR_NOT_CERTIFIED"),
            "texts": [],
            "semantic": {"signals": [], "semantic_score": 0.0},
            "providers": cert.get("providers", []),
        }
    probes = []
    seen = set()
    for raw in times:
        try:
            value = max(0.0, float(raw))
        except (TypeError, ValueError):
            continue
        key = round(value, 2)
        if key in seen:
            continue
        seen.add(key)
        probes.append({"time": value, "priority": 1.0, "reason": "director_candidate"})
        if len(probes) >= 8:
            break
    if not probes:
        return {
            "executed": False,
            "certified": True,
            "reason": "NO_VISUAL_PROBES",
            "texts": [],
            "semantic": {"signals": [], "semantic_score": 0.0},
            "providers": cert.get("providers", []),
        }
    with tempfile.TemporaryDirectory(prefix="zerocut-run121-ocr-") as td:
        frames = base.extract_visual_evidence_frames(
            Path(source), probes, Path(td), width=640, max_workers=3
        )
        ok_frames = [row for row in frames if row.get("ok")]
        result = base.rapidocr_candidate_frames(ok_frames, min_confidence=0.45)
        texts = [str(v).strip() for v in (result.get("texts") or {}).values() if str(v).strip()]
        semantic = base.classify_r6_ocr_text(" ".join(texts))
        return {
            "executed": bool(result.get("executed")),
            "certified": True,
            "reason": result.get("reason", "OK"),
            "texts": texts[:12],
            "semantic": semantic,
            "providers": result.get("providers", cert.get("providers", [])),
            "frame_count": len(ok_frames),
        }


def gameplay_edit_metrics(state: dict, receipt: dict) -> dict:
    before = receipt.get("before") or state.get("segments") or []
    after = receipt.get("after") or []
    before_duration = _total_duration(before)
    after_duration = _total_duration(after)
    return {
        "before_duration": before_duration,
        "after_duration": after_duration,
        "removed_duration": round(max(0.0, before_duration - after_duration), 4),
        "before_segments": len(before),
        "after_segments": len(after),
        "timeline_changed": bool(after and before != after and after_duration < before_duration - 0.04),
    }


def plan_gameplay_autoedit(
    state: dict,
    source: Path,
    *,
    r6_events: list[dict] | None = None,
    language: str = "auto",
    run_whisper: bool = True,
    run_ocr: bool = True,
) -> dict:
    """Create one reviewable gameplay montage transaction from local evidence.

    R6 semantic clips are only created from explicit replay/timeline events that pass
    the existing evidence gate. OCR/audio/motion never fabricate a kill. Without
    certified semantic events ZeroCut falls back to generic multi-signal highlights.
    """
    source = Path(source)
    if not source.is_file():
        return {"ok": False, "error": "MEDIA_SOURCE_MISSING"}

    media = state.get("media") if isinstance(state, dict) else {}
    meta = (media or {}).get("metadata") or base.ffprobe(source)
    try:
        duration = float((meta or {}).get("duration") or 0.0)
    except (TypeError, ValueError):
        duration = 0.0
    if duration <= 0:
        duration = float(base.ffprobe(source).get("duration") or 0.0)
    if duration <= 0:
        return {"ok": False, "error": "INVALID_MEDIA_DURATION"}

    if run_whisper:
        analysis = base.analyze_universal_media_with_local_transcript(
            source, language=str(language or "auto")[:16], transcript_timeout=1800.0,
            duration=duration,
        )
    else:
        analysis = base.analyze_universal_media(source, duration=duration)

    events = list(r6_events or [])
    certified = base.certify_r6_semantic_events(events)
    semantic_clips = base.build_r6_automatic_clips(events, video_duration=duration) if certified.get("accepted") else []

    if semantic_clips:
        mode = "r6_replay_evidence"
        keep_clips = _merge_ranges(semantic_clips, duration)
    else:
        mode = "generic_multisignal"
        keep_clips = _generic_keep_clips(analysis, duration)

    if not keep_clips:
        return {
            "ok": False,
            "error": "NO_SAFE_HIGHLIGHT_CLIPS",
            "mode": mode,
            "semantic": certified,
            "analysis_summary": {
                "scene_count": int(analysis.get("scene_count") or 0),
                "highlight_count": len(analysis.get("highlight_candidates") or []),
            },
        }

    dead_ranges = _complement_ranges(keep_clips, duration)
    if not dead_ranges:
        return {
            "ok": False,
            "error": "TIMELINE_UNCHANGED",
            "mode": mode,
            "keep_clips": keep_clips,
        }

    director_analysis = dict(analysis)
    director_analysis["smart_dead_air_ranges"] = dead_ranges
    director_analysis["duration"] = duration
    director_analysis["schema"] = "zerocut.universal-analysis.v1"
    receipt = base.prepare_dead_air_director_transaction(
        director_analysis,
        media_duration=duration,
        base_segments=state.get("segments") or None,
    )
    if not receipt.get("ok"):
        return {"ok": False, "error": receipt.get("error", "DIRECTOR_PLAN_FAILED"), "transaction": receipt}

    receipt["director_intent"] = "gameplay_highlight_montage"
    receipt["detector"] = mode
    receipt["keep_clips"] = keep_clips
    receipt["requires_preview"] = True
    metrics = gameplay_edit_metrics(state, receipt)
    if not metrics["timeline_changed"]:
        return {"ok": False, "error": "TIMELINE_UNCHANGED", "transaction": receipt, "metrics": metrics}

    probe_times = []
    for event in certified.get("accepted") or []:
        if event.get("video_time") is not None:
            probe_times.append(float(event["video_time"]))
    if not probe_times:
        probe_times = [(float(row["start"]) + float(row["end"])) / 2.0 for row in keep_clips]

    ocr = _ocr_video_evidence(source, probe_times) if run_ocr else {
        "executed": False, "certified": False, "reason": "OCR_DISABLED",
        "texts": [], "semantic": {"signals": [], "semantic_score": 0.0},
    }
    transcript = analysis.get("transcript") if isinstance(analysis.get("transcript"), dict) else {}
    transcript_text = str(transcript.get("text") or "")
    summary = {
        "scene_count": int(analysis.get("scene_count") or 0),
        "highlight_count": len(analysis.get("highlight_candidates") or []),
        "speech_generated": bool(transcript.get("generated")),
        "speech_segment_count": int(transcript.get("segment_count") or len(transcript.get("segments") or [])),
        "speech_preview": transcript_text[:280],
        "ocr_executed": bool(ocr.get("executed")),
        "ocr_signals": list((ocr.get("semantic") or {}).get("signals") or []),
        "r6_events_accepted": int(certified.get("accepted_count") or 0),
        "r6_events_rejected": int(certified.get("rejected_count") or 0),
    }
    limitations = list(dict.fromkeys(
        list(analysis.get("limitations") or [])
        + list(certified.get("limitations") or [])
        + ([] if semantic_clips else ["NO_CERTIFIED_R6_SEMANTIC_EVENT_USED"])
    ))
    return {
        "ok": True,
        "schema": "zerocut.gameplay-director.v1",
        "mode": mode,
        "duration": round(duration, 4),
        "keep_clips": keep_clips,
        "removed_ranges": dead_ranges,
        "transaction": receipt,
        "metrics": metrics,
        "semantic": certified,
        "ocr": ocr,
        "analysis_summary": summary,
        "limitations": limitations,
    }


def apply_gameplay_proposal(state: dict, proposal: dict) -> dict:
    current = copy.deepcopy(state)
    receipt = (proposal or {}).get("transaction") or {}
    before = current.get("segments") or receipt.get("before") or []
    commit = base.commit_director_segment_transaction(
        before,
        receipt,
        expected_revision=str(receipt.get("expected_revision") or ""),
    )
    if not commit.get("ok"):
        return {"ok": False, "error": commit.get("error", "GAMEPLAY_APPLY_FAILED"), "state": current, "commit": commit}
    current["segments"] = commit.get("segments") or []
    current["selected_segment"] = current["segments"][0]["id"] if current["segments"] else None
    current["gameplay_autoedit_proposal"] = None
    return {"ok": True, "state": current, "commit": commit, "metrics": (proposal or {}).get("metrics") or {}}


def cancel_gameplay_proposal(state: dict, proposal: dict | None = None) -> dict:
    current = copy.deepcopy(state)
    current["gameplay_autoedit_proposal"] = None
    return {"ok": True, "state": current, "cancelled": bool(proposal)}


def _enhance_gameplay_ui() -> None:
    web = base.WEB
    html_path, js_path, css_path = web / "index.html", web / "app.js", web / "styles.css"
    try:
        html = html_path.read_text(encoding="utf-8")
        if UI_MARKER not in html:
            card = """
<section id="gameplayDirectorCard" class="panel zc-gameplay-director" data-feature="zerocut-gameplay-director-run121">
  <div class="zc-gameplay-head">
    <div>
      <div class="eyebrow">Gaming AI · montaggio locale</div>
      <h2>Montaggio gameplay</h2>
      <p class="muted">Analizza il video sul PC, propone una timeline diversa e aspetta la tua conferma prima di applicarla.</p>
    </div>
    <span id="gameplayDirectorBadge" class="zc-whisper-badge" data-state="idle">Pronto</span>
  </div>
  <div id="gameplayDirectorSummary" class="zc-gameplay-summary">Nessuna proposta attiva.</div>
  <div class="zc-gameplay-actions">
    <button id="previewGameplayEdit" type="button" class="primary">Crea anteprima</button>
    <button id="applyGameplayEdit" type="button" disabled>Applica montaggio</button>
    <button id="cancelGameplayEdit" type="button" disabled>Annulla</button>
  </div>
</section>
"""
            html = html.replace("</main>", card + "\n</main>", 1) if "</main>" in html else html.replace("</body>", card + "\n</body>", 1)
            html_path.write_text(html, encoding="utf-8")

        js = js_path.read_text(encoding="utf-8")
        if UI_MARKER not in js:
            js += r'''
// zerocut-gameplay-director-run121
(() => {
  const preview = document.getElementById("previewGameplayEdit");
  const apply = document.getElementById("applyGameplayEdit");
  const cancel = document.getElementById("cancelGameplayEdit");
  const summary = document.getElementById("gameplayDirectorSummary");
  const badge = document.getElementById("gameplayDirectorBadge");
  if (!preview || !apply || !cancel || !summary || !badge) return;
  let revision = null;
  const fmt = v => Number(v || 0).toFixed(1) + " s";
  const busy = text => { badge.dataset.state = "idle"; badge.textContent = text; };
  preview.addEventListener("click", async () => {
    preview.disabled = true; busy("Analisi…"); summary.textContent = "Analisi locale di video, audio, testo e segnali gameplay in corso…";
    try {
      const res = await fetch("/api/gameplay/autoedit/preview", {method:"POST",headers:{"Content-Type":"application/json"},body:"{}"});
      const data = await res.json(); if (!res.ok || !data.ok) throw new Error(data.error || "Anteprima non disponibile");
      revision = data.project_revision || null; const m = data.plan.metrics || {}; const a = data.plan.analysis_summary || {};
      summary.textContent = "Prima " + fmt(m.before_duration) + " → Dopo " + fmt(m.after_duration) +
        " · tagliati " + fmt(m.removed_duration) + " · modalità " + data.plan.mode +
        " · Whisper " + (a.speech_generated ? "OK" : "fallback") + " · OCR " + (a.ocr_executed ? "OK" : "non disponibile");
      badge.dataset.state = "ok"; badge.textContent = "Anteprima pronta"; apply.disabled = false; cancel.disabled = false;
    } catch (err) { badge.dataset.state = "error"; badge.textContent = "Da controllare"; summary.textContent = String(err); }
    finally { preview.disabled = false; }
  });
  apply.addEventListener("click", async () => {
    apply.disabled = true; busy("Applico…");
    try {
      const res = await fetch("/api/gameplay/autoedit/apply", {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({project_revision:revision})});
      const data = await res.json(); if (!res.ok || !data.ok) throw new Error(data.error || "Applicazione non riuscita");
      badge.dataset.state = "ok"; badge.textContent = "Applicato"; summary.textContent += " · TIMELINE APPLICATA. Ora puoi esportare con il QC esistente."; cancel.disabled = true;
    } catch (err) { badge.dataset.state = "error"; badge.textContent = "Errore"; summary.textContent = String(err); apply.disabled = false; }
  });
  cancel.addEventListener("click", async () => {
    cancel.disabled = true;
    try {
      const res = await fetch("/api/gameplay/autoedit/cancel", {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({project_revision:revision})});
      const data = await res.json(); if (!res.ok || !data.ok) throw new Error(data.error || "Annullamento non riuscito");
      revision = null; apply.disabled = true; badge.dataset.state = "idle"; badge.textContent = "Pronto"; summary.textContent = "Anteprima annullata. Timeline invariata.";
    } catch (err) { badge.dataset.state = "error"; badge.textContent = "Errore"; summary.textContent = String(err); cancel.disabled = false; }
  });
})();
'''
            js_path.write_text(js, encoding="utf-8")

        css = css_path.read_text(encoding="utf-8")
        if UI_MARKER not in css:
            css += r'''
/* zerocut-gameplay-director-run121 */
.zc-gameplay-director{margin-top:18px;display:grid;gap:14px}
.zc-gameplay-head{display:flex;gap:18px;align-items:flex-start;justify-content:space-between}
.zc-gameplay-head h2{margin:.15rem 0 .35rem}
.zc-gameplay-summary{padding:12px;border-radius:12px;background:rgba(255,255,255,.035);border:1px solid rgba(255,255,255,.07);line-height:1.45}
.zc-gameplay-actions{display:flex;gap:10px;flex-wrap:wrap}
@media(max-width:700px){.zc-gameplay-head{display:grid}.zc-gameplay-actions button{flex:1 1 100%}}
'''
            css_path.write_text(css, encoding="utf-8")
    except OSError:
        return


class Handler(runtime.Handler):
    def do_POST(self):
        path = urlparse(self.path).path
        try:
            if path == "/api/gameplay/autoedit/preview":
                payload = self._body_json()
                state = base.load_state()
                revision = base.project_state_revision(state)
                source = base.media_file(state)
                events = payload.get("r6_events")
                if not isinstance(events, list):
                    events = state.get("r6_events") if isinstance(state.get("r6_events"), list) else []
                plan = plan_gameplay_autoedit(
                    state, source, r6_events=events,
                    language=str(payload.get("language") or "auto")[:16],
                    run_whisper=payload.get("whisper", True) is not False,
                    run_ocr=payload.get("ocr", True) is not False,
                )
                if not plan.get("ok"):
                    base.json_response(self, {"ok": False, "error": plan.get("error"), "plan": plan}, 422)
                    return
                state["gameplay_autoedit_proposal"] = plan
                base.save_state(state, expected_revision=revision)
                base.json_response(self, {
                    "ok": True, "plan": plan,
                    "project_revision": base.project_state_revision(state),
                }, 200)
                return

            if path == "/api/gameplay/autoedit/apply":
                payload = self._body_json()
                state = base.load_state()
                revision = base.project_state_revision(state)
                expected = payload.get("project_revision")
                if expected and str(expected) != revision:
                    base.json_response(self, {"ok": False, "error": "PROJECT_REVISION_CONFLICT"}, 409)
                    return
                proposal = state.get("gameplay_autoedit_proposal") or {}
                applied = apply_gameplay_proposal(state, proposal)
                if not applied.get("ok"):
                    base.json_response(self, {"ok": False, "error": applied.get("error")}, 409)
                    return
                new_state = applied["state"]
                base.save_state(new_state, expected_revision=revision)
                base.json_response(self, {
                    "ok": True, "project": new_state,
                    "commit": applied.get("commit"), "metrics": applied.get("metrics"),
                }, 200)
                return

            if path == "/api/gameplay/autoedit/cancel":
                payload = self._body_json()
                state = base.load_state()
                revision = base.project_state_revision(state)
                expected = payload.get("project_revision")
                if expected and str(expected) != revision:
                    base.json_response(self, {"ok": False, "error": "PROJECT_REVISION_CONFLICT"}, 409)
                    return
                cancelled = cancel_gameplay_proposal(state, state.get("gameplay_autoedit_proposal"))
                base.save_state(cancelled["state"], expected_revision=revision)
                base.json_response(self, {"ok": True, "project": cancelled["state"]}, 200)
                return
        except base.ProjectRevisionConflict as exc:
            base.json_response(self, {"ok": False, "error": str(exc), "code": "PROJECT_REVISION_CONFLICT"}, 409)
            return
        except (ValueError, json.JSONDecodeError, OSError) as exc:
            base.json_response(self, {"ok": False, "error": str(exc)}, 400)
            return
        return super().do_POST()


_enhance_gameplay_ui()


def main():
    runtime.Handler = Handler
    runtime.RUNTIME_NAME = RUNTIME_NAME
    runtime.main()


if __name__ == "__main__":
    main()
