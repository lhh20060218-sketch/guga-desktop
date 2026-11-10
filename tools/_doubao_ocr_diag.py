# -*- coding: utf-8 -*-
"""诊断豆包 adapter OCR 抓屏"""
import os, sys, time
sys.path.insert(0, r'd:\rengongzhineng\guga-competition')
os.environ['GUGA_HOME'] = r'd:\rengongzhineng\guga-competition\dist\e2e-20261110ac-r21\home'

import win32gui, win32con
from core.computer_control import _ensure_foreground

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

# Focus
win32gui.ShowWindow(hwnd, 9)
win32gui.SetForegroundWindow(hwnd)
time.sleep(0.5)

# Get words via adapter's own method
from core.adapters.dispatch import adapter_for
_, a = adapter_for('doubao')

# Find composer ref
hwnd_info = a._ensure_window()
print('hwnd_info:', hwnd_info)

# Capture before
text_before, words_before, img_before = a._capture_words(hwnd)
print('\n=== BEFORE (beforewords count):', len(words_before))
for w in words_before[:10]:
    print(f'  y={w.get("y",0):.2f} text={w.get("text","")[:40]}')
print('  ...')
for w in words_before[-5:]:
    print(f'  y={w.get("y",0):.2f} text={w.get("text","")[:40]}')

prompt = '测试通过'
head, tail = a._fingerprint(prompt)
print(f'\nfingerprint: head={head!r} tail={tail!r}')
bubble_before, _, _ = a._bubble_hits(words_before, prompt)
print(f'bubble_before={bubble_before}')

# Press Enter
print('\n=== Press Enter ===')
a._press_send(hwnd)
time.sleep(2)

# Capture after
text_after, words_after, img_after = a._capture_words(hwnd)
print('\n=== AFTER words count:', len(words_after))
for w in words_after[:10]:
    print(f'  y={w.get("y",0):.2f} text={w.get("text","")[:40]}')
print('  ...')
for w in words_after[-10:]:
    print(f'  y={w.get("y",0):.2f} text={w.get("text","")[:40]}')

bubble_after, _, _ = a._bubble_hits(words_after, prompt)
print(f'\nbubble_after={bubble_after} (before={bubble_before})')

# Also count all text lines with y<0.76
from core.adapters.doubao_adapter import _group_lines
lines_before = [l for l in _group_lines(words_before) if l["y"] < 0.76]
lines_after = [l for l in _group_lines(words_after) if l["y"] < 0.76]
print(f'\n对话区行数 before={len(lines_before)} after={len(lines_after)}')
for l in lines_before[:3]: print(f'  BEFORE y={l["y"]:.2f}: {l["text"][:50]}')
for l in lines_after[-5:]: print(f'  AFTER  y={l["y"]:.2f}: {l["text"][:50]}')
