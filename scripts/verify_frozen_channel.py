# -*- coding: utf-8 -*-
"""打包版自给自足验证：冻结态片段直接指向 exe 自身，并真实握手。

用法：
    python scripts/verify_frozen_channel.py            # frozen 片段 + 握手
    python scripts/verify_frozen_channel.py --both     # 同时对比 source 片段

输出 build/frozen_channel_evidence.json。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

BUILD = ROOT / 'build'


def _entry_for(app_id: str, workspace: Path) -> dict:
    from core.adapters import mcp_channels
    return mcp_channels.mcp_entry(app_id, workspace=workspace)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--both', action='store_true')
    parser.add_argument('--workspace', default='')
    args = parser.parse_args()
    workspace = Path(args.workspace).expanduser() if args.workspace \
        else Path(__file__).resolve().parents[1]
    BUILD.mkdir(parents=True, exist_ok=True)

    from core.adapters import mcp_channels

    report = dict(contract='guga.frozen_channel/1',
                  started_at=time.strftime('%Y-%m-%dT%H:%M:%S'),
                  exe=str(mcp_channels.frozen_exe()), workspace=str(workspace),
                  frozen_mode_forced=True, apps={}, handshakes={})

    os.environ['GUGA_MCP_FORCE_FROZEN'] = '1'
    report['server_command'] = mcp_channels.server_command(
        'workbuddy', workspace=workspace, force=True)

    for app_id in ('workbuddy', 'doubao', 'joycode'):
        snippets = {}
        gen = mcp_channels.snippet(app_id, workspace=workspace)
        snippets['frozen'] = dict(ok=gen.get('ok'), kind=gen.get('kind'),
                                  entry=gen.get('entry'), text=gen.get('text'),
                                  message=gen.get('message'))
        if args.both:
            previous = os.environ.pop('GUGA_MCP_FORCE_FROZEN', '')
            try:
                src = mcp_channels.snippet(app_id, workspace=workspace)
                snippets['source'] = dict(ok=src.get('ok'), kind=src.get('kind'),
                                          entry=src.get('entry'), text=src.get('text'),
                                          message=src.get('message'))
            finally:
                os.environ['GUGA_MCP_FORCE_FROZEN'] = previous or '1'
        report['apps'][app_id] = snippets

    tmp = Path(tempfile.mkdtemp(prefix='guga_frozen_ws_'))
    try:
        for app_id in ('workbuddy', 'doubao', 'joycode'):
            entry = _entry_for(app_id, workspace)
            if not entry.get('command'):
                report['handshakes'][app_id] = dict(ok=False, status='no_entry',
                                                    message=entry.get('error', ''))
                continue
            result = mcp_channels.verify_connection(
                app_id, entry=entry, workspace=tmp, timeout=35)
            result['command'] = entry.get('command')
            result['args'] = entry.get('args')
            report['handshakes'][app_id] = result
            witness = tmp / '.guga' / 'mcp-connections' / (app_id + '.json')
            if witness.is_file():
                result['witness'] = json.loads(witness.read_text(encoding='utf-8-sig'))
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)

    report['finished_at'] = time.strftime('%Y-%m-%dT%H:%M:%S')
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    (BUILD / 'frozen_channel_evidence.json').write_text(payload, encoding='utf-8')
    print(payload)
    ok = all(item.get('ok') for item in report['handshakes'].values())
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
