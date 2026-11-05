import json
import os
import threading
import unittest
from pathlib import Path
import sys
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from launcher import _prepare_qt
_prepare_qt()
from PyQt5.QtWidgets import QApplication
from core.execution_contract import ExecutionLedger, requires_execution
from core.self_agent import SelfAgent

APP=QApplication.instance() or QApplication([])


def call(name,args,call_id='a'):
    return dict(id=call_id,type='function',function=dict(name=name,arguments=json.dumps(args)))


class LedgerTests(unittest.TestCase):
    def test_question_about_how_to_do_something_is_not_an_action_request(self):
        self.assertFalse(requires_execution('请解释如何打开这个文件'))
        self.assertTrue(requires_execution('打开这个文件并保存'))

    def test_knowledge_questions_mentioning_actions_stay_chat(self):
        # The old heuristic sent any sentence containing 下载/删除/打开 to the
        # desktop executor, which made plain questions feel like stuck tasks.
        self.assertFalse(requires_execution('下载速度慢是什么原因'))
        self.assertFalse(requires_execution('这个文件在哪里下载'))
        self.assertFalse(requires_execution('怎么删除这个文件'))
        self.assertFalse(requires_execution('这个文件删除会怎样'))
        self.assertFalse(requires_execution('微信发送失败是什么问题'))

    def test_explicit_request_still_executes(self):
        self.assertTrue(requires_execution('帮我打开浏览器'))
        self.assertTrue(requires_execution('能不能帮我打开浏览器'))
        self.assertTrue(requires_execution('麻烦你下载这个文件'))
        self.assertTrue(requires_execution('打开这个文件并保存'))

    def test_input_requires_later_observation(self):
        led=ExecutionLedger()
        led.record('computer',{'action':'type','hwnd':1},{'ok':True,'result':{'input_sent':True}})
        self.assertTrue(any('尚未复查' in x for x in led.blockers()))
        led.record('computer',{'action':'observe','hwnd':1},{'ok':True,'result':{'observation_id':'o'}})
        self.assertEqual(led.blockers(),[])

    def test_failed_run_blocks_until_successful_run(self):
        led=ExecutionLedger()
        led.record('local_computer',{'action':'run'},{'ok':False,'error':'exit 1'})
        self.assertTrue(led.blockers())
        led.record('local_computer',{'action':'run'},{'ok':True,'result':{'exit_code':0}})
        self.assertEqual(led.blockers(),[])


class CompletionGateTests(unittest.TestCase):
    def test_action_claim_without_any_tool_receipt_is_rejected(self):
        class Bridge:
            def call(self,*a):raise AssertionError('not used')
        agent=SelfAgent(Bridge(),config={'api_key':'offline'})
        done=[];agent.completed.connect(done.append)
        responses=[dict(role='assistant',content='已经完成。'),dict(role='assistant',content='没有工具回执，不能声称完成。')]
        with patch.object(agent,'_request',side_effect=lambda *a,**k:responses.pop(0)):
            agent._run('c',[],'打开记事本并写入内容',threading.Event())
        self.assertFalse(done[0]['ok'])
        self.assertIn('没有任何工具成功回执',done[0]['error'])

    def test_failed_side_effect_cannot_finish_as_success(self):
        class Bridge:
            def call(self,*a):raise AssertionError('not used')
        agent=SelfAgent(Bridge(),config={'api_key':'offline'})
        done=[];agent.completed.connect(done.append)
        responses=[
            dict(role='assistant',content=None,tool_calls=[call('local_computer',{'action':'run','command':'fail'})]),
            dict(role='assistant',content='已经完成。'),
            dict(role='assistant',content='没有完成：命令失败且没有成功回执。')]
        with patch.object(agent,'_request',side_effect=lambda *a,**k:responses.pop(0)), \
             patch('core.desktop_access.DesktopAccess.execute',return_value=dict(exit_code=1,stopped=None)):
            agent._run('c',[],'执行命令',threading.Event())
        self.assertFalse(done[0]['ok'])
        self.assertIn('退出码 1',done[0]['error'])
        self.assertIn('下一步',done[0]['error'])

    def test_completion_gate_can_resolve_with_new_receipt(self):
        class Bridge:
            def call(self,*a):raise AssertionError('not used')
        agent=SelfAgent(Bridge(),config={'api_key':'offline'})
        done=[];agent.completed.connect(done.append)
        responses=[
            dict(role='assistant',content=None,tool_calls=[call('computer',{'action':'type','text':'x'})]),
            dict(role='assistant',content='已经完成。'),
            dict(role='assistant',content=None,tool_calls=[call('computer',{'action':'observe','hwnd':1},'b')]),
            dict(role='assistant',content='输入并复查完成。')]
        with patch.object(agent,'_request',side_effect=lambda *a,**k:responses.pop(0)), \
             patch.object(agent.computer,'execute',side_effect=[{'input_sent':True},{'observation_id':'ok'}]), \
             patch('core.desktop_access.DesktopAccess.execute',return_value={'exit_code':0,'stopped':None,
                 'stdout':'{"name":"Test"}'}):
            agent._run('c',[],'输入并验证',threading.Event())
        self.assertTrue(done[0]['ok'])
        self.assertIn('复查完成',done[0]['text'])


if __name__=='__main__':unittest.main()
