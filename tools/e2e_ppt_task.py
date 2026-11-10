"""PPT 闭环真模型探针：普通需求文字 → 模型自己写大纲 → 调 ppt 工具 → 打开校验。

用法：
  python tools/e2e_ppt_task.py                 # 默认需求文字
  python tools/e2e_ppt_task.py "自定义需求文字"
  python tools/e2e_ppt_task.py --timeout 420
"""
import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from launcher import _prepare_qt  # noqa: E402

_prepare_qt()

from PyQt5.QtCore import QSettings, QTimer  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

from core.chat_workspace import ChatWorkspace  # noqa: E402
from ui.agent_chat import AgentChatWindow  # noqa: E402
from ui.pet_window import PetWindow  # noqa: E402

PACKAGED_CONFIG = Path(os.environ.get('GUGA_E2E_CONFIG') or
                       Path(tempfile.gettempdir()) / 'GUGA' / 'ai_config.json')
DELIVERABLES = ROOT / 'runtime' / 'deliverables'
REQUIREMENT = (
    '下周公司内部技术分享，主题是“桌面 AI 助手如何把一句话变成可交付物”。'
    '我们手上有：语音入口、工具智能体、视觉自动化（无 API 软件）、跨软件派单到 JoyCode、本地出片。'
    '听众是产品与开发约 30 人，时长 20 分钟。'
    '请直接做一份能现场投屏的 PPT，6—8 页，每页给要点和讲者备注，放进工作区交付目录。'
)


def config_path():
    args = sys.argv[1:]
    for index, value in enumerate(args):
        if value == '--config' and index + 1 < len(args):
            return Path(args[index + 1])
    local = ROOT / 'ai_config.json'
    return local if local.is_file() else PACKAGED_CONFIG


def brief(value):
    if not isinstance(value, dict):
        return str(value)[:120]
    keep = ('ok', 'path', 'slides', 'texts', 'size', 'verification', 'submitted', 'verification',
            'message', 'titles')
    return json.dumps({k: value[k] for k in keep if k in value}, ensure_ascii=False)[:700]


def main():
    config = config_path()
    if not config.is_file():
        print('SKIP: 找不到 ai_config.json')
        raise SystemExit(2)
    cfg = json.loads(config.read_text(encoding='utf-8-sig'))
    if not str(cfg.get('api_key') or '').strip():
        print('SKIP: 没有 api_key')
        raise SystemExit(2)
    args = sys.argv[1:]
    timeout, task, skip_next = 420, REQUIREMENT, False
    for index, value in enumerate(args):
        if skip_next:
            skip_next = False
            continue
        if value in ('--config', '--timeout'):
            if value == '--timeout':
                timeout = max(120, int(args[index + 1]))
            skip_next = True
        elif not value.startswith('--'):
            task = value
    started = time.time()
    app = QApplication([])
    with tempfile.TemporaryDirectory() as folder, \
            __import__('unittest.mock', fromlist=['patch']).patch('core.keyboard_hook.KeyboardHook.start'), \
            __import__('unittest.mock', fromlist=['patch']).patch('ui.tts_engine.TTSEngine.speak'):
        QSettings.setDefaultFormat(QSettings.IniFormat)
        QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, folder)
        pet = PetWindow()
        for timer in pet.findChildren(QTimer):
            timer.stop()
        panel = AgentChatWindow(pet, ChatWorkspace(Path(folder) / 'chat.sqlite3'))
        pet._agent_panel = panel
        panel.agent.config = cfg
        panel.show()
        calls = []

        def on_activity(_session, payload):
            payload = payload or {}
            if payload.get('name') != 'ppt':
                return
            arguments = payload.get('arguments') or {}
            calls.append(arguments)
            outline = arguments.get('outline')
            if isinstance(outline, dict):
                outline = dict(outline, slides='%d 页' % len(outline.get('slides') or []))
            print('[%6.1fs] TOOL ppt %s -> %s' % (time.time() - started,
                  json.dumps({k: v for k, v in arguments.items() if k != 'outline'},
                             ensure_ascii=False),
                  brief(payload.get('result'))))

        panel.agent.activity.connect(on_activity)
        print('模型:', cfg.get('model'), '| 需求:', task[:120])
        panel.send(task, force_agent=True)
        while True:
            app.processEvents()
            if not panel.busy:
                break
            if time.time() - started > timeout:
                print('TIMEOUT')
                panel.agent.cancel_event.set()
                break
            time.sleep(.03)
        text = ''
        for message in reversed(panel.store.messages(panel.active_id)):
            if message['role'] == 'assistant' and str(message.get('content') or '').strip():
                text = str(message['content'])
                break
        fresh = [Path(p) for p in (
            list(DELIVERABLES.glob('*.pptx')) if DELIVERABLES.is_dir() else [])
            + list((ROOT / 'runtime' / 'agent-tasks').rglob('*.pptx'))]
        fresh = [p for p in fresh if p.stat().st_mtime >= started - 1]
        print('回执与耗时: %.1fs | ppt 调用 %d 次 | 新产物 %d 个'
              % (time.time() - started, len(calls), len(fresh)))
        ok = False
        for path in sorted(fresh):
            from core.ppt_builder import inspect
            data = inspect(path)
            print('产物:', data['path'], '| %d 页/%.1fKB' % (data['slides'], data['size'] / 1024))
            print('标题:', ' / '.join(x for x in data['titles'] if x))
            ok = ok or data['slides'] >= 5
        print('最后回答:', text[:300] or '（无）')
        print('RESULT:', 'PASS' if ok else 'FAIL')
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
