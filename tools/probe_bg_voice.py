"""One finite real proactive narration probe, no microphone/speaker/game operations."""
import base64
import json
from pathlib import Path
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from launcher import _prepare_qt
_prepare_qt()
from core.realtime_agent import AgentRealtimeVoice
from core.realtime_voice import load_settings, connection_url
import websocket


def main():
    cfg=load_settings()
    if (not cfg.get('free_only') or cfg.get('free_quota_confirmed_model')!=cfg.get('model')
            or cfg.get('free_quota_confirmed_provider')!=cfg.get('provider')):
        raise ValueError('免费额度用尽即停保护尚未确认，未联网')
    voice=AgentRealtimeVoice();voice._cfg=cfg
    metrics=dict(audio_bytes=0,completed=False,task_requested=False,total_tokens=None)
    voice.task_requested.connect(lambda *args:metrics.update(task_requested=True))
    started=time.monotonic();deadline=started+30
    ws=websocket.create_connection(connection_url(cfg),
        header=['Authorization: Bearer '+cfg['api_key'].strip()],timeout=8)
    voice._ws=ws
    try:
        ws.settimeout(2)
        queued=False
        while time.monotonic()<deadline:
            try:raw=ws.recv()
            except websocket.WebSocketTimeoutException:continue
            if not raw:raise RuntimeError('播报测试连接提前结束')
            event=json.loads(raw);kind=event.get('type')
            if kind=='session.created':
                settings=voice._session_settings();settings['turn_detection']=None
                voice._send(dict(type='session.update',session=settings))
            elif kind=='session.updated' and not queued:
                voice._last_activity=time.monotonic()-5
                voice.notify_battleground('protocol-probe','这是战棋主动语音连接测试。当前没有执行游戏操作。')
                queued=True
            else:voice._handle_event(event)
            while not voice._commands.empty():voice._process_command(voice._commands.get_nowait())
            voice._process_command(None)
            if kind=='response.audio.delta':
                metrics['audio_bytes']+=len(base64.b64decode(event.get('delta','')))
            if kind=='response.done' and queued:
                usage=event.get('response',{}).get('usage') or {}
                metrics['total_tokens']=usage.get('total_tokens')
                metrics['completed']=event.get('response',{}).get('status')=='completed' and metrics['audio_bytes']>0
                metrics['elapsed_seconds']=round(time.monotonic()-started,2)
                print(json.dumps(metrics,ensure_ascii=False))
                return 0 if metrics['completed'] and not metrics['task_requested'] else 2
        raise TimeoutError('主动播报协议测试超过30秒预算')
    finally:
        voice._ws=None
        ws.close(timeout=1)


if __name__=='__main__':
    try:sys.exit(main())
    except Exception as exc:
        safe=str(exc) if isinstance(exc,(ValueError,RuntimeError,TimeoutError)) else type(exc).__name__
        print(json.dumps(dict(ok=False,error=safe),ensure_ascii=False));sys.exit(2)
