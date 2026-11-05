"""Bounded real-service acceptance through the production voice worker.

Opt in with --live. Uses synthetic silence and discards PCM; never opens audio
devices, reads the screen, or executes desktop actions. Keeps the free-only
guard in RealtimeVoice.start. Output contains counters/timings, no credentials.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import threading
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from launcher import _prepare_qt
_prepare_qt()
from PyQt5.QtWidgets import QApplication
from core.realtime_agent import AgentRealtimeVoice
from core.realtime_voice import load_settings


class SilentStream:
    source = b''
    offset = 0
    feed = threading.Event()
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.ended = threading.Event()

    def __enter__(self):
        def run():
            frames = self.kwargs['blocksize']
            interval = frames / self.kwargs['samplerate']
            while not self.ended.wait(interval):
                data = bytearray(frames * 2)
                if self.kwargs['samplerate'] == 16000 and self.feed.is_set():
                    chunk = self.source[SilentStream.offset:SilentStream.offset+frames*2]
                    data[:len(chunk)] = chunk
                    SilentStream.offset += len(chunk)
                self.kwargs['callback'](data, frames, None, None)
        self.thread = threading.Thread(target=run, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.ended.set()
        self.thread.join(2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--seconds', type=int, default=40, choices=range(20, 91))
    parser.add_argument('--label', default='after')
    parser.add_argument('--audio-command', action='store_true', help='synthesize one generic website request and send as PCM')
    parser.add_argument('--open-browser', action='store_true', help='actually launch the one website requested by synthetic speech')
    parser.add_argument('--static-context', action='store_true', help='diagnostic: skip mid-session context updates')
    parser.add_argument('--direct', action='store_true', help='diagnostic: connect to configured provider without environment proxy')
    parser.add_argument('--changing-context', action='store_true', help='exercise changing synthetic screen facts every three seconds')
    parser.add_argument('--proactive', action='store_true', help='exercise periodic proactive speech alongside user turns')
    args = parser.parse_args()
    if not args.live:
        parser.error('--live required; uses the configured confirmed free quota')
    app = QApplication.instance() or QApplication([])
    cfg = load_settings()
    if not (cfg.get('free_only') and cfg.get('free_quota_confirmed_model') == cfg.get('model')
            and cfg.get('free_quota_confirmed_provider') == cfg.get('provider')):
        raise RuntimeError('Confirmed free-only configuration required')
    if args.open_browser and not args.audio_command:
        parser.error('--open-browser requires --audio-command')
    if args.audio_command:
        import numpy as np
        from tools.probe_realtime_voice import probe
        preparation, audio = probe(prompt='请只原样念出这句测试语音，不回答：帮我打开 GitHub 官网。', return_audio=True)
        if not preparation['completed']:
            raise RuntimeError('Synthetic test speech unavailable')
        samples = np.frombuffer(audio, dtype='<i2')
        SilentStream.source = np.interp(np.arange(0,len(samples),1.5), np.arange(len(samples)), samples).astype('<i2').tobytes()
    voice = AgentRealtimeVoice()
    if args.static_context:voice._sync_screen_context=lambda *a,**kw:None
    context_started=time.monotonic()
    voice.screen_context_provider = lambda: dict(active=True, fresh=True,
        context='合成测试画面：左侧蓝圆、右侧黄方。'+('测试状态'+str(int((time.monotonic()-context_started)//3)) if args.changing_context else ''), sequence=1)
    voice.set_task_context(dict(running=True, kind='controlled_wait', goal='受控等待', summary='后台仍在等待'))
    result = dict(label=args.label, connected_count=0, drops=0, responses=0,
                  audio_bytes=0, errors=[], events={}, first_audio_ms=[], fast_commands=[],
                  microphone=False, speaker=False, desktop_actions=args.open_browser,
                  synthetic_audio=args.audio_command, speech_started=0, speech_stopped=0)
    result['static_context']=args.static_context
    result['direct']=args.direct
    started = time.monotonic()
    sent_at = None
    audio_seen = False
    original = voice._handle_event

    def handle(event):
        nonlocal audio_seen
        kind = event.get('type', '')
        result['events'][kind] = result['events'].get(kind, 0) + 1
        if kind == 'response.audio.delta':
            import base64
            result['audio_bytes'] += len(base64.b64decode(event.get('delta', '')))
            if sent_at is not None and not audio_seen:
                result['first_audio_ms'].append(round((time.monotonic()-sent_at)*1000, 1))
                audio_seen = True
        if kind == 'response.done':
            result['responses'] += 1
        if kind == 'input_audio_buffer.speech_started':result['speech_started'] += 1
        if kind == 'input_audio_buffer.speech_stopped':result['speech_stopped'] += 1
        if kind == 'error':
            error = event.get('error') or {}
            result['errors'].append(dict(code=error.get('code'), type=error.get('type'),param=error.get('param')))
        original(event)
    voice._handle_event = handle
    def connection(value):
        if value:
            result['connected_count'] += 1
        elif not voice._stop.is_set():
            result['drops'] += 1
    voice.connected_changed.connect(connection)
    voice.failed.connect(lambda error: result['errors'].append(dict(failure=error)))
    def fast(command):
        receipt = dict(ok=True, message='测试执行器已受理')
        if args.open_browser:
            from core.fast_commands import execute
            # The probe is deliberately limited to this one harmless target.
            if command.get('action')!='open_url' or command.get('target')!='https://github.com':
                receipt = dict(ok=False, error='unexpected action blocked by probe')
            else:receipt=execute(command)
        result['fast_commands'].append(dict(action=command['action'],
            asr_after_speech_ms=command.get('asr_after_speech_ms'),
            ms=round((time.monotonic()-command['recognized_at'])*1000, 1),
            ok=receipt['ok'], launch_requested=receipt.get('launch_requested',False)))
        voice.complete_fast_command(command['fast_id'], receipt)
    voice.fast_command.connect(fast)
    voice.task_requested.connect(lambda ident, request: voice.resolve_task(ident,
        dict(ok=True, answer='这是受控测试回执，后台任务继续执行。')))
    turns = ['请只回答收到两个字。', '画面里左边是什么颜色？请用一句话回答。',
             '请帮我打开 GitHub 官网。', '后台任务还在执行吗？请简短回答。']
    submitted = 0
    proactive_sent=0
    if args.audio_command:turns=[]
    try:
        import websocket
        from urllib.parse import urlsplit
        original_connect=websocket.create_connection
        def connect(url, **kwargs):
            if args.direct:kwargs['http_no_proxy']=[urlsplit(url).hostname]
            return original_connect(url, **kwargs)
        with patch('sounddevice.RawInputStream', SilentStream), patch('sounddevice.RawOutputStream', SilentStream), patch('websocket.create_connection',side_effect=connect):
            voice.start(cfg)
            while time.monotonic()-started < args.seconds:
                app.processEvents()
                elapsed = time.monotonic()-started
                if args.proactive and voice.connected and elapsed>=10*(proactive_sent+1):
                    voice.notify_proactive('probe-'+str(proactive_sent),'只说“本鹅还在”，不调用工具。')
                    proactive_sent+=1
                if args.audio_command and voice.connected and elapsed>=2:SilentStream.feed.set()
                if (voice.connected and submitted < len(turns) and elapsed >= 3+submitted*7
                        and not voice._generating and not voice._playing):
                    sent_at = time.monotonic()
                    audio_seen = False
                    voice.submit_user_text(turns[submitted])
                    submitted += 1
                time.sleep(.01)
            result['connected_at_end'] = voice.connected
            result['background_still_running'] = voice.interaction_status()['task_running']
            result['submitted'] = submitted
            voice.stop()
            if voice._thread:
                voice._thread.join(5)
            app.processEvents()
    finally:
        voice.stop()
    result['elapsed_seconds'] = round(time.monotonic()-started, 2)
    result['worker_stopped'] = not voice.active
    result['ok'] = bool(result.get('connected_at_end') and result['drops'] == 0
        and result['audio_bytes'] and submitted == len(turns) and not result['errors']
        and result['fast_commands'] and all(c['ok'] for c in result['fast_commands']) and result['worker_stopped']
        and (not args.audio_command or (result['speech_started'] and result['speech_stopped'])))
    folder = ROOT/'runtime/long-voice-qa'
    folder.mkdir(parents=True, exist_ok=True)
    (folder/(args.label+'.json')).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=True))
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
