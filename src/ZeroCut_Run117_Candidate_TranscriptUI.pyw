#!/usr/bin/env python3
from __future__ import annotations

import importlib.machinery
import importlib.util
import sys
from pathlib import Path
from urllib.parse import urlparse

BASE_PATH = Path(__file__).with_name("ZeroCut_Run113_Candidate_TranscriptEdit.pyw")
_loader = importlib.machinery.SourceFileLoader("zerocut_run113", str(BASE_PATH))
_spec = importlib.util.spec_from_loader("zerocut_run113", _loader)
if _spec is None:
    raise RuntimeError("RUN113_BASE_NOT_LOADABLE")
core = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = core
_loader.exec_module(core)

UI_MARKER = "zerocut-transcript-editor-run117"

def _enhance_transcript_edit_ui() -> None:
    """Add a compact text-based edit surface to the verified Whisper card."""
    web = core.base.WEB
    html_path, js_path, css_path = web / "index.html", web / "app.js", web / "styles.css"
    try:
        html = html_path.read_text(encoding="utf-8")
        if UI_MARKER not in html:
            panel = """
<div id="transcriptEditor" class="zc-transcript-editor" data-feature="zerocut-transcript-editor-run117">
  <div class="zc-transcript-toolbar">
    <button id="loadTranscriptBlocks" type="button">Modifica dal testo</button>
    <span id="transcriptEditStatus" class="muted">Trascrivi prima il video, poi seleziona le frasi da rimuovere.</span>
  </div>
  <div id="transcriptBlocks" class="zc-transcript-blocks" aria-live="polite"></div>
  <div id="transcriptEditReview" class="zc-transcript-review" hidden>
    <strong id="transcriptEditMetrics">Nessuna anteprima.</strong>
    <div class="zc-transcript-actions">
      <button id="previewTranscriptEdit" type="button">Anteprima taglio</button>
      <button id="applyTranscriptEdit" type="button" class="primary" disabled>Applica</button>
      <button id="cancelTranscriptEdit" type="button" disabled>Annulla</button>
    </div>
  </div>
</div>
"""
            anchor = '<pre id="whisperPreview"'
            if anchor in html:
                pre_start = html.index(anchor)
                pre_end = html.index("</pre>", pre_start) + len("</pre>")
                html = html[:pre_end] + "\n" + panel + html[pre_end:]
            else:
                html = html.replace("</section>", panel + "\n</section>", 1)
            html_path.write_text(html, encoding="utf-8")

        js = js_path.read_text(encoding="utf-8")
        if UI_MARKER not in js:
            js += r'''
// zerocut-transcript-editor-run117
(() => {
  const loadBtn = document.getElementById("loadTranscriptBlocks");
  const blocks = document.getElementById("transcriptBlocks");
  const status = document.getElementById("transcriptEditStatus");
  const review = document.getElementById("transcriptEditReview");
  const metrics = document.getElementById("transcriptEditMetrics");
  const previewBtn = document.getElementById("previewTranscriptEdit");
  const applyBtn = document.getElementById("applyTranscriptEdit");
  const cancelBtn = document.getElementById("cancelTranscriptEdit");
  if (!loadBtn || !blocks || !status || !review || !metrics || !previewBtn || !applyBtn || !cancelBtn) return;

  let projectRevision = null;
  let proposalActive = false;

  const fmt = (v) => Number(v || 0).toFixed(1) + " s";
  const selectedIds = () => Array.from(blocks.querySelectorAll('input[type="checkbox"]:checked')).map(x => x.value);

  const resetProposal = () => {
    projectRevision = null;
    proposalActive = false;
    applyBtn.disabled = true;
    cancelBtn.disabled = true;
    metrics.textContent = "Nessuna anteprima.";
  };

  const renderSegments = (rows) => {
    blocks.textContent = "";
    if (!Array.isArray(rows) || !rows.length) {
      blocks.textContent = "Nessun blocco trascritto disponibile.";
      review.hidden = true;
      return;
    }
    const frag = document.createDocumentFragment();
    rows.forEach((seg, index) => {
      const id = String(seg.id || ("segment-" + index));
      const label = document.createElement("label");
      label.className = "zc-transcript-row";
      const input = document.createElement("input");
      input.type = "checkbox";
      input.value = id;
      const time = document.createElement("span");
      time.className = "zc-transcript-time";
      time.textContent = fmt(seg.start) + " – " + fmt(seg.end);
      const text = document.createElement("span");
      text.className = "zc-transcript-text";
      text.textContent = String(seg.text || "").trim() || "(senza testo)";
      label.append(input, time, text);
      frag.appendChild(label);
    });
    blocks.appendChild(frag);
    review.hidden = false;
    resetProposal();
  };

  loadBtn.addEventListener("click", async () => {
    loadBtn.disabled = true;
    status.textContent = "Carico i blocchi trascritti…";
    try {
      const res = await fetch("/api/transcript/segments", {cache:"no-store"});
      const data = await res.json();
      if (!res.ok || !data.ok) throw new Error(data.error || "Trascrizione completa non disponibile");
      renderSegments(data.segments);
      status.textContent = String(data.segments.length) + " blocchi pronti. Seleziona solo ciò che vuoi rimuovere.";
    } catch (err) {
      renderSegments([]);
      status.textContent = String(err);
    } finally {
      loadBtn.disabled = false;
    }
  });

  previewBtn.addEventListener("click", async () => {
    const ids = selectedIds();
    if (!ids.length) {
      status.textContent = "Seleziona almeno una frase da rimuovere.";
      return;
    }
    previewBtn.disabled = true;
    status.textContent = "Calcolo anteprima senza modificare la timeline…";
    try {
      const res = await fetch("/api/transcript/edit/preview", {
        method:"POST",
        headers:{"Content-Type":"application/json"},
        body:JSON.stringify({selected_ids:ids})
      });
      const data = await res.json();
      if (!res.ok || !data.ok) throw new Error(data.error || "Anteprima non disponibile");
      const m = data.metrics || {};
      projectRevision = data.project_revision || null;
      proposalActive = true;
      metrics.textContent = "Prima " + fmt(m.before_duration) + " → Dopo " + fmt(m.after_duration) + " · rimossi " + fmt(m.removed_duration);
      applyBtn.disabled = false;
      cancelBtn.disabled = false;
      status.textContent = "Anteprima pronta. La timeline non è ancora stata modificata.";
    } catch (err) {
      resetProposal();
      status.textContent = String(err);
    } finally {
      previewBtn.disabled = false;
    }
  });

  applyBtn.addEventListener("click", async () => {
    if (!proposalActive) return;
    applyBtn.disabled = true;
    try {
      const res = await fetch("/api/transcript/edit/apply", {
        method:"POST",
        headers:{"Content-Type":"application/json"},
        body:JSON.stringify({project_revision:projectRevision})
      });
      const data = await res.json();
      if (!res.ok || !data.ok) throw new Error(data.error || "Applicazione non riuscita");
      status.textContent = "Taglio applicato alla timeline.";
      proposalActive = false;
      cancelBtn.disabled = true;
      metrics.textContent += " · APPLICATO";
    } catch (err) {
      status.textContent = String(err);
      applyBtn.disabled = false;
    }
  });

  cancelBtn.addEventListener("click", async () => {
    cancelBtn.disabled = true;
    try {
      const res = await fetch("/api/transcript/edit/cancel", {
        method:"POST",
        headers:{"Content-Type":"application/json"},
        body:JSON.stringify({project_revision:projectRevision})
      });
      const data = await res.json();
      if (!res.ok || !data.ok) throw new Error(data.error || "Annullamento non riuscito");
      resetProposal();
      status.textContent = "Anteprima annullata. Timeline invariata.";
    } catch (err) {
      status.textContent = String(err);
      cancelBtn.disabled = false;
    }
  });
})();
'''
            js_path.write_text(js, encoding="utf-8")

        css = css_path.read_text(encoding="utf-8")
        if UI_MARKER not in css:
            css += r'''
/* zerocut-transcript-editor-run117 */
.zc-transcript-editor{margin-top:14px;padding-top:14px;border-top:1px solid rgba(255,255,255,.08);display:grid;gap:12px}
.zc-transcript-toolbar,.zc-transcript-actions{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.zc-transcript-blocks{display:grid;gap:8px;max-height:280px;overflow:auto}
.zc-transcript-row{display:grid;grid-template-columns:auto 92px 1fr;gap:10px;align-items:start;padding:10px 12px;border-radius:12px;background:rgba(255,255,255,.035);border:1px solid rgba(255,255,255,.07);cursor:pointer}
.zc-transcript-row:has(input:checked){border-color:rgba(250,204,21,.48);background:rgba(250,204,21,.07)}
.zc-transcript-time{font-variant-numeric:tabular-nums;font-size:.8rem;opacity:.72}
.zc-transcript-text{line-height:1.45}
.zc-transcript-review{display:grid;gap:10px;padding:12px;border-radius:12px;background:rgba(0,0,0,.16)}
@media(max-width:700px){.zc-transcript-row{grid-template-columns:auto 1fr}.zc-transcript-time{grid-column:2}.zc-transcript-actions button{flex:1 1 30%}}
'''
            css_path.write_text(css, encoding="utf-8")
    except OSError:
        return

class Handler(core.Handler):
    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/transcript/segments":
            state = core.base.load_state()
            full = state.get("last_transcript_full") or {}
            segments = full.get("segments") if isinstance(full, dict) else None
            if not isinstance(segments, list) or not segments:
                core.base.json_response(self, {"ok": False, "error": "FULL_TRANSCRIPT_NOT_AVAILABLE", "segments": []}, 404)
                return
            core.base.json_response(
                self,
                {
                    "ok": True,
                    "segments": segments,
                    "project_revision": core.base.project_state_revision(state),
                },
                200,
            )
            return
        return super().do_GET()

_enhance_transcript_edit_ui()

def main():
    core.Handler = Handler
    core.main()

if __name__ == "__main__":
    main()
