"""Finite offscreen UI smoke. No external API, game input, microphone or TTS."""
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from launcher import _prepare_qt
_prepare_qt()
from PyQt5.QtCore import QEventLoop, QTimer
from PyQt5.QtGui import QFontDatabase
from PyQt5.QtWidgets import QApplication
from core.bg_agent import DecisionEngine, local_decision
from ui.bg_agent_panel import BattlegroundAgentPanel


app = QApplication([])
for font in ("C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/msyhbd.ttc"):
    if Path(font).exists():
        QFontDatabase.addApplicationFont(font)
panel = BattlegroundAgentPanel()
panel.show()


def await_worker():
    loop = QEventLoop()
    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(loop.quit)
    if panel._worker:
        panel._worker.finished.connect(loop.quit)
        timer.start(4000)
        loop.exec_()
    if panel._worker and panel._worker.isRunning():
        panel._worker.requestInterruption()
        raise AssertionError("worker exceeded finite smoke-test budget")
    app.processEvents()


panel.analyze(False)
await_worker()
result = json.loads(panel.output.toPlainText())
assert result["action"]["entity_id"] == "shop-1"
assert panel.local_button.isEnabled()
assert not result["executable"]

if len(sys.argv) > 1:
    preview = Path(sys.argv[1])
    preview.parent.mkdir(parents=True, exist_ok=True)
    assert panel.grab().save(str(preview))

with tempfile.TemporaryDirectory() as folder:
    tags = {"game_id": "anonymous-import", "revision": 1, "patch": "reference", "source": "offline",
            "phase": "recruit", "local_controller": 1, "shop_controller": 9,
            "hero_entity_id": "h", "player_entity_id": "p", "entities": {
                "h": {"CARDTYPE": "HERO", "CONTROLLER": 1, "HEALTH": 30, "DAMAGE": 7},
                "p": {"CONTROLLER": 1, "RESOURCES": 6, "TEMP_RESOURCES": 1, "RESOURCES_USED": 3}}}
    path = Path(folder) / "anonymous.json"
    path.write_text(json.dumps(tags), encoding="utf-8")
    with patch("ui.bg_agent_panel.QFileDialog.getOpenFileName", return_value=(str(path), "JSON")):
        panel.import_snapshot()
    imported = json.loads(panel.input.toPlainText())
    assert imported["gold"] == 4 and imported["health"] == 23
    panel.load_demo()


class SlowEngine:
    config = {}

    def decide(self, snapshot, use_model):
        time.sleep(.08)
        return local_decision(snapshot)


panel.engine = SlowEngine()
panel.analyze(False)
raw = json.loads(panel.input.toPlainText())
raw["gold"] = 0
panel.input.setPlainText(json.dumps(raw))
await_worker()
assert not panel.output.toPlainText(), "late result must not overwrite edited input"
panel.engine = DecisionEngine()
panel.load_demo()
panel.engine = SlowEngine()
panel.analyze(False)
panel.close()
await_worker()
assert not panel.isVisible()
print("UI: local decision, stale-result discard, close-during-work: PASS")
