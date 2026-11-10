import win32gui, win32con

hwnd = 133368
print(f'Before: vis={win32gui.IsWindowVisible(hwnd)} iconic={win32gui.IsIconic(hwnd)}')

# Try multiple show modes
for mode in [win32con.SW_RESTORE, win32con.SW_SHOW, win32con.SW_SHOWNORMAL, win32con.SW_MAXIMIZE]:
    win32gui.ShowWindow(hwnd, mode)
    vis = win32gui.IsWindowVisible(hwnd)
    print(f'  ShowWindow({mode}) -> vis={vis}')
    if vis:
        break

win32gui.SetForegroundWindow(hwnd)
import time; time.sleep(0.5)
print(f'After: vis={win32gui.IsWindowVisible(hwnd)} fg={win32gui.GetForegroundWindow()}')
