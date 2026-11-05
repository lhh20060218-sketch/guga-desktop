"""Mock Win32 boundaries; these tests never inject desktop input."""
from contextlib import nullcontext
import ctypes
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from core.bg_input import INPUT, LONG, SendInputMouse
from core.bg_live_windows import HearthstoneWindow


class FakeUser:
    def __init__(self, fail_at=None):
        self.events=[]
        self.fail_at=fail_at
        self.cursor=(0,0)

    def GetSystemMetrics(self, index):
        return {76:-1920,77:0,78:3840,79:1080}[index]

    def SendInput(self,count,pointer,size):
        packet=ctypes.cast(pointer,ctypes.POINTER(INPUT)).contents
        self.events.append(dict(flags=packet.mi.dwFlags,x=packet.mi.dx,y=packet.mi.dy,size=size))
        if packet.mi.dwFlags & 0x0001:
            self.cursor=(-1920+round(packet.mi.dx*3839/65535),round(packet.mi.dy*1079/65535))
        return 0 if len(self.events)==self.fail_at else count

    def GetCursorPos(self,pointer):
        values=ctypes.cast(pointer,ctypes.POINTER(LONG))
        values[0],values[1]=self.cursor
        return 1


def backend(user=None):
    b=HearthstoneWindow.__new__(HearthstoneWindow)
    b.mouse=SendInputMouse(user or FakeUser())
    b.physical_dpi=lambda:nullcontext()
    b.find=lambda:10
    b.geometry=lambda hwnd:(10,0,0,1000,700)
    b.cancelled=lambda:False
    b.gui=SimpleNamespace(WindowFromPoint=lambda p:10,GetAncestor=lambda hit,flag:hit,
        GetWindowLong=lambda *a:0,SetWindowPos=Mock(),IsIconic=lambda hwnd:False,
        ShowWindow=Mock(),SetForegroundWindow=Mock(),
        GetForegroundWindow=Mock(side_effect=AssertionError('Execution must not query foreground HWND/PID')))
    b.con=SimpleNamespace(GWL_EXSTYLE=-20,WS_EX_TOPMOST=8,SWP_NOMOVE=2,SWP_NOSIZE=1,
                          SWP_SHOWWINDOW=64,HWND_TOPMOST=-1,HWND_NOTOPMOST=-2)
    return b


class InputTests(unittest.TestCase):
    def test_input_abi_matches_windows(self):
        self.assertEqual(ctypes.sizeof(INPUT),40 if ctypes.sizeof(ctypes.c_void_p)==8 else 28)
        self.assertEqual(INPUT.payload.offset,8 if ctypes.sizeof(ctypes.c_void_p)==8 else 4)

    def test_virtual_desktop_negative_origin_and_endpoints(self):
        user=FakeUser();mouse=SendInputMouse(user)
        mouse.move((-1920,0));mouse.move((1919,1079))
        self.assertEqual([(e['x'],e['y']) for e in user.events],[(0,0),(65535,65535)])
        self.assertTrue(all(e['flags']==0xC001 for e in user.events))
        self.assertEqual(mouse.accepted,2)

    def test_out_of_screen_never_sends(self):
        user=FakeUser();mouse=SendInputMouse(user)
        with self.assertRaisesRegex(RuntimeError,'虚拟桌面'):mouse.move((1920,0))
        self.assertEqual(user.events,[])

    def test_sendinput_zero_is_not_success(self):
        mouse=SendInputMouse(FakeUser(fail_at=1))
        with self.assertRaisesRegex(RuntimeError,'accepted=0/1'):mouse.left_down()
        self.assertEqual(mouse.attempted,1);self.assertEqual(mouse.accepted,0)

    def test_cursor_must_arrive_before_button_down(self):
        b=backend();b.mouse.cursor_position=lambda:(20,20)
        with patch('core.bg_live_windows.time.sleep'),self.assertRaisesRegex(RuntimeError,'光标未到达'):
            b.execute(dict(phase='recruit',confidence=1,source=[.5,.4]),dict(kind='REFRESH'),b.geometry(10))
        self.assertEqual([e['flags'] for e in b.mouse.user.events],[0xC001])

    def test_geometry_enters_physical_context_at_public_boundary(self):
        b=HearthstoneWindow.__new__(HearthstoneWindow)
        context=Mock();context.__enter__=Mock();context.__exit__=Mock(return_value=False)
        b.physical_dpi=Mock(return_value=context)
        b._physical_geometry=Mock(return_value=(10,344,88,1954,1279))
        self.assertEqual(b.geometry(10),(10,344,88,1954,1279))
        context.__enter__.assert_called_once()
        context.__exit__.assert_called_once()

    def test_click_does_not_depend_on_foreground_metadata(self):
        b=backend()
        with patch('core.bg_live_windows.time.sleep'):
            result=b.execute(dict(phase='recruit',confidence=1,source=[.5,.4]),
                             dict(kind='REFRESH'),b.geometry(10))
        self.assertEqual([e['flags'] for e in b.mouse.user.events],[0xC001,2,4])
        self.assertEqual(result['accepted_events'],3)
        self.assertTrue(result['button_released'])
        self.assertFalse(result['game_effect_verified'])
        b.gui.GetForegroundWindow.assert_not_called()
        self.assertEqual(b.gui.SetWindowPos.call_args_list[0].args[1],-1)
        self.assertEqual(b.gui.SetWindowPos.call_args_list[-1].args[1],-2)

    def test_drag_moves_then_releases(self):
        b=backend()
        with patch('core.bg_live_windows.time.sleep'):
            result=b.execute(dict(phase='recruit',confidence=1,source=[.4,.3],destination=[.5,.8]),
                             dict(kind='BUY'),b.geometry(10))
        self.assertEqual(result['accepted_events'],19)
        self.assertEqual(b.mouse.user.events[-1]['flags'],4)

    def test_occluded_target_stops_before_input(self):
        b=backend();b.gui.WindowFromPoint=lambda p:20
        with self.assertRaisesRegex(RuntimeError,'遮挡'):
            b.execute(dict(phase='recruit',confidence=1,source=[.5,.4]),dict(kind='REFRESH'),b.geometry(10))
        self.assertEqual(b.mouse.user.events,[])
        self.assertFalse(b.last_input_receipt['input_sent'])

    def test_cancelled_drag_always_releases_mouse(self):
        b=backend();b.cancelled=lambda:len(b.mouse.user.events)>=4
        with patch('core.bg_live_windows.time.sleep'),self.assertRaisesRegex(RuntimeError,'停止'):
            b.execute(dict(phase='recruit',confidence=1,source=[.4,.3],destination=[.5,.8]),
                      dict(kind='PLAY'),b.geometry(10))
        self.assertEqual(b.mouse.user.events[-1]['flags'],4)
        self.assertTrue(b.last_input_receipt['button_released'])

    def test_drag_occlusion_releases_mouse(self):
        b=backend();b.gui.WindowFromPoint=lambda p:20 if len(b.mouse.user.events)>=4 else 10
        with patch('core.bg_live_windows.time.sleep'),self.assertRaisesRegex(RuntimeError,'遮挡'):
            b.execute(dict(phase='recruit',confidence=1,source=[.4,.3],destination=[.5,.8]),
                      dict(kind='BUY'),b.geometry(10))
        self.assertEqual(b.mouse.user.events[-1]['flags'],4)

    def test_failed_down_requests_release_and_records_partial_events(self):
        b=backend(FakeUser(fail_at=2))
        with self.assertRaisesRegex(RuntimeError,'SendInput'):
            b.execute(dict(phase='recruit',confidence=1,source=[.5,.4]),dict(kind='REFRESH'),b.geometry(10))
        self.assertEqual(b.mouse.user.events[-1]['flags'],4)
        self.assertEqual(b.last_input_receipt['attempted_events'],3)
        self.assertEqual(b.last_input_receipt['accepted_events'],2)

    def test_failed_release_is_not_hidden(self):
        b=backend(FakeUser(fail_at=3))
        with patch('core.bg_live_windows.time.sleep'),self.assertRaisesRegex(RuntimeError,'SendInput'):
            b.execute(dict(phase='recruit',confidence=1,source=[.5,.4]),dict(kind='REFRESH'),b.geometry(10))
        self.assertFalse(b.last_input_receipt['button_released'])

    def test_changed_geometry_stops_before_input(self):
        b=backend()
        with self.assertRaisesRegex(RuntimeError,'窗口位置'):
            b.execute(dict(phase='recruit',confidence=1,source=[.5,.4]),dict(kind='REFRESH'),(10,5,0,1000,700))
        self.assertEqual(b.mouse.user.events,[])

    def test_cached_binding_is_invalidated_on_pid_reuse(self):
        b=HearthstoneWindow.__new__(HearthstoneWindow);b._binding=(10,100)
        b.gui=SimpleNamespace(IsWindow=lambda h:True,IsWindowVisible=lambda h:True,
                              EnumWindows=lambda callback,param:None)
        b.process=SimpleNamespace(GetWindowThreadProcessId=lambda h:(11,100))
        self.assertEqual(b.find(),10)
        b.process.GetWindowThreadProcessId=lambda h:(11,200)
        with self.assertRaises(RuntimeError):b.find()
        self.assertIsNone(b._binding)

    def test_missing_zero_phase_tag_requires_running_shop_options(self):
        from core.bg_live import observed_phase
        parser=SimpleNamespace(entities={
            1:dict(CARDTYPE='GAME',STATE='RUNNING',STEP='MAIN_ACTION'),
            2:dict(CARDTYPE='PLAYER',CONTROLLER=1,PLAYSTATE='PLAYING'),
            3:dict(CARD_ID='TB_BaconShopLockAll_Button',CONTROLLER=1,ZONE='PLAY')},
            options={1:dict(entity_id=3,error_code='NONE')})
        self.assertEqual(observed_phase(parser),'recruit')
        parser.entities[1]['BACON_IN_COMBAT_PHASE']=1
        self.assertEqual(observed_phase(parser),'combat')
        del parser.entities[1]['BACON_IN_COMBAT_PHASE']
        parser.entities[1]['STEP']='MAIN_END'
        self.assertEqual(observed_phase(parser),'unknown')
        parser.entities[1]['STEP']='MAIN_ACTION'
        parser.options[1]['error_code']='INVALID'
        self.assertEqual(observed_phase(parser),'unknown')


if __name__=='__main__':unittest.main()
