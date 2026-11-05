"""Perception evidence, foreground isolation and nonblocking local screen reads."""
import os
import threading
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from launcher import _prepare_qt
_prepare_qt()
from PyQt5.QtWidgets import QApplication
APP=QApplication.instance() or QApplication([])
from core.local_perception import LocalPerception
from core.screen_share import ScreenShareController

WINDOW=dict(hwnd=42,pid=7,title='自有测试页',process='msedge.exe')
VALUE=dict(elements=[dict(name='当前页面文字',type='Text'),dict(name='今天想看什么',type='Edit',value='测试')],
    elapsed_ms=15,source='windows_uia',truncated=False)


class LocalPerceptionTests(unittest.TestCase):
    def reader(self,**kw):
        service=Mock();service.perceive.return_value=VALUE
        reader=LocalPerception(service=service,foreground_provider=lambda:WINDOW,**kw)
        self.addCleanup(reader.close);return reader

    def test_request_does_not_block_capture_and_reading_cannot_reuse_old_window(self):
        reader=self.reader();started=threading.Event();release=threading.Event()
        def slow(hwnd):started.set();release.wait(1);return VALUE
        reader.service.perceive.side_effect=slow
        try:
            before=time.monotonic();reader.request(WINDOW)
            self.assertLess(time.monotonic()-before,.1);self.assertTrue(started.wait(1))
            self.assertFalse(reader.context(WINDOW)['fresh'])
            reader.request(dict(hwnd=99,pid=8));release.set();reader.thread.join(1)
            self.assertFalse(reader.context(WINDOW)['fresh'])
        finally:release.set()

    def test_text_and_controls_are_local_evidence_but_not_visual_facts(self):
        reader=self.reader();reader.request(WINDOW);reader.thread.join(1)
        value=reader.context(WINDOW)
        self.assertTrue(value['fresh']);self.assertTrue(value['local_only']);self.assertFalse(value['visual_content'])
        self.assertIn('今天想看什么',value['context']);self.assertEqual(value['elements'][0]['type'],'Edit')
        other=reader.context(dict(hwnd=99,pid=8))
        self.assertFalse(other['fresh']);self.assertNotIn('context',other);self.assertNotIn('elements',other)

    def test_expired_controls_are_not_returned_as_current(self):
        reader=self.reader();reader.request(WINDOW);reader.thread.join(1);reader.at=time.monotonic()-3
        self.assertFalse(reader.context(WINDOW)['fresh']);self.assertNotIn('context',reader.context(WINDOW))

    def test_close_clears_content_and_closes_its_provider(self):
        reader=self.reader();reader.request(WINDOW);reader.thread.join(1);reader.close()
        self.assertFalse(reader.context(WINDOW)['fresh']);self.assertFalse(reader.value);reader.service.close.assert_called()

    def test_failed_provider_backs_off_instead_of_restarting_each_capture(self):
        reader=self.reader();reader.service.perceive.side_effect=RuntimeError('fixture unavailable')
        reader.request(WINDOW);reader.thread.join(1);reader.attempted=0.
        for _ in range(5):reader.request(WINDOW)
        self.assertEqual(reader.service.perceive.call_count,1);self.assertFalse(reader.context(WINDOW)['fresh'])

    def test_closing_while_provider_is_busy_does_not_wait_on_its_lock(self):
        reader=self.reader();started=threading.Event();release=threading.Event();closed=threading.Event()
        def slow(hwnd):started.set();release.wait(1);return VALUE
        def close():release.wait(1);closed.set()
        reader.service.perceive.side_effect=slow;reader.service.close.side_effect=close
        try:
            reader.request(WINDOW);self.assertTrue(started.wait(1));before=time.monotonic();reader.close()
            self.assertLess(time.monotonic()-before,.1);self.assertFalse(reader.context(WINDOW)['fresh'])
        finally:release.set();reader.thread.join(1);self.assertTrue(closed.wait(1))

    def test_fresh_controls_survive_unrelated_animation_expiring_cloud_summary(self):
        controller=ScreenShareController(SimpleNamespace());controller._active=True;controller._foreground=WINDOW
        reader=self.reader();reader.request(WINDOW);reader.thread.join(1);controller._local_perception=reader
        with patch.object(controller,'context',return_value=dict(active=True,fresh=False,context='旧画面已经变化',foreground=WINDOW)):
            value=controller.assist_context()
        self.assertTrue(value['fresh']);self.assertEqual(value['source'],'windows_uia');self.assertFalse(value['visual_content'])
        self.assertIn('今天想看什么',value['context'])

    def test_routine_actions_disable_deep_thinking_but_engineering_keeps_it(self):
        from core.self_agent import SelfAgent
        agent=SelfAgent(Mock(),config=dict(base_url='https://fixture.invalid',api_key='offline',model='fixture'))
        response=Mock(status_code=200);response.json.return_value=dict(choices=[dict(message=dict(content='received'))])
        for routine in (True,False):
            agent._routine_request=routine
            with patch('core.self_agent.requests.post',return_value=response) as request:
                agent._request([], 'fixture')
            self.assertEqual(request.call_args.kwargs['json']['thinking']['type'],'disabled' if routine else 'enabled')

    def test_short_desktop_task_cannot_repeat_twenty_seven_model_tool_rounds(self):
        import json
        from core.self_agent import SelfAgent
        from core.agent_task import TaskJournal
        agent=SelfAgent(Mock(),config=dict(api_key='offline'));results=[];agent.completed.connect(results.append)
        index=[0]
        def request(*args,**kw):
            index[0]+=1
            return dict(role='assistant',tool_calls=[dict(id='read-'+str(index[0]),type='function',
                function=dict(name='computer',arguments=json.dumps(dict(action='windows',query=str(index[0])))))])
        with tempfile.TemporaryDirectory() as folder,patch.object(agent,'_request',side_effect=request), \
             patch.object(agent.computer,'execute',return_value=dict(windows=[])) as execute:
            agent.journal=TaskJournal(folder)
            agent._run('fixture',[],'看看当前网页的控件',threading.Event(),handoff=dict(_route=dict(category='local_task')))
        self.assertEqual(index[0],4);self.assertEqual(execute.call_count,4)
        self.assertFalse(results[0]['ok']);self.assertIn('4轮',results[0]['error'])

    def test_browser_tool_does_not_hide_the_recordable_companion(self):
        import json
        from core.self_agent import SelfAgent
        from core.agent_task import TaskJournal
        agent=SelfAgent(Mock(),config=dict(api_key='offline'))
        call=dict(role='assistant',tool_calls=[dict(id='status',type='function',
            function=dict(name='browser',arguments=json.dumps(dict(action='session_status'))))])
        with tempfile.TemporaryDirectory() as folder,patch.object(agent,'_request',side_effect=[call,dict(role='assistant',content='normal|none|已检查状态')]), \
             patch('core.browser_agent.execute',return_value=dict(ok=True,result=dict(running=False))) as execute, \
             patch.object(agent,'_desktop_capability') as hide:
            agent.journal=TaskJournal(folder);agent._run('fixture',[],'检查浏览器会话状态',threading.Event())
        hide.assert_not_called();execute.assert_called_once()


if __name__=='__main__':unittest.main()
