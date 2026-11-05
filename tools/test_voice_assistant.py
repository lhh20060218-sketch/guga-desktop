"""Regressions for the reported voice close-page failure, routing and diagnostics."""
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import Mock,patch,PropertyMock

import requests

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from launcher import _prepare_qt
_prepare_qt()
from PyQt5.QtWidgets import QApplication
from core.agent_failure import exception_evidence,explain_failure
from core.agent_task import TaskJournal
from core.browser_actions import close_current_tab,bounded_close
from core.fast_commands import match
from core.self_agent import SelfAgent
from core.task_router import choose_task_route

APP=QApplication.instance() or QApplication([])


class RoutingTests(unittest.TestCase):
    def test_spoken_corrections_and_page_synonyms_are_local(self):
        for text in ('关闭当前页面','不不不，我的意思是让你关闭页面。','请帮我把当前网页关掉',
                     '咕嘎，关掉这个标签页吧','我是说关闭一下当前浏览器页面','把这个页面关上'):
            with self.subTest(text=text):self.assertEqual(match(text).get('action'),'close_page')

    def test_page_close_never_swallows_negation_or_multistep_work(self):
        for text in ('不要关闭当前页面','关闭当前页面然后打开百度','关闭当前页面并保存报告','关闭所有页面'):
            with self.subTest(text=text):self.assertFalse(match(text)['matched'])
        self.assertEqual(match('关闭浏览器')['action'],'close_browser')

    def test_only_complex_engineering_or_explicit_dsh_is_delegated(self):
        for text in ('打开GitHub源码仓库页面','在编辑器修改一行代码','写一个冒泡排序函数',
                     '关闭当前页面','读取项目文件','帮我测试麦克风'):
            with self.subTest(text=text):self.assertEqual(choose_task_route(text)['executor'],'local_agent')
        for text in ('重构这个Python项目并修复多文件测试','开发一个完整的前端项目','交给DSH整理报告'):
            with self.subTest(text=text):self.assertEqual(choose_task_route(text)['executor'],'dsh')


class CloseTests(unittest.TestCase):
    def setUp(self):
        self.windows=patch('core.window_inventory.list_windows',return_value=[dict(hwnd=123,foreground=True)]).start()
        self.tabs=patch('core.browser_actions.BrowserTabs').start().return_value
        self.keys=patch('core.computer_control._send_keys').start()
        patch('core.computer_control.ComputerControl.execute').start()
        patch('win32gui.GetForegroundWindow',return_value=123).start()
        patch('win32gui.IsWindow',return_value=True).start()
        patch('core.browser_actions.time.sleep').start()
        patch('core.desktop_access.DesktopAccess.enabled',new_callable=PropertyMock,return_value=True).start()
        self.addCleanup(patch.stopall)
        self.before=[dict(id='a',selected=True),dict(id='b',selected=False)]

    def test_exact_selected_tab_disappears(self):
        self.tabs.snapshot.side_effect=[self.before,self.before,[dict(id='b',selected=True)]]
        result=close_current_tab()
        self.assertTrue(result['verified']);self.assertEqual(result['evidence'],'selected_tab_removed')
        self.keys.assert_called_once_with([0x11,0x57])

    def test_changed_tab_is_not_closed(self):
        self.tabs.snapshot.side_effect=[self.before,[dict(id='a',selected=False),dict(id='b',selected=True)]]
        result=close_current_tab();self.assertEqual(result['code'],'target_changed');self.keys.assert_not_called()

    def test_multiple_windows_require_target_instead_of_random_close(self):
        self.windows.return_value=[dict(hwnd=1),dict(hwnd=2)]
        result=close_current_tab();self.assertEqual(result['code'],'target_ambiguous');self.keys.assert_not_called()

    def test_a_background_browser_is_not_the_current_page(self):
        self.windows.return_value=[dict(hwnd=123,foreground=False)]
        result=close_current_tab();self.assertEqual(result['code'],'target_not_foreground');self.keys.assert_not_called()

    def test_no_uia_selection_sends_no_input(self):
        self.tabs.snapshot.return_value=[]
        self.assertEqual(close_current_tab()['code'],'tab_unavailable');self.keys.assert_not_called()

    def test_silent_focus_denial_uses_bounded_foreground_handoff(self):
        self.tabs.snapshot.side_effect=[self.before,self.before,[dict(id='b',selected=True)]]
        with patch('core.computer_control.ComputerControl.execute',side_effect=RuntimeError('focus denied')), \
             patch('core.computer_control._attach_focus',return_value=True) as focus:
            result=close_current_tab()
        self.assertTrue(result['verified']);focus.assert_called_once_with(123);self.keys.assert_called_once()

    def test_failed_foreground_handoff_is_explained_and_sends_no_input(self):
        self.tabs.snapshot.return_value=self.before
        with patch('core.computer_control.ComputerControl.execute',side_effect=RuntimeError('焦点未取得')), \
             patch('core.computer_control._attach_focus',return_value=False):
            result=close_current_tab()
        self.assertEqual(result['stage'],'window_focus');self.assertIn('焦点未取得',result['error']);self.keys.assert_not_called()

    def test_unchanged_tabs_report_unverified_without_retry(self):
        self.tabs.snapshot.return_value=self.before
        result=close_current_tab()
        self.assertFalse(result['ok']);self.assertTrue(result['action_sent']);self.keys.assert_called_once()

    def test_verification_error_after_input_does_not_resend(self):
        self.tabs.snapshot.side_effect=[self.before,self.before,RuntimeError('stale')]
        result=close_current_tab();self.assertFalse(result['ok']);self.assertTrue(result['action_sent']);self.keys.assert_called_once()

    def test_worker_timeout_is_explicitly_uncertain(self):
        with patch('subprocess.run',side_effect=subprocess.TimeoutExpired('worker',7)):
            result=bounded_close()
        self.assertEqual(result['code'],'worker_timeout');self.assertIsNone(result['action_sent'])


class FailureTests(unittest.TestCase):
    def test_transport_layers_are_distinct_and_never_log_credentials(self):
        for exc,code in ((requests.exceptions.ProxyError('secret'), 'proxy'),
                         (requests.exceptions.SSLError('secret'),'tls'),
                         (requests.ConnectTimeout('secret'),'connect_timeout'),
                         (requests.ReadTimeout('secret'),'read_timeout'),
                         (requests.ConnectionError(socket.gaierror(11001,'secret')),'dns')):
            with self.subTest(code=code):
                diagnostic=exception_evidence(exc,'https://user:secret@example.com/v1?key=secret')
                self.assertEqual(diagnostic['code'],code)
                self.assertNotIn('secret',json.dumps(diagnostic));self.assertEqual(diagnostic['service_host'],'example.com')

    def test_disconnect_before_tools_produces_a_durable_explanation_without_another_model_call(self):
        agent=SelfAgent(Mock(),config={'api_key':'offline','base_url':'https://example.com/v1'})
        with tempfile.TemporaryDirectory() as tmp:
            agent.journal=TaskJournal(Path(tmp));completed=[];agent.completed.connect(completed.append)
            with patch.object(agent,'_request',side_effect=requests.ConnectionError('private-key')) as request:
                agent._run('test',[],'关闭当前页面',threading.Event())
            request.assert_called_once();result=completed[0]
            self.assertFalse(result['ok']);self.assertIn('尚未调用任何操作工具',result['error'])
            self.assertIn('下一步',result['error']);self.assertNotIn('private-key',json.dumps(result))
            persisted=agent.journal.latest('test');self.assertEqual(persisted['diagnostic']['code'],'connection')

    def test_http_status_and_request_timing_survive_without_body_or_headers(self):
        agent=SelfAgent(Mock(),config={'api_key':'private-key','base_url':'https://example.com/v1'})
        response=Mock(status_code=403)
        with patch('core.self_agent.requests.post',return_value=response):
            with self.assertRaises(requests.HTTPError):agent._request([], 'test')
        self.assertEqual(agent._last_model_diagnostic['http_status'],403)
        self.assertIn('权限',agent._last_model_diagnostic['next_step']);response.close.assert_called_once()
        self.assertNotIn('private-key',json.dumps(agent._last_model_diagnostic))

    def test_partial_operations_are_not_described_as_no_action(self):
        text=explain_failure('连接中断',operations=2,events=[dict(tool='computer',ok=True),dict(tool='wechat',ok=False)])
        self.assertIn('工具2次',text);self.assertIn('wechat',text);self.assertNotIn('没有执行关闭',text)

    def test_uncertain_close_is_not_replayed_by_model(self):
        agent=SelfAgent(Mock(),config={'api_key':'offline'})
        call=lambda ident:dict(id=ident,type='function',function=dict(name='browser',arguments='{"action":"close_tab"}'))
        responses=[dict(role='assistant',content=None,tool_calls=[call('a'),call('b')]),
                   dict(role='assistant',content='没有完成，关闭结果尚未核验。'),
                   dict(role='assistant',content='没有完成，请先核对页面。')]
        with tempfile.TemporaryDirectory() as tmp:
            agent.journal=TaskJournal(Path(tmp));completed=[];agent.completed.connect(completed.append)
            with patch.object(agent,'_request',side_effect=responses), \
                 patch.object(agent,'_desktop_capability',side_effect=lambda callback,cancel:callback()), \
                 patch('core.browser_agent.execute',return_value=dict(ok=False,code='close_unverified',action_sent=None,error='关闭结果未知，请核对页面')) as browser:
                agent._run('test',[],'关闭当前页面',threading.Event())
            browser.assert_called_once();self.assertFalse(completed[0]['ok'])
            self.assertIn('关闭结果未知',completed[0]['error'])

    def test_connection_failure_after_a_tool_keeps_partial_evidence(self):
        agent=SelfAgent(Mock(),config={'api_key':'offline'})
        response=dict(role='assistant',content=None,tool_calls=[dict(id='a',type='function',
                      function=dict(name='computer',arguments='{"action":"windows"}'))])
        with tempfile.TemporaryDirectory() as tmp:
            agent.journal=TaskJournal(Path(tmp));completed=[];agent.completed.connect(completed.append)
            with patch.object(agent,'_request',side_effect=[response,requests.ReadTimeout('private')]) as request, \
                 patch.object(agent.computer,'execute',return_value=dict(windows=[])) as computer:
                agent._run('test',[],'检查当前窗口',threading.Event())
            self.assertEqual(request.call_count,2);computer.assert_called_once()
            self.assertIn('工具1次',completed[0]['error']);self.assertEqual(completed[0]['diagnostic']['code'],'read_timeout')


if __name__=='__main__':unittest.main()
