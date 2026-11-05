"""Natural speech punctuation and message content must not disable execution."""
import os
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from core.execution_contract import requires_execution
from core.fast_commands import match,execute
from core.authorized_apps import AuthorizedApps


class CommandIntentTests(unittest.TestCase):
    def test_question_in_message_body_does_not_turn_request_into_qa(self):
        for text in ('打开，微信，找到验收联系人，发送，最近怎么样，忙完了吗',
                     '打开微信，给验收联系人发送“你在哪里？”',
                     '你能打开微信吗','可以打开微信吗'):
            with self.subTest(text=text):self.assertTrue(requires_execution(text))

    def test_how_to_diagnostics_and_quotations_still_stay_qa(self):
        for text in ('微信发送失败是什么问题','下载速度慢是什么原因','怎么打开微信',
                     '请你解释如何打开微信','打开微信是什么意思','“打开微信”是什么意思'):
            with self.subTest(text=text):self.assertFalse(requires_execution(text))

    def test_single_app_requests_need_no_grant_or_installed_app_scan_in_parser(self):
        with patch.object(AuthorizedApps,'available',side_effect=AssertionError('parser must not scan disk')):
            for text in ('打开微信','打开，微信','帮我打开一下微信好吗','你能打开微信吗','打开，记事本'):
                with self.subTest(text=text):
                    command=match(text);self.assertTrue(command['matched']);self.assertEqual(command['action'],'open_app')
        self.assertEqual(match('你能打开微信吗')['target'],'微信')

    def test_multi_action_does_not_drop_the_rest_or_launch_a_question(self):
        for text in ('打开，微信，找到验收联系人，发送，忙完了吗','打开微信然后找到验收联系人',
                     '不要打开微信','打开微信是什么意思','打开某个新的科学网站'):
            with self.subTest(text=text):self.assertFalse(match(text)['matched'])

    def test_installed_name_resolution_is_case_insensitive_without_fuzzy_guess(self):
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'Fixture.exe';target.touch()
            apps=AuthorizedApps(Path(folder)/'grants.json');apps.access=SimpleNamespace(enabled=True)
            with patch('core.window_inventory.list_windows',return_value=[]),patch.object(apps,'available',return_value={'Fixture':str(target)}),patch('os.startfile') as start:
                receipt=apps.open('fixture');self.assertTrue(receipt['launch_requested']);start.assert_called_once_with(str(target))
                with self.assertRaises(ValueError):apps.open('Fix')

    def test_wechat_never_reuses_work_wechat_or_a_document_title(self):
        from core.window_inventory import matching_windows
        windows=[dict(hwnd=1,title='企业微信',process_name='WXWork.exe'),
                 dict(hwnd=2,title='微信操作说明.txt',process_name='notepad.exe')]
        self.assertEqual(matching_windows(windows,'微信'),[])
        windows.append(dict(hwnd=3,title='微信',process_name='Weixin.exe'))
        self.assertEqual(matching_windows(windows,'微信'),[windows[-1]])


class PendingVoiceResponseTests(unittest.TestCase):
    def test_invalid_semantic_turn_releases_native_wait(self):
        from core.realtime_agent import AgentRealtimeVoice
        voice=AgentRealtimeVoice()
        with patch.object(voice,'_send') as send:
            voice._handle_event(dict(type='input_audio_buffer.speech_started'))
            voice._handle_event(dict(type='input_audio_buffer.speech_stopped',reason='turn_invalid'))
            voice._request_audio_response()
        self.assertEqual(sum(c.args[0]['type']=='response.create' for c in send.call_args_list),1)

    def test_native_vad_gap_does_not_allow_another_response_create(self):
        from core.realtime_agent import AgentRealtimeVoice
        voice=AgentRealtimeVoice()
        with patch.object(voice,'_send') as send:
            voice._handle_event(dict(type='input_audio_buffer.speech_started',item_id='speech-1'))
            voice._handle_event(dict(type='input_audio_buffer.speech_stopped',item_id='speech-1'))
            voice._request_audio_response()
            self.assertFalse(any(c.args[0]['type']=='response.create' for c in send.call_args_list))
            voice._handle_event(dict(type='response.created',response=dict(id='native-1')))
            voice._handle_event(dict(type='response.done',response=dict(id='native-1',status='completed')))
            voice._process_command(None)
            self.assertEqual(sum(c.args[0]['type']=='response.create' for c in send.call_args_list),1)

    def test_native_vad_gap_does_not_push_session_configuration(self):
        from core.realtime_agent import AgentRealtimeVoice
        voice=AgentRealtimeVoice();voice._ws=object();voice._screen_configured=True
        voice.screen_context_provider=lambda:dict(active=True,fresh=True,context='测试画面')
        with patch.object(voice,'_send') as send:
            voice._handle_event(dict(type='input_audio_buffer.speech_started'))
            voice._handle_event(dict(type='input_audio_buffer.speech_stopped'))
            voice._sync_screen_context()
        send.assert_not_called()

    def test_late_old_done_does_not_release_a_new_unacknowledged_create(self):
        from core.realtime_agent import AgentRealtimeVoice
        voice=AgentRealtimeVoice()
        with patch.object(voice,'_send') as send:
            voice._request_audio_response()
            voice._handle_event(dict(type='response.done',response=dict(id='old',status='completed')))
            voice._request_audio_response()
        self.assertEqual(sum(c.args[0]['type']=='response.create' for c in send.call_args_list),1)

    def test_untyped_quota_error_during_handshake_stops_without_reconnect_or_microphone(self):
        from core.realtime_voice import RealtimeVoice,DEFAULTS
        class Socket:
            def __init__(self):self.events=iter([dict(type='session.created'),dict(code='AllocationQuota.FreeTierOnly',message='quota exhausted')])
            def recv(self):return json.dumps(next(self.events))
            def send(self,value):pass
            def close(self,**kwargs):pass
        voice=RealtimeVoice();voice._cfg=dict(DEFAULTS,api_key='offline');failures=[];voice.failed.connect(failures.append)
        with patch('websocket.create_connection',return_value=Socket()) as connect,patch('sounddevice.RawInputStream') as microphone:
            voice._run()
        connect.assert_called_once();microphone.assert_not_called()
        self.assertEqual(len(failures),1);self.assertIn('免费额度',failures[0]);self.assertFalse(voice.connected)

    def test_untyped_quota_error_in_established_session_is_terminal(self):
        from core.realtime_voice import RealtimeVoice
        with self.assertRaisesRegex(ValueError,'免费额度'):
            RealtimeVoice()._handle_event(dict(code='AllocationQuota.FreeTierOnly',message='quota exhausted'))

    def test_user_text_waits_for_not_yet_created_response_then_cancels_once(self):
        from core.realtime_agent import AgentRealtimeVoice
        voice=AgentRealtimeVoice()
        with patch.object(voice,'_send') as send:
            voice._request_audio_response()
            voice._process_command(('user_text','你好，请只回答收到'))
            self.assertEqual(sum(c.args[0]['type']=='response.create' for c in send.call_args_list),1)
            voice._handle_event(dict(type='response.created',response=dict(id='pending')))
            self.assertEqual(sum(c.args[0]['type']=='response.cancel' for c in send.call_args_list),1)
            voice._process_command(None)
            self.assertEqual(sum(c.args[0]['type']=='response.create' for c in send.call_args_list),1)
            voice._handle_event(dict(type='response.done',response=dict(id='pending',status='cancelled')))
            voice._process_command(None)
            self.assertEqual(sum(c.args[0]['type']=='response.create' for c in send.call_args_list),2)


if __name__=='__main__':unittest.main(verbosity=2)
