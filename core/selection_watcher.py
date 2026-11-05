"""Observe selection gestures only. Hook callback never reads text or blocks input."""
import ctypes
from ctypes import wintypes
from collections import deque
import os
from PyQt5.QtCore import QObject,QTimer,pyqtSignal


class MouseInfo(ctypes.Structure):
    _fields_=[('pt',wintypes.POINT),('mouseData',wintypes.DWORD),('flags',wintypes.DWORD),
              ('time',wintypes.DWORD),('extra',ctypes.c_size_t)]


class SelectionWatcher(QObject):
    candidate=pyqtSignal(object)
    def __init__(self,parent=None):
        super().__init__(parent);self.handle=None;self.queue=deque(maxlen=2);self.down=None;self.last_up=None
        self.timer=QTimer(self);self.timer.setInterval(40);self.timer.timeout.connect(self.flush)

    def start(self):
        if self.handle:return True
        user=ctypes.windll.user32
        user.GetForegroundWindow.restype=wintypes.HWND
        user.WindowFromPoint.argtypes=[wintypes.POINT];user.WindowFromPoint.restype=wintypes.HWND
        user.GetAncestor.argtypes=[wintypes.HWND,wintypes.UINT];user.GetAncestor.restype=wintypes.HWND
        user.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
        self.proc_type=ctypes.WINFUNCTYPE(ctypes.c_ssize_t,ctypes.c_int,wintypes.WPARAM,wintypes.LPARAM)
        self.proc=self.proc_type(self.callback)
        user.SetWindowsHookExW.argtypes=[ctypes.c_int,self.proc_type,wintypes.HINSTANCE,wintypes.DWORD]
        user.SetWindowsHookExW.restype=ctypes.c_void_p
        user.CallNextHookEx.argtypes=[ctypes.c_void_p,ctypes.c_int,wintypes.WPARAM,wintypes.LPARAM]
        user.CallNextHookEx.restype=ctypes.c_ssize_t
        self.handle=user.SetWindowsHookExW(14,self.proc,None,0)
        if self.handle:self.timer.start()
        return bool(self.handle)

    def callback(self,code,message,pointer):
        try:
            if code>=0:
                info=ctypes.cast(pointer,ctypes.POINTER(MouseInfo)).contents
                x,y,t=info.pt.x,info.pt.y,info.time
                if message==0x0201:
                    user=ctypes.windll.user32
                    under=user.WindowFromPoint(wintypes.POINT(x,y));hwnd=user.GetAncestor(under,2) if under else None
                    if not hwnd:hwnd=user.GetForegroundWindow()
                    self.down=(x,y,hwnd)
                    pid=wintypes.DWORD()
                    if hwnd:user.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
                    if hwnd and pid.value!=os.getpid():self.queue.append(dict(kind='dismiss'))
                elif message==0x0202:
                    drag=self.down is not None and abs(x-self.down[0])+abs(y-self.down[1])>7
                    double=bool(self.last_up and (t-self.last_up[2])%2**32<420 and abs(x-self.last_up[0])+abs(y-self.last_up[1])<8)
                    if drag or double:
                        hwnd=self.down[2] if self.down else ctypes.windll.user32.GetForegroundWindow();pid=wintypes.DWORD()
                        ctypes.windll.user32.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
                        if hwnd and pid.value!=os.getpid():self.queue.append(dict(kind='selection',hwnd=int(hwnd),x=x,y=y,start_x=self.down[0] if self.down else x,start_y=self.down[1] if self.down else y,selection_gesture=True))
                    self.down=None;self.last_up=(x,y,t)
        except Exception:pass
        return ctypes.windll.user32.CallNextHookEx(self.handle,code,message,pointer)

    def flush(self):
        if self.queue:
            value=self.queue.pop();self.queue.clear();self.candidate.emit(value)

    def stop(self):
        self.timer.stop();self.queue.clear()
        if self.handle:
            ctypes.windll.user32.UnhookWindowsHookEx.argtypes=[ctypes.c_void_p]
            ctypes.windll.user32.UnhookWindowsHookEx(self.handle);self.handle=None
