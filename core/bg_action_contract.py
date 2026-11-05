"""Compile a legal decision into client option fields; no client invocation.

The five fields match locally inspected GameState.SendOption / Network.SendOption.
An actual in-client runtime bridge is still required to execute this request.
"""
from core.bg_live import candidates, fingerprint


def compile_option(before, current, action, phase):
    if phase != 'recruit':
        raise RuntimeError('只有明确的招募阶段才能编译动作')
    if before.get('fingerprint') != fingerprint(before) or current.get('fingerprint') != fingerprint(current):
        raise RuntimeError('局面内容与标识不一致')
    if before['fingerprint'] != current['fingerprint']:
        raise RuntimeError('决策已过期，不能发送旧动作')
    if not any(action == item for item in candidates(current)):
        raise RuntimeError('动作不在当前合法候选中')
    option_set = current.get('option_set')
    if type(option_set) is not int or option_set < 0:
        raise RuntimeError('缺少客户端选项批次')
    # -1 for no suboption and 0 for no target/position were observed in this
    # client's own SendOption receipts, not inferred from pointer layouts.
    return dict(schema=1, client_build=current.get('client_build'),
                state_id=current['fingerprint'], action_id=action['action_id'],
                fields=dict(option_set_id=option_set, option_index=action['option'],
                            target_entity=action.get('target') or 0, sub_option=-1,
                            board_position=action.get('position') or 0),
                transport_ready=False, executed=False,
                required_transport='verified in-client action bridge')
