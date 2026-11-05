"""Honest client identification and stable per-game inference sessions."""
import uuid

_PROCESS_SESSION = uuid.uuid4()


def model_headers(config, state=None):
    state=state or {}
    game_key=str((state.get('game'), state.get('game_start_offset')))
    session=str(uuid.uuid5(_PROCESS_SESSION,game_key))
    return {'Authorization':'Bearer '+config['api_key'],
            'User-Agent':'GugaBattlegroundAgent/1.0', 'x-opencode-session':session}
