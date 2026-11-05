"""Finite actual Qwen acknowledgement/progress/final audio test; no mic/speaker."""
import base64,json,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from launcher import _prepare_qt
_prepare_qt()
from core.realtime_agent import AgentRealtimeVoice
from core.realtime_voice import load_settings,connection_url
import websocket

cfg=load_settings()
if not cfg.get('free_only') or cfg.get('free_quota_confirmed_model')!=cfg.get('model') or cfg.get('free_quota_confirmed_provider')!=cfg.get('provider'):
    raise SystemExit('当前免费额度保护未确认，未联网')
voice=AgentRealtimeVoice();voice._cfg=cfg
state={'stage':'waiting','started':time.monotonic(),'audio':{},'transcripts':{},'delegated':False}
def accepted(call_id,request):
    if state['delegated']:
        voice.resolve_task(call_id,dict(ok=False,error='测试仅允许一次受理，后续只播报反馈'));return
    state['delegated']=True;state['stage']='ack'
    voice.resolve_task(call_id,dict(ok=True,execution_pending=True,answer='收到，你要验证任务反馈。我现在开始。'))
voice.task_requested.connect(accepted)
ws=None
try:
    ws=websocket.create_connection(connection_url(cfg),header=['Authorization: Bearer '+cfg['api_key']],timeout=10)
    voice._ws=ws;ws.settimeout(.3)
    requested=False;deadline=time.monotonic()+40
    while time.monotonic()<deadline:
        try:raw=ws.recv()
        except websocket.WebSocketTimeoutException:raw=None
        if raw:
            event=json.loads(raw);kind=event.get('type')
            if kind=='session.created':
                session=voice._session_settings();session['turn_detection']=None
                voice._send(dict(type='session.update',session=session))
            elif kind=='session.updated' and not requested:
                requested=True
                voice._send(dict(type='conversation.item.create',item=dict(type='message',role='user',content=[dict(type='input_text',text='这是任务反馈协议测试。请先调用ask_deepseek，request填写“验证任务反馈”。收到execution_pending后只说简短确认，等待后续播报，不重复调用工具。')])) )
                voice._send(dict(type='response.create'))
            else:voice._handle_event(event)
            stage=state['stage']
            if kind=='response.audio.delta':state['audio'][stage]=state['audio'].get(stage,0)+len(base64.b64decode(event.get('delta','')))
            if kind=='response.audio_transcript.done':state['transcripts'][stage]=event.get('transcript','')[:120]
            if kind=='response.done' and state['audio'].get(stage,0):
                if stage=='ack':
                    state['ack_seconds']=round(time.monotonic()-state['started'],2);state['stage']='progress'
                    voice._last_activity=time.monotonic()-2
                    voice.notify_battleground('feedback-progress','我已找到编辑器，正在核对目标文件。')
                elif stage=='progress':
                    state['stage']='final';voice._last_activity=time.monotonic()-2
                    voice.notify_battleground('feedback-final','任务反馈流程验证完成。')
                elif stage=='final':
                    print(json.dumps(dict(ok=True,ack_seconds=state.get('ack_seconds'),audio_bytes=state['audio'],transcripts=state['transcripts'],elapsed=round(time.monotonic()-state['started'],2)),ensure_ascii=False));break
        while not voice._commands.empty():voice._process_command(voice._commands.get_nowait())
        voice._process_command(None)
    else:raise TimeoutError('40秒验证预算到达')
finally:
    voice._ws=None
    if ws:ws.close(timeout=1)
