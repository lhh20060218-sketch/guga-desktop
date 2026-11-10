import subprocess, time, win32gui, win32process, psutil

def restart_wb():
    for p in psutil.process_iter(['pid','name']):
        if 'workbuddy' in (p.info.get('name') or '').lower():
            try: p.kill()
            except: pass
    time.sleep(3)
    exe = r'C:\Users\l\AppData\Local\Programs\WorkBuddy\WorkBuddy.exe'
    proc = subprocess.Popen([exe])
    time.sleep(10)
    return proc

# Restart WorkBuddy and keep it visible longer
restart_wb()

# Keep trying to bring it to foreground for 15 seconds
wb_main = None
for attempt in range(30):
    for p in psutil.process_iter(['pid','name']):
        if 'workbuddy' in (p.info.get('name') or '').lower():
            pid = p.info['pid']
            def each(hwnd, _):
                global wb_main
                _, p2 = win32process.GetWindowThreadProcessId(hwnd)
                if p2 == pid:
                    cls = win32gui.GetClassName(hwnd)
                    vis = win32gui.IsWindowVisible(hwnd)
                    if cls == 'Chrome_WidgetWin_1' and vis:
                        wb_main = hwnd
            win32gui.EnumWindows(each, None)
    if wb_main:
        print(f'Found WB main hwnd={wb_main} attempt={attempt}')
        try:
            win32gui.ShowWindow(wb_main, 9)
            win32gui.SetForegroundWindow(wb_main)
        except:
            pass
        break
    time.sleep(0.5)

time.sleep(3)
print('Ready to run driver')
