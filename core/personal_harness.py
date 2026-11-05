"""Durable personal tickets and reviewed experience, adapted from Super-agent concepts.

DSH owns execution; this store owns task identity/recovery, never model weights.
"""
import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from core.agent_memory import safe_text

ROOT = Path(__file__).resolve().parents[1]
_RECOVERED=set()


class PersonalHarness:
    def __init__(self, path=None):
        self.path = Path(path or ROOT/'runtime/personal-harness/tasks.sqlite3')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS tickets (
                    id TEXT PRIMARY KEY, agent TEXT, conversation TEXT, goal TEXT,
                    cwd TEXT, session TEXT, state TEXT, summary TEXT,
                    evidence TEXT NOT NULL DEFAULT '[]', created REAL, updated REAL);
                CREATE TABLE IF NOT EXISTS receipts (
                    id INTEGER PRIMARY KEY, ticket TEXT, tool TEXT, action TEXT,
                    ok INTEGER, summary TEXT, created REAL);
                CREATE TABLE IF NOT EXISTS lessons (
                    id TEXT PRIMARY KEY, agent TEXT, ticket TEXT, recipe TEXT,
                    state TEXT, created REAL);
                CREATE TABLE IF NOT EXISTS inputs (
                    id INTEGER PRIMARY KEY, ticket TEXT, content TEXT, delivered INTEGER DEFAULT 0);
            ''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(str(self.path), timeout=5)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def recover(self):
        # Resume is explicit: never replay side effects after a process crash.
        with self.connect() as db:
            return db.execute("UPDATE tickets SET state='interrupted', updated=? WHERE state='running'",
                              (time.time(),)).rowcount

    def recover_once(self):
        key=str(self.path.resolve())
        if key in _RECOVERED:return 0
        count=self.recover();_RECOVERED.add(key)
        return count

    def create(self, agent, conversation, goal, cwd):
        ident = uuid.uuid4().hex
        now = time.time()
        with self.connect() as db:
            db.execute('INSERT INTO tickets VALUES (?,?,?,?,?,?,?, ?,?,?,?)',
                       (ident, str(agent), str(conversation), safe_text(goal), str(cwd), None,
                        'running', 'DSH 正在启动，尚未完成任务', '[]', now, now))
        return self.get(ident)

    def get(self, ident):
        with self.connect() as db:
            row = db.execute('SELECT * FROM tickets WHERE id=?', (ident,)).fetchone()
        if not row:
            raise ValueError('任务不存在')
        data = dict(row)
        data['evidence'] = json.loads(data['evidence'])
        return data

    def update(self, ident, **values):
        allowed = {'session', 'state', 'summary', 'evidence'}
        if not values or set(values)-allowed:
            raise ValueError('任务更新字段无效')
        values = dict(values)
        if 'summary' in values:
            values['summary'] = safe_text(values['summary'])[:4000]
        if 'evidence' in values:
            values['evidence'] = json.dumps(values['evidence'], ensure_ascii=False)
        values['updated'] = time.time()
        with self.connect() as db:
            db.execute('UPDATE tickets SET '+','.join(k+'=?' for k in values)+' WHERE id=?',
                       (*values.values(), ident))
        return self.get(ident)

    def recent(self, agent, conversation=None, limit=8):
        with self.connect() as db:
            query='SELECT * FROM tickets WHERE agent=?'
            args=[str(agent)]
            if conversation is not None:
                query+=' AND conversation=?'; args.append(str(conversation))
            rows=db.execute(query+' ORDER BY created DESC LIMIT ?', (*args, max(1,min(20,int(limit))))).fetchall()
        return [dict(row) for row in rows]

    def receipt(self, ident, name, args, value):
        from core.task_feedback import tool_feedback
        ok=value.get('ok') is True
        summary=tool_feedback(name,args,value)
        with self.connect() as db:
            db.execute('INSERT INTO receipts(ticket,tool,action,ok,summary,created) VALUES (?,?,?,?,?,?)',
                       (ident,name,str(args.get('action',''))[:60],int(ok),summary,time.time()))
        self.update(ident,summary=summary)

    def receipt_count(self, ident):
        with self.connect() as db:
            return db.execute('SELECT COUNT(*) FROM receipts WHERE ticket=? AND ok=1',(ident,)).fetchone()[0]

    def add_input(self,ident,content):
        with self.connect() as db:
            count=db.execute('SELECT COUNT(*) FROM inputs WHERE ticket=? AND delivered=0',(ident,)).fetchone()[0]
            if count>=8:raise ValueError('追加要求已达8条，请等待当前轮结束')
            db.execute('INSERT INTO inputs(ticket,content) VALUES (?,?)',(ident,safe_text(content)))

    def pending_inputs(self,ident):
        with self.connect() as db:
            return [dict(r) for r in db.execute('SELECT id,content FROM inputs WHERE ticket=? AND delivered=0 ORDER BY id',(ident,))]

    def acknowledge_inputs(self,ident,ids):
        with self.connect() as db:
            for value in ids:db.execute('UPDATE inputs SET delivered=1 WHERE ticket=? AND id=?',(ident,int(value)))

    def take_inputs(self,ident):
        with self.connect() as db:
            rows=db.execute('SELECT content FROM inputs WHERE ticket=? AND delivered=0 ORDER BY id',(ident,)).fetchall()
            db.execute('UPDATE inputs SET delivered=1 WHERE ticket=?',(ident,))
        return '\n'.join(r['content'] for r in rows)

    def checkpoint(self, agent, conversation):
        rows=self.recent(agent,conversation,1)
        if not rows:
            return ''
        row=rows[0]
        return safe_text(json.dumps({k:row[k] for k in ('id','goal','state','summary','cwd')},ensure_ascii=False))[:4000]

    def propose(self, agent, ticket, recipe):
        row=self.get(ticket)
        if row['agent']!=str(agent):
            raise ValueError('不能使用其他成员的任务生成经验')
        recipe=safe_text(recipe)[:3000]
        if not recipe:
            raise ValueError('经验内容不能为空')
        ident=uuid.uuid4().hex
        with self.connect() as db:
            db.execute('INSERT INTO lessons VALUES (?,?,?,?,?,?)',
                       (ident,str(agent),ticket,recipe,'candidate',time.time()))
        return dict(id=ident,state='candidate',message='已保存经验候选，尚未启用')

    def lessons(self, agent, active=False):
        with self.connect() as db:
            rows=db.execute('SELECT * FROM lessons WHERE agent=?'+(" AND state='active'" if active else '')+
                            ' ORDER BY created DESC LIMIT 12',(str(agent),)).fetchall()
        return [dict(row) for row in rows]

    def review(self, agent, ident, success):
        row=self.get(ident)
        if row['agent']!=str(agent) or row['state']=='running':
            raise ValueError('任务仍在运行或不属于当前成员')
        self.update(ident,state='verified' if success else 'failed')
        # Only human-reviewed successful trajectories can become enabled recipes.
        # Recipes are data, not arbitrary Python/plugins or permission changes.
        with self.connect() as db:
            db.execute('UPDATE lessons SET state=? WHERE ticket=?',
                       ('active' if success and self.receipt_count(ident)>0 else 'candidate',ident))
        return self.get(ident)

    def disable_lesson(self, agent, ident):
        with self.connect() as db:
            if db.execute("UPDATE lessons SET state='disabled' WHERE id=? AND agent=?",(ident,str(agent))).rowcount!=1:
                raise ValueError('经验不存在')


def use_dsh(prompt, image=False, backend='auto', workflow=None):
    """Compatibility wrapper for the local-first route policy."""
    from core.task_router import choose_task_route
    return choose_task_route(prompt,image,backend,workflow).get('executor')=='dsh'
