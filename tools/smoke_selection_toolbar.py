"""Finite native smoke test against an owned Qt editor; no network or user app input."""
import ctypes,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from launcher import _prepare_qt
_prepare_qt()
from PyQt5.QtCore import QTimer,Qt,QPoint
from PyQt5.QtGui import QTextCursor
from PyQt5.QtWidgets import QApplication,QDialog,QVBoxLayout,QTextEdit,QPushButton
from PyQt5.QtTest import QTest
from ui.screen_tools import SelectionBar
from ui.selection_clipboard import SelectionCopy


def run():
    app=QApplication([]);app.setQuitOnLastWindowClosed(False)
    dialog=QDialog();dialog.setWindowTitle('咕嘎 · 选词自测（自动关闭）')
    layout=QVBoxLayout(dialog);editor=QTextEdit('A selected interface in its paragraph.');layout.addWidget(editor)
    cursor=editor.textCursor();cursor.setPosition(11);cursor.setPosition(20,QTextCursor.KeepAnchor);editor.setTextCursor(cursor)
    expected=cursor.selectedText();clip=app.clipboard()
    before={k:bytes(clip.mimeData().data(k)) for k in clip.mimeData().formats()} if clip.mimeData() else {}
    result=dict(ok=False,clipboard_restored=False,non_activating=False)
    reader=SelectionCopy(dialog);bar=SelectionBar(dialog)
    user=ctypes.windll.user32;user.GetForegroundWindow.restype=ctypes.wintypes.HWND
    def finish(value):
        after={k:bytes(clip.mimeData().data(k)) for k in clip.mimeData().formats()} if clip.mimeData() else {}
        result.update(ok=bool(value.get('ok') and value.get('text')==expected),clipboard_restored=before==after)
        if not result['ok']:result['error']=value.get('error','selected text mismatch')
        bar.dismiss();dialog.hide();QTimer.singleShot(50,app.quit)
    reader.done.connect(finish)
    bar.chosen.connect(lambda mode,value:reader.read(value['source_hwnd']))
    def present():
        hwnd=int(dialog.winId());result.update(source_hwnd=hwnd,foreground_hwnd=user.GetForegroundWindow(),platform=app.platformName())
        if user.GetForegroundWindow()!=hwnd:
            finish(dict(ok=False,error='owned test editor did not receive foreground focus'));return
        bar.present(dict(source_hwnd=hwnd,selection_gesture=True),dialog.mapToGlobal(QPoint(140,100)))
        user.SendMessageW.argtypes=[ctypes.wintypes.HWND,ctypes.c_uint,ctypes.wintypes.WPARAM,ctypes.wintypes.LPARAM]
        result['mouse_activation_blocked']=user.SendMessageW(int(bar.winId()),0x0021,hwnd,0)==3
        QTimer.singleShot(250,lambda:click(hwnd))
    def click(hwnd):
        result['non_activating']=user.GetForegroundWindow()==hwnd
        buttons=bar.findChildren(QPushButton);QTest.mouseClick(buttons[1],Qt.LeftButton)
    dialog.resize(420,180);dialog.show();dialog.raise_();dialog.activateWindow();editor.setFocus()
    QTimer.singleShot(350,present);QTimer.singleShot(6000,app.quit)
    app.exec_();reader.stop();bar.hide();dialog.hide()
    print(json.dumps(result,ensure_ascii=False))
    return 0 if all(result.get(k) for k in ('ok','clipboard_restored','non_activating','mouse_activation_blocked')) else 1


if __name__=='__main__':sys.exit(run())
