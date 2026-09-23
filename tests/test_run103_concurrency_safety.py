from __future__ import annotations
import importlib.machinery, importlib.util, py_compile, sys, tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
CANDIDATE=ROOT/"src"/"ZeroCut_Run103_Candidate_ConcurrencySafety.pyw"

def load():
    name="zerocut_run103_concurrency"
    loader=importlib.machinery.SourceFileLoader(name,str(CANDIDATE))
    spec=importlib.util.spec_from_loader(name,loader); assert spec
    m=importlib.util.module_from_spec(spec); sys.modules[name]=m; loader.exec_module(m); return m

def state(m, marker):
    s=m.default_state(); s["schema"]=2
    s["media"]={"id":"m1","name":"x.mp4","original_rel":"original/x.mp4","metadata":{"duration":10.0}}
    s["segments"]=[{"id":"seg","start":0.0,"end":10.0}]
    s["selected_segment"]="seg"; s["marker"]=marker
    return s

def main():
    py_compile.compile(str(CANDIDATE),doraise=True); m=load()
    with tempfile.TemporaryDirectory(prefix="zc103-") as td:
        p=Path(td); (p/"backup").mkdir(); m.PROJECT=p
        m.STATE_FILE=p/"project.json"; m.STATE_TMP_FILE=p/"project.json.tmp"
        m.STATE_BACKUP_FILE=p/"backup"/"project.last-good.json"; m.STATE_RECOVERY_DIR=p/"backup"/"recovery"
        first=state(m,"first"); m.save_state(first)
        a=m.load_state(); rev_a=m.project_state_revision(a)
        b=m.load_state(); b["marker"]="newer"; m.save_state(b,expected_revision=rev_a)
        current=m.load_state(); rev_b=m.project_state_revision(current)
        assert rev_b!=rev_a and current["marker"]=="newer"
        stale=dict(a); stale["marker"]="stale-writer"
        try: m.save_state(stale,expected_revision=rev_a)
        except m.ProjectRevisionConflict as exc: assert "PROJECT_REVISION_CONFLICT" in str(exc)
        else: raise AssertionError("stale writer was accepted")
        assert m.load_state()["marker"]=="newer"
        assert m.project_state_revision(m.load_state())==rev_b

        # Background merge pattern: reload latest state, mutate only owned media field, preserve timeline edit.
        ui=m.load_state(); ui["segments"]=[{"id":"seg","start":1.0,"end":9.0}]
        ui_rev=m.project_state_revision(m.load_state()); m.save_state(ui,expected_revision=ui_rev)
        latest=m.load_state(); latest["media"]["proxy_rel"]="proxy/m1.mp4"; m.save_state(latest,expected_revision=m.project_state_revision(m.load_state()))
        done=m.load_state()
        assert done["segments"][0]["start"]==1.0 and done["media"]["proxy_rel"]=="proxy/m1.mp4"
    print("ZEROCUT_RUN103_CONCURRENCY_SAFETY=PASS")

if __name__=="__main__": main()
