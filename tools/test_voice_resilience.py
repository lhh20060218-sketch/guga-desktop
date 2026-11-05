"""End-to-end call resilience checks: real-online flag, text-only fallback,
error grading, reconnect queue preservation. Offline only; no network/audio."""
import base64
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import sys
sys.path.insert(0, str(ROOT))

from launcher import _prepare_qt
_prepare_qt()
from PyQt5.QtWidgets import QApplication
from core.realtime_voice import RealtimeVoice, RecoverableVoiceError
from core.realtime_agent import AgentRealtimeVoice

APP = QApplication.instance() or QApplication([])


class VoiceResilienceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patches = [
            patch('core.realtime_voice.USAGE_PATH', Path(self.tmp.name) / 'usage.log'),
            patch('core.realtime_voice.VOICE_EVENTS_DIR', Path(self.tmp.name)),
        ]
        for item in self.patches:
            item.start()
        self.voice = RealtimeVoice()

    def tearDown(self):
        for item in self.patches:
            item.stop()
        self.tmp.cleanup()

    def _done(self, voice, response_id='r1', status='completed'):
        voice._handle_event(dict(type='response.done', response=dict(id=response_id, status=status, usage={})))

    def test_connected_is_false_without_a_ws_session(self):
        self.assertFalse(self.voice.active)
        self.assertFalse(self.voice.connected)
        self.voice._connected = True
        self.assertFalse(self.voice.connected, 'a dead thread must not report connected')
        self.voice._thread = type('T', (), {'is_alive': lambda self: True})()
        self.assertTrue(self.voice.connected)

    def test_text_only_response_falls_back_once(self):
        seen = []
        self.voice.text_only_response.connect(seen.append)
        self.voice._handle_event(dict(type='response.created', response=dict(id='r1')))
        self.voice._handle_event(dict(type='response.text.done', response_id='r1', text='只有文字没有音频'))
        self._done(self.voice)
        self._done(self.voice)
        self.assertEqual(seen, ['只有文字没有音频'])

    def test_response_with_audio_does_not_fall_back(self):
        seen = []
        self.voice.text_only_response.connect(seen.append)
        self.voice._handle_event(dict(type='response.created', response=dict(id='r1')))
        self.voice._handle_event(dict(type='response.audio.delta', response_id='r1',
                                      delta=base64.b64encode(b'\x00\x00').decode('ascii')))
        self.voice._handle_event(dict(type='response.text.done', response_id='r1', text='有音频'))
        self._done(self.voice)
        self.assertEqual(seen, [])

    def test_recoverable_error_requests_reconnect(self):
        with self.assertRaises(RecoverableVoiceError):
            self.voice._handle_event(dict(type='error', error=dict(code='server_busy')))
        self.assertTrue(issubclass(RecoverableVoiceError, ConnectionError))

    def test_fatal_errors_end_the_call(self):
        for code in ('AllocationQuota.FreeTierOnly', 'auth_failed', 'invalid_api_key', 'quota_exceeded'):
            with self.subTest(code=code):
                with self.assertRaises(ValueError):
                    self.voice._handle_event(dict(type='error', error=dict(code=code)))

    def test_reconnect_preserves_progress_and_results_but_not_audio(self):
        agent = AgentRealtimeVoice()
        agent._input.put_nowait(b'audio')
        agent._commands.put_nowait(('bg_notice', 'k1', '进度', 0.0, 0))
        agent._commands.put_nowait(('task_result', 'call-1', dict(ok=True, answer='结果')))
        agent._commands.put_nowait(('abandon', ['call-2']))
        agent._clear_queues()
        self.assertTrue(agent._input.empty())
        kept = []
        while True:
            try:
                kept.append(agent._commands.get_nowait())
            except Exception:
                break
        kinds = [item[0] for item in kept]
        self.assertIn('bg_notice', kinds)
        self.assertIn('task_result', kinds)
        self.assertNotIn('abandon', kinds, 'old call IDs must never cross a reconnect')


if __name__ == '__main__':
    unittest.main(verbosity=2)
