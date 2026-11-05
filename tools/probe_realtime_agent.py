"""Finite real Qwen -> DeepSeek -> Qwen audio probe. No microphone or speaker access."""
import base64
import json
from pathlib import Path
import queue
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from launcher import _prepare_qt
_prepare_qt()
from core.realtime_agent import AgentRealtimeVoice
from core.realtime_voice import load_settings, connection_url
from core.self_agent import SelfAgent
import websocket


def probe():
    cfg = load_settings()
    if (not cfg.get('free_only') or cfg.get('free_quota_confirmed_model') != cfg.get('model') or
            cfg.get('free_quota_confirmed_provider') != cfg.get('provider')):
        raise ValueError('当前平台/模型的免费额度保护未确认，未联网')
    voice = AgentRealtimeVoice()
    voice._cfg = cfg
    brain = SelfAgent(None)
    metrics = dict(voice_model=cfg['model'], reasoning_model=brain.config.get('model'),
                   session_configured=False, delegated=False, deepseek_ok=False,
                   return_audio_bytes=0, completed=False)

    def answer(call_id, question):
        if metrics['delegated']:
            voice.resolve_task(call_id, dict(ok=False, error='本次协议测试只允许一次调用；请播报已有结果'))
            return
        metrics['delegated'] = True
        # Only a generic arithmetic test. No application tools, user history or recordings.
        result = brain._request([
            dict(role='system', content='这是通用连接测试。请只回答计算结果，不调用工具。'),
            dict(role='user', content='2+3 等于多少？')], 'guga-qwen-deepseek-probe', tools=False)
        text = result.get('content', '')
        metrics['deepseek_ok'] = bool(text)
        voice.resolve_task(call_id, dict(ok=bool(text), answer=text))

    voice.task_requested.connect(answer)
    started = time.monotonic()
    deadline = started + 45
    ws = websocket.create_connection(connection_url(cfg),
        header=['Authorization: Bearer ' + cfg['api_key'].strip()], timeout=12)
    voice._ws = ws
    requested = False
    try:
        ws.settimeout(2)
        while time.monotonic() < deadline:
            try:
                raw = ws.recv()
            except websocket.WebSocketTimeoutException:
                continue
            if not raw:
                raise ConnectionError('连接在测试完成前关闭')
            event = json.loads(raw)
            kind = event.get('type')
            if kind == 'session.created':
                session = voice._session_settings()
                session['turn_detection'] = None
                voice._send(dict(type='session.update', session=session))
            elif kind == 'session.updated' and not requested:
                metrics['session_configured'] = True
                voice._send(dict(type='conversation.item.create', item=dict(type='message', role='user',
                    content=[dict(type='input_text', text='这是双模型协议测试。请调用 ask_deepseek 询问 2+3 等于多少，再用一句话播报它返回的答案。只调用一次。')])))
                voice._send(dict(type='response.create'))
                requested = True
            else:
                voice._handle_event(event)
            while not voice._commands.empty():
                voice._process_command(voice._commands.get_nowait())
            voice._process_command(None)
            if kind == 'response.audio.delta' and metrics['deepseek_ok']:
                metrics['return_audio_bytes'] += len(base64.b64decode(event.get('delta', '')))
            if kind == 'response.done' and metrics['deepseek_ok'] and metrics['return_audio_bytes']:
                metrics['completed'] = event.get('response', {}).get('status') == 'completed'
                metrics['elapsed_seconds'] = round(time.monotonic() - started, 2)
                print(json.dumps(metrics, ensure_ascii=False), flush=True)
                return 0 if metrics['completed'] else 1
        raise TimeoutError('本次双模型测试超过时间预算，连接已结束')
    finally:
        voice._ws = None
        ws.close(timeout=1)


if __name__ == '__main__':
    try:
        sys.exit(probe())
    except Exception as exc:
        safe = str(exc) if isinstance(exc, (ValueError, TimeoutError, RuntimeError)) else type(exc).__name__
        print(json.dumps(dict(probe_failed=safe, http_status=getattr(exc, 'status_code', None)), ensure_ascii=False), flush=True)
        sys.exit(1)
