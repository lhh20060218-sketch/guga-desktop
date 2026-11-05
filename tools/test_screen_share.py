"""Screen sharing, memory initiative and visible bubble regressions."""
import os,tempfile,time,unittest
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock,Mock,patch
from PIL import Image

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from launcher import _prepare_qt
_prepare_qt()
from PyQt5.QtWidgets import QApplication,QWidget
from core.fast_commands import match
from core.screen_share import ScreenShareController
from core.proactive_conversation import ProactiveConversation
from core.screen_visual import describe_frame

APP=QApplication.instance() or QApplication([])


def fake_settings(values=None):
    values=values or {};store=Mock();store.value.side_effect=lambda key,default=None,type=None:values.get(key,default)
    return SimpleNamespace(_s=store)


def fake_panel(memory,voice_active=False):
    voice=SimpleNamespace(active=voice_active,_playing=False,_generating=False,_user_speaking=False,
        _last_activity=time.monotonic()-300,notify_proactive=MagicMock(return_value=True))
    pet=SimpleNamespace(_config=fake_settings({'screen/share_fps':3,'screen/context_seconds':2.5}),_say_with_expression=MagicMock())
    return SimpleNamespace(memory=memory,voice=voice,voice_active=voice_active,busy=False,
        runtime=SimpleNamespace(music=SimpleNamespace(playing=False),dsh=None),active_profile=memory.profile('001'),
        pet=pet,active_agent_id='001',active_id='c',store=Mock(),_last_user_activity=time.monotonic()-300,
        _show_active_bubble=MagicMock())


class ScreenShareTests(unittest.TestCase):
    def setUp(self):
        from core.agent_memory import AgentMemoryStore
        self.tmp=tempfile.TemporaryDirectory();self.memory=AgentMemoryStore(Path(self.tmp.name)/'memory.sqlite3')
        self.panel=fake_panel(self.memory)
        access=SimpleNamespace(enabled=True)
        self.access=patch('core.screen_share.DesktopAccess',return_value=access).start();self.addCleanup(patch.stopall)

    def tearDown(self):self.tmp.cleanup()

    def test_spoken_share_commands_are_distinct_from_screenshots(self):
        self.assertEqual(match('共享屏幕')['action'],'screen_share_start')
        self.assertEqual(match('开始共享一下屏幕')['action'],'screen_share_start')
        self.assertEqual(match('共享屏幕每秒五帧')['fps'],5)
        self.assertEqual(match('停止分享屏幕')['action'],'screen_share_stop')
        self.assertFalse(match('截一张屏幕截图')['matched'])

    def test_real_bounded_capture_stays_in_memory_and_supports_two_to_five_fps(self):
        controller=ScreenShareController(self.panel);frames=[];contexts=[]
        controller.frame_ready.connect(frames.append);controller.context_ready.connect(contexts.append)
        with patch('core.screen_visual.describe_frame',return_value=dict(ok=True,text='桌面上打开了记事本，输入区是当前焦点。',model='fixture')):
            result=controller.start(2,'test');deadline=time.monotonic()+3
            while time.monotonic()<deadline and (len(frames)<3 or not contexts):APP.processEvents();time.sleep(.03)
            state=controller.status();controller.stop()
        self.assertTrue(result['started']);self.assertGreaterEqual(len(frames),3)
        self.assertTrue(state['active']);self.assertEqual(state['storage'],'memory_only')
        self.assertGreaterEqual(state['sequence'],3);self.assertTrue(state['context']);self.assertEqual(state['fps'],2)
        self.assertGreater(frames[0]['size']['width'],0)
        with self.assertRaises(ValueError):controller.start(6)

    def test_stale_context_is_not_presented_as_current(self):
        controller=ScreenShareController(self.panel)
        controller._active=True;controller._context='旧画面';controller._context_at=time.monotonic()-30;controller._frame_uri='data:image/jpeg;base64,AA=='
        state=controller.context(max_age=12)
        self.assertFalse(state['fresh']);self.assertIn('旧资料',state['context'])

    def test_foreground_window_change_invalidates_old_visual_context(self):
        controller=ScreenShareController(self.panel)
        controller._active=True;controller._context='旧窗口内容';controller._context_at=time.monotonic()
        controller._foreground=dict(hwnd=2,title='新窗口');controller._context_foreground=dict(hwnd=1,title='旧窗口')
        state=controller.assist_context(max_age=12)
        self.assertFalse(state['fresh']);self.assertFalse(state['context_matches_foreground'])
        self.assertIn('当前前台已经改变',state['context'])

    def test_rate_limit_uses_ocr_fallback_and_backoff(self):
        controller=ScreenShareController(self.panel)
        controller._frame_uri='data:image/jpeg;base64,'+__import__('base64').b64encode(b'fake').decode('ascii')
        with patch('core.screen_visual.describe_frame',return_value=dict(ok=False,code='http',http_status=429,error='限流')), \
             patch.object(controller,'_ocr_fallback',return_value=dict(ok=True,text='本机文字识别：SCREEN_SHARE_PROBE')):
            controller._generation=1;controller._frame_uri='data:image/jpeg;base64,'+__import__('base64').b64encode(b'fake').decode('ascii')
            controller._analyze(controller._frame_uri,1)
        state=controller.status();self.assertTrue(state['context']);self.assertEqual(state['ocr_count'],1)
        self.assertGreater(state['analysis_retry_after_seconds'],0)

    def test_primary_vision_failure_uses_configured_chat_vision_once(self):
        with patch('core.screen_visual._call_primary',return_value=dict(ok=False,code='http',http_status=429,error='limited')) as primary, \
             patch('core.screen_visual._call_chat_fallback',return_value=dict(ok=True,text='当前记事本显示测试文本。',source='chat')) as fallback:
            result=describe_frame('data:image/jpeg;base64,AA==')
        self.assertTrue(result['ok']);self.assertEqual(result['source'],'chat')
        self.assertEqual(result['primary_error']['http_status'],429);primary.assert_called_once();fallback.assert_called_once()

    def test_usage_is_aggregated_and_visual_calls_are_rate_budgeted(self):
        controller=ScreenShareController(self.panel)
        controller._add_usage(dict(prompt_tokens=475,completion_tokens=66,total_tokens=541))
        self.assertEqual(controller.status()['usage']['total_tokens'],541)
        now=time.monotonic();controller._analysis_request_times.extend([now]*controller.max_calls_per_minute)
        with patch('core.screen_share.threading.Thread') as thread:
            controller._start_analysis('data:image/jpeg;base64,AA==',controller._generation)
        thread.assert_not_called();self.assertGreater(controller.status()['analysis_retry_after_seconds'],0)

    def test_transient_capture_error_recovers_without_stopping_share(self):
        controller=ScreenShareController(self.panel);controller.fps=5
        controller._active=True;controller._generation=1;controller._stop.clear()
        frame=Image.new('RGB',(320,200),'white')
        controller.frame_ready.connect(lambda event:controller._stop.set())
        with patch('core.screen_share.ImageGrab.grab',side_effect=[OSError('transient'),frame]) as grab, \
             patch.object(controller,'_start_analysis') as analysis:
            worker=threading.Thread(target=controller._capture_loop,args=(1,));worker.start();worker.join(2)
        self.assertFalse(worker.is_alive());self.assertGreaterEqual(grab.call_count,2)
        state=controller.status();self.assertGreaterEqual(state['sequence'],1);self.assertEqual(state['capture_recoveries'],1)
        analysis.assert_called_once()
        controller._active=False

    def test_stop_discards_last_frame_and_context(self):
        controller=ScreenShareController(self.panel)
        controller._frame_image=Image.new('RGB',(320,200));controller._context='private test content'
        controller._context_at=time.monotonic();controller.stop()
        self.assertFalse(controller.snapshot()['ok']);self.assertEqual(controller.context()['context'],'')

    def test_static_screen_keeps_context_but_new_change_invalidates_it(self):
        controller=ScreenShareController(self.panel);controller._active=True
        now=time.monotonic();controller._context='静止测试页';controller._context_at=now-40
        controller._context_frame_at=now-41;controller._last_change=now-42;controller._last_at=now
        self.assertTrue(controller.context()['fresh']);self.assertTrue(controller.context()['unchanged_since_analysis'])
        controller._last_change=now-1
        self.assertFalse(controller.context()['fresh'])
        controller._context_at=now
        self.assertFalse(controller.context()['fresh']) # even a newly completed analysis may describe an older frame

    def test_failed_static_frame_retries_have_a_finite_budget(self):
        controller=ScreenShareController(self.panel)
        with patch('core.screen_visual.describe_frame',return_value=dict(ok=False,code='fixture')), \
             patch.object(controller,'_ocr_fallback',return_value=dict(ok=False)):
            for index in range(3):
                controller._analysis_pending=False
                controller._analyze('data:image/jpeg;base64,AA==',controller._generation)
                self.assertEqual(controller._analysis_pending,index<2)

    def test_unexpected_vision_exception_does_not_wedge_analysis(self):
        controller=ScreenShareController(self.panel);controller._analysis_active=True
        with patch('core.screen_visual.describe_frame',side_effect=RuntimeError('fixture')), \
             patch.object(controller,'_ocr_fallback',return_value=dict(ok=False)):
            controller._analyze('data:image/jpeg;base64,AA==',controller._generation)
        state=controller.status();self.assertFalse(state['analysis_active']);self.assertEqual(state['last_analysis']['code'],'vision_exception')


class BubbleTests(unittest.TestCase):
    def test_visible_bubble_keeps_full_medium_response_and_is_wider(self):
        from ui.speech_bubble import PetSpeechBubble
        pet=QWidget();pet.resize(100,100);pet.move(300,200)
        bubble=PetSpeechBubble(pet)
        text='这是一段需要在桌面上直接读完的完整说明。'*12
        bubble.show_text(text,'c')
        self.assertEqual(bubble.full_text,text);self.assertEqual(bubble.text.text(),text)
        self.assertGreaterEqual(bubble.width(),380);self.assertLessEqual(bubble.width(),620)
        bubble.hide()


class ProactiveTests(unittest.TestCase):
    def setUp(self):
        from core.agent_memory import AgentMemoryStore
        self.tmp=tempfile.TemporaryDirectory();self.memory=AgentMemoryStore(Path(self.tmp.name)/'memory.sqlite3')
        self.memory.add_dialogue('001','user','我最近在整理 AI 相关的学习资料。')
        self.panel=fake_panel(self.memory,voice_active=False)
        self.proactive=ProactiveConversation(self.panel,self.memory);self.proactive.started_at=time.monotonic()-300

    def tearDown(self):self.proactive.stop();self.tmp.cleanup()

    def test_offline_memory_initiative_uses_memory_and_speaks_when_idle(self):
        with patch.object(self.proactive,'_compose_offline') as compose,patch('core.proactive_conversation.threading.Thread') as thread:
            result=self.proactive.tick()
        self.assertEqual(result['mode'],'offline');compose.assert_not_called()
        args=thread.call_args.kwargs['args'];self.assertIn('AI 相关的学习资料',args[1])
        self.proactive._deliver_offline(result['event'],'你那些 AI 资料整理得还顺利吗？')
        self.panel._show_active_bubble.assert_called_once()
        self.panel.pet._say_with_expression.assert_called_once()
        self.panel.store.append.assert_called_once()

    def test_busy_task_suppresses_both_call_and_offline_initiative(self):
        self.panel.busy=True;self.assertIsNone(self.proactive.tick())
        self.panel.busy=False;self.panel.voice_active=True;self.panel.voice.active=True
        self.panel.voice._playing=True;self.assertIsNone(self.proactive.tick())

    def test_timer_is_idempotent_and_runs_without_voice_call(self):
        first=self.proactive.start();second=self.proactive.start()
        self.assertTrue(first['active']);self.assertTrue(second['active']);self.assertFalse(second['call_active'])
