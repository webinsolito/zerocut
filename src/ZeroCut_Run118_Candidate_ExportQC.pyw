#!/usr/bin/env python3
from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import os
import sys
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse

BASE_PATH = Path(__file__).with_name("ZeroCut_Run117_Candidate_TranscriptUI.pyw")
_loader = importlib.machinery.SourceFileLoader("zerocut_run117", str(BASE_PATH))
_spec = importlib.util.spec_from_loader("zerocut_run117", _loader)
if _spec is None:
    raise RuntimeError("RUN117_BASE_NOT_LOADABLE")
ui = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = ui
_loader.exec_module(ui)

base = ui.core.base
EXPORT_QC_FILE = base.DIAGNOSTICS / "last-export-qc.json"
UI_MARKER = "zerocut-export-qc-run118"


def _atomic_json(path: Path, payload: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".{uuid.uuid4().hex[:8]}.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def read_latest_export_qc() -> dict | None:
    try:
        row = json.loads(EXPORT_QC_FILE.read_text(encoding="utf-8"))
        return row if isinstance(row, dict) else None
    except (FileNotFoundError, OSError, json.JSONDecodeError, TypeError):
        return None


_original_verify_render_output = base.verify_render_output


def verify_render_output_with_qc(path: Path, expected_duration: float, *, expect_audio: bool = False,
                                 ffmpeg_bin: str | None = None, ffprobe_bin: str | None = None) -> dict:
    """Verify a real render and persist a compact proof when it is an actual ZeroCut export."""
    result = _original_verify_render_output(
        path,
        expected_duration,
        expect_audio=expect_audio,
        ffmpeg_bin=ffmpeg_bin,
        ffprobe_bin=ffprobe_bin,
    )
    p = Path(path)
    try:
        is_export = p.resolve().parent == base.RENDER.resolve()
    except OSError:
        is_export = False
    if is_export:
        final_name = p.name.replace(".working.mp4", ".mp4") if p.name.endswith(".working.mp4") else p.name
        av = result.get("av_timing") if isinstance(result.get("av_timing"), dict) else {}
        decode = result.get("decode_smoke") if isinstance(result.get("decode_smoke"), dict) else {}
        record = {
            "schema": "zerocut.export-qc.v1",
            "ok": bool(result.get("ok")),
            "verified_at": time.time(),
            "file": final_name,
            "expected_duration": round(float(expected_duration or 0.0), 4),
            "actual_duration": round(float(result.get("duration") or 0.0), 4),
            "size_bytes": int(result.get("size") or 0),
            "audio_expected": bool(expect_audio),
            "av_sync_ok": bool(av.get("ok")),
            "av_start_delta": av.get("start_delta"),
            "av_duration_delta": av.get("duration_delta"),
            "decode_ok": bool(decode.get("ok")),
            "decode_points": list(decode.get("checked") or []),
        }
        _atomic_json(EXPORT_QC_FILE, record)
        result["qc_record"] = record
    return result


# Patch the exact function used by the existing /api/export async commit callback.
base.verify_render_output = verify_render_output_with_qc


def _enhance_export_qc_ui() -> None:
    web = base.WEB
    html_path, js_path, css_path = web / "index.html", web / "app.js", web / "styles.css"
    try:
        html = html_path.read_text(encoding="utf-8")
        if UI_MARKER not in html:
            card = """
<section id="exportQcCard" class="panel zc-export-qc" data-feature="zerocut-export-qc-run118" aria-labelledby="exportQcTitle">
  <div class="zc-export-qc-head">
    <div>
      <div class="eyebrow">Export · controllo qualità</div>
      <h2 id="exportQcTitle">Ultimo video esportato</h2>
      <p class="muted">ZeroCut pubblica l'export solo dopo controllo durata, audio/video e decodifica reale.</p>
    </div>
    <span id="exportQcBadge" class="zc-whisper-badge" data-state="idle">Nessun QC</span>
  </div>
  <div id="exportQcMetrics" class="zc-export-qc-metrics">
    <span>Durata: —</span><span>Dimensione: —</span><span>A/V: —</span><span>Decode: —</span>
  </div>
  <div class="zc-export-qc-actions">
    <button id="refreshExportQc" type="button">Aggiorna controllo</button>
    <span id="exportQcFile" class="muted">Nessun export verificato in questa sessione.</span>
  </div>
</section>
"""
            html = html.replace("</main>", card + "\n</main>", 1) if "</main>" in html else html.replace("</body>", card + "\n</body>", 1)
            html_path.write_text(html, encoding="utf-8")

        js = js_path.read_text(encoding="utf-8")
        if UI_MARKER not in js:
            js += r'''
// zerocut-export-qc-run118
(() => {
  const card = document.getElementById("exportQcCard");
  const badge = document.getElementById("exportQcBadge");
  const metrics = document.getElementById("exportQcMetrics");
  const file = document.getElementById("exportQcFile");
  const refresh = document.getElementById("refreshExportQc");
  if (!card || !badge || !metrics || !file || !refresh) return;

  const fmt = (seconds) => Number(seconds || 0).toFixed(2) + " s";
  const mb = (bytes) => (Number(bytes || 0) / 1048576).toFixed(1) + " MB";

  const render = (qc) => {
    if (!qc || !qc.ok) {
      badge.dataset.state = "idle";
      badge.textContent = "Nessun QC";
      metrics.innerHTML = "<span>Durata: —</span><span>Dimensione: —</span><span>A/V: —</span><span>Decode: —</span>";
      file.textContent = "Nessun export verificato in questa sessione.";
      return;
    }
    const durationOk = Math.abs(Number(qc.actual_duration) - Number(qc.expected_duration)) <= Math.max(.35, Number(qc.expected_duration) * .02);
    const allOk = durationOk && qc.av_sync_ok && qc.decode_ok;
    badge.dataset.state = allOk ? "ok" : "error";
    badge.textContent = allOk ? "Verificato" : "Da controllare";
    metrics.innerHTML =
      "<span>Durata: " + fmt(qc.actual_duration) + " / " + fmt(qc.expected_duration) + "</span>" +
      "<span>Dimensione: " + mb(qc.size_bytes) + "</span>" +
      "<span>A/V: " + (qc.av_sync_ok ? "OK" : "ERRORE") + "</span>" +
      "<span>Decode: " + (qc.decode_ok ? "OK" : "ERRORE") + "</span>";
    file.textContent = qc.file || "Export verificato";
  };

  async function loadQc() {
    try {
      const res = await fetch("/api/export/qc/latest", {cache:"no-store"});
      if (res.status === 404) { render(null); return; }
      const data = await res.json();
      render(data.qc || null);
    } catch (_) {}
  }

  refresh.addEventListener("click", loadQc);
  loadQc();
  setInterval(() => { if (!document.hidden) loadQc(); }, 5000);
})();
'''
            js_path.write_text(js, encoding="utf-8")

        css = css_path.read_text(encoding="utf-8")
        if UI_MARKER not in css:
            css += r'''
/* zerocut-export-qc-run118 */
.zc-export-qc{margin-top:18px;display:grid;gap:14px}
.zc-export-qc-head{display:flex;gap:18px;align-items:flex-start;justify-content:space-between}
.zc-export-qc-head h2{margin:.15rem 0 .35rem}
.zc-export-qc-metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px}
.zc-export-qc-metrics span{padding:10px;border-radius:10px;background:rgba(255,255,255,.035);border:1px solid rgba(255,255,255,.07);font-variant-numeric:tabular-nums}
.zc-export-qc-actions{display:flex;gap:12px;align-items:center;flex-wrap:wrap}
@media(max-width:700px){.zc-export-qc-head{display:grid}.zc-export-qc-metrics{grid-template-columns:1fr 1fr}.zc-export-qc-actions button{width:100%}}
'''
            css_path.write_text(css, encoding="utf-8")
    except OSError:
        return


class Handler(ui.Handler):
    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/export/qc/latest":
            qc = read_latest_export_qc()
            if not qc:
                base.json_response(self, {"ok": False, "error": "EXPORT_QC_NOT_AVAILABLE", "qc": None}, 404)
                return
            base.json_response(self, {"ok": True, "qc": qc}, 200)
            return
        return super().do_GET()


_enhance_export_qc_ui()


def main():
    ui.core.Handler = Handler
    ui.core.main()


if __name__ == "__main__":
    main()
