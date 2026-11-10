import psutil, ctypes

user32 = ctypes.windll.user32

for p in psutil.process_iter(['pid','name']):
    if 'workbuddy' in (p.info.get('name') or '').lower():
        pid = p.info['pid']
        name = p.info['name']
        results = []
        def cb(hwnd, _, target_pid=pid):
            buf = ctypes.c_ulong(0)
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(buf))
            if buf.value == target_pid:
                cls = ctypes.create_unicode_buffer(256)
                user32.GetClassNameW(hwnd, cls, 256)
                title = ctypes.create_unicode_buffer(512)
                user32.GetWindowTextW(hwnd, title, 512)
                vis = user32.IsWindowVisible(hwnd)
                rect = ctypes.wintypes.RECT()
                user32.GetWindowRect(hwnd, ctypes.byref(rect))
                results.append((hwnd, cls.value, title.value[:60], vis, rect.right - rect.left, rect.bottom - rect.top))
            return True
        WT = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        user32.EnumWindows(WT(cb), 0)
        print(f'PID={pid} NAME={name}')
        for h, c, t, v, w, ht in results:
            print(f'  hwnd={h} cls="{c}" vis={v} size={w}x{ht} title="{t}"')
