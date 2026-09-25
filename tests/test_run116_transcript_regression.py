from pathlib import Path

SOURCE = Path("src/ZeroCut_Run112_Candidate_WhisperUX.pyw")


def source_text():
    return SOURCE.read_text(encoding="utf-8")


def test_cancel_reads_payload_before_using_project_revision():
    text = source_text()
    marker = 'if path == "/api/autoedit/cancel":'
    assert marker in text
    block = text.split(marker, 1)[1].split('if path == "/api/analyze/universal":', 1)[0]
    assert "payload = self._body_json()" in block, "cancel uses payload without reading request JSON"
    assert 'payload.get("project_revision")' in block


def test_apply_has_timeline_revision_guard():
    text = source_text()
    marker = 'if path == "/api/autoedit/apply":'
    assert marker in text
    block = text.split(marker, 1)[1].split('if path == "/api/autoedit/cancel":', 1)[0]
    assert "director_timeline_revision(current) != expected" in block
    assert "TIMELINE_REVISION_CONFLICT" in block


def test_transcript_analysis_returns_segments_for_review():
    text = source_text()
    marker = 'if path == "/api/analyze/transcript":'
    assert marker in text
    block = text.split(marker, 1)[1].split('if path == "/api/autoedit/analyze":', 1)[0]
    assert 'body["segments"] = result.get("segments") or []' in block
