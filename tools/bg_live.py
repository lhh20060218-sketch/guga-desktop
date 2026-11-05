"""Open the same live-operation panel used by the desktop pet."""
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

if __name__=='__main__':
    from launcher import _prepare_qt
    _prepare_qt()
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtCore import QTimer
    from ui.bg_live_panel import BattlegroundLivePanel
    app=QApplication(sys.argv)
    panel=BattlegroundLivePanel()
    panel.show()
    if '--test-timeout' in sys.argv:
        QTimer.singleShot(240000,panel.close)
    if '--smoke-ui' in sys.argv:
        QTimer.singleShot(250,panel.close)
    sys.exit(app.exec_())
