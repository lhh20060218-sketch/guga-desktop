"""Bounded native-PCM soak: one connection, no microphone or real actions.

Requires confirmed free-only credentials. Synthetic speech is generated once,
kept in memory, and repeated through production capture/VAD/FC/playback. Any
unexpected drop fails the sample immediately instead of counting recovery as
continuous service. Progress contains only counters, never transcripts/keys.
"""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import sys
import threading
import time
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from launcher import _prepare_qt
_prepare_qt()
from PyQt5.QtWidgets import QApplication
from core.realtime_agent import AgentRealtimeVoice
from core.realtime_voice import load_settings
from tools.probe_long_voice_acceptance import SilentStream


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live',action='store_true')
    parser.add_argument('--seconds',type=int,default=600,choices=range(120,901))
    parser.add_argument('--label',default='native-voice-soak')
    args=parser.parse_args()
    if not args.live:parser.error('--live required; uses confirmed free quota')
    cfg=load_settings()
    if not (cfg.get('free_only') and cfg.get('free_quota_confirmed_provider')==cfg.get('provider') and
            cfg.get('free_quota_confirmed_model')==cfg.get('model')):raise RuntimeError('Confirmed free-only configuration required')
    import numpy as np
    from tools.probe_realtime_voice import probe
    clips=[]
    for text in ('咕嘎你好，请只回答收到。','帮我打开GitHub官网。','请解释什么是变量，只说一句话。'):
        preparation,audio=probe(prompt='只原样念出这句测试语音，不回答：'+text,return_audio=True)
        if not preparation.get('completed'):raise RuntimeError('Synthetic speech preparation failed')
        source=np.frombuffer(audio,dtype='<i2')
        pcm=np.interp(np.arange(0,len(source),1.5),np.arange(len(source)),source).astype('<i2').tobytes()
        clips.append(pcm)
    # Every 18 seconds, then a 54-second idle interval in the middle.
    duration=args.seconds+10;source=bytearray(32000*duration);planned=0
    for offset in range(3,args.seconds-8,18):
        if args.seconds*.45<=offset<args.seconds*.45+54:continue
        clip=clips[planned%len(clips)];start=offset*32000
        source[start:start+len(clip)]=clip;planned+=1
    SilentStream.source=bytes(source);SilentStream.offset=0;SilentStream.feed.clear()
    app=QApplication.instance() or QApplication([]);voice=AgentRealtimeVoice()
    begun=time.monotonic();counts=Counter();errors=[];connections=0;drops=0;fast=0;delegations=0
    outbound=Counter();threads=set();states=[];connected_at=None;deadline=None
    folder=ROOT/'runtime/voice-soak-qa';folder.mkdir(parents=True,exist_ok=True)
    progress=folder/(args.label+'.progress.json');output=folder/(args.label+'.json')
    def snapshot():
        return dict(pid=os.getpid(),seconds=round(time.monotonic()-begun,2),target_seconds=args.seconds,
            connected_count=connections,drops=drops,connected=voice.connected,events=dict(counts),
            outbound=dict(outbound),writer_threads=sorted(threads),fast_commands=fast,delegations=delegations,
            errors=list(errors),audio_planned=planned,microphone=False,speaker=False,real_desktop_actions=False)
    original=voice._handle_event
    def event(value):
        kind=value.get('type','');counts[kind]+=1
        if kind=='error' or (not kind and value.get('code')):
            error=value.get('error') or value
            errors.append(dict(code=error.get('code'),type=error.get('type'),param=error.get('param')))
        return original(value)
    voice._handle_event=event
    send=voice._send
    def outgoing(value):
        outbound[value.get('type','')]+=1;threads.add(threading.current_thread().name)
        return send(value)
    voice._send=outgoing
    def connection(value):
        nonlocal connections,drops,connected_at,deadline
        if value:
            connections+=1
            if connected_at is None:connected_at=time.monotonic();deadline=connected_at+args.seconds
            SilentStream.feed.set()
        elif not voice._stop.is_set():drops+=1
    voice.connected_changed.connect(connection)
    voice.failed.connect(lambda message:errors.append(dict(failure=message)))
    def fast_command(command):
        nonlocal fast
        fast+=1
        if command.get('action')!='open_url' or command.get('target')!='https://github.com':
            errors.append(dict(unexpected_fast_action=command.get('action')))
        voice.complete_fast_command(command['fast_id'],dict(ok=True,message='受控执行器已受理，没有实际打开网页'))
    voice.fast_command.connect(fast_command)
    def task(ident,request):
        nonlocal delegations
        delegations+=1
        voice.resolve_task(ident,dict(ok=True,answer='变量是保存数值的名字。这是隔离验收回执。'))
    voice.task_requested.connect(task)
    voice.screen_context_provider=lambda:dict(active=True,fresh=True,context='合成测试画面，蓝圆与黄方，测试状态'+str(int((time.monotonic()-begun)//4)),sequence=1)
    voice.set_task_context(dict(running=True,kind='controlled_wait',goal='持续通话隔离验收',summary='后台仍在等待'))
    last_progress=0;last_proactive=0;typed=0
    try:
        with patch('sounddevice.RawInputStream',SilentStream),patch('sounddevice.RawOutputStream',SilentStream):
            voice.start(cfg)
            while (deadline is None and time.monotonic()-begun<25) or (deadline is not None and time.monotonic()<deadline):
                app.processEvents();now=time.monotonic();elapsed=now-(connected_at or begun)
                if errors or drops or (not voice.active and now-begun>1):break
                if voice.connected and elapsed>=last_proactive+31:
                    voice.notify_proactive('soak-'+str(int(elapsed)),'只说“本鹅还在”，不调用工具。');last_proactive=elapsed
                if voice.connected and typed<3 and elapsed>80+typed*150 and not voice._generating and not voice._playing:
                    voice.submit_user_text('请只回答收到。');typed+=1
                if now-last_progress>=10:
                    progress.write_text(json.dumps(snapshot(),ensure_ascii=False,indent=2),encoding='utf-8');last_progress=now
                time.sleep(.01)
            active_seconds=time.monotonic()-(connected_at or time.monotonic())
            result=snapshot();result.update(continuous_seconds=round(active_seconds,2),typed_turns=typed)
            voice.stop()
            if voice._thread:voice._thread.join(5)
            app.processEvents()
    finally:voice.stop()
    result['worker_stopped']=not voice.active
    minimum=max(4,int(planned*.7))
    result['ok']=bool(active_seconds>=args.seconds and connections==1 and not drops and not errors and
        counts['conversation.item.input_audio_transcription.completed']>=minimum and fast>=max(1,planned//6) and
        counts['response.done']>=minimum and len(threads)==1 and result['worker_stopped'])
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    progress.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=True))
    return 0 if result['ok'] else 1


if __name__=='__main__':raise SystemExit(main())
