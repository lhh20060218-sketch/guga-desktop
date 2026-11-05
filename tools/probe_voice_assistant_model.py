"""At most 3 real Go model requests against simulated browser failures; no desktop input."""
import json,os,sys,threading,time
from pathlib import Path
from unittest.mock import Mock,patch

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from launcher import _prepare_qt
_prepare_qt()
from PyQt5.QtWidgets import QApplication
from core.self_agent import SelfAgent,TOOLS
from core.agent_task import TaskJournal
from core.task_router import choose_task_route
import requests

app=QApplication([])
folder=ROOT/'runtime/voice-assistant-qa/model-failure';folder.mkdir(parents=True,exist_ok=True)
cfg=json.loads((ROOT/'ai_config.json').read_text(encoding='utf-8'))
cfg['task_budget_seconds']=40
bridge=Mock();bridge.call.return_value=dict(ok=True,result=dict(pet=dict(visible=False)))
agent=SelfAgent(bridge,config=cfg);agent.journal=TaskJournal(folder/'tasks')
request=agent._request;post=requests.post;count=0;started=time.monotonic();done=[]
agent.completed.connect(done.append)

def bounded_request(*args,**kwargs):
    global count
    count+=1
    if count>3 or time.monotonic()-started>35:raise RuntimeError('模型验收预算已到，未执行任何真实桌面操作')
    return request(*args,**kwargs)

def bounded_post(*args,**kwargs):
    kwargs['timeout']=(6,30)
    return post(*args,**kwargs)

fake=dict(ok=False,code='target_ambiguous',action_sent=False,
          error='检测到两个浏览器窗口，无法确定要关闭哪一个；没有发送关闭操作。请先切到目标页面')
with patch('core.self_agent.TOOLS',[x for x in TOOLS if x['function']['name']=='browser']), \
     patch.object(agent,'_request',side_effect=bounded_request), \
     patch('core.self_agent.requests.post',side_effect=bounded_post), \
     patch('core.browser_agent.execute',return_value=fake) as browser, \
     patch.object(agent.computer,'execute',side_effect=RuntimeError('本次夹具禁止真实桌面访问')):
    prompt='请关闭我现在正在看的那个网页'
    agent._run('voice-assistant-controlled-model',[],prompt,threading.Event(),{'_route':choose_task_route(prompt)})
result=done[0]
out=dict(ok=bool(not result['ok'] and browser.called and '两个浏览器窗口' in result.get('error','')),
         model_requests=count,browser_calls=browser.call_count,
         browser_actions=[x.args[1].get('action') for x in browser.call_args_list],
         explanation=result.get('error'),elapsed_seconds=round(time.monotonic()-started,2),real_desktop_input=False)
(folder/'result.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(out,ensure_ascii=False))
