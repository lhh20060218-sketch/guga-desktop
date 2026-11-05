"""Finite real Windows input test against this script's own disposable Qt window."""
import ctypes
from pathlib import Path
import sys
import tempfile
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from launcher import _prepare_qt
_prepare_qt()
try:ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
except OSError:pass
from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QApplication,QWidget,QVBoxLayout,QLabel,QLineEdit,QPushButton
from core.desktop_access import DesktopAccess
from core.computer_control import ComputerControl

app=QApplication([]);window=QWidget();window.setWindowTitle('咕嘎 · 自有窗口控制验证（自动关闭）')
window.resize(540,180);layout=QVBoxLayout(window)
layout.addWidget(QLabel('仅验证此窗口；不操作其他软件；最多8秒自动结束。'))
edit=QLineEdit();button=QPushButton('验证点击');layout.addWidget(edit);layout.addWidget(button)
clicked=[];button.clicked.connect(lambda:clicked.append(True));errors=[]
folder=tempfile.TemporaryDirectory();access=DesktopAccess(Path(folder.name)/'access.json');access.set_enabled(True)
control=ComputerControl(access);state=[0]
def step():
    try:
        import win32gui
        hwnd=int(window.winId())
        if win32gui.GetForegroundWindow()!=hwnd:raise RuntimeError('自有测试窗口不是前台，未发送输入')
        observation=control.execute(dict(action='observe',hwnd=hwnd));token=observation['observation_id']
        assert observation['_image_url'].startswith('data:image/jpeg;base64,')
        def click(widget):
            center=widget.mapToGlobal(widget.rect().center())
            control.execute(dict(action='click',observation_id=token,coordinate_space='desktop',x=center.x(),y=center.y()))
        if state[0]==0:click(edit)
        elif state[0]==1:control.execute(dict(action='type',observation_id=token,text='咕嘎中文输入 7316'))
        elif state[0]==2:
            assert edit.text()=='咕嘎中文输入 7316',repr(edit.text())
            control.execute(dict(action='hotkey',observation_id=token,keys='ctrl+a'))
        elif state[0]==3:control.execute(dict(action='type',observation_id=token,text='已验证'))
        elif state[0]==4:
            assert edit.text()=='已验证',repr(edit.text());click(button)
        else:
            assert clicked
            print('PASS: actual window screenshot, guarded clicks, Unicode input, Ctrl+A and verified button callback')
            window.close();app.quit();return
        state[0]+=1;QTimer.singleShot(120,step)
    except Exception as exc:
        errors.append(str(exc));window.close();app.quit()
def timeout():
    errors.append('8秒测试预算已到');window.close();app.quit()
window.show();window.raise_();window.activateWindow()
QTimer.singleShot(600,step);QTimer.singleShot(8000,timeout)
app.exec_();folder.cleanup()
if errors:raise SystemExit('; '.join(errors))
