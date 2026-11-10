# -*- coding: utf-8 -*-
"""MCP 通道实测：生成三份配置片段、写入本机配置、真实握手并跑通任务闭环。

做的事情（按顺序）：
1. 只读探测三款软件（命中情况）；
2. 每款生成配置片段，打印配置位置与“是否已接入”；
3. WorkBuddy / JoyCode 写入真实配置（写前备份），豆包只给界面指引（无本地文件）；
4. 按写入后的条目真实拉起 MCP server：initialize → list_tools → get_task；
5. 在临时工作区跑一遍任务闭环：get_task → report_progress → ask_guga（pending→answered）
   → submit_artifact，并读取回执；
6. 检查目标软件侧是否已经感知（WorkBuddy 的 mcp-tool-list、JoyCode 的 /guga-run 与技能）。

不会启动任何目标软件窗口；只拉起 guga_mcp_server.py 子进程，用完即退出。

用法：
    python scripts/verify_mcp_channels.py
    python scripts/verify_mcp_channels.py --json
    python scripts/verify_mcp_channels.py --no-write      # 只生成片段，不写本机配置
"""
from __future__ import annotations

import argparse
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

os.environ.setdefault('GUGA_APP_REGISTRY_CACHE',
                      str(Path(tempfile.mkdtemp(prefix='guga_mcp_cache_')) / 'cache.json'))

from core.adapters import app_registry  # noqa: E402
from core.adapters import mcp_channels  # noqa: E402

APPS = ('workbuddy', 'doubao', 'joycode')
TASK_ID = 'T-CONNECT-001'


def _server() -> dict:
    python = mcp_channels.python_command()
    script = mcp_channels.server_script()
    return dict(python=python, script=script,
                ok=bool(python.get('ok') and script.get('ok')))


async def _roundtrip(entry: dict, workspace: Path) -> dict:
    """用真实 stdio 配置跑完整任务闭环（临时工作区，不碰用户 .guga）。"""
    from mcp import Client
    from mcp.client.stdio import StdioServerParameters

    inbox = workspace / '.guga' / 'inbox'
    outbox = workspace / '.guga' / 'outbox'
    answers = workspace / '.guga' / 'answers'
    inbox.mkdir(parents=True, exist_ok=True)
    artifact = workspace / 'artifacts' / 'result.txt'
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text('咕嘎连接实测产物\n', encoding='utf-8')
    task = dict(task_id=TASK_ID, goal='验证 MCP 通道能领取任务并交回执',
                acceptance='get_task 返回本任务；submit_artifact 写出回执',
                deadline='', callback='verify-mcp-channels')
    (inbox / (TASK_ID + '.json')).write_text(
        json.dumps(task, ensure_ascii=False, indent=2), encoding='utf-8')

    env = {key: str(value) for key, value in dict(os.environ).items()}
    env.update({str(k): str(v) for k, v in (entry.get('env') or {}).items()})
    env['GUGA_WORKSPACE'] = str(workspace)
    params = StdioServerParameters(command=str(entry['command']),
                                   args=[str(item) for item in entry.get('args') or []],
                                   env=env)

    def payload(result):
        text = ''
        for item in (getattr(result, 'content', None) or []):
            text += str(getattr(item, 'text', '') or '')
        try:
            return json.loads(text)
        except ValueError:
            return {'raw': text}

    async with Client(params) as client:
        tools = [tool.name for tool in (await client.list_tools()).tools]
        got = payload(await client.call_tool('get_task', {}))
        progress = payload(await client.call_tool('report_progress', {
            'task_id': TASK_ID, 'summary': '连接实测：已领取任务', 'status': 'running'}))
        asked = payload(await client.call_tool('ask_guga', {
            'task_id': TASK_ID, 'question': '连接实测要不要继续？',
            'options': ['继续', '停止'], 'timeout_seconds': 0}))
        question_id = asked.get('question_id') or ''
        if question_id:
            answers.mkdir(parents=True, exist_ok=True)
            (answers / (question_id + '.json')).write_text(json.dumps({
                'task_id': TASK_ID, 'question_id': question_id,
                'answer': '继续（verify 脚本模拟咕嘎回答）',
                'answered_by': 'guga-verify',
                'answered_at': time.strftime('%Y-%m-%dT%H:%M:%S')},
                ensure_ascii=False, indent=2), encoding='utf-8')
        answered = payload(await client.call_tool('ask_guga', {
            'task_id': TASK_ID, 'question': '连接实测要不要继续？',
            'options': ['继续', '停止'], 'timeout_seconds': 5}))
        receipt = payload(await client.call_tool('submit_artifact', {
            'task_id': TASK_ID, 'artifact_paths': [str(artifact)],
            'self_check': '连接实测：工具依次调用成功，回执由 submit_artifact 写出', 'status': 'done'}))

    receipt_file = outbox / (TASK_ID + '.json')
    return dict(
        tools=tools,
        get_task=got,
        report_progress=progress,
        ask_guga_pending=asked,
        ask_guga_answered=answered,
        submit=receipt,
        receipt_path=str(receipt_file),
        receipt_exists=receipt_file.is_file(),
        receipt=json.loads(receipt_file.read_text(encoding='utf-8-sig'))
        if receipt_file.is_file() else None,
    )


def _app_process_running(name: str) -> bool:
    try:
        import psutil
    except Exception:
        return False
    for proc in psutil.process_iter(['name']):
        try:
            if str(proc.info.get('name') or '').casefold() == name.casefold():
                return True
        except Exception:
            continue
    return False


def _workbuddy_tool_list() -> dict:
    path = Path(os.path.expandvars(r'%USERPROFILE%\.workbuddy\mcp-tool-list.json'))
    try:
        raw = path.read_text(encoding='utf-8-sig')
    except OSError:
        return dict(path=str(path), exists=False, has_guga=False)
    return dict(path=str(path), exists=True, has_guga='"guga"' in raw or 'guga' in raw.lower(),
                size=len(raw), mtime=time.strftime('%Y-%m-%dT%H:%M:%S',
                                                   time.localtime(path.stat().st_mtime)))


def _joycode_assets(workspace: Path) -> dict:
    command = workspace / '.joycode' / 'commands' / 'guga-run.md'
    skill = workspace / '.joycode' / 'skills' / 'guga-worker' / 'SKILL.md'
    project_config = workspace / '.joycode' / 'mcp.json'
    user_config = Path(os.path.expandvars(r'%USERPROFILE%\.joycode\joycode-mcp.json'))
    return dict(
        command=str(command), command_exists=command.is_file(),
        skill=str(skill), skill_exists=skill.is_file(),
        project_config=str(project_config), project_config_exists=project_config.is_file(),
        user_config=str(user_config), user_config_exists=user_config.is_file(),
    )


def _doubao_evidence() -> dict:
    app_dir = Path(os.path.expandvars(r'%LOCALAPPDATA%\Doubao'))
    local_mcp = list(app_dir.glob('**/mcp*.json')) if app_dir.is_dir() else []
    return dict(
        install_dir=str(app_dir), install_dir_exists=app_dir.is_dir(),
        local_mcp_files=[str(path) for path in local_mcp[:5]],
        conclusion=('豆包没有本地 mcpServers 文件；个人 MCP 连接器只能登录后在界面创建，'
                    '保存在云端（AGWManageCreatePersonalConnector），因此无法自动写入/离线检测。'),
    )


def run(workspace: Path, write: bool) -> dict:
    report = dict(contract=mcp_channels.CONTRACT, started_at=time.strftime('%Y-%m-%dT%H:%M:%S'),
                  workspace=str(workspace), write_enabled=write, server=_server(),
                  probes={}, snippets={}, applied={}, handshakes={}, roundtrip={},
                  runtimes={}, doubao=_doubao_evidence(), onboarding={})
    report['onboarding'] = mcp_channels.onboarding(apps=APPS, workspace=workspace, force_probe=True)
    for item in report['onboarding']['apps']:
        report['probes'][item['app']] = dict(
            installed=item['installed'], probe_status=item['probe_status'],
            exe=item['exe'], channel=item['channel'].get('direction'),
            transport=item['channel'].get('transport'),
            registration=item['channel'].get('registration'),
            added=item['channel'].get('added'), action=item['action'],
            message=item['probe_message'])

    for app_id in APPS:
        generated = mcp_channels.snippet(app_id, workspace=workspace)
        status = mcp_channels.channel_status(app_id, workspace=workspace)
        report['snippets'][app_id] = dict(
            ok=generated.get('ok'), kind=generated.get('kind'),
            registration=generated.get('registration'),
            text=generated.get('text', ''), config_path=status.get('config_path', ''),
            config_paths=status.get('config_paths', []),
            added=status.get('added'), conflict=status.get('conflict'),
            action=status.get('action'), message=status.get('message'),
            entry=status.get('entry') or generated.get('entry') or {})

    for app_id in APPS:
        if app_id == 'doubao':
            report['applied'][app_id] = dict(
                ok=False, status='ui_managed',
                message='豆包无本地配置文件，已生成连接器表单字段；需登录后在界面添加')
            continue
        if not write:
            report['applied'][app_id] = dict(ok=True, status='skipped',
                                             message='--no-write：只生成片段，未写入配置')
            continue
        result = mcp_channels.apply(app_id, workspace=workspace)
        report['applied'][app_id] = result
        after = mcp_channels.channel_status(app_id, workspace=workspace)
        report['snippets'][app_id]['added_after'] = after.get('added')
        report['snippets'][app_id]['config_path_after'] = after.get('config_path')

    tmp_ws = Path(tempfile.mkdtemp(prefix='guga_mcp_roundtrip_'))
    try:
        for app_id in APPS:
            entry = report['snippets'][app_id]['entry']
            if app_id == 'doubao':
                # 豆包条目是界面表单（command+params），不是文件条目；握手用底层 stdio 配置，
                # 证明“用户按表单填完后，服务端确实能被连上”。
                entry = mcp_channels.mcp_entry(app_id, workspace=workspace)
            if not isinstance(entry, dict) or not entry.get('command'):
                report['handshakes'][app_id] = dict(
                    ok=False, status='no_entry',
                    message='没有可用的 MCP 条目（见 server 段）')
                continue
            result = mcp_channels.verify_connection(
                app_id, entry=entry, workspace=tmp_ws, timeout=30)
            if app_id == 'doubao':
                result['note'] = '服务端可用；豆包侧仍卡在登录+界面新建连接器，未完成注册'
            report['handshakes'][app_id] = result
            if app_id == 'workbuddy':
                try:
                    report['roundtrip'][app_id] = asyncio.run(
                        asyncio.wait_for(_roundtrip(entry, tmp_ws), timeout=45))
                except Exception as exc:
                    report['roundtrip'][app_id] = dict(
                        ok=False, status='exception',
                        message='%s: %s' % (type(exc).__name__, str(exc)[:200]))
    finally:
        shutil.rmtree(tmp_ws, ignore_errors=True)

    report['runtimes']['workbuddy'] = dict(
        running=_app_process_running('WorkBuddy.exe'),
        tool_list=_workbuddy_tool_list(),
        note='mcp.json 写入后需重启 WorkBuddy 才会加载；上面握手用同一份命令验证服务端可用')
    report['runtimes']['joycode'] = dict(
        running=_app_process_running('JoyCode.exe'),
        assets=_joycode_assets(workspace),
        note='工作区 .joycode/mcp.json 新建后重启 JoyCode；/guga-run 与 guga-worker 技能已就绪')
    report['runtimes']['doubao'] = dict(
        running=_app_process_running('Doubao.exe'), blocked_at='login+ui_manage',
        note='无本地文件入口，无法自动注册；需登录后在“连接器/个人 MCP”添加')
    report['finished_at'] = time.strftime('%Y-%m-%dT%H:%M:%S')
    return report


def _print_human(report):
    print('== MCP server ==')
    python = report['server']['python']
    script = report['server']['script']
    print('  python: %s (%s)' % (python.get('command'), python.get('source')))
    print('  script: %s' % script.get('path'))
    print('\n== 本机探测与通道 ==')
    for app_id, item in report['probes'].items():
        print('  %-10s installed=%-5s %-12s registration=%-4s added=%s action=%s' % (
            app_id, item['installed'], item['transport'], item['registration'],
            item['added'], item['action']))
        print('             %s' % item['message'])
    print('\n== 配置片段与写入 ==')
    for app_id, item in report['snippets'].items():
        print('  [%s] %s' % (app_id, item['text'].splitlines()[0] if item['text'] else '无片段'))
        print('      config=%s added=%s' % (item['config_path'] or '(无本地文件)', item['added']))
        applied = report['applied'].get(app_id) or {}
        print('      apply=%s %s' % (applied.get('status'), applied.get('message', '')))
    print('\n== 真实握手 ==')
    for app_id, item in report['handshakes'].items():
        print('  %-10s %s %s' % (app_id, item.get('status'), item.get('message', '')))
        if item.get('tools'):
            print('             tools=%s' % ', '.join(item['tools']))
    rt = report['roundtrip'].get('workbuddy')
    if rt:
        print('\n== 任务闭环（临时工作区）==')
        print('  get_task: %s' % json.dumps(rt.get('get_task'), ensure_ascii=False)[:300])
        print('  report_progress: %s' % json.dumps(rt.get('report_progress'), ensure_ascii=False)[:200])
        print('  ask_guga pending: %s' % json.dumps(rt.get('ask_guga_pending'), ensure_ascii=False)[:260])
        print('  ask_guga answered: %s' % json.dumps(rt.get('ask_guga_answered'), ensure_ascii=False)[:260])
        print('  submit_artifact: %s' % json.dumps(rt.get('submit'), ensure_ascii=False)[:260])
        print('  receipt_exists=%s path=%s' % (rt.get('receipt_exists'), rt.get('receipt_path')))
    print('\n== 软件侧现状 ==')
    print('  WorkBuddy: running=%s tool_list_has_guga=%s (%s)' % (
        report['runtimes']['workbuddy']['running'],
        report['runtimes']['workbuddy']['tool_list']['has_guga'],
        '需重启生效'))
    print('  JoyCode: running=%s command=%s skill=%s project_config=%s user_config=%s' % (
        report['runtimes']['joycode']['running'],
        report['runtimes']['joycode']['assets']['command_exists'],
        report['runtimes']['joycode']['assets']['skill_exists'],
        report['runtimes']['joycode']['assets']['project_config_exists'],
        report['runtimes']['joycode']['assets']['user_config_exists']))
    print('  豆包: %s' % report['runtimes']['doubao']['note'])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--workspace', default='')
    parser.add_argument('--no-write', action='store_true',
                        help='只生成片段，不写 WorkBuddy/JoyCode 配置')
    args = parser.parse_args()
    workspace = Path(args.workspace).expanduser() if args.workspace \
        else mcp_channels.default_workspace()
    report = run(workspace, write=not args.no_write)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print_human(report)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
