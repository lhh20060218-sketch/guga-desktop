# -*- coding: utf-8 -*-
"""逐步调豆包 adapter，看哪步导致崩"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ['GUGA_HOME'] = r'd:\rengongzhineng\guga-competition\dist\e2e-20261110ac-r21\home'

def check():
    import win32gui
    hwnds = []
    def cb(h, _):
        if win32gui.IsWindowVisible(h):
            t = win32gui.GetWindowText(h)
            if '豆包' in t: hwnds.append((h, t))
    win32gui.EnumWindows(cb, None)
    return (len(hwnds) > 0), (hwnds[0][0] if hwnds else 0)

import win32gui, win32con

alive, hwnd = check()
print(f'[0] alive={alive} hwnd={hwnd}')
if not alive:
    print('豆包不在！')
    sys.exit(1)

# Focus it
import ctypes
user32 = ctypes.windll.user32
win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
win32gui.SetForegroundWindow(hwnd)
time.sleep(0.5)
print(f'[0.5] fg={win32gui.GetForegroundWindow()} match={win32gui.GetForegroundWindow()==hwnd}')

# Step 1: _ensure_window
from core.adapters.dispatch import adapter_for
_, a = adapter_for('doubao')
print('\n=== 1. _ensure_window ===')
try:
    hwnd2 = a._ensure_window()
    print(f'  OK hwnd={hwnd2}')
except Exception as e:
    print(f'  FAIL: {e}')
alive, hwnd = check()
print(f'  after: alive={alive}')
if not alive: print('DIED @ step 1'); sys.exit(1)

# Step 2: find composer
print('\n=== 2. _find_composer ===')
try:
    ref, ctrl = a._find_composer(hwnd)
    print(f'  OK ref={ref[:30] if ref else None}')
except Exception as e:
    print(f'  FAIL: {e}')
alive, hwnd = check()
print(f'  after: alive={alive}')
if not alive: print('DIED @ step 2'); sys.exit(1)

# Step 3: inject clipboard
print('\n=== 3. _inject_clipboard ===')
try:
    ref, ok = a._inject_clipboard(hwnd, '你好世界')
    print(f'  OK ref={ref[:30] if ref else None} ok={ok}')
except Exception as e:
    print(f'  FAIL: {e}')
alive, hwnd = check()
print(f'  after: alive={alive}')
if not alive: print('DIED @ step 3'); sys.exit(1)

# Step 4: press Enter
print('\n=== 4. _press_send (Enter) ===')
try:
    a._press_send(hwnd)
    print('  OK')
except Exception as e:
    print(f'  FAIL: {e}')
time.sleep(2)
alive, hwnd = check()
print(f'  after 2s: alive={alive}')
if not alive: print('DIED @ step 4'); sys.exit(1)

print('\n=== 全部通过！豆包活到最后 ===')
