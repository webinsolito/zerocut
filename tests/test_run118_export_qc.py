from __future__ import annotations
import importlib.machinery, importlib.util, json, shutil, subprocess, sys, tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'src'/'ZeroCut_Run117_Candidate_TranscriptUI.pyw'

def load():
    name='zc118'; loader=importlib.machinery.SourceFileLoader(name,str(SOURCE)); spec=importlib.util.spec_from_loader(name,loader); assert spec
    m=importlib.util.module_from_spec(spec); sys.modules[name]=m; loader.exec_module(m); return m

def run(cmd):
    p=subprocess.run(cmd,capture_output=True,text=True,timeout=120)
    if p.returncode: raise AssertionError((p.stderr or p.stdout)[-1500:])
    return p.stdout.strip()

def duration(path,ffprobe):
    out=run([ffprobe,'-v','error','-show_entries','format=duration','-of','json',str(path)])
    return float(json.loads(out)['format']['duration'])

def export_segments(src,out,segments,ffmpeg):
    # Export the actual edited timeline as playable MP4, not a metadata-only proof.
    parts=[]
    for i,seg in enumerate(segments):
        start=float(seg['start']); end=float(seg['end']); assert end>start
        parts += [f'[0:v]trim=start={start}:end={end},setpts=PTS-STARTPTS[v{i}]',
                  f'[0:a]atrim=start={start}:end={end},asetpts=PTS-STARTPTS[a{i}]']
    links=';'.join(parts)+ ';' + ''.join(f'[v{i}][a{i}]' for i in range(len(segments))) + f'concat=n={len(segments)}:v=1:a=1[v][a]'
    run([ffmpeg,'-hide_banner','-loglevel','error','-y','-i',str(src),'-filter_complex',links,
         '-map','[v]','-map','[a]','-c:v','libx264','-preset','ultrafast','-pix_fmt','yuv420p','-c:a','aac','-movflags','+faststart',str(out)])

def main():
    ffmpeg=shutil.which('ffmpeg'); ffprobe=shutil.which('ffprobe'); assert ffmpeg and ffprobe
    m=load(); m.core.base._refresh_media_tools(ffmpeg,ffprobe)
    with tempfile.TemporaryDirectory(prefix='zc118-') as td:
        td=Path(td); src=td/'spoken.mp4'; out=td/'edited.mp4'
        run([ffmpeg,'-hide_banner','-loglevel','error','-y','-f','lavfi','-i','testsrc2=size=320x180:rate=30:duration=12',
             '-f','lavfi','-i','sine=frequency=700:sample_rate=48000:duration=12','-shortest','-c:v','libx264','-preset','ultrafast','-pix_fmt','yuv420p','-c:a','aac',str(src)])
        state={'media':{'metadata':{'duration':12.0}},'segments':[{'id':'source0','start':0.0,'end':12.0}],
               'last_transcript_full':{'segments':[{'id':'cut-me','start':3.0,'end':5.5,'text':'remove this section'},
                                                    {'id':'keep-me','start':7.0,'end':9.0,'text':'keep this section'}]}}
        receipt=m.core.prepare_transcript_edit(state,['cut-me'],padding=0.0); assert receipt.get('ok') is True,receipt
        metrics=m.core.transcript_edit_metrics(state,receipt); assert metrics['timeline_changed'] is True,metrics
        edited=receipt.get('after') or receipt.get('segments') or []
        assert edited,receipt
        export_segments(src,out,edited,ffmpeg)
        input_d=duration(src,ffprobe); output_d=duration(out,ffprobe); expected=float(metrics['after_duration'])
        assert output_d < input_d-2.0,(input_d,output_d)
        assert abs(output_d-expected)<=0.20,(output_d,expected,edited)
        qc=m.core.base.verify_render_output(out,expected,expect_audio=True,ffmpeg_bin=ffmpeg,ffprobe_bin=ffprobe)
        assert qc['av_timing']['ok'] is True,qc
        print('ZEROCUT_RUN118_EXPORT_QC=PASS')
        print(f'RUN118_INPUT={input_d:.3f} TIMELINE={expected:.3f} EXPORT={output_d:.3f} REMOVED={input_d-output_d:.3f}')
if __name__=='__main__': main()
