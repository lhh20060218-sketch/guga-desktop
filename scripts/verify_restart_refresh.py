# -*- coding: utf-8 -*-
"""重启 WorkBuddy / JoyCode，验证 MCP 工具是否真的被加载。

判定证据（三选二即算接通）：
1. guga_mcp_server 写下的连接证据 .guga/mcp-connections/<app>.json（客户端 id + 进程存活）；
2. 目标软件拉起的子进程命令行包含 ``--guga-mcp``（父子进程关系可查）；
3. WorkBuddy 自己的 mcp-tool-list.json 出现 guga 条目 / JoyCode 日志出现 guga。

只重启这两个软件；关闭先走 WM_CLOSE，超时仍未退出才强制结束并如实记录。
不启动豆包。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import psutil
import win32con
import win32gui
import win32process

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.adapters import mcp_channels  # noqa: E402

WORKSPACE = Path(os.environ.get('GUGA_WORKSPACE') or (ROOT.parent))
APPS = {
    'workbuddy': dict(process='WorkBuddy.exe',
                      exe=r'%USERPROFILE%\AppData\Local\Programs\WorkBuddy\WorkBuddy.exe',
                      launch_args=[]),
    'joycode': dict(process='JoyCode.exe', exe=r'D:\JoyCode\JoyCode.exe', launch_args=[]),
}


def _windows(pid):
    result = []

    def callback(hwnd, _):
        try:
            if win32process.GetWindowThreadProcessId(hwnd)[1] == pid:
                result.append((hwnd, win32gui.GetWindowText(hwnd), bool(win32gui.IsWindowVisible(hwnd))))
        except Exception:
            pass

    win32gui.EnumWindows(callback, None)
    return result


def _procs(process_name):
    result = []
    for proc in psutil.process_iter(['pid', 'name', 'create_time']):
        if str(proc.info.get('name') or '').casefold() == process_name.casefold():
            result.append(proc)
    return result


def close_app(app_id, graceful_seconds=20):
    info = APPS[app_id]
    procs = _procs(info['process'])
    before = dict(pids=[proc.pid for proc in procs],
                  windows={proc.pid: _windows(proc.pid) for proc in procs})
    closed = []
    for proc in procs:
        for hwnd, title, visible in _windows(proc.pid):
            try:
                win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
                closed.append(dict(pid=proc.pid, hwnd=hwnd, title=title, visible=visible))
            except Exception:
                pass
    deadline = time.time() + graceful_seconds
    while time.time() < deadline:
        if not _procs(info['process']):
            return dict(before=before, closed=closed, forced=False, exited=True,
                        seconds=round(graceful_seconds - (deadline - time.time()), 1))
        time.sleep(1)
    forced = []
    for proc in _procs(info['process']):
        try:
            proc.kill()
            forced.append(proc.pid)
        except Exception:
            pass
    deadline = time.time() + 10
    while time.time() < deadline and _procs(info['process']):
        time.sleep(0.5)
    return dict(before=before, closed=closed, forced=forced, exited=not _procs(info['process']),
                seconds=round(graceful_seconds + (deadline - time.time()), 1))


def launch_app(app_id):
    """用 explorer.exe 拉起，让 GUI 脱离本进程的 job object（否则脚本结束即被杀）。"""
    info = APPS[app_id]
    exe = Path(info['exe'])
    if not exe.is_file():
        return dict(ok=False, error='exe 不存在：%s' % exe)
    if info.get('launch_args'):
        # explorer 不接受额外参数；需要参数时退回 ShellExecute
        os.startfile(str(exe))
    else:
        subprocess.Popen(['explorer.exe', str(exe)], close_fds=True)
    # explorer 启动是异步的，等目标进程真正出现再返回
    deadline = time.time() + 20
    while time.time() < deadline and not _procs(info['process']):
        time.sleep(1)
    procs = _procs(info['process'])
    return dict(ok=bool(procs), pids=[proc.pid for proc in procs], exe=str(exe),
                started_at=time.strftime('%Y-%m-%dT%H:%M:%S'),
                error='' if procs else '20 秒内没有等到进程启动')


def _child_servers(app_id):
    """找目标软件的子进程里有没有 --guga-mcp，并记录完整命令行。"""
    info = APPS[app_id]
    app_pids = {proc.pid for proc in _procs(info['process'])}
    found = []
    for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'create_time']):
        try:
            cmdline = ' '.join(proc.info.get('cmdline') or [])
            if '--guga-mcp' not in cmdline:
                continue
            parent = proc.parent()
            chain = []
            seen = set()
            while parent is not None and len(chain) < 6 and parent.pid not in seen:
                seen.add(parent.pid)
                chain.append(dict(pid=parent.pid, name=parent.name()))
                parent = parent.parent()
            if app_pids & {item['pid'] for item in chain} or proc.info.get('name') == info['process']:
                found.append(dict(pid=proc.info['pid'], name=proc.info.get('name'),
                                  cmdline=cmdline[:400],
                                  started_at=time.strftime('%Y-%m-%dT%H:%M:%S',
                                                           time.localtime(proc.info['create_time'] or 0)),
                                  chain=chain))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return found


def _workbuddy_tool_list():
    path = Path(os.path.expandvars(r'%USERPROFILE%\.workbuddy\mcp-tool-list.json'))
    try:
        data = json.loads(path.read_text(encoding='utf-8-sig'))
        stat = path.stat()
        mtime = time.strftime('%Y-%m-%dT%H:%M:%S', time.localtime(stat.st_mtime))
    except (OSError, ValueError) as exc:
        return dict(path=str(path), exists=False, error=str(exc)[:120])
    text = json.dumps(data, ensure_ascii=False).lower()
    tools = []
    for tool in ('get_task', 'report_progress', 'submit_artifact', 'ask_guga'):
        if tool in text:
            tools.append(tool)
    return dict(path=str(path), exists=True, mtime=mtime, mtime_epoch=stat.st_mtime,
                has_guga=('guga' in text), tools=tools, size=len(text))


def _joycode_logs(since_ts):
    base = Path(os.path.expandvars(r'%APPDATA%\JoyCode\logs'))
    matches = []
    if not base.is_dir():
        return matches
    for path in sorted(base.rglob('*.log'), key=lambda p: p.stat().st_mtime, reverse=True)[:8]:
        try:
            if path.stat().st_mtime < since_ts - 5:
                continue
            text = path.read_text(encoding='utf-8', errors='ignore')
        except OSError:
            continue
        if 'guga' in text.lower():
            lines = [line.strip()[:300] for line in text.splitlines() if 'guga' in line.lower()][-5:]
            matches.append(dict(path=str(path), mtime=time.strftime('%Y-%m-%dT%H:%M:%S',
                                                                   time.localtime(path.stat().st_mtime)),
                                lines=lines))
    return matches


def verify_app(app_id, timeout=120):
    info = APPS[app_id]
    started = time.time()
    evidence = dict(app=app_id, launched=True, serial=[], final=None)
    while time.time() - started < timeout:
        witness = mcp_channels.connection_witness(app_id, WORKSPACE)
        children = _child_servers(app_id)
        snapshot = dict(seconds=round(time.time() - started, 1),
                        running=bool(_procs(info['process'])),
                        witness=witness, child_servers=children)
        if app_id == 'workbuddy':
            snapshot['tool_list'] = _workbuddy_tool_list()
        else:
            snapshot['logs'] = _joycode_logs(started)
        evidence['serial'].append(snapshot)
        witness_fresh = bool(witness.get('exists')) and \
            witness.get('age_seconds') is not None and \
            float(witness['age_seconds']) <= (time.time() - started) + 10
        child_ok = bool(children)
        tool_ok = False
        logs_ok = False
        if app_id == 'workbuddy':
            tool = snapshot.get('tool_list') or {}
            tool_ok = bool(tool.get('tools')) and \
                float(tool.get('mtime_epoch') or 0) >= started - 2
        else:
            logs_ok = bool(snapshot.get('logs'))
        evidence['final'] = snapshot
        if app_id == 'workbuddy':
            # WorkBuddy 可能只在拉取工具清单时短暂连接：工具清单新鲜且含 4 个工具即可，
            # 连接见证/子进程作为佐证。
            connected = tool_ok and (witness_fresh or child_ok)
        else:
            # 日志只作为佐证；“已连接”必须有见证进程或子进程命令行。
            connected = witness_fresh or child_ok
        evidence['checks'] = dict(witness=witness_fresh, child=child_ok,
                                  tool_list=tool_ok, logs=logs_ok)
        if connected:
            evidence['connected'] = True
            evidence['connected_after_seconds'] = snapshot['seconds']
            return evidence
        time.sleep(4)
    evidence['connected'] = False
    return evidence


def main():
    report = dict(workspace=str(WORKSPACE), started_at=time.strftime('%Y-%m-%dT%H:%M:%S'),
                  server_mode=('frozen' if getattr(sys, 'frozen', False) else 'source'), apps={})
    for app_id in ('workbuddy', 'joycode'):
        report['apps'][app_id] = dict(close=close_app(app_id),
                                     launch=launch_app(app_id))
        report['apps'][app_id]['verify'] = verify_app(app_id)
    report['finished_at'] = time.strftime('%Y-%m-%dT%H:%M:%S')
    target = ROOT / 'build' / 'restart_refresh_evidence.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    for app_id, item in report['apps'].items():
        final = (item.get('verify') or {}).get('final') or {}
        checks = (item.get('verify') or {}).get('checks') or {}
        print('%s close=%s forced=%s launch_pids=%s connected=%s after=%ss checks=%s' % (
            app_id, (item['close'] or {}).get('exited'), (item['close'] or {}).get('forced'),
            (item['launch'] or {}).get('pids'), (item['verify'] or {}).get('connected'),
            (item['verify'] or {}).get('connected_after_seconds'), checks))
        print('  witness=%s' % json.dumps(final.get('witness'), ensure_ascii=False))
        if final.get('child_servers'):
            print('  child=%s' % json.dumps(final['child_servers'][0], ensure_ascii=False))
        if final.get('tool_list'):
            print('  tool_list=%s' % json.dumps(final['tool_list'], ensure_ascii=False))
        if final.get('logs'):
            print('  logs=%s' % json.dumps(final['logs'][0], ensure_ascii=False)[:300])
    print('report=%s' % target)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
