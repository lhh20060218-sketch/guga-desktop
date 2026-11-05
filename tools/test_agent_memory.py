"""Isolated SQLite checks: identity separation, redaction, retrieval and recency."""
import tempfile,unittest
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core.agent_memory import AgentMemoryStore


class AgentMemoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'memory.sqlite3';self.memory=AgentMemoryStore(self.path)

    def tearDown(self):self.tmp.cleanup()

    def test_default_profiles_have_distinct_roles_and_specialties(self):
        profiles={p['agent_id']:p for p in self.memory.profiles()}
        self.assertEqual(set(profiles),{'001','002','003'})
        self.assertEqual(profiles['002']['display_name'],'大肥鱼')
        self.assertIn('DeepSeek Harness',profiles['002']['specialty'])
        self.assertEqual(profiles['003']['display_name'],'Dora')
        self.assertIn('橘子',profiles['003']['specialty'])

    def test_memories_and_dialogue_do_not_leak_between_agents(self):
        self.memory.add_dialogue('001','user','我在做咕嘎项目，担心改动破坏原有功能。')
        self.memory.remember('001','主人偏好：先备份再升级。',importance=5)
        self.memory.add_dialogue('002','user','今天专门检查测试失败的边界。')
        self.memory.remember('002','002偏好：审查所有未验证完成声明。',importance=5)
        recalled=self.memory.recall('001','咕嘎 备份 改动',limit=4)
        joined='\n'.join(x['content'] for x in recalled)
        self.assertIn('先备份',joined);self.assertNotIn('未验证完成声明',joined)
        other=self.memory.recall('002','测试 验证',limit=4)
        self.assertTrue(any('未验证' in x['content'] or '测试失败' in x['content'] for x in other))

    def test_secrets_are_redacted_before_persistence(self):
        sample='key=sk-abcdefghijklmnopqrstuvwx12345'
        self.memory.remember('001',sample)
        rows=self.memory.recall('001','key')
        stored='\n'.join(x['content'] for x in rows)
        self.assertNotIn('abcdefghijklmnopqrstuvwx12345',stored)
        self.assertIn('[REDACTED]',stored)

    def test_proactive_candidates_prefer_recent_user_topics_and_ignore_tiny_noise(self):
        self.memory.add_dialogue('001','user','今天想继续把唱歌互动做得自然一点')
        self.memory.add_dialogue('001','user','嗯')
        self.memory.remember('001','主人喜欢偶尔主动聊项目进展',importance=4)
        topics=self.memory.proactive_topics('001')
        self.assertTrue(topics);self.assertFalse(any(x=='嗯' for x in topics))
        self.assertTrue(any('唱歌' in x for x in topics))


if __name__=='__main__':unittest.main()
