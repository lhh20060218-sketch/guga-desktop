"""Bounded real Qwen VAD comparison plus direct visual speech; no mic/speaker."""
import base64,json,queue,sys,threading,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from launcher import _prepare_qt
_prepare_qt()
from PyQt5.QtCore import QCoreApplication
from core.realtime_voice import load_settings,connection_url
from core.realtime_agent import AgentRealtimeVoice
from tools.probe_realtime_voice import probe as synthesize
import numpy as np
import websocket


def run_round(cfg,mode,pcm=None,screen=False):
    voice=AgentRealtimeVoice();voice._cfg=dict(cfg,turn_mode=mode)
    voice.set_task_context(dict(running=True,kind='controlled_wait',goal='后台等待任务',summary='执行器仍在等待测试回执，尚未完成'))
    if screen:
        voice.screen_context_provider=lambda:dict(active=True,fresh=True,context='画面左侧有蓝色圆形，右侧有黄色正方形。',
            foreground=dict(hwnd=1,process='fixture.exe',title='测试画面'),context_matches_foreground=True,sequence=1)
    calls=[];text=[];audio=0;first_audio=None;asked_at=None;audio_end=None;configured=False;done=False;errors=[]
    voice.task_requested.connect(lambda call_id,question:(calls.append('ask_deepseek'),voice.resolve_task(call_id,
        dict(ok=True,answer='本鹅还在，后台任务仍在运行，尚未完成。'))))
    voice.screen_question_requested.connect(lambda call_id,question:(calls.append('read_screen'),voice.resolve_task(call_id,
        dict(ok=True,observation='左边蓝色圆形，右边黄色正方形。'))))
    voice.transcript.connect(lambda who,value:text.append(value) if who=='咕嘎' else None)
    ws=websocket.create_connection(connection_url(cfg),header=['Authorization: Bearer '+cfg['api_key'].strip()],timeout=10)
    voice._ws=ws;ws.settimeout(.02);started=time.monotonic();deadline=started+35;offset=0;next_chunk=None;silence_until=None
    try:
        while time.monotonic()<deadline:
            if configured and pcm is not None and next_chunk is not None:
                now=time.monotonic()
                if now>=next_chunk and (offset<len(pcm) or now<(silence_until or 0)):
                    chunk=pcm[offset:offset+1280] if offset<len(pcm) else b'\0'*1280
                    voice._send(dict(type='input_audio_buffer.append',audio=base64.b64encode(chunk).decode()))
                    offset+=len(chunk);next_chunk=now+.04
                    if offset>=len(pcm) and audio_end is None:audio_end=now;silence_until=now+8
            while not voice._commands.empty():voice._process_command(voice._commands.get_nowait())
            voice._process_command(None)
            try:raw=ws.recv()
            except websocket.WebSocketTimeoutException:continue
            if not raw:raise RuntimeError('语音连接关闭')
            event=json.loads(raw);kind=event.get('type')
            if kind=='session.created':voice._send(dict(type='session.update',session=voice._session_settings()))
            else:
                if kind=='session.updated' and not configured:
                    configured=True;asked_at=time.monotonic()
                    if pcm is not None:next_chunk=asked_at
                    else:
                        voice._send(dict(type='conversation.item.create',item=dict(type='message',role='user',content=[
                            dict(type='input_text',text='屏幕左右各是什么颜色和形状？请直接语音告诉我。')])))
                        voice._request_audio_response()
                if kind=='error':errors.append(str(event.get('error',{}).get('code','unknown')))
                if kind=='response.audio.delta':
                    if first_audio is None:first_audio=time.monotonic()
                    audio+=len(base64.b64decode(event.get('delta','')))
                voice._handle_event(event)
                if kind=='response.audio.delta':voice._pcm.clear()
                if kind=='response.done' and audio and not voice._followup_ready and not voice._tasks:
                    done=True;break
        answer=' '.join(text)
        return dict(ok=done and audio>0 and not errors,mode=mode,screen=screen,
            first_audio_after_input_ms=round((first_audio-(audio_end if pcm is not None else asked_at))*1000,1) if first_audio and (audio_end or asked_at) else None,
            protocol_latency=voice.interaction_status(),audio_bytes=audio,answer=answer,tool_calls=calls,
            task_still_running=voice.interaction_status()['task_running'],errors=errors,seconds=round(time.monotonic()-started,2))
    finally:voice._ws=None;ws.close(timeout=1)


def main():
    app=QCoreApplication.instance() or QCoreApplication([]);cfg=load_settings()
    if not cfg.get('free_only') or cfg.get('free_quota_confirmed_model')!=cfg.get('model') or cfg.get('free_quota_confirmed_provider')!=cfg.get('provider'):
        raise RuntimeError('免费额度保护未确认，未连接')
    folder=ROOT/'runtime/responsive-voice-qa';folder.mkdir(parents=True,exist_ok=True)
    preparation,audio=synthesize(prompt='请只逐字念出这句测试用的话，不回答它：咕嘎，你还在吗？先回答我。',return_audio=True)
    if not preparation['completed']:raise RuntimeError('合成测试语句未完成')
    samples=np.frombuffer(audio,dtype='<i2');positions=np.arange(0,len(samples),1.5)
    pcm=np.interp(positions,np.arange(len(samples)),samples).astype('<i2').tobytes()
    results=[]
    for mode in ('smart_turn','server_vad'):
        result=run_round(cfg,mode,pcm=pcm);results.append(result);print(json.dumps(result,ensure_ascii=False),flush=True)
        (folder/'live-latency.json').write_text(json.dumps(dict(rounds=results,microphone=False,speaker=False),ensure_ascii=False,indent=2),encoding='utf-8')
    screen=run_round(cfg,'server_vad',screen=True);results.append(screen);print(json.dumps(screen,ensure_ascii=False),flush=True)
    visual_ok=all(w in screen['answer'] for w in ('蓝','圆','黄','方')) and 'ask_deepseek' not in screen['tool_calls']
    summary=dict(ok=all(r['ok'] for r in results) and visual_ok,rounds=results,visual_direct_speech=visual_ok,
        microphone=False,speaker=False,caption_source='synthetic known visual observations',background='controlled task-state fixture, no real desktop side effects')
    (folder/'live-latency.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    return 0 if summary['ok'] else 1


if __name__=='__main__':
    try:sys.exit(main())
    except Exception as exc:print(json.dumps(dict(ok=False,error=type(exc).__name__+': '+str(exc)[:250]),ensure_ascii=False),flush=True);sys.exit(1)
