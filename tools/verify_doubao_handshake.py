# -*- coding: utf-8 -*-
"""可复现验证：豆包 HTTP 握手三态（未验证 → 通道就绪 → 已连接）。

用法（源码态，默认）：
    python tools/verify_doubao_handshake.py

用法（冻结包）：
    python tools/verify_doubao_handshake.py --exe "D:\\GUGA\\GUGA-Desktop.exe"

脚本会：
1. 用隔离的 GUGA_HOME/GUGA_WORKSPACE 启动一次 HTTP MCP 端点（不碰用户真实配置）；
2. 断言连接前状态不是“已连接”；
3. 以 `guga-selfcheck` 身份真实握手一次 → 断言变成“通道已就绪”；
4. 以 `豆包` 身份真实握手一次 → 断言变成“已连接”，且证据文件与面板读的是同一份；
5. 退出时结束临时端点，默认删除临时目录（--keep 可保留排查）。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _wait_listening(proc, record: Path, seconds=30) -> dict:
    end = time.time() + seconds
    while time.time() < end:
        if proc.poll() is not None:
            raise RuntimeError('端点进程提前退出 code=%s' % proc.returncode)
        try:
            data = json.loads(record.read_text(encoding='utf-8-sig'))
            if (data.get('state') == 'listening' and data.get('url')
                    and int(data.get('pid') or 0) == proc.pid):
                return data
        except Exception:
            pass
        time.sleep(0.3)
    raise RuntimeError('等待 HTTP 端点监听超时（%s）' % record)


async def _handshake(url: str, name: str) -> dict:
    from mcp import ClientSession, types
    from mcp.client.streamable_http import streamable_http_client

    async with streamable_http_client(url) as (read, write):
        async with ClientSession(read, write,
                                 client_info=types.Implementation(name=name, version='1.0')) as session:
            await session.initialize()
            tools = await session.list_tools()
            return dict(tools=[tool.name for tool in tools.tools])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--exe', default='',
                        help='冻结包 GUGA-Desktop.exe；不填则用源码 tools/comp_entry.py')
    parser.add_argument('--port', type=int, default=18898)
    parser.add_argument('--client-name', default='豆包',
                        help='客户端 clientInfo.name；可用 Coze/MCP Client 复现“名称未识别”场景')
    parser.add_argument('--keep', action='store_true', help='保留临时目录（含端点日志）')
    parser.add_argument('--timeout', type=float, default=20)
    args = parser.parse_args()

    temp = Path(tempfile.mkdtemp(prefix='guga-doubao-verify-'))
    home, workspace = temp / 'home', temp / 'workspace'
    record = home / 'runtime' / 'mcp_http.json'
    env = dict(os.environ)
    env.update(GUGA_HOME=str(home), GUGA_WORKSPACE=str(workspace),
               GUGA_MCP_HTTP_PORT=str(args.port), PYTHONIOENCODING='utf-8')
    for key in ('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY'):
        env.pop(key, None)
    os.environ.update(GUGA_HOME=str(home), GUGA_WORKSPACE=str(workspace))

    if args.exe:
        command = [str(Path(args.exe).expanduser().resolve()), '--guga-mcp-http']
        cwd = str(Path(args.exe).expanduser().resolve().parent)
    else:
        command = [sys.executable, str(ROOT / 'tools' / 'comp_entry.py'), '--guga-mcp-http']
        cwd = str(ROOT)

    log_path = temp / 'endpoint.log'
    log = open(log_path, 'w', encoding='utf-8')
    proc = subprocess.Popen(command, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    problems = []
    try:
        data = _wait_listening(proc, record)
        url = str(data['url'])
        print('[1] endpoint listening: %s' % url)

        from core.adapters import mcp_channels

        before = mcp_channels.channel_status('doubao', workspace=workspace)
        print('[2] before handshake: state=%s connected=%s' % (before['state'], before['connected']))
        if before['connected']:
            problems.append('连接前就显示已连接')

        verified = mcp_channels.verify_connection(
            'doubao', entry=dict(transport='HTTP', url=url),
            workspace=workspace, timeout=args.timeout)
        if not verified.get('ok'):
            problems.append('自检握手失败：%s' % verified.get('message'))
        ready = mcp_channels.channel_status('doubao', workspace=workspace)
        print('[3] selfcheck handshake: ok=%s state=%s' % (verified.get('ok'), ready['state']))
        if ready['state'] != 'endpoint_ready':
            problems.append('自检后状态应为 endpoint_ready，实际 %s' % ready['state'])
        if ready['connected']:
            problems.append('自检被误判成豆包已接入')

        tools = asyncio.run(_handshake(url, args.client_name))
        print('[4] client handshake (name=%s): tools=%s'
              % (args.client_name, ','.join(tools['tools'])))
        after = mcp_channels.channel_status('doubao', workspace=workspace)
        print('[5] after client: state=%s connected=%s' % (after['state'], after['connected']))
        print('    message=%s' % str(after.get('message'))[:220])
        witness = workspace / '.guga' / 'mcp-connections' / 'doubao.json'
        print('    witness=%s exists=%s' % (witness, witness.is_file()))
        if after['state'] != 'connected':
            problems.append('真实客户端握手后状态应为 connected，实际 %s' % after['state'])
        if not witness.is_file():
            problems.append('握手证据文件缺失：%s' % witness)
        else:
            record_data = json.loads(witness.read_text(encoding='utf-8-sig'))
            saved_name = str(record_data.get('client_name') or '')
            if record_data.get('client_unidentified'):
                # 名称不在别名表里是真实场景：只要落盘证据明确标记未识别，状态仍算一致。
                if saved_name != args.client_name:
                    problems.append('未识别客户端的证据名不一致：%r != %r'
                                    % (saved_name, args.client_name))
            elif saved_name != '豆包':
                problems.append('证据里的 client_name 不是“豆包”：%r' % saved_name)
    except Exception as exc:
        problems.append('%s: %s' % (type(exc).__name__, exc))
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()
        log.close()

    if problems:
        print('FAIL')
        for item in problems:
            print(' - %s' % item)
        print('端点日志：%s' % log_path)
    else:
        print('PASS：豆包 HTTP 握手三态与真实证据一致')
    if not args.keep and not problems:
        shutil.rmtree(str(temp), ignore_errors=True)
    elif not args.keep:
        print('临时目录保留（有失败）：%s' % temp)
    return 0 if not problems else 1


if __name__ == '__main__':
    sys.exit(main())
