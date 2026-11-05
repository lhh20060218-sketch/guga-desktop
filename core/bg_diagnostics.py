"""Bounded bot-core inspection. No desktop UI, input, model request or memory write."""
import time
from pathlib import Path


def input_permissions():
    import win32api
    import win32security
    from core.bg_live_windows import HearthstoneWindow
    window = HearthstoneWindow()
    hwnd = window.find()
    _, pid = window.process.GetWindowThreadProcessId(hwnd)
    handle = win32api.OpenProcess(0x1000, False, pid)
    own = game = None
    try:
        own = win32security.OpenProcessToken(win32api.GetCurrentProcess(), 8)
        game = win32security.OpenProcessToken(handle, 8)
        def integrity(token):
            sid, _ = win32security.GetTokenInformation(token, win32security.TokenIntegrityLevel)
            return sid.GetSubAuthority(sid.GetSubAuthorityCount() - 1)
        own_level, game_level = integrity(own), integrity(game)
        return dict(reader_elevated=bool(win32security.GetTokenInformation(own, win32security.TokenElevation)),
                    game_elevated=bool(win32security.GetTokenInformation(game, win32security.TokenElevation)),
                    reader_integrity=own_level, game_integrity=game_level,
                    input_integrity_compatible=own_level >= game_level,
                    input_verified=False)
    finally:
        for obj in (own, game, handle):
            if obj is not None:
                obj.Close()


def probe(include_memory=False, log_path=None):
    from core.bg_live import LiveReader, observed_phase, candidates
    from core.bg_pipeline import backend_capabilities
    from core.log_reader import find_log_path
    result = dict(observed_at=time.time(), capabilities=backend_capabilities(),
                  input_sent=False, memory_written=False)
    try:
        result['permissions'] = input_permissions()
    except Exception:
        result['permissions'] = dict(available=False, input_verified=False)
    path = log_path or find_log_path(current_session=True)
    if path:
        try:
            reader = LiveReader(path, latest_game=True)
            started = time.monotonic()
            reader.poll()
            result['log'] = dict(available=True, read_ms=round((time.monotonic()-started)*1000, 2),
                                 age_seconds=round(max(0, time.time()-Path(path).stat().st_mtime), 2),
                                 phase=observed_phase(reader.parser), client_build=reader.client_build,
                                 entity_count=len(reader.parser.entities))
            try:
                state = reader.state()
                count = len(candidates(state))
                ready = observed_phase(reader.parser) == 'recruit' and count > 0
                result['log'].update(state_id=state['fingerprint'], snapshot_available=True,
                                     candidate_count=count, decision_ready=ready)
                if not ready:
                    result['log']['reason'] = '招募阶段尚未确认或没有支持的候选，不能仅凭历史候选执行'
            except RuntimeError as exc:
                result['log'].update(decision_ready=False, reason=str(exc))
        except (OSError, RuntimeError) as exc:
            result['log'] = dict(available=False, reason=str(exc))
    else:
        result['log'] = dict(available=False, reason='没有找到 Power.log')
    if include_memory:
        from core.bg_memory import read_board
        started = time.monotonic()
        try:
            result['memory'] = dict(available=True, snapshot=read_board())
        except RuntimeError as exc:
            result['memory'] = dict(available=False, code=getattr(exc, 'code', 'read_failed'), reason=str(exc))
        result['memory']['elapsed_ms'] = round((time.monotonic()-started)*1000, 2)
    else:
        result['memory'] = dict(attempted=False)
    result['automatic_memory_play_ready'] = False
    return result
