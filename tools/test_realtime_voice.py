"""Offline behavioral checks: no external APIs, audio capture or user credentials."""
import base64
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch,Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from launcher import _prepare_qt
_prepare_qt()
from PyQt5.QtWidgets import QApplication
from core.realtime_voice import DEFAULTS, PCMBuffer, RealtimeVoice, connection_url, session_settings, normalize_usage
from ui.voice_dialog import VoiceSettingsDialog, VoiceCallDialog

APP = QApplication.instance() or QApplication([])
CFG = dict(DEFAULTS, provider='bailian', workspace_id='test-space', api_key='test-credential', headphones=True,
           free_quota_confirmed_model=DEFAULTS['model'], free_quota_confirmed_provider='bailian', owner_only=False)


class Stream:
    opened = []
    def __init__(self, **kw):
        self.kw = kw
    def __enter__(self):
        self.opened.append(self)
        return self
    def __exit__(self, *args):
        self.opened.remove(self)


class Socket:
    def __init__(self):
        self.events = [dict(type='session.created'), dict(type='session.updated')]
        self.sent = []
        self.closed = threading.Event()
    def recv(self):
        if self.events:
            return json.dumps(self.events.pop(0))
        if self.closed.wait(0.02):
            return ''
        import websocket
        raise websocket.WebSocketTimeoutException()
    def send(self, message):
        self.sent.append(json.loads(message))
    def settimeout(self, timeout):
        pass
    def shutdown(self):
        self.closed.set()
    def close(self, **kwargs):
        self.closed.set()


class VoiceTests(unittest.TestCase):
    def setUp(self):
        self.usage_temp = tempfile.TemporaryDirectory()
        self.usage_patch = patch('core.realtime_voice.USAGE_PATH', Path(self.usage_temp.name)/'usage.log')
        self.usage_patch.start()
        self.addCleanup(self.usage_patch.stop)
        self.addCleanup(self.usage_temp.cleanup)

    def test_service_usage_missing_is_unknown_not_zero(self):
        self.assertIsNone(normalize_usage(None))
        self.assertIsNone(normalize_usage({'input_tokens':10}))
        usage = normalize_usage(dict(total_tokens=224, input_tokens=156, output_tokens=68))
        self.assertEqual(usage['total_tokens'], 224)
        self.assertIsNone(usage['input_audio_tokens'])

    def test_usage_counts_cancelled_responses_and_deduplicates(self):
        engine = RealtimeVoice()
        engine._cancelled.append('old')
        event = dict(type='response.done', response=dict(id='old', status='cancelled', usage=dict(total_tokens=5,input_tokens=3,output_tokens=2)))
        engine._handle_event(event)
        engine._handle_event(event)
        self.assertEqual(engine._usage_total, 5)
        self.assertEqual(engine._usage_rounds, 1)
        engine._handle_event(dict(type='response.done',response=dict(id='missing',status='cancelled')))
        self.assertEqual(engine._usage_total, 5)
        self.assertEqual(engine._usage_missing, 1)

    def test_usage_ui_does_not_claim_zero_for_cancelled_round(self):
        engine = RealtimeVoice()
        dialog = VoiceCallDialog(engine)
        dialog._usage(dict(rounds=2,reported_total_tokens=12,unreported_rounds=1,last_round=dict(round=2,usage=None)))
        self.assertEqual(dialog.last_tokens.text(), '—')
        self.assertEqual(dialog.total_tokens.text(), '≥ 12')
        dialog.close()
        dialog.deleteLater()

    def test_region_and_key_validation(self):
        self.assertIn('test-space.cn-beijing.maas.aliyuncs.com', connection_url(CFG))
        for changed in [dict(workspace_id='../../evil'), dict(region='elsewhere'), dict(api_key='')]:
            with self.assertRaises(ValueError):
                connection_url(dict(CFG, **changed))

    def test_qianwen_needs_only_key_and_uses_its_own_host(self):
        cfg = dict(CFG, provider='qianwen', workspace_id='', region='')
        self.assertEqual(connection_url(cfg),
                         'wss://maas.qianwenaiapi.com/api-ws/v1/realtime?model=qwen-audio-3.1-realtime-plus')
        with self.assertRaises(ValueError):
            connection_url(dict(cfg, api_key=''))

    def test_free_quota_confirmation_cannot_cross_platforms(self):
        engine = RealtimeVoice()
        with patch('websocket.create_connection') as connect:
            engine.start(dict(CFG, provider='qianwen', workspace_id=''))
            self.assertFalse(engine.active)
            connect.assert_not_called()

    def test_qianwen_settings_hide_workspace_and_clear_key_on_platform_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'ai_config.json'
            cfg = dict(CFG, provider='qianwen', workspace_id='', free_quota_confirmed_provider='qianwen')
            path.write_text(json.dumps({'realtime_voice':cfg}), encoding='utf-8')
            with patch('ui.voice_dialog.CONFIG_PATH', path):
                dialog = VoiceSettingsDialog()
                self.assertTrue(dialog.workspace.isHidden())
                self.assertTrue(dialog.region.isHidden())
                dialog._save()
                self.assertEqual(json.loads(path.read_text())['realtime_voice']['provider'], 'qianwen')
                dialog.provider.setCurrentIndex(1)
                self.assertEqual(dialog.key.text(), '')
                self.assertFalse(dialog.free_guard.isChecked())
                dialog.deleteLater()

    def test_bounded_pcm_and_zero_padding(self):
        buf = PCMBuffer(8)
        buf.append(b'abcd')
        self.assertEqual(buf.read(6), (b'abcd\0\0', True))
        with self.assertRaises(BufferError):
            buf.append(b'012345678')
        self.assertFalse(buf)

    def test_capture_gating_mute_and_queue_limit(self):
        engine = RealtimeVoice()
        engine._cfg = dict(CFG, headphones=False)
        engine._generating = True
        engine._capture(b'abcd', 2, None, None)
        self.assertEqual(engine._input.get_nowait(), b'abcd','Thinking/tool waits must not mute capture')
        engine._playing = True
        engine._capture(b'abcd', 2, None, None)
        self.assertEqual(engine._input.get_nowait(), bytes(4))
        engine._cfg['headphones'] = True
        engine._capture(b'abcd', 2, None, None)
        self.assertEqual(engine._input.get_nowait(), b'abcd')
        engine.mute(True)
        for i in range(100):
            engine._capture(b'abcd', 2, None, None)
        self.assertEqual(engine._input.qsize(), 30)
        self.assertEqual(engine._input.get_nowait(), bytes(4))

    def test_verified_audio_is_not_muted_during_silent_model_generation(self):
        engine=RealtimeVoice();engine._cfg=dict(CFG,headphones=False)
        engine._generating=True
        engine._speaker_output(b'abcd')
        self.assertEqual(engine._input.get_nowait(),b'abcd')
        engine._pcm.append(b'abcd')
        engine._speaker_output(b'abcd')
        self.assertEqual(engine._input.get_nowait(),bytes(4))

    def test_owner_gate_receives_mute_and_reports_processing_failure(self):
        engine=RealtimeVoice();engine._cfg=dict(CFG)
        gate=Mock();gate.submit.return_value=True;gate.error=''
        engine._speaker_gate=gate
        levels=[];engine.audio_level.connect(levels.append)
        engine._capture(b'\x10\x01'*640,640,None,None)
        gate.submit.assert_called_with(b'\x10\x01'*640,blocked=False)
        self.assertTrue(levels)
        engine.mute(True)
        engine._capture(b'\x10\x01'*640,640,None,None)
        gate.submit.assert_called_with(bytes(1280),blocked=True)
        gate.submit.return_value=False;gate.error='声纹队列已满'
        engine._capture(bytes(1280),640,None,None)
        self.assertTrue(engine._stop.is_set())
        self.assertEqual(engine.last_error,'声纹队列已满')

    def test_delayed_owner_release_cannot_bypass_mute(self):
        engine=RealtimeVoice();engine._cfg=dict(CFG)
        engine.mute(True)
        engine._speaker_output(b'\x10\x01'*640)
        self.assertEqual(engine._input.get_nowait(),bytes(1280))

    def test_owner_stream_congestion_is_reported_instead_of_dropping_words(self):
        engine=RealtimeVoice();engine._cfg=dict(CFG)
        for _ in range(30):engine._input.put_nowait(bytes(1280))
        engine._speaker_output(b'\x10\x01'*640)
        self.assertTrue(engine._stop.is_set())
        self.assertIn('避免静默丢字',engine.last_error)

    def test_cancelled_audio_never_returns(self):
        engine = RealtimeVoice()
        engine._handle_event(dict(type='response.created', response={'id':'old'}))
        data = base64.b64encode(b'1234').decode()
        engine._handle_event(dict(type='response.audio.delta', response_id='old', delta=data))
        self.assertTrue(engine._pcm)
        engine.interrupt()
        engine._handle_event(dict(type='response.audio.delta', response_id='old', delta=data))
        self.assertFalse(engine._pcm)
        engine._handle_event(dict(type='response.created', response={'id':'new'}))
        engine._handle_event(dict(type='response.audio.delta', response_id='new', delta=data))
        engine._handle_event(dict(type='response.done', response={'id':'old'}))
        self.assertTrue(engine._pcm)
        self.assertTrue(engine._generating)

    def test_context_is_bounded_and_not_persisted(self):
        settings = session_settings(CFG, [('饲养员', 'x'*2000)]*150)
        self.assertLess(len(settings['instructions']), 17000)
        self.assertEqual(settings['turn_detection']['type'], 'server_vad')
        self.assertEqual(settings['max_history_turns'], 16)

    def test_server_vad_interrupt_does_not_send_duplicate_cancel(self):
        engine = RealtimeVoice()
        engine._handle_event(dict(type='response.created', response={'id':'old'}))
        engine._pcm.append(b'1234')
        with patch.object(engine, '_send') as send:
            engine._handle_event(dict(type='input_audio_buffer.speech_started'))
            send.assert_not_called()
        self.assertFalse(engine._pcm)

    def test_unconfirmed_free_quota_blocks_network(self):
        engine = RealtimeVoice()
        with patch('websocket.create_connection') as connect:
            engine.start(dict(CFG, free_quota_confirmed_model=''))
            self.assertFalse(engine.active)
            connect.assert_not_called()

    def test_exhausted_free_quota_is_fatal(self):
        engine = RealtimeVoice()
        with self.assertRaisesRegex(ValueError, '免费额度'):
            engine._handle_event(dict(type='error', error={'code':'AllocationQuota.FreeTierOnly'}))

    def test_stop_releases_both_devices(self):
        engine = RealtimeVoice()
        socket = Socket()
        with patch('websocket.create_connection', return_value=socket), \
             patch('sounddevice.RawInputStream', Stream), patch('sounddevice.RawOutputStream', Stream):
            engine.start(CFG)
            deadline = time.monotonic() + 2
            while len(Stream.opened) < 2 and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertEqual(len(Stream.opened), 2)
            engine.stop()
            engine._thread.join(3)
            self.assertFalse(engine.active)
            self.assertFalse(Stream.opened)
            self.assertTrue(socket.closed.is_set())

    def test_voice_defaults_to_direct_capture_without_speaker_enrollment(self):
        self.assertFalse(DEFAULTS['owner_only'])
        engine=RealtimeVoice();socket=Socket();cfg=dict(CFG);cfg.pop('owner_only',None)
        with patch('websocket.create_connection',return_value=socket), \
             patch('sounddevice.RawInputStream',Stream),patch('sounddevice.RawOutputStream',Stream), \
             patch('core.speaker_gate.SpeakerGate') as gate:
            engine.start(cfg)
            deadline=time.monotonic()+2
            while len(Stream.opened)<2 and time.monotonic()<deadline:time.sleep(.01)
            gate.assert_not_called();self.assertIsNone(engine._speaker_gate)
            engine._capture(b'abcd',2,None,None)
            self.assertEqual(engine._input.get_nowait(),b'abcd')
            engine.stop();engine._thread.join(3)

    def test_server_rejects_config_before_microphone_opens(self):
        engine = RealtimeVoice()
        socket = Socket()
        socket.events[1] = dict(type='error', error={'code':'invalid_parameter'})
        with patch('websocket.create_connection', return_value=socket), \
             patch('sounddevice.RawInputStream', Stream), patch('sounddevice.RawOutputStream', Stream):
            engine.start(CFG)
            engine._thread.join(3)
            self.assertFalse(engine.active)
            self.assertFalse(Stream.opened)
            self.assertIn('invalid_parameter', engine.last_error)

    def test_settings_preserve_existing_config_and_mask_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'ai_config.json'
            path.write_text(json.dumps({'api_key':'old-chat-key','unrelated':42,'realtime_voice':CFG}), encoding='utf-8')
            with patch('ui.voice_dialog.CONFIG_PATH', path):
                dialog = VoiceSettingsDialog()
                self.assertEqual(dialog.key.echoMode(), dialog.key.Password)
                dialog._save()
                saved = json.loads(path.read_text(encoding='utf-8'))
                self.assertEqual(saved['api_key'], 'old-chat-key')
                self.assertEqual(saved['unrelated'], 42)
                self.assertEqual(saved['realtime_voice']['workspace_id'], 'test-space')
                dialog.deleteLater()

    def test_call_window_close_stops_capture(self):
        engine = RealtimeVoice()
        dialog = VoiceCallDialog(engine)
        dialog.show()
        dialog.close()
        self.assertTrue(engine._stop.is_set())
        dialog.deleteLater()


if __name__ == '__main__':
    unittest.main()
