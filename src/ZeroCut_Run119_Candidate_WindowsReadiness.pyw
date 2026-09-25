#!/usr/bin/env python3
from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import os
import sys
import uuid
from pathlib import Path
from urllib.parse import urlparse

BASE_PATH = Path(__file__).with_name("ZeroCut_Run118_Candidate_ExportQC.pyw")
_loader = importlib.machinery.SourceFileLoader("zerocut_run118", str(BASE_PATH))
_spec = importlib.util.spec_from_loader("zerocut_run118", _loader)
if _spec is None:
    raise RuntimeError("RUN118_BASE_NOT_LOADABLE")
qc = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = qc
_loader.exec_module(qc)

base = qc.ui.core.base
RUNTIME_NAME = "Run119_WindowsReadiness"


def _pop_ready_file(argv: list[str]) -> Path | None:
    ready = None
    kept = [argv[0]]
    i = 1
    while i < len(argv):
        arg = argv[i]
        if arg == "--ready-file":
            if i + 1 >= len(argv):
                raise SystemExit("--ready-file requires a path")
            ready = Path(argv[i + 1]).expanduser().resolve()
            i += 2
            continue
        if arg.startswith("--ready-file="):
            ready = Path(arg.split("=", 1)[1]).expanduser().resolve()
            i += 1
            continue
        kept.append(arg)
        i += 1
    argv[:] = kept
    return ready


READY_FILE = _pop_ready_file(sys.argv)


def _write_ready(server) -> None:
    if READY_FILE is None:
        return
    host, port = server.server_address[:2]
    host = str(host or "127.0.0.1")
    if host in {"0.0.0.0", "::"}:
        host = "127.0.0.1"
    payload = {
        "ok": True,
        "service": "ZeroCut Gaming AI",
        "runtime": RUNTIME_NAME,
        "pid": os.getpid(),
        "host": host,
        "port": int(port),
        "url": f"http://{host}:{int(port)}",
        "project": str(base.PROJECT),
    }
    READY_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = READY_FILE.with_name(READY_FILE.name + f".{uuid.uuid4().hex[:8]}.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, READY_FILE)


class Handler(qc.Handler):
    def do_GET(self):
        if urlparse(self.path).path == "/api/health":
            base.json_response(self, {
                "ok": True,
                "service": "ZeroCut Gaming AI",
                "runtime": RUNTIME_NAME,
                "pid": os.getpid(),
                "ffmpeg": base._active_media_tool("ffmpeg"),
                "ffprobe": base._active_media_tool("ffprobe"),
            }, 200)
            return
        return super().do_GET()


def main():
    qc.ui.core.Handler = Handler
    original_server = base.ThreadingHTTPServer

    class ReadyServer(original_server):
        def __init__(self, address, handler):
            super().__init__(address, handler)
            _write_ready(self)

        def server_close(self):
            try:
                super().server_close()
            finally:
                if READY_FILE is not None:
                    try:
                        READY_FILE.unlink(missing_ok=True)
                    except OSError:
                        pass

    base.ThreadingHTTPServer = ReadyServer
    try:
        qc.ui.core.main()
    finally:
        base.ThreadingHTTPServer = original_server


if __name__ == "__main__":
    main()
