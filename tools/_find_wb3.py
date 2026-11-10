import ctypes, psutil

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

def enum_all():
    results = []
    def cb(hwnd, _):
        buf = ctypes.c_ulong(0)
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(buf))
        cls = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, cls, 256)
        title = ctypes.create_unicode_buffer(512)
        user32.GetWindowTextW(hwnd, title, 512)
        vis = user32.IsWindowVisible(hwnd)
        if vis and title.value:
            pname = ''
            try:
                p = psutil.Process(buf.value)
                pname = (p.info.get('name') or '')
            except: pass
            rect = ctypes.wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            results.append((hwnd, cls.value, title.value[:60], buf.value, pname, rect.right-rect.left, rect.bottom-rect.top))
        return True
    WT = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    user32.EnumWindows(WT(cb), 0)
    return results

all_w = enum_all()
# 只看 Chrome_WidgetWin_1 或有 WorkBuddy 标题的
print(f'Total visible windows with title: {len(all_w)}')
for h, c, t, pid, pname, w, ht in all_w:
    if 'Chrome_WidgetWin_1' in c or 'workbuddy' in (t + pname).lower():
        print(f'  hwnd={h} pid={pid} pname="{pname}" cls="{c}" size={w}x{ht} title="{t}"')

print('\n--- list_windows("workbuddy") source analysis ---')
import sys; sys.path.insert(0, r'D:\rengongzhineng\guga-competition')
from core.window_inventory import list_windows
items = list(list_windows('workbuddy'))
print(f'list_windows returned {len(items)} items')
for it in items[:5]:
    print(f'  {it}')
