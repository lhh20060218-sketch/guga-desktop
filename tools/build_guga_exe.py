# -*- coding: utf-8 -*-
"""一键重跑咕嘎 Windows exe 打包（参赛版 comp_main 入口）

用法:
    python tools/build_guga_exe.py              # 构建 dist/GUGA-Desktop
    python tools/build_guga_exe.py --zip        # 额外产出 release zip（根目录带使用说明）
    python tools/build_guga_exe.py --zip --zip-out dist/verify/x.zip  # 输出到指定路径
    python tools/build_guga_exe.py --no-clean   # 复用已有 build 缓存（调试用）

产物:
    dist/GUGA-Desktop/GUGA-Desktop.exe
    dist/GUGA-Desktop/_internal/...
    dist/build-report.json                      # 大小/耗时/版本信息

设计说明:
- 只用现有 GUGA-Desktop.spec，资源与隐藏依赖都在 spec 里维护；
  本脚本只负责清场、调用 PyInstaller、补齐配置模板、输出构建报告。
- 不修改任何业务代码；runtime/ 与 ai_config.json 属于运行期数据，不随包。
"""
import argparse
import atexit
import ctypes
import datetime
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import release_guard as guard
import write_guard
SPEC = ROOT / 'GUGA-Desktop.spec'
DIST = ROOT / 'dist'
WORK = ROOT / 'build/guga-exe'
OUT = DIST / 'GUGA-Desktop'
REPORT = DIST / 'build-report.json'
INTEGRITY = DIST / 'build-integrity.json'
LOCK = DIST / '.build.lock'
GUIDE_MD = ROOT / 'docs' / '评委安装与使用说明.md'
GUIDE_FOLDER = DIST / 'release-docs'
GUIDE_NAMES = ('使用说明.html', '使用说明.txt', '安装说明.txt', '作品介绍.txt',
               'RELEASE-NOTES.md', '豆包连接器配置教程.txt')
STATIC_GUIDES = (
    ('安装说明.txt', ROOT / 'docs' / '安装说明.txt'),
    ('作品介绍.txt', ROOT / 'docs' / '作品介绍.txt'),
    ('RELEASE-NOTES.md', ROOT / 'RELEASE-NOTES.md'),
    ('豆包连接器配置教程.txt', ROOT / 'docs' / '豆包连接器配置教程.txt'),
)

# 构建后完整性闸门：任一项缺失即判定产物不可交付并删除。
# 2026-11-07 事故：runtime/clean/install 里的副本只有 31 个文件、缺 _overlapped /
# pywintypes，起因是构建与外部拷贝并发；这里把“缺文件也能产出目录”的路堵死。
REQUIRED_FILES = [
    ('GUGA-Desktop.exe', '主程序 exe'),
    ('_internal/base_library.zip', 'Python 标准库压缩包'),
    ('_internal/python*.dll', 'Python 运行时'),
    ('_internal/_overlapped.pyd', 'asyncio 重叠 IO 扩展'),
    ('_internal/pywin32_system32/pywintypes*.dll', 'pywin32 pywintypes'),
    ('_internal/pywin32_system32/pythoncom*.dll', 'pywin32 pythoncom'),
    ('_internal/win32/win32api.pyd', 'pywin32 win32api'),
    ('_internal/win32/win32clipboard.pyd', 'pywin32 win32clipboard'),
    ('_internal/VCRUNTIME140.dll', 'VC++ 运行库 VCRUNTIME140'),
    ('_internal/VCRUNTIME140_1.dll', 'VC++ 运行库 VCRUNTIME140_1'),
    ('_internal/MSVCP140.dll', 'VC++ 运行库 MSVCP140'),
    ('_internal/MSVCP140_1.dll', 'VC++ 运行库 MSVCP140_1'),
    ('_internal/PyQt5/Qt5/bin/Qt5Core.dll', 'Qt5Core'),
    ('_internal/PyQt5/Qt5/bin/Qt5Gui.dll', 'Qt5Gui'),
    ('_internal/PyQt5/Qt5/bin/Qt5Widgets.dll', 'Qt5Widgets'),
    ('_internal/PyQt5/Qt5/plugins/platforms/qwindows.dll', 'Qt Windows 平台插件'),
    ('_internal/ai_config.example.json', '配置模板'),
    ('_internal/build-info.json', '版本/构建 SHA/包摘要'),
]
REQUIRED_DIRS = [
    '_internal/resources/actions',
    '_internal/resources/actions/task-motion/rekeyed/accept/frames',
    '_internal/resources/actions/task-motion/rekeyed/error/frames',
    '_internal/resources/actions/idle-motion/v2/doze/frames',
    '_internal/resources/actions/idle-motion/v2/heart/frames',
    '_internal/data',
    '_internal/knowledge',
    '_internal/armor_packs',
    '_internal/lib',
    '_internal/tools',
]
MIN_FRAMES = [
    ('_internal/resources/actions/task-motion/rekeyed/accept/frames', 90),
    ('_internal/resources/actions/idle-motion/v2/doze/frames', 110),
]
MIN_FILES = 4000      # 正常包 5000+ 文件；低于此值必是半成品


def _pid_alive(pid):
    handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, int(pid))
    if handle:
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    return False


def _acquire_lock():
    """同一时间只允许一个构建，避免并发清目录时被拷贝成半成品。"""
    DIST.mkdir(parents=True, exist_ok=True)
    if LOCK.exists():
        try:
            pid = int(LOCK.read_text(encoding='utf-8').strip() or 0)
        except (OSError, ValueError):
            pid = 0
        if pid and pid != os.getpid() and _pid_alive(pid):
            raise SystemExit('另一个构建正在进行（pid=%s），请等它结束再打' % pid)
        LOCK.unlink(missing_ok=True)
    LOCK.write_text(str(os.getpid()), encoding='utf-8')
    atexit.register(lambda: LOCK.unlink(missing_ok=True) if LOCK.exists() else None)


def _sha256_file(path, chunk=1024 * 1024):
    digest = hashlib.sha256()
    with open(str(path), 'rb') as handle:
        while True:
            data = handle.read(chunk)
            if not data:
                break
            digest.update(data)
    return digest.hexdigest()


_SOURCE_SUFFIXES = ('.py', '.json', '.md', '.txt', '.spec', '.qss', '.html', '.js',
                    '.ui', '.ini', '.bat', '.ps1', '.yml', '.yaml')
_SOURCE_SKIP = {'dist', 'build', '.git', 'runtime', '__pycache__', 'node_modules',
                '.pytest_cache', 'release-docs'}


def _source_sha256(root):
    """构建 SHA = 源码快照摘要（相对路径 + 文件大小 + 文件 SHA256）。"""
    rows = []
    for path in sorted(Path(root).rglob('*')):
        try:
            if not path.is_file():
                continue
            rel = path.relative_to(root)
            if any(part in _SOURCE_SKIP for part in rel.parts):
                continue
            if path.suffix.lower() not in _SOURCE_SUFFIXES:
                continue
            if path.stat().st_size > 10 * 1024 * 1024:
                continue
            rows.append('%s\t%d\t%s' % (rel.as_posix().lower(), path.stat().st_size,
                                        _sha256_file(path)))
        except OSError:
            continue
    digest = hashlib.sha256('\n'.join(rows).encode('utf-8')).hexdigest()
    return digest, len(rows)


def _bundle_content_sha256(out):
    """包内容摘要：解压后可按同样规则复算；排除 build-info.json 自身。"""
    rows = []
    total = 0
    for path in sorted(Path(out).rglob('*')):
        try:
            if not path.is_file():
                continue
            rel = path.relative_to(out)
            if rel.as_posix().lower() == '_internal/build-info.json':
                continue
            size = path.stat().st_size
            total += size
            rows.append('%s\t%d\t%s' % (rel.as_posix().lower(), size, _sha256_file(path)))
        except OSError:
            continue
    return hashlib.sha256('\n'.join(rows).encode('utf-8')).hexdigest(), len(rows), total


def write_build_info(out, version='', package_name=''):
    """把版本/构建 SHA/包内容摘要写进包内固定位置 _internal/build-info.json。"""
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from core import env_check
    content_sha, files, total = _bundle_content_sha256(out)
    source_sha, source_files = _source_sha256(ROOT)
    payload = dict(
        schema='guga.build-info/1',
        version=str(version or os.environ.get('GUGA_BUILD_TAG') or 'dev'),
        check_version=str(getattr(env_check, 'CHECK_VERSION', '')),
        check_count=int(env_check.check_count()),
        build_sha=source_sha,
        build_sha_algorithm='sha256(相对路径+大小+文件SHA256，排除 dist/build/.git)',
        build_sha_files=source_files,
        package_name=str(package_name or ''),
        package_content_sha256=content_sha,
        package_content_sha256_algorithm=(
            '解压后对全部文件按“相对路径+大小+文件SHA256”排序拼接再 SHA256，'
            '排除 _internal/build-info.json 自身'),
        package_files=files,
        package_bytes=total,
        built_at=datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        python=sys.version.split()[0],
        note='zip 自身 SHA256 由同名 .sha256 sidecar 记录（zip 内不能包含自身哈希）；'
             '诊断导出会优先读本文件，并在能找到原始 zip 时实测其 SHA256',
    )
    target = Path(out) / '_internal' / 'build-info.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    print('[build][info] %s version=%s check=%s build_sha=%s... files=%d'
          % (target, payload['version'], payload['check_version'],
             payload['build_sha'][:16], files))
    return payload


def write_zip_sidecar(target):
    """打包后写 <zip>.sha256：诊断导出可读取，用于与 zip 实际 SHA 对齐。"""
    target = Path(target)
    sha = _sha256_file(target)
    sidecar = Path(str(target) + '.sha256')
    sidecar.write_text('%s  %s\n' % (sha, target.name), encoding='utf-8')
    print('[build][sha] %s -> %s' % (sha.upper(), sidecar))
    return sha


def verify_bundle(out):
    """校验产物完整性；失败则删除目录并中止，绝不产出“看起来可用”的包。"""
    problems = []
    for pattern, label in REQUIRED_FILES:
        if not list(out.glob(pattern)):
            problems.append('%s（%s）' % (label, pattern))
    for rel in REQUIRED_DIRS:
        if not (out / rel).is_dir():
            problems.append('目录缺失：%s' % rel)
    for rel, need in MIN_FRAMES:
        folder = out / rel
        count = len([p for p in folder.glob('*')
                     if p.suffix.lower() in ('.webp', '.png', '.jpg', '.jpeg')]) if folder.is_dir() else 0
        if count < need:
            problems.append('%s 帧数不足：%d < %d' % (rel, count, need))
    # P0：发行包绝不能带运行期 ai_config.json（避免旧 Key 被当成用户自己的凭据）。
    runtime_cfg = [p for p in out.rglob('ai_config.json') if p.is_file()]
    if runtime_cfg:
        problems.append('运行期配置泄漏：%s' % '、'.join(str(p.relative_to(out)) for p in runtime_cfg))
    total, files = _tree_size(out)
    if files < MIN_FILES:
        problems.append('文件数异常：%d < %d（疑似半成品）' % (files, MIN_FILES))
    payload = dict(checked_at=datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                   path=str(out), ok=not problems, missing=problems,
                   files=files, bytes=total,
                   checks=len(REQUIRED_FILES) + len(REQUIRED_DIRS) + len(MIN_FRAMES) + 2)
    INTEGRITY.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    if problems:
        print('[build][integrity] FAIL：%d 项缺失，删除不完整产物 %s' % (len(problems), out))
        for item in problems:
            print('  - %s' % item)
        shutil.rmtree(out, ignore_errors=True)
        raise SystemExit('构建完整性校验失败（详见 %s）' % INTEGRITY)
    print('[build][integrity] ok：%d 项必需文件/目录齐全，%d 文件 / %.1fMB'
          % (payload['checks'], files, total / (1024 * 1024)))


def _selfcheck_gate(out):
    """打包闸门：包内 --selfcheck-json 的项数/版本必须等于源码当前值。

    2026-11-08 事故：f 包里跑的是旧的 13 项自检，源码新写的 19 项没打进包，
    于是“自检全绿、派单报 Windows OCR 不可用”。这里不一致就直接构建失败。
    """
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from core import env_check as source_check
    expected_version = getattr(source_check, 'CHECK_VERSION', '')
    expected_count = source_check.check_count()
    expected_bundle = str(os.environ.get('GUGA_BUNDLE_VERSION') or '')
    result = dict(expected_version=expected_version, expected_count=expected_count,
                  expected_bundle=expected_bundle, ok=False)
    target = ROOT / 'build' / 'selfcheck-frozen.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        target.unlink()
    command = [str(out / 'GUGA-Desktop.exe'), '--selfcheck-json', str(target)]
    try:
        proc = subprocess.run(command, capture_output=True, text=True, timeout=300,
                              creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        data = json.loads(target.read_text(encoding='utf-8'))
    except Exception as exc:
        result['error'] = '%s: %s' % (type(exc).__name__, str(exc)[:200])
        _merge_integrity({'selfcheck': result})
        shutil.rmtree(out, ignore_errors=True)
        raise SystemExit('包内自检无法运行（%s），拒绝产出' % result['error'])
    result.update(returncode=proc.returncode,
                  pack_version=data.get('check_version'), pack_count=data.get('check_count'),
                  items=len(data.get('items') or []),
                  summary=data.get('summary') or {},
                  summary_consistent=bool(data.get('summary_consistent')))
    build_info = {}
    try:
        build_info = json.loads((out / '_internal' / 'build-info.json').read_text(
            encoding='utf-8-sig'))
        result['package_version'] = build_info.get('version')
        result['package_check_version'] = build_info.get('check_version')
        result['build_sha'] = build_info.get('build_sha')
        result['package_content_sha256'] = build_info.get('package_content_sha256')
    except Exception as exc:
        result['build_info_error'] = '%s: %s' % (type(exc).__name__, str(exc)[:120])
    problems = []
    if proc.returncode != 0:
        problems.append('包内自检退出码 %s（summary 计数不自洽时为 3）' % proc.returncode)
    if not result['summary_consistent']:
        problems.append('包内 summary 计数不自洽：%s'
                        % (data.get('summary_error') or result['summary']))
    summary = result['summary'] if isinstance(result['summary'], dict) else {}
    states = sum(int(summary.get(key) or 0) for key in ('pass', 'degraded', 'fail', 'untested'))
    if states != result['items']:
        problems.append('summary 各 state 之和 %d != 实际项数 %d' % (states, result['items']))
    if result['pack_version'] != expected_version:
        problems.append('自检版本不一致：包内 %r != 源码 %r'
                        % (result['pack_version'], expected_version))
    if result['pack_count'] != expected_count:
        problems.append('自检项数不一致：包内 %r != 源码 %r'
                        % (result['pack_count'], expected_count))
    if result['items'] != expected_count:
        problems.append('包内实际产出 %d 项，源码注册 %d 项'
                        % (result['items'], expected_count))
    if result.get('build_info_error'):
        problems.append('包内 build-info.json 不可用：%s' % result['build_info_error'])
    if build_info:
        if build_info.get('check_version') != expected_version:
            problems.append('build-info 自检版本 %r != 源码 %r'
                            % (build_info.get('check_version'), expected_version))
        if build_info.get('check_version') != result['pack_version']:
            problems.append('build-info 版本 %r != 包内自检版本 %r'
                            % (build_info.get('check_version'), result['pack_version']))
        if int(build_info.get('check_count') or 0) != result['items']:
            problems.append('build-info 项数 %r != 包内自检项数 %r'
                            % (build_info.get('check_count'), result['items']))
        version = str(build_info.get('version') or '')
        tag = re.match(r'^\d{8}([a-z]\d*)$', version)
        if tag and not str(result['pack_version']).startswith(tag.group(1) + '-'):
            problems.append('包版本 %r 与自检版本 %r 的包标识不一致（应为 %s-…）'
                            % (version, result['pack_version'], tag.group(1)))
        if expected_bundle and version != expected_bundle:
            problems.append('build-info 包版本 %r != 期望 %r' % (version, expected_bundle))
    if problems:
        result['problems'] = problems
        _merge_integrity({'selfcheck': result})
        shutil.rmtree(out, ignore_errors=True)
        raise SystemExit('包内自检与源码不一致，拒绝产出：%s' % '；'.join(problems))
    result['ok'] = True
    _merge_integrity({'selfcheck': result})
    print('[build][selfcheck] ok：包内 %s / %d 项与源码一致；summary 自洽；包版本 %s'
          % (result['pack_version'], result['pack_count'], result.get('package_version')))
    return result


def _merge_integrity(extra):
    """把凭据扫描结果并入 build-integrity.json（成功/失败都要留证）。"""
    try:
        payload = json.loads(INTEGRITY.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        payload = {}
    payload.update(extra)
    INTEGRITY.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')


def _tree_size(path):
    total = 0
    files = 0
    for dirpath, _dirnames, filenames in os.walk(path):
        for name in filenames:
            try:
                total += (Path(dirpath) / name).stat().st_size
                files += 1
            except OSError:
                pass
    return total, files


# ---------------------------------------------------------------- 使用说明随包

def _inline_md(text):
    out = html.escape(text)
    out = re.sub(r'`([^`]+)`', lambda m: '<code>%s</code>' % m.group(1), out)
    out = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', out)
    out = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', out)
    return out


def _table_cells(line):
    cells = [cell.strip() for cell in line.strip().strip('|').split('|')]
    return cells


def _is_table_sep(line):
    return bool(re.match(r'^\s*\|?[\s:\-|]+\|?\s*$', line)) and '-' in line


def _render_html(markdown_text, title='咕嘎 · 评委安装与使用说明'):
    """极简 Markdown → 单文件 HTML（标题/表格/列表/代码/引用足够本说明使用）。"""
    lines = markdown_text.splitlines()
    body = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            i += 1
            continue
        if stripped.startswith('```'):
            i += 1
            block = []
            while i < len(lines) and not lines[i].strip().startswith('```'):
                block.append(lines[i])
                i += 1
            i += 1
            body.append('<pre><code>%s</code></pre>' % html.escape('\n'.join(block)))
            continue
        match = re.match(r'^(#{1,6})\s+(.*)$', stripped)
        if match:
            level = len(match.group(1))
            body.append('<h%d>%s</h%d>' % (level, _inline_md(match.group(2)), level))
            i += 1
            continue
        if re.match(r'^-{3,}$', stripped):
            body.append('<hr>')
            i += 1
            continue
        if '|' in stripped and i + 1 < len(lines) and _is_table_sep(lines[i + 1]):
            header = _table_cells(stripped)
            i += 2
            rows = []
            while i < len(lines) and '|' in lines[i] and lines[i].strip():
                rows.append(_table_cells(lines[i]))
                i += 1
            cells = ''.join('<th>%s</th>' % _inline_md(c) for c in header)
            parts = ['<table><thead><tr>%s</tr></thead><tbody>' % cells]
            for row in rows:
                parts.append('<tr>%s</tr>' % ''.join(
                    '<td>%s</td>' % _inline_md(c) for c in row))
            parts.append('</tbody></table>')
            body.append(''.join(parts))
            continue
        if stripped.startswith('>'):
            quoted = []
            while i < len(lines) and lines[i].strip().startswith('>'):
                quoted.append(lines[i].strip().lstrip('>').strip())
                i += 1
            body.append('<blockquote>%s</blockquote>' % _inline_md(' '.join(quoted)))
            continue
        if re.match(r'^[-*]\s+', stripped):
            items = []
            while i < len(lines) and re.match(r'^[-*]\s+', lines[i].strip()):
                items.append(_inline_md(re.sub(r'^[-*]\s+', '', lines[i].strip())))
                i += 1
            body.append('<ul>%s</ul>' % ''.join('<li>%s</li>' % x for x in items))
            continue
        if re.match(r'^\d+\.\s+', stripped):
            items = []
            while i < len(lines) and re.match(r'^\d+\.\s+', lines[i].strip()):
                items.append(_inline_md(re.sub(r'^\d+\.\s+', '', lines[i].strip())))
                i += 1
            body.append('<ol>%s</ol>' % ''.join('<li>%s</li>' % x for x in items))
            continue
        para = []
        while i < len(lines) and lines[i].strip() and not re.match(
                r'^(#{1,6}\s|```|>|[-*]\s|\d+\.\s)', lines[i].strip()):
            para.append(lines[i].strip())
            i += 1
        body.append('<p>%s</p>' % _inline_md(' '.join(para)))
    style = """
body{margin:0 auto;padding:28px 20px 60px;max-width:980px;background:#fff;
color:#1a1c20;font:15px/1.75 "Microsoft YaHei","PingFang SC",system-ui,sans-serif}
h1{font-size:26px;border-bottom:3px solid #f0b429;padding-bottom:8px}
h2{font-size:21px;margin-top:34px;border-left:5px solid #f0b429;padding-left:10px}
h3{font-size:17px;margin-top:24px}
table{border-collapse:collapse;width:100%;margin:12px 0;font-size:14px}
th,td{border:1px solid #d8dce2;padding:7px 9px;text-align:left;vertical-align:top}
th{background:#f5f7fa}
code{background:#f2f4f7;padding:1px 5px;border-radius:4px;
font-family:Consolas,monospace;font-size:13px}
pre{background:#1e2430;color:#e8edf5;padding:14px;border-radius:8px;overflow:auto}
pre code{background:none;color:inherit;padding:0}
blockquote{margin:10px 0;padding:8px 14px;background:#fff8e6;
border-left:4px solid #f0b429;color:#5b5344}
a{color:#0b66c3}
hr{border:0;border-top:1px solid #e3e7ed;margin:26px 0}
@media (max-width:640px){body{padding:16px 12px}table{font-size:12px}}
"""
    return ('<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            '<title>%s</title><style>%s</style></head><body>\n%s\n</body></html>'
            % (html.escape(title), style, '\n'.join(body)))


def _plain_text(markdown_text):
    """给没有浏览器关联的机器兜底：去掉 Markdown 记号，保留表格与缩进。"""
    out = []
    in_code = False
    for line in markdown_text.splitlines():
        stripped = line.strip()
        if stripped.startswith('```'):
            in_code = not in_code
            continue
        if not in_code:
            if re.match(r'^-{3,}$', stripped):
                out.append('-' * 60)
                continue
            if stripped.startswith('|') and _is_table_sep(stripped):
                continue
            if stripped.startswith('|'):
                line = ' | '.join(_table_cells(stripped))
            line = re.sub(r'^(#{1,6})\s+', '', line)
            line = re.sub(r'^>\s?', '', line)
            line = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'\1 (\2)', line)
            line = line.replace('**', '').replace('`', '')
        out.append(line)
    return '\n'.join(out) + '\n'


def build_manual():
    """按 docs 里的正文生成 zip 根目录的两份使用说明，返回 [(arcname, path)]。"""
    if not GUIDE_MD.is_file():
        raise SystemExit('缺少使用说明源文件：%s' % GUIDE_MD)
    text = GUIDE_MD.read_text(encoding='utf-8')
    GUIDE_FOLDER.mkdir(parents=True, exist_ok=True)
    html_path = GUIDE_FOLDER / GUIDE_NAMES[0]
    txt_path = GUIDE_FOLDER / GUIDE_NAMES[1]
    html_path.write_text(_render_html(text), encoding='utf-8-sig')
    txt_path.write_text(_plain_text(text), encoding='utf-8-sig')
    manuals = [(GUIDE_NAMES[0], html_path), (GUIDE_NAMES[1], txt_path)]
    for arcname, source in STATIC_GUIDES:
        if not source.is_file():
            raise SystemExit('缺少随包文档：%s' % source)
        manuals.append((arcname, source))
    return manuals


def make_release_zip(archive, folder, manuals):
    """说明放 zip 根目录，程序目录保持 GUGA-Desktop/ 一层，避免解压后找不到入口。"""
    pending = archive.parent / (archive.name + '.tmp')
    with zipfile.ZipFile(pending, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as handle:
        for arcname, path in manuals:
            handle.write(path, arcname)
        for path in sorted(folder.rglob('*')):
            if path.is_file():
                handle.write(path, path.relative_to(DIST).as_posix())
    os.replace(pending, archive)


def verify_release_zip(archive):
    """闸门：说明书必须在根目录且非空，主程序目录必须存在。"""
    problems = []
    with zipfile.ZipFile(archive) as handle:
        names = set(handle.namelist())
        for name in GUIDE_NAMES:
            if name not in names:
                problems.append('zip 根目录缺少 %s' % name)
            elif handle.getinfo(name).file_size < 1024:
                problems.append('%s 内容异常（<1KB）' % name)
        if 'GUGA-Desktop/GUGA-Desktop.exe' not in names:
            problems.append('缺少 GUGA-Desktop/GUGA-Desktop.exe')
    if problems:
        archive.unlink(missing_ok=True)
        raise SystemExit('压缩包校验失败：' + '；'.join(problems))
    print('[build][zip] 说明已在根目录：%s，主程序目录完整' % '、'.join(GUIDE_NAMES))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--zip', action='store_true', help='构建后压缩成 release zip')
    parser.add_argument('--zip-out', default='',
                        help='zip 输出路径（默认 dist/GUGA-Desktop-win64.zip）')
    parser.add_argument('--no-clean', action='store_true', help='保留 build 缓存（默认 --clean 全量重编）')
    parser.add_argument('--bundle-version', default='',
                        help='包版本标识（如 20261108i），用于 build-info 与构建闸门校验')
    parser.add_argument('--package-name', default='',
                        help='发行 zip 文件名（写入 build-info，诊断导出按它找原始 zip）')
    args = parser.parse_args()

    bundle_version = str(args.bundle_version or os.environ.get('GUGA_BUILD_TAG') or '')
    if bundle_version:
        os.environ['GUGA_BUNDLE_VERSION'] = bundle_version

    if not SPEC.exists():
        raise SystemExit('缺少 %s' % SPEC)
    _acquire_lock()

    # 防呆：本机配置里有真实 Key 时明确告知，并确保发布包只带模板、不复制运行期配置。
    secrets = set()
    local_config = ROOT / 'ai_config.json'
    if local_config.is_file():
        try:
            secrets = guard.collect_secrets(json.loads(local_config.read_text(encoding='utf-8-sig')))
        except (OSError, ValueError, UnicodeError):
            secrets = set()
    # GUGA_BUILD_SECRETS：指向不提交进仓库的真实 Key 文件，用于精确值比对。
    env_secrets = guard.load_secret_file(os.environ.get('GUGA_BUILD_SECRETS'))
    secrets |= env_secrets
    if env_secrets:
        print('[build][guard] 已从 GUGA_BUILD_SECRETS 载入 %d 个真实凭据作为比对针'
              % len(env_secrets))
    if secrets:
        print('[build][guard] 已载入 %d 个真实凭据作为比对针；发布包不携带运行期配置'
              '（只放 ai_config.example.json 模板），已确保不复制。' % len(secrets))
    else:
        print('[build][guard] 未载入真实凭据针（仍按 sk- 等形态扫描）；发布包只带模板')

    started = time.time()
    if WORK.exists() and not args.no_clean:
        shutil.rmtree(WORK, ignore_errors=True)
    if OUT.exists():
        shutil.rmtree(OUT, ignore_errors=True)
    WORK.mkdir(parents=True, exist_ok=True)

    cmd = [sys.executable, '-m', 'PyInstaller', SPEC.name,
           '--noconfirm', '--distpath', str(DIST), '--workpath', str(WORK)]
    if not args.no_clean:
        cmd.insert(3, '--clean')
    print('[build] ' + ' '.join(cmd))
    result = subprocess.run(cmd, cwd=str(ROOT))
    if result.returncode:
        raise SystemExit('PyInstaller 失败（退出码 %d）' % result.returncode)

    exe = OUT / 'GUGA-Desktop.exe'
    if not exe.exists():
        raise SystemExit('未生成 %s' % exe)

    # README 约定：配置模板放在 _internal/ 根，用户复制成 ai_config.json 填写
    template = ROOT / 'ai_config.example.json'
    internal = OUT / '_internal'
    if template.exists() and internal.exists():
        shutil.copy2(template, internal / 'ai_config.example.json')
    # 清掉任何残留的运行期配置（历史构建/本机调试遗留），发布包只允许模板。
    stale = internal / 'ai_config.json'
    if stale.exists():
        stale.unlink()
        print('[build][guard] 已移除 _internal/ai_config.json（运行期配置不进发行包）')

    # 包内固定位置写版本/构建 SHA/内容摘要（诊断导出优先读它）。
    build_info = write_build_info(OUT, bundle_version, args.package_name)

    # 发布前完整性闸门：缺 pywin32 / VC++ / 资源目录 / 帧数不足一律删除产物并失败。
    verify_bundle(OUT)

    # 发布前自检一致性闸门：包内自检项数/版本必须等于源码，防止旧自检被打进包。
    _selfcheck_gate(OUT)

    # 发布前强制扫描：解包 PYZ/pyc 后按形态扫，扫到真实 Key 或非示例配置就删除产物并失败。
    credentials = {}
    try:
        guard.assert_clean([OUT], secrets, purge=True, result=credentials)
    finally:
        # 成功与失败都留证：闸门结果必须落到 build-integrity.json。
        _merge_integrity({'credentials': credentials
                          or {'ok': False, 'error': '扫描未完成'}})
    print('[build] 凭据扫描通过：dist/GUGA-Desktop 内无真实 Key，也无非示例配置')

    folder_bytes, folder_files = _tree_size(OUT)
    try:
        import PyInstaller
        pyinstaller_version = PyInstaller.__version__
    except Exception:
        pyinstaller_version = 'unknown'
    report = dict(
        built_at=datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        entry='tools/comp_entry.py -> comp_main.py',
        spec=str(SPEC),
        exe=str(exe),
        exe_bytes=exe.stat().st_size,
        folder_bytes=folder_bytes,
        folder_mb=round(folder_bytes / (1024 * 1024), 1),
        folder_files=folder_files,
        seconds=round(time.time() - started, 1),
        python=sys.version.split()[0],
        pyinstaller=pyinstaller_version,
        version=build_info.get('version'),
        check_version=build_info.get('check_version'),
        check_count=build_info.get('check_count'),
        build_sha=build_info.get('build_sha'),
        package_content_sha256=build_info.get('package_content_sha256'),
        package_name=build_info.get('package_name'),
    )
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print('[build] ok exe=%s folder=%.1fMB files=%d %.1fs'
          % (exe, report['folder_mb'], folder_files, report['seconds']))

    if args.zip:
        # 写入前硬闸：输出必须是绝对路径，且不得落到 C:\Users\<用户> 根或直属一层；
        # 拒绝 ~/$HOME 这类写法（20261110w 事故：$home 把配置写到了用户目录根）。
        try:
            target = write_guard.resolve_write_path(
                args.zip_out or str(DIST / 'GUGA-Desktop-win64.zip'))
        except write_guard.UnsafeWritePath as exc:
            raise SystemExit('[build][blocked] %s' % exc)
        print('[build][path] zip 解析后的绝对路径：%s' % target)
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.parent.is_dir():
            raise SystemExit('[build][blocked] 父目录不存在：%s' % target.parent)
        manuals = build_manual()
        make_release_zip(target, OUT, manuals)
        verify_release_zip(target)
        if not target.is_file():
            raise SystemExit('[build][blocked] zip 写入后复核失败：%s' % target)
        print('[build][path] Test-Path 复核：%s -> True' % target)
        # zip 再解包逐条目扫一遍（文档/模板/内嵌 PYZ 都不放过）；有泄露则删除 zip。
        zip_credentials = {}
        try:
            guard.assert_clean([target], secrets, purge=True, result=zip_credentials)
        finally:
            _merge_integrity({'zip_credentials': zip_credentials
                              or {'ok': False, 'error': '扫描未完成'}})
        print('[build] zip 凭据扫描通过：解包后逐条目无真实 Key')
        zip_sha = write_zip_sidecar(target)
        print('[build] zip=%s %.1fMB' % (target, target.stat().st_size / (1024 * 1024)))
        report['zip'] = str(target)
        report['zip_bytes'] = target.stat().st_size
        report['zip_sha256'] = zip_sha
        report['manual'] = [str(GUIDE_FOLDER / name) for name in GUIDE_NAMES]
        REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
