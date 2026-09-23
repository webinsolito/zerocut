from __future__ import annotations

import hashlib
import importlib.machinery
import importlib.util
import json
import py_compile
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN100 = ROOT / "src" / "ZeroCut_Run100_Candidate_StudioWorkspace.pyw"
RUN99 = ROOT / "rollback" / "Run99_FocusWorkspaceUX.pyw"
REPORT = ROOT / "reports" / "Run100_StudioWorkspace_TEST_REPORT.json"

EXPECTED_RUN100 = "66e756d74b1eaa66eea9446c09db5062bdcc8a55c893ee2d33c51105c9520d30"
EXPECTED_RUN99 = "05772979e0619290680a108197cc7fa0a1d6d499c9d6ae835311bbcfeca4d263"

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def main() -> None:
    assert sha256(RUN100) == EXPECTED_RUN100
    assert sha256(RUN99) == EXPECTED_RUN99

    report = json.loads(REPORT.read_text(encoding="utf-8"))
    assert report["candidate_sha256"] == EXPECTED_RUN100
    assert report["baseline_sha256"] == EXPECTED_RUN99
    assert report["rollback_sha256"] == EXPECTED_RUN99

    py_compile.compile(str(RUN100), doraise=True)

    name = "zerocut_run100_source_truth"
    loader = importlib.machinery.SourceFileLoader(name, str(RUN100))
    spec = importlib.util.spec_from_loader(name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    loader.exec_module(module)
    assert callable(getattr(module, "main", None))

    print("ZEROCUT_SOURCE_TRUTH_SMOKE=PASS")

if __name__ == "__main__":
    main()
