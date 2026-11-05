"""Opt-in local stdio MCP host (2025-11-25 tools subset), bounded process lifetime."""
import json
import os
from pathlib import Path
import queue
import subprocess
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
VERSIONS = ('2025-11-25', '2025-06-18', '2025-03-26', '2024-11-05')


class StdioMCP:
    def __init__(self, config, cancel=None):
        command = config.get('command')
        args = config.get('args', [])
        if not isinstance(command, str) or not command or not isinstance(args, list):
            raise ValueError('MCP 需要 command 字符串和 args 数组')
        env = dict(os.environ, **config.get('env', {}))
        self.cancel = cancel or threading.Event()
        self.proc = subprocess.Popen([command] + args, cwd=config.get('cwd') or str(ROOT),
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            encoding='utf-8', text=True, env=env, bufsize=1,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        self.lines = queue.Queue(maxsize=64)
        self.sequence = 0
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        try:
            while self.proc.stdout:
                line = self.proc.stdout.readline(2_000_001)
                if not line:
                    break
                if len(line) > 2_000_000:
                    break
                self.lines.put(line, timeout=2)
        except (OSError, ValueError, queue.Full):
            pass

    def send(self, value):
        self.proc.stdin.write(json.dumps(value, ensure_ascii=False) + '\n')
        self.proc.stdin.flush()

    def request(self, method, params=None):
        self.sequence += 1
        ident = self.sequence
        self.send(dict(jsonrpc='2.0', id=ident, method=method, params=params or {}))
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline and not self.cancel.is_set():
            try:
                line = self.lines.get(timeout=.1)
            except queue.Empty:
                if self.proc.poll() is not None:
                    raise RuntimeError('MCP 软件进程已退出')
                continue
            message = json.loads(line)
            if message.get('method'):
                if 'id' in message:
                    if message['method'] == 'ping':
                        self.send(dict(jsonrpc='2.0', id=message['id'], result={}))
                    else:
                        self.send(dict(jsonrpc='2.0', id=message['id'], error=dict(code=-32601, message='Unsupported client capability')))
                continue
            if message.get('id') == ident:
                if message.get('error'):
                    raise RuntimeError('MCP 请求失败：' + str(message['error'].get('code')))
                return message.get('result', {})
        raise RuntimeError('MCP 操作已取消或超过 20 秒')

    def initialize(self):
        result = self.request('initialize', dict(protocolVersion=VERSIONS[0], capabilities={},
            clientInfo=dict(name='guga-desktop', version='2.0.0')))
        if result.get('protocolVersion') not in VERSIONS:
            raise RuntimeError('暂不支持该 MCP 协议版本，请使用兼容 2025-11-25 的服务器')
        if 'tools' not in result.get('capabilities', {}):
            raise RuntimeError('此 MCP 软件未提供 tools 能力')
        self.send(dict(jsonrpc='2.0', method='notifications/initialized'))

    def close(self):
        try:
            self.proc.stdin.close()
            self.proc.wait(timeout=.5)
        except (OSError, ValueError, subprocess.TimeoutExpired):
            self.proc.terminate()
            try:
                self.proc.wait(timeout=1)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=1)
        if self.proc.stdout:
            self.proc.stdout.close()


class MCPHost:
    def __init__(self, path=None):
        self.path = Path(path or ROOT / 'mcp_servers.json')

    def execute(self, args, cancel=None, approve=None):
        configs = json.loads(self.path.read_text(encoding='utf-8-sig')).get('mcpServers', {}) if self.path.exists() else {}
        action = args.get('action')
        if action == 'list_servers':
            return {'servers': [dict(name=name, enabled=bool(cfg.get('enabled', False)),
                                     allowed_tools=cfg.get('allowed_tools', []), routine_tools=cfg.get('routine_tools', [])) for name, cfg in configs.items()]}
        server = args.get('server', '')
        cfg = configs.get(server)
        if not cfg or not cfg.get('enabled', False):
            raise ValueError('该软件未配置或尚未授权启用')
        if action not in ('list_tools', 'call'):
            raise ValueError('未知生态操作')
        if action == 'call' and args.get('tool') not in cfg.get('allowed_tools', []):
            raise ValueError('工具不在你授予此软件的 allowed_tools 列表中')
        if action == 'call' and (args.get('tool') not in cfg.get('routine_tools', []) or
                                 args.get('tool') in cfg.get('confirmation_tools', [])):
            if not approve or not approve(dict(server=server, tool=args['tool'], arguments=args.get('arguments', {}))):
                raise ValueError('此操作未获得本次确认，未执行')
        if cancel and cancel.is_set():
            raise RuntimeError('操作已取消')
        client = StdioMCP(cfg, cancel)
        try:
            client.initialize()
            if action == 'list_tools':
                result = client.request('tools/list')
                return {'tools': result.get('tools', []), 'nextCursor': result.get('nextCursor'),
                        'allowed_tools': cfg.get('allowed_tools', [])}
            result = client.request('tools/call', dict(name=args['tool'], arguments=args.get('arguments', {})))
            return result
        finally:
            client.close()
