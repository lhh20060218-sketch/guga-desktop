import sqlite3,tempfile,unittest
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core.chat_workspace import ChatWorkspace


class ChatAgentMigrationTests(unittest.TestCase):
    def test_old_database_migrates_and_agent_views_are_separate(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'chat.sqlite3'
            db=sqlite3.connect(path)
            db.executescript('''CREATE TABLE projects(id TEXT PRIMARY KEY,name TEXT NOT NULL);
                CREATE TABLE conversations(id TEXT PRIMARY KEY,project_id TEXT,name TEXT NOT NULL,archived INTEGER DEFAULT 0,updated TEXT DEFAULT CURRENT_TIMESTAMP);
                INSERT INTO conversations(id,name) VALUES ('old','旧对话');''')
            db.close();store=ChatWorkspace(path)
            old=store.conversation('old');self.assertEqual(old['agent_id'],'001')
            second=store.create_conversation('002 的对话',agent_id='002')
            self.assertEqual(len(store.snapshot(agent_id='001')['conversations']),1)
            self.assertEqual(store.snapshot(agent_id='002')['conversations'][0]['id'],second)
            self.assertEqual(len(store.snapshot()['conversations']),2)

    def test_appending_keeps_each_conversation_isolated(self):
        with tempfile.TemporaryDirectory() as folder:
            store=ChatWorkspace(Path(folder)/'chat.sqlite3')
            a=store.create_conversation('A',agent_id='001');b=store.create_conversation('B',agent_id='002')
            store.append(a,'user','一');store.append(b,'user','二')
            self.assertEqual([x['content'] for x in store.messages(a)],['一'])
            self.assertEqual([x['content'] for x in store.messages(b)],['二'])


if __name__=='__main__':unittest.main()
