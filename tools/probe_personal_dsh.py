"""Bounded real DSH/MCP acceptance in an isolated workspace, no voice or desktop input."""
import argparse,json,os,sys,time,uuid
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from launcher import _prepare_qt
_prepare_qt()
from PyQt5.QtCore import QCoreApplication,QObject
from core.agent_memory import AgentMemoryStore
from core.chat_workspace import ChatWorkspace
from core.dsh_worker import DshManager
from core.self_agent import SelfAgent,ToolBridge
from ui.mcp_bridge import SelfMCPBridge


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--real',action='store_true');parser.add_argument('--resume',action='store_true')
    parser.add_argument('--media-source');parser.add_argument('--media-subtitles')
    options=parser.parse_args()
    folder=ROOT/'runtime/personal-harness-probe'/time.strftime('%Y%m%d-%H%M%S');folder.mkdir(parents=True)
    app=QCoreApplication([])
    os.environ['GUGA_MCP_PIPE']='guga-self-probe-'+uuid.uuid4().hex
    class Pet(QObject):
        def _ensure_agent_panel(self):return panel
    pet=Pet();panel=QObject(pet)
    panel.store=ChatWorkspace(folder/'chat.sqlite3');panel.memory=AgentMemoryStore(folder/'memory.sqlite3')
    panel.bridge=ToolBridge(lambda name,args: {'pet':{'visible':False}} if name=='app_state' else {},panel)
    panel.agent=SelfAgent(panel.bridge,panel)
    from core.media_workflow import MediaWorkflow
    manager=DshManager(panel);manager.tools_enabled=True;panel.runtime=SimpleNamespace(dsh=manager,media=MediaWorkflow(folder/'media'))
    bridge=SelfMCPBridge(pet)
    if not bridge.available:raise RuntimeError('isolated MCP pipe not available')
    overlay=manager._overlay('config-only')
    import subprocess,shutil
    cli=Path.home()/'.local/bin/node_modules/@deepseek-ai/dsh/lib/bin.js'
    check=subprocess.run([shutil.which('node'),str(cli),'--profile','headless','--patch',str(overlay),'--dump-config'],
                         capture_output=True,encoding='utf-8',errors='replace',timeout=30,creationflags=subprocess.CREATE_NO_WINDOW)
    report=dict(config_ok=check.returncode==0 and 'guga-personal-mcp' in check.stdout,model_calls=0,voice_calls=0)
    if not report['config_ok']:
        from core.desktop_access import redact
        report['config_error']=redact(check.stderr[-1500:])
    if options.real and report['config_ok']:
        panel.memory.remember('001','测试报告请用简短中文；标记为蓝企鹅',kind='user_preference')
        (folder/'input.txt').write_text('SOURCE_MARKER_7419',encoding='utf-8')
        events=[];manager.event.connect(events.append)
        def run(task):
            manager.start(task,'probe-chat',cwd=folder,seconds=150,
                          profile=dict(agent_id='001',display_name='咕嘎'),memory_context='测试任务，真实偏好通过personal_memory召回。')
            end=time.monotonic()+155
            while manager.thread.is_alive() and time.monotonic()<end:
                app.processEvents();time.sleep(.02)
            if manager.thread.is_alive():manager.stop();manager.thread.join(6)
            app.processEvents()
            return manager.status()
        report['model_calls']+=1
        normal_task=('隔离验收：必须只使用 mcp__guga__ 工具完成。先personal_memory(recall,query=测试报告)，'
                  '再local_computer读取input.txt，将原文标记和记忆中报告标记一起写进report.txt，再回读report.txt核验。'
                  '随后personal_memory(propose_lesson,content=文件写入后回读核对内容)保存经验候选，最后task_report(ready)简短报告。'
                  '不要用内置shell绕过MCP桥，所有路径相对本工作目录的绝对路径为：'+str(folder))
        media_task=('这是三秒合成样片的隔离处理验收，不是用户真实录制，不要打开任何软件或联网发布。'
                    '必须只使用mcp__guga__工具：先media_workflow(inspect)，随后task_report(progress,milestone=true)说明已核对样片；'
                    '再media_workflow(render,path='+str(Path(options.media_source).resolve())+',subtitles='+str(Path(options.media_subtitles).resolve())+')，'
                    '用wait有限等待成片，准备好后media_workflow(submission)按字幕内容拟标题和简介；'
                    'task_report(progress,milestone=true)说明成片和清单已准备好。最后task_report(needs_input)询问是否发布，然后结束等待用户。'
                    '不要调用内置shell或用local_computer替代媒体工具，不要真的发布。') if options.media_source else ''
        first=run(media_task or normal_task)
        output=(folder/'report.txt').read_text(encoding='utf-8-sig') if (folder/'report.txt').exists() else ''
        report.update(first_task_state=first.get('ticket_state'),receipts=first.get('receipt_count'),
                      file_verified='SOURCE_MARKER_7419' in output and '蓝企鹅' in output,
                      candidate_saved=bool(manager.archive.lessons('001')),session_created=bool(first.get('session_id')))
        if options.media_source:
            media=panel.runtime.media.status()
            manifests=list((folder/'media').glob('*/submission.json'))
            report.update(media_mode=True,media_ready=media.get('state')=='ready',media_output_exists=Path(media.get('output','')).is_file(),
                          submission_prepared=bool(manifests),important_reports=sum(1 for e in events if e.get('event',{}).get('type')=='report' and e['event'].get('milestone')),
                          waits_for_user=first.get('ticket_state')=='needs_input')
        if options.resume and first.get('session_id'):
            report['model_calls']+=1
            second=run('继续上个任务：不要重新写report.txt。只通过mcp__guga__local_computer回读report.txt，'
                       '核对SOURCE_MARKER_7419和蓝企鹅，然后task_report(ready)交付。')
            report.update(resume_same_session=second.get('session_id')==first.get('session_id'),
                          resumed_state=second.get('ticket_state'),resumed_receipts=second.get('receipt_count'))
        report['events']=[{'type':e.get('type'),'event_type':e.get('event',{}).get('type'),
                           'ok':e.get('ok'),'error':e.get('error','')[:1200]} for e in events if e.get('type')=='dsh_completed' or e.get('event',{}).get('type')=='tool_receipt']
    report['ok']=report['config_ok'] and (not options.real or report.get('file_verified') and report.get('candidate_saved') and report.get('first_task_state')=='awaiting_review')
    if options.media_source:
        report['ok']=all(report.get(k) for k in ('config_ok','media_ready','media_output_exists','submission_prepared','important_reports','waits_for_user'))
    if options.resume:report['ok']=bool(report['ok'] and report.get('resume_same_session') and report.get('resumed_receipts',0)>0)
    (folder/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    bridge.close();print(json.dumps(dict(report=report,path=str(folder/'result.json')),ensure_ascii=False))
    return 0 if report['ok'] else 1


if __name__=='__main__':sys.exit(main())
