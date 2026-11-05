"""Explicit policy for automatic disconnects inside a full-auto session.

The passive plugin/shadow-observer never calls this policy. It only skips the
combat animation in an automation session already started by the user.
"""

MIN_VISIBLE_MINIONS = 7


def auto_netcut_decision(board, *, full_auto, remaining, cooldown_remaining=0,
                         already_cut=False):
    """Decide whether the current combat is worth skipping in full-auto mode.

    This is a resource/animation policy, not a win-rate estimate. Small combats
    are left alone; sizeable combat boards qualify for one bounded cut.
    """
    try:
        mine=len(board.get('mine') or [])
        theirs=len(board.get('theirs') or [])
    except (AttributeError,TypeError):
        return False,'局面无效'
    if not full_auto:
        return False,'插件/手动模式禁止自动拔线'
    if not board.get('active'):
        return False,'没有进行中的对局'
    if not theirs:
        return False,'当前不在可确认的战斗阶段'
    if already_cut:
        return False,'本场战斗已经拔过线'
    if remaining <= 0:
        return False,'本局已达到 9 次硬上限'
    if cooldown_remaining > 0:
        return False,'仍在重连冷却期'
    if mine + theirs < MIN_VISIBLE_MINIONS:
        return False,f'可见随从仅 {mine + theirs} 个，短战斗不值得断线'
    return True,f'全自动会话：可见随从 {mine + theirs} 个，判定为较长战斗，执行一次拔线'
