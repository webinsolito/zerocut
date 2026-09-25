from __future__ import annotations
import importlib.machinery, importlib.util, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "ZeroCut_Run113_Candidate_TranscriptEdit.pyw"

def load():
    name = "zc_run113_regression"
    loader = importlib.machinery.SourceFileLoader(name, str(SOURCE))
    spec = importlib.util.spec_from_loader(name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    loader.exec_module(module)
    return module

def route_block(text: str, start: str, end: str) -> str:
    assert start in text, start
    return text.split(start, 1)[1].split(end, 1)[0]

def main():
    text = SOURCE.read_text(encoding="utf-8")

    cancel = route_block(
        text,
        'if path in {"/api/transcript/edit/cancel","/api/autoedit/cancel"}:',
        "except base.ProjectRevisionConflict",
    )
    assert "payload=self._body_json()" in cancel, "cancel must read request JSON before project_revision"
    assert 'payload.get("project_revision")' in cancel

    apply = route_block(
        text,
        'if path=="/api/transcript/edit/apply":',
        'if path in {"/api/transcript/edit/cancel","/api/autoedit/cancel"}:',
    )
    assert "PROJECT_REVISION_CONFLICT" in apply
    assert "commit_director_segment_transaction" in apply

    analyze = route_block(
        text,
        'if path=="/api/analyze/transcript":',
        'if path=="/api/transcript/edit/preview":',
    )
    assert '"segments":result.get("segments") or []' in analyze
    assert 'state["last_transcript_full"]' in analyze

    m = load()
    state = {
        "media": {"metadata": {"duration": 10.0}},
        "segments": [{"id": "source0", "start": 0.0, "end": 10.0}],
        "last_transcript_full": {
            "segments": [
                {"id": "speech-1", "start": 2.0, "end": 4.0, "text": "remove this phrase"},
                {"id": "speech-2", "start": 6.0, "end": 7.0, "text": "keep this phrase"},
            ]
        },
    }

    receipt = m.prepare_transcript_edit(state, ["speech-1"], padding=0.0)
    assert receipt.get("ok") is True, receipt
    metrics = m.transcript_edit_metrics(state, receipt)
    assert metrics["timeline_changed"] is True, metrics
    assert metrics["after_duration"] < metrics["before_duration"], metrics
    assert metrics["removed_duration"] > 0.0, metrics
    assert receipt.get("requires_preview") is True
    assert "speech-1" in (receipt.get("selected_ids") or [])

    empty = m.prepare_transcript_edit(state, [], padding=0.0)
    assert empty.get("ok") is False, empty

    print("ZEROCUT_RUN116_TRANSCRIPT_REGRESSION=PASS")
    print(
        "RUN116_TIMELINE_BEFORE="
        + str(metrics["before_duration"])
        + " AFTER="
        + str(metrics["after_duration"])
        + " REMOVED="
        + str(metrics["removed_duration"])
    )

if __name__ == "__main__":
    main()
