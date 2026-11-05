"""Offline Qwen=>DeepSeek handoff, cancellation, serialization and native voice regressions."""
import json
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
from core.realtime_voice import DEFAULTS, RealtimeVoice
from core.realtime_agent import AgentRealtimeVoice

APP = QApplication.instance() or QApplication([])


class RealtimeAgentTests(unittest.TestCase):
    def engine(self):
        engine = AgentRealtimeVoice()
        engine._cfg = dict(DEFAULTS)
        return engine

    def test_live_screen_facts_and_reader_tool_reach_initial_session(self):
        engine=self.engine();engine.screen_context_provider=lambda:dict(active=True,fresh=True,
            context='蓝色圆形与屏幕验收',foreground=dict(hwnd=12,process='fixture.exe',title='验收页'),sequence=7)
        settings=engine._session_settings()
        self.assertIn('蓝色圆形',settings['instructions'])
        self.assertIn('"active": true',settings['instructions'])
        self.assertIn('read_screen',[tool['name'] for tool in settings['tools']])

    def test_screen_updates_replace_instructions_without_creating_speech(self):
        engine=self.engine();state=dict(active=True,fresh=True,context='验收页面',foreground=dict(hwnd=12),sequence=1)
        engine.screen_context_provider=lambda:state;engine._ws=object()
        engine._handle_event(dict(type='session.updated'))
        with patch.object(engine,'_send') as send:
            engine._sync_screen_context(force=True)
            self.assertEqual(send.call_args.args[0]['type'],'session.update')
            self.assertEqual(list(send.call_args.args[0]['session']),['instructions'])
            engine._handle_event(dict(type='session.updated'))
            engine._screen_checked_at=0;state['sequence']=2;engine._sync_screen_context()
            self.assertEqual(send.call_count,1) # no new model request for every captured frame
            state.update(fresh=False,context='当前画面已变化，待重新读取');engine._screen_checked_at=0
            engine._screen_last_sent_at=time.monotonic()-11
            engine._sync_screen_context();self.assertEqual(send.call_count,2)
            self.assertIn('待重新读取',send.call_args.args[0]['session']['instructions'])
            self.assertFalse(any(c.args[0]['type']=='response.create' for c in send.call_args_list))
        engine._handle_event(dict(type='session.updated'))
        self.assertEqual(engine.screen_bridge_status()['updates_acked'],2)

    def test_screen_updates_wait_for_ack_and_coalesce_to_latest_state(self):
        engine=self.engine();state=dict(active=True,fresh=True,context='原画面')
        engine.screen_context_provider=lambda:state;engine._ws=object();engine._screen_configured=True
        with patch.object(engine,'_send') as send:
            engine._sync_screen_context(force=True)
            state['context']='中间画面';engine._screen_checked_at=0;engine._screen_last_sent_at=time.monotonic()-11
            engine._sync_screen_context();self.assertEqual(send.call_count,1)
            state['context']='最新画面';engine._handle_event(dict(type='session.updated'));engine._screen_checked_at=0
            engine._sync_screen_context();self.assertEqual(send.call_count,2)
            self.assertIn('最新画面',send.call_args.args[0]['session']['instructions'])
            self.assertNotIn('中间画面',send.call_args.args[0]['session']['instructions'])

    def test_screen_updates_do_not_interrupt_playback_or_unacknowledged_reply(self):
        for busy in ('_playing','_audio_request_pending'):
            engine=self.engine();engine._ws=object();engine._screen_configured=True
            engine.screen_context_provider=lambda:dict(active=True,fresh=True,context='新画面')
            setattr(engine,busy,True)
            with patch.object(engine,'_send') as send:engine._sync_screen_context()
            send.assert_not_called()

    def test_read_screen_dispatches_to_host_without_starting_task(self):
        engine=self.engine();questions=[];tasks=[]
        engine.screen_question_requested.connect(lambda call_id,question:questions.append((call_id,question)))
        engine.task_requested.connect(lambda *args:tasks.append(args))
        engine._handle_event(dict(type='response.function_call_arguments.done',response_id='r-screen',
            call_id='screen-call',name='read_screen',arguments=json.dumps(dict(question='画面里是什么颜色？'))))
        self.assertEqual(questions,[('screen-call','画面里是什么颜色？')]);self.assertFalse(tasks)

    def test_manual_screen_stop_is_reflected_in_next_session_update(self):
        engine=self.engine();engine._ws=object();engine._screen_configured=True
        engine.screen_context_provider=lambda:dict(active=False,fresh=False,context='')
        with patch.object(engine,'_send') as send:
            engine._sync_screen_context(force=True)
        self.assertIn('"active": false',send.call_args.args[0]['session']['instructions'])

    def test_reconnect_clears_stuck_notice_state(self):
        engine=self.engine()
        engine._notice_active=True;engine._notice_responses.append('r1');engine._user_speaking=True
        engine._invalidate_tasks()
        self.assertFalse(engine._notice_active)
        self.assertEqual(len(engine._notice_responses),0)
        self.assertFalse(engine._user_speaking)

    def test_stale_notice_does_not_reject_later_tool_call(self):
        engine=self.engine()
        engine._notice_active=True;engine._response_id=None
        engine._accept_call(dict(name='read_web',call_id='c1',arguments='{}'))
        queued=engine._commands.get_nowait()
        self.assertEqual(queued[0],'task_result')
        self.assertTrue(queued[2].get('ok'))

    def test_fast_command_success_without_waiter_is_spoken_once(self):
        engine=self.engine()
        engine._fast_jobs['job1']=dict(waiters=[],result=None)
        engine.complete_fast_command('job1',dict(ok=True,message='已请求浏览器打开新窗口'))
        notices=[]
        while True:
            try:item=engine._commands.get_nowait()
            except Exception:break
            if item[0]=='fast_notice':notices.append(item)
        self.assertEqual(len(notices),1)
        self.assertIn('浏览器',notices[0][2])

    @staticmethod
    def call_event(call_id='c1', response_id='r1'):
        return dict(type='response.function_call_arguments.done', response_id=response_id,
                    call_id=call_id, name='ask_deepseek', arguments=json.dumps({'request': '检查当前记事本窗口状态'}))

    def test_qwen_voice_config_preserved_with_single_delegate_tool(self):
        engine = self.engine()
        settings = engine._session_settings()
        self.assertEqual(engine._cfg['model'], 'qwen-audio-3.1-realtime-plus')
        self.assertEqual(settings['voice'], DEFAULTS['voice'])
        self.assertEqual(settings['modalities'], ['text', 'audio'])
        self.assertEqual(settings['turn_detection']['type'], 'server_vad')
        self.assertEqual(settings['tools'][0]['name'], 'ask_deepseek')
        self.assertEqual(settings['tool_choice'], 'auto')

    def test_stop_command_is_local_cancels_audio_and_deduplicates(self):
        engine=self.engine();commands=[];engine.fast_command.connect(commands.append)
        engine._handle_event(dict(type='response.created',response=dict(id='r0')))
        with patch.object(engine,'_send') as send,patch.object(engine,'_record_usage'):
            engine._handle_event(dict(type='conversation.item.input_audio_transcription.completed',transcript='停止对话'))
            event=dict(type='response.function_call_arguments.done',response_id='r1',call_id='fast',
                       name='ask_deepseek',arguments=json.dumps({'request':'停止对话'}))
            engine._handle_event(event)
        self.assertEqual([c['action'] for c in commands],['stop_call'])
        self.assertTrue(any(c.args[0].get('type')=='response.cancel' for c in send.call_args_list))

    def test_fast_tool_waits_for_real_result_and_deduplicates_polite_transcript(self):
        engine=self.engine();commands=[];engine.fast_command.connect(commands.append)
        event=dict(type='response.function_call_arguments.done',response_id='r1',call_id='browser',
            name='ask_deepseek',arguments=json.dumps({'request':'打开浏览器'}))
        with patch.object(engine,'resolve_task') as resolve:
            engine._handle_event(event)
            resolve.assert_not_called()
            engine._handle_event(dict(type='conversation.item.input_audio_transcription.completed',transcript='请帮我打开浏览器'))
            self.assertEqual(len(commands),1)
            engine.complete_fast_command(commands[0]['fast_id'],dict(ok=False,error='没有默认浏览器'))
            self.assertEqual(resolve.call_args.args[0],'browser')
            result=resolve.call_args.args[1]
            self.assertFalse(result['ok']);self.assertFalse(result['silent'])
            self.assertIn('没有默认浏览器',result['answer'])

    def test_successful_transcript_execution_is_shared_with_later_tool(self):
        engine=self.engine();commands=[];engine.fast_command.connect(commands.append)
        engine._handle_event(dict(type='conversation.item.input_audio_transcription.completed',transcript='帮我打开浏览器'))
        engine.complete_fast_command(commands[0]['fast_id'],dict(ok=True,message='已请求默认浏览器打开'))
        with patch.object(engine,'resolve_task') as resolve:
            engine._handle_event(dict(type='response.function_call_arguments.done',response_id='r1',call_id='browser',
                name='ask_deepseek',arguments=json.dumps({'request':'打开默认浏览器'})))
            self.assertEqual(len(commands),1)
            self.assertTrue(resolve.call_args.args[1]['ok']);self.assertTrue(resolve.call_args.args[1]['silent'])

    def test_tool_deduplicates_across_all_native_events(self):
        engine = self.engine()
        calls = []
        engine.task_requested.connect(lambda *args: calls.append(args))
        event = self.call_event()
        engine._handle_event(event)
        item = dict(type='function_call', call_id='c1', name='ask_deepseek', arguments=event['arguments'])
        engine._handle_event(dict(type='response.output_item.done', response_id='r1', item=item))
        with patch.object(engine, '_record_usage'):
            engine._handle_event(dict(type='response.done', response=dict(id='r1', output=[item])))
        engine._flush_pending_requests(now=10**12)
        self.assertEqual(calls, [('c1', '检查当前记事本窗口状态')])

    def test_verbatim_asr_overrides_model_paraphrase_before_long_task_starts(self):
        engine=self.engine();commands=[];calls=[]
        engine.fast_command.connect(commands.append);engine.task_requested.connect(lambda *args:calls.append(args))
        engine._handle_event(dict(type='response.function_call_arguments.done',response_id='r1',call_id='c1',
            name='ask_deepseek',arguments=json.dumps({'request':'用户反馈浏览器没有打开，请排查并修复桌宠项目'})))
        self.assertFalse(calls)
        engine._handle_event(dict(type='conversation.item.input_audio_transcription.completed',transcript='打开浏览器'))
        self.assertFalse(calls)
        self.assertEqual(len(commands),1)
        self.assertFalse(engine._pending_requests)

    def test_vague_testing_phrase_does_not_start_source_code_investigation(self):
        engine=self.engine();calls=[];engine.task_requested.connect(lambda *args:calls.append(args))
        engine._handle_event(dict(type='response.function_call_arguments.done',response_id='r1',call_id='c1',
            name='ask_deepseek',arguments=json.dumps({'request':'请确认具体要测试什么，并读取项目源码'})))
        with patch.object(engine,'resolve_task') as result:
            engine._handle_event(dict(type='conversation.item.input_audio_transcription.completed',transcript='现在进行测试'))
            self.assertFalse(calls)
            self.assertIn('请直接说',result.call_args.args[1]['answer'])

    def test_transcription_does_not_execute_a_task(self):
        engine = self.engine()
        calls = []
        engine.task_requested.connect(lambda *args: calls.append(args))
        engine._handle_event(dict(type='conversation.item.input_audio_transcription.completed', transcript='打开记事本'))
        self.assertEqual(calls, [])

    def test_deepseek_result_returns_as_function_output_then_qwen_audio_response(self):
        engine = self.engine()
        engine._handle_event(dict(type='response.created', response={'id': 'r1'}))
        engine._handle_event(self.call_event())
        self.assertTrue(engine.resolve_task('c1', {'ok': True, 'answer': '已提交启动请求'}))
        with patch.object(engine, '_send') as send, patch.object(engine, '_record_usage'):
            engine._process_command(engine._commands.get_nowait())
            first = send.call_args_list[0].args[0]
            self.assertEqual(first['item']['type'], 'function_call_output')
            self.assertEqual(first['item']['call_id'], 'c1')
            self.assertEqual(json.loads(first['item']['output'])['answer'], '已提交启动请求')
            self.assertEqual(send.call_count, 1, 'Must not start a response while parent is generating')
            engine._handle_event(dict(type='response.done', response={'id': 'r1'}))
            engine._process_command(None)
            self.assertEqual(send.call_args.args[0]['type'], 'response.create')
            engine._process_command(None)
            self.assertEqual(send.call_count, 2, 'Must not duplicate follow-up generation')

    def test_interrupt_discards_late_task_result(self):
        engine = self.engine()
        cancelled = []
        engine.tasks_cancelled.connect(lambda: cancelled.append(True))
        engine._handle_event(self.call_event())
        engine.interrupt()
        self.assertEqual(cancelled, [True])
        self.assertFalse(engine._tasks)
        engine.resolve_task('c1', {'ok': True, 'answer': '迟到结果'})
        with patch.object(engine, '_send') as send:
            while not engine._commands.empty():
                engine._process_command(engine._commands.get_nowait())
            values = [c.args[0] for c in send.call_args_list]
            self.assertFalse(any(v['type'] == 'response.create' for v in values))
            self.assertFalse(any('迟到结果' in json.dumps(v, ensure_ascii=False) for v in values))

    def test_speech_interrupt_and_disconnect_cancel_pending_tasks(self):
        engine = self.engine()
        cancelled = []
        engine.tasks_cancelled.connect(lambda: cancelled.append(True))
        engine._handle_event(self.call_event())
        engine._handle_event(dict(type='input_audio_buffer.speech_started'))
        self.assertEqual(cancelled, [True])
        engine._handle_event(self.call_event('c2', 'r2'))
        with patch.object(RealtimeVoice, '_connection', side_effect=ConnectionError('test')):
            with self.assertRaises(ConnectionError):
                engine._connection()
        self.assertEqual(len(cancelled), 2)
        self.assertFalse(engine._tasks)

    def test_stop_blocks_new_requests_and_late_results(self):
        engine = self.engine()
        engine.stop()
        calls = []
        engine.task_requested.connect(lambda *args: calls.append(args))
        engine._handle_event(self.call_event())
        self.assertFalse(calls)
        self.assertFalse(engine.resolve_task('c1', {'answer': 'late'}))


if __name__ == '__main__':
    unittest.main()
