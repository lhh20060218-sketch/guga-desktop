"""杀掉残留的 GUGA/WorkBuddy，然后启动 driver。"""
import psutil, subprocess, time, sys

# Kill old GUGA
for p in psutil.process_iter(['pid', 'name']):
    name = (p.info.get('name') or '').lower()
    if 'guga-desktop' in name or 'guga_desktop' in name:
        try:
            p.kill()
            print('killed GUGA pid=%s' % p.info['pid'])
        except: pass
time.sleep(2)

# Run driver
exe = r'D:\rengongzhineng\guga-competition\dist\e2e-20261110ac-r9\driver\drive.py'
print('starting driver...')
result = subprocess.run(
    [sys.executable, exe],
    cwd=r'D:\rengongzhineng\guga-competition',
    timeout=1200,
)
print('driver exit code:', result.returncode)
