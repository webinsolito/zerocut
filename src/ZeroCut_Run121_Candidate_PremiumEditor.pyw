#!/usr/bin/env python3
from __future__ import annotations

import importlib.machinery
import importlib.util
import sys
from pathlib import Path
from urllib.parse import urlparse

BASE_PATH = Path(__file__).with_name("ZeroCut_Run119_Candidate_WindowsReadiness.pyw")
_loader = importlib.machinery.SourceFileLoader("zerocut_run119", str(BASE_PATH))
_spec = importlib.util.spec_from_loader("zerocut_run119", _loader)
if _spec is None:
    raise RuntimeError("RUN119_BASE_NOT_LOADABLE")
app = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = app
_loader.exec_module(app)

base = app.base
RUNTIME_NAME = "Run121_PremiumEditor"
UI_MARKER = "zerocut-premium-editor-run121"


def _enhance_premium_editor() -> None:
    """Polish the real embedded editor without replacing the verified editing core."""
    web = base.WEB
    html_path, js_path, css_path = web / "index.html", web / "app.js", web / "styles.css"
    try:
        html = html_path.read_text(encoding="utf-8")
        if UI_MARKER not in html:
            rail = """
<section id="deliveryFlow" class="zc-delivery-flow" data-feature="zerocut-premium-editor-run121" aria-label="Flusso di montaggio">
  <div class="zc-delivery-brand">
    <span class="zc-delivery-mark" aria-hidden="true">Z</span>
    <div><strong>ZeroCut Studio</strong><small>Editor gaming locale</small></div>
  </div>
  <ol class="zc-delivery-steps">
    <li data-stage="import"><span>1</span><b>Importa</b></li>
    <li data-stage="analysis"><span>2</span><b>Analizza</b></li>
    <li data-stage="review"><span>3</span><b>Rivedi</b></li>
    <li data-stage="export"><span>4</span><b>Esporta</b></li>
  </ol>
  <div class="zc-local-pill"><i></i><span id="zcLocalStatus">Locale · dati privati</span></div>
</section>
"""
            anchor = html.find("<main")
            if anchor >= 0:
                html = html[:anchor] + rail + "\n" + html[anchor:]
            else:
                html = html.replace("<body>", "<body>\n" + rail, 1)
            html_path.write_text(html, encoding="utf-8")

        js = js_path.read_text(encoding="utf-8")
        if UI_MARKER not in js:
            js += r'''
// zerocut-premium-editor-run121
(() => {
  const rail = document.getElementById("deliveryFlow");
  if (!rail) return;
  const stages = Array.from(rail.querySelectorAll("[data-stage]"));
  const setStage = (name) => {
    const order = ["import", "analysis", "review", "export"];
    const active = Math.max(0, order.indexOf(name));
    stages.forEach((node, index) => {
      node.dataset.state = index < active ? "done" : index === active ? "active" : "pending";
    });
  };
  setStage("import");

  const localStatus = document.getElementById("zcLocalStatus");
  const engineText = document.getElementById("engineText");
  const engineDot = document.getElementById("engineDot");
  const mirrorEngine = () => {
    if (!localStatus || !engineText) return;
    const value = (engineText.textContent || "").trim();
    localStatus.textContent = value && !/controllo/i.test(value) ? value : "Locale · dati privati";
    rail.dataset.engine = engineDot && engineDot.classList.contains("bad") ? "error" : "ready";
  };
  if (engineText) new MutationObserver(mirrorEngine).observe(engineText, {childList:true, subtree:true, characterData:true});
  if (engineDot) new MutationObserver(mirrorEngine).observe(engineDot, {attributes:true, attributeFilter:["class"]});
  mirrorEngine();

  const bind = (id, stage) => {
    const node = document.getElementById(id);
    if (node) node.addEventListener("click", () => setStage(stage));
  };
  ["runWhisperTranscript", "loadTranscriptBlocks"].forEach(id => bind(id, "analysis"));
  ["previewTranscriptEdit", "applyTranscriptEdit", "cancelTranscriptEdit"].forEach(id => bind(id, "review"));
  ["refreshExportQc"].forEach(id => bind(id, "export"));

  document.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "e") {
      event.preventDefault();
      const exportButton = Array.from(document.querySelectorAll("button")).find(
        button => /esporta|export/i.test(button.textContent || "")
      );
      if (exportButton && !exportButton.disabled) exportButton.click();
    }
  });
})();
'''
            js_path.write_text(js, encoding="utf-8")

        css = css_path.read_text(encoding="utf-8")
        if UI_MARKER not in css:
            css += r'''
/* zerocut-premium-editor-run121 */
:root{
  --zc-ink:#f7f8fc;--zc-muted:#909aab;--zc-bg:#07090d;--zc-panel:#10141b;
  --zc-panel-2:#151b24;--zc-line:rgba(255,255,255,.09);--zc-violet:#7868ff;
  --zc-cyan:#3dc9e8;--zc-good:#52d7a2;--zc-shadow:0 22px 70px rgba(0,0,0,.34);
}
html{background:var(--zc-bg)}
*,*:before,*:after{box-sizing:border-box}
html,body{width:100%;max-width:100%;overflow-x:hidden}
body{
  color:var(--zc-ink);
  background:
    radial-gradient(900px 440px at 52% -160px,rgba(120,104,255,.20),transparent 68%),
    radial-gradient(680px 360px at 100% 30%,rgba(61,201,232,.08),transparent 70%),
    linear-gradient(180deg,#090c12 0%,#06080c 100%)!important;
}
body:before{
  content:"";position:fixed;inset:0;pointer-events:none;opacity:.18;z-index:-1;
  background-image:linear-gradient(rgba(255,255,255,.018) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.018) 1px,transparent 1px);
  background-size:28px 28px;
}
.zc-delivery-flow{
  width:min(1480px,calc(100% - 32px));margin:16px auto 4px;padding:12px 14px;
  display:grid;grid-template-columns:minmax(210px,1fr) auto minmax(210px,1fr);
  align-items:center;gap:20px;border:1px solid var(--zc-line);border-radius:18px;
  background:linear-gradient(145deg,rgba(21,27,36,.92),rgba(10,13,19,.94));
  box-shadow:0 14px 50px rgba(0,0,0,.26),inset 0 1px rgba(255,255,255,.035);
  backdrop-filter:blur(24px);-webkit-backdrop-filter:blur(24px);
}
.zc-delivery-brand{display:flex;align-items:center;gap:11px;min-width:0}
.zc-delivery-brand strong,.zc-delivery-brand small{display:block}
.zc-delivery-brand strong{font-size:15px;letter-spacing:-.025em}
.zc-delivery-brand small{margin-top:1px;color:var(--zc-muted);font-size:11px}
.zc-delivery-mark{
  width:38px;height:38px;display:grid;place-items:center;border-radius:12px;font-weight:950;
  background:linear-gradient(145deg,#9589ff,#6657e7 58%,#4233bb);
  box-shadow:0 10px 30px rgba(105,88,232,.32),inset 0 1px 1px rgba(255,255,255,.36);
}
.zc-delivery-steps{list-style:none;margin:0;padding:0;display:flex;align-items:center;gap:9px}
.zc-delivery-steps li{display:flex;align-items:center;gap:6px;color:#687386;font-size:11px;font-weight:760}
.zc-delivery-steps li:not(:last-child):after{content:"";width:26px;height:1px;margin-left:3px;background:#293241}
.zc-delivery-steps span{width:25px;height:25px;display:grid;place-items:center;border-radius:50%;border:1px solid #303a4a;background:#111720;font-size:10px}
.zc-delivery-steps li[data-state="active"]{color:#fff}
.zc-delivery-steps li[data-state="active"] span{border-color:#958aff;background:var(--zc-violet);box-shadow:0 0 0 5px rgba(120,104,255,.12)}
.zc-delivery-steps li[data-state="done"]{color:#a7b1c0}
.zc-delivery-steps li[data-state="done"] span{color:#07130f;border-color:#49c894;background:var(--zc-good)}
.zc-local-pill{justify-self:end;display:flex;align-items:center;gap:7px;padding:7px 10px;border:1px solid var(--zc-line);border-radius:999px;color:#b1bac8;font-size:10px;background:rgba(3,6,10,.38)}
.zc-local-pill i{width:7px;height:7px;border-radius:50%;background:var(--zc-good);box-shadow:0 0 12px rgba(82,215,162,.8)}
.zc-delivery-flow[data-engine="error"] .zc-local-pill{border-color:rgba(255,108,125,.5);color:#ffc1c9}.zc-delivery-flow[data-engine="error"] .zc-local-pill i{background:#ff6c7d;box-shadow:0 0 12px rgba(255,108,125,.7)}
body>.studioTopbar{display:none!important}
main{width:min(1480px,calc(100% - 32px));margin-inline:auto}
.panel,.card,section[class*="panel"]{
  border-color:var(--zc-line)!important;border-radius:16px!important;
  background:linear-gradient(150deg,rgba(19,25,34,.94),rgba(11,15,21,.96))!important;
  box-shadow:0 12px 38px rgba(0,0,0,.22),inset 0 1px rgba(255,255,255,.025)!important;
}
button{
  min-height:38px;border-radius:10px!important;border-color:rgba(255,255,255,.11)!important;
  transition:transform .16s ease,border-color .16s ease,background .16s ease,box-shadow .16s ease!important;
}
button:hover:not(:disabled){transform:translateY(-1px);border-color:rgba(145,132,255,.62)!important}
button.primary,.primary{
  background:linear-gradient(135deg,#887aff,#6859e8)!important;
  box-shadow:0 10px 26px rgba(100,82,225,.25),inset 0 1px rgba(255,255,255,.22)!important;
}
input,textarea,select,pre{
  border-radius:11px!important;border-color:rgba(255,255,255,.10)!important;
  background:rgba(2,5,9,.45)!important;
}
.eyebrow{color:#9e93ff!important;letter-spacing:.13em;font-weight:850}
.muted{color:var(--zc-muted)!important}
.zc-transcript-row{
  border-radius:11px!important;border:1px solid transparent;padding:9px 10px!important;
  transition:background .15s ease,border-color .15s ease;
}
.zc-transcript-row:hover{background:rgba(120,104,255,.07);border-color:rgba(120,104,255,.2)}
.zc-export-qc-metrics span{border-radius:12px!important;background:rgba(255,255,255,.03)!important}
@media(max-width:980px){
  .zc-delivery-flow{grid-template-columns:1fr auto}
  .zc-delivery-steps{grid-column:1/-1;grid-row:2;justify-content:center}
}
@media(max-width:560px){
  .zc-delivery-flow{width:calc(100% - 20px);max-width:calc(100% - 20px);margin-top:10px;padding:11px;gap:11px;overflow:hidden}
  .zc-local-pill span{display:none}
  .zc-delivery-steps{width:100%;gap:4px;justify-content:space-between}
  .zc-delivery-steps li{gap:4px;font-size:9px;min-width:0}
  .zc-delivery-steps li b{display:none}
  .zc-delivery-steps li:not(:last-child):after{width:18px}
  .zc-delivery-steps span{width:23px;height:23px}
  main{width:calc(100% - 20px);max-width:calc(100% - 20px);padding:8px!important}
  main>*,main section,.panel,.card{min-width:0!important;max-width:100%!important}
  .studioHero{width:100%!important;padding:34px 18px 38px!important;overflow:hidden}
  .studioHero h1{width:100%;max-width:100%!important;font-size:clamp(32px,10vw,40px)!important;overflow-wrap:anywhere}
  .studioHero>p,.studioDrop{width:100%;max-width:100%!important}
  .studioDrop{min-height:210px!important;padding:18px 12px}
  .panel,.card,section[class*="panel"]{border-radius:14px!important}
}
@media(prefers-reduced-motion:reduce){button,.zc-transcript-row{transition:none!important}}
'''
            css_path.write_text(css, encoding="utf-8")
    except OSError:
        return


class Handler(app.Handler):
    def do_GET(self):
        if urlparse(self.path).path == "/api/ui/version":
            base.json_response(self, {
                "ok": True,
                "runtime": RUNTIME_NAME,
                "ui": UI_MARKER,
                "verified_capabilities": [
                    "transcript-edit-preview-apply-cancel",
                    "timeline-export-qc",
                    "windows-onefile-readiness",
                ],
                "pending_capabilities": [
                    "real-playstation-rainbow-six-certification",
                    "creator-engine-local",
                ],
            }, 200)
            return
        return super().do_GET()


_enhance_premium_editor()


def main():
    app.Handler = Handler
    app.main()


if __name__ == "__main__":
    main()
