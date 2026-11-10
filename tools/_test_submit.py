# -*- coding: utf-8 -*-
"""probe 精确流程 - 启动后立刻跑 + AttachThreadInput"""
import sys, time, os, subprocess
sys.path.insert(0, r'd:\rengongzhineng\guga-competition')
os.environ['GUGA_HOME'] = r'd:\rengongzhineng\guga-competition\dist\e2e-20261110ac-r21\home'

print('[0] Launching WorkBuddy...')
subprocess.Popen([r'C:\Users\l\AppData\Local\Programs\WorkBuddy\WorkBuddy.exe'])
time.sleep(8)

import win32gui, win32api, win32con, win32clipboard as clip, win32con as wc, win32process
import ctypes
from core.computer_control import _send_keys

# 找主窗口
hwnd = None
def enum_cb(h, _):
    global hwnd
    if win32gui.IsWindowVisible(h):
        cls = win32gui.GetClassName(h)
        title = win32gui.GetWindowText(h)
        if cls == 'Chrome_WidgetWin_1' and title == 'WorkBuddy':
            hwnd = h
win32gui.EnumWindows(enum_cb, None)

for i in range(20):
    if hwnd: break
    time.sleep(1)
    win32gui.EnumWindows(enum_cb, None)

if not hwnd:
    print('FATAL: no WB main window')
    sys.exit(1)

print(f'[1] Found hwnd={hwnd}')

# ===== AttachThreadInput 抢前台 =====
fg = win32gui.GetForegroundWindow()
fg_tid, _ = win32process.GetWindowThreadProcessId(fg)
my_tid = win32api.GetCurrentThreadId()
ctypes.windll.user32.AttachThreadInput(fg_tid, my_tid, True)
win32gui.ShowWindow(hwnd, 9)  # SW_RESTORE
time.sleep(0.2)
win32gui.ShowWindow(hwnd, 3)  # SW_MAXIMIZE
time.sleep(0.2)
win32gui.BringWindowToTop(hwnd)
win32gui.SetForegroundWindow(hwnd)
time.sleep(0.5)
ctypes.windll.user32.AttachThreadInput(fg_tid, my_tid, False)

fg2 = win32gui.GetForegroundWindow()
print(f'    Foreground after grab: {fg2} (expect {hwnd})')

# Ctrl+N
print('[2] Ctrl+N...')
_send_keys([17, 78]); time.sleep(2.5)

rect = win32gui.GetWindowRect(hwnd)
left, top, right, bottom = rect
cx = left + int((right-left) * 0.50)
cy = top + int((bottom-top) * 0.60)
print(f'[3] Click ({cx},{cy})')
win32api.SetCursorPos((cx, cy)); time.sleep(0.1)
win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0); time.sleep(0.05)
win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0); time.sleep(0.3)

print('[4] Clear...')
_send_keys([27]); time.sleep(0.15)
_send_keys([17, 65]); time.sleep(0.2)
_send_keys([46]); time.sleep(0.3)
_send_keys([27]); time.sleep(0.15)

prompt = '生成一个简单PPT，主题是人工智能。'
print('[5] Clipboard...')
clip.OpenClipboard(); clip.EmptyClipboard()
clip.SetClipboardData(wc.CF_UNICODETEXT, prompt)
clip.CloseClipboard(); time.sleep(0.2)

print('[6] Ctrl+V...')
_send_keys([17, 86]); time.sleep(1.0)

print('[7] Enter!')
_send_keys([17, 35]); time.sleep(0.1)
_send_keys([13])

print('[8] Poll BUSY...')
from core.workbuddy_bridge import _grab
BUSY_WORDS = ['等待模型响应', '生成中', '正在生成', '思考中', '处理中', '制作中', '深度思考中', '生成 PPT']
for i in range(45):
    time.sleep(1.0)
    alive = win32gui.IsWindow(hwnd)
    if not alive:
        print(f'  t={i}s ** WB DIED **')
        break
    page = _grab(hwnd)
    found = [w for w in BUSY_WORDS if w in page]
    if found:
        print(f'  t={i}s [BUSY] {found}')
        print('  === SUCCESS! ===')
        sys.exit(0)
    if i % 5 == 0:
        print(f'  t={i}s len={len(page)} alive={alive}...')

print('  no BUSY')
print(f'  tail: {page[-300:]}')
