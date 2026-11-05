"""Finite offline tests: durability, tool feedback, cancellation and MCP wire protocol."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from launcher import _prepare_qt
_prepare_qt()
from core.chat_workspace import ChatWorkspace
from core.self_agent import SelfAgent
from core.mcp_host import StdioMCP, MCPHost


class WorkspaceTests(unittest.TestCase):
    def test_persistence_move_rename_archive_and_isolation(self):
        with tempfile.TemporaryDirectory() as folder:
            store = ChatWorkspace(Path(folder) / 'chat.sqlite3')
            project = store.create_project('学习')
            a = store.create_conversation(project_id=project)
            b = store.create_conversation('另一段')
            store.append(a, 'user', '独立上下文')
            store.rename('conversation', a, '新名称')
            store.move(a, None)
            store.archive(a)
            reopened = ChatWorkspace(store.path)
            self.assertEqual(reopened.messages(b), [])
            self.assertEqual(reopened.messages(a)[0]['content'], '独立上下文')
            self.assertIsNone(reopened.conversation(a)['project_id'])
            self.assertEqual(reopened.snapshot(True)['conversations'][0]['name'], '新名称')
            reopened.archive(a, False)
            self.assertEqual(len(reopened.snapshot()['conversations']), 2)
            with self.assertRaises(Exception):
                store.move(a, 'missing-project')

    def test_tool_result_is_fed_back_and_self_ask_is_bounded(self):
        class Bridge:
            def call(self, name, args, cancel):
                return dict(ok=True, result={'actual_x': 45})
        agent = SelfAgent(Bridge(), config={'api_key': 'test'})
        requests = []
        results = []
        agent.completed.connect(results.append)
        def call(name, arguments, ident):
            return dict(id=ident, type='function', function=dict(name=name, arguments=json.dumps(arguments)))
        responses = [
            dict(role='assistant', content=None, tool_calls=[call('pet_control', {'action': 'move', 'x': 45, 'y': 20}, 'a')]),
            dict(role='assistant', content=None, tool_calls=[call('self_ask', {'question': '检查结果'}, 'b'), call('self_ask', {'question': '重复'}, 'c')]),
            dict(role='assistant', content='结果合理'),
            dict(role='assistant', content='happy|bounce|已移动')]
        def request(messages, session, tools=True):
            requests.append((list(messages), tools))
            return responses.pop(0)
        with patch.object(agent, '_request', side_effect=request):
            agent._run('session-test', [], '移动自己', threading.Event())
        self.assertTrue(results[0]['ok'])
        self.assertIn('actual_x', requests[1][0][-1]['content'])
        self.assertEqual(sum(not tools for _, tools in requests), 1)
        feedback=[m['content'] for messages,_ in requests for m in messages if m.get('role')=='tool']
        self.assertTrue(any('本轮已自问一次' in str(content) for content in feedback))

    def test_cancel_prevents_tools_after_network_return(self):
        class Bridge:
            def call(self, *args):
                raise AssertionError('Cancelled tool must not execute')
        agent = SelfAgent(Bridge(), config={'api_key': 'test'})
        cancel = threading.Event()
        results = []
        agent.completed.connect(results.append)
        def request(*args):
            cancel.set()
            return dict(content=None, tool_calls=[dict(id='a', function=dict(name='pet_control', arguments='{}'))])
        with patch.object(agent, '_request', side_effect=request):
            agent._run('cancel-test', [], '停止', cancel)
        self.assertFalse(results[0]['ok'])

    def test_real_stdio_mcp_handshake_and_tools(self):
        client = StdioMCP(dict(command=sys.executable, args=[str(ROOT / 'tools/guga_mcp_server.py')]))
        try:
            client.initialize()
            names = {t['name'] for t in client.request('tools/list')['tools']}
            self.assertEqual(names, {'app_state', 'pet_control', 'workspace', 'applications','voice_session','screen_share'})
        finally:
            client.close()
        self.assertIsNotNone(client.proc.poll())

    def test_mcp_permissions_are_explicit(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'mcp.json'
            path.write_text(json.dumps({'mcpServers': {'demo': {'enabled': True, 'allowed_tools': ['read']}}}))
            host = MCPHost(path)
            with self.assertRaisesRegex(ValueError, 'allowed_tools'):
                host.execute(dict(action='call', server='demo', tool='delete'))
            with self.assertRaisesRegex(ValueError, '本次确认'):
                host.execute(dict(action='call', server='demo', tool='read'))

    def test_only_explicitly_granted_app_can_launch(self):
        from core.authorized_apps import AuthorizedApps
        with tempfile.TemporaryDirectory() as folder:
            apps = AuthorizedApps(Path(folder) / 'apps.json')
            executable = Path(folder) / 'demo.exe'
            executable.write_bytes(b'offline-test-only')
            with patch('core.authorized_apps.os.startfile') as launch:
                with self.assertRaises(ValueError):
                    apps.open('未授权软件')
                launch.assert_not_called()
                apps.grant('测试软件', str(executable))
                self.assertTrue(apps.open('测试软件')['launch_requested'])
                launch.assert_called_once_with(str(executable.resolve()))
                apps.revoke('测试软件')
                with self.assertRaises(ValueError):
                    apps.open('测试软件')

    def test_owner_voice_script_uses_persistent_verified_console(self):
        from core.authorized_apps import AuthorizedApps
        with tempfile.TemporaryDirectory() as folder:
            apps=AuthorizedApps(Path(folder)/'apps.json')
            class Proc:
                pid=321
                def poll(self):return None
            with patch('core.authorized_apps.subprocess.Popen',return_value=Proc()) as launch, \
                 patch('core.authorized_apps.time.sleep'):
                result=apps.open('录入主人声音的脚本')
            self.assertTrue(result['verified_running'])
            self.assertEqual(result['pid'],321)
            args=launch.call_args.args[0]
            self.assertEqual(args[0],'cmd.exe');self.assertIn('/k',args);self.assertIn('call',args)
            self.assertTrue(args[-1].endswith('录入主人声音.bat'))

    def test_script_that_exits_immediately_is_reported_as_failure(self):
        from core.authorized_apps import AuthorizedApps
        with tempfile.TemporaryDirectory() as folder:
            apps=AuthorizedApps(Path(folder)/'apps.json')
            class Proc:
                pid=322
                def poll(self):return 7
            with patch('core.authorized_apps.subprocess.Popen',return_value=Proc()), \
                 patch('core.authorized_apps.time.sleep'):
                with self.assertRaisesRegex(RuntimeError,'退出码 7'):
                    apps.open('录入主人声音')

    def test_continuous_voice_releases_microphone_between_turns(self):
        import types
        import numpy as np
        from core.agent_voice import AgentVoice
        events = []
        voice = AgentVoice()
        class Stream:
            def __init__(self, **kwargs):
                self.callback = kwargs['callback']
            def __enter__(self):
                events.append('open')
                self.callback(np.array([1000, -1000], dtype=np.int16).tobytes(), 2, None, None)
                return self
            def __exit__(self, *args):
                events.append('release')
        class Recognizer:
            def __init__(self, *args): pass
            def AcceptWaveform(self, data): return True
            def Result(self): return json.dumps({'text': '咕嘎打开记事本'})
        fake_sd = types.SimpleNamespace(RawInputStream=Stream)
        fake_vosk = types.SimpleNamespace(Model=lambda path: object(), KaldiRecognizer=Recognizer)
        def utterance(text):
            events.append(text)
            self.assertFalse(voice.listening.is_set())
            voice.stop()
        voice.utterance.connect(utterance)
        with tempfile.TemporaryDirectory() as folder, patch.dict(sys.modules, {'sounddevice': fake_sd, 'vosk': fake_vosk}), \
                patch('core.asr.MODEL_DIR', folder), patch('core.asr._pick_input_device', return_value=0):
            voice.listening.set()
            voice._run()
        self.assertEqual(events, ['open', '咕嘎打开记事本', 'release'])


if __name__ == '__main__':
    unittest.main()
