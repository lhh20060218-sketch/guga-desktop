# -*- coding: utf-8 -*-
"""声明式软件适配注册表：只读探测 + 模拟场景验证脚本。

默认只做只读探测（注册表、文件路径、快捷方式），不会拉起任何软件。
``--launch-mechanism`` 会用系统自带记事本启动一次并立即关闭，仅验证 Popen→就绪→关闭链路；
``--launch-real`` 只在目标软件已经有可见窗口时调用 launch（预期 already_running），不新起实例。

用法：
    python scripts/verify_app_registry.py
    python scripts/verify_app_registry.py --json
    python scripts/verify_app_registry.py --launch-mechanism
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_WORK_BASE = Path(tempfile.mkdtemp(prefix='guga_app_registry_verify_'))
os.environ['GUGA_APP_REGISTRY_CACHE'] = str(_WORK_BASE / 'cache.json')
os.environ['GUGA_APP_REGISTRY_USER'] = str(_WORK_BASE / 'user_override.json')
os.environ.pop('GUGA_APP_ADAPTERS', None)

from core.adapters import app_registry as registry  # noqa: E402


def _brief(result):
    keys = ('id', 'name', 'status', 'installed', 'exe', 'source', 'source_label',
            'elapsed_ms', 'cached', 'running', 'message')
    data = {key: result.get(key) for key in keys}
    data['errors'] = result.get('errors') or []
    data['incomplete'] = result.get('incomplete') or []
    channel = result.get('channel') or {}
    data['channel'] = {key: channel.get(key) for key in
                       ('direction', 'transport', 'registration', 'fallback', 'config_path')}
    data['download'] = result.get('download') or {}
    return data


def _print_result(result, prefix=''):
    line = ('%s%-12s status=%-18s src=%-14s %7.1fms%s' %
            (prefix, result.get('id'), result.get('status'),
             result.get('source') or '-', result.get('elapsed_ms') or 0,
             ' [cache]' if result.get('cached') else ''))
    print(line)
    if result.get('exe'):
        print('    exe: %s' % result['exe'])
    channel = result.get('channel') or {}
    if channel.get('direction'):
        print('    channel: %s / %s / registration=%s / fallback=%s / config=%s' % (
            channel.get('direction'), channel.get('transport'),
            channel.get('registration'), channel.get('fallback'),
            channel.get('config_path') or '(无本地文件)'))
    print('    %s' % result.get('message'))


def _base_decl(app_id, name, exe_name, install, **ready):
    window = dict(title_keywords=[name, exe_name], process=exe_name, class_keywords=[])
    window.update(ready.pop('window', {}) or {})
    decl = {
        'schema': 'guga.app_adapter/1',
        'id': app_id,
        'name': name,
        'aliases': [name],
        'capabilities': ['chat'],
        'process_names': [exe_name],
        'install': install,
        'launch': {'exe_name': exe_name, 'args': [], 'cwd': 'exe_dir',
                   'timeout_seconds': 20, 'show': 'min_no_activate',
                   'single_instance': True},
        'ready': {'window': window, 'min_width': 200, 'min_height': 150,
                  'extra_settle_seconds': 0, 'input_anchor': {'must_exist': False}},
        'anchors': {'input': {'uia': {'control_types': ['Edit']}},
                    'send': {'keys': ['ENTER']},
                    'done': {'any': ['stop_button_gone']},
                    'failure_codes': []},
        'receipt': {'mode': 'ui_clipboard'},
        'login': {'required': False, 'signals': [], 'hint': ''},
    }
    decl['ready'].update(ready)
    return decl


def _install(common_paths=None, env=None, registry_cfg=None, menu_root=None,
             portable=None, path_lookup=False, detect_running=False):
    aliases = ['guga-sim-never-match']
    roots = [str(menu_root)] if menu_root else []
    return {
        'user_override': True,
        'env': list(env or []),
        'common_paths': list(common_paths or []),
        'registry': registry_cfg or {},
        'start_menu': {'aliases': aliases, 'roots': roots},
        'portable': portable or {},
        'path_lookup': path_lookup,
        'detect_running': detect_running,
    }


def _prepare_scenario(name, declarations, run):
    folder = _WORK_BASE / name
    folder.mkdir(parents=True, exist_ok=True)
    for decl in declarations:
        path = folder / ('%s.json' % decl['id'])
        path.write_text(json.dumps(decl, ensure_ascii=False, indent=2), encoding='utf-8')
    os.environ['GUGA_APP_ADAPTERS'] = str(folder)
    registry.declarations(force=True)
    registry.invalidate()
    try:
        return run()
    finally:
        os.environ.pop('GUGA_APP_ADAPTERS', None)
        registry.declarations(force=True)
        registry.invalidate()


def _make_fake_exe(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b'MZ' + b'\0' * 64)
    return path


def _other_drive_root():
    for candidate in (Path('D:/'), Path('E:/')):
        if candidate.is_dir():
            return candidate / 'rengongzhineng' / '.guga_app_registry_sim'
    return _WORK_BASE / 'other_drive_sim'


def simulate():
    menu = _WORK_BASE / 'empty_menu'
    menu.mkdir(parents=True, exist_ok=True)
    empty_portable = _WORK_BASE / 'empty_portable'
    empty_portable.mkdir(parents=True, exist_ok=True)
    exe = 'GugaSim.exe'

    results = {}

    # 场景 1：模拟未安装（所有来源都检查成功但没命中）
    decl = _base_decl('sim_uninstalled', 'GugaSim', exe,
                      _install(common_paths=[str(_WORK_BASE / 'missing' / exe)],
                               menu_root=menu))
    decl['download'] = {'url': 'https://example.com/guga-sim-download',
                        'hint': '模拟下载页：用于验证未安装提示'}
    results['uninstalled'] = _prepare_scenario(
        'uninstalled', [decl], lambda: registry.probe('sim_uninstalled', force=True))

    # 场景 2：模拟装在非默认盘（D:/E:）
    drive_root = _other_drive_root()
    if drive_root.exists():
        shutil.rmtree(drive_root, ignore_errors=True)
    target = _make_fake_exe(drive_root / 'Vendor' / 'GugaSim' / exe)
    decl = _base_decl('sim_other_drive', 'GugaSim', exe,
                      _install(common_paths=[str(target)], menu_root=menu))
    results['other_drive'] = _prepare_scenario(
        'other_drive', [decl], lambda: registry.probe('sim_other_drive', force=True))
    results['other_drive']['fixture'] = str(target)

    # 场景 3：模拟绿色版解压目录（只有 portable 扫描能命中）
    portable_root = _WORK_BASE / 'portable'
    portable_target = _make_fake_exe(portable_root / 'GreenVendor' / 'sub' / exe)
    decl = _base_decl('sim_portable', 'GugaSim', exe,
                      _install(
                          common_paths=[str(_WORK_BASE / 'missing2' / exe)],
                          menu_root=menu,
                          portable={'roots': [str(portable_root)],
                                    'name_globs': [exe], 'depth': 3,
                                    'budget_ms': 1200, 'max_entries': 200}))
    results['portable'] = _prepare_scenario(
        'portable', [decl], lambda: registry.probe('sim_portable', force=True))
    results['portable']['fixture'] = str(portable_target)

    # 场景 4：用户手工指定路径（绿色版/异盘/特殊目录最可靠）
    override_target = _make_fake_exe(_WORK_BASE / 'override' / 'Manual' / exe)
    decl = _base_decl('sim_override', 'GugaSim', exe,
                      _install(common_paths=[str(_WORK_BASE / 'missing_override' / exe)],
                               menu_root=menu))

    def run_override():
        registry.set_override('sim_override', override_target, note='绿色版手工指定')
        try:
            return registry.probe('sim_override', force=True)
        finally:
            registry.clear_override('sim_override')

    results['user_override'] = _prepare_scenario('override', [decl], run_override)
    results['user_override']['fixture'] = str(override_target)

    # 场景 5：缓存目录不可写（模拟 Program Files / 受限目录），探测结果不能受影响
    cache_target = _make_fake_exe(_WORK_BASE / 'cache_readonly' / 'Vendor' / exe)
    decl = _base_decl('sim_cache_readonly', 'GugaSim', exe,
                      _install(common_paths=[str(cache_target)], menu_root=menu))
    original_cache = os.environ.get('GUGA_APP_REGISTRY_CACHE')

    def run_cache_readonly():
        os.environ['GUGA_APP_REGISTRY_CACHE'] = str(_WORK_BASE)  # 指向目录，写入必然失败
        try:
            return registry.probe('sim_cache_readonly', force=True)
        finally:
            if original_cache:
                os.environ['GUGA_APP_REGISTRY_CACHE'] = original_cache
            else:
                os.environ.pop('GUGA_APP_REGISTRY_CACHE', None)

    results['cache_readonly'] = _prepare_scenario(
        'cache_readonly', [decl], run_cache_readonly)
    results['cache_readonly']['fixture'] = str(cache_target)

    # 场景 6：模拟环境变量指向失效路径 → 明确返回 unknown，而不是 not_installed
    os.environ['GUGA_SIM_BAD_EXE'] = str(_WORK_BASE / 'missing3' / exe)
    decl = _base_decl('sim_unknown', 'GugaSim', exe,
                      _install(env=['GUGA_SIM_BAD_EXE'], menu_root=menu,
                               portable={'roots': [str(empty_portable)],
                                         'name_globs': [exe], 'depth': 1,
                                         'budget_ms': 400, 'max_entries': 100}))
    try:
        results['unknown'] = _prepare_scenario(
            'unknown', [decl], lambda: registry.probe('sim_unknown', force=True))
    finally:
        os.environ.pop('GUGA_SIM_BAD_EXE', None)

    # 场景 5：注册表读取被拒绝（故障注入，模拟普通用户 / 组策略限制）
    decl = _base_decl('sim_registry_denied', 'GugaSim', exe,
                      _install(menu_root=menu,
                               registry_cfg={'uninstall': [
                                   {'hive': 'HKLM', 'view': 'any',
                                    'display_name_contains': ['guga-sim']}],
                                   'app_paths': []}))
    folder = _WORK_BASE / 'registry_denied'
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'sim_registry_denied.json').write_text(
        json.dumps(decl, ensure_ascii=False, indent=2), encoding='utf-8')
    os.environ['GUGA_APP_ADAPTERS'] = str(folder)
    registry.declarations(force=True)
    registry.invalidate()
    original_open = registry._reg_open

    def denied(*_args, **_kwargs):
        raise PermissionError('注入：拒绝访问')

    registry._reg_open = denied
    try:
        results['registry_denied'] = registry.probe('sim_registry_denied', force=True)
    finally:
        registry._reg_open = original_open
        os.environ.pop('GUGA_APP_ADAPTERS', None)
        registry.declarations(force=True)
        registry.invalidate()

    return results


def launch_mechanism():
    """用系统记事本验证启动链路；启动一次并立即关闭，不碰用户已开的软件。"""
    menu = _WORK_BASE / 'empty_menu'
    menu.mkdir(parents=True, exist_ok=True)
    notepad = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32' / 'notepad.exe'
    if not notepad.is_file():
        return dict(status='blocked', message='系统里没有 notepad.exe，跳过启动链路验证')
    decl = _base_decl('sim_launch', 'NotepadSim', 'notepad.exe',
                      _install(common_paths=[str(notepad)], menu_root=menu),
                      window={'title_keywords': ['记事本', 'Notepad', '无标题', 'Untitled'],
                              'process': 'notepad.exe'},
                      input_anchor={'must_exist': False})
    decl['launch']['timeout_seconds'] = 15

    def run():
        return registry.launch('sim_launch', verify=True, timeout=15, close_after_probe=True)

    return _prepare_scenario('launch', [decl], run)


def real_launch(ids):
    out = {}
    for app_id in ids:
        decl = registry.declaration(app_id)
        if not decl:
            out[app_id] = dict(status='unknown_app', message='无声明')
            continue
        window = registry._find_window(decl, include_minimized=True)
        if not window:
            out[app_id] = dict(
                status='skipped', message='当前没有可见窗口；为避免打扰用户，不执行真实启动')
            continue
        out[app_id] = registry.launch(app_id, verify=True, timeout=5)
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--json', action='store_true', help='输出完整 JSON')
    parser.add_argument('--launch-mechanism', action='store_true',
                        help='用记事本验证一次启动链路（会启动并关闭一次）')
    parser.add_argument('--launch-real', action='store_true',
                        help='仅当目标软件已有可见窗口时调用 launch，验证 already_running')
    parser.add_argument('--ids', default='doubao,workbuddy,joycode')
    args = parser.parse_args()

    ids = [item.strip() for item in args.ids.split(',') if item.strip()]
    report = dict(started_at=time.strftime('%Y-%m-%dT%H:%M:%S'),
                  declaration_dirs=[str(path) for path in registry.declaration_dirs()],
                  cache=str(registry.cache_path()), real={}, simulated={})

    invalid = registry.declaration_errors()
    if invalid:
        report['invalid_declarations'] = invalid
    if not args.json:
        print('== 声明目录 ==')
        for path in registry.declaration_dirs():
            print('  %s' % path)
        if invalid:
            print('!! 声明不合法: %s' % json.dumps(invalid, ensure_ascii=False))
        print('\n== 本机只读探测（cold → warm） ==')
    for app_id in ids:
        cold = registry.probe(app_id, force=True)
        warm = registry.probe(app_id)
        report['real'][app_id] = dict(cold=_brief(cold), warm=_brief(warm))
        if not args.json:
            _print_result(cold, prefix='cold ')
            _print_result(warm, prefix='warm ')

    if not args.json:
        print('\n== 模拟场景 ==')
    report['simulated'] = {}
    for name, result in simulate().items():
        item = _brief(result)
        item['fixture'] = result.get('fixture')
        report['simulated'][name] = item

    if not args.json:
        for name, result in report['simulated'].items():
            _print_result(result, prefix=name.ljust(14))

    if args.launch_mechanism:
        launched = launch_mechanism()
        report['launch_mechanism'] = launched
        if not args.json:
            print('\n== 启动链路（记事本，启动并关闭一次） ==')
            print(json.dumps(launched, ensure_ascii=False, indent=2))

    if args.launch_real:
        report['launch_real'] = real_launch(ids)
        if not args.json:
            print('\n== 真实 launched（已有窗口时只返回 already_running） ==')
            print(json.dumps(report['launch_real'], ensure_ascii=False, indent=2))

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print('\n完成时间: %s' % time.strftime('%Y-%m-%dT%H:%M:%S'))

    if _WORK_BASE.exists():
        shutil.rmtree(_WORK_BASE, ignore_errors=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
