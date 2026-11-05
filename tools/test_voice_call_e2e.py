"""Offline end-to-end acceptance for the long-call fixes.

Simulates a real WS lifecycle with fake sockets and fake audio streams:
connect -> text-only response fallback -> drop -> reconnect -> clean stop.
No network, no microphone, no model calls.
"""
import base64
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from launcher import _prepare_qt
_prepare_qt()
from PyQt5.QtWidgets import QApplication
import websocket
from core.realtime_voice import DEFAULTS, RealtimeVoice

APP = QApplication.instance() or QApplication([])
CFG = dict(DEFAULTS, provider='bailian', workspace_id='test-space', api_key='test-credential', headphones=True,
           free_quota_confirmed_model=DEFAULTS['model'], free_quota_confirmed_provider='bailian', owner_only=False)


class Stream:
    opened = []
    def __init__(self, **kw):
        self.kw = kw
    def __enter__(self):
        Stream.opened.append(self)
        return self
    def __exit__(self, *args):
        Stream.opened.remove(self)


class FakeSocket:
    """Session handshake succeeds; subsequent recv can drop like a dead WS."""
    def __init__(self):
        self.events = [dict(type='session.created'), dict(type='session.updated')]
        self.sent = []
        self.closed = threading.Event()
        self.drop_after_events = False
    def queue(self, event):
        self.events.append(event)
    def recv(self):
        if self.events:
            return json.dumps(self.events.pop(0))
        if self.drop_after_events:
            self.drop_after_events = False
            raise ConnectionError('simulated transport drop')
        if self.closed.wait(0.02):
            return ''
        raise websocket.WebSocketTimeoutException()
    def send(self, message):
        self.sent.append(json.loads(message))
    def settimeout(self, timeout):
        pass
    def shutdown(self):
        self.closed.set()
    def close(self, **kwargs):
        self.closed.set()


def wait_until(predicate, timeout=8.0, interval=0.02):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        APP.processEvents()
        if predicate():
            return True
        time.sleep(interval)
    return False


class VoiceCallEndToEndTests(unittest.TestCase):
    def test_send_timeout_is_not_swallowed_as_receive_idle(self):
        engine=RealtimeVoice();engine._cfg=CFG;engine._call_started=time.monotonic();socket=FakeSocket();calls=[]
        def outgoing():
            calls.append(True)
            if len(calls)==1:raise websocket.WebSocketTimeoutException('send blocked')
            engine.stop()
        with patch('websocket.create_connection',return_value=socket),patch('sounddevice.RawInputStream',Stream), \
             patch('sounddevice.RawOutputStream',Stream),patch.object(engine,'_pump_outgoing',side_effect=outgoing):
            with self.assertRaises(websocket.WebSocketTimeoutException):engine._connection()
        self.assertEqual(len(calls),1)

    def test_unlimited_call_does_not_proactively_reconnect_after_110_minutes(self):
        engine=RealtimeVoice();engine._cfg=dict(CFG,max_call_minutes=0,idle_minutes=0)
        clock=[100.0];engine._call_started=100.0;socket=FakeSocket();reads=[];original_recv=socket.recv
        def receive():
            if not socket.events:
                reads.append(True);engine.stop();raise websocket.WebSocketTimeoutException()
            return original_recv()
        socket.recv=receive;original_connected=engine._set_connected
        def connected(value,reason=''):
            original_connected(value,reason)
            if value:clock[0]=7300.0
        with patch.object(engine,'_set_connected',side_effect=connected),patch('time.monotonic',side_effect=lambda:clock[0]), \
             patch('websocket.create_connection',return_value=socket),patch('sounddevice.RawInputStream',Stream),patch('sounddevice.RawOutputStream',Stream):
            engine._connection()
        self.assertEqual(reads,[True],'unlimited call must keep receiving rather than close at 110 minutes')

    def test_one_worker_owns_protocol_before_and_after_reconnect(self):
        engine=RealtimeVoice();created=[];owners=[]
        for socket in self.sockets:
            original_send=socket.send;original_recv=socket.recv
            def send(value,original=original_send):
                owners.append(threading.current_thread().name);return original(value)
            def recv(original=original_recv):
                owners.append(threading.current_thread().name);return original()
            socket.send=send;socket.recv=recv
        def connect(*args,**kwargs):
            socket=self.sockets[len(created)];created.append(socket);return socket
        with patch('websocket.create_connection',side_effect=connect),patch('sounddevice.RawInputStream',Stream),patch('sounddevice.RawOutputStream',Stream):
            try:
                engine.start(CFG);self.assertTrue(wait_until(lambda:engine.connected))
                self.sockets[0].drop_after_events=True
                self.assertTrue(wait_until(lambda:len(created)==2 and engine.connected))
            finally:
                engine.stop();self.assertTrue(wait_until(lambda:not engine.active))
        self.assertEqual(set(owners),{'guga-realtime'})

    def test_buffered_websocket_frame_is_read_without_waiting_for_new_socket_data(self):
        from types import SimpleNamespace
        socket=SimpleNamespace(sock=object(),frame_buffer=SimpleNamespace(recv_buffer=[b'buffered frame']))
        with patch('select.select',side_effect=AssertionError('already buffered')):
            self.assertTrue(RealtimeVoice._readable(socket))

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patches = [
            patch('core.realtime_voice.USAGE_PATH', Path(self.tmp.name) / 'usage.log'),
            patch('core.realtime_voice.VOICE_EVENTS_DIR', Path(self.tmp.name)),
        ]
        for item in self.patches:
            item.start()
        Stream.opened = []
        self.sockets = [FakeSocket(), FakeSocket()]

    def tearDown(self):
        for item in self.patches:
            item.stop()
        self.tmp.cleanup()

    def test_connect_text_only_fallback_drop_reconnect_stop(self):
        engine = RealtimeVoice()
        fallbacks = []
        engine.text_only_response.connect(fallbacks.append)
        created = []

        def connect_side_effect(*args, **kwargs):
            socket = self.sockets[len(created)]
            created.append(socket)
            return socket

        with patch('websocket.create_connection', side_effect=connect_side_effect), \
             patch('sounddevice.RawInputStream', Stream), patch('sounddevice.RawOutputStream', Stream):
            engine.start(CFG)
            # 1) real handshake -> connected requires the WS session and both streams
            self.assertTrue(wait_until(lambda: engine.connected and len(Stream.opened) >= 2),
                            f'not connected: {engine.last_error} {len(Stream.opened)}')
            # 2) a response with text but no audio must fall back locally exactly once
            self.sockets[0].queue(dict(type='response.created', response=dict(id='r1')))
            self.sockets[0].queue(dict(type='response.text.done', response_id='r1', text='这是只有文字的回答'))
            self.sockets[0].queue(dict(type='response.done',
                                       response=dict(id='r1', status='completed', usage={})))
            self.assertTrue(wait_until(lambda: fallbacks == ['这是只有文字的回答']), fallbacks)
            # 3) transport drop -> reconnect: connected is false during the gap
            self.sockets[0].drop_after_events = True
            self.assertTrue(wait_until(lambda: not engine.connected, timeout=3), 'connected stayed true after drop')
            # 4) second connection restores connected (2s backoff first attempt)
            self.assertTrue(wait_until(lambda: len(created) >= 2 and engine.connected, timeout=8),
                            f'reconnect failed: created={len(created)} connected={engine.connected} '
                            f'last_error={engine.last_error}')
            self.assertTrue(engine.active)
            engine.stop()
            self.assertTrue(wait_until(lambda: not engine.active, timeout=6))
        # 5) lifecycle log proves the sequence was recorded (no audio/text content)
        log = Path(self.tmp.name)
        lines = []
        for file in log.glob('voice-events-*.jsonl'):
            lines.extend(json.loads(line) for line in file.read_text(encoding='utf-8').splitlines() if line.strip())
        kinds = [item['kind'] for item in lines]
        self.assertIn('connected', kinds)
        self.assertIn('text_only_response', kinds)
        self.assertIn('reconnect', kinds)
        self.assertIn('disconnect', kinds)
        self.assertFalse(any('这是只有文字' in json.dumps(item, ensure_ascii=False) for item in lines),
                         'event log must not contain response text')

    def test_recoverable_server_error_reconnects_instead_of_ending_call(self):
        engine = RealtimeVoice()
        created = []

        def connect_side_effect(*args, **kwargs):
            socket = self.sockets[len(created)]
            created.append(socket)
            return socket

        with patch('websocket.create_connection', side_effect=connect_side_effect), \
             patch('sounddevice.RawInputStream', Stream), patch('sounddevice.RawOutputStream', Stream):
            engine.start(CFG)
            self.assertTrue(wait_until(lambda: engine.connected and len(Stream.opened) >= 2))
            self.sockets[0].queue(dict(type='error', error={'code': 'server_busy'}))
            self.assertTrue(wait_until(lambda: len(created) >= 2 and engine.connected, timeout=8),
                            f'did not reconnect: created={len(created)} last_error={engine.last_error}')
            self.assertNotIn('server_busy', engine.last_error)
            engine.stop()
            self.assertTrue(wait_until(lambda: not engine.active, timeout=6))


if __name__ == '__main__':
    unittest.main(verbosity=2)
