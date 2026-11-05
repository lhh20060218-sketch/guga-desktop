"""Real bounded local process tests; no user apps launched and no real keys read."""
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core.desktop_access import DesktopAccess,redact,redact_value
from core.authorized_apps import AuthorizedApps


class DesktopTests(unittest.TestCase):
    def test_audit_preserves_nested_arguments_with_quotes(self):
        value=dict(content='api_key = "example"\nprint("hello")',nested=[dict(password='example',count=2)])
        cleaned=redact_value(value)
        self.assertEqual(json.loads(json.dumps(cleaned)),cleaned)
        self.assertNotIn('example',str(cleaned))
        self.assertEqual(cleaned['nested'][0]['count'],2)

    def test_disabled_by_default_and_user_toggle_persists(self):
        with tempfile.TemporaryDirectory() as folder:
            access=DesktopAccess(Path(folder)/'access.json')
            self.assertFalse(access.enabled)
            with self.assertRaises(ValueError):access.execute(dict(action='list',path=folder))
            access.set_enabled(True)
            self.assertTrue(DesktopAccess(access.state_path).enabled)
            access.set_enabled(False)
            self.assertFalse(access.enabled)

    def test_source_write_validates_syntax_and_preserves_backup(self):
        with tempfile.TemporaryDirectory() as folder:
            access=DesktopAccess(Path(folder)/'access.json');access.set_enabled(True)
            path=Path(folder)/'example.py';path.write_text('value = 1\n',encoding='utf-8')
            with self.assertRaises(SyntaxError):access.execute(dict(action='write',path=str(path),content='def broken('))
            self.assertEqual(path.read_text(),'value = 1\n')
            result=access.execute(dict(action='write',path=str(path),content='value = 2\n'))
            self.assertEqual(Path(result['backup']).read_text(),'value = 1\n')
            self.assertEqual(path.read_text(),'value = 2\n')
            self.assertTrue(result['syntax_checked'])

    def test_read_redacts_keys(self):
        with tempfile.TemporaryDirectory() as folder:
            access=DesktopAccess(Path(folder)/'access.json');access.set_enabled(True)
            path=Path(folder)/'sample.json';key='sk-'+'a'*32
            path.write_text(json.dumps(dict(api_key=key,value=42)),encoding='utf-8')
            content=access.execute(dict(action='read',path=str(path)))['content']
            self.assertNotIn(key,content);self.assertIn('42',content)

    def test_full_access_can_open_exact_executable_without_manual_grant(self):
        with tempfile.TemporaryDirectory() as folder:
            apps=AuthorizedApps(Path(folder)/'apps.json')
            path=Path(folder)/'fake.exe';path.write_bytes(b'not executable')
            apps.access.set_enabled(True)
            with patch.object(apps,'available',return_value={}),patch('core.authorized_apps.os.startfile') as launch:
                self.assertTrue(apps.open(str(path))['launch_requested'])
                launch.assert_called_once_with(str(path))
                with self.assertRaises(ValueError):apps.open('powershell.exe -Command something')

    def test_real_command_success_and_failure_exit_codes(self):
        with tempfile.TemporaryDirectory() as folder:
            access=DesktopAccess(Path(folder)/'access.json');access.set_enabled(True)
            result=access.execute(dict(action='run',command="Write-Output 'GUGA_LOCAL_TOOL_OK'",cwd=folder,seconds=5))
            self.assertEqual(result['exit_code'],0,result)
            self.assertIn('GUGA_LOCAL_TOOL_OK',result['stdout'])
            result=access.execute(dict(action='run',command='exit 7',cwd=folder,seconds=5))
            self.assertEqual(result['exit_code'],7)

    def test_timeout_and_cancel_stop_owned_command(self):
        with tempfile.TemporaryDirectory() as folder:
            access=DesktopAccess(Path(folder)/'access.json');access.set_enabled(True)
            began=time.monotonic()
            result=access.execute(dict(action='run',command='Start-Sleep -Seconds 20',cwd=folder,seconds=1))
            self.assertEqual(result['stopped'],'timeout');self.assertLess(time.monotonic()-began,5)
            cancel=threading.Event();timer=threading.Timer(.3,cancel.set);timer.start()
            try:
                result=access.execute(dict(action='run',command='Start-Sleep -Seconds 20',cwd=folder,seconds=5),cancel)
                self.assertEqual(result['stopped'],'cancelled')
            finally:timer.cancel()

if __name__=='__main__':unittest.main()
