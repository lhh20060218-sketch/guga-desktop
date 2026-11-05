"""Bounded human-trace observer with a same-version-only offline trainer."""
import json,os,subprocess,sys,time
from pathlib import Path
import psutil

ROOT=Path(__file__).resolve().parents[1]
ACTIVE=ROOT/'runtime/shadow-active.json'
ENGINE=ROOT/'runtime/bg-engine-current'
HDT=Path.home()/'Desktop/游戏/HDT/HearthstoneDeckTracker.exe'


def _alive(pid):
    try:return psutil.Process(int(pid)).status() not in (psutil.STATUS_ZOMBIE,psutil.STATUS_DEAD)
    except (psutil.Error,ValueError,TypeError):return False


class ShadowManager:
    def __init__(self):self.state={}
    def status(self):
        if not self.state and ACTIVE.exists():
            try:self.state=json.loads(ACTIVE.read_text(encoding='utf-8'))
            except (OSError,ValueError):pass
        hdt=next((p for p in psutil.process_iter(['pid','name']) if p.info['name']=='HearthstoneDeckTracker.exe'),None)
        return dict(self.state,observer_running=_alive(self.state.get('observer_pid')),
                    training_running=_alive(self.state.get('training_pid')),
                    hdt_running=bool(hdt),hdt_pid=hdt.pid if hdt else None,
                    client_patch=self._client_patch())
    @staticmethod
    def _client_patch():
        from core.bg_version import client_patch
        return client_patch()
    def start(self,seconds=900,train=True):
        seconds=max(30,min(int(seconds),1800))
        state=self.status()
        if state.get('observer_running'):raise RuntimeError('只读观察已经在运行')
        stamp=time.strftime('%Y%m%d-%H%M%S');observation=ROOT/'runtime/shadow-observations'/stamp
        training_output=ROOT/'runtime/bg-lab'/('shadow-training-'+stamp)
        flags=getattr(subprocess,'CREATE_NO_WINDOW',0);env=dict(os.environ,OMP_NUM_THREADS='2',MKL_NUM_THREADS='2')
        observer=subprocess.Popen([sys.executable,str(ROOT/'tools/observe_bg_logs.py'),'--seconds',str(seconds),
            '--output',str(observation)],cwd=ROOT,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=flags)
        self.state=dict(started_at=time.time(),observer_pid=observer.pid,training_pid=None,
            observation_output=str(observation),observation_seconds=seconds,
            training_output=str(training_output),training_started=False,client_patch=self._client_patch())
        if not next((p for p in psutil.process_iter(['name']) if p.info['name']=='HearthstoneDeckTracker.exe'),None) and HDT.is_file():
            subprocess.Popen([str(HDT)],cwd=str(HDT.parent),creationflags=flags)
        if train:
            try:
                from core.bg_version import verify_same_patch
                version=verify_same_patch(ENGINE)
                trainer=subprocess.Popen([sys.executable,str(ROOT/'tools/train_bg_selfplay.py'),'--engine',str(ENGINE),
                    '--output',str(training_output),'--bc-games','8','--rl-games','16','--eval-games','16',
                    '--max-seconds',str(min(seconds,900)),'--seed',str(int(time.time()))],cwd=ROOT,env=env,
                    stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=flags)
                self.state.update(training_pid=trainer.pid,training_started=True,**version)
            except Exception as exc:
                self.state.update(training_error=str(exc)[:240],
                    training_blocked_reason='offline_patch_must_equal_live_client')
        ACTIVE.write_text(json.dumps(self.state,ensure_ascii=False,indent=2),encoding='utf-8')
        return self.status()
    def stop(self):
        stopped=[]
        for key in ('training_pid','observer_pid'):
            pid=self.state.get(key)
            if pid and _alive(pid):
                try:psutil.Process(pid).terminate();stopped.append(key)
                except psutil.Error:pass
        self.state['stopped']=stopped;self.state['stopped_at']=time.time()
        ACTIVE.write_text(json.dumps(self.state,ensure_ascii=False,indent=2),encoding='utf-8')
        return self.status()
