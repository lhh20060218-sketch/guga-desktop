"""Bounded live Edge TTS + Qt playback check; no paid fallback or microphone.

Run with the same Python as the pet: python tools/diag_tts.py
Plays one generic sentence and exits within 30 seconds.
"""
import json
import sys
from importlib.metadata import version
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from launcher import _prepare_qt

_prepare_qt()
from PyQt5.QtCore import QTimer
from PyQt5.QtMultimedia import QMediaPlayer
from PyQt5.QtWidgets import QApplication
from ui.tts_engine import TTSEngine


def main():
    app = QApplication([])
    tts = TTSEngine()
    # Verify Edge itself, without consuming any configured paid TTS quota.
    tts._use_doubao = False
    result = {
        'edge_version': version('edge-tts'),
        'voice': tts.EDGE_VOICE,
        'rate': tts.EDGE_RATE,
        'pitch': tts.EDGE_PITCH,
        'available': tts._player.isAvailable(),
        'played': False,
        'position_ms': 0,
        'ended': False,
        'timed_out': False,
        'player_error': 0,
    }

    def state_changed(state):
        if state == QMediaPlayer.PlayingState:
            result['played'] = True

    def position_changed(position):
        result['position_ms'] = max(result['position_ms'], position)

    def media_changed(status):
        if status == QMediaPlayer.EndOfMedia:
            result['ended'] = True

    def player_error(error):
        result['player_error'] = int(error)

    def timeout():
        result['timed_out'] = True
        tts.stop()
        app.quit()

    tts._player.stateChanged.connect(state_changed)
    tts._player.positionChanged.connect(position_changed)
    tts._player.mediaStatusChanged.connect(media_changed)
    tts._player.error.connect(player_error)
    tts.speak_finished.connect(lambda: QTimer.singleShot(300, app.quit))
    QTimer.singleShot(30000, timeout)
    QTimer.singleShot(100, lambda: tts.speak('咕嘎，本鹅回来啦。'))
    app.exec_()
    tts.stop()
    result['ok'] = (result['played'] and result['position_ms'] > 0
                    and result['ended'] and not result['timed_out']
                    and result['player_error'] == 0)
    print(json.dumps(result, ensure_ascii=True), flush=True)
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    sys.exit(main())
