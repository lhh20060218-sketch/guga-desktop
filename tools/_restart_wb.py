import subprocess, time, win32gui, win32process, psutil

# Kill all
for p in psutil.process_iter(['pid','name']):
    if 'workbuddy' in (p.info.get('name') or '').lower():
        print(f'Killing WB pid={p.info["pid"]}')
        try: p.kill()
        except: pass
time.sleep(4)

# Launch
exe = r'C:\Users\l\AppData\Local\Programs\WorkBuddy\WorkBuddy.exe'
print(f'Launching: {exe}')
proc = subprocess.Popen([exe])
time.sleep(12)

# Find all WB windows
wb_pids = set()
for p in psutil.process_iter(['pid','name']):
    if 'workbuddy' in (p.info.get('name') or '').lower():
        wb_pids.add(p.info['pid'])
print(f'WB pids alive: {wb_pids}')

wb_main = None
def each(hwnd, _):
    global wb_main
    _, pid = win32process.GetWindowThreadProcessId(hwnd)
    if pid in wb_pids:
        title = win32gui.GetWindowText(hwnd)
        cls = win32gui.GetClassName(hwnd)
        vis = win32gui.IsWindowVisible(hwnd)
        iconic = win32gui.IsIconic(hwnd)
        print(f'  hwnd={hwnd} pid={pid} vis={vis} iconic={iconic} title="{title[:50]}" cls={cls}')
        if cls == 'Chrome_WidgetWin_1' and title:
            wb_main = hwnd
win32gui.EnumWindows(each, None)

if wb_main:
    win32gui.ShowWindow(wb_main, 9)
    time.sleep(0.5)
    try:
        win32gui.SetForegroundWindow(wb_main)
    except:
        pass
    print(f'\nWorkBuddy main hwnd={wb_main} fg={win32gui.GetForegroundWindow()}')
else:
    print('\nNo WB main window')
