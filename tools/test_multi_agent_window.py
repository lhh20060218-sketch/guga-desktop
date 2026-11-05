"""Offscreen integration: independent Guga companions and per-agent conversation switching."""
import os,sys,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from launcher import _prepare_qt
_prepare_qt()
from PyQt5.QtCore import QSettings,QTimer
from PyQt5.QtWidgets import QApplication
from core.agent_memory import AgentMemoryStore
from core.chat_workspace import ChatWorkspace
from ui.pet_window import PetWindow
from ui.agent_chat import AgentChatWindow
from ui.multi_agent_window import MultiAgentManager
APP=QApplication.instance() or QApplication([])


class MultiAgentWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder=tempfile.TemporaryDirectory();path=Path(cls.folder.name)
        QSettings.setDefaultFormat(QSettings.IniFormat);QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,str(path))
        cls.patches=[patch('core.keyboard_hook.KeyboardHook.start'),patch('ui.tts_engine.TTSEngine.speak'),
            patch('core.browser_launch.default_executable',return_value=None)]
        for item in cls.patches:item.start()
        cls.pet=PetWindow();cls.pet._agent_memory=AgentMemoryStore(path/'memory.sqlite3')
        old=cls.pet._multi_agent;old.close();cls.manager=MultiAgentManager(cls.pet,cls.pet._agent_memory);cls.pet._multi_agent=cls.manager
        for timer in cls.pet.findChildren(QTimer):timer.stop()
        cls.pet._anim.stop()
        cls.panel=AgentChatWindow(cls.pet,ChatWorkspace(path/'chat.sqlite3'),memory=cls.pet._agent_memory);cls.pet._agent_panel=cls.panel

    @classmethod
    def tearDownClass(cls):
        cls.manager.close();cls.panel.shutdown();cls.panel.hide();cls.pet._screen_tools.stop();cls.pet._self_mcp.close();cls.pet._tray.hide();cls.pet.hide()
        for item in cls.patches:item.stop()
        cls.folder.cleanup()

    def setUp(self):
        self.manager.close();self.manager.companions={}
        self.panel.busy=False;self.panel.voice_active=False;self.panel.agent.cancel_event.clear()

    def test_two_companions_are_distinct_lightweight_windows(self):
        first=self.manager.summon('002');again=self.manager.summon('002');third=self.manager.summon('003')
        self.assertIs(first,again);self.assertIsNot(first,third)
        self.assertTrue(first.isVisible() and third.isVisible())
        self.assertEqual(first.anim.appearance,'dafish');self.assertEqual(third.anim.appearance,'dora')
        self.assertEqual(first.agent_id,'002');self.assertEqual(third.agent_id,'003')
        self.assertFalse(hasattr(first,'_tray'))
        self.assertFalse(hasattr(first,'_hook'))
        self.assertEqual(self.manager.status()['companions'][0]['role'],'技术审查员')

    def test_open_companion_chat_switches_identity_and_isolated_conversation(self):
        self.manager.summon('002');self.assertTrue(self.manager.open_chat('002'))
        self.assertEqual(self.panel.active_agent_id,'002');self.assertEqual(self.panel.active_profile['role'],'技术审查员')
        self.assertEqual(self.panel.store.conversation(self.panel.active_id)['agent_id'],'002')
        self.assertIn('大肥鱼',self.panel.title.text())
        self.assertTrue(self.manager.open_chat('001'));self.assertEqual(self.panel.active_agent_id,'001')
        self.assertNotEqual(self.panel.store.conversation(self.panel.active_id)['agent_id'],'002')
        self.panel.store.preference('agent/active_id','003')
        fresh=AgentChatWindow(self.pet,ChatWorkspace(self.panel.store.path),memory=self.pet._agent_memory)
        self.assertEqual(fresh.active_agent_id,'001')
        fresh.shutdown();fresh.hide()

    def test_replies_are_routed_to_the_active_companion_bubble(self):
        fish=self.manager.summon('002')
        self.manager.say('002','大肥鱼审查完了：测试通过。')
        self.assertEqual(fish.bubble.full_text,'大肥鱼审查完了：测试通过。')
        self.assertTrue(fish.bubble.isVisible())
        self.assertNotIn('测试通过',self.pet._agent_bubble.full_text)

    def test_specialty_and_manual_note_update_own_memory(self):
        self.manager.summon('002')
        with patch('ui.multi_agent_window.QInputDialog.getText',return_value=('审查用户界面回归',True)):
            self.assertTrue(self.manager.edit_specialty('002'))
        self.assertEqual(self.pet._agent_memory.profile('002')['specialty'],'审查用户界面回归')
        with patch('ui.multi_agent_window.QInputDialog.getMultiLineText',return_value=('测试任务优先检查真实文件而不是口头完成',True)):
            self.assertTrue(self.manager.remember_note('002'))
        remembered='\n'.join(x['content'] for x in self.pet._agent_memory.recall('002','测试 文件'))
        self.assertIn('真实文件',remembered);self.assertNotIn('真实文件','\n'.join(x['content'] for x in self.pet._agent_memory.recall('001','测试 文件')))



    def test_real_companion_text_tool_changes_dora_sprite_and_holds_sleep(self):
        self.manager.summon('003');self.manager.open_chat('003')
        result=self.panel.runtime._pet(dict(action='set_expression',name='angry'))
        dora=self.manager.companions['003']
        self.assertTrue(result['applied']);self.assertEqual(Path(dora.anim.path).name,'angry.png')
        self.panel.runtime._pet(dict(action='set_expression',name='sleepy'))
        self.manager.say('003','后台汇报不会叫醒我','happy')
        self.assertEqual(dora.anim.expression,'sleepy')
        self.manager.user_interaction('003');self.assertEqual(dora.anim.expression,'happy')
        self.panel.runtime._pet(dict(action='set_expression',name='eating'))
        self.assertEqual(Path(dora.anim.path).name,'happy.png')


    def test_each_companion_resizes_independently_and_keeps_own_menu_cached(self):
        first=self.manager.summon('002');third=self.manager.summon('003')
        original=self.pet.size();first.set_scale(.5);third.set_scale(.8)
        self.assertEqual(first.width(),round(first.anim.width*.5))
        self.assertEqual(third.width(),round(third.anim.width*.8));self.assertEqual(self.pet.size(),original)
        menu=first._ensure_menu();self.assertIs(menu,first._ensure_menu())
        labels=[a.text() for a in menu.actions()]
        for item in ('战旗','对话','长语音','截图分析','解释','大小','音乐与动作','声音与人格'):
            self.assertTrue(any(item in label for label in labels),item)
        battle=next(a.menu() for a in menu.actions() if a.text()=='战旗')
        for item in ('一键拔线','日志分析','战局分析'):
            self.assertTrue(any(item in a.text() for a in battle.actions()),item)
            self.assertFalse(any(item in label for label in labels),item)
        first.set_scale(1.);third.set_scale(1.)


    def test_current_member_menu_stays_available_during_own_voice_call(self):
        self.manager.open_chat('003');self.panel.voice_active=True
        self.assertTrue(self.panel.activate_agent('003'))
        self.assertFalse(self.panel.activate_agent('002'))
        self.assertEqual(self.panel.active_agent_id,'003')
        self.panel.voice_active=False

if __name__=='__main__':unittest.main()
