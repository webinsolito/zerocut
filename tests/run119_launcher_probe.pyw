from pathlib import Path
import os

probe = os.environ.get("ZEROCUT_PROBE_FILE")
if not probe:
    raise SystemExit(21)
Path(probe).write_text("ZEROCUT_RUN119_PROCESS_HANDOFF=PASS\n", encoding="utf-8")
