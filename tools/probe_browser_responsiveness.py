"""Finite native UIA benchmark against an isolated local Edge fixture.

UIA performs actions; Playwright independently verifies the local page. No
personal profile, microphone, remote page, or real form submission is used.
"""
import argparse
import functools
import http.server
import json
import os
from pathlib import Path
import statistics
import sys
import tempfile
import threading
import time

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def perception_round(hwnd):
    from core.local_perception import LocalPerception
    from core.screen_share import _foreground_snapshot
    from core.computer_control import ComputerControl
    from types import SimpleNamespace
    reader=LocalPerception();samples=[]
    try:
        ComputerControl(SimpleNamespace(enabled=True)).execute(dict(action='focus',hwnd=hwnd))
        for _ in range(3):
            foreground=_foreground_snapshot()
            if not foreground or foreground.get('hwnd')!=hwnd:
                samples.append(dict(fresh=False,error='foreground_changed',process=(foreground or {}).get('process')))
                break
            before=time.monotonic();reader.request(foreground)
            while reader.busy and time.monotonic()-before<5.6:time.sleep(.01)
            state=reader.context(foreground)
            names={item.get('name') for item in state.get('elements',[])}
            samples.append(dict(fresh=state['fresh'],provider_ms=state.get('elapsed_ms'),
                wall_ms=round((time.monotonic()-before)*1000,2),controls=len(names),
                input_seen='验收输入' in names,button_seen='执行测试' in names,error=state.get('error')))
            if not state['fresh']:break
            if len(samples)<3:time.sleep(1.02)
    finally:reader.close()
    return dict(ok=len(samples)==3 and all(s['fresh'] and s['input_seen'] and s['button_seen'] for s in samples),
        samples=samples,source='windows_uia',remote_model_calls=0,provider_closed=True)


def voice_round(page,interaction,hwnd):
    from launcher import _prepare_qt
    _prepare_qt()
    from PyQt5.QtWidgets import QApplication
    from core.realtime_agent import AgentRealtimeVoice
    from core.realtime_voice import load_settings
    from tools.probe_realtime_voice import probe as synthesize
    from tools.probe_long_voice_acceptance import SilentStream
    from unittest.mock import patch
    import numpy as np
    app=QApplication.instance() or QApplication([]);cfg=load_settings()
    clips=[]
    for text in ('输入界面响应速度测试','点击执行测试'):
        preparation,audio=synthesize(prompt='请只原样念出这句测试语音，不回答：'+text,return_audio=True)
        if not preparation['completed']:raise RuntimeError('Synthetic voice unavailable')
        samples=np.frombuffer(audio,dtype='<i2')
        clips.append(np.interp(np.arange(0,len(samples),1.5),np.arange(len(samples)),samples).astype('<i2').tobytes()+bytes(32000*4))
    SilentStream.source=b''.join(clips);SilentStream.offset=0;SilentStream.feed.clear()
    voice=AgentRealtimeVoice();measurements=[];delegations=[];errors=[];drops=[]
    from core.local_perception import LocalPerception
    from core.screen_share import _foreground_snapshot
    local=LocalPerception()
    def local_context():
        foreground=_foreground_snapshot();state=local.context(foreground)
        return dict(state,active=True,foreground=foreground,context_matches_foreground=state.get('window_matches',False))
    voice.screen_context_provider=local_context
    def fast(command):
        if command.get('action')!='browser_step':errors.append('unexpected command');return
        def run():
            # Never let a fixture probe act on another browser if foreground
            # focus changes during cloud synthesis or the spoken turn.
            result=interaction.execute(command,hwnd=hwnd)
            measurements.append(dict(action=command['browser_action'],ok=result['ok'],
                asr_after_speech_ms=command.get('asr_after_speech_ms'),
                transcript_to_result_ms=round((time.monotonic()-command['recognized_at'])*1000,2),error=result.get('error')))
            voice.complete_fast_command(command['fast_id'],result)
        threading.Thread(target=run,daemon=True).start()
    voice.fast_command.connect(fast)
    voice.task_requested.connect(lambda ident,text:(delegations.append(ident),voice.resolve_task(ident,dict(ok=False,error='probe permits only local single steps'))))
    voice.failed.connect(errors.append)
    voice.connected_changed.connect(lambda value:drops.append(True) if not value and not voice._stop.is_set() else None)
    page.bring_to_front()
    from core.computer_control import ComputerControl
    from core.fast_commands import match
    from types import SimpleNamespace
    ComputerControl(SimpleNamespace(enabled=True)).execute(dict(action='focus',hwnd=hwnd))
    page.locator('#qa-input').click()
    try:
        focus=interaction.uia.focused(hwnd)['element']
        cdp_input_focused=focus.get('name')=='验收输入' and focus.get('type')=='Edit'
    except RuntimeError:cdp_input_focused=False
    # Native UIA establishes the focus used by the real spoken "input" step;
    # a CDP page click alone does not prove native keyboard focus on Windows.
    focus_receipt=interaction.execute(match('点击输入框'),hwnd=hwnd)
    if not focus_receipt.get('ok'):raise RuntimeError('Fixture input did not acquire native UIA focus')
    before=page.evaluate('window.clicks || 0')
    started=time.monotonic()
    with patch('sounddevice.RawInputStream',SilentStream),patch('sounddevice.RawOutputStream',SilentStream):
        voice.start(cfg)
        try:
            while time.monotonic()-started<28:
                app.processEvents()
                local.request(_foreground_snapshot())
                if voice.connected and time.monotonic()-started>1:SilentStream.feed.set()
                if len(measurements)>=2 and time.monotonic()-started>17:break
                time.sleep(.005)
        finally:
            connected=voice.connected;voice.stop()
            if voice._thread:voice._thread.join(5)
            app.processEvents()
            local.close()
    actual=page.input_value('#qa-input');clicks=page.evaluate('window.clicks || 0')
    return dict(ok=bool(len(measurements)==2 and all(m['ok'] for m in measurements) and not errors and not delegations
        and not drops and connected and '界面' in actual and clicks==before+1 and not voice.active),
        measurements=measurements,delegations=len(delegations),drops=len(drops),errors=errors,
        input_verified='界面' in actual,click_verified=clicks==before+1,worker_stopped=not voice.active,
        cdp_input_focused=cdp_input_focused,native_focus_verified=True,fixture_window_guard=True,
        local_perception_reads=local.reads,screen_bridge_updates=voice._screen_updates_sent,
        seconds=round(time.monotonic()-started,2),microphone=False,speaker=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--label',default='before')
    parser.add_argument('--commands',action='store_true')
    parser.add_argument('--live-voice',action='store_true',help='explicitly use confirmed free voice quota and synthetic speech')
    parser.add_argument('--browser',choices=('edge','default'),default='edge')
    args=parser.parse_args()
    from playwright.sync_api import sync_playwright
    from core.uia_backend import UIABackend
    from core.window_inventory import list_windows
    from core.computer_control import ComputerControl
    from types import SimpleNamespace
    folder=ROOT/'runtime/browser-response-qa';folder.mkdir(parents=True,exist_ok=True)
    result=dict(label=args.label,snapshot_ms=[],name_action_ms=[],ref_action_ms=[],errors=[],checks=[],microphone=False)
    started=time.monotonic()
    class Handler(http.server.SimpleHTTPRequestHandler):
        def log_message(self,*args):pass
    with tempfile.TemporaryDirectory() as tmp:
        title='Guga UIA Response Fixture'
        html='''<!doctype html><html lang="zh"><meta charset="utf-8"><title>Guga UIA Response Fixture</title>
        <body><h1>咕嘎响应验收，自有页面</h1><label for="qa-input">验收输入</label>
        <input id="qa-input" aria-label="验收输入"><button id="qa-button" onclick="window.clicks=(window.clicks||0)+1;document.querySelector('#status').textContent='已执行 '+window.clicks">执行测试</button>
        <p id="status">待执行</p><div>'''+''.join('<button>占位按钮'+str(n)+'</button>' for n in range(100))+'''</div>
        <div style="height:1800px"></div><button id="deep">底部测试</button></body></html>'''
        Path(tmp,'index.html').write_text(html,encoding='utf-8')
        handler=functools.partial(Handler,directory=tmp)
        server=http.server.ThreadingHTTPServer(('127.0.0.1',0),handler)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        try:
            with sync_playwright() as pw:
                launch=dict(channel='msedge')
                if args.browser=='default':
                    from core.browser_launch import default_executable
                    executable=default_executable()
                    if not executable:raise RuntimeError('Default browser executable unavailable')
                    launch=dict(executable_path=str(executable));result['browser']=executable.name
                browser=pw.chromium.launch(**launch,timeout=8000,headless=False,args=['--force-renderer-accessibility','--no-first-run'])
                try:
                    page=browser.new_page(viewport=dict(width=1100,height=780));page.set_default_timeout(4000)
                    page.goto('http://127.0.0.1:'+str(server.server_port)+'/index.html');page.bring_to_front()
                    windows=list_windows(title,5)
                    if len(windows)!=1:raise RuntimeError('Fixture window not uniquely identified')
                    hwnd=windows[0]['hwnd'];control=ComputerControl(SimpleNamespace(enabled=True))
                    control.execute(dict(action='focus',hwnd=hwnd))
                    result['local_perception']=perception_round(hwnd)
                    result['checks'].append(result['local_perception']['ok'])
                    if not result['local_perception']['ok']:raise RuntimeError('Local perception fixture conditions failed; no actions sent')
                    t=time.perf_counter();backend=UIABackend();result['load_ms']=round((time.perf_counter()-t)*1000,2)
                    for _ in range(3):
                        t=time.perf_counter();snapshot=backend.snapshot(hwnd,240)
                        result['snapshot_ms'].append(round((time.perf_counter()-t)*1000,2))
                    inputs=[r for r in snapshot['elements'] if r['name']=='验收输入' and r['type']=='Edit']
                    if len(inputs)!=1:raise RuntimeError('Input missing from snapshot')
                    for n in range(3):
                        text='具体验收'+str(n)
                        t=time.perf_counter();backend.act(hwnd,'set_value',name='验收输入',control_type='Edit',value=text)
                        result['name_action_ms'].append(round((time.perf_counter()-t)*1000,2))
                        result['checks'].append(page.input_value('#qa-input')==text)
                        t=time.perf_counter();backend.act(hwnd,'set_value',ref=inputs[0]['ref'],value='引用'+str(n))
                        result['ref_action_ms'].append(round((time.perf_counter()-t)*1000,2))
                        result['checks'].append(page.input_value('#qa-input')=='引用'+str(n))
                    backend.act(hwnd,'invoke',name='执行测试',control_type='Button')
                    result['checks'].append(page.evaluate('window.clicks')==1)
                    result['node_count']=len(snapshot['elements'])
                    if args.commands or args.live_voice:
                        from core.browser_interaction import BrowserInteraction
                        from core.fast_commands import match
                        interaction=BrowserInteraction();interaction.warmup()
                        result['command_ms']=[]
                        for text in ('点击输入框','输入语音原子指令验收','点击执行测试','向下滚动','向上滚动'):
                            command=match(text)
                            t=time.perf_counter();receipt=interaction.execute(command,hwnd=hwnd)
                            result['command_ms'].append(dict(action=command.get('browser_action'),ms=round((time.perf_counter()-t)*1000,2),ok=receipt.get('ok'),code=receipt.get('code'),error=receipt.get('error')))
                            result['checks'].append(receipt.get('ok') is True)
                            if command.get('browser_action')=='scroll_down':
                                page.wait_for_function('window.scrollY > 0',timeout=1000)
                                down=page.evaluate('window.scrollY');result['checks'].append(down>0)
                            elif command.get('browser_action')=='scroll_up':
                                page.wait_for_function('(before) => window.scrollY < before',arg=down,timeout=1000)
                                result['checks'].append(page.evaluate('window.scrollY')<down)
                        result['checks'].append(page.input_value('#qa-input')=='语音原子指令验收')
                        result['checks'].append(page.evaluate('window.clicks')==2)
                        for text in ('你帮我点一下上面的搜索框','往搜索框里输入自然说法验收','点击那个执行测试好吗'):
                            command=match(text);t=time.perf_counter();receipt=interaction.execute(command,hwnd=hwnd)
                            result['command_ms'].append(dict(action=command.get('browser_action'),ms=round((time.perf_counter()-t)*1000,2),ok=receipt.get('ok'),error=receipt.get('error')))
                            result['checks'].append(receipt.get('ok') is True)
                        result['checks'].append(page.input_value('#qa-input')=='自然说法验收')
                        result['checks'].append(page.evaluate('window.clicks')==3)
                        if args.live_voice:
                            result['voice']=voice_round(page,interaction,hwnd)
                            result['checks'].append(result['voice']['ok'])
                        interaction.close()
                finally:browser.close()
        except Exception as exc:result['errors'].append(type(exc).__name__+': '+str(exc)[:250])
        finally:server.shutdown();server.server_close()
    result['elapsed_seconds']=round(time.monotonic()-started,2)
    result['ok']=bool(result['checks'] and all(result['checks']) and not result['errors'])
    (folder/(args.label+'.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=True))
    return 0 if result['ok'] else 1


if __name__=='__main__':raise SystemExit(main())
