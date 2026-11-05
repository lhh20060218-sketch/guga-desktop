"""One bounded Qwen -> grounded Q&A -> Qwen round, with no mic or speakers."""
import base64,json,os,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from launcher import _prepare_qt
_prepare_qt()
from PyQt5.QtWidgets import QApplication
from core.chat_answer import AnswerWorker
from core.companion_dialogue import speech_answer
from core.realtime_agent import AgentRealtimeVoice
from core.realtime_voice import connection_url,load_settings
import websocket


def main():
    app=QApplication.instance() or QApplication([]);cfg=load_settings()
    if not (cfg.get('free_only') and cfg.get('free_quota_confirmed_model')==cfg.get('model') and
            cfg.get('free_quota_confirmed_provider')==cfg.get('provider')):
        raise RuntimeError('free quota guard not confirmed; not connected')
    voice=AgentRealtimeVoice();voice._cfg=cfg
    voice.agent_profile=dict(agent_id='001',display_name='咕嘎',role='桌面伙伴',specialty='对话与电脑任务')
    voice.set_task_context(dict(running=True,kind='controlled_wait',goal='受控后台等待',summary='执行器仍在等待测试回执，任务尚未完成'))
    voice.screen_context_provider=lambda:dict(active=True,fresh=True,context='合成测试画面，无需额外读屏。')
    worker=AnswerWorker();calls=[];answers=[];spoken=[];errors=[];reply_sent=False
    def request(call_id,text):
        calls.append(call_id)
        if len(calls)>1:
            voice.resolve_task(call_id,dict(ok=False,error='single request probe budget reached'));return
        worker.start('live-voice-qa',[],text)
    def completed(result):
        nonlocal reply_sent
        answers.append(result);reply_sent=True
        voice.resolve_task(calls[-1],dict(ok=result.get('ok',False),answer=speech_answer(result.get('text','')),error=result.get('error','')))
    voice.task_requested.connect(request);worker.completed.connect(completed)
    voice.transcript.connect(lambda who,text:spoken.append(text) if who=='咕嘎' else None)
    ws=websocket.create_connection(connection_url(cfg),header=['Authorization: Bearer '+cfg['api_key'].strip()],timeout=10)
    voice._ws=ws;ws.settimeout(.04);started=time.monotonic();configured=False;done=False;audio_after_reply=0
    try:
        while time.monotonic()-started<65:
            app.processEvents()
            while not voice._commands.empty():voice._process_command(voice._commands.get_nowait())
            voice._process_command(None)
            try:raw=ws.recv()
            except websocket.WebSocketTimeoutException:continue
            if not raw:break
            event=json.loads(raw);kind=event.get('type')
            if kind=='session.created':voice._send(dict(type='session.update',session=voice._session_settings()))
            else:
                if kind=='session.updated' and not configured:
                    configured=True
                    voice._send(dict(type='conversation.item.create',item=dict(type='message',role='user',content=[dict(type='input_text',
                        text='Python列表和元组有什么区别？请依据联网资料跟我解释，后台任务继续执行。')])))
                    voice._request_audio_response()
                if kind=='error':errors.append(str(event.get('error',{}).get('code','unknown')))
                if kind=='response.audio.delta' and reply_sent:audio_after_reply+=len(base64.b64decode(event.get('delta','')))
                voice._handle_event(event)
                if kind=='response.audio.delta':voice._pcm.clear()
                if kind=='response.done' and not voice._tasks and not voice._pending_requests:
                    if reply_sent or not calls:done=True;break
        result=dict(ok=bool(done and answers and answers[0].get('ok') and audio_after_reply and not errors),
            knowledge_calls=len(calls),search_state=answers[0].get('search_state') if answers else None,
            source_count=len(answers[0].get('sources',[])) if answers else 0,audio_after_reply=audio_after_reply,
            background_still_running=voice.interaction_status()['task_running'],seconds=round(time.monotonic()-started,2),
            spoken=spoken,errors=errors,microphone=False,speaker=False,desktop_actions=False,
            background='controlled task state; no real desktop side effects')
        folder=ROOT/'runtime/companion-modes-qa';folder.mkdir(parents=True,exist_ok=True)
        (folder/'live-voice-qa.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({k:v for k,v in result.items() if k!='spoken'},ensure_ascii=True))
    finally:
        if worker.active:worker.cancel()
        voice._ws=None;ws.close(timeout=1)


if __name__=='__main__':main()
