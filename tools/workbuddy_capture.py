"""WorkBuddy 回答抓取（真实 UI）：新建任务 → 发需求 → 判定生成结束 → 全选复制回读 → 落任务包。

用法：
  python tools/workbuddy_capture.py --runs 2
  python tools/workbuddy_capture.py "自定义需求"
"""
import argparse
import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import win32clipboard as clip  # noqa: E402
import win32con  # noqa: E402
from PIL import ImageGrab  # noqa: E402

from core.computer_control import ComputerControl, _ensure_foreground, _send_keys  # noqa: E402
from core.window_inventory import list_windows  # noqa: E402

BUSY = ('深度思考中', '正在生成', '已处理', '生成中', '正在思考', '停止生成', '正在调用')

PROMPTS = [
    '请只输出文本，不要执行任何文件或网页操作，也不要创建任务文件。'
    '帮我写一段可以直接交给代码生成工具的高质量提示词：制作一个介绍“桌面 AI 助手”产品的官网，'
    '要求说明页面结构、视觉风格、交互细节、响应式要求和可验收标准，中文，1200 字以上。',
    '请只输出文本，不要执行任何文件或网页操作，也不要创建任务文件。'
    '为一个面向小学生的天文科普网站写一段可直接交给代码生成工具的提示词，'
    '覆盖首页、星球百科、互动问答三个板块，说明配色、动效、无障碍和验收标准，中文，1200 字以上。',
]


def window():
    for item in list_windows('workbuddy'):
        return item
    raise SystemExit('WorkBuddy 未运行')


def rect(hwnd):
    import ctypes
    box = ctypes.wintypes.RECT()
    ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(box))
    return box.left, box.top, box.right, box.bottom


def click_ratio(hwnd, rx, ry):
    import ctypes
    left, top, right, bottom = rect(hwnd)
    x, y = int(left + (right - left) * rx), int(top + (bottom - top) * ry)
    user = ctypes.windll.user32
    user.SetCursorPos(x, y)
    time.sleep(0.1)
    user.mouse_event(2, 0, 0, 0, 0)
    user.mouse_event(4, 0, 0, 0, 0)
    time.sleep(0.22)


def read_clip():
    for _ in range(6):
        try:
            clip.OpenClipboard()
            try:
                return clip.GetClipboardData(win32con.CF_UNICODETEXT) or ''
            finally:
                clip.CloseClipboard()
        except Exception:
            time.sleep(0.12)
    return ''


def grab(hwnd):
    """页面全选 + 复制；返回页面纯文本（含会话标题、提问、回答、页脚）。"""
    click_ratio(hwnd, 0.620, 0.240)
    _send_keys([17, 65])
    time.sleep(0.2)
    _send_keys([17, 67])
    time.sleep(0.55)
    return read_clip()


def extract_answer(page, prompt):
    """从整页文本里截出回答正文：提问之后、时间戳/模型页脚之前。

    页面里找不到本次提问锚点，说明这单没真正发出去（或还在旧会话页面）；
    此时返回空串，由调用方判失败，禁止把旧页面正文当成本次回答。
    """
    import re
    anchor = prompt.strip()[-18:]
    index = page.rfind(anchor)
    if index < 0:
        return ''
    body = page[index + len(anchor):]
    body = body.split('DeepSeek-V4.1-Flash')[0].replace('\ufeff', '').replace('\u200b', '')
    lines = [line.strip() for line in body.splitlines()]
    drop = lambda line: (not line or line == 'WorkBuddy' or re.match(r'^\d{1,2}:\d{2}$', line)
                         or re.match('^已处理', line))
    while lines and drop(lines[0]):
        lines.pop(0)
    while lines and drop(lines[-1]):
        lines.pop()
    return '\n'.join(lines)


def looks_done(page):
    """回答已结束的页脚证据：尾部出现独立时间戳行，且没有生成中状态词。"""
    import re
    tail = page[-300:]
    return bool(re.search(r'\r?\n\d{1,2}:\d{2}\r?\n', tail)) and not any(word in tail for word in BUSY)


def run(index, prompt, out_root):
    item = window()
    hwnd = item['hwnd']
    _ensure_foreground(hwnd, 3)
    click_ratio(hwnd, 0.043, 0.120)          # 新建任务
    time.sleep(1.6)
    click_ratio(hwnd, 0.621, 0.452)          # 首页居中输入框
    ComputerControl._paste_multiline(prompt, hwnd, __import__('threading').Event())
    time.sleep(0.5)
    started = time.perf_counter()
    _send_keys([13])
    polls, same, previous, last = [], 0, '', ''
    while time.perf_counter() - started < 240:
        began = time.perf_counter()
        text = grab(hwnd)
        cost = int((time.perf_counter() - began) * 1000)
        busy = [word for word in BUSY if word in text]
        digest = hashlib.md5(text.encode('utf-8')).hexdigest()
        same = same + 1 if digest == previous else 0
        previous, last = digest, text
        elapsed = int((time.perf_counter() - started) * 1000)
        polls.append(dict(at_ms=elapsed, chars=len(text), busy=busy, stable=same, grab_ms=cost))
        print('  [%6.1fs] %5d 字 busy=%s stable=%d' % (elapsed / 1000, len(text), busy, same), flush=True)
        anchor_ok = prompt.strip()[-18:] in text
        if same >= 2 and not busy and looks_done(text) and anchor_ok:
            settle = grab(hwnd)
            polls.append(dict(at_ms=int((time.perf_counter() - started) * 1000), chars=len(settle),
                              busy=[], stable=same + 1, grab_ms=0))
            answer = extract_answer(settle, prompt)
            if not answer:
                raise SystemExit('SUBMIT-FAILED 页面里没有本次提问（可能没发出去），不落任务包、不判成功')
            folder = out_root / ('workbuddy-%s' % datetime.now().strftime('%H%M%S'))
            folder.mkdir(parents=True, exist_ok=True)
            (folder / 'prompt.txt').write_text(prompt, encoding='utf-8')
            (folder / 'page.txt').write_text(settle, encoding='utf-8')
            (folder / 'answer.txt').write_text(answer, encoding='utf-8')
            package = dict(task_id=folder.name, source='workbuddy-ui', created=datetime.now().isoformat(timespec='seconds'),
                           prompt_path=str(folder / 'prompt.txt'), answer_path=str(folder / 'answer.txt'),
                           answer_chars=len(answer), page_chars=len(settle),
                           elapsed_ms=int((time.perf_counter() - started) * 1000),
                           capture_method='uia+select-all-copy', polls=polls,
                           next_step='把 answer.txt 作为 JoyCode 派单正文')
            (folder / 'package.json').write_text(json.dumps(package, ensure_ascii=False, indent=2), encoding='utf-8')
            shot = folder / 'screen.png'
            ImageGrab.grab(bbox=(-8, -8, 1928, 1048)).save(shot)
            print('  -> %d 字 / %d ms / %s' % (len(answer), package['elapsed_ms'], folder), flush=True)
            return package
        time.sleep(1.4)
    raise SystemExit('TIMEOUT 等待 WorkBuddy 完成')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('prompt', nargs='?')
    parser.add_argument('--runs', type=int, default=2)
    args = parser.parse_args()
    out_root = ROOT / 'runtime' / 'agent-tasks'
    results = []
    for index in range(args.runs):
        prompt = args.prompt if args.prompt and args.runs == 1 else PROMPTS[index % len(PROMPTS)]
        print('[run %d] 需求 %d 字' % (index + 1, len(prompt)))
        package = run(index, prompt, out_root)
        results.append({k: package[k] for k in ('task_id', 'answer_chars', 'page_chars', 'elapsed_ms')})
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
