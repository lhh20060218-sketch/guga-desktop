# -*- mode: python ; coding: utf-8 -*-
"""咕嘎桌宠（参赛版合一入口）PyInstaller 打包配置

入口为 tools/comp_entry.py：默认转发到 comp_main.main()，同时接管 frozen 下
自身 exe 被拉起的 --uia-worker / --guga-mcp 子进程模式（这两个分支原本在
launcher.py 里，参赛版入口不经过 launcher，必须在打包层补上）。

产物形态: onedir（GUGA-Desktop.exe + _internal/）
  - 素材/知识库/数据/能力包/lib 收进 _internal/，core/ui 的
    Path(__file__).resolve().parents[1] 在 frozen 下仍指向 _internal
  - runtime/ 与 ai_config.json 属于运行期数据，不由安装包携带：
    ai_config.json 首次运行由向导生成（模板随包放 _internal/ 根）
  - agent/*.py 通过 hiddenimports + pathex 打进 PYZ（源码目录不再需要）

用法（推荐用一键脚本，避免漏参数）:
    python tools/build_guga_exe.py
或手工:
    python -m PyInstaller GUGA-Desktop.spec --noconfirm --clean \
        --distpath dist --workpath build/guga-exe
"""
import os

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

ROOT = os.path.abspath(SPECPATH)

datas = [
    # 形象素材（帧序列 + manifest + visual-review 审批记录）、音频/模型
    (os.path.join(ROOT, 'resources'), 'resources'),
    # 运行数据（卡牌库、提醒、战棋缓存等）
    (os.path.join(ROOT, 'data'), 'data'),
    # 本地知识库（管家 RAG）
    (os.path.join(ROOT, 'knowledge'), 'knowledge'),
    # 管家能力包配置
    (os.path.join(ROOT, 'armor_packs'), 'armor_packs'),
    # 炉石只读解析 DLL（第三方许可见 THIRD_PARTY_NOTICES.md）
    (os.path.join(ROOT, 'lib'), 'lib'),
    # 无 API 工具链依赖的 PowerShell 脚本（OCR / 选区）
    (os.path.join(ROOT, 'tools', 'windows_ocr.ps1'), 'tools'),
    (os.path.join(ROOT, 'tools', 'windows_selection.ps1'), 'tools'),
    # 配置模板（README 约定放在 _internal/ 根）
    (os.path.join(ROOT, 'ai_config.example.json'), '.'),
    # 声明式软件适配注册表：一个软件一份 JSON，随包分发；用户覆盖文件留在 runtime/
    (os.path.join(ROOT, 'core', 'adapters', 'apps'), 'core/adapters/apps'),
]
binaries = []
hiddenimports = []

# VC++ 运行库：vcruntime140 由 PyInstaller 收在 _internal/ 根，但 msvcp140 只在
# PyQt5/Qt5/bin 与 numpy.libs 里。lib/ 下的 .NET 桥与部分扩展按 _internal/ 根
# 查找，裸机（没装 VC++ Redist）会缺这一份，因此补两份到根目录。
try:
    import PyQt5
    _qt_bin = os.path.join(os.path.dirname(PyQt5.__file__), 'Qt5', 'bin')
    for _dll in ('MSVCP140.dll', 'MSVCP140_1.dll'):
        _src = os.path.join(_qt_bin, _dll)
        if os.path.isfile(_src):
            binaries.append((_src, '.'))
except Exception:
    pass

# 全量收录 core/ui（大量模块是函数内动态 import，静态分析扫不到），
# 以及 agent 执行方（源码目录不随包，必须进 PYZ）
hiddenimports += collect_submodules('core')
hiddenimports += collect_submodules('ui')
hiddenimports += [
    # 任务总线 MCP server（exe --guga-mcp）；只收运行所需子模块，避开需要 typer 的 mcp.cli
    'mcp', 'mcp.types', 'mcp.server', 'mcp.server.mcpserver', 'mcp.client', 'mcp.client.stdio',
    'guga_agent',
    'guga_executor',
    'guga_selfcheck',
    'workbuddy_executor',
    'guga_mcp_server',
]

# 带二进制/数据文件的第三方包：音频设备、离线转写、本地视频合成、.NET 桥
for package in ('sounddevice', 'vosk', 'imageio_ffmpeg', 'pythonnet'):
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(package)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden

# python-pptx 的默认模板是包内数据文件
datas += collect_data_files('pptx')

hiddenimports += [
    # 内嵌执行方四件套 + 相关依赖
    'pyautogui', 'pymsgbox', 'pytweening', 'pyscreeze', 'mouseinfo',
    'pyperclip', 'pygetwindow',
    'PIL.ImageGrab',
    # Win32 / 语音 / 实时链路
    'win32timezone',
    # pywin32 运行文件与 asyncio 重叠 IO：正常由 hook 带入，显式声明防止
    # 部分环境下漏收（2026-11-07 曾出现缺 _overlapped / pywintypes 的半成品）。
    'win32api', 'win32clipboard', 'win32con', 'win32gui', 'win32process',
    'win32file', 'win32event', 'pythoncom', 'pywintypes', '_overlapped',
    'edge_tts',
    'websocket', 'websockets',
    'clr', 'clr_loader',
    # 本地视频兜底 + 文档生成
    'pptx', 'lxml',
]

a = Analysis(
    [os.path.join(ROOT, 'tools', 'comp_entry.py')],
    pathex=[
        ROOT,
        os.path.join(ROOT, 'agent'),
        os.path.join(ROOT, 'tools'),   # tools/guga_mcp_server.py 以顶层模块名冻结
    ],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 巨型可选依赖：本机未安装或桌宠链路不使用，明确排除防误收
        'tkinter', 'matplotlib', 'scipy', 'pandas', 'IPython', 'jedi',
        'torch', 'tensorflow', 'transformers', 'faster_whisper',
        'onnxruntime', 'kaldi_native_fbank', 'cv2',
        'OpenGL', 'OpenGL_accelerate', 'av',
        'PyQt6', 'PySide6', 'PySide2', 'playwright',
        'pytest', 'notebook',
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
    upx=False,                      # 素材为主，UPX 收益小且易误报毒
    console=False,                  # 桌宠无控制台窗口
    icon=os.path.join(ROOT, 'assets', 'icon.ico')
    if os.path.exists(os.path.join(ROOT, 'assets', 'icon.ico')) else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='GUGA-Desktop',
)
