"""Offline checks for Go conversation routing; no credentials or external API."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from launcher import _prepare_qt
_prepare_qt()
from core.ai_chat import AIChatEngine


class ConversationRoutingTests(unittest.TestCase):
    def make_engine(self, url):
        with patch.object(AIChatEngine, '_load_config', return_value={
            'base_url': url, 'api_key': 'test-only', 'model': 'test-model',
        }):
            return AIChatEngine()

    def test_go_turns_share_session_until_history_reset(self):
        engine = self.make_engine('https://opencode.ai/inference/go/openai/v1/')
        with patch('core.ai_chat.requests.post') as post, patch(
                'core.ai_chat.AIChatWorker.start'):
            post.return_value.status_code = 200
            post.return_value.json.return_value = {
                'choices': [{'message': {'content': 'normal|none|OK'}}]}
            ids = []
            for question in ('first', 'second'):
                engine._start(question, '', None)
                engine._worker.run()
                ids.append(post.call_args.kwargs['headers']['x-opencode-session'])
            self.assertEqual(ids[0], ids[1])
            self.assertEqual(post.call_args.args[0],
                'https://opencode.ai/inference/go/openai/v1/chat/completions')
            self.assertEqual(post.call_args.kwargs['headers']['User-Agent'],
                             'GugaDesktopPet/1.0')
            engine.reset_history()
            engine._start('new conversation', '', None)
            engine._worker.run()
            self.assertNotEqual(ids[0],
                post.call_args.kwargs['headers']['x-opencode-session'])

    def test_other_provider_keeps_existing_headers(self):
        engine = self.make_engine('https://open.bigmodel.cn/api/paas/v4')
        with patch('core.ai_chat.requests.post') as post, patch(
                'core.ai_chat.AIChatWorker.start'):
            post.return_value.status_code = 200
            post.return_value.json.return_value = {
                'choices': [{'message': {'content': 'normal|none|OK'}}]}
            engine._start('hello', '', None)
            engine._worker.run()
            self.assertNotIn('x-opencode-session', post.call_args.kwargs['headers'])


if __name__ == '__main__':
    unittest.main()
