"""Bounded local UIA perception, separate from the action provider and cloud vision."""
import threading
import time


def _foreground():
    import win32gui,win32process
    hwnd=int(win32gui.GetForegroundWindow())
    return dict(hwnd=hwnd,pid=win32process.GetWindowThreadProcessId(hwnd)[1]) if hwnd else {}


def _key(window):return (window or {}).get('hwnd'),(window or {}).get('pid')


class LocalPerception:
    def __init__(self,service=None,foreground_provider=None):
        if service is None:
            from core.uia_service import UIAService
            service=UIAService()  # observation cannot occupy the action worker
        self.service=service;self.foreground_provider=foreground_provider or _foreground
        self.lock=threading.RLock();self.closed=False;self.busy=False;self.thread=None
        self.expected=None;self.window={};self.value={};self.at=0.;self.attempted=0.;self.error=''
        self.reads=0;self.failures=0
        self.retry_after=0.;self.consecutive_failures=0

    def request(self,window):
        window=dict(window or {});key=_key(window);now=time.monotonic()
        with self.lock:
            if self.closed:return
            if key!=self.expected:self.attempted=0.;self.expected=key;self.retry_after=0.;self.consecutive_failures=0
            if not key[0] or window.get('own_app') or self.busy or now<self.retry_after or now-self.attempted<1.:return
            self.busy=True;self.attempted=now
            def work():
                try:
                    self.service.warmup()
                    value=self.service.perceive(window['hwnd'])
                    current=self.foreground_provider()
                    with self.lock:
                        if not self.closed and self.expected==key and _key(current)==key:
                            self.value=value;self.window=window;self.at=time.monotonic();self.reads+=1;self.error='';self.consecutive_failures=0
                except Exception as exc:
                    with self.lock:
                        self.failures+=1;self.error=type(exc).__name__;self.consecutive_failures+=1
                        self.retry_after=time.monotonic()+min(30,2**min(self.consecutive_failures,5))
                finally:
                    with self.lock:self.busy=False
            self.thread=threading.Thread(target=work,name='guga-local-perception',daemon=True)
            self.thread.start()

    def context(self,window):
        with self.lock:
            age=time.monotonic()-self.at if self.at else None
            matches=bool(self.at and _key(window)==_key(self.window))
            fresh=bool(not self.closed and matches and age is not None and age<=2.)
            state=dict(source='windows_uia',local_only=True,fresh=fresh,window_matches=matches,
                age_seconds=round(age,2) if age is not None else None,reading=self.busy,
                reads=self.reads,failures=self.failures,error=self.error,
                elapsed_ms=self.value.get('elapsed_ms'),visual_content=False)
            if not fresh:return state
            # Prioritize fields and buttons so a concise voice context retains
            # actionable facts even when the page contains many links.
            items=list(self.value.get('elements',[]))
            priorities={'Edit':0,'ComboBox':0,'Button':1,'Document':2,'Text':3}
            items.sort(key=lambda item:priorities.get(item.get('type'),4))
            labels=[]
            for item in items:
                text=item.get('name') or '未命名'
                if item.get('value'):text+='，当前值：'+item['value']
                label=item.get('type','')+'：'+text
                if label not in labels:labels.append(label)
            state.update(context=('本机结构化控件实读；不含图片、视频或颜色判断。窗口：'+str(window.get('title',''))+
                '\n'+'\n'.join(labels))[:2600],elements=items[:160],truncated=self.value.get('truncated',False))
            return state

    def close(self):
        with self.lock:self.closed=True;self.value={};self.at=0.
        # A stuck provider has a finite IPC timeout. Closing a call from Qt must
        # not wait on that IPC lock; the separate cleanup worker reaps it.
        if self.thread and self.thread.is_alive():
            threading.Thread(target=self.service.close,name='guga-perception-cleanup',daemon=True).start()
        else:self.service.close()
