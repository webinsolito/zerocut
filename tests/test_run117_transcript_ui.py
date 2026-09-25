from __future__ import annotations
import importlib.machinery, importlib.util, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "ZeroCut_Run117_Candidate_TranscriptUI.pyw"

def load():
    name = "zc_run117_ui"
    loader = importlib.machinery.SourceFileLoader(name, str(SOURCE))
    spec = importlib.util.spec_from_loader(name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    loader.exec_module(module)
    return module

def main():
    m = load()
    html = (m.core.base.WEB / "index.html").read_text(encoding="utf-8")
    js = (m.core.base.WEB / "app.js").read_text(encoding="utf-8")
    css = (m.core.base.WEB / "styles.css").read_text(encoding="utf-8")

    assert "zerocut-transcript-editor-run117" in html
    assert 'id="loadTranscriptBlocks"' in html
    assert 'id="previewTranscriptEdit"' in html
    assert 'id="applyTranscriptEdit"' in html
    assert 'id="cancelTranscriptEdit"' in html

    for endpoint in (
        "/api/transcript/segments",
        "/api/transcript/edit/preview",
        "/api/transcript/edit/apply",
        "/api/transcript/edit/cancel",
    ):
        assert endpoint in js or endpoint in SOURCE.read_text(encoding="utf-8"), endpoint

    assert ".zc-transcript-row" in css
    assert "Prima " in js and "Dopo " in js
    assert "Timeline invariata" in js

    state = {
        "media": {"metadata": {"duration": 12.0}},
        "segments": [{"id": "source0", "start": 0.0, "end": 12.0}],
        "last_transcript_full": {
            "segments": [
                {"id": "cut-me", "start": 3.0, "end": 5.5, "text": "remove this section"},
                {"id": "keep-me", "start": 7.0, "end": 9.0, "text": "keep this section"},
            ]
        },
    }
    receipt = m.core.prepare_transcript_edit(state, ["cut-me"], padding=0.0)
    assert receipt.get("ok") is True, receipt
    metrics = m.core.transcript_edit_metrics(state, receipt)
    assert metrics["timeline_changed"] is True, metrics
    assert metrics["before_duration"] == 12.0, metrics
    assert metrics["after_duration"] == 9.5, metrics
    assert metrics["removed_duration"] == 2.5, metrics

    print("ZEROCUT_RUN117_TRANSCRIPT_UI=PASS")
    print("RUN117_TIMELINE_BEFORE=12.0 AFTER=9.5 REMOVED=2.5")

if __name__ == "__main__":
    main()
