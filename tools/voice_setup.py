"""Standalone setup; no pet restart, capture or API requests."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from launcher import _prepare_qt
_prepare_qt()
from PyQt5.QtWidgets import QApplication
from ui.voice_dialog import VoiceSettingsDialog
app = QApplication(sys.argv)
dialog = VoiceSettingsDialog()
dialog.exec_()
