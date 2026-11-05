"""Real owned-browser workflows on loopback only; no user pages or model API."""
import json
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import tempfile
import threading
import unittest
from types import SimpleNamespace

from core.browser_session import BrowserSession
from core.browser_agent import execute
from core.execution_contract import ExecutionLedger

HTML='''<!doctype html><meta charset="utf-8"><title>咕嘎表单验收</title>
<h1>日常任务测试</h1><form onsubmit="event.preventDefault(); document.querySelector('#done').textContent='提交成功：'+nameField.value;fetch('/submit',{method:'POST'});">
<label>姓名<input id="nameField" name="person" required></label>
<label>城市<select><option>北京</option><option>上海</option></select></label>
<label>备注<textarea></textarea></label><label>同意<input type="checkbox" required></label>
<label>附件<input type="file" onchange="document.querySelector('#file').textContent=this.files[0].name"></label>
<div id="file"></div><button type="button" onclick="document.querySelector('#next').hidden=false">下一步</button>
<section id="next" hidden><label>编号<input name="code" required></label><button>确认提交</button></section>
</form><p id="done"></p><a href="/report" download="report.txt">下载报告</a>
<iframe title="子表单" srcdoc="<label>子表单字段<input></label>"></iframe>'''


class Handler(BaseHTTPRequestHandler):
    submissions=0
    def log_message(self,*args):pass
    def do_GET(self):
        body=('验收报告'.encode() if self.path=='/report' else HTML.encode())
        self.send_response(200);self.send_header('Content-Type','text/plain; charset=utf-8' if self.path=='/report' else 'text/html; charset=utf-8')
        self.end_headers();self.wfile.write(body)
    def do_POST(self):
        Handler.submissions+=1;self.send_response(204);self.end_headers()


class BrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.root=Path(cls.temp.name)
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        cls.server_thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.server_thread.start()
        cls.url='http://127.0.0.1:'+str(cls.server.server_port)
        cls.cancel=threading.Event();cls.session=BrowserSession(cls.root/'browser-profile')
        cls.computer=SimpleNamespace(access=SimpleNamespace(enabled=True),browser_session=cls.session)
        cls.initial=execute(cls.computer,dict(action='session_start',url=cls.url,headless=True),cls.cancel)
        if not cls.initial.get('ok'):
            cls.session.close();cls.server.shutdown();cls.server.server_close();cls.temp.cleanup()
            raise RuntimeError(str(cls.initial))
        cls.page_id=cls.initial['page_id']
    @classmethod
    def tearDownClass(cls):
        cls.session.close();cls.server.shutdown();cls.server.server_close();cls.server_thread.join(2);cls.temp.cleanup()
    def setUp(self):
        self.state=self.call('navigate',url=self.url)
        # iframe load is allowed one bounded wait, rather than screenshot polling.
        self.state=self.call('wait',milliseconds=150)
        self.assertTrue(self.state['ok'],self.state)
    def call(self,action,**args):
        return execute(self.computer,dict(action=action,page_id=self.page_id,**args),self.cancel)
    def ref(self,label):
        return next(c['ref'] for c in self.state['controls'] if c['label']==label)
    def fill(self,fields):
        self.state=self.call('fill_form',snapshot_id=self.state['snapshot_id'],fields=fields)
        return self.state
    def test_chinese_multifield_and_multistep_submit_once(self):
        result=self.fill([dict(ref=self.ref('姓名'),kind='text',value='咕嘎😀'),
            dict(ref=self.ref('城市'),kind='select',value='上海'),
            dict(ref=self.ref('备注'),kind='text',value='第一行\n第二行'),
            dict(ref=self.ref('同意'),kind='check',checked=True)])
        self.assertTrue(result['verified'],result);self.assertEqual(len(result['fields_verified']),4)
        self.state=self.call('click',snapshot_id=self.state['snapshot_id'],ref=self.ref('下一步'),operation_id='step-next')
        self.assertTrue(self.state['ok'],self.state)
        self.assertTrue(self.fill([dict(ref=self.ref('编号'),kind='text',value='20261102')])['verified'])
        args=dict(snapshot_id=self.state['snapshot_id'],ref=self.ref('确认提交'),operation_id='submit-once')
        before=Handler.submissions;receipt=self.call('click',**args)
        self.assertTrue(receipt['ok'],receipt);self.assertFalse(receipt['verified'])
        repeated=self.call('click',**args);self.assertTrue(repeated['duplicate_suppressed'])
        verified=self.call('wait',milliseconds=200)
        self.assertIn('提交成功：咕嘎😀',verified['text']);self.assertEqual(Handler.submissions,before+1)
    def test_consumed_observation_does_not_type_twice(self):
        args=dict(snapshot_id=self.state['snapshot_id'],fields=[dict(ref=self.ref('姓名'),kind='text',value='第一次')])
        self.assertTrue(self.call('fill_form',**args)['ok'])
        result=self.call('fill_form',**args)
        self.assertFalse(result['ok']);self.assertFalse(result['action_sent'])
    def test_unknown_ref_prevalidates_entire_batch(self):
        result=self.fill([dict(ref=self.ref('姓名'),kind='text',value='不应输入'),dict(ref='missing',kind='text',value='x')])
        self.assertFalse(result['ok']);self.assertFalse(result['action_sent'])
        state=self.call('snapshot');self.assertEqual(next(c['value'] for c in state['controls'] if c['label']=='姓名'),'')
    def test_iframe_field_readback(self):
        self.assertTrue(self.fill([dict(ref=self.ref('子表单字段'),kind='text',value='跨iframe中文')])['verified'])
        field=next(c for c in self.state['controls'] if c['label']=='子表单字段')
        self.assertEqual(field['value'],'跨iframe中文');self.assertGreater(field['frame'],0)
    def test_upload_and_download_actual_bytes(self):
        file=self.root/'fixture.txt';file.write_text('本地验收文件',encoding='utf-8')
        self.state=self.call('upload',snapshot_id=self.state['snapshot_id'],ref=self.ref('附件'),path=str(file),operation_id='upload-fixture')
        self.assertTrue(self.state['ok'],self.state);self.assertIn('fixture.txt',self.state['text'])
        args=dict(snapshot_id=self.state['snapshot_id'],ref=self.ref('下载报告'),operation_id='download-report')
        result=self.call('download',**args);self.assertTrue(result['verified'],result)
        path=Path(result['download_path'])
        try:
            self.assertEqual(path.read_text(encoding='utf-8'),'验收报告')
            self.assertTrue(self.call('download',**args)['duplicate_suppressed'])
        finally:path.unlink(missing_ok=True)
    def test_explicit_page_identity_and_new_tab(self):
        other=self.call('new_tab',url=self.url+'/other');self.assertTrue(other['ok'],other)
        result=self.call('fill_form',snapshot_id=other['snapshot_id'],fields=[dict(ref='e1',kind='text',value='错误标签')])
        self.assertFalse(result['ok']);self.assertFalse(result['action_sent'])
        self.assertGreaterEqual(len(self.call('tabs')['tabs']),2)
    def test_operation_id_cannot_be_reused_for_different_action(self):
        args=dict(snapshot_id=self.state['snapshot_id'],ref=self.ref('下一步'),operation_id='reuse-guard')
        self.assertTrue(self.call('click',**args)['ok'])
        result=self.call('press',**args,keys='Enter');self.assertFalse(result['ok']);self.assertFalse(result['action_sent'])
    def test_cancel_and_access_disabled_do_not_send_input(self):
        cancel=threading.Event();cancel.set()
        self.assertFalse(execute(self.computer,dict(action='snapshot'),cancel)['action_sent'])
        denied=SimpleNamespace(access=SimpleNamespace(enabled=False))
        self.assertFalse(execute(denied,dict(action='session_start'),threading.Event())['action_sent'])


class LedgerTests(unittest.TestCase):
    def test_click_needs_explicit_readback_of_same_page(self):
        ledger=ExecutionLedger()
        ledger.record('browser',dict(action='click',page_id='p'),dict(ok=True,page_id='p',action_sent=True))
        self.assertTrue(ledger.blockers())
        ledger.record('browser',dict(action='tabs'),dict(ok=True))
        self.assertTrue(ledger.blockers())
        ledger.record('browser',dict(action='snapshot'),dict(ok=True,page_id='other',snapshot_id='s'))
        self.assertTrue(ledger.blockers())
        ledger.record('browser',dict(action='snapshot'),dict(ok=True,page_id='p',snapshot_id='s'))
        self.assertFalse(ledger.blockers())


if __name__=='__main__':unittest.main()
