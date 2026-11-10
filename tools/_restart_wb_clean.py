"""彻底清理 + 干净启动 WorkBuddy。"""
import subprocess, time, psutil, sys

# 1. 杀所有 workbuddy
killed = 0
for p in psutil.process_iter(['pid','name','cmdline']):
    name = (p.info.get('name') or '').lower()
    cmdline = (p.info.get('cmdline') or [])
    if 'workbuddy' in name or any('workbuddy' in (c or '').lower() for c in cmdline):
        try:
            p.kill()
            killed += 1
        except: pass
print('killed=%d workbuddy processes' % killed)
time.sleep(5)

# 2. 再起一个干净的
exe = r'C:\Users\l\AppData\Local\Programs\WorkBuddy\WorkBuddy.exe'
if not __import__('pathlib').Path(exe).is_file():
    print('exe not found:', exe); sys.exit(1)

proc = subprocess.Popen([exe])
print('started pid=%d waiting 20s...' % proc.pid)
time.sleep(20)

# 3. 验证活著
import win32gui, win32process, ctypes
user32 = ctypes.windll.user32
alive = []
for p in psutil.process_iter(['pid','name']):
    if 'workbuddy' in (p.info.get('name') or '').lower():
        alive.append(p.info['pid'])
print('alive pids:', alive)

# 4. 找主窗口
hwnd = None
def each(h, _):
    global hwnd
    cls = win32gui.GetClassName(h)
    title = win32gui.GetWindowText(h)
    if cls == 'Chrome_WidgetWin_1' and title == 'WorkBuddy':
        hwnd = h
win32gui.EnumWindows(each, None)
print('main hwnd:', hwnd)

if hwnd:
    vis = win32gui.IsWindowVisible(hwnd)
    iconic = win32gui.IsIconic(hwnd)
    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    print('before: vis=%s iconic=%s rect=(%s,%s,%s,%s)' % (vis, iconic, left, top, right, bottom))

    # 抢前台 + 最大化
    current_fg = win32gui.GetForegroundWindow()
    fg_tid = user32.GetWindowThreadProcessId(current_fg, None)
    my_tid = ctypes.windll.kernel32.GetCurrentThreadId()
    if fg_tid and my_tid and fg_tid != my_tid:
        user32.AttachThreadInput(fg_tid, my_tid, True)
    win32gui.ShowWindow(hwnd, 9)
    win32gui.ShowWindow(hwnd, 3)
    time.sleep(0.8)
    try: win32gui.BringWindowToTop(hwnd)
    except: pass
    try: win32gui.SetForegroundWindow(hwnd)
    except: pass
    if fg_tid and my_tid and fg_tid != my_tid:
        user32.AttachThreadInput(fg_tid, my_tid, False)

    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    print('after max: rect=(%s,%s,%s,%s) size=%sx%s' % (left, top, right, bottom, right-left, bottom-top))

print('done')
