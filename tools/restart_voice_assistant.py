"""Restart only the identified idle source runtime, preserving its Windows privilege."""
import ctypes,json,os,subprocess,sys,time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));os.chdir(ROOT)
OUTPUT=ROOT/'runtime/voice-assistant-qa/restart.json'


def restart(force=False):
    import psutil
    from launcher import _prepare_qt
    _prepare_qt()
    from PyQt5.QtCore import QCoreApplication
    from tools.guga_mcp_server import invoke
    app=QCoreApplication([])
    response=invoke('app_state',{});state=response.get('result',{})
    runtime=state.get('runtime',{})
    if not response.get('ok') or Path(runtime.get('project_root','')).resolve()!=ROOT:
        raise RuntimeError('Project identity mismatch; nothing stopped')
    from core.self_agent import HARNESS_VERSION
    if (not force and state.get('agent_harness_version')==HARNESS_VERSION and
        state.get('assistant_contract',{}).get('voice_control')=='local_mcp_start_status_stop_free_guard_v1' and
        state.get('assistant_contract',{}).get('screen_share',{}).get('capture_fps')):
        return dict(ok=True,already_loaded=True,new_pid=runtime['pid'],created=time.time())
    task_status=state.get('task',{}).get('status')
    if (state.get('voice_active') or state.get('dsh',{}).get('running') or
        task_status=='running' or state.get('assistant_contract',{}).get('fast_action_running')):
        raise RuntimeError('Active voice or execution; restart cancelled')
    elevated=bool(ctypes.windll.shell32.IsUserAnAdmin())
    if state.get('local_access',{}).get('administrator')!=elevated:
        raise RuntimeError('Privilege mismatch; nothing stopped')
    old=psutil.Process(int(runtime['pid']));args=old.cmdline()
    if old.name().lower()!='pythonw.exe' or not (Path(old.cwd()).resolve()==ROOT or any(str(ROOT).casefold() in a.casefold() for a in args)):
        raise RuntimeError('Process identity mismatch; nothing stopped')
    interpreter=old.exe();old_pid=old.pid
    music=state.get('music',{})
    if music.get('playing'):
        receipt=ROOT/'runtime/personal-harness/restart.json';receipt.parent.mkdir(parents=True,exist_ok=True)
        receipt.write_text(json.dumps(dict(created=time.time(),music=music)),encoding='utf-8')
    old.terminate();old.wait(8)
    new=subprocess.Popen([interpreter,str(ROOT/'launcher.py')],cwd=str(ROOT),creationflags=subprocess.CREATE_NO_WINDOW)
    return dict(ok=True,old_pid=old_pid,new_pid=new.pid,administrator=elevated,created=time.time())


if __name__=='__main__':
    try:result=restart(force='--force' in sys.argv)
    except Exception as exc:result=dict(ok=False,error=type(exc).__name__+': '+str(exc))
    OUTPUT.parent.mkdir(parents=True,exist_ok=True)
    OUTPUT.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
