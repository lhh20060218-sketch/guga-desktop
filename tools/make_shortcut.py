# -*- coding: utf-8 -*-
"""在桌面创建「咕嘎企鹅」一键启动快捷方式"""
import os
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import win32com.client

desktop = os.path.join(os.environ.get("USERPROFILE", ""), "Desktop")
if not os.path.isdir(desktop):
    import ctypes
    buf = ctypes.create_unicode_buffer(512)
    if ctypes.windll.shell32.SHGetFolderPathW(None, 0x0000, None, 0, buf) == 0:
        desktop = buf.value

project = os.path.join(os.environ.get('USERPROFILE', ''),
                       '.zcode', 'workspace', 'default', 'guga-penguin-pet')
target = os.path.join(project, "启动企鹅.bat")
icon = os.path.join(project, "resources", "expressions", "happy_transparent.png")
lnk = os.path.join(desktop, "咕嘎企鹅桌宠.lnk")

ws = win32com.client.Dispatch("WScript.Shell")
sc = ws.CreateShortcut(lnk)
sc.TargetPath = target
sc.WorkingDirectory = project
sc.WindowStyle = 7
sc.IconLocation = icon if os.path.exists(icon) else target
sc.Description = "启动咕嘎企鹅桌宠（酒馆战棋军师 · 视觉 · 语音）"
sc.Save()
print("快捷方式已创建:", lnk)
