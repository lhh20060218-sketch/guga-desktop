# -*- coding: utf-8 -*-
import os, sys, time
sys.path.insert(0, r'd:\rengongzhineng\guga-competition')
os.environ['GUGA_HOME'] = r'd:\rengongzhineng\guga-competition\dist\e2e-20261110ac-r21\home'

import win32gui
def alive():
    h = []
    def cb(w, _):
        if win32gui.IsWindowVisible(w):
            t = win32gui.GetWindowText(w)
            if '豆包' in t: h.append(w)
    win32gui.EnumWindows(cb, None)
    return len(h) > 0

print('[0] alive=', alive())
from core.adapters.dispatch import adapter_for
_, a = adapter_for('doubao')
print('[1] adapter alive=', alive())
print('[2] ask start...')
r = a.ask('写一句测试')
ok = r.get('ok')
code = r.get('code')
print('[3] ask done alive=', alive(), 'ok=', ok, 'code=', code)
time.sleep(3)
print('[4] +3s alive=', alive())
