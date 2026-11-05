"""Foreground response, perception facts and Qt responsiveness regression checks."""
import base64
import json
import os
import queue
from pathlib import Path
import threading
import time
import unittest
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from launcher import _prepare_qt
_prepare_qt()
from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QApplication
from core.realtime_voice import DEFAULTS,VoiceCommandQueue,RealtimeVoice,session_settings
from core.realtime_agent import AgentRealtimeVoice
from core.self_agent import ToolBridge
APP=QApplication.instance() or QApplication([])


class ResponsiveTests(unittest.TestCase):
    def test_results_overtake_narration_and_have_reserved_capacity(self):
        q=VoiceCommandQueue()
        for i in range(48):q.put_nowait(('bg_notice',str(i)))
        with self.assertRaises(queue.Full):q.put_nowait(('bg_notice','overflow'))
        q.put_nowait(('task_result','user',dict(answer='收到')))
        self.assertEqual(q.get_nowait()[0],'task_result')

    def test_foreground_result_speaks_while_an_unrelated_tool_is_pending(self):
        voice=AgentRealtimeVoice();voice._tasks={'slow':'r-old','screen':'r-current'}
        voice.resolve_task('screen',dict(ok=True,observation='蓝色圆形与黄色方形'))
        with patch.object(voice,'_send') as send:
            voice._process_command(voice._commands.get_nowait())
        self.assertEqual(voice._tasks,{'slow':'r-old'})
        self.assertEqual(send.call_args.args[0],dict(type='response.create',response=dict(modalities=['audio','text'])))
        result=json.loads(send.call_args_list[0].args[0]['item']['output'])
        self.assertIn('observation',result);self.assertNotIn('answer',result)

    def test_finished_pcm_does_not_keep_microphone_gated_during_tool_wait(self):
        voice=RealtimeVoice();voice._cfg=dict(DEFAULTS);voice._playing=True;voice._generating=True
        out=bytearray(8);voice._playback(out,4,None,None)
        self.assertFalse(voice._playing)
        voice._echo_until=0;voice._capture(b'\x03\x00'*4,4,None,None)
        self.assertEqual(voice._input.get_nowait(),b'\x03\x00'*4)

    def test_fast_vad_and_optional_semantic_turn_are_distinct(self):
        fast=session_settings(dict(DEFAULTS,silence_duration_ms=1000))
        self.assertEqual(fast['turn_detection'],dict(type='server_vad',threshold=.5,silence_duration_ms=600))
        semantic=session_settings(dict(DEFAULTS,turn_mode='smart_turn_v2'))
        self.assertEqual(semantic['turn_detection'],dict(type='smart_turn_v2'))

    def test_consecutive_background_speech_does_not_flood_live_history(self):
        settings=session_settings(DEFAULTS,[('饲养员','我的问题'),('咕嘎','旧后台播报'),('咕嘎','最新后台状态'),('饲养员','现在回答我')])
        self.assertNotIn('旧后台播报',settings['instructions'])
        self.assertIn('我的问题',settings['instructions']);self.assertIn('最新后台状态',settings['instructions'])

    def test_current_task_is_available_to_speaking_agent_without_querying_executor(self):
        voice=AgentRealtimeVoice();voice._cfg=dict(DEFAULTS)
        voice.set_task_context(dict(running=True,kind='browser',goal='填写测试表单',summary='第2步，等待网页返回'))
        settings=voice._session_settings()
        self.assertIn('填写测试表单',settings['instructions']);self.assertIn('第2步',settings['instructions'])

    def test_misrouted_screen_question_stays_out_of_execution_agent(self):
        voice=AgentRealtimeVoice();voice.screen_context_provider=lambda:dict(active=True,fresh=True,context='蓝色圆形')
        reads=[];tasks=[]
        voice.screen_question_requested.connect(lambda *args:reads.append(args))
        voice.task_requested.connect(lambda *args:tasks.append(args))
        voice._handoff_request('screen','你现在能看到我的屏幕吗？')
        self.assertEqual(reads,[('screen','你现在能看到我的屏幕吗？')]);self.assertFalse(tasks)
        voice._handoff_request('action','请帮我点击屏幕里的提交按钮')
        self.assertEqual(len(tasks),1)

    def test_application_launch_does_not_hold_qt_event_loop(self):
        release=threading.Event();started=threading.Event();tick=[]
        def slow(name,args):started.set();release.wait(2);return dict(ok=True)
        bridge=ToolBridge(slow)
        request=dict(name='applications',arguments=dict(action='open',name='fixture'),cancel=threading.Event(),ready=threading.Event())
        try:
            before=time.monotonic();bridge._execute(request)
            self.assertLess(time.monotonic()-before,.1)
            self.assertTrue(started.wait(1));QTimer.singleShot(0,lambda:tick.append(True));APP.processEvents()
            self.assertTrue(tick);self.assertFalse(request['ready'].is_set())
        finally:release.set();request['ready'].wait(2)

    def test_first_audio_latency_is_reported_without_transcript_content(self):
        voice=AgentRealtimeVoice();voice._speech_stopped_at=time.monotonic()-.7;voice._tool_result_at=time.monotonic()-.2
        voice._first_audio_pending=True
        voice._handle_event(dict(type='response.audio.delta',delta=base64.b64encode(b'\0\0').decode()))
        status=voice.interaction_status();self.assertGreaterEqual(status['first_audio_after_speech_ms'],690)
        self.assertLess(status['first_audio_after_tool_ms'],350);self.assertNotIn('transcript',status)


if __name__=='__main__':unittest.main()
