"""Persistent, bounded UIA provider process; no UI-thread calls or action retry."""
import atexit
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]


class UIAService:
    def __init__(self):
        self.lock=threading.RLock();self.process=None;self.replies=None;self._timeouts=0
        atexit.register(self.close)

    def _start(self):
        if self.process and self.process.poll() is None:return
        command=([sys.executable,'--uia-worker'] if getattr(sys,'frozen',False) else
                 [sys.executable,'-u',str(ROOT/'tools/uia_worker.py')])
        self.replies=queue.Queue(maxsize=32)
        self.process=subprocess.Popen(command,cwd=str(ROOT),stdin=subprocess.PIPE,stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,text=True,encoding='utf-8',env=dict(os.environ,PYTHONIOENCODING='utf-8'),
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        process=self.process;replies=self.replies
        def receive():
            try:
                for line in process.stdout:
                    try:value=json.loads(line)
                    except ValueError:continue
                    try:replies.put_nowait(value)
                    except queue.Full:break
            except (OSError,UnicodeError):pass
            finally:
                try:replies.put_nowait(dict(closed=True))
                except queue.Full:pass
        threading.Thread(target=receive,name='guga-uia-replies',daemon=True).start()

    def call(self,method,hwnd=0,timeout=2.5,**arguments):
        from core.uia_backend import UIAUnavailable
        started=time.monotonic()
        if not self.lock.acquire(timeout=timeout):raise RuntimeError('UIA正忙，本次未发送操作')
        try:
            self._start();ident=uuid.uuid4().hex
            if time.monotonic()-started>=timeout:raise RuntimeError('UIA等待已超时，本次未发送操作')
            payload=dict(id=ident,method=method,hwnd=int(hwnd),arguments=arguments)
            try:
                self.process.stdin.write(json.dumps(payload,ensure_ascii=False)+'\n');self.process.stdin.flush()
                deadline=started+timeout
                while True:
                    reply=self.replies.get(timeout=max(.001,deadline-time.monotonic()))
                    if reply.get('closed'):raise OSError('provider closed')
                    if reply.get('id')==ident:break
                if not reply.get('ok'):
                    error=reply.get('error','UIA操作失败')
                    if reply.get('unavailable'):raise UIAUnavailable(error)
                    raise RuntimeError(error)
                self._timeouts=0
                return reply['result']
            except (queue.Empty,OSError,BrokenPipeError) as exc:
                # A single timeout does not mean a broken provider: replies are
                # matched by request id, so a late answer is discarded safely.
                # Restarting on every timeout used to cost seconds per step and
                # made cross-app runs look flaky. Only stop after repeated
                # timeouts or a dead pipe.
                self._timeouts=0 if isinstance(exc,OSError) else self._timeouts+1
                if isinstance(exc,OSError) or self._timeouts>=2:
                    self._timeouts=0;self.close()
                    raise RuntimeError('UIA执行器超时或中断，已停止该执行器；操作结果不确定，请先核对，未自动重试') from None
                raise RuntimeError('UIA执行器本次响应超时；执行器仍在运行，操作结果不确定，请先核对再继续，未自动重试') from None
        finally:self.lock.release()

    def warmup(self):return self.call('warmup',timeout=4)
    def snapshot(self,hwnd,limit=240,time_budget=1.5):return self.call('snapshot',hwnd,limit=limit,time_budget=time_budget)
    def read(self,hwnd,**selector):return self.call('read',hwnd,**selector)
    def focused(self,hwnd):return self.call('focused',hwnd)
    def page_input(self,hwnd,search=False):return self.call('page_input',hwnd,search=search)
    def first_edit(self,hwnd):return self.call('first_edit',hwnd,timeout=5.0)
    def composer(self,hwnd,time_budget=4.0):return self.call('composer',hwnd,timeout=max(4.0,float(time_budget)+1.0),time_budget=float(time_budget))
    def perceive(self,hwnd,limit=160):return self.call('perceive',hwnd,timeout=1.5,limit=limit)
    def text(self,hwnd,limit=6000):return self.call('text',hwnd,timeout=5.0,limit=limit)
    def from_point(self,x,y):return self.call('from_point',0,timeout=4.0,x=int(x),y=int(y))
    def value(self,hwnd,ref):return self.call('value',hwnd,timeout=3.0,ref=ref)
    def text_of(self,hwnd,ref,limit=4000):return self.call('text_of',hwnd,timeout=3.0,ref=ref,limit=limit)
    def act(self,hwnd,operation,**arguments):return self.call('act',hwnd,operation=operation,**arguments)
    def scroll_state(self,hwnd,**arguments):return self.call('scroll_state',hwnd,timeout=3.0,**arguments)
    def wait(self,hwnd,seconds=5,**arguments):return self.call('wait',hwnd,timeout=min(32,seconds+1),seconds=seconds,**arguments)

    def close(self):
        with self.lock:
            process=self.process;self.process=None
            if process:
                if process.poll() is None:
                    process.terminate()
                    try:process.wait(1)
                    except subprocess.TimeoutExpired:process.kill();process.wait(1)
                for stream in (process.stdin,process.stdout):
                    if stream:
                        try:stream.close()
                        except OSError:pass


_service=None
_service_lock=threading.Lock()
def shared_service():
    global _service
    with _service_lock:
        if _service is None:_service=UIAService()
        return _service


def serve():
    for stream in (sys.stdin,sys.stdout):
        if hasattr(stream,'reconfigure'):stream.reconfigure(encoding='utf-8')
    import pythoncom
    pythoncom.CoInitializeEx(pythoncom.COINIT_MULTITHREADED)
    from core.uia_backend import UIABackend,UIAUnavailable
    backend=None
    try:
        for line in sys.stdin:
            request={}
            try:
                request=json.loads(line);method=request['method'];hwnd=int(request.get('hwnd',0))
                if backend is None:backend=UIABackend()
                if method=='warmup':result=dict(ready=True)
                elif method in ('snapshot','read','focused','page_input','perceive','act','wait',
                                'text','from_point','first_edit','value','scroll_state',
                                'composer','text_of'):
                    if method=='act':
                        import win32gui
                        if win32gui.GetForegroundWindow()!=hwnd:raise RuntimeError('前台窗口已变化，未发送操作')
                    result=getattr(backend,method)(hwnd,**request.get('arguments',{}))
                else:raise ValueError('未知UIA方法')
                response=dict(id=request['id'],ok=True,result=result)
            except Exception as exc:
                response=dict(id=request.get('id'),ok=False,error=str(exc)[:400],unavailable=isinstance(exc,UIAUnavailable))
            sys.stdout.write(json.dumps(response,ensure_ascii=False)+'\n');sys.stdout.flush()
    finally:pythoncom.CoUninitialize()
