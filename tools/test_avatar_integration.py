"""App-owned Qt test: switching, menu latency, music and GL fallback.
No capture of other applications, microphone, model call or sent message.
"""
import json
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from launcher import _prepare_qt
_prepare_qt()
from PyQt5.QtCore import QSettings,QTimer,QPoint,Qt
from PyQt5.QtGui import QContextMenuEvent
from PyQt5.QtWidgets import QApplication
from PyQt5.QtTest import QTest
from ui.pet_window import PetWindow
from ui.agent_chat import AgentChatWindow
from core.chat_workspace import ChatWorkspace

app=QApplication([])
# Explicit developer-only opt-in: production never loads the rejected shell.
sys.argv.append('--experimental-avatar-3d')
with tempfile.TemporaryDirectory() as folder, patch('core.keyboard_hook.KeyboardHook.start'), patch('ui.tts_engine.TTSEngine.speak'):
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,folder)
    from core.config_manager import ConfigManager
    ConfigManager().avatar_mode='3d'
    pet=PetWindow()
    for timer in pet.findChildren(QTimer):timer.stop()
    assert pet._anim3d is pet._anim and pet._anim3d is not None,pet._appearance_error
    canvas_size=pet.size()
    pet._perform_gesture('sunglasses');pet._perform_gesture('dance')
    pet._anim.mouth_open=.6
    pet._set_avatar_mode('illustration',persist=False)
    assert pet._anim is pet._anim2d and pet._anim.sunglasses and pet._anim.dancing
    assert not pet._anim3d._timer.isActive()
    pet._set_avatar_mode('3d',persist=False)
    assert pet.size()==canvas_size and pet._anim.sunglasses and pet._anim.dancing
    assert pet._anim.mouth_open==.6 and not pet._anim2d._timer.isActive()
    panel=AgentChatWindow(pet,ChatWorkspace(Path(folder)/'chat.sqlite3'))
    pet._agent_panel=panel
    panel._music_event(dict(type='playing',title='local-test'))
    assert pet._anim.sunglasses and pet._anim.dancing
    assert pet._anim._sunglasses_until==0
    panel._music_event(dict(type='stopped'))
    assert not pet._anim.sunglasses and not pet._anim.dancing
    pet._set_avatar_mode('illustration',persist=False)
    callbacks=[]
    with patch('ui.pet_window.QTimer.singleShot',side_effect=lambda ms,cb:callbacks.append((ms,cb))):
        pet._show_avatar_actions()
    assert pet._anim is pet._anim3d and pet._avatar_demo_running
    next(cb for ms,cb in callbacks if ms==15000)()
    assert pet._anim is pet._anim2d and not pet._avatar_demo_running
    assert pet._last_avatar_demo['state']=='completed'
    # A manual appearance choice cancels every pending demo event.
    callbacks=[]
    with patch('ui.pet_window.QTimer.singleShot',side_effect=lambda ms,cb:callbacks.append((ms,cb))):
        pet._show_avatar_actions()
    pet._set_avatar_mode('illustration',persist=True)
    for _,cb in callbacks:cb()
    assert pet._anim is pet._anim2d and not pet._avatar_demo_running
    assert pet._last_avatar_demo['state']=='cancelled'
    pet._set_avatar_mode('3d',persist=False)
    # Dragging is an animation input; Qt retains the original movement path.
    pet._anim.set_dragging(True,100);pet._anim.motion.advance(.1)
    assert pet._anim.motion.pose.roll>0
    pet._anim.set_dragging(False)
    pet._ensure_pet_menu()
    durations=[]
    for _ in range(2):
        started=time.perf_counter()
        event=QContextMenuEvent(QContextMenuEvent.Mouse,QPoint(100,100),pet.mapToGlobal(QPoint(100,100)))
        pet.contextMenuEvent(event);app.processEvents()
        assert pet._pet_menu.isVisible()
        durations.append(round((time.perf_counter()-started)*1000,2))
        pet._pet_menu.hide();app.processEvents()
    # Fault injection verifies fallback using the actual paint path.
    failed=pet._anim3d
    with patch.object(failed,'paint_image',return_value=None):
        pet.grab()
    app.processEvents()
    assert pet._anim is pet._anim2d and pet._anim3d is None
    # The last valid 2D frame remains visible after a driver failure.
    assert not pet.grab().isNull()
    for timer in pet.findChildren(QTimer):timer.stop()
    pet._anim2d.stop();pet._tray.hide();pet._pet_menu.hide()
    panel.shutdown()
    pet._self_mcp.close()
    pet.hide()
    print(json.dumps(dict(ok=True,mode_switch=True,music=True,fallback=True,menu_open_ms=durations)))
