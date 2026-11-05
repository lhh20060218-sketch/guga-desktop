"""No user input: running-window discovery and visual receipt regressions."""
import json,os,tempfile,threading,unittest
from unittest.mock import patch
from types import SimpleNamespace
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from tools.test_agent_handoff import APP,Bridge
from core.self_agent import SelfAgent
from core.agent_task import TaskJournal
from core.window_inventory import matching_windows
from core.authorized_apps import AuthorizedApps

class DiscoveryTests(unittest.TestCase):
    def test_process_finds_document_title_and_minimized_window(self):
        windows=[dict(hwnd=1,title='小军',process_name='Weixin.exe',executable='G:\\Weixin.exe',minimized=True),
                 dict(hwnd=2,title='论文.txt',process_name='notepad.exe',executable='C:\\Windows\\notepad.exe')]
        self.assertEqual(matching_windows(windows,'微信'),[windows[0]])
        self.assertEqual(matching_windows(windows,'记事本'),[windows[1]])
        self.assertEqual(matching_windows(windows,'G:\\Weixin.exe'),[windows[0]])
        self.assertEqual(matching_windows(windows,'没有的软件'),[])
        unrelated=dict(hwnd=3,title='微信操作说明.txt',process_name='notepad.exe')
        self.assertEqual(matching_windows(windows+[unrelated],'微信'),[windows[0]])

    def test_open_existing_app_focuses_without_launch(self):
        apps=AuthorizedApps();apps.access=SimpleNamespace(enabled=True)
        with patch('core.window_inventory.list_windows',return_value=[dict(hwnd=7)]),patch('core.computer_control.ComputerControl.execute',return_value=dict(focused=True)) as execute,patch('os.startfile') as launch:
            r=apps.open('微信')
        self.assertTrue(r['reused_existing']);self.assertFalse(r['launch_requested'])
        launch.assert_not_called();self.assertEqual(execute.call_args.args[0]['hwnd'],7)

    def test_multiple_windows_are_returned_for_selection_without_launch(self):
        apps=AuthorizedApps();apps.access=SimpleNamespace(enabled=True)
        with patch('core.window_inventory.list_windows',return_value=[dict(hwnd=7),dict(hwnd=8)]),patch('os.startfile') as launch:
            r=apps.open('记事本')
        self.assertTrue(r['selection_required']);launch.assert_not_called()

    def test_multiple_windows_do_not_count_as_completed_open(self):
        from core.execution_contract import ExecutionLedger
        ledger=ExecutionLedger('打开微信')
        ledger.record('applications',dict(action='open'),dict(ok=True,result=dict(selection_required=True)))
        self.assertTrue(ledger.blockers())
        ledger.record('computer',dict(action='observe',hwnd=9),dict(ok=True,result=dict(hwnd=9)))
        self.assertTrue(ledger.blockers())
        ledger.record('computer',dict(action='focus',hwnd=7),dict(ok=True,result=dict(focused=True)))
        ledger.record('computer',dict(action='observe',hwnd=7),dict(ok=True,result=dict(hwnd=7)))
        self.assertFalse(ledger.blockers())

    def test_fast_route_preserves_existing_app_receipt_and_delegates_ambiguity(self):
        from core.fast_commands import _open_app
        with patch.object(AuthorizedApps,'open',return_value=dict(reused_existing=True,launch_requested=False,verified_running=True)):
            result=_open_app('test-app');self.assertTrue(result['reused_existing'])
        with patch.object(AuthorizedApps,'open',return_value=dict(selection_required=True)):
            with self.assertRaisesRegex(RuntimeError,'内部智能体'):_open_app('test-app')

    def test_top_level_wechat_image_reaches_model_but_not_journal(self):
        with tempfile.TemporaryDirectory() as folder:
            agent=SelfAgent(Bridge(),config=dict(api_key='offline'));agent.journal=TaskJournal(folder)
            requests=[];events=[];agent.activity.connect(lambda *a:events.append(a))
            def model(messages,*a,**kw):
                requests.append(list(messages))
                if len(requests)==1:
                    return dict(role='assistant',tool_calls=[dict(id='a',type='function',function=dict(name='wechat',arguments=json.dumps(dict(action='open',recipient='小军'))))])
                self.assertEqual(messages[-1]['content'][1]['image_url']['url'],'data:image/png;base64,FIXTURE')
                return dict(role='assistant',content='当前是小军的会话。')
            with patch.object(agent,'_request',side_effect=model),patch.object(agent.wechat,'execute',return_value=dict(ok=True,ready_for_message=True,_image_url='data:image/png;base64,FIXTURE')):
                agent._run('test',[],'看看小军聊天窗口',threading.Event())
            self.assertEqual(len(requests),2);self.assertNotIn('base64',str(events))
            self.assertNotIn('base64',str(agent.journal.data))

    def test_already_open_prompt_includes_window_context_before_model(self):
        with tempfile.TemporaryDirectory() as folder:
            agent=SelfAgent(Bridge(),config=dict(api_key='offline'));agent.journal=TaskJournal(folder);seen=[]
            def model(messages,*a,**kw):
                seen.append(messages)
                return dict(role='assistant',content='窗口标题是小军。')
            with patch.object(agent.computer,'execute',return_value=dict(windows=[dict(hwnd=7,title='小军',process_name='Weixin.exe',minimized=True)])) as execute,patch.object(agent,'_request',side_effect=model):
                agent._run('test',[],'微信已经打开，窗口标题是什么',threading.Event())
            self.assertIn('Weixin.exe',str(seen[0]));execute.assert_called_once()

if __name__=='__main__':unittest.main()
