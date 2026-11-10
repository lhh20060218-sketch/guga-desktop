"""零额度成片闭环真模型探针：需求文字 → 模型自己拆分镜 → 调 video 工具 → 本地合成并核验。

用法：
  python tools/e2e_video_task.py                 # 默认需求文字
  python tools/e2e_video_task.py "自定义需求文字"
  python tools/e2e_video_task.py --timeout 420
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
    '给比赛演示做一条 20—40 秒的产品介绍短片，主题是“一句话交给咕嘎，最后落成可交付物”。'
    '要求你先把文案拆成分镜：每镜一句解说（会烧成字幕）+ 一句画面描述；'
    '画面由本地绘制，不调用需要额度的生图接口；带配音和字幕，直接出 mp4。'
    '调用 video 工具时用默认的本地合成，不要传 source_path。'
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
    keep = ('ok', 'route', 'path', 'seconds', 'audio', 'verified', 'voice',
            'fallback_from', 'fallback_reason', 'timings', 'error', 'message')
    return json.dumps({k: value[k] for k in keep if k in value}, ensure_ascii=False)[:900]


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
            if payload.get('name') != 'video':
                return
            arguments = payload.get('arguments') or {}
            calls.append(arguments)
            script = arguments.get('script')
            shots = len(script.get('shots') or []) if isinstance(script, dict) else 0
            print('[%6.1fs] TOOL video %s / %d 镜 -> %s' % (time.time() - started,
                  json.dumps({k: v for k, v in arguments.items() if k != 'script'}, ensure_ascii=False),
                  shots, brief(payload.get('result'))))

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
        candidates = list(DELIVERABLES.glob('*.mp4')) if DELIVERABLES.is_dir() else []
        candidates += list((ROOT / 'runtime' / 'agent-tasks').rglob('*.mp4'))
        fresh = [p for p in candidates if p.stat().st_mtime >= started - 1]
        print('回执与耗时: %.1fs | video 调用 %d 次 | 新产物 %d 个'
              % (time.time() - started, len(calls), len(fresh)))
        ok = False
        for path in sorted(fresh):
            from core import video_studio
            data = video_studio.inspect(path)
            print('产物:', data['path'], '| %.1fs / %.1fKB / 音轨=%s'
                  % (data['seconds'], data['size'] / 1024, data['audio']))
            ok = ok or (calls and 20 <= data['seconds'] <= 40.5)
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
