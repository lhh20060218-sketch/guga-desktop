"""Finite offscreen desktop integration smoke; no external APIs or microphone."""
import os
import sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from launcher import _prepare_qt
_prepare_qt()
from PyQt5.QtCore import QTimer
from PyQt5.QtGui import QFontDatabase
from PyQt5.QtWidgets import QApplication
from ui.pet_window import PetWindow
from ui.voice_dialog import VoiceCallDialog
from core.realtime_voice import RealtimeVoice

app = QApplication([])
for font_path in ('C:/Windows/Fonts/msyh.ttc', 'C:/Windows/Fonts/msyhbd.ttc', 'C:/Windows/Fonts/segoeui.ttf'):
    if Path(font_path).exists():
        QFontDatabase.addApplicationFont(font_path)
with patch('core.keyboard_hook.KeyboardHook.start'), patch('ui.tts_engine.TTSEngine.speak'):
    pet = PetWindow()
    engine = RealtimeVoice(pet)
    pet._realtime_voice = engine
    panel = VoiceCallDialog(engine, pet)
    pet._voice_call_panel = panel
    panel.show()
    panel._append('饲养员', '我想连续聊一会儿。')
    panel._append('咕嘎', '咕嘎，饲养员，本鹅在听呢。')
    panel._status('持续通话中 · 可以直接说话')
    panel._usage(dict(rounds=1, reported_total_tokens=224, unreported_rounds=0,
        last_round=dict(round=1, usage=dict(total_tokens=224, input_tokens=156, output_tokens=68,
            input_text_tokens=156, input_audio_tokens=None, output_text_tokens=14, output_audio_tokens=53))))
    def finish():
        assert any(a.text() == '🎙 长语音 · 咕嘎智能体' for a in pet._tray.contextMenu().actions())
        assert '连续聊' in panel.transcript.toPlainText()
        assert panel.last_tokens.text() == '224'
        output = Path(__file__).resolve().parents[1] / 'runtime/chat/legacy-voice-preview.png'
        output.parent.mkdir(parents=True, exist_ok=True)
        panel.grab().save(str(output))
        for timer in pet.findChildren(QTimer):
            timer.stop()
        panel.close()
        pet._anim.stop()
        pet._status.stop()
        pet._tray.hide()
        print('Desktop + call panel + tray actions: PASS', flush=True)
        app.quit()
    QTimer.singleShot(150, finish)
    app.exec_()
