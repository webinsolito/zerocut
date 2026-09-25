from __future__ import annotations

import runpy
import sys
from pathlib import Path

ACTIVE_RUNTIME = "ZeroCut_Run121_Candidate_GameplayDirector.pyw"

def bundle_root() -> Path:
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        return Path(frozen_root).resolve()
    return Path(__file__).resolve().parents[2]

def main() -> None:
    root = bundle_root()
    target = root / "src" / ACTIVE_RUNTIME
    if not target.is_file():
        raise SystemExit(f"ZEROCUT_PACKAGED_RUNTIME_MISSING:{target}")
    src_dir = str(target.parent)
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)
    sys.argv[0] = str(target)
    runpy.run_path(str(target), run_name="__main__")

if __name__ == "__main__":
    main()
