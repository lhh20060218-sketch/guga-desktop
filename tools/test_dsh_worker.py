import os
from pathlib import Path
import sys
import threading
import time
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from launcher import _prepare_qt
_prepare_qt()
from PyQt5.QtWidgets import QApplication
from core.dsh_worker import DshManager

APP=QApplication.instance() or QApplication([])


class FakeStdin:
    def write(self,text):self.text=text
    def close(self):pass


class FakeStdout:
    def __init__(self,lines,done):self.lines=lines;self.done=done
    def __iter__(self):
        for line in self.lines:yield line
        self.done.set()


class FakeStderr:
    def __iter__(self):return iter(())


class FakeProc:
    def __init__(self,lines,returncode=0):
        self.stdin=FakeStdin();self.returncode=returncode;self.pid=999;self.done=threading.Event()
        self.stdout=FakeStdout(lines,self.done);self.stderr=FakeStderr()
    def poll(self):return self.returncode if self.done.is_set() else None
    def wait(self,timeout=None):return self.returncode


class DshTests(unittest.TestCase):
    def test_streams_session_status_and_final_without_qt_coupling(self):
        lines=[
            '{"type":"session","sessionId":"s1"}\n',
            '{"type":"status","phase":"turn_start","turn":1}\n',
            '{"type":"status","phase":"step_start","turn":1,"step":1}\n',
            '{"type":"final","text":"已完成测试"}\n']
        manager=DshManager();events=[];manager.event.connect(events.append)
        with patch('core.dsh_worker.subprocess.Popen',return_value=FakeProc(lines)):
            manager.start('复杂任务',conversation_id='c1',seconds=30)
            manager.thread.join(3)
            for _ in range(20):APP.processEvents();time.sleep(.01)
        self.assertTrue(any(e.get('type')=='dsh_event' for e in events))
        done=[e for e in events if e.get('type')=='dsh_completed']
        self.assertEqual(len(done),1);self.assertTrue(done[0]['ok']);self.assertEqual(done[0]['text'],'已完成测试')
        self.assertEqual(done[0]['session_id'],'s1')

    def test_status_and_invalid_budget(self):
        manager=DshManager();self.assertFalse(manager.status()['running'])
        with self.assertRaises(ValueError):manager.start('',seconds=30)

    def test_sidecar_receives_member_method_memory_and_emits_owner(self):
        from core.agent_identity import PERSONALITIES
        lines=['{"type":"final","text":"尚未验证"}\n']
        proc=FakeProc(lines);manager=DshManager();events=[];manager.event.connect(events.append)
        with patch('core.dsh_worker.subprocess.Popen',return_value=proc):
            manager.start('审查项目',conversation_id='fish-chat',seconds=30,
                profile=dict(agent_id='002',personality=PERSONALITIES['002']),memory_context='FISH_ONLY_MEMORY')
            manager.thread.join(3)
            APP.processEvents()
        self.assertIn('FISH_ONLY_MEMORY',proc.stdin.text)
        self.assertIn('先复现问题',proc.stdin.text)
        self.assertTrue(events);self.assertTrue(all(e['agent_id']=='002' for e in events))

    def test_launch_failure_still_emits_exactly_one_terminal_event(self):
        manager=DshManager();events=[];manager.event.connect(events.append)
        with patch('core.dsh_worker.subprocess.Popen',side_effect=FileNotFoundError):
            manager.start('测试',conversation_id='c1',seconds=30)
            manager.thread.join(3);APP.processEvents()
        done=[e for e in events if e.get('type')=='dsh_completed']
        self.assertEqual(len(done),1);self.assertFalse(done[0]['ok'])


if __name__=='__main__':unittest.main()
