import psutil, ctypes

user32 = ctypes.windll.user32
pids = [p.info['pid'] for p in psutil.process_iter(['pid','name']) if 'workbuddy' in (p.info.get('name') or '').lower()]
print(f'WorkBuddy pids: {pids}')

results = []
def cb(hwnd, _):
    _, pid = user32.GetWindowThreadProcessId(hwnd, 0)
    if pid in pids:
        name = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, name, 256)
        title = ctypes.create_unicode_buffer(512)
        user32.GetWindowTextW(hwnd, title, 512)
        vis = user32.IsWindowVisible(hwnd)
        results.append((hwnd, name.value, title.value[:60], vis))
    return True

WT = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
user32.EnumWindows(WT(cb), 0)

print(f'WB windows: {len(results)}')
for h, n, t, v in results:
    print(f'  hwnd={h} cls="{n}" vis={v} title="{t}"')
