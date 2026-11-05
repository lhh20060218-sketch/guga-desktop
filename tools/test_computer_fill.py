"""Atomic input regression checks; no actual user windows or keystrokes."""
import ctypes
from pathlib import Path
import sys
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core.computer_control import ComputerControl
from core.execution_contract import ExecutionLedger

class FillTests(unittest.TestCase):
    def test_open_then_type_is_not_swallowed_by_fast_app_launcher(self):
        from core.fast_commands import match
        for text in ('打开豆包浏览器输入哔哩哔哩','帮我打开记事本写一段文章','打开浏览器并编辑文档'):
            with self.subTest(text=text):self.assertFalse(match(text)['matched'])
        self.assertTrue(match('帮我打开浏览器')['matched'])

    def setUp(self):
        self.control=ComputerControl(SimpleNamespace(enabled=True))
        self.control.observation=dict(id='fresh',hwnd=777,rect=(0,0,2560,1504),image_size=(1600,940),time=time.monotonic())
        self.patches=[patch('win32gui.GetForegroundWindow',return_value=777),
            patch('win32gui.GetWindowRect',return_value=(0,0,2560,1504)),
            patch.object(ctypes.windll.user32,'SendInput',return_value=2),
            patch.object(ctypes.windll.user32,'SetCursorPos'),
            patch.object(ctypes.windll.user32,'mouse_event'),
            patch('core.computer_control._send_keys')]
        self.mocks=[p.start() for p in self.patches]
        self.addCleanup(lambda:[p.stop() for p in reversed(self.patches)])

    def test_click_and_unicode_type_consume_one_observation(self):
        result=self.control._execute(dict(action='fill',observation_id='fresh',x=800,y=300,text='咕嘎😀'))
        self.mocks[3].assert_called_once_with(1280,480)
        self.assertEqual(self.mocks[4].call_count,2)
        self.assertEqual(self.mocks[2].call_count,4) # UTF-16 units, including surrogate pair
        self.assertIsNone(self.control.observation)
        self.assertEqual(result['action'],'fill')
        self.assertEqual(result['next_action'],'observe')
        with self.assertRaisesRegex(ValueError,'消耗或过期'):
            self.control._execute(dict(action='type',observation_id='fresh',text='no duplicate'))

    def test_address_field_shortcut_then_type(self):
        self.control._execute(dict(action='fill',observation_id='fresh',keys='ctrl+l',text='bilibili.com'))
        self.mocks[5].assert_called_once_with([17,76])
        self.mocks[4].assert_not_called()
        self.assertEqual(self.mocks[2].call_count,12)

    def test_foreground_change_after_click_blocks_typing(self):
        self.mocks[0].side_effect=[777,999]
        with self.assertRaisesRegex(RuntimeError,'前台窗口改变'):
            self.control._execute(dict(action='fill',observation_id='fresh',x=20,y=30,text='private'))
        self.mocks[2].assert_not_called()

    def test_foreground_change_during_typing_stops_remaining_text(self):
        self.mocks[0].side_effect=[777,777,777,999]
        with self.assertRaisesRegex(RuntimeError,'部分文字可能已输入'):
            self.control._execute(dict(action='fill',observation_id='fresh',text='abc'))
        self.assertEqual(self.mocks[2].call_count,1)

    def test_invalid_locator_does_not_click_or_type(self):
        with self.assertRaises(ValueError):
            self.control._execute(dict(action='fill',observation_id='fresh',keys='ctrl+l',x=20,y=30,text='x'))
        self.mocks[4].assert_not_called();self.mocks[2].assert_not_called()

    def test_stale_token_sends_no_input(self):
        with self.assertRaises(ValueError):
            self.control._execute(dict(action='fill',observation_id='old',text='x'))
        self.mocks[2].assert_not_called()

    def test_denied_focus_is_recoverable_and_sends_no_input(self):
        import pywintypes
        self.mocks[0].return_value=999
        with patch('win32gui.IsWindow',return_value=True),patch('win32gui.ShowWindow'),patch('win32gui.SetForegroundWindow',side_effect=pywintypes.error(0,'SetForegroundWindow','')):
            with self.assertRaisesRegex(RuntimeError,'尚未发送输入'):
                self.control._execute(dict(action='focus',hwnd=777))
        self.mocks[2].assert_not_called()

    def test_fill_requires_verification_before_completion(self):
        ledger=ExecutionLedger()
        ledger.record('computer',{'action':'fill'},{'ok':True,'result':{'input_sent':True}})
        self.assertTrue(ledger.blockers())
        ledger.record('computer',{'action':'observe'},{'ok':True,'result':{'observation_id':'new'}})
        self.assertEqual(ledger.blockers(),[])

if __name__=='__main__':unittest.main()
