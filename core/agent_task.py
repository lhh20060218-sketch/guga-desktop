"""Durable, bounded task checkpoints, without credentials or screenshot payloads."""
import json
from pathlib import Path
import time
import uuid
from core.desktop_access import ROOT,redact_value
from core import guga_paths

class TaskJournal:
    def __init__(self,root=None):
        self.root=Path(root or guga_paths.RUNTIME/'agent-tasks');self.data={}
        self.save_error=''
    def start(self,conversation,goal):
        self.data=dict(id=uuid.uuid4().hex,conversation=conversation,goal=goal,status='running',plan=[],events=[],updated=time.time())
        workspace=(self.root/self.data['id']/'workspace').resolve();workspace.mkdir(parents=True,exist_ok=True)
        self.data['workspace']=str(workspace)
        self.save();return self.data['id']
    def latest(self,conversation):
        if not self.root.exists():return None
        candidates=sorted(self.root.glob('*.json'),key=lambda p:p.stat().st_mtime,reverse=True)[:100]
        for path in candidates:
            try:
                data=json.loads(path.read_text(encoding='utf-8'))
                if data.get('conversation')==conversation:return data
            except (OSError,ValueError):continue
        return None
    def update(self,**values):
        self.data.update(values);self.save()
    def event(self,name,result):
        self.data['events']=(self.data.get('events',[])+[dict(tool=name,ok=result.get('ok'),time=time.time())])[-120:]
        self.save()
    def save(self):
        """落盘台账。失败不抛异常、不静默：记在 save_error 里给界面显示。"""
        self.data['updated']=time.time()
        try:
            self.root.mkdir(parents=True,exist_ok=True)
            target=self.root/(self.data['id']+'.json');temporary=target.with_suffix('.tmp')
            temporary.write_text(json.dumps(redact_value(self.data),ensure_ascii=False,indent=2),encoding='utf-8')
            temporary.replace(target)
            self.save_error=''
            return True
        except OSError as exc:
            self.save_error='任务台账写入失败：%s'%str(exc)[:160]
            return False


# ---- 聊天回复前强制读台账（第五项） -------------------------------------------
#: 台账不可读时必须原样出现在回复里的句子；不允许用猜测顶上。
LEDGER_MISSING_PHRASE = '我现在读不到任务状态'


def ledger_snapshot(root=None, conversation=None):
    """只读当前任务台账（最新一份，或指定会话）：步骤/状态/失败码/产物/证据数。"""
    base = Path(root) if root else (guga_paths.RUNTIME / 'agent-tasks')
    try:
        if not base.exists():
            return dict(ok=False, reason='台账目录不存在：%s' % base, source='')
        candidates = sorted(base.glob('*.json'),
                            key=lambda p: p.stat().st_mtime, reverse=True)[:100]
    except OSError as exc:
        return dict(ok=False, reason='台账目录读不到：%s' % str(exc)[:120], source='')
    if not candidates:
        return dict(ok=False, reason='还没有任何任务台账', source='')
    picked = None
    for path in candidates:
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        if conversation and str(data.get('conversation') or '') != str(conversation):
            continue
        picked = (path, data)
        break
    if picked is None:
        return dict(ok=False, reason='没有匹配当前会话的任务台账', source='')
    path, data = picked
    chain = data.get('chain') if isinstance(data.get('chain'), dict) else {}
    failure = (data.get('last_tool_failure')
               if isinstance(data.get('last_tool_failure'), dict) else {})
    contract = data.get('contract') if isinstance(data.get('contract'), dict) else {}
    try:
        evidence_count = int(contract.get('evidence_count') or 0)
    except (TypeError, ValueError):
        evidence_count = 0
    return dict(ok=True, source=str(path), task_id=str(data.get('id') or ''),
                goal=str(data.get('goal') or ''), status=str(data.get('status') or ''),
                summary=str(data.get('summary') or ''),
                step=chain.get('step'), total=chain.get('total'),
                chain_status=str(chain.get('status') or ''),
                failure_code=str(failure.get('code') or ''),
                failure_stage=str(failure.get('stage') or ''),
                failure_error=str(failure.get('error') or ''),
                next_action=str(failure.get('next_action') or ''),
                artifact=str(data.get('artifact') or ''),
                evidence_count=evidence_count,
                updated=float(data.get('updated') or 0))


def ledger_note(snapshot=None, **kwargs):
    """把台账渲染成可直接注入聊天上下文的事实文本（读不到就写明读不到）。"""
    snap = snapshot if isinstance(snapshot, dict) else ledger_snapshot(**kwargs)
    if not snap.get('ok'):
        return ('【当前任务台账（只读）】%s（原因：%s）。'
                '本轮不许编造步骤、进度、失败码或产物；用户问进度时必须先原样说明'
                '“%s”。'
                % (LEDGER_MISSING_PHRASE, snap.get('reason') or '台账不可读',
                   LEDGER_MISSING_PHRASE))
    lines = ['【当前任务台账（来自本机 runtime/agent-tasks，只读）】',
             '任务：%s' % (snap.get('goal') or '(未记录)'),
             '状态：%s' % (snap.get('status') or '未知')]
    if snap.get('total'):
        lines.append('步骤：第 %s/%s 步（%s）'
                     % (snap.get('step') if snap.get('step') is not None else '?',
                        snap.get('total'), snap.get('chain_status') or '未知'))
    if snap.get('failure_code'):
        line = '失败码：%s' % snap['failure_code']
        if snap.get('failure_stage'):
            line += '（阶段：%s）' % snap['failure_stage']
        lines.append(line)
    if snap.get('failure_error'):
        lines.append('失败原因：%s' % snap['failure_error'][:200])
    if snap.get('artifact'):
        lines.append('产物：%s' % snap['artifact'])
    if snap.get('evidence_count'):
        lines.append('证据条数：%s' % snap['evidence_count'])
    if snap.get('next_action'):
        lines.append('下一步：%s' % snap['next_action'])
    if snap.get('summary'):
        lines.append('摘要：%s' % snap['summary'][:300])
    lines.append('以上是本机台账真实字段；没写到的不要补，没证据只能说“未执行/未确认”。')
    return '\n'.join(lines)
