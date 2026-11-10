import win32gui, win32process
import psutil

# Collect all visible windows
visible = {}
def each(hwnd, _):
    if not win32gui.IsWindowVisible(hwnd): return
    title = win32gui.GetWindowText(hwnd)
    cls = win32gui.GetClassName(hwnd)
    _, pid = win32process.GetWindowThreadProcessId(hwnd)
    if pid:
        visible.setdefault(pid, []).append((hwnd, title, cls))
win32gui.EnumWindows(each, None)

# Also check iconic ones
iconic = {}
def each2(hwnd, _):
    if not win32gui.IsIconic(hwnd): return
    title = win32gui.GetWindowText(hwnd)
    cls = win32gui.GetClassName(hwnd)
    _, pid = win32process.GetWindowThreadProcessId(hwnd)
    if pid:
        iconic.setdefault(pid, []).append((hwnd, title, cls))
win32gui.EnumWindows(each2, None)

for p in psutil.process_iter(['pid','name']):
    if 'doubao' in (p.info.get('name') or '').lower():
        pid = p.info['pid']
        if pid in visible:
            for hwnd, title, cls in visible[pid]:
                print(f'VISIBLE Doubao pid={pid} hwnd={hwnd} title="{title[:60]}" cls={cls}')
        if pid in iconic:
            for hwnd, title, cls in iconic[pid]:
                print(f'ICONIC Doubao pid={pid} hwnd={hwnd} title="{title[:60]}" cls={cls} → RESTORING')
                try:
                    win32gui.ShowWindow(hwnd, 9)  # SW_RESTORE
                except Exception as e:
                    print(f'  restore fail: {e}')

print('\nDone')
