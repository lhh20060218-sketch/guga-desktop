"""Offscreen real Qt integration. No API requests, microphone capture or TTS."""
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from launcher import _prepare_qt
_prepare_qt()
from PyQt5.QtCore import QTimer, QSettings
from PyQt5.QtGui import QFontDatabase
from PyQt5.QtWidgets import QApplication
from core.chat_workspace import ChatWorkspace
from ui.agent_chat import AgentChatWindow
from ui.pet_window import PetWindow

app = QApplication([])
for path in ('C:/Windows/Fonts/msyh.ttc', 'C:/Windows/Fonts/msyhbd.ttc'):
    QFontDatabase.addApplicationFont(path)
with tempfile.TemporaryDirectory() as folder, patch('core.keyboard_hook.KeyboardHook.start'), patch('ui.tts_engine.TTSEngine.speak'):
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, folder)
    pet = PetWindow()
    for timer in pet.findChildren(QTimer):
        timer.stop()
    panel = AgentChatWindow(pet, ChatWorkspace(Path(folder) / 'chat.sqlite3'))
    pet._agent_panel = panel
    project = panel.store.create_project('学习计划')
    panel.store.create_conversation('Python 每日练习', project)
    panel.store.create_conversation('一个新的想法')
    panel.store.rename('conversation', panel.active_id, '让咕嘎动起来')
    panel.show()
    panel.agent.config = {'api_key': 'offline-only'}
    responses = [dict(role='assistant', content=None, tool_calls=[
        dict(id='a', type='function', function=dict(name='pet_control', arguments=json.dumps({'action': 'move', 'x': 120, 'y': 90}))),
        dict(id='b', type='function', function=dict(name='workspace', arguments=json.dumps({'action': 'create_project', 'name': '创作空间'})))]),
        dict(role='assistant', content='咕嘎～本鹅已经挪好位置，也建好“创作空间”了。你可以继续用语音指挥我。')]
    with patch.object(panel.agent, '_request', side_effect=lambda *args, **kwargs: responses.pop(0)):
        panel.send('把自己移动到左上角，再新建一个“创作空间”项目。')
        deadline = time.monotonic() + 8
        while panel.busy and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(.01)
        assert not panel.busy, 'Agent did not complete'
        assert (pet.x(), pet.y()) == (120, 90)
        assert len(panel.store.snapshot()['projects']) == 2
        assert len([m for m in panel.store.messages(panel.active_id) if m['role'] == 'tool']) == 2
        assert panel.store.messages(panel.active_id)[-1]['role'] == 'assistant'
        panel.refresh_tree()
        app.processEvents()
        output = ROOT / 'runtime/chat/agent-preview.png'
        output.parent.mkdir(parents=True, exist_ok=True)
        panel.grab().save(str(output))
        print('PASS: floating UI, queued real pet movement, project creation, audit and reply', flush=True)
    # Real MCP client => stdio server => local pipe => Qt => same application runtime.
    from core.mcp_host import StdioMCP
    import threading
    outcome = []
    def mcp_probe():
        client = StdioMCP(dict(command=sys.executable, args=[str(ROOT / 'tools/guga_mcp_server.py')]))
        try:
            client.initialize()
            outcome.append(client.request('tools/call', dict(name='app_state', arguments={})))
        finally:
            client.close()
    probe = threading.Thread(target=mcp_probe, daemon=True)
    probe.start()
    deadline = time.monotonic() + 12
    while probe.is_alive() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(.01)
    assert outcome and not outcome[0].get('isError'), outcome
    assert 'current_conversation_id' in outcome[0]['content'][0]['text']
    print('PASS: MCP host / stdio server / user-only pipe / live Qt state roundtrip', flush=True)
    # The default voice button must use Qwen E2E, delegate to the existing real
    # agent loop, and send its result back to Qwen without Edge TTS.
    from core.realtime_agent import AgentRealtimeVoice
    from core.realtime_voice import DEFAULTS
    cfg = dict(DEFAULTS, api_key='offline-only')
    with patch('core.realtime_voice.load_settings', return_value=cfg), patch.object(AgentRealtimeVoice, 'start') as start:
        panel.voice_button.setChecked(True)
        assert isinstance(panel.voice, AgentRealtimeVoice)
        assert pet._realtime_voice is panel.voice
        start.assert_called_once_with(cfg)
        panel.voice._cfg = cfg
        panel.read_aloud.setChecked(True)
        with patch.object(panel.agent, '_request', return_value=dict(role='assistant', content='DeepSeek 测试答案：5。')), \
             patch.object(pet, '_say_with_expression') as local_speech:
            panel.voice.transcript.emit('饲养员', '二加三等于多少？')
            panel.voice._handle_event(dict(type='response.function_call_arguments.done', response_id='voice-r1',
                call_id='voice-c1', name='ask_deepseek', arguments=json.dumps({'request': '二加三等于多少？'})))
            deadline = time.monotonic() + 5
            while panel.busy and time.monotonic() < deadline:
                app.processEvents()
                time.sleep(.01)
            assert not panel.busy
            local_speech.assert_not_called()
            with patch.object(panel.voice, '_send') as native_send:
                while not panel.voice._commands.empty():
                    panel.voice._process_command(panel.voice._commands.get_nowait())
                packet = native_send.call_args_list[0].args[0]
                assert packet['item']['call_id'] == 'voice-c1'
                ack=json.loads(packet['item']['output'])
                assert ack['execution_pending'] is True and '开始处理' in ack['answer']
                assert any('DeepSeek 测试答案：5。' in speech for speech,_ in panel.voice._notices), 'Final answer must be queued separately after immediate acknowledgement'
        assert panel.close_button.isVisible()
        panel.close_button.click()
        assert not panel.isVisible()
        assert pet.isVisible(), 'Closing chat must keep the pet running'
        assert panel.voice._stop.is_set(), 'Closing chat must stop Qwen capture'
        panel.show()
        panel.reject()
        assert not panel.isVisible(), 'Esc/reject must use the same cleanup path'
    print('PASS: Qwen default voice -> DeepSeek -> native result; close button/Esc stop call and keep pet', flush=True)
    pet._self_mcp.close()
    panel.shutdown()
    panel.hide()
    pet._anim.stop()
    pet._status.stop()
    pet._tray.hide()
    pet.hide()
    app.quit()
