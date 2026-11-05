"""One bounded real-model request proving memory-grounded off-call initiative."""
import json,os,sys,tempfile,time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from launcher import _prepare_qt
_prepare_qt()
from PyQt5.QtWidgets import QApplication
from core.agent_memory import AgentMemoryStore
from core.proactive_conversation import ProactiveConversation

app=QApplication([])
folder=ROOT/'runtime/voice-assistant-qa/proactive';folder.mkdir(parents=True,exist_ok=True)


class Settings:
    def value(self,key,default=None,type=None):
        return {'multiagent/proactive_idle_seconds':1,'multiagent/proactive_cooldown_seconds':1,
                'multiagent/proactive_offline_speak':False}.get(key,default)


with tempfile.TemporaryDirectory() as tmp:
    memory=AgentMemoryStore(Path(tmp)/'memory.sqlite3')
    memory.add_dialogue('001','user','我最近在集中整理 AI 学习资料，喜欢简短直接的中文进展报告。')
    panel=SimpleNamespace(memory=memory,voice=None,voice_active=False,busy=False,
        runtime=SimpleNamespace(music=SimpleNamespace(playing=False),dsh=None),active_profile=memory.profile('001'),
        pet=SimpleNamespace(_config=SimpleNamespace(_s=Settings()),_say_with_expression=Mock()),
        active_agent_id='001',active_id='probe',store=Mock(),_last_user_activity=time.monotonic()-100,
        _show_active_bubble=Mock())
    proactive=ProactiveConversation(panel,memory);proactive.started_at=time.monotonic()-100
    got=[];proactive.offline_ready.connect(lambda event,text:got.append(text))
    from core.proactive_conversation import office_music
    diagnostics=dict(idle_gap=time.monotonic()-max(proactive.started_at,panel._last_user_activity),
        interval=proactive.interval_seconds,busy=panel.busy,music=office_music(panel).playing,
        voice_active=panel.voice_active,composing=proactive._compose_active,
        modal=QApplication.activeModalWidget() is not None)
    trigger=proactive.tick();deadline=time.monotonic()+22
    while not got and time.monotonic()<deadline:app.processEvents();time.sleep(.05)
    reply=got[0] if got else ''
    result=dict(triggered=bool(trigger),mode=(trigger or {}).get('mode'),reply_received=bool(reply),
        reply_length=len(reply),used_memory_markers={'AI':('AI' in reply),'报告':('报告' in reply)},
        state=(proactive.status().get('last_result') or {}).get('state'),diagnostics=diagnostics)
    (folder/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False),flush=True)
    proactive.stop();app.quit()
