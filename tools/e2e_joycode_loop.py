"""JoyCode 闭环真模型探针：模型派单 → 视觉层触发 → 读回执 → 依据回执决定下一步。

不是写死脚本：每一步由模型看上一轮工具回执后自己选，探针只打印回执与耗时。

用法：
  python tools/e2e_joycode_loop.py                     # 默认任务，真模型
  python tools/e2e_joycode_loop.py --timeout 900
  python tools/e2e_joycode_loop.py --config <路径>     # 指定 ai_config.json
  python tools/e2e_joycode_loop.py "自定义任务"
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
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from launcher import _prepare_qt  # noqa: E402

_prepare_qt()

from PyQt5.QtCore import QSettings, QTimer  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

from core.ai_chat import AIChatEngine  # noqa: E402
from core.chat_workspace import ChatWorkspace  # noqa: E402
from ui.agent_chat import AgentChatWindow  # noqa: E402
from ui.pet_window import PetWindow  # noqa: E402

PACKAGED_CONFIG = Path(os.environ.get('GUGA_E2E_CONFIG') or
                       Path(tempfile.gettempdir()) / 'GUGA' / 'ai_config.json')
E2E_DIR = os.environ.get('GUGA_E2E_DIR') or str(Path(tempfile.gettempdir()) / 'guga-e2e')
DEFAULT_TASK = (
    '演示任务，只能用 joycode 工具，不要自己写文件：'
    '1) joycode(action="dispatch", goal="在 ' + E2E_DIR + ' 新建 joycode-demo.md，正文包含 GUGALOOP-DEMO 和一句给咕嘎的说明", '
    'acceptance="joycode-demo.md 存在且正文包含 GUGALOOP-DEMO")；'
    '若 ok=false，读 detail.error 判断原因；只要拿到 task_id，就用 joycode(action="prompt", text="/guga-run <task_id>") '
    '把命令送进 IDE，不要放弃；'
    '2) 用 task_id 反复 joycode(action="receipt", task_id=<task_id>, seconds=45)；'
    'found=false 就继续查，最多 6 次；'
    '3) found=true 后汇报 status 与 self_check 前 200 字，并说明你依据哪些回执字段决定下一步。'
)
KEEP = ('action', 'goal', 'acceptance', 'task_id', 'text', 'seconds', 'auto', 'launch')


def config_path():
    for index, value in enumerate(sys.argv[1:], 1):
        if value == '--config' and index + 1 < len(sys.argv):
            return Path(sys.argv[index + 1])
    local = ROOT / 'ai_config.json'
    if local.is_file():
        return local
    return PACKAGED_CONFIG


def brief(value):
    """只留下结构化回执的关键字段，不把原始日志塞进探针输出。"""
    if not isinstance(value, dict):
        return str(value)[:120]
    keys = ('ok', 'task_id', 'found', 'error', 'detail', 'status', 'submitted', 'filled', 'text_found',
            'pending', 'elapsed_ms', 'hint', 'manual', 'point', 'steps', 'verification', 'receipt',
            'trigger', 'launched', 'launch_error', 'identity')
    out = {}
    for key in keys:
        if key in value:
            item = value[key]
            if key == 'receipt' and isinstance(item, dict):
                item = dict(task_id=item.get('task_id'), status=item.get('status'),
                            self_check=str(item.get('self_check') or '')[:160])
            out[key] = item
    return json.dumps(out, ensure_ascii=False)[:900]


def main():
    config = config_path()
    if not config.is_file():
        print('SKIP: 找不到 ai_config.json，真模型闭环无法运行')
        raise SystemExit(2)
    cfg = json.loads(config.read_text(encoding='utf-8-sig'))
    if not str(cfg.get('api_key') or '').strip():
        print('SKIP: 配置里没有 api_key')
        raise SystemExit(2)
    task = DEFAULT_TASK
    timeout = 900
    args = sys.argv[1:]
    skip_next = False
    for index, value in enumerate(args):
        if skip_next:
            skip_next = False
            continue
        if value in ('--config', '--timeout'):
            if value == '--timeout' and index + 1 < len(args):
                timeout = max(120, int(args[index + 1]))
            skip_next = True
            continue
        if not value.startswith('--'):
            task = value

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
        started = time.time()
        print('模型:', cfg.get('model'), '| 任务:', task[:160])
        seen_events = 0

        def on_activity(_session, payload):
            payload = payload or {}
            name = payload.get('name')
            if name != 'joycode':
                return
            arguments = payload.get('arguments') or {}
            compact = {k: (v[:60] + '…' if isinstance(v, str) and len(v) > 60 else v)
                       for k, v in arguments.items() if k in KEEP}
            print('[%6.1fs] TOOL joycode %s -> %s' % (time.time() - started,
                  json.dumps(compact, ensure_ascii=False), brief(payload.get('result'))))

        panel.agent.activity.connect(on_activity)
        panel.send(task, force_agent=True)
        while True:
            app.processEvents()
            events = panel.agent.journal.data.get('events', [])
            for event in events[seen_events:]:
                print('[%6.1fs] %s %s' % (event['time'] - started,
                      'OK  ' if event.get('ok') else 'FAIL', event.get('tool')))
            seen_events = len(events)
            if not panel.busy:
                break
            if time.time() - started > timeout:
                print('TIMEOUT: %.0f 秒仍未结束' % timeout)
                panel.agent.cancel_event.set()
                break
            time.sleep(.03)
        status = panel.agent.journal.data
        text = ''
        for message in reversed(panel.store.messages(panel.active_id)):
            if message['role'] == 'assistant' and str(message.get('content') or '').strip():
                text = str(message['content'])
                break
        tasks = status.get('operations')
        task_ids = [row.get('task_id') for row in tasks if isinstance(row, dict) and row.get('task_id')] \
            if isinstance(tasks, list) else []
        receipts = {}
        for task_id in set(task_ids):
            path = ROOT / '.guga' / 'outbox' / (str(task_id) + '.json')
            receipts[str(task_id)] = path.is_file()
        print('状态:', status.get('status'), '| 耗时: %.1fs' % (time.time() - started),
              '| 工具回执: %d' % len(status.get('events', [])))
        print('回执文件:', json.dumps(receipts, ensure_ascii=False))
        print('最后回答:', text[:400] or '（无）')
        ok = (status.get('status') == 'completed' and bool(text.strip())
              and any(receipts.values()))
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
