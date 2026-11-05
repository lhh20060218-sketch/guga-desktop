"""Offline checks for the ego -> voice web-fact bridge."""
import json
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from launcher import _prepare_qt
_prepare_qt()
from PyQt5.QtWidgets import QApplication

from core.dsh_worker import DshManager, ego_tool_fact
from core.realtime_voice import DEFAULTS
from core.realtime_agent import AgentRealtimeVoice
from ui.agent_chat import web_fact_from_tool_event

APP = QApplication.instance() or QApplication([])


class EgoFactParsingTests(unittest.TestCase):
    def test_navigate_result_yields_url_title_without_page_text(self):
        item = dict(type='tool_result', tool='ego_navigate', status='completed',
                    input={'url': 'https://example.com'},
                    result=json.dumps({'ok': True, 'page': {'url': 'https://example.com/',
                                                            'title': 'Example Domain'},
                                       'text': '页面正文不应进入语音事实'}))
        fact = ego_tool_fact(item)
        self.assertEqual(fact['tool'], 'ego_navigate')
        self.assertEqual(fact['url'], 'https://example.com/')
        self.assertEqual(fact['title'], 'Example Domain')
        self.assertTrue(fact['ok'])
        self.assertNotIn('text', fact)
        self.assertNotIn('页面正文', json.dumps(fact, ensure_ascii=False))

    def test_non_ego_tool_is_ignored(self):
        self.assertIsNone(ego_tool_fact(dict(type='tool_result', tool='graph', result='{"ok":true}')))
        # An ego call that carries no URL/title has no voice-bridge value.
        self.assertIsNone(ego_tool_fact(dict(type='tool_call', tool='ego_navigate', input={})))

    def test_call_event_carries_the_requested_url(self):
        fact = ego_tool_fact(dict(type='tool_call', tool='ego_navigate', input={'url': 'https://a.test/x'}))
        self.assertEqual(fact['url'], 'https://a.test/x')

    def test_publish_exposes_only_ego_facts(self):
        manager = DshManager()
        events = []
        manager.event.connect(events.append)
        manager._publish(dict(type='dsh_event', job_id='j1', conversation_id='c1', event=dict(
            type='tool_result', tool='ego_page_info', status='completed', ok=True,
            input={'url': 'https://example.com/'},
            result=json.dumps({'ok': True, 'page': {'url': 'https://example.com/', 'title': 'Example Domain'}}))))
        event = events[-1]['event']
        self.assertEqual(event['ego']['title'], 'Example Domain')
        self.assertNotIn('input', event)
        self.assertNotIn('result', event)
        manager._publish(dict(type='dsh_event', job_id='j1', conversation_id='c1',
                              event=dict(type='tool_result', tool='graph', status='completed', ok=True,
                                         input={'secret': 'x'})))
        self.assertNotIn('ego', events[-1]['event'])
        self.assertNotIn('input', events[-1]['event'])

    def test_result_event_recovers_tool_name_from_call_id(self):
        manager = DshManager()
        manager._annotate_event(dict(type='tool_call', callId='c9', tool='ego_navigate', input={'url': 'https://x.test'}))
        annotated = manager._annotate_event(dict(type='tool_result', callId='c9', status='completed',
                                                 result=json.dumps({'ok': True,
                                                                    'page': {'url': 'https://x.test/', 'title': 'X'}})))
        self.assertEqual(annotated['tool'], 'ego_navigate')
        events = []
        manager.event.connect(events.append)
        manager._publish(dict(type='dsh_event', job_id='j', conversation_id='c', event=annotated))
        self.assertEqual(events[-1]['event']['ego']['title'], 'X')
        self.assertTrue(events[-1]['event']['ego']['ok'])

    def test_agent_chat_fact_requires_browser_evidence(self):
        self.assertIsNone(web_fact_from_tool_event(dict(type='tool_result', tool='ego_click')))
        fact = web_fact_from_tool_event(dict(type='tool_result', ego=dict(
            tool='ego_navigate', url='https://example.com/', title='Example Domain', ok=True)))
        self.assertEqual(fact['title'], 'Example Domain')
        self.assertEqual(fact['url'], 'https://example.com/')
        self.assertTrue(fact['ok'])
        self.assertIn('at', fact)


class VoiceWebBridgeTests(unittest.TestCase):
    def engine(self):
        engine = AgentRealtimeVoice()
        engine._cfg = dict(DEFAULTS)
        return engine

    def test_web_facts_reach_session_instructions_and_read_web_tool(self):
        engine = self.engine()
        engine.set_web_context(dict(tool='ego_navigate', url='https://example.com/',
                                    title='Example Domain', ok=True, page_text='x' * 500))
        settings = engine._session_settings()
        self.assertIn('Example Domain', settings['instructions'])
        self.assertIn('https://example.com/', settings['instructions'])
        self.assertIn('read_web', [tool['name'] for tool in settings['tools']])
        self.assertNotIn('x' * 50, settings['instructions'])

    def test_empty_web_context_adds_nothing(self):
        engine = self.engine()
        self.assertEqual(engine._web_instructions({}), '')
        engine.set_web_context(None)
        self.assertEqual(engine._web_state(), {})

    def test_read_web_returns_recorded_fact_and_honest_empty(self):
        engine = self.engine()
        engine._accept_call(dict(name='read_web', call_id='w1', arguments='{}'))
        first = engine._commands.get_nowait()
        self.assertEqual(first[0], 'task_result')
        self.assertIn('还没有后台浏览器网页记录', first[2]['answer'])
        engine.set_web_context(dict(tool='ego_navigate', url='https://example.com/',
                                    title='Example Domain', ok=True))
        engine._accept_call(dict(name='read_web', call_id='w2', arguments='{}'))
        second = engine._commands.get_nowait()
        self.assertEqual(second[0], 'task_result')
        self.assertIn('Example Domain', second[2]['answer'])
        self.assertIn('https://example.com/', second[2]['answer'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
