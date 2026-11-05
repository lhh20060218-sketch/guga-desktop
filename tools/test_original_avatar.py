"""Normal startup must keep the original art even with stale 3D preferences."""
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from launcher import _prepare_qt
_prepare_qt()
from PyQt5.QtCore import QSettings,QTimer,Qt
from PyQt5.QtGui import QImage,QPainter
from PyQt5.QtWidgets import QApplication
from core.config_manager import ConfigManager
from ui.pet_window import PetWindow
app=QApplication([])
with tempfile.TemporaryDirectory() as folder, patch('core.keyboard_hook.KeyboardHook.start'),patch('ui.tts_engine.TTSEngine.speak'):
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,folder)
    ConfigManager().avatar_mode='3d'
    with patch.object(sys,'argv',['main.py','--avatar-demo']),patch('ui.avatar_renderer.GLPenguinRenderer',side_effect=AssertionError('3D must not initialize')):
        pet=PetWindow()
        assert pet._anim is pet._anim2d and pet._anim3d is None
        pet._set_avatar_mode('3d')
        assert pet._anim is pet._anim2d
        pet._show_avatar_actions()
        assert pet._last_avatar_demo['state']=='disabled'
        assert not getattr(pet,'_avatar_demo_running',False)
        pet._ensure_pet_menu()
        assert not pet._menu_avatar_3d.isEnabled()
    # Render the original sprite directly, with no shell or 3D replacement.
    image=QImage(pet._anim.width,pet._anim.height,QImage.Format_ARGB32)
    image.fill(Qt.transparent);p=QPainter(image);pet._anim.draw(p,0,0);p.end()
    output=ROOT/'runtime/original-sprite-restored.png';image.save(str(output))
    for timer in pet.findChildren(QTimer):timer.stop()
    pet._anim.stop();pet._tray.hide();pet._pet_menu.hide();pet._self_mcp.close();pet.hide()
    print(json.dumps(dict(ok=True,original_sprite=True,stale_3d_preference_blocked=True,
                          automatic_demo_disabled=True,preview=str(output))))
