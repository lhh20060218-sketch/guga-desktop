import win32gui, win32process, psutil
results = []
def enum_cb(h, _):
    if win32gui.IsWindowVisible(h):
        cls = win32gui.GetClassName(h)
        if cls == 'Chrome_WidgetWin_1':
            rect = win32gui.GetWindowRect(h)
            w, ht = rect[2]-rect[0], rect[3]-rect[1]
            title = win32gui.GetWindowText(h)
            results.append((h, cls, title[:60], w, ht))
win32gui.EnumWindows(enum_cb, None)
results.sort(key=lambda x: x[3]*x[4], reverse=True)
for hwnd, cls, title, w, ht in results:
    tid, pid = win32process.GetWindowThreadProcessId(hwnd)
    try:
        pname = psutil.Process(pid).name()
    except:
        pname = '?'
    print(f'{hwnd:>10} {w:>5}x{ht:<5} pid={pid:>6} proc={pname:<20} title="{title}"')
