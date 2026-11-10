"""真模型复合任务端到端探针：一条多步任务 + 每步回执与耗时。

用法：
  python tools/e2e_composite_task.py                 # 真模型 + 真桌面执行
  python tools/e2e_composite_task.py --dry-run       # 不需要 Key，只验证脚本链路
  python tools/e2e_composite_task.py "自定义复合任务" # 覆盖默认任务
  python tools/e2e_composite_task.py --timeout 600

真跑会真实打开应用、聚焦窗口、输入文字；不会向微信联系人发送消息。
"""
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from launcher import _prepare_qt
_prepare_qt()

from PyQt5.QtCore import QSettings, QTimer
from PyQt5.QtWidgets import QApplication

from core.ai_chat import AIChatEngine
from core.chat_workspace import ChatWorkspace
from ui.agent_chat import AgentChatWindow
from ui.pet_window import PetWindow

DEFAULT_TASK = '打开浏览器搜索“咕嘎桌面助手”，然后在记事本里写下搜到的第一条标题，保存到桌面 guga_e2e.txt'
DRY_TASK = '读取应用状态，然后把表情切换为开心，再读取一次应用状态确认。'


def config_or_exit():
    cfg = AIChatEngine._load_config()
    key = str(cfg.get('api_key') or '').strip()
    if not key or key == 'offline-only':
        print('SKIP: ai_config.json 没有可用 api_key；填好 Key 后重跑，或先用 --dry-run 验证脚本。')
        raise SystemExit(2)
    return cfg


def dry_replies():
    def call(tool, **args):
        return dict(role='assistant', content=None, tool_calls=[
            dict(id='dry-'+tool, type='function', function=dict(name=tool, arguments=json.dumps(args)))])

    return [call('app_state'), call('pet_control', action='set_expression', name='happy'),
            call('app_state'), dict(role='assistant', content='复合任务已完成：状态已读取，表情已切换，再次读取确认。')]


def main():
    task = DEFAULT_TASK
    dry = '--dry-run' in sys.argv
    timeout = 480
    for index, value in enumerate(sys.argv[1:], 1):
        if value == '--timeout' and index + 1 < len(sys.argv):
            timeout = max(60, int(sys.argv[index + 1]))
        elif not value.startswith('--'):
            task = value
    cfg = dict(api_key='offline-only') if dry else config_or_exit()
    if dry:
        task = DRY_TASK

    app = QApplication([])
    with tempfile.TemporaryDirectory() as folder, \
            patch('core.keyboard_hook.KeyboardHook.start'), patch('ui.tts_engine.TTSEngine.speak'):
        QSettings.setDefaultFormat(QSettings.IniFormat)
        QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, folder)
        pet = PetWindow()
        for timer in pet.findChildren(QTimer):
            timer.stop()
        panel = AgentChatWindow(pet, ChatWorkspace(Path(folder) / 'chat.sqlite3'))
        pet._agent_panel = panel
        panel.agent.config = cfg
        panel.show()
        print('任务:', task)
        print('模式:', 'dry-run（假模型）' if dry else '真模型 ' + str(cfg.get('model')))
        started = time.time()
        if dry:
            replies = dry_replies()
            patch.object(panel.agent, '_request', side_effect=lambda *a, **k: replies.pop(0)).start()
        panel.send(task)
        seen = 0
        timed_out = False
        while True:
            app.processEvents()
            events = panel.agent.journal.data.get('events', [])
            for event in events[seen:]:
                print('[%6.1fs] %s %s' % (event['time'] - started,
                    'OK  ' if event.get('ok') else 'FAIL', event.get('tool')))
            seen = len(events)
            if not panel.busy:
                break
            if time.time() - started > timeout:
                timed_out = True
                panel.agent.cancel_event.set()
                break
            time.sleep(.03)
        elapsed = time.time() - started
        status = panel.agent.journal.data
        text = ''
        for message in reversed(panel.store.messages(panel.active_id)):
            if message['role'] == 'assistant' and str(message.get('content') or '').strip():
                text = str(message['content'])
                break
        print('状态:', status.get('status'), '| 耗时: %.1fs' % elapsed, '| 工具回执: %d' % len(status.get('events', [])))
        print('最后回答:', text[:300] or '（无）')
        if status.get('failure_explanation'):
            print('失败说明:', str(status['failure_explanation'])[:500])
        ok = (not timed_out and status.get('status') == 'completed' and bool(text.strip()))
        print('RESULT:', 'PASS' if ok else 'FAIL')
        try:
            patch.stopall()
        except Exception:
            pass
        panel.shutdown()
        panel.hide()
        pet._anim.stop()
        pet._status.stop()
        pet._tray.hide()
        pet.hide()
        app.quit()
        raise SystemExit(0 if ok else 1)


if __name__ == '__main__':
    main()
