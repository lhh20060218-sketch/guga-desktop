"""Member identity, scaling/menu and per-request voice regressions."""
import json,os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch,MagicMock
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from launcher import _prepare_qt
_prepare_qt()
from PyQt5.QtWidgets import QApplication
from core.agent_memory import AgentMemoryStore
from core.agent_identity import identity_instructions,voice_preferences,realtime_config
from core.realtime_agent import AgentRealtimeVoice
APP=QApplication.instance() or QApplication([])

class IdentityTests(unittest.TestCase):
    def test_different_personalities_and_voices_survive_reopening_without_memory_leak(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'memory.sqlite3';memory=AgentMemoryStore(path)
            fish=memory.profile('002');dora=memory.profile('003')
            self.assertIn('白米饭',identity_instructions(fish));self.assertIn('温柔体贴',identity_instructions(dora))
            memory.remember('002','我喜欢白米饭')
            memory.update_profile('003',personality='温柔体贴，喜欢给人打气',
                                  voice_settings=dict(qwen31='longanfengyue_v3.1',edge_voice='zh-CN-XiaoxiaoNeural'))
            reopened=AgentMemoryStore(path)
            self.assertIn('给人打气',reopened.profile('003')['personality'])
            self.assertEqual(voice_preferences(reopened.profile('003'))['qwen31'],'longanfengyue_v3.1')
            self.assertEqual(reopened.recall('003','白米饭'),[])
            self.assertTrue(reopened.recall('002','白米饭'))
    def test_native_call_receives_member_specific_voice_but_guga_inherits_user_voice(self):
        with tempfile.TemporaryDirectory() as folder:
            memory=AgentMemoryStore(Path(folder)/'memory.sqlite3');selected=[]
            for ident in ('001','002','003'):
                voice=AgentRealtimeVoice();voice._cfg=dict(model='qwen-audio-3.1-realtime-plus',voice='longanqian_v3.1')
                voice.agent_profile=memory.profile(ident)
                settings=voice._session_settings();selected.append(settings['voice'])
                if ident=='002':self.assertIn('懒洋洋',settings['instructions'])
                if ident=='003':self.assertIn('温柔体贴',settings['instructions'])
            self.assertEqual(len(set(selected)),3)
            custom=dict(model='qwen-audio-3.1-realtime-plus',voice='custom-guga')
            self.assertEqual(realtime_config(custom,memory.profile('001'))['voice'],'custom-guga')
    def test_foreign_model_does_not_receive_a_qwen_audio_voice_id(self):
        cfg=dict(model='qwen3.8-omni-flash-realtime',voice='Tina')
        self.assertEqual(realtime_config(cfg,dict(voice_settings={'qwen31':'longanhuan_v3.1'}))['voice'],'Tina')
    def test_voice_settings_reject_credentials_and_unknown_fields(self):
        with tempfile.TemporaryDirectory() as folder:
            memory=AgentMemoryStore(Path(folder)/'memory.sqlite3')
            with self.assertRaises(ValueError):memory.update_profile('003',voice_settings=dict(api_key='do-not-store'))
    def test_edge_synthesis_passes_voice_snapshot_without_mutating_guga_defaults(self):
        from ui.tts_engine import TTSEngine
        with patch.object(TTSEngine,'_cleanup_stale_tmp'):
            engine=TTSEngine()
        before=(engine.EDGE_VOICE,engine.EDGE_RATE,engine.EDGE_PITCH)
        preferences=dict(edge_voice='zh-CN-XiaoxiaoNeural',edge_rate='+0%',edge_pitch='+0Hz')
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'test.mp3'
            async def save(path):Path(path).write_bytes(b'x'*256)
            synthesizer=MagicMock();synthesizer.save=save
            with patch('edge_tts.Communicate',return_value=synthesizer) as communicate:
                self.assertTrue(engine._synth_edge('测试',str(target),preferences))
                self.assertEqual(communicate.call_args.args[1],'zh-CN-XiaoxiaoNeural')
                self.assertEqual(communicate.call_args.kwargs['rate'],'+0%')
        self.assertEqual(before,(engine.EDGE_VOICE,engine.EDGE_RATE,engine.EDGE_PITCH))

if __name__=='__main__':unittest.main()
