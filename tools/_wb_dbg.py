import subprocess, time, psutil, sys, os

# 清掉所有旧的 WB
for p in psutil.process_iter(['pid','name']):
    if 'workbuddy' in (p.info.get('name') or '').lower():
        try: p.kill()
        except: pass
time.sleep(2)

# 直接启动，捕捉输出
exe = r'C:\Users\l\AppData\Local\Programs\WorkBuddy\WorkBuddy.exe'
print(f'Launching {exe}...')
try:
    p = subprocess.Popen([exe], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=r'C:\Users\l\AppData\Local\Programs\WorkBuddy')
    time.sleep(8)
    
    # 检查存活
    alive = psutil.pid_exists(p.pid)
    print(f'PID={p.pid} alive_after_8s={alive}')
    
    if alive:
        # 等久点
        time.sleep(12)
        alive2 = psutil.pid_exists(p.pid)
        print(f'alive_after_20s={alive2}')
        
        # 看打开的文件
        print(f'  cmdline: {psutil.Process(p.pid).cmdline()}')
    else:
        # 取输出
        try:
            out, err = p.communicate(timeout=2)
            print(f'  stdout: {out[:2000]}')
            print(f'  stderr: {err[:2000]}')
        except Exception as e:
            print(f'  communicate err: {e}')
except Exception as e:
    print(f'Launch error: {e}')

# 查日志
for logdir in [os.path.expanduser(r'~\AppData\Local\WorkBuddy'), 
               os.path.expanduser(r'~\AppData\Roaming\WorkBuddy'),
               os.path.expanduser(r'~\WorkBuddy'),
               r'C:\ProgramData\WorkBuddy']:
    if os.path.exists(logdir):
        print(f'\nLog dir: {logdir}')
        for root, dirs, files in os.walk(logdir):
            for f in files[-5:]:
                fp = os.path.join(root, f)
                if os.path.getmtime(fp) > time.time() - 300:  # 5分钟内修改
                    print(f'  RECENT: {fp} ({os.path.getsize(fp)} bytes)')
