"""Rendered test-frame source -> real vision -> real Qwen speech, no mic/speaker."""
import base64
import json
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
os.environ.pop('QT_QPA_PLATFORM',None)
from launcher import _prepare_qt
_prepare_qt()
from PyQt5.QtCore import Qt,QBuffer,QByteArray,QIODevice
from PyQt5.QtGui import QColor,QFont,QPainter,QPolygon
from PyQt5.QtCore import QPoint
from PyQt5.QtWidgets import QApplication,QWidget
from core.realtime_agent import AgentRealtimeVoice
from core.realtime_voice import load_settings,connection_url
from core.screen_share import ScreenShareController
from core.screen_visual import answer_frame
import websocket
import io
from PIL import Image


def render_frame(window):
    array=QByteArray();buffer=QBuffer(array);buffer.open(QIODevice.WriteOnly)
    window.grab().save(buffer,'PNG');buffer.close()
    return Image.open(io.BytesIO(bytes(array))).convert('RGB')


class Fixture(QWidget):
    scene=0
    def paintEvent(self,event):
        painter=QPainter(self);painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(),QColor('white'));painter.setPen(QColor('#172334'));painter.setFont(QFont('Microsoft YaHei',38))
        painter.drawText(70,100,'海风读书角' if self.scene==0 else '星河音乐站')
        painter.setPen(Qt.NoPen)
        if self.scene==0:
            painter.setBrush(QColor('#1466e8'));painter.drawEllipse(120,200,240,240)
            painter.setBrush(QColor('#f4cd19'));painter.drawRect(600,200,240,240)
        else:
            painter.setBrush(QColor('#119a47'));painter.drawPolygon(QPolygon([QPoint(240,190),QPoint(100,440),QPoint(380,440)]))
            painter.setBrush(QColor('#e32c32'));painter.drawEllipse(600,200,240,240)
        painter.setPen(QColor('#172334'));painter.setFont(QFont('Microsoft YaHei',23))
        painter.drawText(70,570,'屏幕辅助连接验收 · 仅为合成测试内容')


def main():
    cfg=load_settings()
    if not cfg.get('free_only') or cfg.get('free_quota_confirmed_model')!=cfg.get('model') or cfg.get('free_quota_confirmed_provider')!=cfg.get('provider'):
        raise RuntimeError('当前免费额度保护未确认，未连接')
    app=QApplication.instance() or QApplication([])
    window=Fixture();window.resize(1100,650);window.setWindowTitle('咕嘎屏幕连接验收')
    window.setAttribute(Qt.WA_DontShowOnScreen,True);window.show();app.processEvents()
    rect=[0,0,1100,650];frames=[render_frame(window)]
    foreground=dict(hwnd=int(window.winId()),title=window.windowTitle(),pid=os.getpid(),process='fixture.exe',rect=rect,own_app=False)
    panel=SimpleNamespace(pet=None);share=ScreenShareController(panel)
    voice=AgentRealtimeVoice();voice._cfg=cfg;voice.screen_context_provider=share.assist_context
    voice.context_history=[('饲养员','看得见屏幕吗？'),('咕嘎','本鹅目前还没有看到屏幕画面，可能需要先开启共享。')]
    folder=ROOT/'runtime/screen-voice-qa';folder.mkdir(parents=True,exist_ok=True)
    transcripts=[];audio_bytes=[0];reading=[False]
    voice.transcript.connect(lambda who,text:transcripts.append(text) if who=='咕嘎' else None)
    def read_screen(call_id,question):
        if reading[0]:voice.resolve_task(call_id,dict(ok=False,answer='已有读屏请求'));return
        reading[0]=True
        frame=share.snapshot();result=answer_frame(frame['_image_url'],question,allow_primary=False)
        voice.resolve_task(call_id,dict(ok=result.get('ok'),answer=result.get('text') or result.get('error')))
    voice.screen_question_requested.connect(read_screen)
    ws=None;results=[];started=time.monotonic();deadline=started+95
    try:
        with patch('core.screen_share.DesktopAccess',return_value=SimpleNamespace(enabled=True)), \
             patch('core.screen_share._foreground_snapshot',return_value=foreground), \
             patch('core.screen_share.ImageGrab.grab',side_effect=lambda **kwargs:frames[0].copy()):
            share.start(2,'synthetic-long-call-acceptance')
            limit=time.monotonic()+18
            while time.monotonic()<limit and not share.context().get('fresh'):
                app.processEvents();time.sleep(.03)
            state=share.context()
            if not state.get('fresh'):
                print(json.dumps(dict(stage='freshness_failure',active=state['active'],context=state['context'],sequence=state['sequence'],
                    context_age=state['context_age_seconds'],frame_age=state['frame_age_seconds'],
                    analyses=state['analysis_count'],analysis_active=state['analysis_active'],pending=state['analysis_pending'],
                    frame_at=share._context_frame_at,last_change=share._last_change,foreground=foreground),ensure_ascii=False),flush=True)
                raise RuntimeError('首场景没有得到有效视觉资料')
            print(json.dumps(dict(stage='vision_ready',context=state['context'],sequence=state['sequence']),ensure_ascii=False),flush=True)
            ws=websocket.create_connection(connection_url(cfg),header=['Authorization: Bearer '+cfg['api_key'].strip()],timeout=10)
            voice._ws=ws;ws.settimeout(.3);configured=False;response_done=False;errors=[]
            def receive():
                nonlocal configured,response_done
                app.processEvents()
                while not voice._commands.empty():voice._process_command(voice._commands.get_nowait())
                voice._process_command(None)
                try:raw=ws.recv()
                except websocket.WebSocketTimeoutException:return
                if not raw:raise RuntimeError('语音连接提前关闭')
                event=json.loads(raw);kind=event.get('type')
                if kind=='session.created':
                    settings=voice._session_settings();settings['turn_detection']=None
                    voice._send(dict(type='session.update',session=settings))
                else:
                    if kind=='session.updated':configured=True
                    if kind=='error':errors.append(str(event.get('error',{}))[:350])
                    if kind=='response.audio.delta':audio_bytes[0]+=len(base64.b64decode(event.get('delta','')))
                    voice._handle_event(event)
                    # This probe has no audio output device to drain the PCM ring.
                    if kind=='response.audio.delta':voice._pcm.clear()
                    if kind=='response.done' and not voice._tasks and not voice._followup_ready:response_done=True
            while not configured and time.monotonic()<deadline:receive()
            if not configured:raise RuntimeError('语音会话未确认配置')
            for scene in (0,1):
                if scene:
                    previous=share.status()['analysis_count'];window.scene=1;window.repaint();app.processEvents();frames[0]=render_frame(window);limit=min(deadline,time.monotonic()+20)
                    while time.monotonic()<limit and not (share.context().get('fresh') and share.status()['analysis_count']>previous):
                        receive();time.sleep(.02)
                    state=share.context()
                    if not state.get('fresh') or share.status()['analysis_count']<=previous:raise RuntimeError('第二场景视觉未刷新')
                voice._screen_checked_at=0;voice._sync_screen_context(force=True)
                before=len(transcripts);before_audio=audio_bytes[0];response_done=False
                voice._send(dict(type='conversation.item.create',item=dict(type='message',role='user',content=[dict(type='input_text',
                    text='现在能看见我的屏幕吗？请直接说出画面上的中文标题，以及两个图形各自的颜色和形状。' if scene==0 else
                    '我已经换了画面。现在屏幕的中文标题和两个图形分别是什么？直接回答实际画面。')])))
                voice._generating=True;voice._send(dict(type='response.create'))
                limit=min(deadline,time.monotonic()+24)
                while time.monotonic()<limit and not response_done:receive()
                text=' '.join(transcripts[before:]);required=('海风读书角','蓝','圆','黄','方') if scene==0 else ('星河音乐站','绿','三角','红','圆')
                ok=all(word in text for word in required) and audio_bytes[0]>before_audio
                results.append(dict(scene=scene,ok=ok,answer=text,audio_bytes=audio_bytes[0]-before_audio,
                    vision_context=share.context().get('context'),bridge=voice.screen_bridge_status()))
                print(json.dumps(dict(stage='scene_result',**results[-1]),ensure_ascii=False),flush=True)
                if not response_done:raise RuntimeError('场景回复超时')
            result=dict(ok=all(r['ok'] for r in results) and not errors,scenes=results,errors=errors,
                seconds=round(time.monotonic()-started,2),microphone=False,speaker=False,synthetic_window_only=True,
                capture_source='rendered_Qt_fixture_frames_not_live_desktop',real_vision=True,real_qwen_audio=True)
            (folder/'real-bridge.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps(dict(ok=result['ok'],seconds=result['seconds'],scenes=len(results),errors=errors),ensure_ascii=False),flush=True)
            return 0 if result['ok'] else 1
    finally:
        share.stop();voice._ws=None
        if ws:ws.close(timeout=1)
        window.close();app.processEvents()


if __name__=='__main__':
    try:sys.exit(main())
    except Exception as exc:
        print(json.dumps(dict(ok=False,error=type(exc).__name__+': '+str(exc)[:600]),ensure_ascii=False),flush=True);sys.exit(1)
