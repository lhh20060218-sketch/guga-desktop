"""Regressions for interruption races and low-latency website requests."""
import os
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from launcher import _prepare_qt
_prepare_qt()
from PyQt5.QtWidgets import QApplication
from core.fast_commands import match
from core.realtime_voice import RealtimeVoice, RecoverableVoiceError
from core.realtime_agent import AgentRealtimeVoice

APP = QApplication.instance() or QApplication([])


class LongVoiceStabilityTests(unittest.TestCase):
    @unittest.skipUnless(os.name=='nt','Windows registered URL handler')
    def test_default_browser_flags_and_single_url_argument_are_preserved(self):
        from core.browser_launch import launch_arguments
        executable=Path('C:/Example/Doubao.exe')
        url='https://example.com/?q=hello&x=1'
        with patch('winreg.OpenKey'),patch('winreg.QueryValueEx',return_value=('Example.Url',1)), \
                patch('winreg.QueryValue',return_value='"C:/Example/Doubao.exe" --single-argument %1'):
            args=launch_arguments(executable,url)
            self.assertEqual(Path(args[0]),executable)
            self.assertEqual(args[1:],['--single-argument',url])

    def test_fast_transcript_finishes_native_tool_instead_of_cancelling_it(self):
        import json
        voice=AgentRealtimeVoice();commands=[]
        voice.fast_command.connect(commands.append)
        voice._handle_event(dict(type='response.created',response=dict(id='native')))
        with patch.object(voice,'_send') as send:
            voice._handle_event(dict(type='conversation.item.input_audio_transcription.completed',transcript='打开百度'))
            self.assertFalse(any(c.args[0]['type']=='response.cancel' for c in send.call_args_list))
            voice._handle_event(dict(type='response.function_call_arguments.done',response_id='native',call_id='native-call',
                name='ask_deepseek',arguments=json.dumps(dict(request='打开百度'))))
            voice.complete_fast_command(commands[0]['fast_id'],dict(ok=True,message='已提交网址'))
            voice._process_command(voice._commands.get_nowait())
            outputs=[c.args[0] for c in send.call_args_list if c.args[0].get('item',{}).get('call_id')=='native-call']
            self.assertEqual(len(commands),1);self.assertEqual(len(outputs),1)
            self.assertTrue(json.loads(outputs[0]['item']['output'])['ok'])

    def test_polite_site_requests_are_local(self):
        for text in ('你能帮我打开一下 GitHub 官网吗？', '帮我打开一个百度的网站',
                     '给我打开B站这个网站吧', '用默认浏览器打开 https://example.com/docs 好吗？'):
            with self.subTest(text=text):
                result = match(text)
                self.assertEqual(result.get('action'), 'open_url')

    def test_compound_and_negative_requests_are_not_simple_opens(self):
        for text in ('不要打开百度', '打开百度然后下载软件', '打开https://example.com然后帮我登录'):
            self.assertFalse(match(text)['matched'], text)

    def test_local_text_fallback_does_not_wait_for_model_routing(self):
        voice = AgentRealtimeVoice()
        commands = []
        voice.fast_command.connect(commands.append)
        with patch.object(voice, '_send') as send:
            voice._process_command(('user_text', '请帮我打开 GitHub 官网'))
        self.assertEqual(len(commands), 1)
        self.assertFalse(any(c.args[0]['type'] == 'response.create' for c in send.call_args_list))

    def test_delayed_model_call_does_not_open_same_site_twice(self):
        voice = AgentRealtimeVoice()
        commands = []
        voice.fast_command.connect(commands.append)
        voice._dispatch_fast(match('打开百度'))
        for job in voice._fast_jobs.values():
            job['started'] = time.monotonic()-5
        voice._dispatch_fast(match('打开百度'), 'late-call')
        self.assertEqual(len(commands), 1)

    def test_user_speech_gate_survives_task_invalidation(self):
        voice = AgentRealtimeVoice()
        voice._handle_event(dict(type='input_audio_buffer.speech_started'))
        self.assertTrue(voice._user_speaking)
        voice._handle_event(dict(type='input_audio_buffer.speech_stopped'))
        self.assertFalse(voice._user_speaking)

    def test_cancelled_response_done_releases_current_generation(self):
        voice = RealtimeVoice()
        voice._response_id = 'old'
        voice._generating = True
        voice._cancelled.append('old')
        voice._handle_event(dict(type='response.done', response=dict(id='old', status='cancelled')))
        self.assertFalse(voice._generating)

    def test_late_done_does_not_clear_new_response(self):
        voice = RealtimeVoice()
        voice._response_id = 'new'
        voice._generating = True
        voice._handle_event(dict(type='response.done', response=dict(id='old', status='completed')))
        self.assertTrue(voice._generating)
        self.assertEqual(voice._response_id, 'new')

    def test_turn_state_errors_do_not_end_or_reconnect_call(self):
        voice = RealtimeVoice()
        voice._handle_event(dict(type='response.created', response=dict(id='active')))
        for code in ('response_cancel_not_active', 'response_already_in_progress', 'invalid_request_error'):
            voice._handle_event(dict(type='error', error=dict(type='invalid_request_error', code=code)))
        self.assertEqual(voice._response_id, 'active')

    def test_transient_failed_turn_is_recoverable_but_quota_still_stops(self):
        voice = RealtimeVoice()
        with self.assertRaises(RecoverableVoiceError):
            voice._handle_event(dict(type='response.done', response=dict(id='r', status='failed',
                status_details=dict(error=dict(code='server_error')))))
        with self.assertRaises(ValueError):
            voice._handle_event(dict(type='response.done', response=dict(id='r2', status='failed',
                status_details=dict(error=dict(code='AllocationQuota.FreeTierOnly')))))

    def test_interrupt_text_waits_for_cancel_ack_before_response_create(self):
        voice = AgentRealtimeVoice()
        voice._handle_event(dict(type='response.created', response=dict(id='old')))
        with patch.object(voice, '_send') as send:
            voice._process_command(('user_text', '你好，请只回答收到'))
            self.assertFalse(any(c.args[0]['type'] == 'response.create' for c in send.call_args_list))
            voice._handle_event(dict(type='response.done', response=dict(id='old', status='cancelled')))
            voice._process_command(None)
            self.assertEqual(sum(c.args[0]['type'] == 'response.create' for c in send.call_args_list), 1)

    def test_reconnect_does_not_send_old_session_tool_outputs(self):
        voice = AgentRealtimeVoice()
        voice._commands.put_nowait(('abandon', ['old-call']))
        voice._clear_queues()
        with patch.object(voice, '_send') as send:
            while not voice._commands.empty():
                voice._process_command(voice._commands.get_nowait())
        self.assertFalse(any(c.args[0].get('item', {}).get('call_id') == 'old-call' for c in send.call_args_list))


if __name__ == '__main__':
    unittest.main(verbosity=2)
