# -*- coding: utf-8 -*-
"""M3 装配契约冒烟: 无真 PyQt5 环境验证 butler_attach 装配链.

实机(有 PyQt5)直接跑 python main.py 做真机验证; 本脚本用于沙盒/CI 回归.
运行: python scripts/smoke_butler_attach.py
"""
import sys
import types
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))


def _install_qt_stub():
    try:
        import PyQt5  # noqa: F401
        return
    except ImportError:
        pass

    class _Signal:
        def __init__(self, *a, **k):
            pass

        def __get__(self, obj, cls=None):
            if obj is None:
                return self
            name = '_sig_%d' % id(self)
            if name not in obj.__dict__:
                slots = []

                def connect(self, slot):
                    slots.append(slot)

                def emit(self, *a):
                    for f in list(slots):
                        f(*a)
                obj.__dict__[name] = type('_B', (),
                                          {'connect': connect, 'emit': emit})()
            return obj.__dict__[name]

    class QObject:
        def __init__(self, *a, **k):
            pass

    class QTimer:
        timeout = _Signal()

        def __init__(self, *a, **k):
            pass

        def setInterval(self, v):
            pass

        def start(self):
            pass

        @staticmethod
        def singleShot(*a, **k):
            pass

    class _FakeAction:
        pass

    class _FakeMenu:
        def addAction(self, t):
            return _FakeAction()

        def addSeparator(self):
            return None

    class QMenu:
        def addMenu(self, t):
            return _FakeMenu()

        def addAction(self, t):
            return _FakeAction()

        def addSeparator(self):
            return None

    class QInputDialog:
        @staticmethod
        def getText(*a, **k):
            return ('', False)

    qtcore = types.ModuleType('PyQt5.QtCore')
    qtcore.QObject, qtcore.pyqtSignal, qtcore.QTimer = QObject, _Signal, QTimer
    qtwidgets = types.ModuleType('PyQt5.QtWidgets')
    qtwidgets.QMenu, qtwidgets.QInputDialog = QMenu, QInputDialog
    pkg = types.ModuleType('PyQt5')
    pkg.QtCore, pkg.QtWidgets = qtcore, qtwidgets
    sys.modules['PyQt5'] = pkg
    sys.modules['PyQt5.QtCore'] = qtcore
    sys.modules['PyQt5.QtWidgets'] = qtwidgets
    print('(无真 PyQt5, 使用桩信号 — 装配契约验证)')


def main():
    _install_qt_stub()
    from core.ai_chat import AIChatEngine
    from core.butler_reminder import ReminderService
    from ui.butler_attach import attach_butler

    class FakeAnim:
        pass

    class FakeTTS:
        def __init__(self):
            self.lines = []

        def speak(self, t):
            self.lines.append(t)
            print('  [TTS]', t[:46])

    class FakePet:
        def __init__(self):
            self._anim = FakeAnim()
            self._tts = FakeTTS()
            self._ai = AIChatEngine()

        def _ensure_pet_menu(self):
            return _FakeMenu2()

        def _say_with_expression(self, *a, **k):
            pass

    class _FakeMenu2:
        def addMenu(self, t):
            return type('_M', (), {'addAction': lambda s, x: _FakeAction2(),
                                   'addSeparator': lambda s: None})()

    class _FakeAction2:
        pass

    pet = FakePet()
    rt = attach_butler(pet)
    # 冒烟不污染真实待办: 把提醒服务换成临时文件
    import tempfile
    rt.reminders = ReminderService(
        path=str(Path(tempfile.mkdtemp()) / 'reminders.json'))
    rt.announcer.bind(rt.reminders)
    assert rt is not None and rt.mm.current_id == 'butler', '装配失败'
    print('attach OK: current = %s | provider 挂载: %s | persona 挂载: %s'
          % (rt.mm.current_id, pet._ai._rag_provider is not None,
             pet._ai._persona_fn is not None))
    assert pet._ai._rag_provider is not None
    assert pet._ai._persona_fn is not None

    rt.mm._animator = type('A', (), {
        'clips': {},
        'play_clip': lambda s, n, loop=False: None,
        '_load_action_frames': lambda s, *a, **k: None})()
    assert rt.summon('scholar') and rt.mm.current_id == 'scholar'
    print('summon(scholar) OK')
    rt.summon('butler')
    assert rt.mm.current_id == 'butler'
    print('召回管家 OK')

    rt.reminders.add('+1m', '试点提醒')
    rt._tick()
    print('提醒录入+巡检 OK, 待办: %d' % len(rt.reminders.list_pending()))
    assert len(pet._tts.lines) >= 2, '应有召唤+召回两条报幕'
    print('\n=== M3 装配契约冒烟 全部通过 ===')


if __name__ == '__main__':
    main()
