# -*- coding: utf-8 -*-
"""MCP 自报路径自测：注册落盘 → 覆盖错误声明路径 → 脏记录回退 → 删除后回退探测。

不启动任何真实 GUI；用 notepad.exe 复制成测试 exe，声明与缓存全部指向临时目录。
"""
from __future__ import annotations

import asyncio
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

from core import guga_paths
from core.adapters import app_registry, app_reports

BUILD = ROOT / 'build'
SERVER = ROOT / 'core' / 'adapters' / 'guga_mcp_server.py'


def _declaration(temp: Path, probe_exe: Path) -> Path:
    template = json.loads((ROOT / 'core' / 'adapters' / 'apps' / '_template.json')
                          .read_text(encoding='utf-8'))
    template.update(id='mcptest', name='MCP 自报测试', aliases=[], capabilities=['chat'],
                    process_names=['GUGA-Probe.exe'], automation='ui_only', adapter='',
                    notes='自测用假声明')
    start_menu_dir = temp / 'empty-start-menu'
    start_menu_dir.mkdir(parents=True, exist_ok=True)
    template['install'] = dict(
        user_override=True, env=['GUGA_PROBE_EXE'],
        common_paths=['D:\\definitely-missing\\GUGA-Probe.exe'],
        registry={}, start_menu={'aliases': [], 'roots': [str(start_menu_dir)]},
        portable={'roots': [], 'name_globs': [], 'depth': 1, 'budget_ms': 100,
                  'max_entries': 10},
        path_lookup=False, detect_running=False,
    )
    template['launch'].update(exe_name='GUGA-Probe.exe', args=[], timeout_seconds=20)
    template['ready'] = dict(window={'title_keywords': ['记事本', 'Notepad'],
                                     'process': 'GUGA-Probe.exe', 'class_keywords': []},
                             min_width=200, min_height=100, extra_settle_seconds=0)
    template['receipt'] = dict(mode='ui_clipboard', receipt_required=False, notes='自测')
    template['login'] = dict(required=False, signals=[], hint='')
    template['channel'].update(config_path='', config_paths=[], registration='file')
    template['download'] = dict(url='', hint='')
    folder = temp / 'adapters'
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / 'mcptest.json'
    path.write_text(json.dumps(template, ensure_ascii=False, indent=2), encoding='utf-8')
    return folder


def _summary(result):
    return dict(status=result.get('status'), source=result.get('source'),
                exe=result.get('exe'),
                warnings=[item.get('detail') for item in result.get('warnings') or []],
                message=str(result.get('message') or '')[:220])


async def _mcp_register(probe_exe: Path) -> dict:
    from mcp import Client
    from mcp.client.stdio import StdioServerParameters

    env = dict(os.environ)
    env.update(GUGA_CLIENT_ID='mcptest-client', PYTHONIOENCODING='utf-8')
    params = StdioServerParameters(command=sys.executable, args=[str(SERVER)], env=env)
    async with Client(params) as client:
        tools = [tool.name for tool in (await client.list_tools()).tools]
        result = await client.call_tool('report_app', dict(
            app_id='mcptest', name='MCP 自报测试', exe_path=str(probe_exe),
            version='1.2.3', capabilities=['chat', 'probe']))
        payload = getattr(result, 'structuredContent', None) or \
            getattr(result, 'structured_content', None)
        if payload is None:
            text = ''.join(str(getattr(item, 'text', '')) for item in (result.content or []))
            payload = json.loads(text) if text.strip() else {}
    return dict(tools=tools, result=payload)


def main() -> dict:
    temp = Path(tempfile.mkdtemp(prefix='guga_discovery_'))
    probe_exe = temp / 'GUGA-Probe.exe'
    shutil.copy2(Path(os.environ.get('WINDIR', r'C:\Windows')) / 'System32' / 'notepad.exe',
                 probe_exe)
    folder = _declaration(temp, probe_exe)
    os.environ['GUGA_APP_ADAPTERS'] = str(folder)
    os.environ['GUGA_APP_REGISTRY_CACHE'] = str(temp / 'registry_cache.json')
    os.environ['GUGA_APP_REGISTRY_USER'] = str(temp / 'user_overrides.json')
    os.environ['GUGA_PROBE_EXE'] = str(probe_exe)
    app_registry.invalidate()

    report = dict(contract='guga.mcp_discovery/1', started_at=time.strftime('%Y-%m-%dT%H:%M:%S'),
                  temp=str(temp), probe_exe=str(probe_exe), report_path=str(app_reports.report_path()),
                  steps={})

    # 1) 基线：自报前由 env 命中（声明里 common_paths 是错误路径）
    base = app_registry.probe('mcptest', force=True)
    report['steps']['baseline_env'] = _summary(base)

    # 2) 通过 MCP 工具注册，验证落盘与回读
    registration = asyncio.run(_mcp_register(probe_exe))
    report['steps']['mcp'] = registration
    valid = app_reports.valid_report('mcptest')
    report['steps']['persisted'] = dict(valid=valid.get('valid'), exe=valid.get('exe'),
                                        record=valid.get('record'),
                                        file_exists=app_reports.report_path().is_file(),
                                        raw=json.loads(app_reports.report_path()
                                                       .read_text(encoding='utf-8-sig')))

    # 3) 去掉 env，让声明里的错误路径暴露出来 —— 自报路径应覆盖它
    os.environ.pop('GUGA_PROBE_EXE', None)
    app_registry.invalidate()
    claimed = app_registry.probe('mcptest', force=True)
    report['steps']['report_overrides_bad_declaration'] = _summary(claimed)

    # 4) 制造脏记录（路径被移动/删除）：必须回退到探测并记原因
    raw = json.loads(app_reports.report_path().read_text(encoding='utf-8-sig'))
    raw['apps']['mcptest']['exe'] = str(temp / 'moved' / 'GUGA-Probe.exe')
    guga_paths.write_config(raw, path=app_reports.report_path())
    os.environ['GUGA_PROBE_EXE'] = str(probe_exe)
    app_registry.invalidate()
    dirty = app_registry.probe('mcptest', force=True)
    report['steps']['stale_report_falls_back'] = _summary(dirty)

    # 5) 删除记录后回退：有 env 时仍能命中；无 env 时返回明确状态而不是报错
    app_reports.delete_report('mcptest')
    os.environ.pop('GUGA_PROBE_EXE', None)
    app_registry.invalidate()
    removed = app_registry.probe('mcptest', force=True)
    report['steps']['removed_falls_back'] = _summary(removed)
    os.environ['GUGA_PROBE_EXE'] = str(probe_exe)
    app_registry.invalidate()
    recovered = app_registry.probe('mcptest', force=True)
    report['steps']['removed_env_detection'] = _summary(recovered)

    # 收尾：不把测试记录留在真实注册表
    app_reports.delete_report('mcptest')
    report['finished_at'] = time.strftime('%Y-%m-%dT%H:%M:%S')
    report['passed'] = (
        report['steps']['mcp']['result'].get('ok') is True
        and report['steps']['persisted']['valid']
        and report['steps']['report_overrides_bad_declaration']['source'] == 'mcp_report'
        and '已失效' in (report['steps']['stale_report_falls_back']['warnings'] or [''])[0]
        and report['steps']['stale_report_falls_back']['source'] == 'env'
        and report['steps']['removed_falls_back']['status'] == 'not_installed'
        and report['steps']['removed_env_detection']['status'] == 'ready'
    )
    shutil.rmtree(temp, ignore_errors=True)
    BUILD.mkdir(parents=True, exist_ok=True)
    (BUILD / 'mcp_discovery_evidence.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return report


if __name__ == '__main__':
    result = main()
    print(json.dumps(dict(passed=result['passed'],
                          report_path=result['report_path'],
                          tools=result['steps']['mcp']['tools'],
                          mcp_result={key: result['steps']['mcp']['result'].get(key)
                                      for key in ('ok', 'message', 'path')},
                          persisted=dict(valid=result['steps']['persisted']['valid'],
                                         exe=result['steps']['persisted']['exe'],
                                         record=result['steps']['persisted']['record']),
                          report_wins=result['steps']['report_overrides_bad_declaration'],
                          stale_fallback=result['steps']['stale_report_falls_back'],
                          removed_fallback=result['steps']['removed_falls_back'],
                          env_recovered=result['steps']['removed_env_detection']),
                     ensure_ascii=False, indent=2))
    raise SystemExit(0 if result['passed'] else 1)
