"""Finite end-to-end test: owned on-screen highlight -> toolbar -> vision explanation/translation.

Only generated fixture text is captured. --live makes exactly two configured-model calls.
"""
import os,sys,json,time,tempfile,ctypes,argparse
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from launcher import _prepare_qt
_prepare_qt()
from PyQt5.QtCore import Qt,QSettings,QPoint
from PyQt5.QtGui import QFont,QTextCursor,QFontDatabase,QPixmap
from PyQt5.QtWidgets import QApplication,QDialog,QTextEdit,QWidget,QVBoxLayout,QLabel,QPushButton
from PyQt5.QtTest import QTest
from ui.screen_tools import ScreenTools


def pump(app,predicate,seconds):
    until=time.monotonic()+seconds
    while not predicate() and time.monotonic()<until:app.processEvents();time.sleep(.01)
    if not predicate():raise AssertionError('Bounded fixture step did not finish')


def run(live=False):
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling,True);QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps,True)
    app=QApplication([]);app.setQuitOnLastWindowClosed(False)
    for font in ('C:/Windows/Fonts/msyh.ttc','C:/Windows/Fonts/msyhbd.ttc','C:/Windows/Fonts/arial.ttf'):QFontDatabase.addApplicationFont(font)
    out=Path(__file__).resolve().parents[1]/'runtime/selection-visual-20261029';out.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as folder:
        pet=QWidget();pet._config=SimpleNamespace(_s=QSettings(str(Path(folder)/'settings.ini'),QSettings.IniFormat));pet._agent_bubble=QWidget()
        errors=[];pet._show_agent_bubble=lambda text,*args:errors.append(text)
        tools=ScreenTools(pet,register=False);pet._screen_tools=tools
        source=QDialog(None,Qt.Window|Qt.WindowStaysOnTopHint);source.setWindowTitle('咕嘎选词链路自测（合成文本，自动关闭）')
        layout=QVBoxLayout(source);layout.addWidget(QLabel('本窗口仅用于测试高亮文字识别，不含用户资料。'))
        editor=QTextEdit('An interface allows two programs to exchange information.\n\nA timeout means waiting too long for a response.')
        editor.setFont(QFont('Arial',18));editor.setStyleSheet('QTextEdit{background:white;color:#222;selection-background-color:#83b3ff;selection-color:#13253c;}')
        layout.addWidget(editor);source.resize(850,270);source.move(110,100);source.show();source.raise_();source.activateWindow();editor.setFocus()
        cursor=editor.textCursor();cursor.setPosition(3);cursor.setPosition(12,QTextCursor.KeepAnchor);editor.setTextCursor(cursor)
        clipboard=app.clipboard();before={k:bytes(clipboard.mimeData().data(k)) for k in clipboard.mimeData().formats()} if clipboard.mimeData() else {}
        records=[]
        try:
            until=time.monotonic()+.25
            while time.monotonic()<until:app.processEvents();time.sleep(.01)
            native=ctypes.wintypes.RECT();user=ctypes.windll.user32
            user.GetWindowRect.argtypes=[ctypes.wintypes.HWND,ctypes.POINTER(ctypes.wintypes.RECT)]
            user.GetWindowRect(int(editor.winId()),ctypes.byref(native))
            sx=(native.right-native.left)/editor.width();sy=(native.bottom-native.top)/editor.height()
            start=QTextCursor(editor.document());start.setPosition(3);end=QTextCursor(editor.document());end.setPosition(12)
            a=editor.cursorRect(start).center();b=editor.cursorRect(end).center()
            event=dict(hwnd=int(source.winId()),start_x=round(native.left+a.x()*sx),start_y=round(native.top+a.y()*sy),x=round(native.left+b.x()*sx),y=round(native.top+b.y()*sy),selection_gesture=True)
            with patch('core.computer_control._attach_focus',side_effect=AssertionError('Must not restore foreground')),patch('core.computer_control._send_keys',side_effect=AssertionError('Must not send Ctrl+C')):
                tools._selection_candidate(event);pump(app,lambda:tools.selection_bar.isVisible(),3)
                payload=dict(tools.selection_bar.payload)
                import base64
                (out/'fixture-selection.png').write_bytes(base64.b64decode(payload['image_url'].split(',',1)[1]))
                for index,mode in enumerate(('explain','translate')):
                    tools.selection_bar.present(payload,QPoint(330,220))
                    if live:
                        QTest.mouseClick(tools.selection_bar.findChildren(QPushButton)[index],Qt.LeftButton)
                        pump(app,lambda:tools.popup is not None and not tools.popup.pending,18)
                    else:
                        with patch('core.screen_question.explain',return_value='interface：接口，是程序之间交换信息的入口。'):
                            QTest.mouseClick(tools.selection_bar.findChildren(QPushButton)[index],Qt.LeftButton)
                            pump(app,lambda:tools.popup is not None and not tools.popup.pending,3)
                    answer=tools.popup.messages[-1] if tools.popup.messages else {}
                    text=answer.get('content','') if answer.get('role')=='assistant' else ''
                    ok=bool(text and '接口' in text and 'interface' in text.lower() and 'an interface' not in text.lower())
                    records.append(dict(mode=mode,ok=ok,answer=text[:220],image_preview=tools.popup.preview.isVisible()))
                    tools.popup.grab().save(str(out/(mode+'-preview.png')));tools.popup.close();app.processEvents()
            after={k:bytes(clipboard.mimeData().data(k)) for k in clipboard.mimeData().formats()} if clipboard.mimeData() else {}
            result=dict(ok=len(records)==2 and all(r['ok'] for r in records),live_api=live,clipboard_unchanged=before==after,no_foreground_restore=True,no_keyboard_copy=True,errors=errors,results=records)
            print(json.dumps(result,ensure_ascii=False));(out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
            return 0 if result['ok'] and result['clipboard_unchanged'] else 1
        finally:tools.stop();source.close();pet.close();pet._agent_bubble.close();app.processEvents()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--live',action='store_true');args=parser.parse_args();sys.exit(run(args.live))
