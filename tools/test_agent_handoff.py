import json,os,tempfile,threading,unittest
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from launcher import _prepare_qt
_prepare_qt()
from PyQt5.QtWidgets import QApplication
from core.self_agent import SelfAgent,PERSONA
from core.agent_task import TaskJournal
from core.fast_commands import match
from core.wechat_demo import WeChatAgent
APP=QApplication.instance() or QApplication([])

class Bridge:
    def __init__(self):self.calls=[]
    def call(self,name,args,cancel):
        self.calls.append((name,args))
        return dict(ok=True,result=dict(pet=dict(visible=True))) if name=='app_state' else dict(ok=True,result={})

class HandoffTests(unittest.TestCase):
    def test_unknown_site_is_reasoning_task_not_fake_local_app(self):
        self.assertFalse(match('打开某个新的科学网站')['matched'])
        self.assertEqual(match('打开哔哩哔哩这个网站')['target'],'https://www.bilibili.com')
    def test_wechat_open_then_compose_send_and_deduplicate(self):
        with tempfile.TemporaryDirectory() as folder:
            bridge=Bridge();agent=SelfAgent(bridge,config=dict(api_key='offline'));agent.journal=TaskJournal(folder)
            done=[];agent.completed.connect(done.append);seen=[]
            def call(action,**kw):return dict(role='assistant',reasoning_content='fixture reasoning',content=None,tool_calls=[dict(id='c'+str(len(seen)),type='function',function=dict(name='wechat',arguments=json.dumps(dict(action=action,recipient='小军',**kw))))])
            def model(messages,*args,**kwargs):
                seen.append(list(messages))
                if len(seen)==1:return call('open')
                if len(seen) in (2,3):return call('send',text='这是由内层模型组织的演示文字',chat_token='token')
                return dict(role='assistant',content='消息已出现在小军聊天区。')
            def tool(args,cancel):
                return dict(ok=True,ready_for_message=True,chat_token='token') if args['action']=='open' else dict(ok=True,send_clicked=True,verified_message_visible=True)
            with patch.object(agent,'_request',side_effect=model),patch.object(agent.wechat,'execute',side_effect=tool) as execute:
                agent._run('test',[],'给微信小军写一段话并发送',threading.Event(),dict(origin='voice'))
            self.assertEqual([c.args[0]['action'] for c in execute.call_args_list],['open','send'])
            self.assertTrue(done[0]['ok']);self.assertEqual(len(seen),4)
            self.assertIn('实时语音智能体',seen[0][0]['content'])
            self.assertTrue(any(m.get('reasoning_content') for m in seen[-1]))
            self.assertTrue(any('voice' in str(m.get('content')) for m in seen[0]))
            self.assertEqual(sum(1 for name,args in bridge.calls if name=='pet_control' and args['action']=='hide'),2)
            self.assertEqual(sum(1 for name,args in bridge.calls if name=='pet_control' and args['action']=='show'),2)
    def test_pet_is_restored_after_tool_exception(self):
        bridge=Bridge();agent=SelfAgent(bridge,config=dict(api_key='offline'))
        with self.assertRaises(RuntimeError):agent._desktop_capability(lambda:(_ for _ in ()).throw(RuntimeError('fixture')),threading.Event())
        self.assertEqual(bridge.calls[-1],('pet_control',dict(action='show')))
    def test_stale_wechat_token_never_sends(self):
        controller=WeChatAgent(None)
        with patch('core.wechat_demo.send_message') as send:
            with self.assertRaises(ValueError):controller.execute(dict(action='send',recipient='小军',text='hello',chat_token='old'),threading.Event())
            send.assert_not_called()
    def test_open_chat_cannot_claim_message_sent(self):
        from core.execution_contract import ExecutionLedger
        ledger=ExecutionLedger('给小军发一段介绍并发送')
        ledger.record('wechat',dict(action='open'),dict(ok=True,ready_for_message=True))
        self.assertTrue(ledger.blockers())
        ledger.record('wechat',dict(action='send'),dict(ok=True,verified_message_visible=True))
        self.assertFalse(ledger.blockers())
if __name__=='__main__':unittest.main()
