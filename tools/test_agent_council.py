import json,tempfile,time,unittest
from pathlib import Path
from unittest.mock import MagicMock,patch
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from launcher import _prepare_qt
_prepare_qt();
from PyQt5.QtWidgets import QApplication
from core.agent_memory import AgentMemoryStore
from core.agent_council import DiscussionWorker,council_payload
APP=QApplication.instance() or QApplication([])


class CouncilTests(unittest.TestCase):
    def pump(self,predicate,seconds=2):
        until=time.monotonic()+seconds
        while not predicate() and time.monotonic()<until:APP.processEvents();time.sleep(.01)
        self.assertTrue(predicate())

    def test_payload_keeps_identity_and_no_tools_or_reasoning(self):
        profile=dict(display_name='咕嘎 002',role='审查员',specialty='测试验收')
        payload=council_payload(dict(model='offline',api_key='x'),profile,'主人担心回归测试','方案评审','001：先看风险')
        self.assertEqual(payload['thinking']['type'],'disabled');self.assertNotIn('tools',payload)
        self.assertIn('测试验收',payload['messages'][0]['content'])
        self.assertIn('方案评审',payload['messages'][1]['content'])

    def test_two_turns_are_persisted_to_separate_members_and_shared_log(self):
        with tempfile.TemporaryDirectory() as folder:
            memory=AgentMemoryStore(Path(folder)/'memory.sqlite3')
            worker=DiscussionWorker(memory=memory,config=dict(api_key='offline',base_url='https://example.test'))
            turns=[];done=[];worker.turn.connect(turns.append);worker.completed.connect(done.append)
            responses=[dict(choices=[dict(message=dict(content='001：先备份，再检查边界。'))]),
                       dict(choices=[dict(message=dict(content='002：同意，必须补测试；还要验证失败路径。'))])]
            def post(*args,**kwargs):
                return MagicMock(status_code=200,json=lambda:responses.pop(0))
            with patch('core.agent_council.requests.post',side_effect=post):
                worker.start('升级前怎样降低风险',('001','002'),rounds=1);self.pump(lambda:bool(done),3)
            self.assertTrue(done[0]['ok']);self.assertEqual([x['agent_id'] for x in turns],['001','002'])
            self.assertIn('先备份',memory.recent_dialogue('001')[-1]['content'])
            self.assertIn('失败路径',memory.recent_dialogue('002')[-1]['content'])
            self.assertNotIn('失败路径',memory.recent_dialogue('001')[-1]['content'])

    def test_cancel_does_not_emit_late_completion(self):
        memory=AgentMemoryStore(Path(tempfile.mkdtemp())/'memory.sqlite3')
        worker=DiscussionWorker(memory=memory,config=dict(api_key='offline'))
        done=[];worker.completed.connect(done.append)
        with patch('core.agent_council.requests.post',side_effect=MagicMock(status_code=500)):
            worker.start('测试取消',('001','002'));worker.cancel();self.pump(lambda:not worker.active)
        self.assertEqual(done,[])


if __name__=='__main__':unittest.main()
