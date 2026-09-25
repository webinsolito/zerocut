#!/usr/bin/env python3
from __future__ import annotations

# ZeroCut Gaming AI Run 110 - OCR Certification candidate.
# P1 scope: real RapidOCR inference certification plus R6 semantic text self-test.
# Generated from the validated Run 67 sources; web UI and local AI runtime manager are embedded.

import base64
import ctypes
import webbrowser
import zlib
import hashlib
import importlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
import uuid
import zipfile
from pathlib import Path
from typing import Iterable

WHISPER_RELEASE_TAG = "b5130"  # nightly referenced by stable whisper.cpp v1.9.4
WHISPER_RELEASE_API = f"https://api.github.com/repos/ggml-org/whisper.cpp/releases/tags/{WHISPER_RELEASE_TAG}"
WHISPER_MODEL_NAME = "ggml-tiny.en.bin"
WHISPER_MODEL_URL = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-tiny.en.bin"
# Current upstream Xet object after the Dec 2025 tiny.en refresh. Fail closed if upstream changes.
WHISPER_MODEL_SHA256 = "8729634ed8e45db72893c34a6c671a2eef06f551eaf1056b8fa92ab45008b425"
WHISPER_MODEL_BYTES = 77_704_698
RAPIDOCR_VERSION = "3.9.2"
ONNXRUNTIME_VERSION = "1.30.0"
ONNXRUNTIME_DML_VERSION = "1.24.4"
USER_AGENT = "ZeroCut-Gaming-AI/0.21 (+local-runtime-bootstrap)"

WHISPER_ASSET_PINS = {
    ("windows", "x86_64"): {
        "name": "whisper-bin-x64.zip",
        "size": 8_573_270,
        "digest": "sha256:f9ec6c52a2e949b62ab51fa21d0d497958f9e41c3010c157c4e42932d5316f3c",
        "browser_download_url": "https://github.com/ggml-org/whisper.cpp/releases/download/b5130/whisper-bin-x64.zip",
    },
    ("windows", "arm64"): {
        "name": "whisper-bin-win-cpu-arm64.zip",
        "size": 4_361_895,
        "digest": "sha256:799543b926ab5b6c2d60cab269a2092e0ae8d27820e9e15429e59de3699546fc",
        "browser_download_url": "https://github.com/ggml-org/whisper.cpp/releases/download/b5130/whisper-bin-win-cpu-arm64.zip",
    },
    ("linux", "x86_64"): {
        "name": "whisper-bin-ubuntu-x64.tar.gz",
        "size": 9_793_438,
        "digest": "sha256:53e7fd8b5764edad916b8848dd0af6abb1ff1d3b86c899e79c78652412536c32",
        "browser_download_url": "https://github.com/ggml-org/whisper.cpp/releases/download/b5130/whisper-bin-ubuntu-x64.tar.gz",
    },
    ("linux", "arm64"): {
        "name": "whisper-bin-ubuntu-arm64.tar.gz",
        "size": 4_605_905,
        "digest": "sha256:93532a0e3777f26f041ffa358ee77dd88b1a33a86847c1990745327ff335a5d6",
        "browser_download_url": "https://github.com/ggml-org/whisper.cpp/releases/download/b5130/whisper-bin-ubuntu-arm64.tar.gz",
    },
}


class RuntimeBootstrapError(RuntimeError):
    pass


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as fh:
        while True:
            chunk = fh.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _normalize_machine(machine: str | None = None) -> str:
    value = (machine or platform.machine() or "").lower().replace("amd64", "x86_64")
    if value in {"x64", "x86-64"}:
        return "x86_64"
    if value in {"aarch64", "arm64"}:
        return "arm64"
    return value


def pinned_whisper_asset(system: str | None = None, machine: str | None = None) -> dict:
    """Return ZeroCut's release-pinned CPU asset without requiring GitHub API access.

    The tuple is intentionally fail-closed: name, size, digest and URL all belong
    to the audited b5130 release. This avoids a runtime dependency on the GitHub
    release API and its rate limits while preserving supply-chain verification.
    """
    system_name = (system or platform.system()).lower()
    arch = _normalize_machine(machine)
    asset = WHISPER_ASSET_PINS.get((system_name, arch))
    if asset is None:
        raise RuntimeBootstrapError(f"WHISPER_PLATFORM_UNSUPPORTED:{system_name}:{arch}")
    return dict(asset)


def select_whisper_asset(assets: Iterable[dict], system: str | None = None, machine: str | None = None) -> dict:
    """Select a conservative CPU prebuilt for the current platform.

    CUDA/OpenCL builds are intentionally not auto-selected. GPU enablement belongs
    behind ZeroCut's existing real hardware smoke tests.
    """
    system_name = (system or platform.system()).lower()
    arch = _normalize_machine(machine)
    wanted: list[str]
    if system_name == "windows" and arch == "x86_64":
        wanted = ["whisper-bin-x64.zip"]
    elif system_name == "windows" and arch == "arm64":
        wanted = ["whisper-bin-win-cpu-arm64.zip"]
    elif system_name == "linux" and arch == "x86_64":
        wanted = ["whisper-bin-ubuntu-x64.tar.gz"]
    elif system_name == "linux" and arch == "arm64":
        wanted = ["whisper-bin-ubuntu-arm64.tar.gz"]
    else:
        raise RuntimeBootstrapError(f"WHISPER_PLATFORM_UNSUPPORTED:{system_name}:{arch}")
    by_name = {str(a.get("name") or ""): a for a in assets if isinstance(a, dict)}
    for name in wanted:
        asset = by_name.get(name)
        if asset:
            digest = str(asset.get("digest") or "")
            if not digest.startswith("sha256:") or len(digest.split(":", 1)[1]) != 64:
                raise RuntimeBootstrapError("WHISPER_ASSET_DIGEST_MISSING")
            if not str(asset.get("browser_download_url") or "").startswith("https://github.com/ggml-org/whisper.cpp/releases/"):
                raise RuntimeBootstrapError("WHISPER_ASSET_URL_UNTRUSTED")
            return asset
    raise RuntimeBootstrapError("WHISPER_ASSET_NOT_FOUND")


def fetch_json(url: str, timeout: float = 20.0) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeBootstrapError(f"NETWORK_ERROR:{type(exc).__name__}:{exc}") from exc
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeBootstrapError("INVALID_JSON_RESPONSE") from exc
    if not isinstance(data, dict):
        raise RuntimeBootstrapError("INVALID_JSON_RESPONSE")
    return data


def download_file(url: str, destination: Path, *, expected_sha256: str | None = None,
                  expected_bytes: int | None = None, timeout: float = 120.0) -> dict:
    """Download to a temporary sibling and promote only after integrity checks."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    tmp = destination.with_name(destination.name + f".part-{uuid.uuid4().hex[:8]}")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    digest = hashlib.sha256()
    total = 0
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response, tmp.open("wb") as out:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)
                digest.update(chunk)
                total += len(chunk)
        actual = digest.hexdigest()
        if expected_bytes is not None and total != int(expected_bytes):
            raise RuntimeBootstrapError(f"SIZE_MISMATCH:{total}:{expected_bytes}")
        if expected_sha256 and actual.lower() != expected_sha256.lower():
            raise RuntimeBootstrapError(f"SHA256_MISMATCH:{actual}")
        os.replace(tmp, destination)
        return {"path": str(destination), "bytes": total, "sha256": actual}
    except RuntimeBootstrapError:
        tmp.unlink(missing_ok=True)
        raise
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        tmp.unlink(missing_ok=True)
        raise RuntimeBootstrapError(f"NETWORK_ERROR:{type(exc).__name__}:{exc}") from exc


def _validated_members(names: Iterable[str], destination: Path) -> None:
    base = destination.resolve()
    for name in names:
        target = (destination / name).resolve()
        try:
            target.relative_to(base)
        except ValueError as exc:
            raise RuntimeBootstrapError("ARCHIVE_PATH_TRAVERSAL") from exc


def extract_archive_safely(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as zf:
            _validated_members(zf.namelist(), destination)
            zf.extractall(destination)
        return
    if tarfile.is_tarfile(archive):
        with tarfile.open(archive) as tf:
            names = [m.name for m in tf.getmembers()]
            _validated_members(names, destination)
            # Python 3.12+ filter blocks special-file/path traversal classes too.
            try:
                tf.extractall(destination, filter="data")
            except TypeError:  # Python 3.11 compatibility
                tf.extractall(destination)
        return
    raise RuntimeBootstrapError("ARCHIVE_FORMAT_UNSUPPORTED")


def _replace_dir_atomic(staged: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    backup = target.with_name(target.name + ".rollback")
    if backup.exists():
        shutil.rmtree(backup, ignore_errors=True)
    had_old = target.exists()
    try:
        if had_old:
            os.replace(target, backup)
        os.replace(staged, target)
        if backup.exists():
            shutil.rmtree(backup, ignore_errors=True)
    except Exception:
        if target.exists() and not had_old:
            shutil.rmtree(target, ignore_errors=True)
        if backup.exists():
            if target.exists():
                shutil.rmtree(target, ignore_errors=True)
            os.replace(backup, target)
        raise


def _find_whisper_cli(root: Path, system: str | None = None) -> Path | None:
    names = ["whisper-cli.exe"] if (system or platform.system()).lower() == "windows" else ["whisper-cli"]
    for name in names:
        hits = sorted(root.rglob(name))
        if hits:
            return hits[0]
    return None


def install_whisper_runtime(project_root: Path, *, timeout: float = 120.0) -> dict:
    project_root = Path(project_root)
    tools = project_root / "tools"
    target = tools / "whisper"
    model_target = project_root / "project" / "models" / WHISPER_MODEL_NAME
    try:
        asset = pinned_whisper_asset()
        expected_asset_hash = str(asset["digest"]).split(":", 1)[1]
        with tempfile.TemporaryDirectory(prefix="zerocut-whisper-bootstrap-") as td:
            td_path = Path(td)
            archive = td_path / str(asset["name"])
            download_file(str(asset["browser_download_url"]), archive,
                          expected_sha256=expected_asset_hash,
                          expected_bytes=int(asset.get("size") or 0) or None,
                          timeout=timeout)
            extracted = td_path / "extract"
            extract_archive_safely(archive, extracted)
            cli = _find_whisper_cli(extracted)
            if cli is None:
                raise RuntimeBootstrapError("WHISPER_CLI_NOT_IN_ARCHIVE")
            staged_runtime = tools / (".whisper-stage-" + uuid.uuid4().hex[:8])
            if staged_runtime.exists():
                shutil.rmtree(staged_runtime)
            shutil.copytree(cli.parent, staged_runtime)
            staged_cli = _find_whisper_cli(staged_runtime)
            if staged_cli is None:
                raise RuntimeBootstrapError("WHISPER_CLI_STAGE_FAILED")
            if os.name != "nt":
                staged_cli.chmod(staged_cli.stat().st_mode | 0o111)

            model_stage = td_path / WHISPER_MODEL_NAME
            if model_target.exists() and model_target.stat().st_size == WHISPER_MODEL_BYTES and sha256_file(model_target) == WHISPER_MODEL_SHA256:
                model_downloaded = False
            else:
                download_file(WHISPER_MODEL_URL, model_stage,
                              expected_sha256=WHISPER_MODEL_SHA256,
                              expected_bytes=WHISPER_MODEL_BYTES,
                              timeout=max(timeout, 180.0))
                model_downloaded = True

            _replace_dir_atomic(staged_runtime, target)
            if model_downloaded:
                model_target.parent.mkdir(parents=True, exist_ok=True)
                os.replace(model_stage, model_target)

        return {
            "ok": True,
            "component": "whisper",
            "release": WHISPER_RELEASE_TAG,
            "asset": asset["name"],
            "asset_sha256": expected_asset_hash,
            "model": WHISPER_MODEL_NAME,
            "model_sha256": WHISPER_MODEL_SHA256,
            "model_bytes": WHISPER_MODEL_BYTES,
            "path": str(target),
        }
    except RuntimeBootstrapError as exc:
        return {"ok": False, "component": "whisper", "reason": str(exc)}
    except Exception as exc:
        return {"ok": False, "component": "whisper", "reason": f"UNEXPECTED:{type(exc).__name__}:{exc}"}


def rapidocr_packages(system: str | None = None) -> list[str]:
    system_name = (system or platform.system()).lower()
    engine = f"onnxruntime-directml=={ONNXRUNTIME_DML_VERSION}" if system_name == "windows" else f"onnxruntime=={ONNXRUNTIME_VERSION}"
    return [f"rapidocr=={RAPIDOCR_VERSION}", engine]


def rapidocr_pip_command(target: Path, system: str | None = None) -> list[str]:
    return [
        sys.executable, "-m", "pip", "install",
        "--disable-pip-version-check", "--no-input", "--upgrade", "--prefer-binary",
        "--target", str(target),
        *rapidocr_packages(system),
    ]


def _probe_python_vendor(target: Path, timeout: float = 45.0) -> dict:
    code = (
        "import json, rapidocr, onnxruntime as ort; "
        "from rapidocr import RapidOCR; "
        "assert callable(RapidOCR); "
        "print(json.dumps({'rapidocr':getattr(rapidocr,'__version__',None),"
        "'onnxruntime':getattr(ort,'__version__',None),'providers':ort.get_available_providers(),"
        "'rapidocr_file':getattr(rapidocr,'__file__',None),'onnxruntime_file':getattr(ort,'__file__',None)}))"
    )
    env = os.environ.copy()
    old = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(target) + (os.pathsep + old if old else "")
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=timeout, env=env)
    if proc.returncode != 0:
        raise RuntimeBootstrapError("RAPIDOCR_IMPORT_PROBE_FAILED:" + proc.stderr.strip()[-300:])
    lines = [x.strip() for x in proc.stdout.splitlines() if x.strip()]
    try:
        data = json.loads(lines[-1])
    except (IndexError, json.JSONDecodeError) as exc:
        raise RuntimeBootstrapError("RAPIDOCR_IMPORT_PROBE_INVALID") from exc
    root = target.resolve()
    for key in ("rapidocr_file", "onnxruntime_file"):
        raw = data.get(key)
        if not raw:
            raise RuntimeBootstrapError("RAPIDOCR_IMPORT_PROBE_PATH_MISSING:" + key)
        try:
            Path(raw).resolve().relative_to(root)
        except ValueError as exc:
            raise RuntimeBootstrapError("RAPIDOCR_IMPORT_PROBE_NOT_LOCAL:" + key) from exc
    return data


def classify_pip_failure(output: str) -> str:
    text = str(output or "")
    low = text.lower()
    network_markers = (
        "temporary failure in name resolution", "failed to establish a new connection",
        "name or service not known", "connection timed out", "connection refused",
        "could not fetch url", "network is unreachable",
    )
    if any(marker in low for marker in network_markers):
        return "NETWORK_ERROR:PIP"
    if "no module named pip" in low:
        return "PIP_NOT_AVAILABLE"
    if "requires-python" in low or "requires a different python" in low:
        return "PYTHON_VERSION_INCOMPATIBLE"
    if "no matching distribution found" in low or "could not find a version that satisfies the requirement" in low:
        return "PACKAGE_VERSION_UNAVAILABLE"
    return "PIP_INSTALL_FAILED"


def install_rapidocr_runtime(project_root: Path, *, timeout: float = 300.0) -> dict:
    project_root = Path(project_root)
    tools = project_root / "tools"
    target = tools / "python"
    staged = tools / (".python-stage-" + uuid.uuid4().hex[:8])
    staged.mkdir(parents=True, exist_ok=False)
    cmd = rapidocr_pip_command(staged)
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout)[-500:].replace("\n", " ")
            raise RuntimeBootstrapError(classify_pip_failure(proc.stderr or proc.stdout) + ":" + detail)
        probe = _probe_python_vendor(staged)
        _replace_dir_atomic(staged, target)
        importlib.invalidate_caches()
        return {
            "ok": True,
            "component": "rapidocr",
            "packages": rapidocr_packages(),
            "probe": probe,
            "path": str(target),
        }
    except RuntimeBootstrapError as exc:
        shutil.rmtree(staged, ignore_errors=True)
        return {"ok": False, "component": "rapidocr", "reason": str(exc), "command": cmd}
    except (OSError, subprocess.TimeoutExpired) as exc:
        shutil.rmtree(staged, ignore_errors=True)
        return {"ok": False, "component": "rapidocr", "reason": f"{type(exc).__name__}:{exc}", "command": cmd}
    except Exception as exc:
        shutil.rmtree(staged, ignore_errors=True)
        return {"ok": False, "component": "rapidocr", "reason": f"UNEXPECTED:{type(exc).__name__}:{exc}", "command": cmd}


def bootstrap_ai_runtime(project_root: Path, components: Iterable[str] = ("whisper", "rapidocr")) -> dict:
    requested = []
    for c in components:
        token = str(c).strip().lower()
        if token in {"whisper", "rapidocr"} and token not in requested:
            requested.append(token)
    if not requested:
        raise RuntimeBootstrapError("NO_VALID_COMPONENTS")
    results = []
    for component in requested:
        if component == "whisper":
            results.append(install_whisper_runtime(project_root))
        elif component == "rapidocr":
            results.append(install_rapidocr_runtime(project_root))
    return {"ok": all(r.get("ok") for r in results), "results": results}


def runtime_manifest() -> dict:
    return {
        "whisper": {
            "release": WHISPER_RELEASE_TAG,
            "release_api": WHISPER_RELEASE_API,
            "release_api_required_for_bootstrap": False,
            "model": WHISPER_MODEL_NAME,
            "model_url": WHISPER_MODEL_URL,
            "model_sha256": WHISPER_MODEL_SHA256,
            "model_bytes": WHISPER_MODEL_BYTES,
            "asset_pins": {f"{system}/{arch}": dict(meta) for (system, arch), meta in WHISPER_ASSET_PINS.items()},
        },
        "rapidocr": {
            "version": RAPIDOCR_VERSION,
            "onnxruntime": ONNXRUNTIME_VERSION,
            "onnxruntime_directml": ONNXRUNTIME_DML_VERSION,
            "packages": rapidocr_packages(),
        },
    }


import argparse
import concurrent.futures
import hashlib
import json
import math
import mimetypes
import os
import platform
import re
import shutil
import subprocess
import statistics
import sys
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


_EMBEDDED_WEB = {'index.html': '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', 'app.js': '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', 'styles.css': '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'}


def _portable_root() -> Path:
    explicit = os.environ.get("ZEROCUT_HOME")
    if explicit:
        return Path(explicit).expanduser().resolve()
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home())
        return (base / "ZeroCutGamingAI").resolve()
    return (Path(__file__).resolve().parent / "ZeroCutGamingAI-Data").resolve()


def _ensure_embedded_web_assets() -> None:
    WEB.mkdir(parents=True, exist_ok=True)
    for name, payload in _EMBEDDED_WEB.items():
        target = WEB / name
        data = zlib.decompress(base64.b64decode(payload.encode("ascii")))
        current = None
        try:
            current = target.read_bytes()
        except OSError:
            pass
        if current == data:
            continue
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, target)


def _message_box(title: str, message: str, error: bool = False) -> None:
    if os.name == "nt":
        try:
            flags = 0x10 if error else 0x40
            ctypes.windll.user32.MessageBoxW(0, str(message), str(title), flags)
            return
        except Exception:
            pass
    stream = sys.stderr if error else sys.stdout
    print(f"{title}: {message}", file=stream)


def _candidate_ffmpeg_dirs() -> list[Path]:
    rows: list[Path] = []
    launch_dir = os.environ.get("ZEROCUT_LAUNCH_DIR")
    if launch_dir:
        rows.append(Path(launch_dir))
    rows.extend([
        Path(__file__).resolve().parent,
        ROOT / "tools" / "ffmpeg" / "bin",
        ROOT / "tools" / "ffmpeg",
    ])
    if os.name == "nt":
        rows.extend([
            Path("C:/ffmpeg/bin"),
            Path("C:/Program Files/ffmpeg/bin"),
            Path("C:/Program Files (x86)/ffmpeg/bin"),
        ])
    # Preserve order while removing duplicates.
    out: list[Path] = []
    seen: set[str] = set()
    for p in rows:
        key = str(p).lower() if os.name == "nt" else str(p)
        if key not in seen:
            seen.add(key)
            out.append(p)
    return out


def _prepare_ffmpeg_path() -> tuple[str | None, str | None]:
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if ffmpeg and ffprobe:
        return ffmpeg, ffprobe
    exe = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    probe = "ffprobe.exe" if os.name == "nt" else "ffprobe"
    for folder in _candidate_ffmpeg_dirs():
        try:
            f = folder / exe
            p = folder / probe
            if f.is_file() and p.is_file():
                os.environ["PATH"] = str(folder) + os.pathsep + os.environ.get("PATH", "")
                return str(f), str(p)
        except OSError:
            continue
    return None, None

FFMPEG_RELEASE_API = "https://api.github.com/repos/BtbN/FFmpeg-Builds/releases/latest"
FFMPEG_ASSET_BY_ARCH = {
    "x86_64": "ffmpeg-n9.0-latest-win64-gpl-shared-9.0.zip",
    "arm64": "ffmpeg-n9.0-latest-winarm64-gpl-shared-9.0.zip",
}


def _ffmpeg_tools_smoke(ffmpeg: str, ffprobe: str, *, encode: bool = False) -> tuple[bool, str]:
    """Verify that FFmpeg/FFprobe really start; optionally test H.264 encoding."""
    try:
        a = subprocess.run([ffmpeg, "-hide_banner", "-version"], capture_output=True, text=True, timeout=20)
        b = subprocess.run([ffprobe, "-hide_banner", "-version"], capture_output=True, text=True, timeout=20)
        if a.returncode != 0 or b.returncode != 0:
            return False, f"version_check_failed:{a.returncode}:{b.returncode}"
        if "ffmpeg version" not in (a.stdout or "").lower() or "ffprobe version" not in (b.stdout or "").lower():
            return False, "unexpected_version_output"
        if encode:
            with tempfile.TemporaryDirectory(prefix="zerocut-ffmpeg-smoke-") as td:
                out = Path(td) / "smoke.mp4"
                cmd = [
                    ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", "color=c=black:s=160x90:r=25:d=0.20",
                    "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(out),
                ]
                enc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                if enc.returncode != 0 or not out.is_file() or out.stat().st_size <= 0:
                    return False, "h264_encode_failed:" + (enc.stderr or "").strip()[-300:]
                probe = subprocess.run(
                    [ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=codec_name", "-of", "default=nw=1:nk=1", str(out)],
                    capture_output=True, text=True, timeout=20,
                )
                if probe.returncode != 0 or "h264" not in (probe.stdout or "").lower():
                    return False, "h264_probe_failed"
        return True, "ok"
    except Exception as exc:
        return False, f"{type(exc).__name__}:{exc}"


def _select_btb_ffmpeg_asset(release: dict, machine: str | None = None) -> dict:
    arch = _normalize_machine(machine or platform.machine())
    wanted = FFMPEG_ASSET_BY_ARCH.get(arch)
    if not wanted:
        raise RuntimeBootstrapError(f"FFMPEG_PLATFORM_UNSUPPORTED:{arch}")
    assets = release.get("assets") if isinstance(release, dict) else None
    if not isinstance(assets, list):
        raise RuntimeBootstrapError("FFMPEG_RELEASE_ASSETS_MISSING")
    for asset in assets:
        if not isinstance(asset, dict) or str(asset.get("name") or "") != wanted:
            continue
        digest = str(asset.get("digest") or "")
        url = str(asset.get("browser_download_url") or "")
        size = int(asset.get("size") or 0)
        if not digest.startswith("sha256:") or len(digest.split(":", 1)[1]) != 64:
            raise RuntimeBootstrapError("FFMPEG_ASSET_DIGEST_MISSING")
        if not url.startswith("https://github.com/BtbN/FFmpeg-Builds/releases/download/"):
            raise RuntimeBootstrapError("FFMPEG_ASSET_URL_UNTRUSTED")
        if size < 10_000_000 or size > 400_000_000:
            raise RuntimeBootstrapError(f"FFMPEG_ASSET_SIZE_INVALID:{size}")
        return dict(asset)
    raise RuntimeBootstrapError(f"FFMPEG_ASSET_NOT_FOUND:{wanted}")


def _install_ffmpeg_archive(archive: Path, target_root: Path) -> tuple[Path, Path]:
    """Install an already verified FFmpeg zip atomically, preserving required DLLs."""
    target_root = Path(target_root)
    with tempfile.TemporaryDirectory(prefix="zerocut-ffmpeg-extract-") as td:
        extracted = Path(td) / "extract"
        extract_archive_safely(Path(archive), extracted)
        ffmpegs = sorted(extracted.rglob("ffmpeg.exe"))
        pair = None
        for f in ffmpegs:
            q = f.parent / "ffprobe.exe"
            if q.is_file():
                pair = (f, q)
                break
        if pair is None:
            raise RuntimeBootstrapError("FFMPEG_EXECUTABLES_NOT_FOUND")
        src_bin = pair[0].parent
        staged = target_root.with_name(target_root.name + f".install-{uuid.uuid4().hex[:8]}")
        if staged.exists():
            shutil.rmtree(staged, ignore_errors=True)
        (staged / "bin").parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src_bin, staged / "bin")
        (staged / "SOURCE.txt").write_text(
            "FFmpeg external runtime downloaded by ZeroCut from BtbN/FFmpeg-Builds on GitHub.\n"
            "Build family: FFmpeg 9.0 GPL shared. ZeroCut invokes it as a separate executable.\n"
            "Source: https://github.com/BtbN/FFmpeg-Builds\n",
            encoding="utf-8",
        )
        _replace_dir_atomic(staged, target_root)
    ffmpeg = target_root / "bin" / "ffmpeg.exe"
    ffprobe = target_root / "bin" / "ffprobe.exe"
    if not ffmpeg.is_file() or not ffprobe.is_file():
        raise RuntimeBootstrapError("FFMPEG_INSTALL_INCOMPLETE")
    return ffmpeg, ffprobe


def _bootstrap_ffmpeg_windows(root: Path = None) -> tuple[str, str]:
    """Download, SHA-256 verify, install and smoke-test a private FFmpeg runtime."""
    if os.name != "nt":
        raise RuntimeBootstrapError("FFMPEG_BOOTSTRAP_WINDOWS_ONLY")
    root = Path(root or ROOT)
    release = fetch_json(FFMPEG_RELEASE_API, timeout=30.0)
    asset = _select_btb_ffmpeg_asset(release)
    digest = str(asset["digest"]).split(":", 1)[1]
    size = int(asset["size"])
    url = str(asset["browser_download_url"])
    runtime = root / "runtime" / "downloads"
    runtime.mkdir(parents=True, exist_ok=True)
    archive = runtime / str(asset["name"])
    if archive.is_file():
        good = archive.stat().st_size == size and sha256_file(archive).lower() == digest.lower()
        if not good:
            archive.unlink(missing_ok=True)
    if not archive.is_file():
        download_file(url, archive, expected_sha256=digest, expected_bytes=size, timeout=300.0)
    target = root / "tools" / "ffmpeg"
    ffmpeg, ffprobe = _install_ffmpeg_archive(archive, target)
    os.environ["PATH"] = str(ffmpeg.parent) + os.pathsep + os.environ.get("PATH", "")
    ok, reason = _ffmpeg_tools_smoke(str(ffmpeg), str(ffprobe), encode=True)
    if not ok:
        shutil.rmtree(target, ignore_errors=True)
        raise RuntimeBootstrapError("FFMPEG_SMOKE_FAILED:" + reason)
    try:
        (target / "verified.json").write_text(json.dumps({
            "asset": asset.get("name"), "sha256": digest, "size": size,
            "verified": True, "h264_encode_smoke": True,
            "binary_sha256": {
                "ffmpeg": sha256_file(ffmpeg),
                "ffprobe": sha256_file(ffprobe),
            },
        }, indent=2), encoding="utf-8")
    except OSError:
        pass
    return str(ffmpeg), str(ffprobe)


def _verified_ffmpeg_fast_start(ffmpeg: str, ffprobe: str) -> bool:
    """Trust a previously smoke-tested private runtime only when both binaries still match."""
    try:
        ffmpeg_path = Path(ffmpeg).resolve()
        ffprobe_path = Path(ffprobe).resolve()
        if ffmpeg_path.parent != ffprobe_path.parent:
            return False
        target = ROOT / "tools" / "ffmpeg"
        expected_bin = (target / "bin").resolve()
        if ffmpeg_path.parent != expected_bin:
            return False
        marker = target / "verified.json"
        data = json.loads(marker.read_text(encoding="utf-8"))
        if not data.get("verified") or not data.get("h264_encode_smoke"):
            return False
        hashes = data.get("binary_sha256") or {}
        expected_ffmpeg = str(hashes.get("ffmpeg") or "").lower()
        expected_ffprobe = str(hashes.get("ffprobe") or "").lower()
        if len(expected_ffmpeg) != 64 or len(expected_ffprobe) != 64:
            return False
        return (sha256_file(ffmpeg_path).lower() == expected_ffmpeg and
                sha256_file(ffprobe_path).lower() == expected_ffprobe)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return False


def _ensure_ffmpeg_ready() -> tuple[str | None, str | None]:
    """Use an already verified private runtime fast; smoke-test unknown runtimes; self-repair on Windows."""
    ffmpeg, ffprobe = _prepare_ffmpeg_path()
    if ffmpeg and ffprobe:
        if _verified_ffmpeg_fast_start(ffmpeg, ffprobe):
            return ffmpeg, ffprobe
        ok, _ = _ffmpeg_tools_smoke(ffmpeg, ffprobe, encode=True)
        if ok:
            return ffmpeg, ffprobe
    if os.name != "nt":
        return None, None
    _message_box(
        "ZeroCut - prima configurazione",
        "FFmpeg non è presente o non funziona.\n\n"
        "ZeroCut ora lo scaricherà e configurerà automaticamente (circa 80-90 MB).\n"
        "Non devi installare o spostare nulla. Premi OK e attendi il completamento.",
        error=False,
    )
    return _bootstrap_ffmpeg_windows(ROOT)

ROOT = _portable_root()
WEB = ROOT / "web"
PROJECT = ROOT / "project"
ORIGINAL = PROJECT / "original"
PROXY = PROJECT / "proxy"
RENDER = PROJECT / "render"
TRANSCRIPT = PROJECT / "transcript"
SUBTITLES = PROJECT / "subtitles"
MODELS = PROJECT / "models"
STATE_FILE = PROJECT / "project.json"
STATE_TMP_FILE = PROJECT / "project.json.tmp"
STATE_BACKUP_FILE = PROJECT / "backup" / "project.last-good.json"
STATE_RECOVERY_DIR = PROJECT / "backup" / "recovery"
DIAGNOSTICS = PROJECT / "diagnostics"
_STATE_LOCK = threading.RLock()

def bootstrap_media_tools_path(root: Path = ROOT) -> dict:
    """Prefer a private portable FFmpeg bundle without requiring a system install."""
    candidates = [
        root / "tools" / "ffmpeg" / "bin",
        root / "tools" / "ffmpeg",
        root / "runtime" / "ffmpeg" / "bin",
    ]
    for directory in candidates:
        ffmpeg = directory / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
        ffprobe = directory / ("ffprobe.exe" if os.name == "nt" else "ffprobe")
        if ffmpeg.is_file() and ffprobe.is_file():
            current = os.environ.get("PATH", "")
            parts = current.split(os.pathsep) if current else []
            if str(directory) not in parts:
                os.environ["PATH"] = str(directory) + (os.pathsep + current if current else "")
            return {"source": "bundled", "directory": str(directory), "ffmpeg": str(ffmpeg), "ffprobe": str(ffprobe)}
    return {"source": "system", "directory": None, "ffmpeg": shutil.which("ffmpeg"), "ffprobe": shutil.which("ffprobe")}

MEDIA_TOOLS = bootstrap_media_tools_path()


def _active_media_tool(name: str) -> str:
    """Return the exact executable selected for this process, falling back to PATH only when needed."""
    if name not in {"ffmpeg", "ffprobe"}:
        raise ValueError(f"Unsupported media tool: {name}")
    candidate = (MEDIA_TOOLS or {}).get(name) if isinstance(MEDIA_TOOLS, dict) else None
    if candidate:
        try:
            path = Path(candidate)
            if path.is_file():
                return str(path)
        except (OSError, TypeError, ValueError):
            pass
    found = shutil.which(name)
    if found:
        return found
    return name


def _refresh_media_tools(ffmpeg: str | None = None, ffprobe: str | None = None) -> dict:
    """Pin the binaries that passed the startup gate so every core media operation uses the same tools."""
    global MEDIA_TOOLS
    current = dict(MEDIA_TOOLS or {}) if isinstance(MEDIA_TOOLS, dict) else {}
    if ffmpeg:
        current["ffmpeg"] = str(Path(ffmpeg))
    if ffprobe:
        current["ffprobe"] = str(Path(ffprobe))
    current["source"] = current.get("source") or "verified-runtime"
    MEDIA_TOOLS = current
    return dict(MEDIA_TOOLS)

for p in (WEB, ORIGINAL, PROXY, RENDER, TRANSCRIPT, SUBTITLES, MODELS, DIAGNOSTICS, PROJECT / "cache", PROJECT / "backup"):
    p.mkdir(parents=True, exist_ok=True)

_ensure_embedded_web_assets()

ALLOWED_EXTENSIONS = {".mp4", ".mkv", ".mov", ".webm", ".m4v"}
MEDIA_CACHE_FILE = PROJECT / "cache" / "media_index.json"
THUMB_CACHE = PROJECT / "cache" / "thumbnails"
KEYFRAME_CACHE = PROJECT / "cache" / "keyframes"
THUMB_CACHE.mkdir(parents=True, exist_ok=True)
KEYFRAME_CACHE.mkdir(parents=True, exist_ok=True)
THUMB_CACHE_MAX_FILES = max(8, int(os.environ.get("ZEROCUT_THUMB_CACHE_MAX_FILES", "1200")))
THUMB_CACHE_MAX_BYTES = max(64 * 1024 * 1024, int(os.environ.get("ZEROCUT_THUMB_CACHE_MAX_BYTES", str(512 * 1024 * 1024))))
_THUMB_LOCKS_GUARD = threading.Lock()
_THUMB_LOCKS: dict[str, threading.Lock] = {}

def _thumbnail_lock(key: str) -> threading.Lock:
    """Return a per-thumbnail lock so concurrent HTTP requests share one FFmpeg generation."""
    with _THUMB_LOCKS_GUARD:
        return _THUMB_LOCKS.setdefault(key, threading.Lock())


def _load_media_cache() -> dict:
    try:
        data = json.loads(MEDIA_CACHE_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _save_media_cache(data: dict) -> None:
    tmp = MEDIA_CACHE_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, MEDIA_CACHE_FILE)



def _prune_thumbnail_cache(keep: Path | None = None) -> None:
    """Bound persistent filmstrip storage using oldest-accessed files first."""
    try:
        files = [p for p in THUMB_CACHE.glob("*.jpg") if p.is_file()]
        rows = [(p.stat().st_mtime, p.stat().st_size, p) for p in files]
    except OSError:
        return
    total = sum(size for _, size, _ in rows)
    count = len(rows)
    if count <= THUMB_CACHE_MAX_FILES and total <= THUMB_CACHE_MAX_BYTES:
        return
    for _, size, path in sorted(rows):
        if keep is not None and path == keep:
            continue
        try:
            path.unlink()
            total -= size
            count -= 1
        except OSError:
            continue
        if count <= THUMB_CACHE_MAX_FILES and total <= THUMB_CACHE_MAX_BYTES:
            break


def cached_thumbnail(media: dict, timestamp: float, width: int = 320) -> tuple[Path, bool]:
    """Return a deterministic JPEG timeline thumbnail, generating it atomically once."""
    duration = float((media.get("metadata") or {}).get("duration") or 0.0)
    if duration <= 0:
        raise ValueError("Durata media non valida")
    timestamp = max(0.0, min(float(timestamp), max(0.0, duration - 0.001)))
    width = max(96, min(int(width), 1280))
    content_hash = str(media.get("content_hash") or media.get("id") or "media")
    key = hashlib.sha256(f"{content_hash}:{timestamp:.3f}:{width}:jpeg-v1".encode()).hexdigest()[:24]
    target = THUMB_CACHE / f"{key}.jpg"
    if target.exists() and target.stat().st_size > 0:
        try: os.utime(target, None)
        except OSError: pass
        return target, True
    lock = _thumbnail_lock(key)
    with lock:
        # Another request may have completed while this one waited. Re-check before FFmpeg.
        if target.exists() and target.stat().st_size > 0:
            return target, True
        source_rel = media.get("proxy_rel") or media.get("original_rel")
        source = resolve_project_file(source_rel)
        tmp = THUMB_CACHE / f".{key}.{uuid.uuid4().hex}.tmp.jpg"
        try:
            subprocess.check_output([
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-ss", f"{timestamp:.3f}", "-i", str(source), "-frames:v", "1",
                "-vf", f"scale={width}:-2", "-q:v", "4", str(tmp),
            ], stderr=subprocess.STDOUT)
            if not tmp.exists() or tmp.stat().st_size <= 0:
                raise RuntimeError("Thumbnail FFmpeg vuota")
            os.replace(tmp, target)
            _prune_thumbnail_cache(keep=target)
            return target, False
        finally:
            tmp.unlink(missing_ok=True)


def safe_name(name: str) -> str:
    name = Path(name).name.strip()
    name = re.sub(r"[^A-Za-z0-9._ -]+", "_", name)
    name = re.sub(r"\s+", " ", name).strip(" .")
    return (name or "gameplay.mp4")[:180]


def json_response(handler: BaseHTTPRequestHandler, data, status=200):
    body = json.dumps(data, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(body)


def ffprobe(path: Path, ffprobe_bin: str | None = None, timeout: float = 20.0) -> dict:
    """Probe a local media file with the exact validated FFprobe binary and a bounded timeout."""
    path = Path(path)
    if not path.exists() or not path.is_file():
        raise RuntimeError(f"FFprobe input non trovato: {path}")
    try:
        if path.stat().st_size <= 0:
            raise RuntimeError("FFprobe input vuoto")
    except OSError as exc:
        raise RuntimeError(f"FFprobe input non leggibile: {exc}") from exc
    tool = str(ffprobe_bin or _active_media_tool("ffprobe"))
    timeout = max(1.0, min(float(timeout), 120.0))
    cmd = [tool, "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"FFprobe timeout dopo {timeout:.1f}s") from exc
    except OSError as exc:
        raise RuntimeError(f"FFprobe non avviabile: {exc}") from exc
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()[-700:]
        raise RuntimeError(f"FFprobe errore ({proc.returncode}): {detail or 'nessun dettaglio'}")
    try:
        data = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise RuntimeError("FFprobe ha restituito JSON non valido") from exc
    fmt = data.get("format", {}) if isinstance(data, dict) else {}
    streams = data.get("streams", []) if isinstance(data, dict) else []
    if not isinstance(fmt, dict) or not isinstance(streams, list):
        raise RuntimeError("FFprobe metadata malformati")
    video = next((s for s in streams if isinstance(s, dict) and s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if isinstance(s, dict) and s.get("codec_type") == "audio"), None)

    def fps_value(s):
        if not s:
            return 0.0
        token = s.get("avg_frame_rate") or s.get("r_frame_rate") or "0/1"
        try:
            n, d = token.split("/")
            return round(float(n) / float(d), 4) if float(d) else 0.0
        except Exception:
            return 0.0

    try:
        duration = float(fmt.get("duration") or (video or {}).get("duration") or 0.0)
    except (TypeError, ValueError):
        duration = 0.0
    if duration < 0 or not math.isfinite(duration):
        raise RuntimeError("FFprobe durata non valida")
    try:
        size = int(fmt.get("size") or path.stat().st_size)
    except (TypeError, ValueError, OSError):
        size = path.stat().st_size
    return {
        "duration": round(duration, 4),
        "size": size,
        "format_name": fmt.get("format_name", ""),
        "bit_rate": int(fmt.get("bit_rate") or 0),
        "video": None if not video else {
            "codec": video.get("codec_name", ""),
            "width": int(video.get("width") or 0),
            "height": int(video.get("height") or 0),
            "fps": fps_value(video),
            "pix_fmt": video.get("pix_fmt", ""),
            "color_space": video.get("color_space", ""),
            "profile": video.get("profile", ""),
        },
        "audio": None if not audio else {
            "codec": audio.get("codec_name", ""),
            "sample_rate": int(audio.get("sample_rate") or 0),
            "channels": int(audio.get("channels") or 0),
            "channel_layout": audio.get("channel_layout", ""),
        },
        "stream_count": len(streams),
        "probe_binary": tool,
    }

SUBTITLE_STYLES = {
    "gaming-bold": "FontName=DejaVu Sans,FontSize=24,Bold=1,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=3,Shadow=0,Alignment=2,MarginV=34",
    "minimal": "FontName=DejaVu Sans,FontSize=20,Bold=0,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=1,Shadow=0,Alignment=2,MarginV=28",
    "youtube": "FontName=DejaVu Sans,FontSize=22,Bold=1,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=2,Shadow=1,Alignment=2,MarginV=32",
}


def default_state() -> dict:
    return {
        "schema": 2,
        "media": None,
        "segments": [],
        "selected_segment": None,
        "subtitles": [],
        "subtitle_style": "gaming-bold",
        "auto_edit_proposal": None,
        "last_auto_edit": None,
        "updated_at": time.time(),
    }


class ProjectRevisionConflict(RuntimeError):
    pass


def windows_core_environment_report() -> dict:
    """Return explicit host facts used by the Windows core certification gate."""
    return {
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "os_name": os.name,
        "is_windows": platform.system().lower() == "windows" and os.name == "nt",
        "path_separator": os.sep,
    }


def media_roundtrip_selftest(source: Path, workdir: Path, *, ffmpeg_bin: str | None = None,
                             ffprobe_bin: str | None = None) -> dict:
    """Exercise the same core media primitives used by ZeroCut: probe, preview proxy, export and decode verification."""
    source=Path(source); workdir=Path(workdir); workdir.mkdir(parents=True,exist_ok=True)
    ffmpeg_tool=str(ffmpeg_bin or _active_media_tool("ffmpeg"))
    ffprobe_tool=str(ffprobe_bin or _active_media_tool("ffprobe"))
    meta=ffprobe(source,ffprobe_bin=ffprobe_tool,timeout=30)
    duration=float(meta.get("duration") or 0.0)
    if duration <= 0 or not meta.get("video"):
        raise RuntimeError("MEDIA_ROUNDTRIP_SOURCE_INVALID")
    proxy=workdir/"preview-proxy.mp4"
    proxy_cmd,proxy_total=proxy_command(source,proxy,duration,bool(meta.get("audio")),ffmpeg_bin=ffmpeg_tool)
    pp=subprocess.run(proxy_cmd,capture_output=True,text=True,timeout=120)
    if pp.returncode != 0:
        raise RuntimeError("MEDIA_ROUNDTRIP_PROXY_FAILED:"+(pp.stderr or "")[-500:])
    proxy_check=verify_render_output(proxy,proxy_total,expect_audio=bool(meta.get("audio")),
                                     ffmpeg_bin=ffmpeg_tool,ffprobe_bin=ffprobe_tool)

    end=min(duration,max(0.8,duration-0.20))
    start=min(0.20,max(0.0,end-0.60))
    export=workdir/"roundtrip-export.mp4"
    cmd,total=export_command(source,export,[{"start":start,"end":end}],bool(meta.get("audio")),
                             float((meta.get("video") or {}).get("fps") or 0.0),
                             encoder_capability={"verified":False},ffmpeg_bin=ffmpeg_tool)
    ep=subprocess.run(cmd,capture_output=True,text=True,timeout=120)
    if ep.returncode != 0:
        raise RuntimeError("MEDIA_ROUNDTRIP_EXPORT_FAILED:"+(ep.stderr or "")[-500:])
    export_check=verify_render_output(export,total,expect_audio=bool(meta.get("audio")),
                                      ffmpeg_bin=ffmpeg_tool,ffprobe_bin=ffprobe_tool)
    return {"ok":True,"source":meta,"proxy":proxy_check,"export":export_check,
            "ffmpeg":ffmpeg_tool,"ffprobe":ffprobe_tool}


def project_state_revision(state: dict) -> str:
    """Stable revision of user-visible project state, excluding volatile timestamps."""
    payload = dict(state or {})
    payload.pop("updated_at", None)
    payload.pop("_revision", None)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def normalize_project_timeline(segments: list[dict], duration: float, *, max_segments: int = 500,
                               min_segment_duration: float = 0.04) -> list[dict]:
    """Validate timeline edits without silently coercing NaN/duplicates/out-of-range segments."""
    if not isinstance(segments,list):
        raise ValueError("TIMELINE_NOT_LIST")
    if not segments:
        raise ValueError("TIMELINE_EMPTY")
    if len(segments) > int(max_segments):
        raise ValueError("TIMELINE_TOO_MANY_SEGMENTS")
    try: duration=float(duration)
    except (TypeError,ValueError) as exc: raise ValueError("TIMELINE_DURATION_INVALID") from exc
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("TIMELINE_DURATION_INVALID")
    clean=[]; seen=set()
    for index,seg in enumerate(segments):
        if not isinstance(seg,dict):
            raise ValueError(f"TIMELINE_SEGMENT_INVALID:{index}")
        sid=str(seg.get("id") or uuid.uuid4().hex[:8])
        if sid in seen:
            raise ValueError(f"TIMELINE_DUPLICATE_ID:{sid}")
        seen.add(sid)
        try:
            start=float(seg.get("start"))
            end=float(seg.get("end"))
        except (TypeError,ValueError) as exc:
            raise ValueError(f"TIMELINE_SEGMENT_TIME_INVALID:{index}") from exc
        if not math.isfinite(start) or not math.isfinite(end):
            raise ValueError(f"TIMELINE_SEGMENT_TIME_INVALID:{index}")
        if start < 0 or end > duration + 1e-6 or end <= start:
            raise ValueError(f"TIMELINE_SEGMENT_RANGE_INVALID:{index}")
        if end-start < float(min_segment_duration)-1e-9:
            raise ValueError(f"TIMELINE_SEGMENT_TOO_SHORT:{index}")
        clean.append({"id":sid,"start":round(start,6),"end":round(end,6)})
    return clean


def _validate_project_state(data: dict) -> dict:
    """Validate the persisted project envelope without discarding unknown forward-compatible fields."""
    if not isinstance(data, dict):
        raise ValueError("PROJECT_STATE_NOT_OBJECT")
    out = dict(data)
    try:
        schema = int(out.get("schema", 1))
    except (TypeError, ValueError) as exc:
        raise ValueError("PROJECT_SCHEMA_INVALID") from exc
    if schema < 1:
        raise ValueError("PROJECT_SCHEMA_INVALID")
    out["schema"] = schema

    media = out.get("media")
    if media is not None and not isinstance(media, dict):
        raise ValueError("PROJECT_MEDIA_INVALID")

    segments = out.get("segments", [])
    if not isinstance(segments, list):
        raise ValueError("PROJECT_SEGMENTS_INVALID")
    for index, seg in enumerate(segments):
        if not isinstance(seg, dict):
            raise ValueError(f"PROJECT_SEGMENT_INVALID:{index}")
        try:
            start = float(seg.get("start", 0.0))
            end = float(seg.get("end", start))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"PROJECT_SEGMENT_TIME_INVALID:{index}") from exc
        if not math.isfinite(start) or not math.isfinite(end) or start < 0 or end < start:
            raise ValueError(f"PROJECT_SEGMENT_RANGE_INVALID:{index}")

    subtitles = out.get("subtitles", [])
    if not isinstance(subtitles, list):
        raise ValueError("PROJECT_SUBTITLES_INVALID")

    updated = out.get("updated_at", 0.0)
    try:
        updated = float(updated or 0.0)
    except (TypeError, ValueError):
        updated = 0.0
    if not math.isfinite(updated) or updated < 0:
        updated = 0.0
    out["updated_at"] = updated

    out.setdefault("media", None)
    out.setdefault("segments", [])
    out.setdefault("selected_segment", None)
    out.setdefault("subtitles", [])
    out.setdefault("subtitle_style", "gaming-bold")
    out.setdefault("auto_edit_proposal", None)
    out.setdefault("last_auto_edit", None)
    return out


def _read_project_state(path: Path) -> dict:
    raw = Path(path).read_text(encoding="utf-8")
    return _validate_project_state(json.loads(raw))


def _atomic_write_project_state(path: Path, state: dict, *, tmp_path: Path | None = None) -> None:
    """Durably write JSON to a sibling temporary file before atomic replacement."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tmp_path) if tmp_path is not None else path.with_name(path.name + ".tmp")
    payload = json.dumps(state, ensure_ascii=False, indent=2)
    with tmp.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(payload)
        fh.write("\n")
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def _quarantine_project_file(path: Path, reason: str) -> Path | None:
    """Preserve unreadable state instead of deleting it, so manual recovery remains possible."""
    path = Path(path)
    if not path.exists():
        return None
    STATE_RECOVERY_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    safe_reason = re.sub(r"[^A-Za-z0-9_-]+", "-", str(reason)).strip("-")[:48] or "invalid"
    target = STATE_RECOVERY_DIR / f"{path.name}.{stamp}.{uuid.uuid4().hex[:8]}.{safe_reason}.corrupt"
    try:
        os.replace(path, target)
        return target
    except OSError:
        return None


def _state_timestamp(data: dict | None) -> float:
    if not isinstance(data, dict):
        return 0.0
    try:
        value = float(data.get("updated_at") or 0.0)
        return value if math.isfinite(value) and value >= 0 else 0.0
    except (TypeError, ValueError):
        return 0.0


def load_state() -> dict:
    """Load the newest valid project state and recover safely from corruption/interrupted writes."""
    with _STATE_LOCK:
        primary = None
        pending = None
        backup = None
        primary_error = None
        pending_error = None
        backup_error = None

        if STATE_FILE.exists():
            try:
                primary = _read_project_state(STATE_FILE)
            except Exception as exc:
                primary_error = f"{type(exc).__name__}:{exc}"

        if STATE_TMP_FILE.exists():
            try:
                pending = _read_project_state(STATE_TMP_FILE)
            except Exception as exc:
                pending_error = f"{type(exc).__name__}:{exc}"

        if STATE_BACKUP_FILE.exists():
            try:
                backup = _read_project_state(STATE_BACKUP_FILE)
            except Exception as exc:
                backup_error = f"{type(exc).__name__}:{exc}"

        # A fully-written temp with a newer logical timestamp is an interrupted save.
        if pending is not None and (primary is None or _state_timestamp(pending) > _state_timestamp(primary)):
            if primary is not None:
                try:
                    _atomic_write_project_state(STATE_BACKUP_FILE, primary)
                except OSError:
                    pass
            elif primary_error:
                _quarantine_project_file(STATE_FILE, "primary-invalid-before-pending-recovery")
            os.replace(STATE_TMP_FILE, STATE_FILE)
            recovered = _read_project_state(STATE_FILE)
            try:
                _atomic_write_project_state(STATE_BACKUP_FILE, recovered)
            except OSError:
                pass
            return recovered

        # Valid primary wins; stale temp files are not allowed to shadow it.
        if primary is not None:
            if pending_error:
                _quarantine_project_file(STATE_TMP_FILE, "stale-invalid-temp")
            elif pending is not None:
                try:
                    STATE_TMP_FILE.unlink(missing_ok=True)
                except OSError:
                    pass
            return primary

        if primary_error:
            _quarantine_project_file(STATE_FILE, "primary-invalid")

        # If no primary survived, a valid pending file is newer than no state at all.
        if pending is not None:
            os.replace(STATE_TMP_FILE, STATE_FILE)
            recovered = _read_project_state(STATE_FILE)
            try:
                _atomic_write_project_state(STATE_BACKUP_FILE, recovered)
            except OSError:
                pass
            return recovered
        if pending_error:
            _quarantine_project_file(STATE_TMP_FILE, "pending-invalid")

        # Last-known-good backup is restored atomically instead of silently returning an empty project.
        if backup is not None:
            _atomic_write_project_state(STATE_FILE, backup, tmp_path=STATE_TMP_FILE)
            return _read_project_state(STATE_FILE)
        if backup_error:
            _quarantine_project_file(STATE_BACKUP_FILE, "backup-invalid")

        return default_state()


def save_state(state: dict, *, expected_revision: str | None = None):
    """Commit a validated project state atomically; reject stale writers when a revision is supplied."""
    with _STATE_LOCK:
        current_for_revision = None
        if STATE_FILE.exists():
            try:
                current_for_revision = _read_project_state(STATE_FILE)
            except Exception:
                current_for_revision = None
        if expected_revision is not None:
            actual_revision = project_state_revision(current_for_revision or default_state())
            if str(expected_revision) != actual_revision:
                raise ProjectRevisionConflict(f"PROJECT_REVISION_CONFLICT:{actual_revision}")
        candidate = dict(state)
        candidate.pop("_revision", None)
        candidate["updated_at"] = time.time()
        candidate = _validate_project_state(candidate)

        # Never overwrite a good on-disk project with a semantically invalid state.
        current = None
        if STATE_FILE.exists():
            try:
                current = _read_project_state(STATE_FILE)
            except Exception:
                current = None
        if current is not None:
            try:
                _atomic_write_project_state(STATE_BACKUP_FILE, current)
            except OSError:
                pass

        _atomic_write_project_state(STATE_FILE, candidate, tmp_path=STATE_TMP_FILE)

        # Refresh the recovery copy only after the primary commit succeeded.
        try:
            _atomic_write_project_state(STATE_BACKUP_FILE, candidate)
        except OSError:
            pass

        # Preserve existing caller behavior: the in-memory state receives the committed timestamp.
        state["updated_at"] = candidate["updated_at"]


def resolve_project_file(rel: str) -> Path:
    target = (PROJECT / rel).resolve()
    project_resolved = PROJECT.resolve()
    if project_resolved not in target.parents and target != project_resolved:
        raise ValueError("Percorso non valido")
    return target


@dataclass
class Job:
    id: str
    kind: str
    total_duration: float
    command: list[str]
    output_path: str
    status: str = "queued"
    progress: float = 0.0
    out_time: float = 0.0
    error: str = ""
    started_at: float | None = None
    ended_at: float | None = None
    process: subprocess.Popen | None = field(default=None, repr=False)
    on_success: object | None = field(default=None, repr=False)
    cleanup_path: str | None = field(default=None, repr=False)

    def public(self):
        return {
            "id": self.id,
            "kind": self.kind,
            "status": self.status,
            "progress": round(self.progress, 2),
            "out_time": round(self.out_time, 3),
            "total_duration": round(self.total_duration, 3),
            "output_path": self.output_path,
            "error": self.error,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
        }


class JobManager:
    def __init__(self):
        self.jobs: dict[str, Job] = {}
        self.lock = threading.Lock()

    def create(self, kind: str, total_duration: float, command: list[str], output_path: str, on_success=None, cleanup_path=None) -> Job:
        job = Job(uuid.uuid4().hex[:12], kind, total_duration, command, output_path, on_success=on_success, cleanup_path=str(cleanup_path) if cleanup_path else None)
        with self.lock:
            self.jobs[job.id] = job
        threading.Thread(target=self._run, args=(job,), daemon=True).start()
        return job

    def completed(self, kind: str, total_duration: float, output_path: str) -> Job:
        """Register a truthful completed job for reusable cached artifacts."""
        now = time.time()
        job = Job(uuid.uuid4().hex[:12], kind, total_duration, [], output_path,
                  status="done", progress=100.0, out_time=total_duration,
                  started_at=now, ended_at=now)
        with self.lock:
            self.jobs[job.id] = job
        return job

    def get(self, job_id: str) -> Job | None:
        with self.lock:
            return self.jobs.get(job_id)

    def stop(self, job_id: str) -> bool:
        job = self.get(job_id)
        if not job or job.status not in {"queued", "running"}:
            return False
        job.status = "stopping"
        proc = job.process
        if proc and proc.poll() is None:
            try:
                proc.terminate()
            except Exception:
                pass
        return True

    def _run(self, job: Job):
        job.status = "running"
        job.started_at = time.time()
        stderr_lines: list[str] = []
        try:
            proc = subprocess.Popen(
                job.command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
            job.process = proc

            def drain_stderr():
                assert proc.stderr is not None
                for line in proc.stderr:
                    stderr_lines.append(line.rstrip())
                    if len(stderr_lines) > 120:
                        del stderr_lines[:40]

            threading.Thread(target=drain_stderr, daemon=True).start()
            assert proc.stdout is not None
            for line in proc.stdout:
                line = line.strip()
                if not line or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                if key in {"out_time_us", "out_time_ms"}:
                    try:
                        # FFmpeg reports microseconds in out_time_us. Some builds expose out_time_ms with the same scale.
                        job.out_time = max(0.0, float(value) / 1_000_000.0)
                        if job.total_duration > 0:
                            job.progress = min(99.5, job.out_time / job.total_duration * 100.0)
                    except Exception:
                        pass
                elif key == "progress" and value == "end" and job.status != "stopping":
                    job.progress = 100.0
            rc = proc.wait()
            if job.status == "stopping":
                # Remove partial output before publishing the terminal state so callers
                # never observe `cancelled` while a .working artifact still exists.
                if job.cleanup_path:
                    try:
                        Path(job.cleanup_path).unlink(missing_ok=True)
                    except Exception:
                        pass
                if job.total_duration > 0:
                    job.progress = min(99.0, job.out_time / job.total_duration * 100.0)
                job.status = "cancelled"
            elif rc == 0:
                if job.on_success:
                    try:
                        job.on_success()
                    except Exception as exc:
                        job.status = "failed"
                        job.error = f"Post-processing failed: {exc}"
                    else:
                        job.status = "done"
                        job.progress = 100.0
                else:
                    job.status = "done"
                    job.progress = 100.0
            else:
                job.status = "failed"
                job.error = "\n".join(stderr_lines[-15:]) or f"FFmpeg exited with code {rc}"
        except Exception as exc:
            job.status = "failed"
            job.error = str(exc)
        finally:
            if job.status in {"failed", "cancelled"} and job.cleanup_path:
                try:
                    Path(job.cleanup_path).unlink(missing_ok=True)
                except Exception:
                    pass
            job.ended_at = time.time()


JOBS = JobManager()


def media_file(state: dict) -> Path:
    media = state.get("media")
    if not media or not media.get("original_rel"):
        raise ValueError("Nessun gameplay importato")
    path = resolve_project_file(media["original_rel"])
    if not path.exists():
        raise ValueError("File originale non trovato")
    return path


def srt_time_to_seconds(token: str) -> float:
    token = token.strip().replace(".", ",")
    m = re.fullmatch(r"(\d{1,3}):(\d{2}):(\d{2}),(\d{1,3})", token)
    if not m:
        raise ValueError(f"Timestamp SRT non valido: {token}")
    h, minute, sec, ms = [int(x) for x in m.groups()]
    if minute > 59 or sec > 59:
        raise ValueError(f"Timestamp SRT non valido: {token}")
    return h * 3600 + minute * 60 + sec + ms / (10 ** len(m.group(4)))


def seconds_to_srt_time(value: float) -> str:
    value = max(0.0, float(value))
    total_ms = int(round(value * 1000))
    h, rem = divmod(total_ms, 3_600_000)
    minute, rem = divmod(rem, 60_000)
    sec, ms = divmod(rem, 1000)
    return f"{h:02d}:{minute:02d}:{sec:02d},{ms:03d}"


def parse_srt(text: str) -> list[dict]:
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return []
    blocks = re.split(r"\n\s*\n", text)
    items = []
    for block in blocks:
        lines = [line.rstrip() for line in block.split("\n") if line.strip()]
        if not lines:
            continue
        timing_idx = next((i for i, line in enumerate(lines) if "-->" in line), None)
        if timing_idx is None:
            continue
        timing = lines[timing_idx]
        start_token, end_token = [part.strip() for part in timing.split("-->", 1)]
        start = srt_time_to_seconds(start_token.split()[0])
        end = srt_time_to_seconds(end_token.split()[0])
        body = "\n".join(lines[timing_idx + 1:]).strip()
        if body and end > start:
            items.append({
                "id": uuid.uuid4().hex[:10],
                "start": round(start, 3),
                "end": round(end, 3),
                "text": body[:2000],
                "source": "srt",
            })
    return items


def normalize_subtitles(items, duration: float) -> list[dict]:
    if not isinstance(items, list):
        raise ValueError("subtitles deve essere una lista")
    out = []
    for raw in items[:5000]:
        if not isinstance(raw, dict):
            continue
        text = str(raw.get("text") or "").strip()
        if not text:
            continue
        start = max(0.0, min(duration, float(raw.get("start", 0))))
        end = max(start, min(duration, float(raw.get("end", start))))
        if end - start < 0.02:
            continue
        entry = {
            "id": str(raw.get("id") or uuid.uuid4().hex[:10])[:64],
            "start": round(start, 3),
            "end": round(end, 3),
            "text": text[:2000],
            "source": str(raw.get("source") or "manual")[:32],
        }
        if isinstance(raw.get("words"), list):
            words = []
            for word in raw["words"][:1000]:
                if not isinstance(word, dict):
                    continue
                wtext = str(word.get("text") or "").strip()
                if not wtext:
                    continue
                wstart = max(start, min(end, float(word.get("start", start))))
                wend = max(wstart, min(end, float(word.get("end", wstart))))
                words.append({"text": wtext[:120], "start": round(wstart, 3), "end": round(wend, 3)})
            if words:
                entry["words"] = words
        out.append(entry)
    out.sort(key=lambda item: (item["start"], item["end"]))
    return out


def remap_subtitles(items: list[dict], segments: list[dict]) -> list[dict]:
    """Map source-media timestamps onto the edited/concatenated timeline."""
    output = []
    timeline_offset = 0.0
    for seg in segments:
        seg_start = float(seg.get("start", 0))
        seg_end = float(seg.get("end", 0))
        if seg_end <= seg_start:
            continue
        for item in items:
            start = max(seg_start, float(item.get("start", 0)))
            end = min(seg_end, float(item.get("end", 0)))
            if end - start < 0.02:
                continue
            mapped = {
                "id": f"{item.get('id','sub')}-{len(output)}",
                "start": round(timeline_offset + (start - seg_start), 3),
                "end": round(timeline_offset + (end - seg_start), 3),
                "text": str(item.get("text") or ""),
                "source_id": item.get("id"),
            }
            output.append(mapped)
        timeline_offset += seg_end - seg_start
    output.sort(key=lambda item: (item["start"], item["end"]))
    return output


def subtitles_to_srt(items: list[dict]) -> str:
    blocks = []
    for i, item in enumerate(items, start=1):
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        blocks.append(
            f"{i}\n{seconds_to_srt_time(item['start'])} --> {seconds_to_srt_time(item['end'])}\n{text}"
        )
    return "\n\n".join(blocks) + ("\n" if blocks else "")


def _ffmpeg_filter_escape(path: Path) -> str:
    value = str(path.resolve()).replace("\\", "/")
    value = value.replace(":", r"\:").replace("'", r"\'").replace("[", r"\[").replace("]", r"\]")
    return value


def discover_whisper() -> dict:
    candidates = []
    env_bin = os.environ.get("ZEROCUT_WHISPER_BIN")
    if env_bin:
        candidates.append(Path(env_bin))
    candidates.extend([
        ROOT / "tools" / "whisper" / "whisper-cli",
        ROOT / "tools" / "whisper" / "whisper-cli.exe",
    ])
    which = shutil.which("whisper-cli")
    if which:
        candidates.append(Path(which))
    def usable_binary(p: Path) -> bool:
        if not (p.exists() and p.is_file()):
            return False
        # Windows executables do not expose POSIX execute bits reliably.
        if os.name == "nt":
            return p.suffix.lower() == ".exe"
        return os.access(p, os.X_OK)

    binary = next((p for p in candidates if usable_binary(p)), None)

    model_candidates = []
    env_model = os.environ.get("ZEROCUT_WHISPER_MODEL")
    if env_model:
        model_candidates.append(Path(env_model))
    model_candidates.extend(sorted(MODELS.glob("ggml-*.bin")))
    # Real Whisper GGML models are many MB. Reject tiny placeholders/corrupt stubs so
    # the UI never advertises ASR as available merely because a file has the right name.
    model = next((p for p in model_candidates if p.exists() and p.is_file() and p.stat().st_size >= 1_000_000), None)
    available = bool(binary and model)
    if available:
        reason_code = "OK"
        reason = ""
    elif not binary and not model:
        reason_code = "BINARY_AND_MODEL_MISSING"
        reason = "whisper-cli e modello GGML non sono disponibili localmente"
    elif not binary:
        reason_code = "BINARY_MISSING"
        reason = "whisper-cli non è disponibile o non è eseguibile"
    else:
        reason_code = "MODEL_MISSING"
        reason = "nessun modello GGML Whisper valido è disponibile localmente"
    return {
        "available": available,
        "binary": str(binary) if binary else None,
        "model": str(model) if model else None,
        "model_bytes": model.stat().st_size if model else None,
        "reason_code": reason_code,
        "reason": reason,
    }


def whisper_inference_selftest(audio_path: Path | None = None, timeout: float = 90.0) -> dict:
    """Run a *real* whisper.cpp inference when runtime assets are present.

    This never upgrades a capability based on file presence alone. The bundled
    spoken-WAV fixture lets the same self-test run on Windows without requiring
    a system TTS engine.
    """
    cap = discover_whisper()
    if not cap["available"]:
        return {"executed": False, "passed": False, "reason": cap.get("reason_code", "NOT_AVAILABLE")}
    fixture = Path(audio_path) if audio_path else ROOT / "tests" / "fixtures" / "whisper_zerocut.wav"
    if not fixture.exists() or fixture.stat().st_size < 1000:
        return {"executed": False, "passed": False, "reason": "AUDIO_FIXTURE_MISSING"}
    with tempfile.TemporaryDirectory(prefix="zerocut-whisper-") as td:
        out_base = Path(td) / "selftest"
        cmd = build_whisper_command(Path(cap["binary"]), Path(cap["model"]), fixture, out_base, "en")
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {"executed": True, "passed": False, "reason": type(exc).__name__}
        text = ""
        for candidate in (out_base.with_suffix(".srt"), out_base.with_suffix(".json"), out_base.with_suffix(".txt")):
            if candidate.exists():
                try:
                    text += " " + candidate.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    pass
        normalized = re.sub(r"[^a-z0-9]+", " ", text.lower())
        # TTS may render ZeroCut as one or two words; accept either, but require actual text output.
        semantic_hit = ("zero cut" in normalized) or ("zerocut" in normalized)
        passed = proc.returncode == 0 and bool(normalized.strip()) and semantic_hit
        return {
            "executed": True, "passed": passed, "reason": "OK" if passed else "TRANSCRIPTION_MISMATCH",
            "returncode": proc.returncode, "text_preview": normalized.strip()[:240],
        }


def build_whisper_command(binary: Path, model: Path, audio: Path, output_base: Path, language="auto") -> list[str]:
    return [
        str(binary), "-m", str(model), "-f", str(audio), "-l", language,
        "-ojf", "-osrt", "-sow", "-of", str(output_base), "-np",
    ]



def transcribe_media_whisper(media_path: Path, *, language: str = "auto", ffmpeg_bin: str = "ffmpeg",
                             timeout: float = 1800.0) -> dict:
    """Run a real local whisper.cpp transcription when certified runtime assets exist.

    The result is content-addressed by source + model fingerprint and cached atomically.
    No network/API fallback exists: missing local assets fail closed.
    """
    media_path=Path(media_path).resolve()
    if not media_path.exists() or not media_path.is_file():
        return {"ok":False,"executed":False,"reason":"MEDIA_MISSING"}
    cap=discover_whisper()
    if not cap.get("available"):
        return {"ok":False,"executed":False,"reason":cap.get("reason_code","WHISPER_NOT_AVAILABLE")}
    source_fp=_file_fingerprint(media_path)
    model_fp=_file_fingerprint(cap.get("model"))
    if not source_fp.get("sha256") or not model_fp.get("sha256"):
        return {"ok":False,"executed":False,"reason":"FINGERPRINT_FAILED"}
    lang=(language or "auto").strip().lower()
    key=hashlib.sha256(json.dumps({"source":source_fp["sha256"],"model":model_fp["sha256"],"lang":lang,"schema":1},sort_keys=True).encode()).hexdigest()
    cache_dir=TRANSCRIPT / "cache"
    cache_dir.mkdir(parents=True,exist_ok=True)
    cache_file=cache_dir / f"{key}.json"
    try:
        cached=json.loads(cache_file.read_text(encoding="utf-8"))
        if cached.get("ok") and isinstance(cached.get("segments"),list):
            cached["cache_hit"]=True
            return cached
    except (OSError,ValueError,TypeError):
        pass
    with tempfile.TemporaryDirectory(prefix="zerocut-asr-") as td:
        td=Path(td); wav=td/"audio.wav"; out_base=td/"whisper"
        extract=[ffmpeg_bin,"-hide_banner","-loglevel","error","-y","-i",str(media_path),"-vn","-ac","1","-ar","16000","-c:a","pcm_s16le",str(wav)]
        try:
            ep=subprocess.run(extract,capture_output=True,text=True,timeout=min(timeout,300.0))
        except (OSError,subprocess.TimeoutExpired) as exc:
            return {"ok":False,"executed":True,"reason":type(exc).__name__}
        if ep.returncode!=0 or not wav.exists() or wav.stat().st_size<1000:
            return {"ok":False,"executed":True,"reason":"AUDIO_EXTRACTION_FAILED"}
        cmd=build_whisper_command(Path(cap["binary"]),Path(cap["model"]),wav,out_base,lang)
        try:
            wp=subprocess.run(cmd,capture_output=True,text=True,timeout=timeout)
        except (OSError,subprocess.TimeoutExpired) as exc:
            return {"ok":False,"executed":True,"reason":type(exc).__name__}
        srt=out_base.with_suffix(".srt")
        if wp.returncode!=0 or not srt.exists():
            return {"ok":False,"executed":True,"reason":"WHISPER_FAILED","returncode":wp.returncode}
        segments=parse_srt(srt.read_text(encoding="utf-8",errors="replace"))
        if not segments:
            return {"ok":False,"executed":True,"reason":"EMPTY_TRANSCRIPT"}
        result={"ok":True,"executed":True,"reason":"OK","cache_hit":False,"language":lang,"segments":segments,
                "text":" ".join(x["text"] for x in segments),"source_sha256":source_fp["sha256"],"model_sha256":model_fp["sha256"]}
        tmp=cache_file.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
        os.replace(tmp,cache_file)
        return result

def ffmpeg_video_encoders(ffmpeg: str = "ffmpeg") -> set[str]:
    """Return video encoders advertised by this FFmpeg build. Advertisement is not proof of usability."""
    try:
        proc = subprocess.run([ffmpeg, "-hide_banner", "-encoders"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return set()
    if proc.returncode != 0:
        return set()
    out = set()
    for line in proc.stdout.splitlines():
        m = re.match(r"^\s*V[.A-Z]{5}\s+(\S+)", line)
        if m:
            out.add(m.group(1))
    return out


def smoke_test_video_encoder(encoder: str, ffmpeg: str = "ffmpeg", timeout: float = 12.0) -> bool:
    """Verify that an advertised encoder can actually encode one tiny frame on this machine."""
    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
           "color=c=black:s=128x128:d=0.05", "-frames:v", "1", "-an", "-c:v", encoder,
           "-f", "null", "-"]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=timeout)
        return proc.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def ffmpeg_hwaccels(ffmpeg: str = "ffmpeg") -> set[str]:
    """Return hardware acceleration methods advertised by FFmpeg; not proof they work on this host."""
    try:
        proc = subprocess.run([ffmpeg, "-hide_banner", "-hwaccels"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return set()
    if proc.returncode != 0:
        return set()
    return {line.strip().lower() for line in proc.stdout.splitlines() if line.strip() and not line.lower().startswith("hardware acceleration")}


def smoke_test_hw_decode(method: str, source: Path, ffmpeg: str = "ffmpeg", timeout: float = 12.0) -> bool:
    """Actually decode a few frames through a requested hwaccel. Fail closed; never enables it on advertisement alone."""
    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-hwaccel", method, "-i", str(source),
           "-frames:v", "8", "-an", "-f", "null", "-"]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=timeout)
        return proc.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def detect_usable_hw_decoders(source: Path, ffmpeg: str = "ffmpeg") -> dict:
    """Capability gate for future preview acceleration: report only methods proven on the current media/host."""
    advertised = ffmpeg_hwaccels(ffmpeg)
    platform_order = ("d3d11va", "dxva2", "cuda", "qsv", "vaapi", "videotoolbox")
    tested = []
    usable = []
    for method in platform_order:
        if method not in advertised:
            continue
        ok = smoke_test_hw_decode(method, source, ffmpeg)
        tested.append({"method": method, "passed": ok})
        if ok:
            usable.append(method)
    return {"advertised": sorted(advertised), "tested": tested, "usable": usable,
            "hardware_decode_enabled": False, "reason": "CAPABILITY_ONLY_NOT_AUTO_ENABLED"}


def benchmark_hw_decode(source: Path, ffmpeg: str = "ffmpeg", seconds: float = 2.0, min_speedup: float = 1.15, repeats: int = 3, max_cv: float = 0.12) -> dict:
    """Benchmark proven hw decoders against CPU using warm-up + median timings. Advisory only; fail closed."""
    import time
    import statistics
    seconds = max(0.25, min(float(seconds), 5.0))
    min_speedup = max(1.0, float(min_speedup))
    repeats = max(2, min(int(repeats), 5))
    max_cv = max(0.01, min(float(max_cv), 0.50))
    caps = detect_usable_hw_decoders(source, ffmpeg)

    def one(method=None):
        cmd=[ffmpeg,"-hide_banner","-loglevel","error"]
        if method:
            cmd += ["-hwaccel", method]
        cmd += ["-t", f"{seconds:.3f}", "-i", str(source), "-an", "-f", "null", "-"]
        started=time.perf_counter()
        try:
            proc=subprocess.run(cmd,capture_output=True,timeout=max(12.0, seconds*8.0))
            return proc.returncode == 0, max(time.perf_counter()-started, 1e-6)
        except (OSError, subprocess.TimeoutExpired):
            return False, None

    def run(method=None):
        # First invocation is a warm-up and is intentionally excluded: driver/context
        # startup otherwise biases short clips heavily against hardware decode.
        warm_ok, _ = one(method)
        if not warm_ok:
            return {"passed":False,"elapsed_seconds":None,"samples":[]}
        samples=[]
        for _ in range(repeats):
            ok, elapsed=one(method)
            if not ok or elapsed is None:
                return {"passed":False,"elapsed_seconds":None,"samples":[round(x,4) for x in samples]}
            samples.append(elapsed)
        median=float(statistics.median(samples))
        mean=float(statistics.mean(samples))
        stdev=float(statistics.pstdev(samples)) if len(samples) > 1 else 0.0
        cv=(stdev/mean) if mean > 0 else 1.0
        stable=cv <= max_cv
        return {"passed":True,"elapsed_seconds":round(median,4),"samples":[round(x,4) for x in samples],
                "coefficient_of_variation":round(cv,4),"stable":stable}

    cpu=run()
    rows=[]
    if cpu["passed"] and cpu["elapsed_seconds"]:
        for method in caps["usable"]:
            result=run(method)
            speedup=None
            if result["passed"] and result["elapsed_seconds"]:
                speedup=round(cpu["elapsed_seconds"]/result["elapsed_seconds"],3)
            rows.append({"method":method,**result,"speedup_vs_cpu":speedup})
    eligible=[r for r in rows if r["passed"] and r.get("stable") and cpu.get("stable") and r["speedup_vs_cpu"] is not None and r["speedup_vs_cpu"] >= min_speedup]
    best=max(eligible,key=lambda r:r["speedup_vs_cpu"],default=None)
    return {"cpu":cpu,"hardware":rows,"recommended":best["method"] if best else None,
            "min_speedup":min_speedup,"repeats":repeats,"statistic":"median_after_warmup","max_cv":max_cv,"auto_enabled":False,
            "reason":"BENCHMARK_ADVISORY_NOT_AUTO_ENABLED"}


_VIDEO_ENCODER_CAP_CACHE: dict[tuple, dict] = {}

def _ffmpeg_capability_identity(ffmpeg: str) -> tuple:
    """Stable-enough identity so cached hardware probes are invalidated when the FFmpeg binary changes."""
    resolved = shutil.which(ffmpeg) or ffmpeg
    try:
        path = Path(resolved).resolve()
        st = path.stat()
        return (str(path), int(st.st_size), int(st.st_mtime_ns))
    except (OSError, ValueError):
        return (str(resolved), None, None)

def detect_best_video_encoder(ffmpeg: str = "ffmpeg") -> dict:
    """Choose a proven H.264 encoder once per FFmpeg binary identity; retain CPU fallback."""
    identity = _ffmpeg_capability_identity(ffmpeg)
    cached = _VIDEO_ENCODER_CAP_CACHE.get(identity)
    if cached is not None:
        return dict(cached)
    advertised = ffmpeg_video_encoders(ffmpeg)
    result = None
    for encoder, label in (("h264_nvenc", "NVIDIA NVENC"), ("h264_qsv", "Intel QSV"), ("h264_amf", "AMD AMF")):
        if encoder in advertised and smoke_test_video_encoder(encoder, ffmpeg):
            result = {"encoder": encoder, "label": label, "hardware": True, "verified": True}
            break
    if result is None:
        # libx264 is ZeroCut's validated baseline; smoke-test it too so callers can expose a truthful capability state.
        ok = "libx264" in advertised and smoke_test_video_encoder("libx264", ffmpeg)
        result = {"encoder": "libx264", "label": "CPU libx264", "hardware": False, "verified": ok}
    _VIDEO_ENCODER_CAP_CACHE[identity] = dict(result)
    return dict(result)


def benchmark_verified_video_encoder(ffmpeg: str = "ffmpeg", seconds: float = 0.8, repeats: int = 3,
                                     min_speedup: float = 1.10, max_cv: float = 0.20) -> dict:
    """Benchmark only smoke-verified hardware encoders against libx264 and fail closed to CPU.

    This is intentionally bounded and conservative: a warm-up is excluded, median elapsed time is used,
    unstable samples are rejected, and no hardware encoder is selected unless it beats the validated CPU
    baseline by min_speedup. Output is discarded to null, so this is a capability benchmark, not a quality claim.
    """
    import time
    import statistics
    seconds=max(0.25,min(float(seconds),2.0)); repeats=max(2,min(int(repeats),5))
    min_speedup=max(1.0,float(min_speedup)); max_cv=max(0.01,min(float(max_cv),0.50))
    advertised=ffmpeg_video_encoders(ffmpeg)

    def verified(enc):
        return enc in advertised and smoke_test_video_encoder(enc, ffmpeg)

    def one(enc):
        cmd=[ffmpeg,"-hide_banner","-loglevel","error","-f","lavfi","-i",
             f"testsrc2=s=640x360:r=30:d={seconds:.3f}","-an","-c:v",enc]
        if enc == "libx264": cmd += ["-preset","veryfast","-crf","18"]
        elif enc == "h264_nvenc": cmd += ["-preset","p5","-cq","19"]
        elif enc == "h264_qsv": cmd += ["-global_quality","19"]
        elif enc == "h264_amf": cmd += ["-quality","quality","-qp_i","19","-qp_p","19"]
        cmd += ["-f","null","-"]
        t=time.perf_counter()
        try:
            proc=subprocess.run(cmd,capture_output=True,timeout=max(15.0,seconds*10.0))
            return proc.returncode == 0, max(time.perf_counter()-t,1e-6)
        except (OSError, subprocess.TimeoutExpired): return False,None

    def measure(enc):
        ok,_=one(enc)  # warm-up excluded
        if not ok: return {"encoder":enc,"passed":False,"stable":False,"samples":[]}
        xs=[]
        for _ in range(repeats):
            ok,t=one(enc)
            if not ok or t is None: return {"encoder":enc,"passed":False,"stable":False,"samples":[round(x,4) for x in xs]}
            xs.append(t)
        med=float(statistics.median(xs)); mean=float(statistics.mean(xs)); sd=float(statistics.pstdev(xs))
        cv=sd/mean if mean else 1.0
        return {"encoder":enc,"passed":True,"stable":cv <= max_cv,"elapsed_seconds":round(med,4),
                "samples":[round(x,4) for x in xs],"coefficient_of_variation":round(cv,4)}

    if not verified("libx264"):
        return {"recommended":{"encoder":"libx264","label":"CPU libx264","hardware":False,"verified":False},
                "cpu":None,"hardware":[],"reason":"CPU_BASELINE_NOT_VERIFIED","auto_selected":False}
    cpu=measure("libx264"); rows=[]
    for enc,label in (("h264_nvenc","NVIDIA NVENC"),("h264_qsv","Intel QSV"),("h264_amf","AMD AMF")):
        if not verified(enc): continue
        r=measure(enc); r["label"]=label
        if r.get("passed") and cpu.get("passed") and r.get("elapsed_seconds") and cpu.get("elapsed_seconds"):
            r["speedup_vs_cpu"]=round(cpu["elapsed_seconds"]/r["elapsed_seconds"],3)
        rows.append(r)
    eligible=[r for r in rows if r.get("passed") and r.get("stable") and cpu.get("stable") and
              r.get("speedup_vs_cpu",0) >= min_speedup]
    best=max(eligible,key=lambda r:r["speedup_vs_cpu"],default=None)
    if best:
        rec={"encoder":best["encoder"],"label":best["label"],"hardware":True,"verified":True,
             "benchmarked":True,"speedup_vs_cpu":best["speedup_vs_cpu"]}
        reason="VERIFIED_STABLE_SPEEDUP"
    else:
        rec={"encoder":"libx264","label":"CPU libx264","hardware":False,"verified":True,"benchmarked":True}
        reason="NO_VERIFIED_STABLE_HARDWARE_ADVANTAGE"
    return {"recommended":rec,"cpu":cpu,"hardware":rows,"reason":reason,"auto_selected":bool(best),
            "min_speedup":min_speedup,"repeats":repeats,"max_cv":max_cv}

def _encoder_export_args(capability: dict | None) -> list[str]:
    """Map only a previously smoke-verified encoder capability to conservative FFmpeg args."""
    cap = capability or {}
    if not cap.get("verified"):
        return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18"]
    encoder = str(cap.get("encoder") or "libx264")
    if encoder == "h264_nvenc":
        return ["-c:v", encoder, "-preset", "p5", "-cq", "19"]
    if encoder == "h264_qsv":
        return ["-c:v", encoder, "-global_quality", "19"]
    if encoder == "h264_amf":
        return ["-c:v", encoder, "-quality", "quality", "-qp_i", "19", "-qp_p", "19"]
    return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18"]

def export_command(source: Path, output: Path, segments: list[dict], has_audio: bool, fps: float = 0.0,
                   subtitle_path: Path | None = None, subtitle_style: str = "gaming-bold",
                   encoder_capability: dict | None = None, ffmpeg_bin: str | None = None) -> tuple[list[str], float]:
    clean = []
    for seg in segments:
        start = max(0.0, float(seg.get("start", 0)))
        end = max(start, float(seg.get("end", 0)))
        if end - start < 0.04:
            continue
        clean.append((start, end))
    if not clean:
        raise ValueError("Timeline vuota")
    total = sum(end - start for start, end in clean)

    cmd = [str(ffmpeg_bin or _active_media_tool("ffmpeg")), "-y", "-hide_banner", "-nostdin", "-i", str(source)]
    filters = []
    concat_inputs = []
    for i, (start, end) in enumerate(clean):
        filters.append(f"[0:v:0]trim=start={start:.6f}:end={end:.6f},setpts=PTS-STARTPTS[v{i}]")
        concat_inputs.append(f"[v{i}]")
        if has_audio:
            filters.append(f"[0:a:0]atrim=start={start:.6f}:end={end:.6f},asetpts=PTS-STARTPTS[a{i}]")
            concat_inputs.append(f"[a{i}]")
    if has_audio:
        filters.append("".join(concat_inputs) + f"concat=n={len(clean)}:v=1:a=1[vbase][aout]")
    else:
        filters.append("".join(concat_inputs) + f"concat=n={len(clean)}:v=1:a=0[vbase]")

    video_out = "[vbase]"
    if subtitle_path:
        style = SUBTITLE_STYLES.get(subtitle_style, SUBTITLE_STYLES["gaming-bold"])
        escaped = _ffmpeg_filter_escape(subtitle_path)
        filters.append(f"[vbase]subtitles=filename='{escaped}':force_style='{style}'[vsub]")
        video_out = "[vsub]"

    cmd += ["-filter_complex", ";".join(filters), "-map", video_out]
    if has_audio:
        cmd += ["-map", "[aout]"]
    cmd += _encoder_export_args(encoder_capability)
    cmd += ["-pix_fmt", "yuv420p"]
    if fps > 0:
        fps_text = (f"{fps:.6f}").rstrip("0").rstrip(".")
        cmd += ["-r", fps_text, "-fps_mode", "cfr"]
    cmd += ["-movflags", "+faststart"]
    if has_audio:
        cmd += ["-c:a", "aac", "-b:a", "192k", "-ar", "48000"]
    cmd += ["-progress", "pipe:1", "-nostats", str(output)]
    return cmd, total


def decode_smoke_check(path: Path, duration: float, ffmpeg_bin: str | None = None, timeout: float = 20.0) -> dict:
    """Decode real frames near both ends of an export before it is published.

    FFprobe can describe a container whose media payload is nevertheless undecodable.
    This bounded check decodes one frame near the beginning and one near the tail; it
    is intentionally cheap and fails closed on decoder errors/timeouts.
    """
    ffmpeg_bin = str(ffmpeg_bin or _active_media_tool("ffmpeg"))
    points = [0.0]
    duration = max(0.0, float(duration or 0.0))
    if duration > 0.8:
        points.append(max(0.0, duration - min(0.5, duration * 0.1)))
    checked=[]
    for point in points:
        cmd=[ffmpeg_bin,"-v","error","-xerror","-ss",f"{point:.6f}","-i",str(path),
             "-map","0:v:0","-frames:v","1","-f","null","-"]
        try:
            proc=subprocess.run(cmd,capture_output=True,text=True,timeout=float(timeout))
        except (OSError,subprocess.TimeoutExpired) as exc:
            return {"ok":False,"checked":checked,"reason":type(exc).__name__}
        if proc.returncode != 0:
            return {"ok":False,"checked":checked,"reason":"DECODE_ERROR","stderr":proc.stderr[-500:]}
        checked.append(point)
    return {"ok":True,"checked":checked,"reason":"OK"}


def probe_av_timing(path: Path, *, ffprobe_bin: str | None = None, timeout: float = 20.0,
                    start_tolerance: float = 0.25, duration_tolerance: float = 0.35) -> dict:
    """Measure audio/video start and duration deltas from real stream timestamps."""
    tool=str(ffprobe_bin or _active_media_tool("ffprobe"))
    cmd=[tool,"-v","error","-show_entries","stream=codec_type,start_time,duration","-of","json",str(path)]
    try: proc=subprocess.run(cmd,capture_output=True,text=True,timeout=float(timeout))
    except (OSError,subprocess.TimeoutExpired) as exc:
        return {"ok":False,"reason":type(exc).__name__}
    if proc.returncode != 0:
        return {"ok":False,"reason":"FFPROBE_ERROR","stderr":(proc.stderr or "")[-500:]}
    try: rows=json.loads(proc.stdout or "{}").get("streams") or []
    except json.JSONDecodeError:
        return {"ok":False,"reason":"INVALID_JSON"}
    def first(kind):
        return next((x for x in rows if isinstance(x,dict) and x.get("codec_type")==kind),None)
    v=first("video"); a=first("audio")
    if not v: return {"ok":False,"reason":"VIDEO_STREAM_MISSING"}
    def num(row,key):
        try:
            val=float((row or {}).get(key) or 0.0)
            return val if math.isfinite(val) else 0.0
        except (TypeError,ValueError): return 0.0
    vs=num(v,"start_time"); vd=num(v,"duration")
    if not a:
        return {"ok":True,"reason":"VIDEO_ONLY","video_start":vs,"video_duration":vd,
                "audio_start":None,"audio_duration":None,"start_delta":None,"duration_delta":None}
    ast=num(a,"start_time"); ad=num(a,"duration")
    start_delta=abs(ast-vs); duration_delta=abs(ad-vd) if ad and vd else 0.0
    ok=start_delta <= float(start_tolerance) and duration_delta <= float(duration_tolerance)
    return {"ok":ok,"reason":"OK" if ok else "AV_SYNC_OUT_OF_TOLERANCE",
            "video_start":vs,"video_duration":vd,"audio_start":ast,"audio_duration":ad,
            "start_delta":round(start_delta,6),"duration_delta":round(duration_delta,6),
            "start_tolerance":float(start_tolerance),"duration_tolerance":float(duration_tolerance)}


def verify_render_output(path: Path, expected_duration: float, *, expect_audio: bool = False,
                         ffmpeg_bin: str | None = None, ffprobe_bin: str | None = None) -> dict:
    """Fail closed before publishing a render that FFmpeg created but is unusable/truncated."""
    if not path.exists() or path.stat().st_size < 1024:
        raise RuntimeError("Render mancante o troppo piccolo")
    meta = ffprobe(path, ffprobe_bin=ffprobe_bin)
    video = meta.get("video") or {}
    if not video.get("codec"):
        raise RuntimeError("Render senza stream video valido")
    actual = float(meta.get("duration") or 0.0)
    expected = max(0.0, float(expected_duration or 0.0))
    # Encoding/muxing timestamps can differ slightly. Reject only meaningful truncation/overrun.
    tolerance = max(0.35, min(2.0, expected * 0.02)) if expected else 0.35
    if actual <= 0 or (expected and abs(actual - expected) > tolerance):
        raise RuntimeError(f"Durata render non valida: attesa {expected:.3f}s, ottenuta {actual:.3f}s")
    if expect_audio and not (meta.get("audio") or {}).get("codec"):
        raise RuntimeError("Render senza audio atteso")
    av_timing = probe_av_timing(path, ffprobe_bin=ffprobe_bin)
    if expect_audio and not av_timing.get("ok"):
        raise RuntimeError(f"Render A/V non sincronizzato: {av_timing.get('reason','UNKNOWN')} start_delta={av_timing.get('start_delta')}")
    decode_check = decode_smoke_check(path, actual, ffmpeg_bin=ffmpeg_bin)
    if not decode_check.get("ok"):
        raise RuntimeError(f"Render video non decodificabile: {decode_check.get('reason','UNKNOWN')}")
    return {"ok": True, "duration": actual, "size": path.stat().st_size, "metadata": meta,
            "av_timing": av_timing, "decode_smoke": decode_check}


def can_lossless_passthrough_export(segments: list[dict], metadata: dict, *, has_subtitles: bool) -> bool:
    """Allow stream-copy only for an untouched full-length MP4-compatible timeline."""
    if has_subtitles or len(segments or []) != 1: return False
    duration = float((metadata or {}).get("duration") or 0.0)
    if duration <= 0: return False
    seg = segments[0]
    try: start, end = float(seg.get("start", 0.0)), float(seg.get("end", 0.0))
    except (TypeError, ValueError): return False
    if abs(start) > 0.001 or abs(end - duration) > 0.05: return False
    video = ((metadata or {}).get("video") or {}).get("codec", "").lower()
    audio = ((metadata or {}).get("audio") or {}).get("codec", "").lower()
    return video in {"h264", "hevc", "mpeg4", "av1"} and (not audio or audio in {"aac", "mp3", "ac3", "eac3", "alac"})

def lossless_passthrough_command(source: Path, output: Path, duration: float, ffmpeg_bin: str | None = None) -> tuple[list[str], float]:
    cmd = [str(ffmpeg_bin or _active_media_tool("ffmpeg")), "-y", "-hide_banner", "-nostdin", "-i", str(source), "-map", "0:v:0", "-map", "0:a:0?", "-c", "copy", "-movflags", "+faststart", "-progress", "pipe:1", "-nostats", str(output)]
    return cmd, float(duration)


def probe_video_keyframes(source: Path, ffprobe_bin: str | None = None, timeout: float = 20.0) -> list[float]:
    """Return decoded video keyframe timestamps for safe stream-copy trim decisions."""
    ffprobe_bin = str(ffprobe_bin or _active_media_tool("ffprobe"))
    cmd=[ffprobe_bin,"-v","error","-select_streams","v:0","-skip_frame","nokey",
         "-show_entries","frame=best_effort_timestamp_time","-of","csv=p=0",str(source)]
    try:
        proc=subprocess.run(cmd,capture_output=True,text=True,timeout=float(timeout))
    except (OSError,subprocess.TimeoutExpired): return []
    if proc.returncode != 0: return []
    out=[]
    for line in proc.stdout.splitlines():
        token=line.strip().split(',')[0].strip()
        try: value=float(token)
        except (TypeError,ValueError): continue
        if value >= 0: out.append(value)
    return sorted(set(out))


def cached_video_keyframes(source: Path, ffprobe_bin: str | None = None, timeout: float = 20.0) -> tuple[list[float], bool]:
    """Return a persistent keyframe index keyed by immutable-enough local file identity.

    Keyframe scans decode video metadata across the whole file and can be noticeable on
    long recordings.  The cache key includes resolved path, size and nanosecond mtime,
    so replaced/modified media fail closed into a fresh probe. Cache files are written
    atomically and malformed entries are ignored.
    """
    source = Path(source).resolve()
    try:
        st = source.stat()
    except OSError:
        return [], False
    identity = f"{source}|{st.st_size}|{st.st_mtime_ns}|keyframes-v1"
    key = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    target = KEYFRAME_CACHE / f"{key}.json"
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
        values = payload.get("keyframes") if isinstance(payload, dict) else None
        if isinstance(values, list):
            keys = sorted(set(float(v) for v in values if float(v) >= 0))
            return keys, True
    except (FileNotFoundError, OSError, ValueError, TypeError, json.JSONDecodeError):
        pass
    keys = probe_video_keyframes(source, ffprobe_bin=ffprobe_bin, timeout=timeout)
    if keys:
        tmp = target.with_suffix(f".{uuid.uuid4().hex}.tmp")
        try:
            tmp.write_text(json.dumps({"schema": 1, "keyframes": keys}, separators=(",", ":")), encoding="utf-8")
            os.replace(tmp, target)
        except OSError:
            tmp.unlink(missing_ok=True)
    return keys, False


def can_lossless_keyframe_trim_export(source: Path, segments: list[dict], metadata: dict, *,
                                      has_subtitles: bool, tolerance: float = 0.035) -> bool:
    """Permit zero-generation-loss trim only when BOTH boundaries are real keyframes.

    Stream-copying arbitrary trims can start on an undecodable GOP or drift from the
    requested edit.  ZeroCut therefore probes the actual source and fails closed unless
    the one requested segment starts and ends on keyframes (the media end is also safe).
    """
    if has_subtitles or len(segments or []) != 1: return False
    duration=float((metadata or {}).get("duration") or 0.0)
    if duration <= 0: return False
    video=((metadata or {}).get("video") or {}).get("codec","").lower()
    audio=((metadata or {}).get("audio") or {}).get("codec","").lower()
    if video not in {"h264","hevc","mpeg4","av1"} or (audio and audio not in {"aac","mp3","ac3","eac3","alac"}): return False
    try: start=float(segments[0].get("start",0.0)); end=float(segments[0].get("end",0.0))
    except (TypeError,ValueError): return False
    if start < 0 or end <= start or end > duration + 0.05: return False
    if abs(start) <= tolerance and abs(end-duration) <= max(tolerance,0.05): return False  # handled by passthrough gate
    keys,_cache_hit=cached_video_keyframes(Path(source))
    if not keys: return False
    start_ok=abs(start) <= tolerance or any(abs(k-start) <= tolerance for k in keys)
    end_ok=abs(end-duration) <= max(tolerance,0.05) or any(abs(k-end) <= tolerance for k in keys)
    return bool(start_ok and end_ok)


def lossless_keyframe_trim_command(source: Path, output: Path, start: float, end: float,
                                   ffmpeg_bin: str | None = None) -> tuple[list[str], float]:
    start=max(0.0,float(start)); end=max(start,float(end)); span=end-start
    cmd=[str(ffmpeg_bin or _active_media_tool("ffmpeg")),"-y","-hide_banner","-nostdin","-i",str(source),"-ss",f"{start:.6f}",
         "-t",f"{span:.6f}","-map","0:v:0","-map","0:a:0?","-c","copy","-avoid_negative_ts","make_zero",
         "-movflags","+faststart","-progress","pipe:1","-nostats",str(output)]
    return cmd,span


def scene_cut_command(source: Path, threshold: float = 0.30) -> list[str]:
    """Build a dependency-free FFmpeg scene-boundary scan.

    Pattern adapted from slhck/scenecut-extractor (MIT): use FFmpeg's scene
    score and showinfo timestamps, while keeping ZeroCut's own parser/API.
    """
    threshold = max(0.0, min(1.0, float(threshold)))
    vf = f"select=gt(scene\\,{threshold:.3f}),showinfo"
    return [
        "ffmpeg", "-hide_banner", "-nostdin", "-i", str(source),
        "-an", "-vf", vf, "-vsync", "vfr", "-f", "null", "-",
    ]


def parse_scene_cut_log(stderr: str) -> list[float]:
    cuts = []
    for match in re.finditer(r"\bpts_time:([0-9]+(?:\.[0-9]+)?)", stderr or ""):
        value = float(match.group(1))
        if not cuts or abs(value - cuts[-1]) > 1e-6:
            cuts.append(value)
    return cuts


def detect_scene_cuts(source: Path, threshold: float = 0.30, timeout: float = 300.0) -> list[float]:
    proc = subprocess.run(scene_cut_command(source, threshold), stdout=subprocess.DEVNULL,
                          stderr=subprocess.PIPE, text=True, timeout=timeout, check=False)
    if proc.returncode != 0:
        tail = (proc.stderr or "")[-1200:]
        raise RuntimeError(f"FFmpeg scene scan failed ({proc.returncode}): {tail}")
    return parse_scene_cut_log(proc.stderr)




def silence_detect_command(source: Path, noise_db: float = -38.0, min_silence: float = 0.70) -> list[str]:
    """Build a local FFmpeg silence scan for generic post-production analysis.

    The detector is intentionally conservative: it only marks sustained low-level
    audio and never claims semantic inactivity. The result is suitable for a
    Director preview, not an automatic destructive commit by itself.
    """
    noise_db = max(-90.0, min(-5.0, float(noise_db)))
    min_silence = max(0.10, min(30.0, float(min_silence)))
    af = f"silencedetect=noise={noise_db:.2f}dB:d={min_silence:.3f}"
    return [
        "ffmpeg", "-hide_banner", "-nostdin", "-i", str(source), "-vn",
        "-af", af, "-f", "null", "-",
    ]


def parse_silence_detect_log(stderr: str, *, duration: float | None = None) -> list[dict]:
    """Parse FFmpeg silencedetect output into bounded, non-overlapping intervals."""
    events=[]
    for line in (stderr or "").splitlines():
        start=re.search(r"silence_start:\s*(-?[0-9]+(?:\.[0-9]+)?)", line)
        if start:
            events.append(("start", float(start.group(1))))
        end=re.search(r"silence_end:\s*(-?[0-9]+(?:\.[0-9]+)?)", line)
        if end:
            events.append(("end", float(end.group(1))))
    limit=None if duration is None else max(0.0,float(duration))
    rows=[]; current=None
    for kind,value in events:
        value=max(0.0,value)
        if limit is not None:
            value=min(limit,value)
        if kind=="start":
            if current is None:
                current=value
        elif current is not None and value>current:
            rows.append({"start":round(current,4),"end":round(value,4),"duration":round(value-current,4)})
            current=None
    if current is not None and limit is not None and limit>current:
        rows.append({"start":round(current,4),"end":round(limit,4),"duration":round(limit-current,4)})
    # Defensive normalization in case FFmpeg emits duplicate/overlapping events.
    merged=[]
    for row in sorted(rows,key=lambda x:(x["start"],x["end"])):
        if merged and row["start"] <= merged[-1]["end"] + 1e-4:
            merged[-1]["end"]=round(max(merged[-1]["end"],row["end"]),4)
            merged[-1]["duration"]=round(merged[-1]["end"]-merged[-1]["start"],4)
        else:
            merged.append(dict(row))
    return merged


def detect_silences(source: Path, *, duration: float | None = None, noise_db: float = -38.0,
                    min_silence: float = 0.70, timeout: float = 300.0) -> list[dict]:
    proc=subprocess.run(silence_detect_command(source,noise_db,min_silence),stdout=subprocess.DEVNULL,
                        stderr=subprocess.PIPE,text=True,timeout=timeout,check=False)
    if proc.returncode != 0:
        tail=(proc.stderr or "")[-1200:]
        raise RuntimeError(f"FFmpeg silence scan failed ({proc.returncode}): {tail}")
    return parse_silence_detect_log(proc.stderr,duration=duration)


def keep_segments_from_silences(duration: float, silences: list[dict], *, padding: float = 0.12,
                                min_remove: float = 0.80, min_keep: float = 0.12) -> list[dict]:
    """Return a non-destructive preview timeline with long silent interiors removed.

    Small padding is retained around speech/audio transitions to avoid clipped syllables.
    The result is only a candidate; Director commit safety remains handled separately.
    """
    duration=max(0.0,float(duration)); padding=max(0.0,float(padding))
    min_remove=max(0.05,float(min_remove)); min_keep=max(0.04,float(min_keep))
    remove=[]
    for row in silences or []:
        try: a=max(0.0,float(row["start"])); b=min(duration,float(row["end"]))
        except (KeyError,TypeError,ValueError): continue
        if b-a < min_remove: continue
        cut_a=min(b,max(a,a+padding)); cut_b=max(cut_a,min(b,b-padding))
        if cut_b-cut_a >= 0.04:
            remove.append((cut_a,cut_b))
    # Merge removal ranges first.
    merged=[]
    for a,b in sorted(remove):
        if merged and a <= merged[-1][1] + 1e-6:
            merged[-1]=(merged[-1][0],max(merged[-1][1],b))
        else: merged.append((a,b))
    keep=[]; cursor=0.0
    for a,b in merged:
        if a-cursor >= min_keep:
            keep.append({"id":f"keep-{len(keep)+1:03d}","start":round(cursor,6),"end":round(a,6)})
        cursor=max(cursor,b)
    if duration-cursor >= min_keep:
        keep.append({"id":f"keep-{len(keep)+1:03d}","start":round(cursor,6),"end":round(duration,6)})
    return keep or ([{"id":"keep-001","start":0.0,"end":round(duration,6)}] if duration>0 else [])


def motion_sample_command(source: Path, sample_fps: float = 4.0, analysis_width: int = 320) -> list[str]:
    """Build a cheap local FFmpeg frame-difference scan.

    The pipeline downsizes before measuring grayscale frame differences so motion
    analysis stays bounded even for 4K sources. `tblend=difference` +
    `signalstats.YAVG` is deterministic and requires no AI/runtime dependency.
    """
    sample_fps=max(0.5,min(12.0,float(sample_fps)))
    analysis_width=max(64,min(640,int(analysis_width)))
    analysis_width -= analysis_width % 2
    vf=(f"fps={sample_fps:.3f},scale={analysis_width}:-2:flags=area,format=gray,"
        "tblend=all_mode=difference,signalstats,"
        "metadata=mode=print:key=lavfi.signalstats.YAVG")
    return [
        "ffmpeg","-hide_banner","-nostdin","-i",str(source),"-an","-vf",vf,
        "-f","null","-",
    ]


def parse_motion_sample_log(stderr: str) -> list[dict]:
    """Parse FFmpeg metadata output into timestamped frame-difference energy."""
    rows=[]; current_time=None
    for line in (stderr or "").splitlines():
        tm=re.search(r"\bpts_time:([0-9]+(?:\.[0-9]+)?)",line)
        if tm:
            current_time=float(tm.group(1))
        ym=re.search(r"lavfi\.signalstats\.YAVG=([0-9]+(?:\.[0-9]+)?)",line)
        if ym and current_time is not None:
            value=max(0.0,min(255.0,float(ym.group(1))))
            row={"time":round(current_time,4),"motion_yavg":round(value,4)}
            if rows and abs(rows[-1]["time"]-row["time"]) <= 1e-6:
                rows[-1]=row
            else:
                rows.append(row)
    return rows


def detect_motion_samples(source: Path, *, sample_fps: float = 4.0, analysis_width: int = 320,
                          timeout: float = 300.0) -> list[dict]:
    proc=subprocess.run(motion_sample_command(source,sample_fps,analysis_width),stdout=subprocess.DEVNULL,
                        stderr=subprocess.PIPE,text=True,timeout=timeout,check=False)
    if proc.returncode != 0:
        tail=(proc.stderr or "")[-1200:]
        raise RuntimeError(f"FFmpeg motion scan failed ({proc.returncode}): {tail}")
    return parse_motion_sample_log(proc.stderr)


def normalize_motion_samples(samples: list[dict], *, reference_quantile: float = 0.85,
                             reference_floor: float = 1.0) -> tuple[list[dict], float]:
    """Normalize raw YAVG differences using a robust per-video reference.

    A relative reference adapts to screen recordings, chess boards, gameplay and
    camera footage without pretending one global pixel threshold fits every source.
    """
    valid=[]
    for row in samples or []:
        try:
            t=max(0.0,float(row["time"])); value=max(0.0,min(255.0,float(row["motion_yavg"])))
        except (KeyError,TypeError,ValueError):
            continue
        valid.append((t,value))
    if not valid:
        return [],max(0.01,float(reference_floor))
    values=sorted(v for _,v in valid)
    q=max(0.50,min(0.98,float(reference_quantile)))
    idx=max(0,min(len(values)-1,int(math.ceil(q*len(values)))-1))
    reference=max(float(reference_floor),values[idx])
    out=[{"time":round(t,4),"motion_yavg":round(v,4),
          "motion_score":round(max(0.0,min(1.0,v/reference)),4)} for t,v in valid]
    return out,round(reference,4)


def _motion_sample_step(samples: list[dict], default: float = 0.25) -> float:
    times=[]
    for row in samples or []:
        try: times.append(float(row["time"]))
        except (KeyError,TypeError,ValueError): pass
    times=sorted(set(times))
    diffs=[b-a for a,b in zip(times,times[1:]) if 0.001 < b-a < 5.0]
    return max(0.02,float(statistics.median(diffs))) if diffs else max(0.02,float(default))


def motion_activity_ranges(samples: list[dict], *, threshold: float = 0.22,
                           min_duration: float = 0.20, merge_gap: float | None = None) -> list[dict]:
    """Convert normalized motion samples into contiguous active-video ranges."""
    threshold=max(0.0,min(1.0,float(threshold))); min_duration=max(0.02,float(min_duration))
    if not samples: return []
    step=_motion_sample_step(samples); gap=step*1.6 if merge_gap is None else max(0.0,float(merge_gap))
    half=step/2.0; ranges=[]
    for row in samples:
        try: t=float(row["time"]); score=float(row.get("motion_score",0.0))
        except (KeyError,TypeError,ValueError): continue
        if score < threshold: continue
        a=max(0.0,t-half); b=max(a,t+half)
        if ranges and a <= ranges[-1]["end"] + gap:
            ranges[-1]["end"]=max(ranges[-1]["end"],b)
            ranges[-1]["max_motion_score"]=max(ranges[-1]["max_motion_score"],score)
            ranges[-1]["samples"]+=1
        else:
            ranges.append({"start":a,"end":b,"max_motion_score":score,"samples":1})
    out=[]
    for row in ranges:
        if row["end"]-row["start"] >= min_duration:
            out.append({"start":round(row["start"],4),"end":round(row["end"],4),
                        "duration":round(row["end"]-row["start"],4),
                        "max_motion_score":round(row["max_motion_score"],4),"samples":row["samples"]})
    return out


def motion_aware_dead_air_ranges(silences: list[dict], motion_samples: list[dict], *,
                                 motion_threshold: float = 0.18) -> list[dict]:
    """Keep only low-motion portions of sustained silence as dead-air candidates.

    This prevents a silent but visually active sequence (e.g. chess move, gameplay,
    product B-roll) from being removed merely because its audio is quiet.
    """
    if not motion_samples:
        return [dict(x) for x in (silences or [])]
    threshold=max(0.0,min(1.0,float(motion_threshold)))
    step=_motion_sample_step(motion_samples); half=step/2.0
    result=[]
    for silence in silences or []:
        try: start=max(0.0,float(silence["start"])); end=max(start,float(silence["end"]))
        except (KeyError,TypeError,ValueError): continue
        pts=[]
        for row in motion_samples:
            try: t=float(row["time"]); score=float(row.get("motion_score",0.0))
            except (KeyError,TypeError,ValueError): continue
            if start-half <= t <= end+half:
                pts.append((t,score))
        if not pts:
            result.append({"start":round(start,4),"end":round(end,4),"duration":round(end-start,4)})
            continue
        low=[t for t,score in pts if score <= threshold]
        if not low: continue
        groups=[]
        for t in low:
            if groups and t-groups[-1][-1] <= step*1.6:
                groups[-1].append(t)
            else:
                groups.append([t])
        for group in groups:
            a=max(start,group[0]-half); b=min(end,group[-1]+half)
            if group[0]-start <= step*1.6: a=start
            if end-group[-1] <= step*1.6: b=end
            if b-a >= 0.04:
                result.append({"start":round(a,4),"end":round(b,4),"duration":round(b-a,4)})
    # Merge tiny boundary overlaps introduced by sampling windows.
    merged=[]
    for row in sorted(result,key=lambda x:(x["start"],x["end"])):
        if merged and row["start"] <= merged[-1]["end"] + 1e-4:
            merged[-1]["end"]=round(max(merged[-1]["end"],row["end"]),4)
            merged[-1]["duration"]=round(merged[-1]["end"]-merged[-1]["start"],4)
        else: merged.append(dict(row))
    return merged


def build_universal_structure(duration: float, scene_cuts: list[float], silences: list[dict],
                              audio_peaks: list[dict], motion_samples: list[dict] | None = None,
                              *, audio_present: bool = True) -> list[dict]:
    """Create a generic multi-signal scene map usable by every content skill."""
    duration=max(0.0,float(duration)); motion_samples=motion_samples or []
    cuts=sorted({max(0.0,min(duration,float(x))) for x in (scene_cuts or []) if 0<float(x)<duration})
    bounds=[0.0,*cuts,duration] if duration>0 else []
    rows=[]
    for i,(start,end) in enumerate(zip(bounds,bounds[1:]),start=1):
        if end-start < 0.02: continue
        silent=0.0
        for s in silences or []:
            try: a=float(s["start"]); b=float(s["end"])
            except (KeyError,TypeError,ValueError): continue
            silent += max(0.0,min(end,b)-max(start,a))
        peak_rows=[]
        for p in audio_peaks or []:
            try: t=float(p["time"])
            except (KeyError,TypeError,ValueError): continue
            if start <= t < end: peak_rows.append(p)
        motion_rows=[]
        for m in motion_samples:
            try: t=float(m["time"]); score=float(m.get("motion_score",0.0))
            except (KeyError,TypeError,ValueError): continue
            if start <= t < end: motion_rows.append(max(0.0,min(1.0,score)))
        span=end-start; silence_ratio=max(0.0,min(1.0,silent/span if span else 0.0)) if audio_present else 0.0
        peak_score=0.0
        if peak_rows:
            strongest=max(float(x.get("peak_db",-90.0)) for x in peak_rows)
            peak_score=max(0.0,min(1.0,(strongest+45.0)/45.0))
        audio_activity=(max(0.0,min(1.0,0.65*(1.0-silence_ratio)+0.35*peak_score))
                        if audio_present else 0.0)
        motion_score=float(statistics.median(motion_rows)) if motion_rows else 0.0
        scene_change=1.0 if i>1 else 0.0
        importance=max(0.0,min(1.0,0.45*audio_activity+0.45*motion_score+0.10*scene_change))
        activity=max(0.0,min(1.0,0.55*audio_activity+0.45*motion_score))
        motion_guard=(motion_score <= 0.18) if motion_samples else True
        legacy_dead_air=bool(audio_present and silence_ratio>=0.80 and span>=0.70)
        rows.append({
            "id":f"scene-{i:03d}","start":round(start,4),"end":round(end,4),
            "duration":round(span,4),"silence_ratio":round(silence_ratio,4),
            "audio_peak_count":len(peak_rows),"audio_activity_score":round(audio_activity,4),
            "motion_sample_count":len(motion_rows),"motion_score":round(motion_score,4),
            "scene_change":bool(scene_change),"activity_score":round(activity,4),
            "importance_score":round(importance,4),
            "dead_air":legacy_dead_air,
            "smart_dead_air":bool(legacy_dead_air and motion_guard),
        })
    return rows


def rank_multisignal_highlights(structure: list[dict], *, max_results: int = 12,
                                min_score: float = 0.25) -> list[dict]:
    """Rank highlight windows only from explicit local evidence and penalize single-signal spikes."""
    ranked=[]
    for item in structure or []:
        if not isinstance(item,dict) or item.get("smart_dead_air"):
            continue
        try:
            start=float(item["start"]); end=float(item["end"])
            audio=max(0.0,min(1.0,float(item.get("audio_activity_score",0.0))))
            motion=max(0.0,min(1.0,float(item.get("motion_score",0.0))))
        except (KeyError,TypeError,ValueError):
            continue
        if end <= start: continue
        scene=1.0 if item.get("scene_change") else 0.0
        signals=[]
        if audio >= 0.35: signals.append("audio")
        if motion >= 0.25: signals.append("motion")
        if scene: signals.append("scene_change")
        score=0.42*audio+0.48*motion+0.10*scene
        if len(signals) < 2:
            score *= 0.55
        score=max(0.0,min(1.0,score))
        if score < float(min_score):
            continue
        confidence="high" if score>=0.65 and len(signals)>=2 else ("medium" if score>=0.40 else "low")
        ranked.append({
            "id":item.get("id"),"start":round(start,4),"end":round(end,4),
            "score":round(score,4),"confidence":confidence,"evidence":signals,
            "audio_activity_score":round(audio,4),"motion_score":round(motion,4),
            "scene_change":bool(scene),"signal_count":len(signals),
        })
    return sorted(ranked,key=lambda x:(-x["score"],x["start"]))[:max(0,int(max_results))]


def select_important_segments(structure: list[dict], *, max_segments: int = 12,
                              min_score: float = 0.30) -> list[dict]:
    """Rank generic structural segments without claiming semantic meaning."""
    rows=[]
    for item in structure or []:
        try: score=float(item.get("importance_score",0.0)); start=float(item["start"]); end=float(item["end"])
        except (KeyError,TypeError,ValueError): continue
        if score < float(min_score) or end <= start: continue
        rows.append({"id":item.get("id"),"start":round(start,4),"end":round(end,4),
                     "score":round(score,4),"motion_score":float(item.get("motion_score",0.0)),
                     "audio_activity_score":float(item.get("audio_activity_score",0.0))})
    return sorted(rows,key=lambda x:(-x["score"],x["start"]))[:max(0,int(max_segments))]



def build_visual_probe_plan(structure: list[dict], scene_cuts: list[float], *, duration: float,
                            max_frames: int = 24, min_spacing: float = 0.75) -> list[dict]:
    """Select a small deterministic set of visually useful timestamps.

    This is intentionally a *sampling planner*, not semantic recognition.  It lets a
    later local vision model inspect tens of frames instead of decoding every frame.
    High-importance scene midpoints are preferred, then scene-cut neighborhoods, with
    a spacing guard to avoid near-duplicates.
    """
    duration=max(0.0,float(duration)); limit=max(0,int(max_frames)); spacing=max(0.0,float(min_spacing))
    if duration <= 0 or limit == 0: return []
    candidates=[]
    for row in structure or []:
        try:
            a=float(row['start']); b=float(row['end']); score=float(row.get('importance_score',0.0))
        except (KeyError,TypeError,ValueError): continue
        if b <= a: continue
        candidates.append((max(0.0,min(duration,(a+b)/2.0)),score,'scene_midpoint',row.get('id')))
    for cut in scene_cuts or []:
        try: t=float(cut)
        except (TypeError,ValueError): continue
        if 0 <= t <= duration: candidates.append((t,0.55,'scene_cut',None))
    # Always retain broad temporal coverage, even for quiet/static footage.
    for frac in (0.10,0.50,0.90): candidates.append((duration*frac,0.20,'coverage',None))
    chosen=[]
    for t,score,reason,scene_id in sorted(candidates,key=lambda x:(-x[1],x[0],x[2])):
        if any(abs(t-x['time']) < spacing for x in chosen): continue
        chosen.append({'time':round(t,4),'priority':round(max(0.0,min(1.0,score)),4),
                       'reason':reason,'scene_id':scene_id})
        if len(chosen) >= limit: break
    return sorted(chosen,key=lambda x:x['time'])


def extract_visual_evidence_frames(source: Path, probe_plan: list[dict], output_dir: Path, *,
                                   width: int = 384, timeout_per_frame: float = 20.0,
                                   max_workers: int = 3) -> list[dict]:
    """Materialize a bounded visual evidence pack with FFmpeg and content hashes.

    Run 60 extracts independent sparse probes concurrently (bounded to four workers)
    and publishes each JPEG atomically.  Sparse seeking benefits from independent
    FFmpeg seeks while the bound avoids spawning one decoder per planned frame.
    Result ordering remains identical to ``probe_plan`` for deterministic callers.
    """
    source=Path(source); output_dir=Path(output_dir); output_dir.mkdir(parents=True,exist_ok=True)
    jobs=[]
    for idx,item in enumerate(probe_plan or [],start=1):
        try: t=max(0.0,float(item['time']))
        except (KeyError,TypeError,ValueError): continue
        jobs.append((idx,dict(item),t))
    if not jobs: return []
    width=max(64,int(width)); workers=max(1,min(4,int(max_workers),len(jobs)))

    def extract_one(job):
        idx,item,t=job
        dest=output_dir / f'probe-{idx:03d}-{int(round(t*1000)):010d}.jpg'
        tmp=output_dir / f'.{dest.name}.{uuid.uuid4().hex}.tmp.jpg'
        cmd=['ffmpeg','-y','-hide_banner','-loglevel','error','-ss',f'{t:.4f}','-i',str(source),
             '-frames:v','1','-vf',f'scale={width}:-2:flags=area','-q:v','3',str(tmp)]
        try:
            proc=subprocess.run(cmd,capture_output=True,text=True,timeout=float(timeout_per_frame))
        except subprocess.TimeoutExpired:
            try: tmp.unlink(missing_ok=True)
            except OSError: pass
            return {**item,'ok':False,'error':'FRAME_EXTRACT_TIMEOUT'}
        if proc.returncode != 0 or not tmp.exists() or tmp.stat().st_size <= 0:
            try: tmp.unlink(missing_ok=True)
            except OSError: pass
            return {**item,'ok':False,'error':'FRAME_EXTRACT_FAILED'}
        os.replace(tmp,dest)
        payload=dest.read_bytes(); digest=hashlib.sha256(payload).hexdigest()
        return {**item,'ok':True,'path':str(dest),'sha256':digest,'bytes':len(payload)}

    if workers == 1:
        return [extract_one(job) for job in jobs]
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers,thread_name_prefix='zc-vision-probe') as pool:
        return list(pool.map(extract_one,jobs))


def validate_semantic_observations(evidence_rows: list[dict], observations: list[dict], *,
                                   confidence_threshold: float = 0.62) -> list[dict]:
    """Fail-closed semantic observations tied to hashed evidence frames.

    A future local Vision backend may emit labels, but ZeroCut only accepts results
    for evidence hashes it actually produced. Low-confidence or malformed results are
    converted to UNKNOWN instead of being promoted into editing decisions.
    """
    allowed={str(x.get("sha256")):x for x in (evidence_rows or []) if x.get("ok") and x.get("sha256")}
    threshold=max(0.0,min(1.0,float(confidence_threshold))); out=[]
    for raw in observations or []:
        digest=str(raw.get("sha256") or "")
        if digest not in allowed: continue
        try: confidence=max(0.0,min(1.0,float(raw.get("confidence",0.0))))
        except (TypeError,ValueError): confidence=0.0
        label=str(raw.get("label") or "").strip().lower()
        valid=bool(label and label not in {"unknown","none","null"} and confidence>=threshold)
        ev=allowed[digest]
        out.append({"time":round(float(ev.get("time",0.0)),4),"sha256":digest,
                    "label":label if valid else "unknown","confidence":round(confidence,4),
                    "accepted":valid,"threshold":round(threshold,4),
                    "source":str(raw.get("source") or "local_vision")})
    return sorted(out,key=lambda x:(x["time"],x["sha256"]))


def build_semantic_consensus(observations: list[dict], *, window_seconds: float = 3.0,
                             min_support: int = 2, high_confidence: float = 0.94) -> list[dict]:
    """Promote semantic labels only when independent nearby frames agree.

    One exceptionally confident observation may pass; otherwise at least ``min_support``
    accepted, distinct evidence hashes with the same label are required inside the
    temporal window. This reduces one-frame false positives before semantics can steer
    editing.
    """
    rows=[dict(x) for x in (observations or []) if x.get("accepted") and x.get("label") not in {None,"unknown"}]
    rows.sort(key=lambda x:(float(x.get("time",0.0)),str(x.get("sha256",''))))
    window=max(0.0,float(window_seconds)); need=max(1,int(min_support)); hi=max(0.0,min(1.0,float(high_confidence)))
    out=[]
    for row in rows:
        t=float(row.get("time",0.0)); label=str(row.get("label") or "unknown"); conf=float(row.get("confidence",0.0))
        peers=[x for x in rows if str(x.get("label"))==label and abs(float(x.get("time",0.0))-t)<=window]
        hashes={str(x.get("sha256") or "") for x in peers if x.get("sha256")}
        support=len(hashes); consensus=bool(conf>=hi or support>=need)
        item=dict(row); item["consensus_accepted"]=consensus; item["consensus_support"]=support
        item["consensus_window_seconds"]=round(window,4); item["high_confidence_override"]=bool(conf>=hi)
        out.append(item)
    return out


def attach_transcript_to_structure(structure: list[dict], transcript_segments: list[dict] | None) -> list[dict]:
    """Fuse timestamped local-ASR text into structural timeline segments.

    This function makes no semantic guesses. It only clips verified transcript
    intervals to each structural segment and exposes speech coverage/text for
    later Director or specialist logic. Inputs are never mutated.
    """
    transcript=[]
    for raw in transcript_segments or []:
        if not isinstance(raw,dict):
            continue
        text=str(raw.get("text") or "").strip()
        try:
            a=float(raw.get("start")); b=float(raw.get("end"))
        except (TypeError,ValueError):
            continue
        if not text or b <= a:
            continue
        transcript.append({**dict(raw),"start":a,"end":b,"text":text})
    transcript.sort(key=lambda x:(x["start"],x["end"],str(x.get("id") or "")))
    out=[]
    for row in structure or []:
        if not isinstance(row,dict):
            continue
        item=dict(row)
        try:
            start=float(item["start"]); end=float(item["end"])
        except (KeyError,TypeError,ValueError):
            continue
        if end <= start:
            continue
        hits=[]; intervals=[]; word_count=0
        for seg in transcript:
            overlap_start=max(start,float(seg["start"])); overlap_end=min(end,float(seg["end"]))
            if overlap_end <= overlap_start:
                continue
            clipped={"id":str(seg.get("id") or ""),"start":round(overlap_start,4),
                     "end":round(overlap_end,4),"text":seg["text"]}
            if isinstance(seg.get("words"),list):
                words=[]
                for word in seg["words"]:
                    if not isinstance(word,dict):
                        continue
                    try: wa=float(word.get("start")); wb=float(word.get("end"))
                    except (TypeError,ValueError):
                        continue
                    if wb <= overlap_start or wa >= overlap_end:
                        continue
                    wt=str(word.get("text") or "").strip()
                    if wt:
                        words.append({"text":wt,"start":round(max(overlap_start,wa),4),
                                      "end":round(min(overlap_end,wb),4)})
                if words:
                    clipped["words"]=words; word_count += len(words)
            else:
                word_count += len(re.findall(r"\b\w+\b",seg["text"],flags=re.UNICODE))
            hits.append(clipped); intervals.append((overlap_start,overlap_end))
        merged=[]
        for a,b in sorted(intervals):
            if merged and a <= merged[-1][1] + 1e-6:
                merged[-1][1]=max(merged[-1][1],b)
            else:
                merged.append([a,b])
        speech_seconds=sum(b-a for a,b in merged)
        span=end-start
        item["transcript_segments"]=hits
        item["transcript_segment_count"]=len(hits)
        item["transcript_text"]=" ".join(x["text"] for x in hits).strip()
        item["transcript_word_count"]=word_count
        item["speech_seconds"]=round(speech_seconds,4)
        item["speech_coverage_ratio"]=round(max(0.0,min(1.0,speech_seconds/span if span else 0.0)),4)
        item["speech_understanding"]=bool(hits)
        out.append(item)
    return out


def build_semantic_timeline(structure: list[dict], semantic_observations: list[dict],
                            transcript_segments: list[dict] | None = None) -> list[dict]:
    """Fuse structural, accepted Vision evidence, and timestamped transcript data.

    Vision semantics remain fail-closed; transcript attachment is purely temporal
    and does not promote visual labels or specialist routing by itself.
    """
    out=[]
    base_rows=attach_transcript_to_structure(structure,transcript_segments) if transcript_segments is not None else [dict(x) for x in (structure or []) if isinstance(x,dict)]
    for row in base_rows:
        item=dict(row)
        try: a=float(item["start"]); b=float(item["end"])
        except (KeyError,TypeError,ValueError): continue
        hits=[x for x in (semantic_observations or [])
              if x.get("accepted") and x.get("consensus_accepted", True)
              and a <= float(x.get("time",-1)) < b]
        labels={}
        for hit in hits:
            label=str(hit.get("label") or "unknown")
            labels[label]=max(labels.get(label,0.0),float(hit.get("confidence",0.0)))
        ranked=sorted(({"label":k,"confidence":round(v,4)} for k,v in labels.items()),key=lambda x:(-x["confidence"],x["label"]))
        item["semantic_labels"]=ranked
        item["semantic_evidence_count"]=len(hits)
        item["semantic_understanding"]=bool(ranked)
        # Run 57: semantics may be useful for review after a high-confidence
        # single-frame override, but must not steer edits/routing unless the
        # label has genuine temporal support from >=2 distinct evidence frames.
        actionable=[]
        for label_row in ranked:
            label=label_row["label"]
            label_hits=[h for h in hits if str(h.get("label") or "unknown")==label]
            hashes={str(h.get("sha256") or "") for h in label_hits if h.get("sha256")}
            supports=[int(h.get("consensus_support",1) or 1) for h in label_hits]
            support=max([len(hashes),*supports]) if label_hits else 0
            if support >= 2:
                actionable.append({**label_row,"support":support})
        item["actionable_semantic_labels"]=actionable
        item["semantic_actionable"]=bool(actionable)
        out.append(item)
    return out


def route_actionable_semantics(semantic_timeline: list[dict], *, min_coverage: float = 0.12) -> dict:
    """Fail-closed specialist routing with temporal-coverage evidence.

    Temporally corroborated labels are necessary but no longer sufficient: a specialist
    must also cover a meaningful share of the analyzed timeline. This prevents a brief
    chessboard/car/menu insert from hijacking an otherwise unrelated video. Routing is
    advisory and never commits edits.
    """
    skill_map={
        "gameplay":"gaming", "rainbow six siege":"r6", "rainbow six siege x":"r6", "r6":"r6",
        "chessboard":"chess", "chess":"chess", "car":"automotive", "automobile":"automotive",
        "vehicle":"automotive", "talking head":"talking_head", "person speaking":"talking_head",
        "tutorial":"tutorial",
    }
    rows=[x for x in (semantic_timeline or []) if isinstance(x,dict)]
    starts=[]; ends=[]
    for seg in rows:
        try:
            starts.append(float(seg.get("start",0.0))); ends.append(float(seg.get("end",0.0)))
        except (TypeError,ValueError): pass
    total=max(0.0,(max(ends)-min(starts))) if starts and ends else 0.0
    votes={}; covered={}; evidence={}
    for segment in rows:
        if not segment.get("semantic_actionable"): continue
        try: duration=max(0.0,float(segment.get("end",0.0))-float(segment.get("start",0.0)))
        except (TypeError,ValueError): duration=0.0
        for row in segment.get("actionable_semantic_labels") or []:
            label=str(row.get("label") or "").strip().lower(); skill=skill_map.get(label)
            if not skill: continue
            support=max(0,int(row.get("support",0) or 0))
            confidence=max(0.0,min(1.0,float(row.get("confidence",0.0) or 0.0)))
            # Duration matters when real timeline bounds exist; retain legacy behavior for
            # synthetic/older callers without start/end fields.
            temporal_weight=duration if duration>0 else 1.0
            weight=support*confidence*temporal_weight
            votes[skill]=votes.get(skill,0.0)+weight
            covered[skill]=covered.get(skill,0.0)+duration
            evidence.setdefault(skill,[]).append({"label":label,"support":support,"confidence":round(confidence,4),
                                                  "segment_id":segment.get("id"),"duration":round(duration,4)})
    if not votes:
        return {"skill":"generic","actionable":False,"reason":"no_temporally_corroborated_known_semantics","scores":{},"coverage":{},"evidence":[]}
    ranked=sorted(votes.items(),key=lambda x:(-x[1],x[0])); best,best_score=ranked[0]
    coverage={k:round((covered.get(k,0.0)/total) if total>0 else 1.0,4) for k,_ in ranked}
    floor=max(0.0,min(1.0,float(min_coverage)))
    if total>0 and coverage.get(best,0.0)<floor:
        return {"skill":"generic","actionable":False,"reason":"insufficient_timeline_coverage",
                "scores":{k:round(v,4) for k,v in ranked},"coverage":coverage,"evidence":evidence.get(best,[])}
    ambiguous=len(ranked)>1 and abs(best_score-ranked[1][1]) < max(0.15,best_score*0.08)
    if ambiguous:
        return {"skill":"generic","actionable":False,"reason":"ambiguous_specialist_evidence",
                "scores":{k:round(v,4) for k,v in ranked},"coverage":coverage,"evidence":[]}
    return {"skill":best,"actionable":True,"reason":"temporal_consensus_with_coverage",
            "scores":{k:round(v,4) for k,v in ranked},"coverage":coverage,"evidence":evidence.get(best,[])}

def analyze_universal_media(source: Path, *, duration: float | None = None, has_audio: bool | None = None,
                            scene_threshold: float = 0.30, silence_db: float = -38.0,
                            min_silence: float = 0.70, motion_fps: float = 4.0,
                            timeout: float = 300.0) -> dict:
    """Local multi-signal structural understanding for arbitrary imported videos.

    The analyzer intentionally stays below semantic claims: it fuses scene boundaries,
    sustained silence, adaptive audio energy and visual frame-difference motion. Higher
    level skills (R6, chess, vlog, tutorial, etc.) can consume the resulting timeline.
    """
    source=Path(source)
    meta=ffprobe(source)
    media_duration=float(duration if duration is not None else meta.get("duration") or 0.0)
    audio_present=bool((meta.get("audio") or {}).get("codec")) if has_audio is None else bool(has_audio)
    scene_cuts=detect_scene_cuts(source,threshold=scene_threshold,timeout=timeout)
    silences=[]; samples=[]; adaptive=[]
    if audio_present:
        silences=detect_silences(source,duration=media_duration,noise_db=silence_db,min_silence=min_silence,timeout=timeout)
        samples=detect_audio_peaks(source,min_db=-60.0,window_seconds=0.20,timeout=timeout)
        adaptive=select_adaptive_audio_peaks(samples,percentile=0.88,floor_db=-35.0,ceiling_db=-3.0)
    motion_error=None; raw_motion=[]; motion=[]; motion_reference=0.0
    try:
        raw_motion=detect_motion_samples(source,sample_fps=motion_fps,analysis_width=320,timeout=timeout)
        motion,motion_reference=normalize_motion_samples(raw_motion)
    except (RuntimeError,subprocess.TimeoutExpired) as exc:
        motion_error=str(exc)
    smart_dead_air_ranges=motion_aware_dead_air_ranges(silences,motion) if motion else [dict(x) for x in silences]
    audio_highlights=score_highlight_candidates(scene_cuts,adaptive) if adaptive else []
    structure=build_universal_structure(media_duration,scene_cuts,silences,adaptive,motion,audio_present=audio_present)
    important=select_important_segments(structure)
    multisignal_highlights=rank_multisignal_highlights(structure)
    visual_probe_plan=build_visual_probe_plan(structure,scene_cuts,duration=media_duration)
    # Preserve Run 51's public audio-only preview for compatibility; expose the
    # safer multi-signal preview separately so callers can opt in deliberately.
    keep=keep_segments_from_silences(media_duration,silences,min_remove=min_silence)
    removed=max(0.0,media_duration-sum(max(0.0,x["end"]-x["start"]) for x in keep))
    smart_keep=keep_segments_from_silences(media_duration,smart_dead_air_ranges,min_remove=min_silence)
    smart_removed=max(0.0,media_duration-sum(max(0.0,x["end"]-x["start"]) for x in smart_keep))
    limitations=["NO_OBJECT_OR_ACTION_RECOGNITION"]
    if motion_error: limitations.append("MOTION_SCAN_UNAVAILABLE")
    return {
        "schema":"zerocut.universal-analysis.v1","analysis_version":2,
        "source":"ffmpeg_local_multisignal_analysis",
        "duration":round(media_duration,4),"has_audio":audio_present,
        "scene_cuts":scene_cuts,"scene_count":len(structure),"silences":silences,
        "dead_air_ranges":[dict(x) for x in silences],"dead_air_preview_segments":keep,
        "dead_air_removed_seconds":round(removed,4),
        "smart_dead_air_ranges":smart_dead_air_ranges,
        "smart_dead_air_preview_segments":smart_keep,
        "smart_dead_air_removed_seconds":round(smart_removed,4),
        "audio_activity_peaks":adaptive,"audio_highlight_candidates":audio_highlights,
        "highlight_candidates":multisignal_highlights,
        "motion":{"available":bool(motion),"sample_fps":round(float(motion_fps),3),
                  "reference_yavg":motion_reference,"samples":motion,
                  "active_ranges":motion_activity_ranges(motion),"error":motion_error},
        "important_segments":important,"structure":structure,
        "visual_probe_plan":visual_probe_plan,
        "visual_probe_budget":{"planned_frames":len(visual_probe_plan),"max_frames":24,"semantic_inference_run":False},
        "transcript":{"available":bool(discover_whisper().get("available")),"generated":False,
                      "reason":"ANALYSIS_V2_DOES_NOT_AUTO_TRANSCRIBE"},
        "semantic_understanding":False,
        "limitations":limitations,
    }


def analyze_universal_media_with_local_transcript(source: Path, *, language: str = "auto",
                                                   transcript_timeout: float = 1800.0,
                                                   **analysis_kwargs) -> dict:
    """Run Universal Analyzer and enrich it with real local whisper.cpp output when available.

    Structural analysis is always retained. Missing/failing ASR is an explicit
    degraded state; there is no cloud fallback and no fabricated transcript.
    """
    analysis=analyze_universal_media(source,**analysis_kwargs)
    asr=transcribe_media_whisper(Path(source),language=language,timeout=transcript_timeout)
    if not asr.get("ok"):
        analysis["transcript"]={"available":bool(discover_whisper().get("available")),"generated":False,
                                "reason":asr.get("reason","WHISPER_NOT_AVAILABLE"),
                                "executed":bool(asr.get("executed"))}
        analysis["speech_understanding"]=False
        return analysis
    transcript_segments=list(asr.get("segments") or [])
    analysis["structure"]=attach_transcript_to_structure(analysis.get("structure") or [],transcript_segments)
    analysis["transcript"]={"available":True,"generated":True,"reason":"OK","executed":True,
                            "cache_hit":bool(asr.get("cache_hit")),"language":asr.get("language"),
                            "segment_count":len(transcript_segments),"text":str(asr.get("text") or ""),
                            "segments":transcript_segments}
    analysis["speech_understanding"]=bool(transcript_segments)
    return analysis


def cached_universal_analysis(media: dict, *, force: bool = False) -> tuple[dict, bool]:
    """Analyze current media once per content hash and persist the multi-signal map."""
    if not isinstance(media,dict) or not media:
        raise ValueError("MEDIA_NOT_LOADED")
    identity=str(media.get("content_sha256") or media.get("content_hash") or media.get("id") or "")
    if not identity:
        raise ValueError("MEDIA_IDENTITY_MISSING")
    key=hashlib.sha256(f"{identity}:universal-analysis-v2".encode()).hexdigest()[:24]
    cache_path=PROJECT / "cache" / f"universal-{key}.json"
    if not force and cache_path.exists():
        try:
            data=json.loads(cache_path.read_text(encoding="utf-8"))
            if (isinstance(data,dict) and data.get("schema")=="zerocut.universal-analysis.v1"
                    and int(data.get("analysis_version") or 0)==2):
                return data,True
        except (OSError,json.JSONDecodeError,ValueError,TypeError):
            pass
    source_rel=media.get("proxy_rel") or media.get("original_rel")
    if not source_rel:
        raise ValueError("MEDIA_SOURCE_MISSING")
    source=resolve_project_file(source_rel)
    meta=media.get("proxy_metadata") if media.get("proxy_rel") else media.get("metadata")
    meta=meta or ffprobe(source)
    analysis=analyze_universal_media(source,duration=(media.get("metadata") or meta).get("duration"),
                                     has_audio=bool(((media.get("metadata") or meta).get("audio") or {}).get("codec")))
    tmp=cache_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(analysis,ensure_ascii=False,indent=2),encoding="utf-8")
    os.replace(tmp,cache_path)
    return analysis,False

def audio_peak_command(source: Path, window_seconds: float = 0.10) -> list[str]:
    """Build a local FFmpeg scan that emits timestamped audio peak metadata.

    Uses FFmpeg astats + ametadata only; no Python DSP dependency and no audio
    leaves the machine. Window size is bounded to keep highlight pre-scoring cheap.
    """
    window_seconds = max(0.02, min(1.0, float(window_seconds)))
    # Resample to a known rate so asetnsamples produces stable time windows.
    samples = max(960, int(round(48000 * window_seconds)))
    af = (f"aresample=48000,asetnsamples=n={samples}:p=0,"
          "astats=metadata=1:reset=1,"
          "ametadata=print:key=lavfi.astats.Overall.Peak_level")
    return [
        "ffmpeg", "-hide_banner", "-nostdin", "-i", str(source), "-vn",
        "-af", af, "-f", "null", "-",
    ]


def parse_audio_peak_log(stderr: str, min_db: float = -18.0) -> list[dict]:
    """Parse ametadata frames and keep loud windows at/above min_db dBFS."""
    peaks = []
    current_time = None
    for line in (stderr or "").splitlines():
        tm = re.search(r"\bpts_time:([0-9]+(?:\.[0-9]+)?)", line)
        if tm:
            current_time = float(tm.group(1))
            continue
        vm = re.search(r"lavfi\.astats\.Overall\.Peak_level=(-?(?:\d+(?:\.\d+)?|inf))", line, re.I)
        if vm and current_time is not None:
            token = vm.group(1).lower()
            db = float("-inf") if token == "-inf" else float(token)
            if db >= float(min_db):
                peaks.append({"time": round(current_time, 4), "peak_db": round(db, 3)})
            current_time = None
    return peaks


def detect_audio_peaks(source: Path, min_db: float = -18.0, window_seconds: float = 0.10,
                       timeout: float = 300.0) -> list[dict]:
    proc = subprocess.run(audio_peak_command(source, window_seconds), stdout=subprocess.DEVNULL,
                          stderr=subprocess.PIPE, text=True, timeout=timeout, check=False)
    if proc.returncode != 0:
        tail = (proc.stderr or "")[-1200:]
        raise RuntimeError(f"FFmpeg audio peak scan failed ({proc.returncode}): {tail}")
    return parse_audio_peak_log(proc.stderr, min_db)


def select_adaptive_audio_peaks(audio_samples: list[dict], *, percentile: float = 0.85,
                                floor_db: float = -30.0, ceiling_db: float = -3.0) -> list[dict]:
    """Select loud moments relative to the recording instead of a fixed dB threshold.

    Game recordings vary wildly in gain. A relative threshold keeps quiet captures usable
    while preventing a permanently loud mix from marking every window. This stays local,
    deterministic and dependency-free.
    """
    valid=[]
    for item in audio_samples:
        if not isinstance(item, dict) or "time" not in item or "peak_db" not in item:
            continue
        try:
            t=max(0.0,float(item["time"])); db=float(item["peak_db"])
        except (TypeError,ValueError):
            continue
        if db != db or db in (float("inf"),float("-inf")):
            continue
        valid.append({"time":round(t,4),"peak_db":db})
    if not valid:
        return []
    values=sorted(x["peak_db"] for x in valid)
    q=max(0.0,min(1.0,float(percentile)))
    idx=min(len(values)-1,max(0,int(round(q*(len(values)-1)))))
    threshold=max(float(floor_db),min(float(ceiling_db),values[idx]))
    return [{"time":x["time"],"peak_db":round(x["peak_db"],3)} for x in valid if x["peak_db"] >= threshold]


def score_highlight_candidates(scene_times: list[float], audio_peaks: list[dict], *,
                               match_window: float = 1.25, merge_within: float = 2.5,
                               pre_roll: float = 4.0, post_roll: float = 5.0) -> list[dict]:
    """Fuse cheap local scene/audio signals into bounded highlight candidates.

    This intentionally stays deterministic and dependency-free. Audio strength is
    normalized from dBFS, while a nearby scene boundary adds corroboration. Nearby
    detections are merged so downstream OCR/AI can inspect fewer, wider windows.
    """
    scenes = sorted({max(0.0, float(t)) for t in scene_times if float(t) >= 0.0})
    peaks = sorted(
        ({"time": max(0.0, float(p["time"])), "peak_db": float(p["peak_db"])} for p in audio_peaks
         if isinstance(p, dict) and "time" in p and "peak_db" in p),
        key=lambda p: p["time"],
    )
    match_window = max(0.05, float(match_window)); merge_within = max(0.0, float(merge_within))
    raw=[]
    for peak in peaks:
        t=peak["time"]; db=peak["peak_db"]
        nearest=min((abs(t-s) for s in scenes), default=float("inf"))
        scene_match=nearest <= match_window
        # -30 dBFS -> 0, 0 dBFS -> 1. Loudness is useful alone; scene corroboration boosts confidence.
        audio_score=max(0.0,min(1.0,(db+30.0)/30.0))
        score=min(1.0, 0.65*audio_score + (0.35 if scene_match else 0.0))
        raw.append({"time":round(t,4),"score":round(score,4),"audio_peak_db":round(db,3),
                    "scene_match":scene_match,"scene_distance":None if nearest==float("inf") else round(nearest,4)})
    merged=[]
    for item in raw:
        if merged and item["time"]-merged[-1]["last_time"] <= merge_within:
            group=merged[-1]; group["last_time"]=item["time"]; group["signals"].append(item)
            if item["score"] > group["score"]:
                group["score"]=item["score"]; group["time"]=item["time"]
        else:
            merged.append({"time":item["time"],"last_time":item["time"],"score":item["score"],"signals":[item]})
    result=[]
    for group in merged:
        start=max(0.0, group["time"]-max(0.0,float(pre_roll)))
        end=max(start, group["last_time"]+max(0.0,float(post_roll)))
        result.append({"time":round(group["time"],4),"start":round(start,4),"end":round(end,4),
                       "score":round(group["score"],4),"signal_count":len(group["signals"]),
                       "scene_correlated":any(x["scene_match"] for x in group["signals"])})
    return sorted(result,key=lambda x:(-x["score"],x["time"]))


R6_DEFAULT_ROIS = {
    # Normalized x/y/w/h boxes. Kept as configurable presets rather than claiming
    # pixel-perfect support across every R6 HUD revision/resolution.
    "kill_feed": (0.70, 0.03, 0.29, 0.30),
    "round_status": (0.30, 0.00, 0.40, 0.18),
}


def normalized_roi_to_pixels(width: int, height: int, roi: tuple[float, float, float, float]) -> tuple[int, int, int, int]:
    """Convert a bounded normalized ROI to an FFmpeg-safe even-pixel crop."""
    if width < 2 or height < 2 or len(roi) != 4:
        raise ValueError("invalid frame size or ROI")
    x, y, w, h = (float(v) for v in roi)
    if not (0 <= x < 1 and 0 <= y < 1 and w > 0 and h > 0 and x + w <= 1.000001 and y + h <= 1.000001):
        raise ValueError("ROI must be normalized inside the frame")
    px = min(width - 2, max(0, int(x * width)))
    py = min(height - 2, max(0, int(y * height)))
    pw = min(width - px, max(2, int(w * width)))
    ph = min(height - py, max(2, int(h * height)))
    # yuv420-friendly dimensions and coordinates; avoid zero after rounding.
    px -= px % 2; py -= py % 2; pw -= pw % 2; ph -= ph % 2
    return px, py, max(2, pw), max(2, ph)


def roi_frame_command(source: Path, at_seconds: float, roi_px: tuple[int, int, int, int], output: Path) -> list[str]:
    """Extract one small lossless ROI frame for optional downstream OCR."""
    x, y, w, h = roi_px
    return ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-ss", f"{max(0.0,float(at_seconds)):.3f}",
            "-i", str(source), "-frames:v", "1", "-vf", f"crop={w}:{h}:{x}:{y}", "-an", str(output)]


def extract_candidate_roi_frames(source: Path, candidates: list[dict], output_dir: Path, *,
                                 roi: tuple[float, float, float, float] = R6_DEFAULT_ROIS["kill_feed"],
                                 width: int, height: int, max_frames: int = 12, timeout: float = 20.0) -> list[dict]:
    """Bound OCR work to ranked highlight candidates; does not require an OCR dependency."""
    output_dir.mkdir(parents=True, exist_ok=True)
    crop = normalized_roi_to_pixels(width, height, roi)
    chosen = sorted((c for c in candidates if isinstance(c, dict) and "time" in c),
                    key=lambda c: (-float(c.get("score", 0)), float(c["time"])))[:max(0, int(max_frames))]
    out=[]
    for i, candidate in enumerate(chosen):
        target = output_dir / f"r6-roi-{i:03d}-{float(candidate['time']):.3f}.png"
        proc = subprocess.run(roi_frame_command(source, float(candidate["time"]), crop, target),
                              stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, timeout=timeout)
        if proc.returncode == 0 and target.exists() and target.stat().st_size > 0:
            out.append({"time": round(float(candidate["time"]), 4), "score": float(candidate.get("score", 0)),
                        "path": str(target), "crop": crop})
    return out


def _ensure_optional_python_path() -> Path | None:
    """Expose ZeroCut-local optional Python packages without requiring a global install."""
    vendor = ROOT / "tools" / "python"
    if vendor.exists():
        value = str(vendor.resolve())
        if value not in sys.path:
            sys.path.insert(0, value)
        return vendor
    return None


def discover_rapidocr() -> dict:
    """Probe the exact RapidOCR stack ZeroCut intends to use: RapidOCR + ONNX Runtime.

    Since RapidOCR >= 2.0.6 no longer bundles ONNX Runtime, package presence alone
    is not an executable OCR capability. ZeroCut therefore requires a working
    RapidOCR public API *and* ONNX Runtime providers before advertising OCR.
    """
    import importlib
    import importlib.util
    vendor = _ensure_optional_python_path()
    spec = importlib.util.find_spec("rapidocr")
    if spec is None:
        return {"available": False, "engine": "rapidocr", "reason": "PACKAGE_NOT_INSTALLED",
                "directml": False, "providers": [], "vendor_path": str(vendor) if vendor else None}
    try:
        module = importlib.import_module("rapidocr")
    except Exception as exc:
        return {"available": False, "engine": "rapidocr", "reason": "IMPORT_FAILED",
                "detail": f"{type(exc).__name__}: {exc}", "directml": False, "providers": []}
    api = getattr(module, "RapidOCR", None)
    if not callable(api):
        return {"available": False, "engine": "rapidocr", "reason": "API_NOT_FOUND",
                "directml": False, "providers": []}

    if importlib.util.find_spec("onnxruntime") is None:
        return {"available": False, "engine": "rapidocr", "reason": "ONNXRUNTIME_NOT_INSTALLED",
                "directml": False, "providers": []}
    try:
        ort = importlib.import_module("onnxruntime")
        getter = getattr(ort, "get_available_providers", None)
        providers = list(getter()) if callable(getter) else []
    except Exception as exc:
        return {"available": False, "engine": "rapidocr", "reason": "ONNXRUNTIME_IMPORT_FAILED",
                "detail": f"{type(exc).__name__}: {exc}", "directml": False, "providers": []}
    if not providers:
        return {"available": False, "engine": "rapidocr", "reason": "NO_EXECUTION_PROVIDER",
                "directml": False, "providers": []}
    return {"available": True, "engine": "rapidocr", "reason": "OK",
            "version": getattr(module, "__version__", None),
            "onnxruntime_version": getattr(ort, "__version__", None),
            "directml": "DmlExecutionProvider" in providers, "providers": providers,
            "vendor_path": str(vendor) if vendor else None,
            "module_file": str(getattr(module, "__file__", "") or "") or None,
            "onnxruntime_file": str(getattr(ort, "__file__", "") or "") or None}


_RAPIDOCR_CERT_CACHE: dict[tuple, dict] = {}
_RAPIDOCR_ENGINE_CACHE: dict[tuple, object] = {}

def rapidocr_inference_selftest(timeout_hint: float = 30.0) -> dict:
    """Construct RapidOCR and OCR a locally generated image; no network input is used."""
    cap = discover_rapidocr()
    if not cap["available"]:
        return {"executed": False, "passed": False, "reason": cap["reason"],
                "providers": cap.get("providers", [])}
    try:
        from PIL import Image, ImageDraw, ImageFont
        from rapidocr import RapidOCR
        with tempfile.TemporaryDirectory(prefix="zerocut-ocr-") as td:
            image_path = Path(td) / "ocr-selftest.png"
            img = Image.new("RGB", (900, 220), "white")
            draw = ImageDraw.Draw(img)
            font = None
            for fp in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                       "C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/arial.ttf"):
                try:
                    if Path(fp).exists():
                        font = ImageFont.truetype(fp, 64)
                        break
                except OSError:
                    pass
            if font is None:
                font = ImageFont.load_default()
            draw.text((35, 70), "ZEROCUT 123", fill="black", font=font)
            img.save(image_path)
            started = time.monotonic()
            engine = RapidOCR()
            result = engine(str(image_path))
            elapsed = time.monotonic() - started
            # Preserve the exact engine that passed the real inference self-test.
            # This avoids loading the same ONNX models a second time on first OCR use.
            key = (cap.get("version"), cap.get("onnxruntime_version"), cap.get("module_file"),
                   cap.get("onnxruntime_file"), tuple(cap.get("providers", [])))
            _RAPIDOCR_ENGINE_CACHE[key] = engine
            texts = list(getattr(result, "txts", ()) or ())
            scores = [float(x) for x in (getattr(result, "scores", ()) or ())]
            joined = " ".join(str(x) for x in texts).upper()
            passed = bool(texts) and ("ZERO" in joined or "CUT" in joined or "123" in joined)
            return {"executed": True, "passed": passed, "reason": "OK" if passed else "NO_EXPECTED_TEXT",
                    "texts": texts[:8], "scores": scores[:8], "seconds": round(elapsed, 3),
                    "providers": cap.get("providers", [])}
    except Exception as exc:
        return {"executed": True, "passed": False, "reason": "INFERENCE_FAILED",
                "detail": f"{type(exc).__name__}: {exc}", "providers": cap.get("providers", [])}


def certify_rapidocr_inference() -> dict:
    """Certify usable OCR once per loaded runtime identity, then reuse the result.

    Import/provider discovery is necessary but insufficient: model initialization or a real
    inference can still fail.  The cache key changes with package versions/module locations,
    so replacing the local runtime naturally forces a fresh certification after restart/reload.
    """
    cap = discover_rapidocr()
    if not cap.get("available"):
        return {"certified": False, "executed": False, "reason": cap.get("reason", "UNAVAILABLE"),
                "providers": cap.get("providers", [])}
    key = (cap.get("version"), cap.get("onnxruntime_version"), cap.get("module_file"),
           cap.get("onnxruntime_file"), tuple(cap.get("providers", [])))
    cached = _RAPIDOCR_CERT_CACHE.get(key)
    if cached is not None:
        return {**cached, "cached": True}
    test = rapidocr_inference_selftest()
    result = {"certified": bool(test.get("executed") and test.get("passed")),
              "executed": bool(test.get("executed")), "reason": test.get("reason", "UNKNOWN"),
              "providers": test.get("providers", cap.get("providers", [])),
              "seconds": test.get("seconds"), "cached": False}
    if test.get("detail"):
        result["detail"] = test["detail"]
    _RAPIDOCR_CERT_CACHE[key] = result
    return dict(result)


def get_certified_rapidocr_engine():
    """Return one reusable RapidOCR engine per certified runtime identity.

    Certification remains the safety gate. Reusing the initialized engine avoids repeatedly
    loading ONNX models for every bounded R6 OCR batch. Fail closed on any construction error.
    """
    cap = discover_rapidocr()
    cert = certify_rapidocr_inference()
    if not cert.get("certified"):
        return None, cert
    key = (cap.get("version"), cap.get("onnxruntime_version"), cap.get("module_file"),
           cap.get("onnxruntime_file"), tuple(cap.get("providers", [])))
    engine = _RAPIDOCR_ENGINE_CACHE.get(key)
    if engine is not None:
        return engine, {**cert, "engine_cached": True}
    try:
        from rapidocr import RapidOCR
        engine = RapidOCR()
    except Exception as exc:
        failed = {**cert, "certified": False, "reason": "ENGINE_INIT_FAILED",
                  "detail": f"{type(exc).__name__}: {exc}", "engine_cached": False}
        return None, failed
    _RAPIDOCR_ENGINE_CACHE[key] = engine
    return engine, {**cert, "engine_cached": False}


def _file_fingerprint(path_value: str | None) -> dict | None:
    if not path_value:
        return None
    path = Path(path_value)
    if not path.exists() or not path.is_file():
        return None
    digest = hashlib.sha256()
    try:
        with path.open("rb") as fh:
            while True:
                chunk = fh.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
        return {"path": str(path), "bytes": path.stat().st_size, "sha256": digest.hexdigest()}
    except OSError:
        return {"path": str(path), "error": "READ_FAILED"}


def ai_certification_report() -> dict:
    """Produce a truthful AI runtime certificate from real inference self-tests.

    Windows certification is intentionally stricter than generic AI-core
    certification: Whisper inference, RapidOCR inference and DirectML must all
    be real PASS results on an actual Windows process.
    """
    whisper_cap = discover_whisper()
    rapid_cap = discover_rapidocr()
    whisper_test = whisper_inference_selftest()
    rapid_test = rapidocr_inference_selftest()
    is_windows = platform.system().lower() == "windows"
    core_pass = bool(whisper_test.get("passed") and rapid_test.get("passed"))
    dml_pass = bool(rapid_cap.get("directml") and rapid_test.get("passed"))
    windows_certified = bool(is_windows and core_pass and dml_pass)
    if windows_certified:
        reason = "OK"
    elif not is_windows:
        reason = "TEST_WINDOWS_REALE_NON_ESEGUITO"
    elif not core_pass:
        reason = "AI_INFERENCE_NOT_CERTIFIED"
    else:
        reason = "DIRECTML_NOT_CERTIFIED"
    return {
        "schema": 1,
        "generated_at": time.time(),
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python": sys.version.split()[0],
            "windows_real_test_executed": is_windows,
        },
        "manifest": runtime_manifest(),
        "whisper": {
            "capability": whisper_cap,
            "selftest": whisper_test,
            "binary_fingerprint": _file_fingerprint(whisper_cap.get("binary")),
            "model_fingerprint": _file_fingerprint(whisper_cap.get("model")),
        },
        "rapidocr": {
            "capability": rapid_cap,
            "selftest": rapid_test,
            "directml_certified": dml_pass,
        },
        "ai_core_certified": core_pass,
        "windows_ai_certified": windows_certified,
        "reason": reason,
    }


def write_ai_certification_report(report: dict | None = None) -> Path:
    payload = report or ai_certification_report()
    DIAGNOSTICS.mkdir(parents=True, exist_ok=True)
    target = DIAGNOSTICS / "ai-certification.json"
    tmp = target.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, target)
    return target


def classify_r6_ocr_text(text: str) -> dict:
    """Convert OCR text into conservative R6 semantic hints; never claims a kill from noise."""
    clean = re.sub(r"\s+", " ", str(text or "")).strip()
    upper = clean.upper()
    patterns = {
        "headshot": (r"\bHEAD\s*SHOT\b", r"\bHEADSHOT\b"),
        "kill": (r"\bKILL(?:ED)?\b", r"\bELIMINAT(?:ED|ION)\b"),
        "defuser": (r"\bDEFUSER\b", r"\bDEFUS(?:E|ING|ED)\b"),
        "victory": (r"\bVICTORY\b", r"\bROUND\s+WON\b"),
    }
    hits = [name for name, pats in patterns.items() if any(re.search(p, upper) for p in pats)]
    # OCR is only corroborating evidence. Confidence here describes text-pattern strength,
    # not certainty that the underlying gameplay event occurred.
    confidence = min(1.0, 0.45 + 0.15 * len(hits)) if hits else 0.0
    return {"text": clean, "signals": hits, "semantic_score": round(confidence, 3)}


def rapidocr_r6_semantic_selftest() -> dict:
    """Run real OCR against a locally generated R6-like semantic text fixture."""
    cert=certify_rapidocr_inference()
    if not cert.get("certified"):
        return {"executed":False,"passed":False,"reason":cert.get("reason","OCR_NOT_CERTIFIED"),
                "providers":cert.get("providers",[])}
    engine, engine_cert=get_certified_rapidocr_engine()
    if engine is None:
        return {"executed":False,"passed":False,"reason":engine_cert.get("reason","ENGINE_UNAVAILABLE"),
                "providers":engine_cert.get("providers",[])}
    try:
        from PIL import Image,ImageDraw,ImageFont
        with tempfile.TemporaryDirectory(prefix="zerocut-r6-ocr-") as td:
            path=Path(td)/"r6-round-won.png"
            img=Image.new("RGB",(1200,320),"black")
            draw=ImageDraw.Draw(img); font=None
            for fp in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                       "C:/Windows/Fonts/arialbd.ttf","C:/Windows/Fonts/arial.ttf"):
                try:
                    if Path(fp).exists():
                        font=ImageFont.truetype(fp,96);break
                except OSError: pass
            if font is None: font=ImageFont.load_default()
            draw.text((85,95),"ROUND WON",fill="white",font=font)
            img.save(path)
            started=time.monotonic()
            result=engine(str(path))
            elapsed=time.monotonic()-started
            texts=[str(x).strip() for x in (getattr(result,"txts",()) or ()) if str(x).strip()]
            scores=[float(x) for x in (getattr(result,"scores",()) or ())]
            joined=" ".join(texts)
            semantic=classify_r6_ocr_text(joined)
            passed="victory" in semantic.get("signals",[])
            return {"executed":True,"passed":passed,"reason":"OK" if passed else "SEMANTIC_TEXT_NOT_RECOGNIZED",
                    "texts":texts[:8],"scores":scores[:8],"semantic":semantic,
                    "seconds":round(elapsed,3),"providers":engine_cert.get("providers",[])}
    except Exception as exc:
        return {"executed":True,"passed":False,"reason":"INFERENCE_FAILED",
                "detail":f"{type(exc).__name__}: {exc}","providers":engine_cert.get("providers",[])}


def rapidocr_candidate_frames(frames: list[dict], *, min_confidence: float = 0.65) -> dict:
    """OCR only preselected ROI frames and fail closed when the optional stack is unavailable.

    One engine instance is reused for the bounded batch. Low-confidence strings are
    discarded before semantic scoring so OCR noise cannot promote a candidate.
    """
    cap = discover_rapidocr()
    if not cap.get("available"):
        return {"executed": False, "reason": cap.get("reason", "UNAVAILABLE"), "texts": {},
                "providers": cap.get("providers", [])}
    engine, engine_cert = get_certified_rapidocr_engine()
    if engine is None:
        return {"executed": False, "reason": engine_cert.get("reason", "UNAVAILABLE"), "texts": {},
                "providers": cap.get("providers", []), "certified": False}
    try:
        accepted = {}
        details = {}
        threshold = max(0.0, min(1.0, float(min_confidence)))
        for i, frame in enumerate(frames or []):
            path = Path(str(frame.get("path", "")))
            if not path.is_file() or path.stat().st_size <= 0:
                continue
            result = engine(str(path))
            txts = list(getattr(result, "txts", ()) or ())
            scores = [float(v) for v in (getattr(result, "scores", ()) or ())]
            kept = [(str(t).strip(), scores[j] if j < len(scores) else 0.0)
                    for j, t in enumerate(txts) if str(t).strip() and (scores[j] if j < len(scores) else 0.0) >= threshold]
            text = " ".join(t for t, _ in kept).strip()
            if text:
                accepted[i] = text
            details[i] = {"accepted_text": text, "accepted_count": len(kept),
                          "max_confidence": round(max((c for _, c in kept), default=0.0), 4)}
        return {"executed": True, "reason": "OK", "texts": accepted, "details": details,
                "providers": cap.get("providers", [])}
    except Exception as exc:
        # A previously certified ONNX/RapidOCR session can still become unhealthy at
        # runtime (provider reset, native runtime error, corrupt session state). Never
        # keep handing the same failed native engine back to subsequent OCR batches.
        key = (cap.get("version"), cap.get("onnxruntime_version"), cap.get("module_file"),
               cap.get("onnxruntime_file"), tuple(cap.get("providers", [])))
        _RAPIDOCR_ENGINE_CACHE.pop(key, None)
        _RAPIDOCR_CERT_CACHE.pop(key, None)
        return {"executed": True, "reason": "INFERENCE_FAILED", "texts": {},
                "detail": f"{type(exc).__name__}: {exc}", "providers": cap.get("providers", []),
                "runtime_invalidated": True}


def enrich_candidates_with_ocr(candidates: list[dict], ocr_text_by_index: dict[int, str], *, weight: float = 0.20) -> list[dict]:
    """Add optional OCR corroboration while preserving original candidate ordering semantics."""
    out=[]
    for i, candidate in enumerate(candidates):
        item=dict(candidate)
        semantic=classify_r6_ocr_text(ocr_text_by_index.get(i, ""))
        item["ocr"] = semantic
        base=float(item.get("score",0.0))
        item["score"] = round(min(1.0, base + max(0.0, min(1.0, weight))*semantic["semantic_score"]),4)
        out.append(item)
    return sorted(out, key=lambda x: (-float(x.get("score",0.0)), float(x.get("time",x.get("start",0.0)))))




def parse_r6_round_clock_text(text: str, *, max_minutes: int = 9) -> float | None:
    """Parse a conservative M:SS/MM:SS round clock from OCR text.

    Ambiguous bare integers are deliberately rejected: auto-alignment should
    prefer no result over silently anchoring a replay to HUD noise.
    """
    clean = str(text or "").strip()
    matches = re.findall(r"(?<!\d)(\d{1,2})\s*[:;.]\s*([0-5]\d)(?!\d)", clean)
    values=[]
    for minutes, seconds in matches:
        m=int(minutes); sec=int(seconds)
        if 0 <= m <= int(max_minutes):
            values.append(float(m*60+sec))
    return values[0] if len(values)==1 else None


def estimate_r6_round_start(timer_anchors: list[dict], *, round_duration: float,
                            min_anchors: int = 2, max_residual: float = 1.25) -> dict:
    """Estimate video round-start from sparse HUD clock anchors with confidence.

    Each anchor is {video_time, round_clock} or {video_time, text}.  Every valid
    anchor independently implies start = video_time - (duration-round_clock).
    Median/MAD-style rejection makes one bad OCR read unable to drag alignment.
    No sufficiently consistent anchors => no automatic alignment.
    """
    duration=float(round_duration)
    if duration <= 0:
        raise ValueError("round_duration must be positive")
    implied=[]
    for anchor in timer_anchors or []:
        if not isinstance(anchor,dict) or "video_time" not in anchor:
            continue
        try: vt=float(anchor["video_time"])
        except (TypeError,ValueError): continue
        clock=anchor.get("round_clock")
        if clock is None: clock=parse_r6_round_clock_text(anchor.get("text",""))
        try: clock=float(clock)
        except (TypeError,ValueError): continue
        if vt < 0 or clock < 0 or clock > duration: continue
        start=vt-(duration-clock)
        if start >= 0: implied.append(start)
    if len(implied) < max(1,int(min_anchors)):
        return {"aligned":False,"video_round_start":None,"confidence":0.0,
                "anchors_used":0,"anchors_total":len(implied),"reason":"INSUFFICIENT_ANCHORS"}
    ordered=sorted(implied); median=ordered[len(ordered)//2] if len(ordered)%2 else (ordered[len(ordered)//2-1]+ordered[len(ordered)//2])/2
    residual_limit=max(0.10,float(max_residual))
    inliers=[x for x in implied if abs(x-median)<=residual_limit]
    if len(inliers) < max(1,int(min_anchors)):
        return {"aligned":False,"video_round_start":None,"confidence":0.0,
                "anchors_used":len(inliers),"anchors_total":len(implied),"reason":"INCONSISTENT_ANCHORS"}
    start=sum(inliers)/len(inliers)
    mean_residual=sum(abs(x-start) for x in inliers)/len(inliers)
    coverage=min(1.0,len(inliers)/4.0)
    consistency=max(0.0,1.0-mean_residual/residual_limit)
    confidence=round(coverage*0.45+consistency*0.55,3)
    # Two perfect anchors are useful but intentionally not called high confidence.
    auto=confidence >= 0.72 and len(inliers)>=3
    return {"aligned":auto,"video_round_start":round(start,4),"confidence":confidence,
            "anchors_used":len(inliers),"anchors_total":len(implied),
            "mean_residual":round(mean_residual,4),
            "reason":"OK" if auto else "MANUAL_CONFIRMATION_RECOMMENDED"}

def estimate_r6_multi_round_starts(timer_anchors: list[dict], *, round_duration: float,
                                    min_anchors: int = 3, max_residual: float = 1.25,
                                    min_round_gap: float = 20.0) -> dict:
    """Chain multiple R6 rounds from HUD countdown anchors without guessing gaps.

    Anchors independently imply a round start. Implied starts are clustered on
    the video timeline, then each cluster is validated by the same conservative
    single-round estimator. Isolated OCR mistakes never become rounds.
    """
    duration=float(round_duration)
    if duration <= 0: raise ValueError("round_duration must be positive")
    residual=max(.10,float(max_residual)); gap=max(residual*2,float(min_round_gap))
    valid=[]
    for anchor in timer_anchors or []:
        if not isinstance(anchor,dict) or "video_time" not in anchor: continue
        try: vt=float(anchor["video_time"])
        except (TypeError,ValueError): continue
        clock=anchor.get("round_clock")
        if clock is None: clock=parse_r6_round_clock_text(anchor.get("text",""))
        try: clock=float(clock)
        except (TypeError,ValueError): continue
        if vt < 0 or not 0 <= clock <= duration: continue
        start=vt-(duration-clock)
        if start >= 0: valid.append((start,dict(anchor,round_clock=clock)))
    valid.sort(key=lambda x:x[0])
    clusters=[]
    for implied,anchor in valid:
        if not clusters or implied-clusters[-1][-1][0] > gap:
            clusters.append([])
        clusters[-1].append((implied,anchor))
    rounds=[]
    for cluster in clusters:
        if len(cluster) < max(1,int(min_anchors)): continue
        estimate=estimate_r6_round_start([a for _,a in cluster],round_duration=duration,
                                         min_anchors=min_anchors,max_residual=residual)
        if not estimate.get("aligned"): continue
        start=float(estimate["video_round_start"])
        if rounds and start-float(rounds[-1]["video_round_start"]) < gap: continue
        rounds.append({"round_index":len(rounds)+1,**estimate})
    return {"aligned":bool(rounds),"rounds":rounds,"round_count":len(rounds),
            "anchors_total":len(valid),"reason":"OK" if rounds else "NO_CONFIDENT_ROUNDS"}



def _r6_norm_text(value) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def _r6_norm_set(value) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, str):
        values=re.split(r"[,;|/]", value)
    elif isinstance(value, (list,tuple,set)):
        values=list(value)
    else:
        values=[value]
    return {token for token in (_r6_norm_text(v) for v in values) if token}


def _r6_pick(data: dict, *keys, default=None):
    for key in keys:
        if key in data and data.get(key) not in (None, "", [], {}):
            return data.get(key)
    return default


def _r6_player_names(value) -> list[str]:
    """Extract stable player names from parser/player payloads without trusting IDs."""
    if not isinstance(value, list):
        return []
    out=[]
    for item in value:
        if isinstance(item, str):
            name=item.strip()
        elif isinstance(item, dict):
            name=str(_r6_pick(item, "username", "name", "profileName", "playerName", default="") or "").strip()
        else:
            name=""
        if name and name not in out:
            out.append(name)
    return out


def _r6_site_label(value) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        description=str(_r6_pick(value, "description", "name", "site", default="") or "").strip()
        floor=str(_r6_pick(value, "floor", default="") or "").strip()
        if description and floor and floor.lower() not in description.lower():
            return f"{floor} {description}"
        return description or floor
    return ""


def score_r6_highlight_event(event: dict) -> dict:
    """Explainable, fail-closed R6 highlight confidence from proven replay evidence only.

    This scorer intentionally avoids OCR/audio/model guesses. Unknown ownership/POV
    never earns those points, so downstream fusion can safely add corroboration later.
    """
    if not isinstance(event, dict):
        return {"score": 0.0, "tier": "ignore", "reasons": []}
    kind=_r6_event_kind(event)
    if kind not in {"kill", "headshot"}:
        return {"score": 0.0, "tier": "ignore", "reasons": []}
    score=0.35
    reasons=["replay_kill"]
    if event.get("recording_player_action") is True:
        score += 0.25; reasons.append("recording_player_action")
    if event.get("recording_pov_action") is True:
        score += 0.25; reasons.append("recording_pov_confirmed")
    elif event.get("recording_pov_action") is False:
        score -= 0.15; reasons.append("recording_pov_not_visible")
    if bool(event.get("headshot")) or kind=="headshot":
        score += 0.10; reasons.append("headshot")
    if event.get("recording_player_kill_shot_correlated") is True:
        score += 0.10; reasons.append("kill_shot_correlated")
    if event.get("recording_player_trade_kill") is True:
        score += 0.05; reasons.append("trade_kill")
    score=max(0.0,min(1.0,round(score,3)))
    tier="high" if score >= 0.75 else "medium" if score >= 0.50 else "low"
    return {"score": score, "tier": tier, "reasons": reasons}


def normalize_r6_replay_round_payload(payload: dict, *, default_round_duration: float = 180.0) -> dict:
    """Normalize supported R6 replay-parser JSON shapes into ZeroCut's safe boundary.

    Supported shapes include siege-dissect-style top-level round JSON and the
    nested ``header`` shape documented by wnc-replay/replay-tool.  This adapter
    consumes JSON only; it does not execute or bundle either parser.  Ambiguous
    ``timeSecs`` semantics are interpreted only inside the parser-specific field
    that documents them: ``matchFeedback`` is countdown, ``gameEvents`` elapsed.
    """
    if not isinstance(payload, dict):
        return {}
    root=dict(payload)
    header=root.get("header") if isinstance(root.get("header"), dict) else None
    data=dict(header) if header is not None else dict(root)
    source_format="wnc-replay/replay-tool-json" if header is not None else "generic-r6-round-json"

    # replay-tool's current Y11 output keeps core round metadata in ``header`` but
    # analytical streams (gameEvents/binaryFeedback/roundDuration/bombSite/...)
    # inside a sibling ``analysis`` object. Older snapshots exposed some of these
    # directly at the root. Merge both shapes without allowing analysis data to
    # overwrite authoritative header metadata. This is JSON-only adaptation: no
    # external parser is executed or bundled here.
    if header is not None:
        analysis = root.get("analysis") if isinstance(root.get("analysis"), dict) else {}
        for key in ("bombSite", "outcome", "scoreboard", "gameEvents", "matchFeedback", "binaryFeedback",
                    "roundDuration", "recordingPlayer", "players", "teams", "hits", "trades",
                    "spectatorPeriods", "bombPlant", "defuserTicks"):
            if key in data:
                continue
            if key in analysis:
                data[key]=analysis[key]
            elif key in root:
                data[key]=root[key]

    duration=_r6_pick(data, "roundDuration", "round_duration", "duration", default=default_round_duration)
    try:
        duration=float(duration)
    except (TypeError, ValueError):
        duration=float(default_round_duration)
    if duration <= 0:
        duration=float(default_round_duration)

    players=_r6_player_names(_r6_pick(data, "players", "player_names", "playerNames", default=[]))
    if not players and isinstance(data.get("teams"), list):
        combined=[]
        for team in data["teams"]:
            if isinstance(team, dict):
                combined.extend(_r6_player_names(_r6_pick(team, "players", "members", default=[])))
        players=_r6_player_names(combined)

    events=[]; seen=set()
    def push_event(raw: dict, *, time_mode: str):
        if not isinstance(raw, dict):
            return
        item=dict(raw)
        # replay-tool documents matchFeedback.timeSecs as countdown while
        # gameEvents.timeSecs is an elapsed timeline event. Keep that distinction.
        if time_mode=="countdown":
            if item.get("timeInSeconds") is None and item.get("timeSecs") is not None:
                item["timeInSeconds"]=item.get("timeSecs")
            if item.get("timeInSeconds") is None and isinstance(item.get("time"), str):
                parsed=parse_r6_round_clock_text(item["time"])
                if parsed is not None:
                    item["timeInSeconds"]=parsed
        elif time_mode=="elapsed":
            if item.get("elapsed") is None and item.get("timeSecs") is not None:
                item["elapsed"]=item.get("timeSecs")
        elif time_mode=="round_ms":
            if item.get("elapsed") is None and item.get("roundTimeMs") is not None:
                try:
                    item["elapsed"]=float(item["roundTimeMs"])/1000.0
                except (TypeError, ValueError):
                    pass
        elapsed=_r6_event_elapsed(item, round_duration=duration)
        kind=_r6_event_kind(item)
        # Keep untimed descriptive feedback out of identity/timeline evidence.
        if elapsed is None:
            return
        actor=str(item.get("username",item.get("attacker","")) or "")
        target=str(item.get("target","") or "")
        headshot=bool(item.get("headshot",False))
        # Parser outputs can expose the same event in both matchFeedback and
        # gameEvents. Treat an unstructured duplicate as the same event only
        # when semantic kind/time/headshot agree; preserve simultaneous kills
        # when both sides carry distinct structured attacker/target identities.
        for existing in events:
            ex_elapsed=_r6_event_elapsed(existing, round_duration=duration)
            ex_kind=_r6_event_kind(existing)
            same_semantic=(ex_kind==kind or {ex_kind,kind}<={"kill","headshot"})
            if ex_elapsed is None or abs(ex_elapsed-elapsed)>.05 or not same_semantic:
                continue
            ex_actor=str(existing.get("username",existing.get("attacker","")) or "")
            ex_target=str(existing.get("target","") or "")
            ex_headshot=bool(existing.get("headshot",False))
            headshot_compatible=("headshot" not in item or "headshot" not in existing or ex_headshot==headshot)
            if headshot_compatible and ((actor==ex_actor and target==ex_target) or not actor or not ex_actor):
                return
        sig=(round(elapsed,3),kind,actor,target,headshot)
        if sig in seen:
            return
        seen.add(sig); events.append(item)

    # Top-level/generic events already follow ZeroCut semantics.
    generic_events=_r6_pick(data, "events", "feedback", default=[])
    if isinstance(generic_events, list):
        for event in generic_events:
            push_event(event, time_mode="generic")

    match_feedback=data.get("matchFeedback")
    if isinstance(match_feedback, list):
        for event in match_feedback:
            push_event(event, time_mode="countdown")

    game_events=data.get("gameEvents")
    if isinstance(game_events, list):
        for event in game_events:
            push_event(event, time_mode="elapsed")

    # Binary feedback is used only when it has an explicit roundTimeMs field.
    # A bare timeSecs in this stream is intentionally not guessed.
    binary_feedback=data.get("binaryFeedback")
    if isinstance(binary_feedback, list):
        for event in binary_feedback:
            if isinstance(event, dict) and event.get("roundTimeMs") is not None:
                push_event(event, time_mode="round_ms")

    # Resolve replay-tool's recordingPlayer index to a username only when the
    # parser gives an explicit index/name mapping. Never guess list position:
    # replay formats and parser versions can use sparse/non-zero-based indexes.
    recording_index=_r6_pick(data, "recordingPlayer", "recording_player")
    recording_name=""
    analysis_players=data.get("players") if isinstance(data.get("players"), list) else []
    if recording_index is not None:
        for player in analysis_players:
            if not isinstance(player, dict):
                continue
            idx=_r6_pick(player, "playerIndex", "player_index", "index")
            if idx is None or str(idx)!=str(recording_index):
                continue
            recording_name=str(_r6_pick(player, "username", "name", "playerName", default="") or "").strip()
            if recording_name:
                break

    # Add conservative attribution metadata. This does NOT discard other kills:
    # spectator POV periods mean a recording may legitimately show another
    # player's actions after death. Downstream highlight ranking can prefer own
    # actions only when attribution is explicitly resolved.
    if recording_name:
        recording_norm=_r6_norm_text(recording_name)
        player_names_by_index={}
        for player in analysis_players:
            if not isinstance(player, dict):
                continue
            idx=_r6_pick(player, "playerIndex", "player_index", "index")
            name=str(_r6_pick(player, "username", "name", "playerName", default="") or "").strip()
            if idx is not None and name:
                player_names_by_index[str(idx)]=name

        # replay-tool defines spectatorPeriods with exact TargetIndex/Username and
        # StartSecs/EndSecs fields. Normalize only those documented semantics;
        # malformed/unknown period shapes are ignored rather than guessed.
        spectator_periods=[]
        raw_periods=data.get("spectatorPeriods") if isinstance(data.get("spectatorPeriods"), list) else []
        for period in raw_periods:
            if not isinstance(period, dict):
                continue
            target_idx=_r6_pick(period, "targetIndex", "target_index")
            target_name=str(_r6_pick(period, "username", default="") or "").strip()
            if not target_name and target_idx is not None:
                target_name=player_names_by_index.get(str(target_idx), "")
            try:
                start=float(_r6_pick(period, "startSecs", "start_secs"))
                end=float(_r6_pick(period, "endSecs", "end_secs"))
            except (TypeError, ValueError):
                continue
            if not target_name or start < 0 or end < start:
                continue
            spectator_periods.append({"target_index":target_idx,"target_name":target_name,"start":start,"end":end})

        for event in events:
            actor=str(event.get("username",event.get("attacker",event.get("finishedBy",""))) or "").strip()
            if not actor:
                continue
            actor_norm=_r6_norm_text(actor)
            event["recording_player_action"]=actor_norm==recording_norm
            elapsed=_r6_event_elapsed(event, round_duration=duration)
            if elapsed is None:
                continue
            active=[p for p in spectator_periods if p["start"] <= elapsed <= p["end"]]
            if active:
                # During a documented spectator interval, visibility is proven
                # only when the event actor is the camera target. This also
                # prevents an own-action label from implying visible POV while
                # the recording is explicitly spectating somebody else.
                event["recording_pov_action"]=any(_r6_norm_text(p["target_name"])==actor_norm for p in active)
                event["recording_pov_source"]="spectator_period"
            elif event["recording_player_action"]:
                event["recording_pov_action"]=True
                event["recording_pov_source"]="recording_player"

    # Corroborate kill events with replay-tool derived analytics only when the
    # evidence is structurally explicit and temporally close. ``hits`` links a
    # shooter/victim to the shot/health-drop that produced a kill; ``trades``
    # identifies a trader by player index. We intentionally require the
    # recording-player index for ownership evidence and never infer identities
    # from array positions. A 0.35s window absorbs parser timestamp rounding
    # while remaining narrow enough to avoid adjacent gunfights.
    try:
        recording_index_int=int(recording_index) if recording_index is not None else None
    except (TypeError, ValueError):
        recording_index_int=None
    raw_hits=data.get("hits") if isinstance(data.get("hits"), list) else []
    raw_trades=data.get("trades") if isinstance(data.get("trades"), list) else []
    for event in events:
        if _r6_event_kind(event) not in {"kill", "headshot"}:
            continue
        elapsed=_r6_event_elapsed(event, round_duration=duration)
        if elapsed is None:
            continue
        correlated_hits=[]
        for hit in raw_hits:
            if not isinstance(hit, dict) or not bool(hit.get("isKill")):
                continue
            try:
                hit_time=float(_r6_pick(hit, "hitTimeSecs", "shotTimeSecs"))
                shooter=int(hit.get("shooterIndex"))
            except (TypeError, ValueError):
                continue
            if abs(hit_time-elapsed) <= 0.35:
                correlated_hits.append(hit)
                if recording_index_int is not None and shooter==recording_index_int:
                    event["recording_player_kill_shot_correlated"]=True
                    event["kill_shot_delta_secs"]=round(abs(hit_time-elapsed),3)
        if correlated_hits:
            event["kill_shot_correlated"]=True
        for trade in raw_trades:
            if not isinstance(trade, dict):
                continue
            try:
                trade_time=float(trade.get("traderTimeSecs"))
                trader=int(trade.get("traderIndex"))
            except (TypeError, ValueError):
                continue
            if abs(trade_time-elapsed) <= 0.35:
                event["trade_kill"]=True
                if recording_index_int is not None and trader==recording_index_int:
                    event["recording_player_trade_kill"]=True
                break

    # Attach an explainable replay-only confidence signal. This is advisory and
    # never removes events; later OCR/audio fusion can corroborate it.
    for event in events:
        confidence=score_r6_highlight_event(event)
        if confidence["score"] > 0:
            event["highlight_confidence"]=confidence

    normalized=dict(data)
    normalized.update({
        "source_format":source_format,
        "round_number":_r6_pick(data, "round_number", "roundNumber", "round_index", "round"),
        "map":_r6_pick(data, "map", "map_name", "mapName"),
        "duration":duration,
        "players":players,
        "recording_player_index":recording_index,
        "recording_player_name":recording_name or None,
        "site":_r6_site_label(_r6_pick(data, "site", "objective_site", "bomb_site", "bombSite", default="")),
        "events":sorted(events, key=lambda e: (_r6_event_elapsed(e, round_duration=duration) or 0.0, _r6_event_kind(e))),
    })
    return normalized


def _r6_events_from_round(data: dict) -> list[dict]:
    events=_r6_pick(data, "events", "feedback", "matchFeedback", "observed_events", "semantic_events", default=[])
    return [e for e in events if isinstance(e,dict)] if isinstance(events,list) else []


def _r6_event_elapsed(event: dict, *, round_duration: float, video_round_start: float | None = None) -> float | None:
    try:
        if event.get("elapsed") is not None:
            value=float(event["elapsed"])
        elif event.get("video_time") is not None and video_round_start is not None:
            value=float(event["video_time"])-float(video_round_start)
        elif event.get("timeInSeconds") is not None:
            value=float(round_duration)-float(event["timeInSeconds"])
        elif event.get("round_clock") is not None:
            value=float(round_duration)-float(event["round_clock"])
        else:
            return None
    except (TypeError,ValueError):
        return None
    return value if 0 <= value <= float(round_duration)+1.0 else None


def _r6_event_kind(event: dict) -> str:
    kind=_r6_norm_text(_r6_pick(event,"type","kind","event","name",default="other")) or "other"
    if bool(event.get("headshot")):
        return "headshot"
    if "headshot" in kind: return "headshot"
    if "kill" in kind or kind in {"death","elimination"}: return "kill"
    if "dbno" in kind or "down" in kind: return "dbno"
    if "defus" in kind or "plant" in kind: return "defuser"
    if "objective" in kind or "locate" in kind: return "objective"
    return kind


def _r6_temporal_event_similarity(video_round: dict, replay_round: dict, *, round_duration: float,
                                  tolerance: float = 4.0) -> tuple[float | None, str | None]:
    """Compare semantic event shape without trusting ordinal position.

    A headshot only helps when a matching semantic event occurs near the same
    elapsed round time.  This prevents a generic "one headshot happened" count
    from falsely identifying the wrong round.
    """
    v_events=_r6_events_from_round(video_round); r_events=_r6_events_from_round(replay_round)
    if not v_events or not r_events: return None,None
    try: start=float(video_round.get("video_round_start")) if video_round.get("video_round_start") is not None else None
    except (TypeError,ValueError): start=None
    v=[]; r=[]
    for e in v_events:
        t=_r6_event_elapsed(e,round_duration=round_duration,video_round_start=start)
        if t is not None and _r6_event_kind(e) in {"kill","headshot","dbno","defuser","objective"}: v.append((t,_r6_event_kind(e)))
    for e in r_events:
        t=_r6_event_elapsed(e,round_duration=round_duration)
        if t is not None and _r6_event_kind(e) in {"kill","headshot","dbno","defuser","objective"}: r.append((t,_r6_event_kind(e)))
    if not v or not r: return None,None
    tol=max(.25,float(tolerance)); used=set(); credit=0.0
    for vt,vk in sorted(v):
        choices=[]
        for j,(rt,rk) in enumerate(r):
            if j in used: continue
            dist=abs(vt-rt)
            if dist<=tol:
                semantic=1.0 if vk==rk else (0.45 if {vk,rk}<={"kill","headshot"} else 0.0)
                if semantic>0: choices.append((dist,-semantic,j,semantic))
        if choices:
            _,_,j,semantic=min(choices); used.add(j); credit+=semantic
    similarity=credit/max(len(v),len(r))
    return max(0.0,min(1.0,similarity)),f"temporal_events={similarity:.2f}"


def _r6_count_signature(data: dict) -> dict[str,int]:
    explicit=data.get("event_summary") if isinstance(data.get("event_summary"),dict) else {}
    if explicit:
        out={}
        for key in ("kills","headshots","dbno","defuser","objective"):
            try: out[key]=max(0,int(explicit.get(key,0)))
            except (TypeError,ValueError): out[key]=0
        return out
    out={"kills":0,"headshots":0,"dbno":0,"defuser":0,"objective":0}
    for event in _r6_events_from_round(data):
        kind=_r6_event_kind(event)
        if kind=="headshot": out["headshots"]+=1; out["kills"]+=1
        elif kind=="kill": out["kills"]+=1
        elif kind=="dbno": out["dbno"]+=1
        elif kind=="defuser": out["defuser"]+=1
        elif kind=="objective": out["objective"]+=1
    return out


def _r6_count_similarity(a: dict[str,int], b: dict[str,int]) -> float | None:
    if not any(a.values()) and not any(b.values()): return None
    keys=("kills","headshots","dbno","defuser","objective")
    sims=[]
    for key in keys:
        av=int(a.get(key,0)); bv=int(b.get(key,0))
        if av or bv: sims.append(1.0-abs(av-bv)/max(1,av,bv))
    return sum(sims)/len(sims) if sims else None


def score_r6_round_identity(video_round: dict, replay_round: dict, *, round_duration: float,
                            event_tolerance: float = 4.0) -> dict:
    """Score one VIDEO round against one REPLAY round using independent evidence.

    The score deliberately excludes plain list position. Sparse evidence is capped
    so a single matching field can never become an automatic HIGH match.
    """
    if not isinstance(video_round,dict) or not isinstance(replay_round,dict):
        return {"score":0.0,"evidence_count":0,"reasons":[],"conflicts":["invalid_round"]}
    reasons=[]; conflicts=[]; weighted=0.0; total=0.0; evidence=0; strong=0
    def add(label,sim,weight,*,strong_signal=False,hard_mismatch=False):
        nonlocal weighted,total,evidence,strong
        if sim is None: return
        sim=max(0.0,min(1.0,float(sim))); evidence+=1; total+=weight; weighted+=sim*weight
        if strong_signal: strong+=1
        reasons.append(f"{label}={sim:.2f}")
        if hard_mismatch and sim <= .01: conflicts.append(label)

    # Explicit round number is identity evidence, not list position.
    vn=_r6_pick(video_round,"round_number","roundNumber","round_index")
    rn=_r6_pick(replay_round,"round_number","roundNumber","round_index","round")
    if vn is not None and rn is not None:
        try: add("round_number",1.0 if int(vn)==int(rn) else 0.0,.24,strong_signal=True,hard_mismatch=True)
        except (TypeError,ValueError): pass

    for label,aliases,weight in (
        ("map",("map","map_name","mapName"),.09),
        ("site",("site","objective_site","bomb_site","bombSite"),.12),
        ("side",("side","role","team_role","teamRole"),.12),
    ):
        va=_r6_norm_text(_r6_pick(video_round,*aliases,default="")); ra=_r6_norm_text(_r6_pick(replay_round,*aliases,default=""))
        if va and ra: add(label,1.0 if va==ra else 0.0,weight,strong_signal=True,hard_mismatch=(label in {"map","side"}))

    try: vd=float(_r6_pick(video_round,"observed_duration","duration","round_duration",default=round_duration)); rd=float(_r6_pick(replay_round,"duration","round_duration",default=round_duration))
    except (TypeError,ValueError): vd=rd=0
    if vd>0 and rd>0:
        add("duration",max(0.0,1.0-abs(vd-rd)/max(vd,rd,1.0)),.10)

    for label,aliases,weight in (
        ("players",("players","player_names","playerNames"),.08),
        ("operators",("operators","operator_names","operatorNames"),.08),
    ):
        va=_r6_norm_set(_r6_pick(video_round,*aliases)); ra=_r6_norm_set(_r6_pick(replay_round,*aliases))
        if va and ra: add(label,len(va&ra)/len(va|ra),weight,strong_signal=True)

    count_sim=_r6_count_similarity(_r6_count_signature(video_round),_r6_count_signature(replay_round))
    add("event_counts",count_sim,.08,strong_signal=(count_sim is not None))
    temporal,reason=_r6_temporal_event_similarity(video_round,replay_round,round_duration=round_duration,tolerance=event_tolerance)
    add("temporal_events",temporal,.17,strong_signal=(temporal is not None))

    raw=weighted/total if total else 0.0
    # Sparse evidence may suggest a pair but never auto-identify it.
    if evidence < 2: raw=min(raw,.54)
    elif evidence < 3 or strong < 1: raw=min(raw,.69)
    # Conflicting explicit identity signals strongly cap confidence.
    if conflicts: raw=min(raw,.49)
    return {"score":round(max(0.0,min(1.0,raw)),4),"evidence_count":evidence,
            "strong_evidence_count":strong,"reasons":reasons,"conflicts":conflicts}


def match_r6_replay_rounds(video_rounds: list[dict], replay_rounds: list[dict], *, round_duration: float,
                            high_threshold: float = .80, medium_threshold: float = .62,
                            ambiguity_margin: float = .10, event_tolerance: float = 4.0) -> dict:
    """Safely match R6 video rounds to replay rounds without ordinal guessing.

    HIGH matches are one-to-one and automatic. MEDIUM results are proposals only.
    LOW/ambiguous/conflicting inputs remain unmatched for manual review.
    """
    duration=float(round_duration)
    if duration<=0: raise ValueError("round_duration must be positive")
    videos=[dict(v) for v in (video_rounds or []) if isinstance(v,dict)]
    replays=[normalize_r6_replay_round_payload(r, default_round_duration=duration)
             for r in (replay_rounds or []) if isinstance(r,dict)]
    pairs=[]
    for vi,v in enumerate(videos):
        for ri,r in enumerate(replays):
            detail=score_r6_round_identity(v,r,round_duration=duration,event_tolerance=event_tolerance)
            pairs.append({"video_position":vi,"replay_position":ri,**detail})
    # Ambiguity is evaluated from both directions; equal-looking rounds cannot auto-match.
    by_v={i:sorted([p for p in pairs if p["video_position"]==i],key=lambda x:-x["score"]) for i in range(len(videos))}
    by_r={i:sorted([p for p in pairs if p["replay_position"]==i],key=lambda x:-x["score"]) for i in range(len(replays))}
    for p in pairs:
        vr=by_v[p["video_position"]]; rr=by_r[p["replay_position"]]
        v_second=next((x["score"] for x in vr if x["replay_position"]!=p["replay_position"]),0.0)
        r_second=next((x["score"] for x in rr if x["video_position"]!=p["video_position"]),0.0)
        p["margin"]=round(min(p["score"]-v_second,p["score"]-r_second),4)
        p["ambiguous"]=p["margin"] < float(ambiguity_margin)
        if p["conflicts"] or p["ambiguous"] or p["evidence_count"]<2:
            p["level"]="LOW"
        elif p["score"]>=float(high_threshold) and p["evidence_count"]>=3 and p["strong_evidence_count"]>=1:
            p["level"]="HIGH"
        elif p["score"]>=float(medium_threshold):
            p["level"]="MEDIUM"
        else: p["level"]="LOW"

    matches=[]; used_v=set(); used_r=set()
    for p in sorted((x for x in pairs if x["level"]=="HIGH"),key=lambda x:(-x["score"],-x["margin"])):
        vi=p["video_position"]; ri=p["replay_position"]
        if vi in used_v or ri in used_r: continue
        used_v.add(vi); used_r.add(ri)
        v=videos[vi]; r=replays[ri]
        matches.append({**p,"video_round_index":_r6_pick(v,"round_number","roundNumber","round_index",default=vi+1),
                        "replay_round_index":_r6_pick(r,"round_number","roundNumber","round_index","round",default=ri+1),
                        "video_round_start":v.get("video_round_start"),"auto_assigned":True})

    proposals=[]
    for vi in range(len(videos)):
        if vi in used_v or not by_v.get(vi): continue
        p=by_v[vi][0]
        if p["level"]=="MEDIUM" and p["replay_position"] not in used_r:
            v=videos[vi]; r=replays[p["replay_position"]]
            proposals.append({**p,"video_round_index":_r6_pick(v,"round_number","roundNumber","round_index",default=vi+1),
                              "replay_round_index":_r6_pick(r,"round_number","roundNumber","round_index","round",default=p["replay_position"]+1),
                              "video_round_start":v.get("video_round_start"),"auto_assigned":False})

    unmatched_v=[i for i in range(len(videos)) if i not in used_v]
    unmatched_r=[i for i in range(len(replays)) if i not in used_r]
    return {"matches":matches,"proposals":proposals,"pair_matrix":pairs,
            "matched_count":len(matches),"video_rounds_total":len(videos),"replay_rounds_total":len(replays),
            "unmatched_video_rounds":[_r6_pick(videos[i],"round_number","roundNumber","round_index",default=i+1) for i in unmatched_v],
            "unmatched_replay_rounds":[_r6_pick(replays[i],"round_number","roundNumber","round_index","round",default=i+1) for i in unmatched_r],
            "reason":"OK" if matches else "NO_HIGH_CONFIDENCE_MATCHES"}


def build_r6_match_timeline(round_alignments: list[dict], replay_rounds: list, *,
                            round_duration: float, require_confident: bool = True) -> dict:
    """Build one R6 match timeline without unsafe ordinal guessing.

    Backward compatibility: a legacy ``list[list[event]]`` input keeps the old
    strict ordinal pairing. Metadata-rich replay dictionaries use the identity
    matcher; only HIGH one-to-one matches are admitted to the automatic timeline.
    MEDIUM suggestions remain proposals and therefore unmatched.
    """
    duration=float(round_duration)
    if duration <= 0: raise ValueError("round_duration must be positive")
    alignments=[]
    for raw in round_alignments or []:
        if not isinstance(raw,dict) or raw.get("video_round_start") is None: continue
        if require_confident and not bool(raw.get("aligned",False)): continue
        try: start=float(raw["video_round_start"])
        except (TypeError,ValueError): continue
        if start < 0: continue
        alignments.append({**raw,"video_round_start":start})
    alignments.sort(key=lambda x:float(x["video_round_start"]))
    rounds=[]; events=[]

    metadata_mode=bool(replay_rounds) and all(isinstance(x,dict) for x in replay_rounds)
    if metadata_mode:
        normalized_replays=[normalize_r6_replay_round_payload(x, default_round_duration=duration) for x in replay_rounds]
        identity=match_r6_replay_rounds(alignments,normalized_replays,round_duration=duration)
        for match in identity["matches"]:
            vi=int(match["video_position"]); ri=int(match["replay_position"])
            alignment=alignments[vi]; replay=normalized_replays[ri]
            feedback=_r6_events_from_round(replay)
            normalized=normalize_r6_replay_feedback(feedback,round_duration=duration,
                                                    video_round_start=alignment["video_round_start"])
            round_idx=_r6_pick(alignment,"round_number","roundNumber","round_index",default=vi+1)
            rounds.append({"round_index":round_idx,"replay_round_index":match["replay_round_index"],
                           "video_round_start":round(alignment["video_round_start"],4),
                           "confidence":float(match["score"]),"match_level":"HIGH",
                           "event_count":len(normalized),"match_reasons":list(match["reasons"])})
            for event in normalized:
                events.append({**event,"round_index":round_idx,"replay_round_index":match["replay_round_index"]})
        events.sort(key=lambda x:(float(x["video_time"]),str(x["round_index"])))
        rounds.sort(key=lambda x:float(x["video_round_start"]))
        return {"matched":bool(rounds),"rounds":rounds,"events":events,
                "rounds_matched":len(rounds),"aligned_rounds_total":len(alignments),
                "replay_rounds_total":len(replay_rounds or []),
                "unmatched_aligned_rounds":len(identity["unmatched_video_rounds"]),
                "unmatched_replay_rounds":len(identity["unmatched_replay_rounds"]),
                "identity_matches":identity["matches"],"identity_proposals":identity["proposals"],
                "reason":"OK" if rounds else "NO_HIGH_CONFIDENCE_MATCHES"}

    # Legacy strict ordinal mode retained for callers that only have anonymous
    # event lists. It never guesses around gaps; metadata mode is the safe path.
    pair_count=min(len(alignments),len(replay_rounds or []))
    for i in range(pair_count):
        alignment=alignments[i]; feedback=replay_rounds[i] if isinstance(replay_rounds[i],list) else []
        normalized=normalize_r6_replay_feedback(feedback,round_duration=duration,
                                                video_round_start=alignment["video_round_start"])
        round_item={"round_index":i+1,"video_round_start":round(alignment["video_round_start"],4),
                    "confidence":float(alignment.get("confidence",0.0)),"event_count":len(normalized)}
        rounds.append(round_item)
        for event in normalized:
            events.append({**event,"round_index":i+1})
    events.sort(key=lambda x:(float(x["video_time"]),int(x["round_index"])))
    return {"matched":pair_count>0,"rounds":rounds,"events":events,
            "rounds_matched":pair_count,"aligned_rounds_total":len(alignments),
            "replay_rounds_total":len(replay_rounds or []),
            "unmatched_aligned_rounds":max(0,len(alignments)-pair_count),
            "unmatched_replay_rounds":max(0,len(replay_rounds or [])-pair_count),
            "reason":"OK" if pair_count else "NO_MATCHED_ROUNDS"}


def build_universal_edit_plan(prompt: str, *, media_duration: float | None = None) -> dict:
    """Compile a natural-language editing brief into a deterministic, non-executing plan.

    Run 46 deliberately keeps this compiler local and fail-closed: it recognizes
    only operations ZeroCut can represent safely. Unknown creative instructions
    are preserved as notes instead of being hallucinated into executable edits.
    A local LLM can later propose the same schema, but validation remains here.
    """
    import re
    text=" ".join(str(prompt or "").strip().split())
    low=text.lower()
    plan={"schema":"zerocut.edit-plan.v1","source":"deterministic_local_parser","prompt":text,
          "goal":"edit","target_duration_seconds":None,"aspect_ratio":None,
          "operations":[],"creative_notes":[],"requires_content_analysis":False,
          "safe_to_execute":False}
    if not text:
        plan["warnings"]=["EMPTY_PROMPT"]
        return plan

    # Duration: support common Italian/English forms without guessing.
    patterns=[
        (r"(?:di|da|in|about|around|of)\s+(\d+(?:[\.,]\d+)?)\s*(?:minuti|minuto|min|minutes?|mins?)\b",60.0),
        (r"(?:di|da|in|about|around|of)\s+(\d+(?:[\.,]\d+)?)\s*(?:secondi|secondo|sec|seconds?|secs?)\b",1.0),
    ]
    for pat,mul in patterns:
        m=re.search(pat,low)
        if m:
            plan["target_duration_seconds"]=round(float(m.group(1).replace(",","."))*mul,3); break

    if any(x in low for x in ("verticale","vertical","tiktok","reel","shorts","9:16")):
        plan["aspect_ratio"]="9:16"
        plan["operations"].append({"type":"reframe","mode":"vertical","aspect_ratio":"9:16"})
    elif "1:1" in low or "quadrato" in low or "square" in low:
        plan["aspect_ratio"]="1:1"; plan["operations"].append({"type":"reframe","mode":"square","aspect_ratio":"1:1"})

    if any(x in low for x in ("tempi morti","pause lunghe","remove silence","remove silences","dead air","silent parts")):
        plan["operations"].append({"type":"remove_dead_air","detector":"audio_silence","review_required":True})
        plan["requires_content_analysis"]=True
    if any(x in low for x in ("sottotitol","caption","subtitles")):
        plan["operations"].append({"type":"captions","source":"local_asr","review_required":True})
        plan["requires_content_analysis"]=True
    if any(x in low for x in ("momenti migliori","parti migliori","best moments","highlights","highlight")):
        plan["operations"].append({"type":"select_highlights","strategy":"content_aware","review_required":True})
        plan["requires_content_analysis"]=True
    if any(x in low for x in ("zoom leggero","subtle zoom","zoom lieve")):
        plan["operations"].append({"type":"zoom","style":"subtle","trigger":"important_moments","review_required":True})
        plan["requires_content_analysis"]=True
    if any(x in low for x in ("musica bassa","musica molto bassa","low music","background music")):
        plan["operations"].append({"type":"background_music","level":"low","asset_required":True,"review_required":True})

    # Preserve unsupported creative intent rather than pretending it was understood.
    known_tokens=("vertical","tiktok","reel","shorts","9:16","1:1","quadrato","square","tempi morti","pause lunghe",
                  "silence","dead air","silent parts","sottotitol","caption","subtitles","momenti migliori","parti migliori",
                  "best moments","highlight","zoom leggero","subtle zoom","zoom lieve","musica bassa","musica molto bassa","low music","background music")
    if not any(t in low for t in known_tokens) and plan["target_duration_seconds"] is None:
        plan["creative_notes"].append(text)
    if plan["target_duration_seconds"] is not None:
        if media_duration is not None:
            try:
                md=max(0.0,float(media_duration))
                if plan["target_duration_seconds"] > md:
                    plan.setdefault("warnings",[]).append("TARGET_LONGER_THAN_SOURCE")
            except (TypeError,ValueError): pass
        plan["operations"].append({"type":"target_duration","seconds":plan["target_duration_seconds"],"review_required":True})
        plan["requires_content_analysis"]=True
    plan["safe_to_execute"]=bool(plan["operations"]) and not plan.get("creative_notes")
    return plan


DIRECTOR_CAPABILITY_REGISTRY = {
    # Run 48 separates "we can analyse/represent this" from "the Director has a
    # verified mutating executor for it".  Run 47 accidentally allowed analysis-
    # only capabilities to report safe_to_apply=True, which could mislead a future
    # agent into treating a dry-run as executable.
    "target_duration": {"stage": "analysis", "implemented": True, "executor": False, "destructive": False},
    "remove_dead_air": {"stage": "analysis", "implemented": True, "executor": False, "destructive": True},
    "select_highlights": {"stage": "analysis", "implemented": True, "executor": False, "destructive": True},
    "captions": {"stage": "asr", "implemented": True, "executor": False, "destructive": False},
    # Parsed in Run 46, but there is not yet a Director executor that can apply
    # these generically and verify the resulting timeline. Keep them blocked.
    "reframe": {"stage": "timeline", "implemented": False, "executor": False, "destructive": False},
    "zoom": {"stage": "timeline", "implemented": False, "executor": False, "destructive": False},
    "background_music": {"stage": "asset", "implemented": False, "executor": False, "destructive": False},
}


def validate_universal_edit_plan(plan: dict, *, media_loaded: bool = True, whisper_available: bool | None = None) -> dict:
    """Validate a Director plan without changing project state.

    The validator is intentionally stricter than the parser: understanding an
    instruction does not mean ZeroCut is allowed to execute it. Each operation
    must map to an explicit capability and all prerequisites must be present.
    """
    if not isinstance(plan, dict) or plan.get("schema") != "zerocut.edit-plan.v1":
        return {"valid": False, "safe_to_apply": False, "errors": ["INVALID_PLAN_SCHEMA"],
                "operations": [], "summary": {"total": 0, "executable": 0, "blocked": 0, "needs_analysis": 0}}
    if whisper_available is None:
        whisper_available = bool(discover_whisper().get("available"))
    rows=[]; errors=[]
    for index,op in enumerate(plan.get("operations") or []):
        kind=op.get("type") if isinstance(op,dict) else None
        cap=DIRECTOR_CAPABILITY_REGISTRY.get(kind)
        reasons=[]
        if cap is None:
            reasons.append("UNKNOWN_OPERATION")
        else:
            if not cap["implemented"]: reasons.append("DIRECTOR_EXECUTOR_NOT_IMPLEMENTED")
            if not media_loaded: reasons.append("MEDIA_REQUIRED")
            if kind == "captions" and not whisper_available: reasons.append("LOCAL_ASR_NOT_AVAILABLE")
            if kind == "background_music" and op.get("asset_required"): reasons.append("ASSET_REQUIRED")
        if reasons:
            status="blocked"
        elif cap and not cap.get("executor", False):
            status="needs_analysis" if cap["stage"] in ("analysis","asr") else "blocked"
            if status == "blocked": reasons.append("DIRECTOR_EXECUTOR_NOT_IMPLEMENTED")
        else:
            status="executable"
        rows.append({"index":index,"type":kind,"status":status,"reasons":reasons,
                     "destructive":bool(cap and cap["destructive"]),"stage":cap["stage"] if cap else None,
                     "executor_available":bool(cap and cap.get("executor",False))})
    if plan.get("creative_notes"): errors.append("UNRESOLVED_CREATIVE_INTENT")
    if not rows: errors.append("NO_OPERATIONS")
    blocked=sum(r["status"]=="blocked" for r in rows)
    needs=sum(r["status"]=="needs_analysis" for r in rows)
    executable=sum(r["status"] == "executable" for r in rows)
    analyzable=sum(r["status"] == "needs_analysis" for r in rows)
    valid=not errors and blocked==0
    # A plan may be valid and ready for analysis while still having zero verified
    # mutating executors. Never conflate those states.
    safe_to_apply=valid and bool(rows) and executable == len(rows)
    return {"valid":valid,"safe_to_apply":safe_to_apply,"ready_for_analysis":valid and blocked==0,
            "errors":errors,"operations":rows,
            "summary":{"total":len(rows),"executable":executable,"blocked":blocked,"needs_analysis":needs,
                       "analyzable":analyzable,"destructive":sum(r["destructive"] for r in rows)}}


def dry_run_universal_edit_plan(prompt: str, *, media_duration: float | None = None,
                                media_loaded: bool = True, whisper_available: bool | None = None) -> dict:
    """Compile + validate a request, with zero project mutations."""
    plan=build_universal_edit_plan(prompt,media_duration=media_duration)
    validation=validate_universal_edit_plan(plan,media_loaded=media_loaded,whisper_available=whisper_available)
    return {"schema":"zerocut.director-dry-run.v1","mutated":False,"plan":plan,"validation":validation}



def apply_director_segment_transaction(segments: list[dict], operations: list[dict], *, media_duration: float) -> dict:
    """Apply concrete segment edits atomically to an isolated copy.

    This is deliberately narrower than the natural-language Director.  It accepts
    only explicit source-timeline operations (trim/split/remove), validates the
    complete candidate after every operation, and never mutates the caller's
    list.  The returned receipt can therefore be committed by the project layer
    only after preview/verification succeeds.
    """
    import copy
    before = copy.deepcopy(segments or [])
    work = copy.deepcopy(before)
    try:
        duration = float(media_duration)
        if duration <= 0:
            raise ValueError("INVALID_MEDIA_DURATION")
    except (TypeError, ValueError):
        return {"ok": False, "committed": False, "error": "INVALID_MEDIA_DURATION", "before": before, "after": before}

    def normalize(items):
        out=[]
        for i, seg in enumerate(items):
            if not isinstance(seg, dict): raise ValueError("INVALID_SEGMENT")
            a=float(seg.get("start", -1)); b=float(seg.get("end", -1))
            if a < 0 or b <= a or b > duration + 1e-6: raise ValueError("INVALID_SEGMENT_RANGE")
            out.append({**seg, "start": round(a, 6), "end": round(b, 6), "id": seg.get("id") or f"seg{i}"})
        out.sort(key=lambda x:(x["start"],x["end"]))
        for prev,cur in zip(out,out[1:]):
            if cur["start"] < prev["end"] - 1e-6: raise ValueError("OVERLAPPING_SEGMENTS")
        return out

    try:
        work=normalize(work)
        applied=[]
        for op in operations or []:
            if not isinstance(op,dict): raise ValueError("INVALID_OPERATION")
            kind=op.get("type"); sid=op.get("segment_id")
            idx=next((i for i,x in enumerate(work) if x.get("id")==sid),None)
            if idx is None: raise ValueError("SEGMENT_NOT_FOUND")
            seg=work[idx]
            if kind == "trim":
                a=float(op.get("start",seg["start"])); b=float(op.get("end",seg["end"]))
                if a < seg["start"]-1e-6 or b > seg["end"]+1e-6 or b <= a: raise ValueError("INVALID_TRIM_RANGE")
                work[idx]={**seg,"start":a,"end":b}
            elif kind == "split":
                at=float(op.get("at",-1))
                if not (seg["start"] < at < seg["end"]): raise ValueError("INVALID_SPLIT_POINT")
                left={**seg,"end":at,"id":f"{seg['id']}-a"}; right={**seg,"start":at,"id":f"{seg['id']}-b"}
                work[idx:idx+1]=[left,right]
            elif kind == "remove":
                work.pop(idx)
            else:
                raise ValueError("UNSUPPORTED_TRANSACTION_OPERATION")
            work=normalize(work)
            applied.append(kind)
        return {"ok": True, "committed": False, "schema":"zerocut.director-transaction-receipt.v1",
                "before": before, "after": work, "applied": applied, "operation_count": len(applied)}
    except (TypeError, ValueError) as exc:
        return {"ok": False, "committed": False, "error": str(exc), "before": before, "after": before}



def prepare_transcript_removal_transaction(transcript_segments: list[dict], selected_ids: list[str], *,
                                           media_duration: float, padding: float = 0.04) -> dict:
    """Compile explicit transcript selections into a reviewable atomic removal transaction.

    Only transcript IDs explicitly selected by the caller are removed. The function
    never guesses filler words or content value, preserving human agency and making
    text-based editing deterministic. A normal Director revision gate is still required
    before commit.
    """
    import copy
    try: duration=float(media_duration)
    except (TypeError,ValueError):
        return {"ok":False,"committed":False,"error":"INVALID_MEDIA_DURATION"}
    if duration <= 0:
        return {"ok":False,"committed":False,"error":"INVALID_MEDIA_DURATION"}
    wanted={str(x) for x in (selected_ids or []) if str(x)}
    if not wanted:
        return {"ok":False,"committed":False,"error":"NO_TRANSCRIPT_SELECTION"}
    pad=max(0.0,min(0.50,float(padding)))
    ranges=[]; matched=[]
    for seg in transcript_segments or []:
        if not isinstance(seg,dict) or str(seg.get("id") or "") not in wanted:
            continue
        try: a=max(0.0,float(seg.get("start"))-pad); b=min(duration,float(seg.get("end"))+pad)
        except (TypeError,ValueError):
            continue
        if b <= a + 1e-6:
            continue
        ranges.append({"start":a,"end":b}); matched.append(str(seg.get("id")))
    if not ranges:
        return {"ok":False,"committed":False,"error":"TRANSCRIPT_SELECTION_NOT_FOUND","selected_ids":sorted(wanted)}
    ranges.sort(key=lambda x:(x["start"],x["end"])); merged=[]
    for row in ranges:
        if merged and row["start"] <= merged[-1]["end"] + 1e-6:
            merged[-1]["end"]=max(merged[-1]["end"],row["end"])
        else:
            merged.append(dict(row))
    before=[{"id":"source0","start":0.0,"end":round(duration,6)}]
    operations=[]; live=[dict(before[0])]
    boundaries=sorted({x for r in merged for x in (r["start"],r["end"]) if 1e-6 < x < duration-1e-6})
    for at in boundaries:
        seg=next((x for x in live if x["start"] < at < x["end"]),None)
        if not seg: continue
        sid=seg["id"]; operations.append({"type":"split","segment_id":sid,"at":at})
        idx=live.index(seg)
        live[idx:idx+1]=[{**seg,"end":at,"id":f"{sid}-a"},{**seg,"start":at,"id":f"{sid}-b"}]
    for rem in merged:
        for seg in list(live):
            if seg["start"] >= rem["start"]-1e-6 and seg["end"] <= rem["end"]+1e-6:
                operations.append({"type":"remove","segment_id":seg["id"]}); live.remove(seg)
    receipt=apply_director_segment_transaction(before,operations,media_duration=duration)
    if not receipt.get("ok"):
        return {**receipt,"selected_ids":sorted(wanted),"matched_ids":sorted(set(matched))}
    receipt["director_intent"]="remove_selected_transcript"
    receipt["detector"]="explicit_transcript_selection"
    receipt["transcript_ranges"]=[{"start":round(x["start"],6),"end":round(x["end"],6)} for x in merged]
    receipt["selected_ids"]=sorted(wanted); receipt["matched_ids"]=sorted(set(matched))
    receipt["removed_seconds"]=round(sum(x["end"]-x["start"] for x in merged),4)
    receipt["expected_revision"]=director_timeline_revision(before)
    receipt["requires_preview"]=True
    return receipt


def prepare_dead_air_director_transaction(analysis: dict, *, media_duration: float | None = None,
                                          base_segments: list[dict] | None = None) -> dict:
    """Compile Analyzer dead-air into a reviewable transaction on the *current* timeline.

    The original Run 53 implementation always built a synthetic ``source0`` timeline.
    That was correct for unit tests, but a real imported project uses persistent segment
    IDs; consequently a later revision-safe commit could reject a perfectly valid
    proposal.  Run 67 keeps backward compatibility while allowing the UI to pass the
    actual current timeline, so Analyzer -> Director -> Preview -> Commit is one real
    path rather than a parallel editor.
    """
    import copy
    if not isinstance(analysis, dict) or analysis.get("schema") != "zerocut.universal-analysis.v1":
        return {"ok": False, "committed": False, "error": "INVALID_UNIVERSAL_ANALYSIS"}
    try:
        duration=float(media_duration if media_duration is not None else analysis.get("duration"))
    except (TypeError, ValueError):
        return {"ok": False, "committed": False, "error": "INVALID_MEDIA_DURATION"}
    if duration <= 0:
        return {"ok": False, "committed": False, "error": "INVALID_MEDIA_DURATION"}

    ranges=analysis.get("smart_dead_air_ranges")
    detector="smart_motion_aware"
    if not isinstance(ranges, list):
        ranges=analysis.get("silences") or []
        detector="legacy_audio_silence"
    cleaned=[]
    for row in ranges:
        if not isinstance(row, dict):
            continue
        try: a=max(0.0,float(row.get("start"))); b=min(duration,float(row.get("end")))
        except (TypeError,ValueError):
            continue
        if b > a + 1e-6:
            cleaned.append({"start":round(a,6),"end":round(b,6)})
    cleaned.sort(key=lambda x:(x["start"],x["end"]))
    merged=[]
    for row in cleaned:
        if merged and row["start"] <= merged[-1]["end"] + 1e-6:
            merged[-1]["end"]=max(merged[-1]["end"],row["end"])
        else: merged.append(dict(row))

    seed=copy.deepcopy(base_segments) if isinstance(base_segments,list) and base_segments else [
        {"id":"source0","start":0.0,"end":round(duration,6)}
    ]
    normalized=apply_director_segment_transaction(seed,[],media_duration=duration)
    if not normalized.get("ok") or not normalized.get("after"):
        return {"ok":False,"committed":False,"error":normalized.get("error") or "INVALID_BASE_TIMELINE"}
    before=copy.deepcopy(normalized["after"])

    # Compile concrete split/remove operations against the current kept source ranges.
    # Only low-motion dead-air ranges are removable; any silence with strong visual
    # activity has already been excluded by Analyzer V2.
    operations=[]; live=copy.deepcopy(before)
    boundaries=sorted({x for r in merged for x in (r["start"],r["end"]) if 1e-6 < x < duration-1e-6})
    for at in boundaries:
        seg=next((x for x in live if x["start"] < at < x["end"]),None)
        if not seg:
            continue
        sid=seg["id"]
        operations.append({"type":"split","segment_id":sid,"at":at})
        idx=live.index(seg)
        live[idx:idx+1]=[{**seg,"end":at,"id":f"{sid}-a"},{**seg,"start":at,"id":f"{sid}-b"}]
    for dead in merged:
        for seg in list(live):
            if seg["start"] >= dead["start"]-1e-6 and seg["end"] <= dead["end"]+1e-6:
                operations.append({"type":"remove","segment_id":seg["id"]})
                live.remove(seg)

    receipt=apply_director_segment_transaction(before,operations,media_duration=duration)
    if not receipt.get("ok"):
        return {**receipt,"detector":detector,"dead_air_ranges":copy.deepcopy(merged)}
    actual_removed=max(0.0, sum(x["end"]-x["start"] for x in before) - sum(x["end"]-x["start"] for x in receipt.get("after",[])))
    receipt["director_intent"]="remove_dead_air"
    receipt["detector"]=detector
    receipt["dead_air_ranges"]=copy.deepcopy(merged)
    receipt["removed_seconds"]=round(actual_removed,4)
    receipt["expected_revision"]=director_timeline_revision(before)
    receipt["requires_preview"]=True
    return receipt


def summarize_auto_edit_proposal(analysis: dict, receipt: dict, *, prompt: str = "") -> dict:
    """Return compact UI-safe facts without pretending to have Vision/Whisper semantics."""
    before=receipt.get("before") or []
    after=receipt.get("after") or []
    original=sum(max(0.0,float(x.get("end",0))-float(x.get("start",0))) for x in before if isinstance(x,dict))
    proposed=sum(max(0.0,float(x.get("end",0))-float(x.get("start",0))) for x in after if isinstance(x,dict))
    removed=max(0.0,original-proposed)
    structure=analysis.get("structure") if isinstance(analysis.get("structure"),list) else []
    important=analysis.get("important_segments") if isinstance(analysis.get("important_segments"),list) else []
    dead=analysis.get("smart_dead_air_ranges") if isinstance(analysis.get("smart_dead_air_ranges"),list) else []
    return {
        "mode":"smart_dead_air",
        "prompt":str(prompt or "").strip()[:500],
        "original_duration":round(original,4),
        "proposed_duration":round(proposed,4),
        "removed_seconds":round(removed,4),
        "scene_count":len(structure),
        "important_segment_count":len(important),
        "dead_air_count":len(dead),
        "has_changes":bool(receipt.get("ok") and removed >= 0.04 and before != after),
        "detector":receipt.get("detector") or "unknown",
        "limitations":list(analysis.get("limitations") or []),
    }


def normalize_candidate_timeline(candidate: list[dict], *, media_duration: float) -> list[dict]:
    """Fail-closed validation for a user-adjusted preview candidate."""
    checked=apply_director_segment_transaction(candidate or [],[],media_duration=media_duration)
    if not checked.get("ok") or not checked.get("after"):
        raise ValueError(checked.get("error") or "TIMELINE_CANDIDATE_INVALID")
    return checked["after"]

def director_timeline_revision(segments: list[dict]) -> str:
    """Return a stable content revision for optimistic Director commits."""
    import hashlib, json
    payload=json.dumps(segments or [],sort_keys=True,separators=(",",":"),ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def commit_director_segment_transaction(current_segments: list[dict], receipt: dict, *, expected_revision: str) -> dict:
    """Commit a previously prepared candidate only if the timeline is unchanged.

    This is an optimistic-concurrency gate: UI/manual edits made after preview
    invalidate the receipt instead of being silently overwritten.  Inputs are
    never mutated; the caller/project layer owns persistence after this gate.
    """
    import copy
    current=copy.deepcopy(current_segments or [])
    current_revision=director_timeline_revision(current)
    if not isinstance(receipt,dict) or receipt.get("schema") != "zerocut.director-transaction-receipt.v1" or not receipt.get("ok"):
        return {"ok":False,"committed":False,"error":"INVALID_TRANSACTION_RECEIPT","segments":current,"revision":current_revision}
    if not expected_revision or expected_revision != current_revision:
        return {"ok":False,"committed":False,"error":"TIMELINE_REVISION_CONFLICT","segments":current,"revision":current_revision}
    receipt_before=receipt.get("before") or []
    if director_timeline_revision(receipt_before) != current_revision:
        return {"ok":False,"committed":False,"error":"RECEIPT_BASE_MISMATCH","segments":current,"revision":current_revision}
    candidate=copy.deepcopy(receipt.get("after") or [])
    new_revision=director_timeline_revision(candidate)
    return {"ok":True,"committed":True,"schema":"zerocut.director-commit-receipt.v1",
            "segments":candidate,"previous_revision":current_revision,"revision":new_revision,
            "operation_count":int(receipt.get("operation_count") or 0)}

def certify_r6_semantic_events(events: list[dict], *, min_kill_score: float = 0.50,
                                duplicate_window: float = 0.20) -> dict:
    """Certify only explicit R6 semantic events; signal-only detections never become kill claims."""
    accepted=[]; rejected=[]; seen=[]
    kill_gate=max(0.0,min(1.0,float(min_kill_score))); dup=max(0.0,float(duplicate_window))
    supported={"kill","headshot","dbno","defuser","objective"}
    for index,event in enumerate(events or []):
        if not isinstance(event,dict):
            rejected.append({"index":index,"reason":"NOT_OBJECT"}); continue
        kind=_r6_event_kind(event)
        if kind not in supported:
            rejected.append({"index":index,"reason":"UNSUPPORTED_KIND","kind":kind}); continue
        try: t=float(event.get("video_time"))
        except (TypeError,ValueError):
            rejected.append({"index":index,"reason":"VIDEO_TIME_REQUIRED","kind":kind}); continue
        if not math.isfinite(t) or t < 0:
            rejected.append({"index":index,"reason":"VIDEO_TIME_INVALID","kind":kind}); continue
        item=dict(event); item["video_time"]=round(t,4); item["semantic_kind"]=kind
        if kind in {"kill","headshot"}:
            evidence=score_r6_highlight_event(item)
            score=float(evidence.get("score") or 0.0)
            if score < kill_gate:
                rejected.append({"index":index,"reason":"INSUFFICIENT_REPLAY_EVIDENCE","kind":kind,
                                 "score":round(score,3)}); continue
            item["highlight_confidence"]=evidence
        actor=_r6_norm_text(item.get("username",item.get("attacker","")))
        target=_r6_norm_text(item.get("target",""))
        duplicate=False
        for old in seen:
            same_kind=(old["kind"]==kind or {old["kind"],kind}<={"kill","headshot"})
            identity_match=(actor==old["actor"] and target==old["target"]) or (not actor and not old["actor"])
            if same_kind and identity_match and abs(t-old["time"]) <= dup:
                duplicate=True; break
        if duplicate:
            rejected.append({"index":index,"reason":"DUPLICATE_EVENT","kind":kind}); continue
        seen.append({"kind":kind,"actor":actor,"target":target,"time":t})
        item["certified_semantic_event"]=True
        item["certification_sources"]=[
            x for x in ("replay_semantic_event",
                        "recording_player" if item.get("recording_player_action") is True else None,
                        "recording_pov" if item.get("recording_pov_action") is True else None,
                        "kill_shot" if item.get("recording_player_kill_shot_correlated") is True else None)
            if x
        ]
        accepted.append(item)
    accepted.sort(key=lambda x:(x["video_time"],x["semantic_kind"]))
    return {"accepted":accepted,"rejected":rejected,"accepted_count":len(accepted),
            "rejected_count":len(rejected),"gameplay_visual_accuracy_certified":False,
            "limitations":["NO_REAL_R6_GAMEPLAY_FIXTURE"]}


def build_r6_automatic_clips(events: list[dict], *, video_duration: float | None = None,
                             kill_pre: float = 6.0, kill_post: float = 4.0,
                             headshot_pre: float = 7.0, headshot_post: float = 4.5,
                             objective_pre: float = 8.0, objective_post: float = 6.0,
                             merge_gap: float = 2.5, max_clip_duration: float = 30.0) -> list[dict]:
    """Turn corroborated R6 timeline events into deterministic clip suggestions.

    Only semantic replay/timeline events are accepted. Nearby/overlapping windows
    are merged to preserve multikill context and avoid duplicate exports. All
    timing knobs are caller-configurable; no cloud/model dependency is required.
    """
    duration=None
    if video_duration is not None:
        try: duration=max(0.0,float(video_duration))
        except (TypeError,ValueError): duration=None
    gap=max(0.0,float(merge_gap))
    max_duration=max(1.0,float(max_clip_duration))
    raw=[]; seen=set()
    certified = certify_r6_semantic_events(events)
    for event in certified["accepted"]:
        if event.get("video_time") is None: continue
        try: t=float(event["video_time"])
        except (TypeError,ValueError): continue
        if t<0: continue
        kind=_r6_event_kind(event)
        # Run 44: when replay-only confidence is available, use it as a fail-closed
        # selector gate. Low-confidence replay kills (typically another player's
        # action with no proven recorded POV) are preserved in the timeline but
        # are not promoted to automatic clips. Legacy callers without confidence
        # metadata retain the deterministic Run 17 behavior.
        replay_conf=event.get("highlight_confidence") if isinstance(event.get("highlight_confidence"),dict) else None
        replay_score=None
        if replay_conf is not None:
            try: replay_score=float(replay_conf.get("score"))
            except (TypeError,ValueError): replay_score=None
            if kind in {"kill","headshot"} and (replay_score is None or replay_score < 0.50):
                continue
        is_headshot=kind=="headshot" or bool(event.get("headshot"))
        if is_headshot:
            pre,post,base,label=float(headshot_pre),float(headshot_post),.90,"headshot"
        elif kind=="kill":
            pre,post,base,label=float(kill_pre),float(kill_post),.76,"kill"
        elif kind in {"defuser","objective"}:
            pre,post,base,label=float(objective_pre),float(objective_post),.82,kind
        elif kind=="dbno":
            pre,post,base,label=float(kill_pre),float(kill_post),.62,"dbno"
        else:
            continue
        sig=(round(t,3),label,str(event.get("username","")),str(event.get("target","")))
        if sig in seen: continue
        seen.add(sig)
        start=max(0.0,t-max(0.0,pre)); end=t+max(0.0,post)
        if duration is not None and duration>0: end=min(duration,end)
        if end<=start: continue
        if replay_score is not None and kind in {"kill","headshot"}:
            # Replay evidence can raise/lower ranking inside the already-safe
            # semantic class, but cannot exceed the established clip score range.
            base=max(base,min(1.0,replay_score))
        raw.append({"start":start,"end":end,"event_time":t,"score":base,"events":[dict(event)],"reasons":[label]})
    raw.sort(key=lambda x:(x["start"],x["event_time"]))
    merged=[]
    for item in raw:
        if not merged or item["start"] > merged[-1]["end"] + gap:
            merged.append(item)
            continue
        cur=merged[-1]
        proposed_end=max(cur["end"],item["end"])
        # Run 45: overlapping/nearby highlight windows can chain across a busy
        # round and accidentally create a minute-long "clip". Preserve local
        # multikill context, but fail closed on unbounded transitive merging.
        if proposed_end - cur["start"] > max_duration:
            merged.append(item)
            continue
        cur["end"]=proposed_end
        cur["events"].extend(item["events"])
        cur["reasons"].extend(item["reasons"])
        cur["score"]=max(cur["score"],item["score"])
    out=[]
    for i,item in enumerate(merged):
        kinds=[_r6_event_kind(e) for e in item["events"]]
        kills=sum(1 for k in kinds if k in {"kill","headshot"})
        headshots=sum(1 for k in kinds if k=="headshot")
        objectives=sum(1 for k in kinds if k in {"defuser","objective"})
        combo_bonus=min(.08,max(0,kills-1)*.03) + min(.04,objectives*.02)
        score=min(1.0,float(item["score"])+combo_bonus)
        reasons=[]
        if headshots: reasons.append(f"headshot:{headshots}")
        if kills: reasons.append(f"kills:{kills}")
        if objectives: reasons.append(f"objective:{objectives}")
        if kills>=2: reasons.append("multikill_context")
        out.append({"clip_index":i+1,"start":round(item["start"],3),"end":round(item["end"],3),
                    "duration":round(item["end"]-item["start"],3),"score":round(score,3),
                    "event_count":len(item["events"]),"kill_count":kills,"headshot_count":headshots,
                    "objective_count":objectives,"reasons":reasons,"events":item["events"]})
    return sorted(out,key=lambda x:(-x["score"],x["start"]))

def normalize_r6_replay_feedback(feedback: list[dict], *, round_duration: float,
                                 video_round_start: float = 0.0) -> list[dict]:
    """Map r6-dissect countdown timestamps onto a video timeline.

    r6-dissect exports MatchFeedback.timeInSeconds as the round clock value
    (time remaining). ZeroCut deliberately requires the caller to supply the
    round duration/start instead of guessing them from game mode or HUD state.
    """
    duration = float(round_duration)
    start = max(0.0, float(video_round_start))
    if duration <= 0:
        raise ValueError("round_duration must be positive")
    out=[]
    for event in feedback or []:
        if not isinstance(event, dict):
            continue
        elapsed=_r6_event_elapsed(event, round_duration=duration)
        if elapsed is None:
            continue
        kind=str(event.get("type", event.get("kind", "Other")) or "Other").strip()
        video_time=start + elapsed
        item={"type":kind,"video_time":round(video_time,4),
              "round_clock":round(max(0.0,duration-elapsed),4)}
        for key in ("username","attacker","target","headshot","message"):
            if key in event:
                item[key]=event[key]
        out.append(item)
    return sorted(out,key=lambda x:x["video_time"])


def enrich_candidates_with_r6_replay(candidates: list[dict], replay_events: list[dict], *,
                                     tolerance: float = 2.0, weight: float = 0.30) -> list[dict]:
    """Corroborate ranked video candidates with nearby parsed R6 replay events.

    Replay evidence is stronger than OCR/audio but remains bounded by an explicit
    alignment tolerance. No .rec parser is bundled: this consumes safe JSON-like
    output from an optional external parser boundary.
    """
    tol=max(0.05,float(tolerance)); w=max(0.0,min(1.0,float(weight)))
    valid=[]
    for e in replay_events or []:
        if not isinstance(e,dict) or "video_time" not in e:
            continue
        try: t=float(e["video_time"])
        except (TypeError,ValueError): continue
        if t >= 0: valid.append((t,e))
    out=[]
    for candidate in candidates or []:
        if not isinstance(candidate,dict): continue
        item=dict(candidate)
        try: ct=float(item.get("time",item.get("start",0.0)))
        except (TypeError,ValueError): ct=0.0
        nearby=[(abs(ct-t),e) for t,e in valid if abs(ct-t)<=tol]
        nearby.sort(key=lambda pair:pair[0])
        evidence=[]; bonus=0.0
        for distance,event in nearby[:3]:
            kind=str(event.get("type","")).lower()
            strength=1.0 if kind=="kill" else (0.8 if any(k in kind for k in ("plant","disable","objective")) else 0.45)
            if bool(event.get("headshot")): strength=min(1.0,strength+0.15)
            temporal=max(0.0,1.0-distance/tol)
            event_score=strength*(0.65+0.35*temporal)
            bonus=max(bonus,event_score)
            evidence.append({"type":event.get("type","Other"),"distance":round(distance,4),
                             "headshot":bool(event.get("headshot",False)),"score":round(event_score,4)})
        item["r6_replay"]={"matched":bool(evidence),"events":evidence}
        item["score"]=round(min(1.0,float(item.get("score",0.0))+w*bonus),4)
        out.append(item)
    return sorted(out,key=lambda x:(-float(x.get("score",0.0)),float(x.get("time",x.get("start",0.0)))))

def proxy_command(source: Path, output: Path, duration: float, has_audio: bool,
                  ffmpeg_bin: str | None = None) -> tuple[list[str], float]:
    vf = "scale=w='if(gt(iw,1280),1280,iw)':h=-2:flags=lanczos,fps='min(source_fps,60)'"
    # 'source_fps' is not a valid expression variable for fps filter; preserve fps instead.
    vf = "scale=w='if(gt(iw,1280),1280,iw)':h=-2:flags=lanczos"
    cmd = [
        str(ffmpeg_bin or _active_media_tool("ffmpeg")), "-y", "-hide_banner", "-nostdin", "-i", str(source),
        "-vf", vf,
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28", "-pix_fmt", "yuv420p",
    ]
    if has_audio:
        cmd += ["-c:a", "aac", "-b:a", "96k", "-ar", "48000"]
    else:
        cmd += ["-an"]
    cmd += ["-movflags", "+faststart", "-progress", "pipe:1", "-nostats", str(output)]
    return cmd, duration



def detect_audio_highlights(media: dict, *, window_seconds: float = 0.5, max_candidates: int = 12, min_spacing: float = 8.0) -> list[dict]:
    """Find conservative highlight candidates from local audio-energy peaks using FFmpeg only.

    This is deliberately a heuristic signal, not an AI/game-event claim. It is intended to
    become one input to later multimodal Rainbow Six scoring.
    """
    metadata = media.get("metadata") or {}
    if not metadata.get("audio"):
        return []
    duration = float(metadata.get("duration") or 0.0)
    if duration <= 0:
        return []
    window_seconds = max(0.25, min(float(window_seconds), 2.0))
    max_candidates = max(1, min(int(max_candidates), 50))
    min_spacing = max(window_seconds, min(float(min_spacing), 60.0))
    source_rel = media.get("proxy_rel") or media.get("original_rel")
    source = resolve_project_file(source_rel)
    sample_rate = 16000
    samples = max(1, int(round(sample_rate * window_seconds)))
    filt = (
        f"aresample={sample_rate},asetnsamples=n={samples}:p=0,"
        "astats=metadata=1:reset=1,"
        "ametadata=print:key=lavfi.astats.Overall.RMS_level:file=-"
    )
    proc = subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(source),
        "-vn", "-af", filt, "-f", "null", "-",
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=max(30.0, min(600.0, duration * 0.25 + 30.0)))
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or "FFmpeg audio analysis failed")[-1200:])
    rows: list[tuple[float, float]] = []
    current_t: float | None = None
    for line in proc.stdout.splitlines():
        mt = re.search(r"pts_time:([0-9.]+)", line)
        if mt:
            current_t = float(mt.group(1))
            continue
        mr = re.search(r"RMS_level=(-?(?:[0-9]+(?:\.[0-9]+)?|inf))", line)
        if mr and current_t is not None:
            raw = mr.group(1)
            db = -120.0 if raw == "-inf" else float(raw)
            rows.append((current_t, max(-120.0, min(0.0, db))))
            current_t = None
    if not rows:
        return []
    values = sorted(db for _, db in rows)
    # Robust relative loudness: median/MAD prevents one explosion from flattening the
    # rest of the recording, while the prominence gate avoids manufacturing a
    # "highlight" from uniformly quiet/constant footage.
    median = statistics.median(values)
    deviations = [abs(v - median) for v in values]
    mad = statistics.median(deviations)
    robust_scale = max(1.5, 1.4826 * mad)
    prominence_db = max(values) - median
    if prominence_db < max(4.0, 2.5 * robust_scale):
        return []
    scored = [(t, max(0.0, min(1.0, (db - median) / (4.0 * robust_scale))), db) for t, db in rows]
    peaks: list[tuple[float, float, float]] = []
    for i, row in enumerate(scored):
        left = scored[i - 1][1] if i else -1.0
        right = scored[i + 1][1] if i + 1 < len(scored) else -1.0
        if row[1] >= 0.55 and row[1] >= left and row[1] >= right:
            peaks.append(row)
    selected: list[tuple[float, float, float]] = []
    for row in sorted(peaks, key=lambda x: (-x[1], x[0])):
        center = min(duration, row[0] + window_seconds / 2.0)
        if all(abs(center - (old[0] + window_seconds / 2.0)) >= min_spacing for old in selected):
            selected.append(row)
            if len(selected) >= max_candidates:
                break
    result = []
    for t, score, db in sorted(selected, key=lambda x: x[0]):
        center = min(duration, t + window_seconds / 2.0)
        result.append({
            "type": "audio_energy_peak",
            "source": "ffmpeg_rms_heuristic",
            "timestamp": round(center, 3),
            "start": round(max(0.0, center - 6.0), 3),
            "end": round(min(duration, center + 8.0), 3),
            "score": round(score, 4),
            "rms_db": round(db, 2),
        })
    return result


def _media_video_dimensions(metadata: dict | None) -> tuple[int, int]:
    """Read dimensions from ZeroCut ffprobe metadata and tolerate legacy flat metadata.

    ZeroCut's ffprobe() stores video dimensions under metadata["video"].  Some older
    callers/tests used flat width/height keys, so keep that format as a compatibility
    fallback rather than silently disabling ROI analysis.
    """
    if not isinstance(metadata, dict):
        return 0, 0
    video = metadata.get("video") if isinstance(metadata.get("video"), dict) else {}
    try:
        width = int(metadata.get("width") or video.get("width") or 0)
        height = int(metadata.get("height") or video.get("height") or 0)
    except (TypeError, ValueError):
        return 0, 0
    return max(0, width), max(0, height)


def measure_r6_roi_activity(media: dict, candidates: list[dict], *,
                            roi: tuple[float, float, float, float] = R6_DEFAULT_ROIS["kill_feed"],
                            sample_offset: float = 0.35, max_candidates: int = 12) -> list[dict]:
    """Add a cheap visual-activity signal around bounded candidates using FFmpeg only.

    This deliberately does not claim OCR/game-event recognition.  It samples ROI mean
    luma immediately before/at/after each candidate and reports the local range as a
    conservative visual-change score.  Expensive OCR can later be limited to candidates
    that survive this prefilter.
    """
    metadata = media.get("metadata") or {}
    duration = float(metadata.get("duration") or 0.0)
    if duration <= 0:
        return []
    # The proxy may be downscaled to 1280px.  ROI pixel coordinates MUST be based on
    # the actual source being sampled, otherwise a 1440p/4K original can produce a
    # crop outside the proxy frame. Prefer persisted proxy metadata; probe only when
    # old projects do not have it.
    use_proxy = bool(media.get("proxy_rel"))
    source = resolve_project_file(media.get("proxy_rel") or media.get("original_rel"))
    source_meta = (media.get("proxy_metadata") or {}) if use_proxy else metadata
    width, height = _media_video_dimensions(source_meta)
    if width < 2 or height < 2:
        try:
            source_meta = ffprobe(source)
            width, height = _media_video_dimensions(source_meta)
        except (OSError, subprocess.SubprocessError, ValueError, KeyError):
            return []
    if width < 2 or height < 2:
        return []
    x, y, w, h = normalized_roi_to_pixels(width, height, roi)
    chosen = sorted((c for c in candidates if isinstance(c, dict) and "timestamp" in c),
                    key=lambda c: (-float(c.get("score", 0)), float(c["timestamp"])))[:max(0, int(max_candidates))]
    out=[]
    for candidate in chosen:
        center=max(0.0,min(duration,float(candidate["timestamp"])))
        lumas=[]
        for at in (max(0.0,center-sample_offset), center, min(max(0.0,duration-0.001),center+sample_offset)):
            vf=f"crop={w}:{h}:{x}:{y},signalstats,metadata=print:key=lavfi.signalstats.YAVG:file=-"
            proc=subprocess.run(["ffmpeg","-hide_banner","-loglevel","error","-ss",f"{at:.3f}","-i",str(source),
                                 "-frames:v","1","-vf",vf,"-an","-f","null","-"],
                                stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=20.0)
            if proc.returncode != 0:
                continue
            m=re.search(r"lavfi\.signalstats\.YAVG=([0-9.]+)",proc.stdout)
            if m: lumas.append(float(m.group(1)))
        if len(lumas) < 2:
            continue
        delta=max(lumas)-min(lumas)
        visual_score=max(0.0,min(1.0,delta/32.0))
        item=dict(candidate)
        item.update({"visual_source":"ffmpeg_roi_luma_prefilter","roi":"kill_feed","roi_luma_delta":round(delta,3),
                     "visual_score":round(visual_score,4),"claim":"candidate_signal_only"})
        out.append(item)
    return sorted(out,key=lambda c:(-float(c.get("score",0)),float(c["timestamp"])))


def fuse_r6_candidate_signals(candidates: list[dict], *, min_visual_score: float = 0.12) -> list[dict]:
    """Fuse cheap independent signals without claiming a semantic Rainbow Six event.

    Audio is useful for recall, while kill-feed ROI activity adds independent visual
    evidence.  A small visual gate rejects audio-only bursts before any future OCR
    stage, reducing expensive OCR work while keeping the result explicitly heuristic.
    """
    gate=max(0.0,min(1.0,float(min_visual_score)))
    out=[]
    for candidate in candidates:
        if not isinstance(candidate,dict):
            continue
        audio=max(0.0,min(1.0,float(candidate.get("score",0.0))))
        visual=max(0.0,min(1.0,float(candidate.get("visual_score",0.0))))
        if visual < gate:
            continue
        # Geometric mean rewards agreement: one strong signal cannot fully hide a
        # weak independent signal. Keep this as ranking evidence, never a kill claim.
        fused=(audio*visual)**0.5
        item=dict(candidate)
        item.update({
            "fused_score":round(fused,4),
            "fusion_source":"audio_roi_geometric_mean",
            "visual_gate":round(gate,4),
            "claim":"candidate_signal_only",
        })
        out.append(item)
    return sorted(out,key=lambda c:(-float(c.get("fused_score",0)),float(c.get("timestamp",0))))


class Handler(BaseHTTPRequestHandler):
    server_version = "ZeroCutGaming/0.2"

    def log_message(self, fmt, *args):
        print(f"[{self.log_date_time_string()}] {fmt % args}")

    def _body_json(self):
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length > 2_000_000:
            raise ValueError("JSON troppo grande")
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw.decode("utf-8"))

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/api/status":
            state = load_state()
            json_response(self, {
                "ok": True,
                "ffmpeg": shutil.which("ffmpeg"),
                "ffprobe": shutil.which("ffprobe"),
                "whisper": discover_whisper(),
                "rapidocr": discover_rapidocr(),
                "ai_runtime_manifest": runtime_manifest(),
                "project": state,
            })
            return
        if path == "/api/subtitles.srt":
            state = load_state()
            remapped = remap_subtitles(state.get("subtitles", []), state.get("segments", []))
            body = subtitles_to_srt(remapped).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/x-subrip; charset=utf-8")
            self.send_header("Content-Disposition", 'attachment; filename="zerocut-subtitles.srt"')
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return
        if path.startswith("/api/job/"):
            job = JOBS.get(path.rsplit("/", 1)[-1])
            if not job:
                json_response(self, {"error": "Job non trovato"}, 404)
            else:
                json_response(self, job.public())
            return
        if path == "/api/highlights/audio":
            state = load_state()
            media = state.get("media")
            if not media:
                json_response(self, {"error": "Nessun media importato"}, 404)
                return
            query = parse_qs(parsed.query)
            try:
                limit = int((query.get("limit") or ["12"])[0])
                candidates = detect_audio_highlights(media, max_candidates=limit)
                json_response(self, {
                    "ok": True,
                    "detector": "ffmpeg_rms_heuristic",
                    "claim": "candidate_signal_only",
                    "candidates": candidates,
                })
            except (ValueError, OSError, subprocess.SubprocessError, RuntimeError) as exc:
                json_response(self, {"error": f"Analisi audio non disponibile: {exc}"}, 400)
            return
        if path == "/api/highlights/r6-candidates":
            try:
                project = load_state()
                media = project.get("media") or {}
                audio = detect_audio_highlights(media, max_candidates=12)
                visual = measure_r6_roi_activity(media, audio, max_candidates=12)
                fused = fuse_r6_candidate_signals(visual)
                ocr = {"executed": False, "reason": "NO_CANDIDATES", "texts": {}}
                if fused:
                    # Capability gate before any temporary ROI extraction. If the optional
                    # local OCR runtime is unavailable, keep audio/visual candidates unchanged
                    # and avoid unnecessary FFmpeg work and temporary disk I/O.
                    ocr_cap = certify_rapidocr_inference()
                    if not ocr_cap.get("certified"):
                        ocr = {"executed": False, "reason": ocr_cap.get("reason", "UNAVAILABLE"),
                               "texts": {}, "providers": ocr_cap.get("providers", []),
                               "certified": False}
                        fused = enrich_candidates_with_ocr(fused, {})
                    else:
                        use_proxy = bool(media.get("proxy_rel"))
                        source = resolve_project_file(media.get("proxy_rel") or media.get("original_rel"))
                        source_meta = (media.get("proxy_metadata") or {}) if use_proxy else (media.get("metadata") or {})
                        width, height = _media_video_dimensions(source_meta)
                        if width < 2 or height < 2:
                            source_meta = ffprobe(source); width, height = _media_video_dimensions(source_meta)
                        if width < 2 or height < 2:
                            raise ValueError("R6_ROI_DIMENSIONS_UNAVAILABLE")
                        ocr_candidates = [{**c, "time": float(c.get("timestamp", c.get("time", 0.0)))} for c in fused]
                        with tempfile.TemporaryDirectory(prefix="zerocut-r6-ocr-") as td:
                            frames = extract_candidate_roi_frames(source, ocr_candidates, Path(td), width=width, height=height, max_frames=12)
                            ocr = rapidocr_candidate_frames(frames, min_confidence=0.65)
                        fused = enrich_candidates_with_ocr(fused, ocr.get("texts", {}))
                json_response(self, {"detector":"r6_audio_roi_ocr_fusion","claim":"candidate_signal_only",
                                     "ocr":{"executed":ocr.get("executed",False),"reason":ocr.get("reason"),
                                            "providers":ocr.get("providers",[])},"candidates":fused})
                return
            except Exception as exc:
                json_response(self, {"error":str(exc)}, 500)
                return

        if path == "/api/highlights/r6-prefilter":
            state = load_state()
            media = state.get("media")
            if not media:
                json_response(self, {"error": "Nessun media importato"}, 404)
                return
            try:
                candidates = detect_audio_highlights(media, max_candidates=12)
                enriched = measure_r6_roi_activity(media, candidates)
                json_response(self, {"ok": True, "detector": "audio_plus_r6_roi_prefilter",
                                     "claim": "candidate_signal_only", "candidates": enriched})
            except (ValueError, OSError, subprocess.SubprocessError, RuntimeError) as exc:
                json_response(self, {"error": f"Prefiltro R6 non disponibile: {exc}"}, 400)
            return
        if path == "/api/thumbnail":
            state = load_state()
            media = state.get("media")
            if not media:
                json_response(self, {"error": "Nessun media importato"}, 404)
                return
            query = parse_qs(parsed.query)
            try:
                timestamp = float((query.get("t") or ["0"])[0])
                width = int((query.get("w") or ["320"])[0])
                target, cache_hit = cached_thumbnail(media, timestamp, width)
                body = target.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("X-ZeroCut-Thumbnail-Cache", "HIT" if cache_hit else "MISS")
                self.send_header("Cache-Control", "private, max-age=31536000, immutable")
                self.end_headers()
                self.wfile.write(body)
            except (ValueError, OSError, subprocess.CalledProcessError, RuntimeError) as exc:
                json_response(self, {"error": f"Thumbnail non disponibile: {exc}"}, 400)
            return
        if path == "/api/media":
            state = load_state()
            media = state.get("media")
            if not media:
                self.send_error(404)
                return
            rel = media.get("proxy_rel") if media.get("proxy_rel") and resolve_project_file(media["proxy_rel"]).exists() else media.get("original_rel")
            try:
                self._serve_file(resolve_project_file(rel), allow_range=True)
            except Exception:
                self.send_error(404)
            return
        if path.startswith("/api/render/"):
            try:
                target = resolve_project_file("render/" + safe_name(path.split("/api/render/", 1)[1]))
                self._serve_file(target, allow_range=True)
            except Exception:
                self.send_error(404)
            return
        if path == "/":
            return self._serve_file(WEB / "index.html")
        if path.startswith("/static/"):
            target = WEB / path.split("/static/", 1)[1]
            return self._serve_file(target)
        self.send_error(404)

    def _serve_file(self, target: Path, allow_range=False):
        target = target.resolve()
        if not target.exists() or not target.is_file():
            self.send_error(404)
            return
        ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        size = target.stat().st_size
        range_header = self.headers.get("Range") if allow_range else None
        if range_header:
            m = re.match(r"bytes=(\d*)-(\d*)", range_header)
            if not m:
                self.send_error(416)
                return
            start_s, end_s = m.groups()
            start = int(start_s) if start_s else 0
            end = int(end_s) if end_s else size - 1
            end = min(end, size - 1)
            if start > end or start >= size:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.end_headers()
                return
            length = end - start + 1
            self.send_response(206)
            self.send_header("Content-Type", ctype)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.send_header("Content-Length", str(length))
            self.end_headers()
            with target.open("rb") as f:
                f.seek(start)
                remaining = length
                while remaining:
                    chunk = f.read(min(1024 * 1024, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
            return
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(size))
        if allow_range:
            self.send_header("Accept-Ranges", "bytes")
        self.end_headers()
        with target.open("rb") as f:
            shutil.copyfileobj(f, self.wfile, length=1024 * 1024)

    def do_PUT(self):
        parsed = urlparse(self.path)
        if parsed.path != "/api/import":
            self.send_error(404)
            return
        query = parse_qs(parsed.query)
        filename = safe_name((query.get("filename") or ["gameplay.mp4"])[0])
        ext = Path(filename).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            json_response(self, {"error": f"Formato non supportato: {ext or 'nessuno'}"}, 400)
            return
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length <= 0:
            json_response(self, {"error": "File vuoto"}, 400)
            return
        target = ORIGINAL / filename
        stem, suffix = target.stem, target.suffix
        n = 1
        while target.exists():
            target = ORIGINAL / f"{stem}-{n}{suffix}"
            n += 1
        tmp = target.with_suffix(target.suffix + ".part")
        try:
            remaining = length
            digest = hashlib.sha256()
            with tmp.open("wb") as f:
                while remaining > 0:
                    chunk = self.rfile.read(min(1024 * 1024, remaining))
                    if not chunk:
                        raise IOError("Upload interrotto")
                    f.write(chunk)
                    digest.update(chunk)
                    remaining -= len(chunk)
            content_hash = digest.hexdigest()
            cache = _load_media_cache()
            cached = cache.get(content_hash) if isinstance(cache.get(content_hash), dict) else None
            cached_path = None
            if cached and cached.get("original_rel"):
                try:
                    candidate = resolve_project_file(cached["original_rel"])
                    if candidate.exists() and candidate.stat().st_size == length:
                        cached_path = candidate
                except (ValueError, OSError):
                    cached_path = None
            if cached_path is not None:
                tmp.unlink(missing_ok=True)
                target = cached_path
                meta = cached.get("metadata") or ffprobe(target)
                cache_hit = True
            else:
                os.replace(tmp, target)
                meta = ffprobe(target)
                cache_hit = False
            if not meta.get("video"):
                target.unlink(missing_ok=True)
                json_response(self, {"error": "Il file non contiene una traccia video"}, 400)
                return
            state = default_state()
            media_id = uuid.uuid4().hex[:10]
            cached_proxy_rel = None
            cached_proxy_meta = None
            if cached and cached.get("proxy_rel"):
                try:
                    proxy_candidate = resolve_project_file(cached["proxy_rel"])
                    if proxy_candidate.exists() and proxy_candidate.stat().st_size > 0:
                        cached_proxy_rel = cached["proxy_rel"]
                        cached_proxy_meta = cached.get("proxy_metadata") or ffprobe(proxy_candidate)
                except (ValueError, OSError, subprocess.CalledProcessError):
                    cached_proxy_rel = None
                    cached_proxy_meta = None
            state["media"] = {
                "id": media_id,
                "name": target.name,
                "original_rel": str(target.relative_to(PROJECT)).replace("\\", "/"),
                "proxy_rel": cached_proxy_rel,
                "proxy_metadata": cached_proxy_meta,
                "metadata": meta,
                "content_sha256": content_hash,
                "cache_hit": cache_hit,
                "proxy_cache_hit": bool(cached_proxy_rel),
            }
            state["segments"] = [{"id": uuid.uuid4().hex[:8], "start": 0.0, "end": meta["duration"]}]
            state["selected_segment"] = state["segments"][0]["id"]
            cache[content_hash] = {
                "original_rel": state["media"]["original_rel"],
                "metadata": meta,
                "size": length,
                **({"proxy_rel": cached_proxy_rel, "proxy_metadata": cached_proxy_meta} if cached_proxy_rel else {}),
            }
            _save_media_cache(cache)
            save_state(state)
            json_response(self, {"ok": True, "project": state})
        except subprocess.CalledProcessError as exc:
            tmp.unlink(missing_ok=True)
            target.unlink(missing_ok=True)
            json_response(self, {"error": f"FFprobe non riesce a leggere il video: {exc.output[-500:]}"}, 400)
        except Exception as exc:
            tmp.unlink(missing_ok=True)
            json_response(self, {"error": str(exc)}, 500)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            if path == "/api/autoedit/analyze":
                payload = self._body_json()
                state = load_state()
                analysis_base_revision = project_state_revision(state)
                source = media_file(state)
                media = state.get("media") or {}
                metadata = media.get("metadata") or {}
                duration = float(metadata.get("duration") or 0)
                if duration <= 0:
                    raise ValueError("Durata media non valida")
                prompt = str(payload.get("prompt") or "").strip()[:500]
                analysis = analyze_universal_media(
                    source, duration=duration, has_audio=bool(metadata.get("audio")),
                    min_silence=0.70, motion_fps=4.0, timeout=120.0,
                )
                receipt = prepare_dead_air_director_transaction(
                    analysis, media_duration=duration, base_segments=state.get("segments") or None,
                )
                if not receipt.get("ok"):
                    json_response(self, {"ok":False,"error":receipt.get("error") or "AUTO_EDIT_PREPARE_FAILED"}, 409)
                    return
                summary = summarize_auto_edit_proposal(analysis, receipt, prompt=prompt)
                proposal = {
                    "id": uuid.uuid4().hex[:12],
                    "created_at": time.time(),
                    "expected_revision": receipt.get("expected_revision"),
                    "summary": summary,
                    "transaction": receipt,
                    "analysis": {
                        "important_segments": analysis.get("important_segments") or [],
                        "smart_dead_air_ranges": analysis.get("smart_dead_air_ranges") or [],
                        "motion_available": bool((analysis.get("motion") or {}).get("available")),
                        "audio_present": bool(analysis.get("audio_present")),
                        "limitations": analysis.get("limitations") or [],
                    },
                }
                state["auto_edit_proposal"] = proposal
                save_state(state, expected_revision=analysis_base_revision)
                json_response(self, {"ok":True,"proposal":proposal,"project_revision":project_state_revision(state)})
                return

            if path == "/api/autoedit/apply":
                payload = self._body_json()
                state = load_state()
                proposal = state.get("auto_edit_proposal")
                if not isinstance(proposal, dict):
                    json_response(self,{"error":"Nessuna proposta di montaggio attiva"},409)
                    return
                if payload.get("proposal_id") and str(payload.get("proposal_id")) != str(proposal.get("id")):
                    json_response(self,{"error":"Proposta di montaggio non più valida"},409)
                    return
                media = state.get("media") or {}; metadata = media.get("metadata") or {}
                duration=float(metadata.get("duration") or 0)
                current=state.get("segments") or []
                tx=proposal.get("transaction") or {}
                expected=str(proposal.get("expected_revision") or tx.get("expected_revision") or "")
                if director_timeline_revision(current) != expected:
                    json_response(self,{"error":"TIMELINE_REVISION_CONFLICT: la timeline è cambiata dopo l'analisi. Riesegui Analizza video."},409)
                    return
                candidate_payload=payload.get("candidate_segments")
                if isinstance(candidate_payload,list):
                    candidate=normalize_candidate_timeline(candidate_payload,media_duration=duration)
                    commit={"ok":True,"committed":True,"schema":"zerocut.director-commit-receipt.v1",
                            "previous_revision":expected,"new_revision":director_timeline_revision(candidate),
                            "segments":candidate,"manual_preview_adjustment":True}
                else:
                    commit=commit_director_segment_transaction(current,tx,expected_revision=expected)
                    if not commit.get("ok"):
                        json_response(self,{"error":commit.get("error") or "AUTO_EDIT_COMMIT_FAILED"},409)
                        return
                    candidate=commit.get("segments") or []
                state["segments"] = candidate
                state["selected_segment"] = candidate[0]["id"] if candidate else None
                state["last_auto_edit"] = {
                    "proposal_id": proposal.get("id"),
                    "applied_at": time.time(),
                    "summary": proposal.get("summary") or {},
                    "commit": {k:v for k,v in commit.items() if k not in {"segments"}},
                }
                state["auto_edit_proposal"] = None
                expected_project_revision = payload.get("project_revision")
                save_state(state, expected_revision=str(expected_project_revision) if expected_project_revision else None)
                json_response(self,{"ok":True,"project":state,"commit":commit,"project_revision":project_state_revision(state)})
                return

            if path == "/api/autoedit/cancel":
                state=load_state()
                state["auto_edit_proposal"] = None
                expected_revision = payload.get("project_revision")
                save_state(state, expected_revision=str(expected_revision) if expected_revision else None)
                json_response(self,{"ok":True,"project":state,"project_revision":project_state_revision(state)})
                return

            if path == "/api/analyze/universal":
                payload = self._body_json()
                state = load_state()
                media = state.get("media") or {}
                if not media:
                    raise ValueError("MEDIA_NOT_LOADED")
                analysis, cache_hit = cached_universal_analysis(media, force=bool(payload.get("force")))
                json_response(self, {"ok": True, "cache_hit": cache_hit, "analysis": analysis}, 200)
                return
            if path == "/api/director/prepare-dead-air":
                payload = self._body_json()
                state = load_state()
                media = state.get("media") or {}
                if not media:
                    raise ValueError("MEDIA_NOT_LOADED")
                analysis, cache_hit = cached_universal_analysis(media, force=bool(payload.get("force")))
                duration = (media.get("metadata") or {}).get("duration")
                receipt = prepare_dead_air_director_transaction(analysis, media_duration=duration, base_segments=state.get("segments") or None)
                status = 200 if receipt.get("ok") else 422
                json_response(self, {"ok": bool(receipt.get("ok")), "cache_hit": cache_hit,
                                     "analysis_version": analysis.get("analysis_version"),
                                     "transaction": receipt}, status)
                return
            if path == "/api/director/plan":
                payload = self._body_json()
                state = load_state()
                duration = ((state.get("media") or {}).get("metadata") or {}).get("duration")
                plan = build_universal_edit_plan(payload.get("prompt", ""), media_duration=duration)
                json_response(self, {"ok": True, "plan": plan}, 200)
                return
            if path == "/api/director/dry-run":
                payload = self._body_json()
                state = load_state()
                media = state.get("media") or {}
                duration = (media.get("metadata") or {}).get("duration")
                result = dry_run_universal_edit_plan(payload.get("prompt", ""), media_duration=duration,
                                                     media_loaded=bool(media))
                json_response(self, {"ok": True, "dry_run": result}, 200)
                return
            if path == "/api/ai/bootstrap":
                payload = self._body_json()
                components = payload.get("components") or ["whisper", "rapidocr"]
                if not isinstance(components, list):
                    raise ValueError("components deve essere una lista")
                result = bootstrap_ai_runtime(ROOT, components)
                # Report truthful post-install capability and real inference self-tests.
                result["capabilities"] = {
                    "whisper": discover_whisper(),
                    "rapidocr": discover_rapidocr(),
                }
                result["selftests"] = {
                    "whisper": whisper_inference_selftest(),
                    "rapidocr": rapidocr_inference_selftest(),
                }
                result["certification"] = ai_certification_report()
                result["certification_path"] = str(write_ai_certification_report(result["certification"]).relative_to(ROOT)).replace("\\", "/")
                json_response(self, result, 200)
                return
            if path == "/api/project":
                payload = self._body_json()
                state = load_state()
                segments = payload.get("segments")
                if not isinstance(segments, list):
                    raise ValueError("segments richiesto")
                duration = float((state.get("media") or {}).get("metadata", {}).get("duration") or 0)
                clean = normalize_project_timeline(segments,duration)
                selected = str(payload.get("selected_segment") or "")
                if selected not in {seg["id"] for seg in clean}:
                    selected = clean[0]["id"]
                state["segments"] = clean
                state["selected_segment"] = selected
                state["auto_edit_proposal"] = None
                expected_revision = payload.get("project_revision")
                save_state(state, expected_revision=str(expected_revision) if expected_revision else None)
                json_response(self, {"ok": True, "project": state, "project_revision": project_state_revision(state)})
                return
            if path == "/api/subtitles":
                payload = self._body_json()
                state = load_state()
                duration = float((state.get("media") or {}).get("metadata", {}).get("duration") or 0)
                if duration <= 0:
                    raise ValueError("Importa prima un gameplay")
                state["subtitles"] = normalize_subtitles(payload.get("subtitles"), duration)
                style = str(payload.get("style") or state.get("subtitle_style") or "gaming-bold")
                if style not in SUBTITLE_STYLES:
                    raise ValueError("Preset sottotitoli non valido")
                state["subtitle_style"] = style
                state["schema"] = max(int(state.get("schema") or 1), 2)
                expected_revision = payload.get("project_revision")
                save_state(state, expected_revision=str(expected_revision) if expected_revision else None)
                json_response(self, {"ok": True, "project": state, "project_revision": project_state_revision(state)})
                return
            if path == "/api/subtitles/import-srt":
                payload = self._body_json()
                state = load_state()
                duration = float((state.get("media") or {}).get("metadata", {}).get("duration") or 0)
                if duration <= 0:
                    raise ValueError("Importa prima un gameplay")
                text = str(payload.get("srt") or "")
                if len(text.encode("utf-8")) > 1_000_000:
                    raise ValueError("SRT troppo grande")
                parsed_items = parse_srt(text)
                if not parsed_items:
                    raise ValueError("Nessun sottotitolo valido trovato nel file SRT")
                state["subtitles"] = normalize_subtitles(parsed_items, duration)
                state["schema"] = max(int(state.get("schema") or 1), 2)
                expected_revision = payload.get("project_revision")
                save_state(state, expected_revision=str(expected_revision) if expected_revision else None)
                json_response(self, {"ok": True, "count": len(state["subtitles"]), "project": state,
                                     "project_revision": project_state_revision(state)})
                return
            if path == "/api/proxy":
                state = load_state()
                source = media_file(state)
                media = state["media"]
                existing_proxy = media.get("proxy_rel")
                if existing_proxy:
                    try:
                        cached_proxy = resolve_project_file(existing_proxy)
                    except ValueError:
                        cached_proxy = None
                    if cached_proxy and cached_proxy.exists() and cached_proxy.stat().st_size > 0:
                        job = JOBS.completed("proxy", float(media["metadata"]["duration"]), existing_proxy)
                        json_response(self, {"ok": True, "cached": True, "job": job.public()})
                        return
                output = PROXY / f"{media['id']}-proxy.mp4"
                working = PROXY / f"{media['id']}-proxy.working.mp4"
                working.unlink(missing_ok=True)
                cmd, total = proxy_command(source, working, float(media["metadata"]["duration"]), bool(media["metadata"].get("audio")),
                                           ffmpeg_bin=_active_media_tool("ffmpeg"))
                def commit_proxy():
                    if not working.exists():
                        raise FileNotFoundError("Proxy non creato")
                    st = load_state()
                    if not st.get("media") or st["media"].get("id") != media["id"]:
                        raise RuntimeError("Il progetto è cambiato durante la generazione del proxy")
                    os.replace(working, output)
                    st["media"]["proxy_rel"] = str(output.relative_to(PROJECT)).replace("\\", "/")
                    st["media"]["proxy_metadata"] = ffprobe(output)
                    content_hash = st["media"].get("content_sha256")
                    if content_hash:
                        cache = _load_media_cache()
                        entry = cache.get(content_hash) if isinstance(cache.get(content_hash), dict) else {}
                        entry.update({
                            "original_rel": st["media"]["original_rel"],
                            "metadata": st["media"]["metadata"],
                            "size": resolve_project_file(st["media"]["original_rel"]).stat().st_size,
                            "proxy_rel": st["media"]["proxy_rel"],
                            "proxy_metadata": st["media"]["proxy_metadata"],
                        })
                        cache[content_hash] = entry
                        _save_media_cache(cache)
                    save_state(st)

                job = JOBS.create("proxy", total, cmd, str(output.relative_to(PROJECT)).replace("\\", "/"), on_success=commit_proxy, cleanup_path=working)
                json_response(self, {"ok": True, "job": job.public()})
                return
            if path == "/api/export":
                state = load_state()
                source = media_file(state)
                media = state["media"]
                name = safe_name(Path(media["name"]).stem + "-edit.mp4")
                output = RENDER / name
                n = 1
                while output.exists():
                    output = RENDER / f"{Path(name).stem}-{n}.mp4"
                    n += 1
                working = output.with_name(output.stem + ".working.mp4")
                working.unlink(missing_ok=True)
                mapped_subtitles = remap_subtitles(state.get("subtitles", []), state.get("segments", []))
                subtitle_path = None
                if mapped_subtitles:
                    subtitle_path = SUBTITLES / f"export-{media['id']}.srt"
                    subtitle_tmp = subtitle_path.with_suffix(".srt.tmp")
                    subtitle_tmp.write_text(subtitles_to_srt(mapped_subtitles), "utf-8")
                    os.replace(subtitle_tmp, subtitle_path)
                segments = state.get("segments", [])
                ffmpeg_tool = _active_media_tool("ffmpeg")
                ffprobe_tool = _active_media_tool("ffprobe")
                if can_lossless_passthrough_export(segments, media["metadata"], has_subtitles=bool(mapped_subtitles)):
                    cmd, total = lossless_passthrough_command(source, working, float(media["metadata"].get("duration") or 0), ffmpeg_bin=ffmpeg_tool)
                elif can_lossless_keyframe_trim_export(source, segments, media["metadata"], has_subtitles=bool(mapped_subtitles)):
                    cmd, total = lossless_keyframe_trim_command(source, working, float(segments[0]["start"]), float(segments[0]["end"]), ffmpeg_bin=ffmpeg_tool)
                else:
                    encoder_capability = detect_best_video_encoder(ffmpeg_tool)
                    if encoder_capability.get("verified") and encoder_capability.get("hardware"):
                        encoder_capability = benchmark_verified_video_encoder(ffmpeg_tool).get("recommended") or encoder_capability
                    cmd, total = export_command(source, working, segments, bool(media["metadata"].get("audio")), float((media["metadata"].get("video") or {}).get("fps") or 0), subtitle_path=subtitle_path, subtitle_style=state.get("subtitle_style") or "gaming-bold", encoder_capability=encoder_capability, ffmpeg_bin=ffmpeg_tool)
                def commit_export():
                    if not working.exists():
                        raise FileNotFoundError("Render non creato")
                    # FFmpeg exit 0 alone is not enough: validate the temporary artifact
                    # before atomically publishing it as a completed ZeroCut render.
                    verify_render_output(working, total, expect_audio=bool(media["metadata"].get("audio")),
                                         ffmpeg_bin=ffmpeg_tool, ffprobe_bin=ffprobe_tool)
                    os.replace(working, output)
                job = JOBS.create("export", total, cmd, str(output.relative_to(PROJECT)).replace("\\", "/"), on_success=commit_export, cleanup_path=working)
                json_response(self, {"ok": True, "job": job.public(), "download": "/api/render/" + output.name})
                return
            if path.startswith("/api/job/") and path.endswith("/stop"):
                job_id = path.split("/")[-2]
                ok = JOBS.stop(job_id)
                json_response(self, {"ok": ok})
                return
            if path == "/api/reset":
                state = load_state()
                # Keep originals/renders; reset only timeline metadata to avoid accidental data loss.
                if state.get("media"):
                    duration = float(state["media"]["metadata"].get("duration") or 0)
                    state["segments"] = [{"id": uuid.uuid4().hex[:8], "start": 0.0, "end": duration}]
                    state["selected_segment"] = state["segments"][0]["id"]
                    state["auto_edit_proposal"] = None
                    save_state(state)
                json_response(self, {"ok": True, "project": state})
                return
            self.send_error(404)
        except ProjectRevisionConflict as exc:
            json_response(self, {"error": str(exc), "code": "PROJECT_REVISION_CONFLICT"}, 409)
        except (ValueError, json.JSONDecodeError) as exc:
            json_response(self, {"error": str(exc)}, 400)
        except Exception as exc:
            json_response(self, {"error": str(exc)}, 500)


def main():
    parser = argparse.ArgumentParser(description="ZeroCut Gaming AI local server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true", help="Non apre automaticamente il browser")
    parser.add_argument("--bootstrap-ai", action="store_true", help="Installa/aggiorna i runtime AI locali ZeroCut e termina")
    parser.add_argument("--ai-status", action="store_true", help="Mostra capability/runtime AI e termina")
    parser.add_argument("--ai-selftest", action="store_true", help="Esegue inferenza reale Whisper/RapidOCR se disponibili e termina")
    parser.add_argument("--ai-certify", action="store_true", help="Genera un certificato JSON AI/Windows basato su inferenze reali e termina")
    args = parser.parse_args()
    if args.bootstrap_ai:
        result = bootstrap_ai_runtime(ROOT)
        result["capabilities"] = {"whisper": discover_whisper(), "rapidocr": discover_rapidocr()}
        result["selftests"] = {"whisper": whisper_inference_selftest(), "rapidocr": rapidocr_inference_selftest()}
        result["certification"] = ai_certification_report()
        result["certification_path"] = str(write_ai_certification_report(result["certification"]))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        raise SystemExit(0 if result.get("ok") and result["certification"].get("ai_core_certified") else 2)
    if args.ai_status:
        print(json.dumps({
            "manifest": runtime_manifest(),
            "whisper": discover_whisper(),
            "rapidocr": discover_rapidocr(),
        }, ensure_ascii=False, indent=2))
        raise SystemExit(0)
    if args.ai_selftest:
        result = {"whisper": whisper_inference_selftest(), "rapidocr": rapidocr_inference_selftest()}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        raise SystemExit(0 if all(v.get("passed") for v in result.values()) else 3)
    if args.ai_certify:
        result = ai_certification_report()
        result["report_path"] = str(write_ai_certification_report(result))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        raise SystemExit(0 if result.get("windows_ai_certified") else 4)
    try:
        ffmpeg_bin, ffprobe_bin = _ensure_ffmpeg_ready()
    except Exception as exc:
        try:
            DIAGNOSTICS.mkdir(parents=True, exist_ok=True)
            setup_log = DIAGNOSTICS / "ffmpeg-bootstrap-error.log"
            setup_log.write_text(f"{type(exc).__name__}: {exc}\n", encoding="utf-8")
            detail = f"\n\nDettaglio salvato in:\n{setup_log}"
        except Exception:
            detail = ""
        _message_box(
            "ZeroCut - configurazione FFmpeg non riuscita",
            "ZeroCut ha provato a installare FFmpeg automaticamente ma non ci è riuscito.\n\n"
            f"Errore: {type(exc).__name__}: {exc}" + detail +
            "\n\nControlla la connessione Internet e riapri questo stesso file: riproverà automaticamente.",
            error=True,
        )
        raise SystemExit(5)
    if not ffmpeg_bin or not ffprobe_bin:
        _message_box(
            "ZeroCut - FFmpeg non disponibile",
            "FFmpeg/FFprobe non sono disponibili e l'installazione automatica non può essere eseguita su questo sistema.",
            error=True,
        )
        raise SystemExit(5)
    _refresh_media_tools(ffmpeg_bin, ffprobe_bin)
    port = int(args.port)
    server = None
    last_error = None
    for candidate in range(port, port + 10):
        try:
            server = ThreadingHTTPServer((args.host, candidate), Handler)
            port = candidate
            break
        except OSError as exc:
            last_error = exc
    if server is None:
        raise RuntimeError(f"Nessuna porta locale disponibile da {args.port} a {args.port + 9}: {last_error}")
    url = f"http://{args.host}:{port}"
    print(f"ZeroCut Gaming AI: {url}")
    print(f"Project: {PROJECT}")
    if not args.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        try:
            DIAGNOSTICS.mkdir(parents=True, exist_ok=True)
            crash = DIAGNOSTICS / "startup-crash.log"
            crash.write_text(f"{type(exc).__name__}: {exc}\n", encoding="utf-8")
            detail = f"\n\nDettaglio salvato in:\n{crash}"
        except Exception:
            detail = ""
        _message_box("ZeroCut - errore di avvio", f"{type(exc).__name__}: {exc}{detail}", error=True)
        raise
