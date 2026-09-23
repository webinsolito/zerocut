from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import py_compile
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = ROOT / "src" / "ZeroCut_Run102_Candidate_ProjectRecovery.pyw"


def load_candidate():
    name = "zerocut_run102_project_recovery"
    loader = importlib.machinery.SourceFileLoader(name, str(CANDIDATE))
    spec = importlib.util.spec_from_loader(name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    loader.exec_module(module)
    return module


def sample_state(module, marker: str, updated_at: float | None = None):
    state = module.default_state()
    state["schema"] = 2
    state["media"] = {
        "id": marker,
        "name": f"{marker}.mp4",
        "original_rel": f"original/{marker}.mp4",
        "metadata": {"duration": 10.0, "video": {"codec": "h264"}, "audio": None},
    }
    state["segments"] = [{"id": "seg1", "start": 0.0, "end": 10.0}]
    state["selected_segment"] = "seg1"
    if updated_at is not None:
        state["updated_at"] = updated_at
    return state


def main() -> None:
    py_compile.compile(str(CANDIDATE), doraise=True)
    module = load_candidate()

    with tempfile.TemporaryDirectory(prefix="zerocut-run102-") as td:
        td = Path(td)
        project = td / "project"
        backup = project / "backup"
        recovery = backup / "recovery"
        project.mkdir(parents=True)
        backup.mkdir(parents=True)

        module.PROJECT = project
        module.STATE_FILE = project / "project.json"
        module.STATE_TMP_FILE = project / "project.json.tmp"
        module.STATE_BACKUP_FILE = backup / "project.last-good.json"
        module.STATE_RECOVERY_DIR = recovery

        # 1) Normal save is atomic and produces a valid recovery copy.
        state = sample_state(module, "alpha")
        module.save_state(state)
        assert module.STATE_FILE.exists()
        assert module.STATE_BACKUP_FILE.exists()
        loaded = module.load_state()
        assert loaded["media"]["id"] == "alpha"
        assert loaded["segments"][0]["end"] == 10.0

        # 2) Corrupt primary must recover last-known-good instead of returning an empty project.
        module.STATE_FILE.write_text("{broken-json", encoding="utf-8")
        recovered = module.load_state()
        assert recovered["media"]["id"] == "alpha"
        assert module.STATE_FILE.exists()
        assert json.loads(module.STATE_FILE.read_text(encoding="utf-8"))["media"]["id"] == "alpha"
        quarantined = list(recovery.glob("project.json.*.corrupt"))
        assert quarantined, "corrupt primary was not quarantined"

        # 3) A fully written newer temp simulates crash between fsync and os.replace.
        old = module.load_state()
        newer = sample_state(module, "beta", updated_at=float(old["updated_at"]) + 100.0)
        module._atomic_write_project_state(module.STATE_TMP_FILE, module._validate_project_state(newer))
        interrupted = module.load_state()
        assert interrupted["media"]["id"] == "beta"
        assert not module.STATE_TMP_FILE.exists()
        assert json.loads(module.STATE_FILE.read_text(encoding="utf-8"))["media"]["id"] == "beta"

        # 4) Stale temp must not roll a valid primary backwards.
        stale = sample_state(module, "stale", updated_at=max(0.0, float(interrupted["updated_at"]) - 50.0))
        module._atomic_write_project_state(module.STATE_TMP_FILE, module._validate_project_state(stale))
        still_beta = module.load_state()
        assert still_beta["media"]["id"] == "beta"
        assert not module.STATE_TMP_FILE.exists()

        # 5) Invalid semantic state must be rejected before replacing a good project.
        before = module.STATE_FILE.read_bytes()
        bad = sample_state(module, "bad")
        bad["segments"] = [{"id": "bad", "start": 9.0, "end": 1.0}]
        try:
            module.save_state(bad)
        except ValueError as exc:
            assert "PROJECT_SEGMENT_RANGE_INVALID" in str(exc)
        else:
            raise AssertionError("invalid state unexpectedly saved")
        assert module.STATE_FILE.read_bytes() == before
        assert module.load_state()["media"]["id"] == "beta"

        # 6) Missing primary must restore from backup rather than reset.
        module.STATE_FILE.unlink()
        restored = module.load_state()
        assert restored["media"]["id"] == "beta"
        assert module.STATE_FILE.exists()

        # 7) Corrupt primary + corrupt temp + valid backup still recovers backup.
        module.STATE_FILE.write_text("not-json", encoding="utf-8")
        module.STATE_TMP_FILE.write_text("also-not-json", encoding="utf-8")
        restored_again = module.load_state()
        assert restored_again["media"]["id"] == "beta"
        assert module.STATE_FILE.exists()

    print("ZEROCUT_RUN102_PROJECT_RECOVERY=PASS")


if __name__ == "__main__":
    main()
