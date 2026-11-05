"""Read a selection only after clicking Explain/Translate, restoring clipboard data."""
import ctypes
from ctypes import wintypes
import time
import os
from PyQt5.QtCore import QObject,QTimer,QMimeData,pyqtSignal
from PyQt5.QtWidgets import QApplication


class GuiInfo(ctypes.Structure):
    _fields_=[('size',wintypes.DWORD),('flags',wintypes.DWORD),('active',wintypes.HWND),
              ('focus',wintypes.HWND),('capture',wintypes.HWND),('menu_owner',wintypes.HWND),
              ('move_size',wintypes.HWND),('caret',wintypes.HWND),('caret_rect',wintypes.RECT)]


class SelectionCopy(QObject):
    done=pyqtSignal(object)
    def __init__(self,parent=None):
        super().__init__(parent);self.busy=False;self.saved=None
        self.timer=QTimer(self);self.timer.setInterval(40);self.timer.timeout.connect(self.poll)

    def read(self,hwnd,restore_source=False):
        if self.busy:return
        user=ctypes.windll.user32;user.GetForegroundWindow.restype=wintypes.HWND
        user.IsWindow.argtypes=[wintypes.HWND]
        user.GetClipboardOwner.restype=wintypes.HWND
        user.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
        if not user.IsWindow(hwnd):
            self.done.emit(dict(ok=False,error='原选词窗口已切换，请重新选词后再点解释或翻译'));return
        foreground=user.GetForegroundWindow();pid=wintypes.DWORD()
        if foreground:user.GetWindowThreadProcessId(foreground,ctypes.byref(pid))
        if foreground!=hwnd:
            # An explicit click on our selection bar authorizes returning to its
            # recorded source, including when another selection bar took focus.
            # Other callers still cannot move focus away from an unrelated app.
            if pid.value!=os.getpid() and not restore_source:
                self.done.emit(dict(ok=False,error='原选词窗口已切换，请重新选词后再点解释或翻译'));return
            from core.computer_control import _attach_focus
            if not _attach_focus(hwnd):
                self.done.emit(dict(ok=False,error='未能恢复原选词窗口的焦点，请在原窗口重新选词'));return
        clip=QApplication.clipboard();self.saved=QMimeData();total=0
        for name in clip.mimeData().formats() if clip.mimeData() else []:
            value=clip.mimeData().data(name);total+=value.size()
            if total>16_000_000:
                self.saved=None;self.done.emit(dict(ok=False,error='剪贴板内容较大，未执行复制；可使用截图提问'));return
            self.saved.setData(name,value)
        self.hwnd=hwnd;self.source_pid=wintypes.DWORD();user.GetWindowThreadProcessId(hwnd,ctypes.byref(self.source_pid))
        self.busy=True;self.before=user.GetClipboardSequenceNumber();self.deadline=time.monotonic()+1.2
        from core.computer_control import _send_keys
        info=GuiInfo();info.size=ctypes.sizeof(info)
        try:
            if user.GetGUIThreadInfo(0,ctypes.byref(info)) and info.flags & (4|16):
                _send_keys([27]);QTimer.singleShot(80,self.copy)
            else:self.copy()
        except Exception as exc:self.fail(str(exc))

    def copy(self):
        if not self.busy:return
        from core.computer_control import _send_keys
        try:
            if ctypes.windll.user32.GetForegroundWindow()!=self.hwnd:
                self.fail('原选词窗口已切换，请重新选词');return
            _send_keys([17,67]);self.timer.start()
        except Exception as exc:self.fail(str(exc))

    def fail(self,error):
        self.timer.stop();self.saved=None;self.busy=False
        self.done.emit(dict(ok=False,error=error))

    def poll(self):
        if not self.busy:return
        sequence=ctypes.windll.user32.GetClipboardSequenceNumber()
        if sequence!=self.before:
            user=ctypes.windll.user32;owner=user.GetClipboardOwner();pid=wintypes.DWORD()
            if owner:user.GetWindowThreadProcessId(owner,ctypes.byref(pid))
            if pid.value!=self.source_pid.value:
                self.fail('剪贴板被其他程序改变，未读取或覆盖内容，请重新选词');return
            self.timer.stop();text=QApplication.clipboard().text().strip()[:2000]
            if ctypes.windll.user32.GetClipboardSequenceNumber()==sequence:QApplication.clipboard().setMimeData(self.saved)
            self.saved=None;self.busy=False
            self.done.emit(dict(ok=bool(text),text=text,error='' if text else '当前选区不是可复制的文字，请使用截图提问'))
        elif time.monotonic()>self.deadline:
            self.timer.stop();self.saved=None;self.busy=False
            self.done.emit(dict(ok=False,error='没有复制到选中文字，请重新选词或使用截图提问'))

    def stop(self):
        # Copy is normally restored by poll. Flush a completed copy before exit.
        if self.busy:self.poll()
        self.timer.stop();self.saved=None;self.busy=False
