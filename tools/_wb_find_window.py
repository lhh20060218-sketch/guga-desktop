import subprocess, time, sys
sys.path.insert(0, r'D:\rengongzhineng\guga-competition')
import psutil, win32gui, win32process

# 先 kill 所有旧 WB
for p in psutil.process_iter(['pid','name']):
    try:
        if 'workbuddy' in (p.info.get('name') or '').lower():
            p.kill()
    except: pass
time.sleep(2)

# 启动 WB
p = subprocess.Popen([r'C:\Users\l\AppData\Local\Programs\WorkBuddy\WorkBuddy.exe'])
print(f'Launched PID={p.pid}')

# 等 25s
for i in range(13):
    time.sleep(2)
    alive = psutil.pid_exists(p.pid)
    # 查当前所有 WB 进程
    wb_procs = [proc for proc in psutil.process_iter(['pid','name']) 
                if 'workbuddy' in (proc.info.get('name') or '').lower()]
    print(f'  t={i*2}s alive={alive} wb_procs={[x.info["pid"] for x in wb_procs]}')
    if not alive:
        print('WB CRASHED!')
        sys.exit(1)
    if i == 12:
        print('WB alive after 24s')

# 枚举所有窗口，按 WB pid 过滤
all_wb_pids = [proc.info['pid'] for proc in psutil.process_iter(['pid','name']) 
               if 'workbuddy' in (proc.info.get('name') or '').lower()]
print(f'\nWorkBuddy pids: {all_wb_pids}')

results = []
def cb(hwnd, _):
    pid = win32process.GetWindowThreadProcessId(hwnd)[1]
    if pid in all_wb_pids:
        title = win32gui.GetWindowText(hwnd)
        cls = win32gui.GetClassName(hwnd)
        vis = win32gui.IsWindowVisible(hwnd)
        iconic = win32gui.IsIconic(hwnd)
        rect = win32gui.GetWindowRect(hwnd)
        results.append((hwnd, pid, cls, title[:60], vis, iconic, rect))
    return True

win32gui.EnumWindows(cb, 0)
print(f'WB windows: {len(results)}')
for hwnd, pid, cls, title, vis, iconic, rect in results:
    print(f'  hwnd={hwnd} pid={pid} cls="{cls}" vis={vis} iconic={iconic} size={rect[2]-rect[0]}x{rect[3]-rect[1]} title="{title}"')
