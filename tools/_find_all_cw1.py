import psutil, win32gui, win32process

# 枚举所有 Chrome_WidgetWin_1，包括空标题
results = []
def cb(hwnd, _):
    cls = win32gui.GetClassName(hwnd)
    if cls == 'Chrome_WidgetWin_1':
        title = win32gui.GetWindowText(hwnd)
        vis = win32gui.IsWindowVisible(hwnd)
        iconic = win32gui.IsIconic(hwnd)
        pid = win32process.GetWindowThreadProcessId(hwnd)[1]
        try:
            p = psutil.Process(pid)
            pname = p.name()
            exe = p.exe()
        except:
            pname = '?'
            exe = '?'
        rect = win32gui.GetWindowRect(hwnd)
        results.append((hwnd, title[:50] or '(empty)', vis, iconic, pid, pname, exe, rect))
    return True

win32gui.EnumWindows(cb, 0)

print(f'All Chrome_WidgetWin_1 ({len(results)} total):')
print(f'{"hwnd":>10} {"vis":>3} {"icon":>3} {"pid":>8} {"pname":<15} {"title"[:30]:<30}')
for r in results:
    hwnd, title, vis, iconic, pid, pname, exe, rect = r
    size = f'{rect[2]-rect[0]}x{rect[3]-rect[1]}'
    marker = ' <<<' if 'workbuddy' in pname.lower() else ''
    print(f'{hwnd:>10} {vis:>3} {iconic:>3} {pid:>8} {pname[:15]:<15} "{title[:30]:<30}" {size}{marker}')
