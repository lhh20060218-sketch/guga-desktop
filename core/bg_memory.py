"""Optional, process-isolated HearthMirror board reader. No memory writes or invocation."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

MIRROR_DIR = Path.home()/'Desktop/游戏/HDT'
MIRROR_SHA256 = '3cc1180b89582127fe737d0a8c6e03f13d460437a43511a6fc382bc958f31d1d'


class MemoryReadError(RuntimeError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def checked_mirror():
    dll = MIRROR_DIR/'HearthMirror.dll'
    if not dll.is_file() or hashlib.sha256(dll.read_bytes()).hexdigest() != MIRROR_SHA256:
        raise RuntimeError('本机 HearthMirror 不存在或版本已变化；需重新核对读取接口')
    return dll


def normalize_cards(cards):
    if cards is None:
        return None
    result = []
    for card in list(cards)[:32]:
        result.append(dict(card_id=str(card.CardId) if card.CardId else None,
                           entity_id=int(card.EntityId) if card.EntityId is not None else None,
                           position=int(card.ZonePosition)))
    return result


def collect_board(client, denied=lambda: False):
    # GetBoardState's parameter is includeFriendly, not a freshness flag.
    board = client.GetBoardState(True)
    if denied():
        raise MemoryReadError('access_denied', 'HearthMirror 明确返回 AccessDenied；读取进程没有访问游戏的权限')
    if board is None:
        raise MemoryReadError('board_unavailable', 'HearthMirror 未返回棋盘；可能未进入棋盘或版本不兼容，尚不能区分')
    return dict(source='HearthMirror.GetBoardState', observed_at=time.time(),
                mirror_sha256=MIRROR_SHA256, include_friendly=True,
                friendly=normalize_cards(board.Friendly), opposing=normalize_cards(board.Opposing),
                limitations=['Card identity/position only; stats and effects still come from logs',
                             'Read-only snapshot; no memory execution backend'])


def worker_read():
    dll = checked_mirror()
    sys.path.insert(0,str(dll.parent))
    import clr
    clr.AddReference(str(dll))
    from HearthMirror import Reflection
    from System import Action
    status = {'denied': False}
    def on_denied():
        status['denied'] = True
    handler = Action(on_denied)
    Reflection.AccessDenied += handler
    try:
        # Strict allowlist: omit player names, accounts, decks and unrelated memory.
        return collect_board(Reflection.Client, lambda: status['denied'])
    finally:
        Reflection.AccessDenied -= handler


def read_board():
    checked_mirror()
    # A read and an input have different access requirements. Let HearthMirror
    # report actual read access rather than rejecting on input elevation alone.
    tool = Path(__file__).resolve().parents[1]/'tools/bg_memory.py'
    try:
        result = subprocess.run([sys.executable,'-X','utf8',str(tool),'--worker'],
                                capture_output=True, timeout=12, cwd=str(MIRROR_DIR))
    except subprocess.TimeoutExpired:
        raise RuntimeError('内存读取达到 12 秒预算，读取进程已终止') from None
    try:
        reply = json.loads(result.stdout.decode('utf-8-sig'))
    except (ValueError,UnicodeError):
        raise RuntimeError('内存读取没有返回有效快照；未发送游戏操作') from None
    if not reply.get('ok'):
        raise MemoryReadError(reply.get('code','read_failed'), reply.get('error','内存读取失败'))
    return reply['snapshot']
