"""Build a PRIVATE test distribution with explicitly authorized bundled API keys.
No conversations, audio recordings, account grants, logs, or machine paths copied.
"""
import json,shutil,subprocess,sys,time,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
VERSION='2026.11.1.1'
STAGE=ROOT/'build/private-test';OUT=ROOT/'release-private'/VERSION

def stage():
    STAGE.mkdir(parents=True,exist_ok=True);OUT.mkdir(parents=True,exist_ok=True)
    cfg=json.loads((ROOT/'ai_config.json').read_text(encoding='utf-8-sig'))
    allowed=('api_key','base_url','model','temperature','max_tokens','max_history','request_timeout','run_as_admin')
    clean={k:cfg[k] for k in allowed if k in cfg}
    clean['realtime_voice']=dict(cfg['realtime_voice'],input_device=None,output_device=None,owner_only=False)
    clean['realtime_voice']['workspace_id']='' if clean['realtime_voice'].get('provider')=='qianwen' else clean['realtime_voice'].get('workspace_id','')
    (STAGE/'ai_config.json').write_text(json.dumps(clean,ensure_ascii=False,indent=2),encoding='utf-8')
    library=json.loads((ROOT/'runtime/music/library.json').read_text(encoding='utf-8'));entry=library['晴天']
    source=Path(entry['path']);music=STAGE/'runtime/music';music.mkdir(parents=True,exist_ok=True)
    target=music/'qingtian-guga.wav';shutil.copy2(source,target)
    (music/'library.json').write_text(json.dumps({'晴天':dict(entry,path=target.name)},ensure_ascii=False,indent=2),encoding='utf-8')
    return clean

def build():
    stage()
    datas=[(STAGE/'ai_config.json','.'),(ROOT/'resources','resources'),(ROOT/'data','data'),(ROOT/'knowledge','knowledge'),(STAGE/'runtime/music','runtime/music')]
    for name in ('windows_ocr.ps1','windows_selection.ps1'):datas.append((ROOT/'tools'/name,'tools'))
    cmd=[sys.executable,'-m','PyInstaller','--noconfirm','--onedir','--windowed','--name','Guga','--contents-directory','.',
         '--distpath',str(OUT),'--workpath',str(ROOT/'build/pyinstaller'),'--specpath',str(ROOT/'build'),
         '--paths',str(ROOT),'--hidden-import','main','--collect-submodules','core','--collect-submodules','ui',
         '--collect-all','sounddevice','--collect-all','vosk','--collect-all','pythonnet','--hidden-import','clr',
         '--collect-submodules','OpenGL','--collect-all','av',
         '--hidden-import','edge_tts','--hidden-import','win32timezone','--hidden-import','PIL.ImageGrab']
    for excluded in ('torch','tensorflow','transformers','faster_whisper','onnxruntime','kaldi_native_fbank','OpenGL_accelerate','cv2','matplotlib','pandas','PyQt6','PySide6','PySide2','IPython','notebook','pytest'):
        cmd+=['--exclude-module',excluded]
    for source,dest in datas:cmd+=['--add-data',str(source)+';'+dest]
    cmd+=[str(ROOT/'tools/frozen_entry.py')]
    log=OUT/'build.log'
    import win32api,PyQt5
    # Qt's own plugin-path discovery can mangle non-ASCII user directories.
    # Import installed wheels through their verified Windows short path.
    packages=win32api.GetShortPathName(str(Path(PyQt5.__file__).parent.parent))
    env=dict(os.environ,PYTHONPATH=packages+os.pathsep+str(ROOT))
    with log.open('w',encoding='utf-8') as f:
        proc=subprocess.Popen(cmd,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,env=env)
        (OUT/'build-process.json').write_text(json.dumps(dict(pid=proc.pid,started=time.time())),encoding='utf-8')
        try:code=proc.wait(timeout=600)
        except subprocess.TimeoutExpired:
            subprocess.run(['taskkill','/PID',str(proc.pid),'/T','/F'],capture_output=True,timeout=10);raise
    if code:raise RuntimeError('PyInstaller failed; inspect private build.log')
    print(json.dumps(dict(ok=True,output=str(OUT/'Guga/Guga.exe'))))
if __name__=='__main__':build()
