"""Finite behavior tests for gestures, persisted tasks, steering and image feedback."""
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
os.environ['QT_QPA_PLATFORM']='offscreen'
from launcher import _prepare_qt
_prepare_qt()
from PyQt5.QtWidgets import QApplication
from core.embodiment import spoken_reply
from core.agent_task import TaskJournal
from core.self_agent import SelfAgent
from core.computer_control import ComputerControl
from core.desktop_access import DesktopAccess

class UpgradeTests(unittest.TestCase):
    def test_task_ack_is_short_and_never_claims_completion(self):
        from core.task_feedback import acknowledgement,tool_feedback
        ack=acknowledgement('用户希望我在Trae的文件读写.py文件中编写冒泡排序，确保写入正确位置。')
        self.assertIn('文件读写.py',ack);self.assertIn('开始',ack);self.assertNotIn('已完成',ack);self.assertLess(len(ack),85)
        self.assertIn('没有完成',tool_feedback('local_computer',{'action':'run'},{'ok':False}))
    def test_directions_removed_but_normal_speech_kept(self):
        self.assertEqual(spoken_reply('咕嘎|摇头|这个需要先看屏幕。'),('normal','head_shake','这个需要先看屏幕。'))
        self.assertEqual(spoken_reply('（点头）好呀。')[1:],('nod','好呀。'))
        self.assertEqual(spoken_reply('不要摇头，这里有说明。')[2],'不要摇头，这里有说明。')
        from core.ai_chat import parse_reply
        self.assertEqual(parse_reply('happy|nod|已经完成。'),('happy','nod','已经完成。'))

    def test_checkpoint_survives_restart_and_redacts(self):
        with tempfile.TemporaryDirectory() as folder:
            first=TaskJournal(folder);first.start('c1','测试');first.update(summary='已打开窗口',plan=['已完成：启动','待做：验证'])
            second=TaskJournal(folder)
            self.assertEqual(second.latest('c1')['summary'],'已打开窗口')
            self.assertIsNone(second.latest('other'))

    def test_voice_direction_is_removed_before_native_audio_and_gesture_deduplicates(self):
        from core.realtime_agent import AgentRealtimeVoice
        from core.realtime_voice import DEFAULTS
        voice=AgentRealtimeVoice();voice._cfg=dict(DEFAULTS);gestures=[];voice.gesture.connect(gestures.append)
        event=dict(type='response.function_call_arguments.done',response_id='r',call_id='g',name='perform_gesture',arguments='{"name":"head_shake"}')
        voice._handle_event(event);voice._handle_event(event)
        self.assertEqual(gestures,['head_shake'])
        voice._tasks['answer']='r'
        voice.resolve_task('answer',dict(ok=True,answer='咕嘎|摇头|我来看看窗口。'))
        with patch.object(voice,'_send') as send:
            while not voice._commands.empty():voice._process_command(voice._commands.get_nowait())
            outputs=[json.loads(call.args[0]['item']['output']) for call in send.call_args_list if call.args[0].get('item',{}).get('call_id')=='answer']
        self.assertEqual(outputs[0]['answer'],'我来看看窗口。')

    def test_input_requires_current_observation_and_full_access(self):
        with tempfile.TemporaryDirectory() as folder:
            access=DesktopAccess(Path(folder)/'access.json');control=ComputerControl(access)
            with self.assertRaises(ValueError):control.execute(dict(action='windows'))
            access.set_enabled(True)
            with self.assertRaises(ValueError):control.execute(dict(action='type',text='must not type'))
            cancel=threading.Event();cancel.set()
            with self.assertRaises(RuntimeError):control.execute(dict(action='windows'),cancel)

    def test_screenshot_coordinates_map_to_physical_desktop(self):
        import time,ctypes
        from types import SimpleNamespace
        control=ComputerControl(SimpleNamespace(enabled=True))
        control.observation=dict(id='fresh',hwnd=777,rect=(0,0,2560,1504),image_size=(1600,940),time=time.monotonic())
        with (patch('win32gui.GetForegroundWindow',return_value=777),patch('win32gui.GetWindowRect',return_value=(0,0,2560,1504)),
              patch.object(ctypes.windll.user32,'SetCursorPos') as move):
            control._execute(dict(action='move',observation_id='fresh',x=800,y=300))
            move.assert_called_once_with(1280,480)

    def test_uia_fast_path_uses_control_pattern_and_requires_verification(self):
        from types import SimpleNamespace
        class Access:
            enabled=True
            def run(self,*args,**kwargs):
                return dict(exit_code=0,stdout='{"name":"保存","id":"Save","type":"ControlType.Button","enabled":true,"left":1,"top":2,"right":40,"bottom":20,"performed":true,"method":"InvokePattern"}')
        control=ComputerControl(Access())
        from core.uia_backend import UIAUnavailable
        control._uia=lambda: (_ for _ in ()).throw(UIAUnavailable('进程内 UIAutomation 不可用: test'))
        with patch('win32gui.IsWindow',return_value=True),patch('win32gui.GetForegroundWindow',return_value=9):
            result=control.execute(dict(action='uia',hwnd=9,uia_name='保存',uia_operation='invoke'))
        self.assertTrue(result['input_sent']);self.assertTrue(result['needs_observe'])
        self.assertEqual(result['method'],'InvokePattern')

    def test_in_process_uia_ref_avoids_powershell_and_respects_foreground(self):
        from types import SimpleNamespace
        class Backend:
            def act(self,hwnd,operation,**kwargs):
                self.seen=(hwnd,operation,kwargs)
                return dict(input_sent=True,needs_observe=True,method='InvokePattern',control=dict(ref=kwargs['ref']))
        backend=Backend();control=ComputerControl(SimpleNamespace(enabled=True));control._uia_backend=backend
        with patch('win32gui.IsWindow',return_value=True),patch('win32gui.GetForegroundWindow',return_value=9):
            result=control.execute(dict(action='uia',hwnd=9,uia_ref='r1',uia_operation='invoke'))
        self.assertEqual(backend.seen[0:2],(9,'invoke'))
        self.assertEqual(backend.seen[2]['ref'],'r1')
        self.assertEqual(result['method'],'InvokePattern')

    def test_more_than_old_six_rounds_and_steering(self):
        class Bridge:
            def call(self,*a):return dict(ok=True,result={'ack':True})
        with tempfile.TemporaryDirectory() as folder:
            agent=SelfAgent(Bridge(),config={'api_key':'offline'})
            agent.journal=TaskJournal(folder);done=[];agent.completed.connect(done.append)
            count=[0];saw_steer=[False]
            def request(messages,*a,**kw):
                count[0]+=1
                if count[0]==2:agent.steer('增加验证步骤')
                if any('增加验证步骤' in str(m.get('content')) for m in messages):saw_steer[0]=True
                if count[0]>8:return dict(role='assistant',content='normal|head_shake|验证已完成。')
                return dict(role='assistant',content=None,tool_calls=[dict(id=str(count[0]),type='function',function=dict(name='app_state',arguments='{}'))])
            with patch.object(agent,'_request',side_effect=request):agent._run('c1',[],'测试长任务',threading.Event())
            self.assertTrue(done[0]['ok']);self.assertTrue(saw_steer[0]);self.assertEqual(count[0],9)
            self.assertEqual(done[0]['text'],'验证已完成。');self.assertEqual(done[0]['action'],'head_shake')
            self.assertEqual(TaskJournal(folder).latest('c1')['status'],'completed')

    def test_multimodal_image_follows_all_tool_receipts_and_is_not_logged(self):
        class Bridge:
            def call(self,*a):return dict(ok=True,result={})
        with tempfile.TemporaryDirectory() as folder:
            agent=SelfAgent(Bridge(),config={'api_key':'offline'});agent.journal=TaskJournal(folder)
            calls=[dict(id='a',type='function',function=dict(name='computer',arguments='{"action":"observe"}')),
                dict(id='b',type='function',function=dict(name='app_state',arguments='{}'))]
            messages_seen=[];events=[];agent.activity.connect(lambda *v:events.append(v))
            def request(messages,*a,**kw):
                if not messages_seen:
                    messages_seen.append(True);return dict(role='assistant',content=None,tool_calls=calls)
                roles=[m['role'] for m in messages]
                self.assertEqual(roles[-3:],['tool','tool','user'])
                self.assertEqual(messages[-1]['content'][1]['type'],'image_url')
                return dict(role='assistant',content='看到了。')
            with (patch.object(agent.computer,'execute',return_value=dict(_image_url='data:image/jpeg;base64,TEST',observation_id='x')),
                patch.object(agent,'_request',side_effect=request)):
                agent._run('c1',[],'看屏幕',threading.Event())
            self.assertNotIn('base64',str(events))

if __name__=='__main__':unittest.main()
