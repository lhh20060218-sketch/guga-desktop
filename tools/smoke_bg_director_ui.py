"""Real Qt voice -> brain -> background director -> narration queue, with fake game I/O."""
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
os.environ['QT_QPA_PLATFORM']='offscreen'
from launcher import _prepare_qt
_prepare_qt()
from PyQt5.QtCore import QSettings,QTimer
from PyQt5.QtWidgets import QApplication
from core.chat_workspace import ChatWorkspace
from core.realtime_agent import AgentRealtimeVoice
from core.realtime_voice import DEFAULTS
from ui.agent_chat import AgentChatWindow
from ui.pet_window import PetWindow

app=QApplication([])
with tempfile.TemporaryDirectory() as folder, patch('core.keyboard_hook.KeyboardHook.start'), patch('ui.tts_engine.TTSEngine.speak'):
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,folder)
    pet=PetWindow()
    for timer in pet.findChildren(QTimer):timer.stop()
    panel=AgentChatWindow(pet,ChatWorkspace(Path(folder)/'chat.sqlite3'))
    pet._agent_panel=panel
    panel.agent.config={'api_key':'offline-only'}
    record=dict(verified=True,action=dict(kind='BUY'),reason='保留场面战力')
    def session_factory(callback):
        class Session:
            stop=threading.Event()
            reader=SimpleNamespace(parser=SimpleNamespace(entities={}),poll=lambda:[])
            def run(self,*args):
                callback(dict(type='action_confirmed',record=record))
                return dict(records=[record])
        return Session()
    panel.runtime.battleground._factory=session_factory
    cfg=dict(DEFAULTS,api_key='offline-only')
    responses=[dict(role='assistant',content=None,tool_calls=[dict(id='bg-task',type='function',
                function=dict(name='battleground',arguments='{"action":"step","seconds":10}'))]),
               dict(role='assistant',content='后台任务已受理，稍后根据回执复盘。')]
    with patch('core.realtime_voice.load_settings',return_value=cfg),patch.object(AgentRealtimeVoice,'start'), \
         patch.object(panel.agent,'_request',side_effect=lambda *args,**kw:responses.pop(0)):
        panel.voice_button.setChecked(True)
        voice=panel.voice;voice._cfg=cfg
        voice._handle_event(dict(type='response.function_call_arguments.done',response_id='user-r',
            call_id='voice-task',name='ask_deepseek',arguments='{"request":"执行一步战棋操作"}'))
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            app.processEvents()
            if (not panel.busy and not panel.runtime.battleground.status()['running'] and
                    any(m['role']=='system' and '日志确认了 1 步' in m['content'] for m in panel.store.messages(panel.active_id))):
                break
            time.sleep(.01)
        assert not panel.busy
        assert panel.runtime.battleground.status()['confirmed']==1, (panel.runtime.battleground.status(),panel.store.messages(panel.active_id))
        assert not responses
        with patch.object(voice,'_send') as send,patch.object(voice,'_record_usage'):
            voice._last_activity=time.monotonic()-5
            while not voice._commands.empty():voice._process_command(voice._commands.get_nowait())
            voice._handle_event(dict(type='response.created',response=dict(id='answer-r')))
            voice._handle_event(dict(type='response.done',response=dict(id='answer-r')))
            voice._process_command(None)
            events=[c.args[0] for c in send.call_args_list]
            assert any(e.get('item',{}).get('type')=='function_call_output' for e in events)
            assert any('【战棋后台事件，仅播报】' in json.dumps(e,ensure_ascii=False) for e in events)
        panel.stop_turn()
        assert panel.runtime.battleground._stop.is_set()
        assert not panel.voice_active
    panel.close();pet.hide();pet.deleteLater();app.processEvents()
    print('PASS: native voice tool -> DeepSeek -> background step -> verified audit -> same-call narration; stop closes control',flush=True)
