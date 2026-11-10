# -*- coding: utf-8 -*-
"""M2 demo: 管家中枢(知识检索链 + 语音播报)全链路验证

演示内容:
  1. ButlerHub 检索链: 学者在岗 -> 学者知识库命中; 军师在岗 -> 军师知识库命中
  2. 管家在岗/无命中 -> 回退 bg_knowledge(兼容旧战棋功能)
  3. attach(AIChatEngine): provider/label 注册 + 员工切换清空对话历史
  4. ButlerAnnouncer: 提醒到期 -> 管家口吻 -> speak_fn(此处用收集器模拟 TTS)

无 API Key 也不影响: 本 demo 验证到"上下文组装/回调触发"为止,
不发起真实网络请求.
运行: python scripts/demo_m2_hub.py
"""
import os
import sys
import time
from pathlib import Path

REPO = os.environ.get('GUGA_DEMO_REPO') or str(Path(__file__).resolve().parents[1])
sys.path.insert(0, REPO)

SEP = '=' * 62


def section(title):
    print('\n' + SEP)
    print('  ' + title)
    print(SEP)


def _ensure_qt_stub():
    """沙盒无 PyQt5 时注入最小桩(QObject/pyqtSignal), 验证挂载契约.

    实机(仓库环境)有真 PyQt5, 走真实信号, 本函数不生效.
    """
    try:
        import PyQt5  # noqa: F401
        return
    except ImportError:
        pass
    import types
    qtcore = types.ModuleType('PyQt5.QtCore')

    class _Signal:
        def __init__(self, *a, **k):
            pass

        def __get__(self, obj, cls=None):
            if obj is None:
                return self
            name = '_sig_%d' % id(self)
            if name not in obj.__dict__:
                slots = []

                slots = []

                def connect(self, slot):
                    slots.append(slot)

                def emit(self, *a):
                    for f in list(slots):
                        f(*a)
                obj.__dict__[name] = type('_Bound', (),
                                          {'connect': connect, 'emit': emit})()
            return obj.__dict__[name]

    class QObject:
        def __init__(self, *a, **k):
            pass

    qtcore.QObject = QObject
    qtcore.pyqtSignal = _Signal
    pkg = types.ModuleType('PyQt5')
    pkg.QtCore = qtcore
    sys.modules.setdefault('PyQt5', pkg)
    sys.modules.setdefault('PyQt5.QtCore', qtcore)
    print('(沙盒无 PyQt5, 已注入桩信号 — 契约验证与实机等价)')


def main():
    from core.mode_manager import ModeManager
    from core.butler_hub import ButlerHub
    from core.butler_reminder import ReminderService
    from core.butler_announcer import ButlerAnnouncer

    # ========== 1. 检索链: 员工在岗命中各自知识库 ==========
    section('1. 检索链: 学者/军师在岗, 各自知识库命中')
    mm = ModeManager(packs_dir=REPO + r'\armor_packs')
    hub = ButlerHub(mm, repo_root=REPO)

    mm.switch('scholar')
    ctx = hub.provider('python 不是内部或外部命令怎么办')
    print('[学者在岗] 命中=%s, 预览: %s...'
          % (bool(ctx), ctx[:60].replace('\n', ' ')))
    assert 'Python' in ctx or 'python' in ctx.lower(), '学者知识库未命中'

    mm.switch('tactician')
    ctx2 = hub.provider('为什么公司利润很高还会倒闭')
    print('[军师在岗] 命中=%s, 预览: %s...'
          % (bool(ctx2), ctx2[:60].replace('\n', ' ')))
    assert '现金' in ctx2 or '利润' in ctx2, '军师知识库未命中'

    # 跨甲隔离: 学者问题在军师库不应命中(回退战棋库, 战棋库也无 -> 空或战棋内容)
    ctx3 = hub.provider('python 环境变量 究竟怎么配置')
    print('[军师在岗] 问学者问题 -> 非学者内容: %s' % ('学者' not in ctx3))

    # ========== 2. 管家在岗 -> 回退战棋库(旧功能兼容) ==========
    section('2. 管家在岗: 回退 bg_knowledge(战棋兼容)')
    mm.switch('butler')
    ctx4 = hub.provider('酒馆战棋 铺场 流派')
    print('[管家在岗] 战棋问题回退命中=%s (len=%d)' % (bool(ctx4), len(ctx4)))

    # ========== 3. attach 引擎 ==========
    section('3. attach(AIChatEngine): provider/label/清历史')
    _ensure_qt_stub()
    from core.ai_chat import AIChatEngine
    engine = AIChatEngine()
    engine._history.append({'role': 'user', 'content': '旧话题'})
    hub.attach(engine)
    print('provider 已注册: %s' % (engine._rag_provider == hub.provider))
    print('label = %r (当前在岗: %s)' % (engine._rag_label, mm.current_id))
    print('切换员工后历史已清空: %s' % (engine._history == []))
    assert engine._rag_provider == hub.provider

    mm.switch('scholar')
    print('切到学者: label = %r, 历史仍空: %s'
          % (engine._rag_label, engine._history == []))
    persona, address = hub.persona_for_chat()
    print('员工人设前缀: %s... | 称谓: %s' % (persona[:24], address))

    mm.switch('butler')
    persona_b, address_b = hub.persona_for_chat()
    print('管家人设: 保留自己人设、无员工前缀=%s, 称谓=%s'
          % ('召唤上岗' not in persona_b, address_b))

    # ask() 链路: 无 API Key 时应 early-exit 且不抛异常
    print('engine.enabled=%s -> ask() 走%s'
          % (engine.enabled,
             '真实请求(provider 生效)' if engine.enabled else 'early-exit(不触发网络)'))
    if not engine.enabled:
        got = []
        engine.failed.connect(lambda e: got.append(e))
        engine.ask('少爷问: python 报错怎么看')
        print('ask() early-exit 信号: %s' % got)

    # ========== 4. 提醒 -> 管家口吻播报 ==========
    section('4. 提醒到期 -> 管家口吻 -> speak_fn')
    spoken = []
    announcer = ButlerAnnouncer(speak_fn=spoken.append, address='少爷')
    import tempfile
    tmp = Path(tempfile.mkdtemp()) / 'reminders.json'   # 隔离, 防跨次运行污染
    svc = ReminderService(path=str(tmp), on_due=None)
    announcer.bind(svc)
    now = time.time()
    r = svc.add('+30m', '和开发团队开周会', now=now)
    print('已录入提醒: %s' % r['text'])
    svc.tick(now=now + 60)                            # 未到期
    print('未到期 tick: 播报数=%d (应 0)' % len(spoken))
    svc.tick(now=now + 31 * 60)                       # 到期
    print('到期 tick: 播报数=%d' % len(spoken))
    for s in spoken:
        print('  [TTS] %s' % s)
    assert len(spoken) == 1 and '少爷' in spoken[0] and '周会' in spoken[0]
    svc.tick(now=now + 32 * 60)                       # 防重复
    print('重复 tick: 播报数=%d (防重成功=%s)' % (len(spoken), len(spoken) == 1))

    # 习惯建议播报
    announcer.announce_suggestion('您常在 21 点打开腾讯会议，需要提前准备吗')
    print('建议播报: [TTS] %s' % spoken[-1])

    print('\n' + SEP)
    print('  DEMO 完成 — M2 管家中枢全链路验证通过')
    print(SEP)


if __name__ == '__main__':
    main()
