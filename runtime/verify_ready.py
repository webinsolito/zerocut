from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


def fetch(url: str, timeout: float = 2.5) -> tuple[int, bytes]:
    req = urllib.request.Request(url, headers={"User-Agent": "ZeroCut-Launcher/Run119"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return int(response.status), response.read()


def main() -> int:
    if len(sys.argv) < 2:
        print("ZEROCUT_READY_CHECK=FAIL reason=missing_ready_file", file=sys.stderr)
        return 8
    ready_file = Path(sys.argv[1]).expanduser().resolve()
    timeout = float(sys.argv[2]) if len(sys.argv) > 2 else 45.0
    deadline = time.monotonic() + max(3.0, timeout)
    last_error = "not_started"

    while time.monotonic() < deadline:
        try:
            payload = json.loads(ready_file.read_text(encoding="utf-8"))
            url = str(payload.get("url") or "").rstrip("/")
            pid = int(payload.get("pid") or 0)
            if not payload.get("ok") or not url or pid <= 0:
                raise RuntimeError("invalid_ready_payload")
            status, health_raw = fetch(url + "/api/health")
            health = json.loads(health_raw.decode("utf-8"))
            if status != 200 or not health.get("ok") or health.get("runtime") != "Run119_WindowsReadiness":
                raise RuntimeError("health_invalid")
            ui_status, ui_raw = fetch(url + "/")
            if ui_status != 200 or b"ZeroCut" not in ui_raw:
                raise RuntimeError("ui_invalid")
            print(f"ZEROCUT_READY_CHECK=PASS url={url} pid={pid}")
            return 0
        except (OSError, ValueError, TypeError, json.JSONDecodeError, urllib.error.URLError, RuntimeError) as exc:
            last_error = f"{type(exc).__name__}:{exc}"
            time.sleep(0.4)

    print(f"ZEROCUT_READY_CHECK=FAIL reason={last_error}", file=sys.stderr)
    return 8


if __name__ == "__main__":
    raise SystemExit(main())
