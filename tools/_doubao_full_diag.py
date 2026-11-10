# -*- coding: utf-8 -*-
"""完整模拟豆包 adapter: inject → Enter → 看发不发"""
import os, sys, time
sys.path.insert(0, r'd:\rengongzhineng\guga-competition')
os.environ['GUGA_HOME'] = r'd:\rengongzhineng\guga-competition\dist\e2e-20261110ac-r21\home'

import win32gui, win32con

hwnds = []
def cb(h, _):
    if win32gui.IsWindowVisible(h):
        t = win32gui.GetWindowText(h)
        if '豆包' in t: hwnds.append((h, t))
win32gui.EnumWindows(cb, None)
if not hwnds:
    print('NO DOUBAO!')
    sys.exit(1)
hwnd = hwnds[0][0]
print('hwnd:', hwnd)

from core.adapters.dispatch import adapter_for
_, a = adapter_for('doubao')

# Focus
win32gui.ShowWindow(hwnd, 9)
win32gui.SetForegroundWindow(hwnd)
time.sleep(0.5)

# Capture before
text_before, words_before, _ = a._capture_words(hwnd)
print(f'\n[1] BEFORE: {len(words_before)} words')
from core.adapters.doubao_adapter import _group_lines
lines_before = [l for l in _group_lines(words_before) if l["y"] < 0.76]
print(f'    对话区: {len(lines_before)} lines')
for l in lines_before[-5:]:
    print(f'      y={l["y"]:.2f}: {l["text"][:50]}')

# Find composer + inject
print('\n[2] Finding composer...')
try:
    ref, ctrl = a._find_composer(hwnd)
    print(f'    composer ref={ref[:40] if ref else None}')
except Exception as e:
    print(f'    FAIL: {e}')
    ref = None

prompt = '测试通过123'
if ref:
    print(f'[3] Injecting "{prompt}"...')
    try:
        ref2, ok = a._inject_clipboard(hwnd, prompt, ref=ref)
        print(f'    inject ok={ok}')
    except Exception as e:
        print(f'    FAIL: {e}')

# Capture after inject, before Enter
text_mid, words_mid, _ = a._capture_words(hwnd)
lines_mid = [l for l in _group_lines(words_mid) if l["y"] > 0.76]  # 输入框区
print(f'\n[4] AFTER INJECT: composer area words (y>0.76): {len(lines_mid)}')
for l in lines_mid:
    print(f'      y={l["y"]:.2f}: {l["text"][:60]}')

# Enter!
print('\n[5] Press Enter...')
a._press_send(hwnd)
time.sleep(3)

# Capture after Enter
text_after, words_after, _ = a._capture_words(hwnd)
lines_after = [l for l in _group_lines(words_after) if l["y"] < 0.76]
print(f'[6] AFTER ENTER: 对话区: {len(lines_after)} lines (before was {len(lines_before)})')
for l in lines_before[:3]: print(f'  BEFORE y={l["y"]:.2f}: {l["text"][:50]}')
for l in lines_after[-8:]: print(f'  AFTER  y={l["y"]:.2f}: {l["text"][:50]}')

# Check fingerprint
head, tail = a._fingerprint(prompt)
print(f'\nfingerprint head={head!r}')
b_before, _, _ = a._bubble_hits(words_before, prompt)
b_after, _, _ = a._bubble_hits(words_after, prompt)
print(f'bubble_before={b_before} bubble_after={b_after}')

grew = len(a._norm(text_after)) - len(a._norm(text_before))
print(f'chars grew={grew:+d}')

print(f'\n=== RESULT: {"OK - new content!" if len(lines_after) > len(lines_before) or grew > 10 else "STUCK - no change"} ===')
