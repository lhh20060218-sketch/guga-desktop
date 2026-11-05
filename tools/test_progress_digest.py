"""Finite regressions for evidence-only reporting and pending voice tasks."""
import os,unittest
from unittest.mock import patch,MagicMock
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from launcher import _prepare_qt
_prepare_qt()
from PyQt5.QtWidgets import QApplication
from core.task_feedback import EvidenceProgress
from core.realtime_agent import AgentRealtimeVoice
from ui.agent_chat import AgentChatWindow
APP=QApplication.instance() or QApplication([])


class ProgressTests(unittest.TestCase):
    def test_thirty_second_digest_keeps_reporting_real_stalls(self):
        report=EvidenceProgress(now=0)
        self.assertIsNone(report.notice(12))
        self.assertIsNone(report.notice(29))
        self.assertIn('没有可核验',report.notice(30))
        self.assertIn('没有新的',report.notice(60))
        self.assertIn('没有新的',report.notice(90))
        self.assertIsNone(report.notice(91))

    def test_digest_only_uses_receipts_and_never_raw_tool_content(self):
        report=EvidenceProgress(now=0)
        report.tool_result('computer',{'action':'click'},dict(ok=True,reasoning_content='HIDDEN',result={'api_key':'PRIVATE'}))
        report.tool_result('local_computer',{'action':'run'},dict(ok=False,error='PRIVATE'))
        text=report.notice(180)
        self.assertIn('工具回执成功',text);self.assertIn('未完成',text)
        self.assertIn('任务还在继续',text)
        self.assertNotIn('PRIVATE',text);self.assertNotIn('HIDDEN',text)

    def test_pending_voice_task_does_not_block_progress_or_become_completed(self):
        voice=AgentRealtimeVoice();voice._tasks={'task':'response'}
        voice._last_activity=0;voice._generating=False;voice._playing=False
        with patch.object(voice,'_send') as send:
            voice.notify_battleground('progress','文件已写入，还没有通过验证',during_task=True)
            voice._process_command(voice._commands.get_nowait())
        self.assertTrue(any(c.args[0]['type']=='response.create' for c in send.call_args_list))
        self.assertEqual(voice._tasks,{'task':'response'})
        self.assertTrue(voice._notice_active)

    def test_progress_defers_while_user_speaks(self):
        voice=AgentRealtimeVoice();voice._tasks={'task':'response'}
        voice._last_activity=0;voice._generating=False;voice._playing=False;voice._user_speaking=True
        with patch.object(voice,'_send') as send:
            voice.notify_battleground('progress','正在等待核验',during_task=True)
            voice._process_command(voice._commands.get_nowait())
            send.assert_not_called()
        self.assertEqual(len(voice._notices),1)

    def test_sidecar_reporting_survives_parent_turn_completion_and_uses_owner(self):
        panel=MagicMock();panel.busy=False;panel.voice_active=False
        panel._task_reporter=None
        report=EvidenceProgress(now=0)
        report.tool_result('local_computer',{'action':'read'},dict(ok=True))
        panel._dsh_reports={'job':dict(agent_id='002',conversation_id='fish-chat',reporter=report)}
        AgentChatWindow._task_heartbeat(panel)
        self.assertEqual(panel.pet._multi_agent.say.call_args.args[0],'002')
        panel._task_heartbeat_timer.stop.assert_not_called()

if __name__=='__main__':unittest.main()
