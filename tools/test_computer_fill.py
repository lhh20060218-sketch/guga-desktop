"""Atomic input regression checks; no actual user windows or keystrokes."""
import ctypes
from pathlib import Path
import sys
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch
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
        # 输入走的是模块私有 DLL 实例（_USER32_KEYS / _USER32_TEXT），不再经过
        # ctypes.windll.user32；mock 必须挂在私有实例上才数得到真实发送次数。
        self.send_input=MagicMock(side_effect=lambda count,*_:count)
        self.mouse_event=MagicMock()
        self.user32_text=SimpleNamespace(SendInput=self.send_input,mouse_event=self.mouse_event)
        self.user32_keys=SimpleNamespace(SendInput=self.send_input,MapVirtualKeyW=lambda code,flag=0:0)
        self.patches={
            'foreground':patch('win32gui.GetForegroundWindow',return_value=777),
            'rect':patch('win32gui.GetWindowRect',return_value=(0,0,2560,1504)),
            'keys_dll':patch('core.computer_control._USER32_KEYS',self.user32_keys),
            'text_dll':patch('core.computer_control._USER32_TEXT',self.user32_text),
            'cursor':patch.object(ctypes.windll.user32,'SetCursorPos'),
            'send_keys':patch('core.computer_control._send_keys')}
        self.mocks={name:p.start() for name,p in self.patches.items()}
        self.addCleanup(lambda:[p.stop() for p in reversed(list(self.patches.values()))])

    def test_click_and_unicode_type_consume_one_observation(self):
        result=self.control._execute(dict(action='fill',observation_id='fresh',x=800,y=300,text='咕嘎😀'))
        self.mocks['cursor'].assert_called_once_with(1280,480)
        self.assertEqual(result['action'],'fill')
        self.assertEqual(result['next_action'],'observe')
        self.assertEqual(self.mouse_event.call_count,2)
        self.assertEqual(self.send_input.call_count,4) # UTF-16 units, including surrogate pair
        # 点击后不再清观察（否则紧接的 type 会误报“已过期”），同一条观察继续完成本步输入。
        self.assertIsNotNone(self.control.observation)
        self.assertEqual(self.control.observation['id'],'fresh')
        again=self.control._execute(dict(action='type',observation_id='fresh',text='no duplicate'))
        self.assertEqual(again['action'],'type')

    def test_address_field_shortcut_then_type(self):
        self.control._execute(dict(action='fill',observation_id='fresh',keys='ctrl+l',text='bilibili.com'))
        self.mocks['send_keys'].assert_called_once_with([17,76])
        self.mouse_event.assert_not_called()
        self.assertEqual(self.send_input.call_count,12)

    def test_foreground_change_after_click_blocks_typing(self):
        self.mocks['foreground'].side_effect=[777,999]
        with self.assertRaisesRegex(RuntimeError,'前台窗口改变'):
            self.control._execute(dict(action='fill',observation_id='fresh',x=20,y=30,text='private'))
        self.send_input.assert_not_called()

    def test_foreground_change_during_typing_stops_remaining_text(self):
        self.mocks['foreground'].side_effect=[777,777,777,999]
        with self.assertRaisesRegex(RuntimeError,'部分文字可能已输入'):
            self.control._execute(dict(action='fill',observation_id='fresh',text='abc'))
        self.assertEqual(self.send_input.call_count,1)

    def test_invalid_locator_does_not_click_or_type(self):
        with self.assertRaises(ValueError):
            self.control._execute(dict(action='fill',observation_id='fresh',keys='ctrl+l',x=20,y=30,text='x'))
        self.mouse_event.assert_not_called();self.send_input.assert_not_called()

    def test_stale_token_sends_no_input(self):
        # 观察令牌不再比对模型回传的 ID，只校验“最近一次观察是否还新鲜”：
        # 没有观察、或观察超过 30 秒，都必须拒绝并且一个输入事件都不发。
        self.control.observation=None
        with self.assertRaisesRegex(ValueError,'消耗或过期'):
            self.control._execute(dict(action='fill',observation_id='old',text='x'))
        self.control.observation=dict(id='fresh',hwnd=777,rect=(0,0,2560,1504),
            image_size=(1600,940),time=time.monotonic()-31)
        with self.assertRaisesRegex(ValueError,'消耗或过期'):
            self.control._execute(dict(action='fill',observation_id='old',text='x'))
        self.send_input.assert_not_called()

    def test_denied_focus_is_recoverable_and_sends_no_input(self):
        import pywintypes
        self.mocks['foreground'].return_value=999
        with patch('win32gui.IsWindow',return_value=True),patch('win32gui.ShowWindow'),patch('win32gui.SetForegroundWindow',side_effect=pywintypes.error(0,'SetForegroundWindow','')):
            with self.assertRaisesRegex(RuntimeError,'尚未发送输入'):
                self.control._execute(dict(action='focus',hwnd=777))
        self.send_input.assert_not_called()

    def test_fill_requires_verification_before_completion(self):
        ledger=ExecutionLedger()
        ledger.record('computer',{'action':'fill'},{'ok':True,'result':{'input_sent':True}})
        self.assertTrue(ledger.blockers())
        ledger.record('computer',{'action':'observe'},{'ok':True,'result':{'observation_id':'new'}})
        self.assertEqual(ledger.blockers(),[])

if __name__=='__main__':unittest.main()
