"""Offline initiative checks: idle, memory basis, no interruption and protocol queue."""
import tempfile,time,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock,patch
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from launcher import _prepare_qt
_prepare_qt()
from PyQt5.QtWidgets import QApplication
from core.agent_memory import AgentMemoryStore
from core.proactive_conversation import ProactiveConversation
from core.realtime_agent import AgentRealtimeVoice
APP=QApplication.instance() or QApplication([])


def fake_panel(memory):
    runtime=SimpleNamespace(music=SimpleNamespace(playing=False))
    voice=SimpleNamespace(active=True,_playing=False,_generating=False,_user_speaking=False,_last_activity=time.monotonic()-300,
        notify_proactive=MagicMock(return_value=True))
    return SimpleNamespace(memory=memory,voice=voice,voice_active=True,busy=False,runtime=runtime,
        active_profile=memory.profile('001'),pet=None)


class ProactiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.memory=AgentMemoryStore(Path(self.tmp.name)/'memory.sqlite3')
        self.panel=fake_panel(self.memory);self.proactive=ProactiveConversation(self.panel,self.memory)
        self.proactive.started_at=time.monotonic()-300

    def tearDown(self):self.proactive.stop();self.tmp.cleanup()

    def test_memory_topic_is_used_and_cooldown_blocks_repeat(self):
        self.memory.add_dialogue('001','user','我最近想把主动聊天做得自然一点，不要一直汇报任务。')
        result=self.proactive.tick()
        self.assertTrue(result);prompt=self.panel.voice.notify_proactive.call_args.args[1]
        self.assertIn('主动聊天',prompt);self.assertIn('你是咕嘎',prompt)
        self.assertIsNone(self.proactive.tick())

    def test_busy_tasks_music_or_user_speech_never_interrupt(self):
        panel=fake_panel(self.memory);panel.busy=True
        p=ProactiveConversation(panel,self.memory);p.started_at=time.monotonic()-300
        self.assertIsNone(p.tick());p.stop()
        for attr in ('_generating','_playing','_user_speaking'):
            panel=fake_panel(self.memory);setattr(panel.voice,attr,True)
            p=ProactiveConversation(panel,self.memory);p.started_at=time.monotonic()-300
            self.assertIsNone(p.tick());p.stop()
        panel=fake_panel(self.memory);panel.runtime.music.playing=True
        p=ProactiveConversation(panel,self.memory);p.started_at=time.monotonic()-300
        self.assertIsNone(p.tick());p.stop()

    def test_not_enough_idle_time_or_inactive_call_does_nothing(self):
        panel=fake_panel(self.memory);panel.voice._last_activity=time.monotonic()-5
        p=ProactiveConversation(panel,self.memory);p.started_at=time.monotonic()-300
        self.assertIsNone(p.tick());p.stop()
        panel.voice.active=False;p=ProactiveConversation(panel,self.memory);self.assertIsNone(p.tick());p.stop()

    def test_realtime_protocol_queues_initiative_once_without_task_tools(self):
        voice=AgentRealtimeVoice();voice._thread=MagicMock();voice._thread.is_alive.return_value=True
        voice._stop.clear();voice._last_activity=time.monotonic()-10
        voice._tasks.clear();voice._generating=False;voice._playing=False;voice._user_speaking=False
        profile=self.memory.profile('002')
        self.assertTrue(voice.notify_proactive('p1','主动聊一个真实记忆',profile))
        self.assertFalse(voice.notify_proactive('p1','重复事件',profile))
        with patch.object(voice,'_send') as send:
            voice._process_command(voice._commands.get_nowait())
            voice._process_command(('proactive','p1','重复事件',time.monotonic(),voice._notice_epoch,profile))
            calls=[c.args[0]['type'] for c in send.call_args_list]
        self.assertEqual(calls,['conversation.item.create','response.create'])
        created=send.call_args_list[0].args[0]['item']
        self.assertEqual(created['content'][0]['text'],'主动聊一个真实记忆')
        self.assertNotIn('tools',created)


if __name__=='__main__':unittest.main()
