import win32gui, win32process

visible = {}
def each(hwnd, _):
    if not win32gui.IsWindowVisible(hwnd): return
    title = win32gui.GetWindowText(hwnd)
    cls = win32gui.GetClassName(hwnd)
    _, pid = win32process.GetWindowThreadProcessId(hwnd)
    if pid: visible.setdefault(pid, []).append((hwnd, title, cls))

iconic = {}
def each2(hwnd, _):
    if not win32gui.IsIconic(hwnd): return
    title = win32gui.GetWindowText(hwnd)
    cls = win32gui.GetClassName(hwnd)
    _, pid = win32process.GetWindowThreadProcessId(hwnd)
    if pid: iconic.setdefault(pid, []).append((hwnd, title, cls))

win32gui.EnumWindows(each, None)
win32gui.EnumWindows(each2, None)

import psutil
for p in psutil.process_iter(['pid','name']):
    if 'doubao' in (p.info.get('name') or '').lower():
        pid = p.info['pid']
        for hwnd, title, cls in visible.get(pid, []):
            print(f'VISIBLE Doubao pid={pid} hwnd={hwnd} title="{title[:60]}" cls={cls}')
        for hwnd, title, cls in iconic.get(pid, []):
            print(f'ICONIC Doubao pid={pid} hwnd={hwnd} title="{title[:60]}" → RESTORE')
            win32gui.ShowWindow(hwnd, 9)

for p in psutil.process_iter(['pid','name']):
    if 'workbuddy' in (p.info.get('name') or '').lower():
        pid = p.info['pid']
        for hwnd, title, cls in visible.get(pid, []):
            print(f'VISIBLE WB pid={pid} hwnd={hwnd} title="{title[:60]}" cls={cls}')
        for hwnd, title, cls in iconic.get(pid, []):
            print(f'ICONIC WB pid={pid} hwnd={hwnd} title="{title[:60]}" → RESTORE')
            win32gui.ShowWindow(hwnd, 9)

print('Done')
