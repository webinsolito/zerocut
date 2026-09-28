from __future__ import annotations

import importlib.machinery
import importlib.util
import os
import py_compile
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "ZeroCut_Run121_Candidate_PremiumEditor.pyw"


def load():
    name = "zc121_premium_editor"
    loader = importlib.machinery.SourceFileLoader(name, str(SOURCE))
    spec = importlib.util.spec_from_loader(name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    loader.exec_module(module)
    return module


def main():
    py_compile.compile(str(SOURCE), doraise=True)
    with tempfile.TemporaryDirectory(prefix="zc121-ui-") as td:
        old_home = os.environ.get("ZEROCUT_HOME")
        os.environ["ZEROCUT_HOME"] = td
        try:
            module = load()
            html = (module.base.WEB / "index.html").read_text(encoding="utf-8")
            css = (module.base.WEB / "styles.css").read_text(encoding="utf-8")
            js = (module.base.WEB / "app.js").read_text(encoding="utf-8")
        finally:
            if old_home is None:
                os.environ.pop("ZEROCUT_HOME", None)
            else:
                os.environ["ZEROCUT_HOME"] = old_home

    assert "zerocut-premium-editor-run121" in html
    assert 'id="deliveryFlow"' in html
    assert ".zc-delivery-flow" in css
    assert "@media(max-width:560px)" in css
    assert "prefers-reduced-motion" in css
    assert "/api/ui/version" in SOURCE.read_text(encoding="utf-8")
    assert 'setStage("import")' in js
    assert "previewTranscriptEdit" in js
    assert "refreshExportQc" in js
    print("ZEROCUT_RUN121_PREMIUM_EDITOR=PASS")


if __name__ == "__main__":
    main()
