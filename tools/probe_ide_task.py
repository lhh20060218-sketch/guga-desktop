"""Finite real configured-model acceptance task in the explicitly selected IDE."""
import argparse
import json
import os
from pathlib import Path
import sys
import time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
os.environ['QT_QPA_PLATFORM']='offscreen'
from launcher import _prepare_qt
_prepare_qt()
from PyQt5.QtWidgets import QApplication
from core.self_agent import SelfAgent
from core.desktop_access import ROOT as SOURCE_ROOT

parser=argparse.ArgumentParser();parser.add_argument('--path',required=True);parser.add_argument('--hwnd',required=True,type=int)
args=parser.parse_args();target=Path(args.path).resolve(strict=True)
original=target.read_text(encoding='utf-8-sig')
backup=SOURCE_ROOT/'runtime/self-updates/ide-task-acceptance'/target.name
backup.parent.mkdir(parents=True,exist_ok=True);backup.write_text(original,encoding='utf-8')
app=QApplication([])
class Bridge:
    def call(self,name,arguments,cancel):
        if name=='app_state':return dict(ok=True,result={'target':str(target)})
        return dict(ok=False,error='本次验收只允许屏幕控制及目标文件验证')
agent=SelfAgent(Bridge());agent.config=dict(agent.config,task_budget_seconds=110)
execute=agent.computer.execute
def guarded(arguments,cancel=None):
    if arguments.get('action') in ('focus','observe') and arguments.get('hwnd',args.hwnd)!=args.hwnd:
        raise ValueError('本次验收只操作用户明确指定的TRAE窗口')
    return execute(arguments,cancel)
agent.computer.execute=guarded
results=[];last=['']
def progress(ident,event):
    summary=event.get('summary','')
    if summary!=last[0]:print('PROGRESS:',summary,flush=True);last[0]=summary
agent.progress.connect(progress)
def activity(ident,event):
    print('TOOL:',event['name'],event['arguments'].get('action'),event['arguments'].get('keys',''),event['result'].get('ok'),event['result'].get('error','')[:200],flush=True)
agent.activity.connect(activity)
agent.completed.connect(results.append)
prompt=f'''请在已经打开的TRAE CN编辑器中实际完成冒泡排序，让用户看到编辑过程。
当前目标窗口hwnd={args.hwnd}，唯一目标文件：{target}。
用户已明确授权直接接着当前文件完成。先focus/observe当前窗口，核对编辑器，不能扫描磁盘。
已有函数名maopaosort(m)，保留此前所有课程笔记和文件读写示例，只修复当前末尾这个函数：交换要写m[j],m[j+1]=m[j+1],m[j]，每轮未交换时break，最终return m。
必须通过computer在当前编辑器中输入并Ctrl+S保存，不可以local_computer.write/PowerShell/脚本静默替代编辑。
可以使用computer.editor_select_tail（line=34）一次选择从当前def maopaosort行首到末尾，然后observe核对选区，再computer.type整段带正确缩进的完整函数。之后重新observe并hotkey ctrl+s保存。必须先观察确认选区，保留函数前内容。
每一次输入都要引用最新observe的ID；操作会消耗ID，之后重新observe。快捷键用enter/esc/ctrl+s等，不用不受支持的按键名。每次发一条输入操作，不能复用观察ID批量输入。
修改后重新observe，核对代码；用local_computer只读取目标文件确认保存成功。不要执行课程笔记中的其他代码，不要关闭IDE。给出真实结果，不要声称完成未确认操作。
本次任务最多4分钟，到时停止并汇报。'''
print('MODEL:',agent.config.get('model'),'TARGET:',str(target),flush=True)
agent.start('ide-bubble-sort-acceptance',[],prompt)
deadline=time.monotonic()+120
try:
    while not results and time.monotonic()<deadline:
        app.processEvents();time.sleep(.02)
    if not results:agent.cancel();raise RuntimeError('验收超时，已请求取消')
    print('RESULT:',json.dumps(results[0],ensure_ascii=False),flush=True)
finally:
    if agent.worker and agent.worker.is_alive():agent.cancel();agent.worker.join(8)
    agent.mcp.close() if hasattr(agent.mcp,'close') else None
