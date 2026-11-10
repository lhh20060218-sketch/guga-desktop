import sys; sys.path.insert(0, r'D:\rengongzhineng\guga-competition')
import win32gui, win32process, psutil
import ctypes
from ctypes import wintypes

wb_pids = set()
for p in psutil.process_iter(['pid','name']):
    if 'workbuddy' in (p.info.get('name') or '').lower():
        wb_pids.add(p.info['pid'])

all_windows = []
def each(hwnd, _):
    _, pid = win32process.GetWindowThreadProcessId(hwnd)
    if pid in wb_pids:
        all_windows.append(hwnd)
        title = win32gui.GetWindowText(hwnd)
        cls = win32gui.GetClassName(hwnd)
        vis = win32gui.IsWindowVisible(hwnd)
        iconic = win32gui.IsIconic(hwnd)
        box = wintypes.RECT()
        try:
            ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(box))
            x, y = box.left, box.top
            w, h = box.right - box.left, box.bottom - box.top
        except:
            x, y, w, h = 0, 0, 0, 0
        print(f'hwnd={hwnd} pid={pid} vis={vis} iconic={iconic} title="{title[:50]}" cls={cls} rect=({x},{y},{w},{h})')
win32gui.EnumWindows(each, None)

print(f'\nTotal WB windows: {len(all_windows)}')
# Restore all
for hwnd in all_windows:
    try:
        win32gui.ShowWindow(hwnd, 9)  # SW_RESTORE
    except:
        pass
print('Restored all')
