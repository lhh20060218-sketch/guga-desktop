"""One real search+answer and one initiative request; synthetic memory, no mic."""
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
from unittest.mock import Mock

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from launcher import _prepare_qt
_prepare_qt()
from PyQt5.QtWidgets import QApplication
from core.agent_memory import AgentMemoryStore
from core.chat_answer import AnswerWorker
from core.proactive_conversation import ProactiveConversation


def main():
    app=QApplication.instance() or QApplication([])
    folder=ROOT/'runtime/companion-modes-qa';folder.mkdir(parents=True,exist_ok=True)
    result=dict(microphone=False,speaker=False,memory='temporary synthetic user facts',desktop_actions=False)
    worker=AnswerWorker();answers=[];ticks=[];worker.completed.connect(answers.append)
    started=time.monotonic()
    from PyQt5.QtCore import QTimer
    timer=QTimer();timer.setInterval(50);timer.timeout.connect(lambda:ticks.append(1));timer.start()
    worker.start('companion-live-probe',[],'Python 的列表和元组有什么区别？请用两三句自然口语解释。')
    deadline=started+60
    while not answers and time.monotonic()<deadline:app.processEvents();time.sleep(.01)
    timer.stop()
    if not answers:worker.cancel();raise RuntimeError('bounded answer probe timed out')
    answer=answers[0]
    result['answer']=dict(ok=answer.get('ok'),search_state=answer.get('search_state'),sources=answer.get('sources',[]),
        text=answer.get('text'),error=answer.get('error'),seconds=round(time.monotonic()-started,2),ui_ticks=len(ticks))
    with tempfile.TemporaryDirectory() as temp:
        memory=AgentMemoryStore(Path(temp)/'memory.db')
        memory.add_dialogue('001','user','我是软件工程师，我喜欢乌龙茶。')
        panel=SimpleNamespace(memory=memory,pet=None,active_profile=memory.profile('001'),active_agent_id='001',active_id='probe',
            busy=False,voice_active=False,_last_user_activity=0,runtime=SimpleNamespace(music=SimpleNamespace(playing=False)),
            store=Mock(),_show_active_bubble=Mock())
        proactive=ProactiveConversation(panel,memory);proactive.offline_speak=False
        event='synthetic-memory-probe'
        proactive.last_result=dict(event=event)
        proactive._pending_context=dict(event=event,agent_id='001',conversation_id='probe',last_activity=0)
        text=[];proactive.offline_ready.connect(lambda _,value:text.append(value))
        started=time.monotonic();proactive._compose_offline(event,proactive._prompt(panel.active_profile,memory.proactive_topics('001')))
        result['initiative']=dict(ok=bool(text),seconds=round(time.monotonic()-started,2),
            profile_facts=len(memory.facts('001')),uses_synthetic_memory=bool(text and any(x in text[0] for x in ('工程师','乌龙茶','茶'))),
            text=text[0] if text else '',state=proactive.last_result.get('state'))
        proactive.stop()
    result['ok']=bool(answer.get('ok') and answer.get('search_state')=='ok' and result['initiative']['ok'] and len(ticks)>3)
    (folder/'live-dialogue.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(ok=result['ok'],answer_ok=answer.get('ok'),search_state=answer.get('search_state'),
        source_count=len(answer.get('sources',[])),answer_seconds=result['answer']['seconds'],ui_ticks=len(ticks),
        initiative_ok=result['initiative']['ok'],memory_used=result['initiative']['uses_synthetic_memory']),ensure_ascii=False))


if __name__=='__main__':main()
