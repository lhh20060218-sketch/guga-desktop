"""Local, transactional project/conversation storage. No credentials are stored here."""
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path


class ChatWorkspace:
    def __init__(self, path=None):
        self.path = Path(path or Path(__file__).resolve().parents[1] / 'runtime/chat/workspace.sqlite3')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY, project_id TEXT REFERENCES projects(id), agent_id TEXT NOT NULL DEFAULT '001',
                    name TEXT NOT NULL, archived INTEGER NOT NULL DEFAULT 0,
                    updated TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY, conversation_id TEXT NOT NULL REFERENCES conversations(id),
                    role TEXT NOT NULL, content TEXT NOT NULL,
                    created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
                CREATE TABLE IF NOT EXISTS preferences (key TEXT PRIMARY KEY, value TEXT);
            ''')
            columns={row[1] for row in db.execute('PRAGMA table_info(conversations)')}
            if 'agent_id' not in columns:
                db.execute("ALTER TABLE conversations ADD COLUMN agent_id TEXT NOT NULL DEFAULT '001'")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(str(self.path), timeout=5)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def name(value):
        value = str(value).strip()
        if not value or len(value) > 80:
            raise ValueError('名称需要 1—80 个字符')
        return value

    def snapshot(self, archived=False, agent_id=None):
        with self.connect() as db:
            if agent_id is None:
                conversations=[dict(r) for r in db.execute(
                    'SELECT * FROM conversations WHERE archived=? ORDER BY updated DESC,rowid DESC',(int(archived),))]
            else:
                conversations=[dict(r) for r in db.execute(
                    'SELECT * FROM conversations WHERE archived=? AND agent_id=? ORDER BY updated DESC,rowid DESC',
                    (int(archived),str(agent_id)))]
            return dict(projects=[dict(r) for r in db.execute('SELECT * FROM projects ORDER BY rowid')],
                        conversations=conversations)

    def create_project(self, name):
        ident = uuid.uuid4().hex
        with self.connect() as db:
            db.execute('INSERT INTO projects VALUES (?,?)', (ident, self.name(name)))
        return ident

    def create_conversation(self, name='新对话', project_id=None, agent_id='001'):
        ident = uuid.uuid4().hex
        with self.connect() as db:
            db.execute('INSERT INTO conversations(id,project_id,agent_id,name) VALUES (?,?,?,?)',
                       (ident, project_id, str(agent_id), self.name(name)))
        return ident

    def conversation(self, ident):
        with self.connect() as db:
            row = db.execute('SELECT * FROM conversations WHERE id=?', (ident,)).fetchone()
        if not row:
            raise ValueError('会话不存在')
        return dict(row)

    def rename(self, kind, ident, name):
        table = {'project': 'projects', 'conversation': 'conversations'}[kind]
        with self.connect() as db:
            if db.execute(f'UPDATE {table} SET name=? WHERE id=?', (self.name(name), ident)).rowcount != 1:
                raise ValueError('项目或会话不存在')

    def move(self, ident, project_id):
        with self.connect() as db:
            if db.execute('UPDATE conversations SET project_id=? WHERE id=?', (project_id, ident)).rowcount != 1:
                raise ValueError('会话不存在')

    def archive(self, ident, archived=True):
        with self.connect() as db:
            if db.execute('UPDATE conversations SET archived=? WHERE id=?', (int(archived), ident)).rowcount != 1:
                raise ValueError('会话不存在')

    def append(self, ident, role, content):
        if role not in ('user', 'assistant', 'tool', 'system'):
            raise ValueError('无效消息类型')
        with self.connect() as db:
            db.execute('INSERT INTO messages(conversation_id,role,content) VALUES (?,?,?)', (ident, role, content))
            db.execute('UPDATE conversations SET updated=CURRENT_TIMESTAMP WHERE id=?', (ident,))

    def messages(self, ident, limit=200):
        with self.connect() as db:
            return [dict(r) for r in reversed(list(db.execute(
                'SELECT id,role,content,created FROM messages WHERE conversation_id=? ORDER BY id DESC LIMIT ?',
                (ident, limit))))]

    def preference(self, key, value=None):
        with self.connect() as db:
            if value is not None:
                db.execute('INSERT OR REPLACE INTO preferences VALUES (?,?)', (key, value))
                return value
            row = db.execute('SELECT value FROM preferences WHERE key=?', (key,)).fetchone()
            return row[0] if row else None
