from __future__ import annotations
import importlib.machinery, importlib.util, platform, py_compile, sys, tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
CANDIDATE=ROOT/"src"/"ZeroCut_Run104_Candidate_WindowsCore.pyw"

def load():
    name="zerocut_run104_windows_core"
    loader=importlib.machinery.SourceFileLoader(name,str(CANDIDATE))
    spec=importlib.util.spec_from_loader(name,loader); assert spec
    m=importlib.util.module_from_spec(spec); sys.modules[name]=m; loader.exec_module(m); return m

def main():
    assert platform.system()=="Windows", platform.system()
    py_compile.compile(str(CANDIDATE),doraise=True)
    m=load(); facts=m.windows_core_environment_report()
    assert facts["is_windows"] is True and facts["os_name"]=="nt"
    with tempfile.TemporaryDirectory(prefix="zerocut-win104-") as td:
        root=Path(td)/"Progetto_àè_日本_测试"
        (root/"backup").mkdir(parents=True)
        m.PROJECT=root; m.STATE_FILE=root/"project.json"; m.STATE_TMP_FILE=root/"project.json.tmp"
        m.STATE_BACKUP_FILE=root/"backup"/"project.last-good.json"; m.STATE_RECOVERY_DIR=root/"backup"/"recovery"
        state=m.default_state(); state["schema"]=2
        state["media"]={"id":"win","name":"gameplay_à_日本.mp4","original_rel":"original/gameplay_à_日本.mp4","metadata":{"duration":8.0}}
        state["segments"]=[{"id":"s","start":0.0,"end":8.0}]; state["selected_segment"]="s"
        m.save_state(state)
        loaded=m.load_state()
        assert loaded["media"]["name"]=="gameplay_à_日本.mp4"
        assert m.STATE_FILE.exists() and m.STATE_BACKUP_FILE.exists()
        inside=m.resolve_project_file("original/gameplay_à_日本.mp4")
        assert str(inside).startswith(str(root.resolve()))
        try: m.resolve_project_file("../escape.txt")
        except ValueError: pass
        else: raise AssertionError("path traversal accepted")
        # Atomic replace/recovery semantics on NTFS-backed runner.
        before=m.project_state_revision(loaded)
        loaded["segments"]=[{"id":"s","start":1.0,"end":7.0}]
        m.save_state(loaded,expected_revision=before)
        assert m.load_state()["segments"][0]["start"]==1.0
    print("ZEROCUT_RUN104_WINDOWS_CORE=PASS")

if __name__=="__main__": main()
