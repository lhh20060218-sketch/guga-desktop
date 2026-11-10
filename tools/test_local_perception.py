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
        import json
        from core.self_agent import SelfAgent
        agent=SelfAgent(Mock(),config=dict(base_url='https://fixture.invalid',api_key='offline',model='fixture'))
        response=Mock(status_code=200,headers={},text=json.dumps(dict(choices=[dict(message=dict(content='received'))])))
        for routine in (True,False):
            agent._routine_request=routine
            # 模型请求统一走 core.model_endpoint.post（保留 POST 的重定向/代理兜底），
            # 这里必须拦真实入口，否则会打到 fixture.invalid。
            with patch('core.model_endpoint.post',return_value=response) as request:
                agent._request([], 'fixture')
            self.assertEqual(request.call_args.kwargs['json']['thinking']['type'],'disabled' if routine else 'enabled')

    def test_short_composite_task_keeps_full_budget_and_planning_instruction(self):
        import json
        from core.self_agent import SelfAgent
        from core.agent_task import TaskJournal
        agent=SelfAgent(Mock(),config=dict(api_key='offline',task_budget_seconds=40))
        results=[];agent.completed.connect(results.append);seen=[]
        call=dict(role='assistant',tool_calls=[dict(id='w',type='function',
            function=dict(name='computer',arguments=json.dumps(dict(action='windows'))))])
        def request(*args,**kw):
            seen.append([m.get('content','') for m in args[0] if m.get('role')=='system'])
            return call if len(seen)==1 else dict(role='assistant',content='完成|none|已按步骤执行')
        with tempfile.TemporaryDirectory() as folder,patch.object(agent,'_request',side_effect=request), \
             patch.object(agent.computer,'execute',return_value=dict(windows=[])):
            agent.journal=TaskJournal(folder)
            agent._run('fixture',[],'打开浏览器搜索资料，然后发到微信给小军',threading.Event(),
                handoff=dict(_route=dict(category='multi_step')))
        self.assertFalse(agent._routine_request)
        self.assertTrue(any('多步骤复合任务' in text for text in seen[0]))



    def test_composite_chain_runs_past_single_step_cap_and_adapts_after_failure(self):
        import json
        from core.self_agent import SelfAgent
        from core.agent_task import TaskJournal
        agent=SelfAgent(Mock(),config=dict(api_key='offline'))
        results=[];agent.completed.connect(results.append);rounds=[]
        def call(name,arguments):
            return dict(role='assistant',tool_calls=[dict(id=name+str(len(rounds)),type='function',
                function=dict(name=name,arguments=json.dumps(arguments)))])
        def request(*args,**kw):
            rounds.append(1);previous=[m for m in args[0] if m.get('role')=='tool']
            if not previous:return call('task_plan',dict(steps=['查看窗口','聚焦目标','复查结果']))
            last=json.loads(previous[-1]['content'])
            if len(previous)==1:return call('computer',dict(action='focus',hwnd=1))
            if len(previous)==2:
                self.assertFalse(last.get('ok'))
                return call('computer',dict(action='windows',query='记事本'))
            if len(previous)==3:return call('computer',dict(action='observe',hwnd=2))
            return dict(role='assistant',content='完成|none|原定聚焦失败，已改为核对窗口后结束')
        def execute(arguments,cancel):
            if arguments.get('action')=='focus':raise RuntimeError('窗口已关闭')
            if arguments.get('action')=='observe':return dict(observation_id='obs-1')
            return dict(windows=[dict(hwnd=2,title='记事本')])
        with tempfile.TemporaryDirectory() as folder,patch.object(agent,'_request',side_effect=request), \
             patch.object(agent.computer,'execute',side_effect=execute):
            agent.journal=TaskJournal(folder)
            agent._run('fixture',[],'打开记事本，然后查看窗口，最后确认结果',threading.Event(),
                handoff=dict(_route=dict(category='multi_step')))
        self.assertEqual(len(rounds),5)
        self.assertTrue(results[0]['ok'])

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
        # 例行请求步骤预算从 4 提到 12（实测 qwen3-vl-plus 等模型首轮可能只回推理/文字，
        # 需要再追一轮工具调用+回执），仍远低于复合任务的 80 轮。
        self.assertEqual(index[0],12);self.assertEqual(execute.call_count,12)
        self.assertFalse(results[0]['ok']);self.assertIn('12轮',results[0]['error'])

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

    def test_identical_tool_call_loop_pauses_instead_of_spinning(self):
        import json
        from core.self_agent import SelfAgent
        from core.agent_task import TaskJournal
        agent=SelfAgent(Mock(),config=dict(api_key='offline'));results=[];agent.completed.connect(results.append)
        call=dict(role='assistant',tool_calls=[dict(id='obs',type='function',
            function=dict(name='computer',arguments=json.dumps(dict(action='observe',hwnd=7))))])
        with tempfile.TemporaryDirectory() as folder,patch.object(agent,'_request',return_value=call), \
             patch.object(agent.computer,'execute',return_value=dict(observation_id='obs-1')) as execute:
            agent.journal=TaskJournal(folder)
            agent._run('fixture',[],'打开记事本，然后查看窗口，最后确认结果',threading.Event(),
                handoff=dict(_route=dict(category='multi_step')))
        self.assertFalse(results[0]['ok'])
        self.assertIn('连续重复四次',results[0]['error'])
        self.assertEqual(execute.call_count,3)

    def test_same_failed_path_is_not_replayed_forever(self):
        import json
        from core.self_agent import SelfAgent
        from core.agent_task import TaskJournal
        agent=SelfAgent(Mock(),config=dict(api_key='offline'));results=[];agent.completed.connect(results.append)
        call=dict(role='assistant',tool_calls=[dict(id='focus',type='function',
            function=dict(name='computer',arguments=json.dumps(dict(action='focus',hwnd=1))))])
        with tempfile.TemporaryDirectory() as folder,patch.object(agent,'_request',return_value=call), \
             patch.object(agent.computer,'execute',side_effect=RuntimeError('窗口已关闭')) as execute:
            agent.journal=TaskJournal(folder)
            agent._run('fixture',[],'打开记事本，然后查看窗口，最后确认结果',threading.Event(),
                handoff=dict(_route=dict(category='multi_step')))
        self.assertFalse(results[0]['ok'])
        self.assertEqual(agent.journal.data['status'],'paused')
        self.assertEqual(execute.call_count,3)


if __name__=='__main__':unittest.main()
