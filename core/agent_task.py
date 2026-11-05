"""Durable, bounded task checkpoints, without credentials or screenshot payloads."""
import json
from pathlib import Path
import time
import uuid
from core.desktop_access import ROOT,redact_value

class TaskJournal:
    def __init__(self,root=None):
        self.root=Path(root or ROOT/'runtime/agent-tasks');self.data={}
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
        self.data['updated']=time.time();self.root.mkdir(parents=True,exist_ok=True)
        target=self.root/(self.data['id']+'.json');temporary=target.with_suffix('.tmp')
        temporary.write_text(json.dumps(redact_value(self.data),ensure_ascii=False,indent=2),encoding='utf-8');temporary.replace(target)
