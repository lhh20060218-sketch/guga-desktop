"""Bounded board-read subprocess, intentionally separate from Qt and gameplay execution."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core.bg_memory import read_board, worker_read

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker',action='store_true',help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        snapshot = worker_read() if args.worker else read_board()
        print(json.dumps(dict(ok=True,snapshot=snapshot),ensure_ascii=False))
    except Exception as exc:
        error = str(exc)[:240] if isinstance(exc,RuntimeError) else 'HearthMirror 加载或读取失败；未写入客户端'
        print(json.dumps(dict(ok=False,code=getattr(exc,'code','read_failed'),error=error),ensure_ascii=False))
        sys.exit(2)
