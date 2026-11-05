# -*- mode: python ; coding: utf-8 -*-
"""咕嘎桌宠（合一版）打包配置

产物形态: onedir（GUGA-Desktop.exe + _internal/）
  - 所有素材(resources/data/knowledge/armor_packs/agent)收进 _internal/
  - core/ui 模块的 __file__ 相对路径(parent.parent)在 _internal 下语义不变
  - agent/guga_agent 等经 hiddenimports 打进 PYZ, core/local_agent 的
    sys.path 注入逻辑在 frozen 下退化为无害空转, import 走内置 importer

用法: 在 guga-competition 目录下
    python -m PyInstaller GUGA-Desktop.spec --noconfirm
"""
import os

block_cipher = None
ROOT = os.path.abspath('.')

a = Analysis(
    ['comp_main.py'],
    pathex=[os.path.join(ROOT, 'agent')],   # 让 Analysis 扫到 agent/*.py
    binaries=[],
    datas=[
        # 素材与运行数据 → _internal/ 下同名目录（相对路径语义不变）
        (os.path.join(ROOT, 'resources'), 'resources'),
        (os.path.join(ROOT, 'data'), 'data'),
        (os.path.join(ROOT, 'knowledge'), 'knowledge'),
        (os.path.join(ROOT, 'armor_packs'), 'armor_packs'),
    ],
    hiddenimports=[
        # 内嵌执行方（动态 import, 必须显式声明）
        'guga_agent',
        'guga_executor',
        'guga_selfcheck',
        'pyautogui',
        'pyperclip',
        'pygetwindow',
        # 桌宠可选链路里被动态 import 的模块
        'core.realtime_voice',
        'core.voice_dialog',
        'core.browser_agent',
        'core.uia_backend',
        'core.uia_service',
        'ui.pet_window',
        'ui.multi_agent_window',
        'ui.mascot_animator',
        'ui.video_mascot',
        'ui.gl_penguin',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 巨型可选依赖: 环境里未安装, 明确排除防误报
        'tkinter', 'matplotlib', 'scipy', 'pandas', 'IPython', 'jedi',
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,          # onedir 模式
    name='GUGA-Desktop',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                      # 素材为主, UPX 收益小且易误报毒
    console=False,                  # 桌宠无控制台窗口
    icon='assets/icon.ico' if os.path.exists('assets/icon.ico') else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='GUGA-Desktop',
)
