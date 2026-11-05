"""Bounded offline Qt regression for floating chat, attachments and temporary queries."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import base64,json,sys,tempfile,time,threading,unittest
from pathlib import Path
from unittest.mock import patch,MagicMock
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from launcher import _prepare_qt
_prepare_qt()
from PyQt5.QtCore import QTimer,QSettings,Qt,QPoint
from PyQt5.QtGui import QPixmap,QPainter,QColor,QFont,QTextCursor
from PyQt5.QtWidgets import QApplication
from PyQt5.QtTest import QTest
from core.chat_workspace import ChatWorkspace
from core.self_agent import SelfAgent
from core.chat_presentation import user_content,is_progress_ack
from core import screen_question
from ui.pet_window import PetWindow
from ui.agent_chat import AgentChatWindow
from ui.screen_tools import ExplainDialog,RegionCapture,SelectionBar,image_uri,png_data

APP=QApplication.instance() or QApplication([])


class FloatingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder=tempfile.TemporaryDirectory();cls.path=Path(cls.folder.name)
        QSettings.setDefaultFormat(QSettings.IniFormat);QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,cls.folder.name)
        cls.patches=[patch('core.keyboard_hook.KeyboardHook.start'),patch('ui.tts_engine.TTSEngine.speak'),patch('core.browser_launch.default_executable',return_value=None)]
        for p in cls.patches:p.start()
        cls.pet=PetWindow()
        for timer in cls.pet.findChildren(QTimer):timer.stop()
        cls.pet._anim.stop()
        cls.panel=AgentChatWindow(cls.pet,ChatWorkspace(cls.path/'chat.db'));cls.pet._agent_panel=cls.panel
    @classmethod
    def tearDownClass(cls):
        cls.panel.shutdown();cls.panel.hide();cls.pet._screen_tools.stop();cls.pet._self_mcp.close();cls.pet._tray.hide();cls.pet.hide()
        for p in cls.patches:p.stop()
        cls.folder.cleanup()
    def setUp(self):
        self.panel.busy=False;self.panel.agent.cancel_event.clear()
        self.panel._run_kind=None;self.panel._answer_text=''
        self.panel.route_combo.setCurrentIndex(0);self.panel.effort_combo.setCurrentIndex(0)
        self.panel.logs_visible=False;self.panel._clear_attachment()
        self.panel.open_conversation(self.panel.store.create_conversation())
    def pump(self,predicate,seconds=2):
        until=time.monotonic()+seconds
        while not predicate() and time.monotonic()<until:APP.processEvents();time.sleep(.01)
        self.assertTrue(predicate())
    def image(self):
        p=QPixmap(480,180);p.fill(Qt.white);q=QPainter(p);q.setPen(QColor('#273b50'));q.setFont(QFont('Microsoft YaHei UI',24));q.drawText(25,95,'完成 3 / 5 项');q.end();return p
    def test_compact_shell_and_collapsed_records(self):
        p=self.panel;self.assertTrue(p.sidebar.isHidden());self.assertGreaterEqual(p.width(),520);self.assertLessEqual(p.width(),800)
        for role,text in [('user','帮我打开网站'),('tool','SECRET_TOOL_BODY'),('system','后台摘要'),('assistant','已打开你指定的网站。')]:p.store.append(p.active_id,role,text)
        p.render();self.assertIn('已打开',p.view.toPlainText());self.assertNotIn('SECRET_TOOL_BODY',p.view.toPlainText())
        p._toggle_logs(True);self.assertIn('SECRET_TOOL_BODY',p.view.toPlainText())
        self.assertTrue(is_progress_ack('本鹅想一想。'));self.assertFalse(is_progress_ack('这里的意思是程序没有启动。'))
    def test_screenshot_uses_same_conversation_and_never_fast_launches(self):
        p=self.panel;ident=p.active_id;image=image_uri(self.image());p.attach_screenshot(image)
        with patch.object(p.agent,'start') as model,patch('core.fast_commands.execute') as fast:
            p.send('打开浏览器')
        fast.assert_not_called();self.assertEqual(model.call_args.args[0],ident)
        self.assertEqual(model.call_args.kwargs['handoff']['_user_image_url'],image)
        self.assertIsNone(p._pending_image);self.assertNotIn('base64',str(p.store.messages(ident)))
        p.busy=False;p._task_heartbeat_timer.stop()
    def test_busy_and_voice_handoff_do_not_consume_draft_screenshot(self):
        p=self.panel;image=image_uri(self.image());p.attach_screenshot(image);p.busy=True
        self.assertFalse(p.send('解释图片'));self.assertEqual(p._pending_image,image)
        p.busy=False
        with patch.object(p.answer,'start') as model:p.send('你好',use_attachment=False)
        self.assertIsNone(model.call_args.kwargs['image_url'])
        self.assertEqual(p._pending_image,image);p.busy=False;p._task_heartbeat_timer.stop()
    def test_attachment_removed_when_switching_chat(self):
        self.panel.attach_screenshot(image_uri(self.image()))
        self.panel.open_conversation(self.panel.store.create_conversation());self.assertIsNone(self.panel._pending_image)
    def test_spoken_question_uses_attached_screenshot_in_same_call(self):
        from core.realtime_agent import AgentRealtimeVoice
        p=self.panel;p.voice=AgentRealtimeVoice();p.voice_active=True
        image=image_uri(self.image());p.attach_screenshot(image)
        p.store.append(p.active_id,'user','这张截图是什么意思？')
        p.voice.task_requested.connect(p._voice_request)
        with patch.object(p.answer,'start') as model,patch.object(p.voice,'resolve_task') as resolve:
            p.voice.task_requested.emit('screenshot-voice','这张截图是什么意思？')
            self.assertEqual(model.call_args.kwargs['image_url'],image)
            resolve.assert_not_called()
            self.assertEqual(p._voice_task,(p.voice,'screenshot-voice'))
        self.assertIsNone(p._pending_image);p._voice_task=None;p.voice_active=False;p.voice=None;p.busy=False;p._task_heartbeat_timer.stop()
    def test_model_sees_image_without_persisting_image_in_handoff(self):
        from core.agent_task import TaskJournal
        agent=SelfAgent(MagicMock(),config=dict(api_key='offline'));agent.journal=TaskJournal(self.path/'journal')
        seen=[]
        def reply(messages,*a,**kw):seen.extend(messages);return dict(role='assistant',content='截图显示完成了三项。')
        with patch.object(agent,'_request',side_effect=reply):agent._run('image-test',[],'这张图是什么意思？',threading.Event(),dict(_user_image_url=image_uri(self.image())))
        self.assertTrue(any(isinstance(m['content'],list) and any(v.get('type')=='image_url' for v in m['content']) for m in seen))
        self.assertNotIn('base64',json.dumps(agent.journal.data))
        self.assertFalse(any('base64' in m['content'] for m in seen if isinstance(m['content'],str)))
    def test_invalid_image_is_rejected(self):
        with self.assertRaises(ValueError):user_content('test','https://untrusted.example/image.png')
    def test_temporary_explanation_never_touches_chat_history(self):
        p=self.panel;before=p.store.messages(p.active_id);popup=ExplainDialog(self.pet)
        with patch('core.screen_question.explain',return_value='在这里表示程序提供给其他程序使用的入口。') as request:
            popup.load('接口','段落：这个程序提供接口，方便其他工具调用。',True)
            self.pump(lambda:not popup.pending)
            self.assertIn('入口',popup.answer.toPlainText());self.assertIn('段落',request.call_args.args[0][0]['content'])
        self.assertEqual(p.store.messages(p.active_id),before);popup.close()
        self.assertEqual(popup.messages,[]);self.assertEqual(popup.source.toPlainText(),'');self.assertEqual(popup.context,'')
    def test_closed_popup_ignores_late_response(self):
        popup=ExplainDialog(self.pet);popup.load('接口',auto=False);old=popup.generation;popup.close();popup.received(old,'过期回复',True)
        self.assertEqual(popup.messages,[]);self.assertEqual(popup.answer.toPlainText(),'')
    def test_pet_scale_preserves_sleepy_and_stays_below_original_max(self):
        p=self.pet;p._anim.set_expression('sleepy');p._set_pet_scale(.6)
        self.assertEqual(p.width(),round(p._iw*.6));self.assertEqual(p._anim.expression,'sleepy')
        p._set_pet_scale(2);self.assertEqual(p.width(),p._iw)
        p._set_pet_scale(.1);self.assertEqual(p.width(),round(p._iw*.4));p._set_pet_scale(1)
    def test_actual_region_drag_and_escape(self):
        # Exercise the overlay with an owned synthetic background, without screen capture.
        def init(overlay):
            from PyQt5.QtWidgets import QWidget
            QWidget.__init__(overlay);overlay.backdrop=QPixmap(400,250);overlay.backdrop.fill(Qt.white);overlay.setGeometry(0,0,400,250);overlay.start=None;overlay.end=None
        with patch.object(RegionCapture,'__init__',init):
            overlay=RegionCapture();output=[];overlay.selected.connect(output.append);overlay.show()
            QTest.mousePress(overlay,Qt.LeftButton,pos=QPoint(20,30));QTest.mouseRelease(overlay,Qt.LeftButton,pos=QPoint(200,150));APP.processEvents()
            self.assertEqual(len(output),1);self.assertGreater(output[0].width(),170)
            other=RegionCapture();cancel=[];other.cancelled.connect(lambda:cancel.append(True));QTest.keyClick(other,Qt.Key_Escape);self.assertTrue(cancel)
    def test_error_remains_visible_without_expanding_logs(self):
        p=self.panel;p._completed(dict(conversation_id=p.active_id,ok=False,error='目标软件未找到'))
        self.assertIn('目标软件未找到',p.view.toPlainText())
    def test_external_selection_toolbar_explains_and_translates_without_saving(self):
        tools=self.pet._screen_tools;tools.selection_enabled=True
        before=self.panel.store.messages(self.panel.active_id)
        payload=dict(image_url=image_uri(self.image()),source_hwnd=123)
        tools.selection_bar.present(payload,QPoint(200,180))
        self.assertTrue(tools.selection_bar.isVisible())
        with patch('core.screen_question.explain',return_value='interface') as model:
            tools.selection_bar.pick('translate');self.pump(lambda:tools.popup is not None and not tools.popup.pending)
            self.assertIn('翻译',model.call_args.args[0][-1]['content'])
            self.assertTrue(tools.popup.preview.isVisible())
        self.assertFalse(tools.selection_bar.isVisible());self.assertEqual(self.panel.store.messages(self.panel.active_id),before)
        tools.popup.close()
    def test_cached_selection_does_not_depend_on_current_foreground(self):
        tools=self.pet._screen_tools;tools.selection_bar.dismiss()
        with patch('ctypes.windll.user32.GetForegroundWindow',return_value=321),patch('core.screen_question.explain',return_value='interface：接口'):
            tools.selection_bar.present(dict(image_url=image_uri(self.image()),source_hwnd=123),QPoint(100,100))
            tools.selection_bar.pick('translate');self.pump(lambda:tools.popup is not None and not tools.popup.pending)
        self.assertIn('接口',tools.popup.answer.toPlainText());tools.popup.close()
    def test_left_selection_is_cached_before_toolbar_and_click_never_restores_focus(self):
        tools=self.pet._screen_tools;tools.selection_enabled=True;tools.active=False
        tools.selection_bar.dismiss()
        with patch('ui.selection_snapshot.snapshot',return_value=(self.image(),QPoint(200,180),self.image())),patch('core.screen_question.selected_text',return_value={'text':'接口','bounds':[180,160,80,30]}) as lookup:
            tools._selection_candidate(dict(hwnd=123,x=220,y=180,selection_gesture=True))
            self.pump(lambda:tools.selection_bar.isVisible());lookup.assert_called_once_with(123)
        self.assertIn('image_url',tools.selection_bar.payload)
        with patch('core.computer_control._attach_focus') as focus,patch('core.computer_control._send_keys') as keys,patch('core.screen_question.explain',return_value='所选词是“接口”，表示程序之间的调用入口。') as model:
            tools.selection_bar.pick('explain');self.pump(lambda:tools.popup is not None and not tools.popup.pending)
            focus.assert_not_called();keys.assert_not_called()
            self.assertIsInstance(model.call_args.args[0][0]['content'],list)
        self.assertTrue(tools.popup.preview.isVisible());tools.popup.close()
        self.assertEqual(tools.popup.messages,[]);self.assertIsNone(tools.popup.preview.pixmap())

    def test_nontext_drag_does_not_show_selection_bar_or_call_model(self):
        tools=self.pet._screen_tools;tools.selection_enabled=True;tools.selection_bar.dismiss()
        with patch('ui.selection_snapshot.snapshot',return_value=(self.image(),QPoint(200,180),self.image())),patch('core.screen_question.selected_text',return_value={'text':''}),patch('core.screen_question.explain') as model:
            with patch('ui.selection_snapshot.snapshot') as snapshot:
                tools._selection_candidate(dict(hwnd=123,x=220,y=180,selection_gesture=True))
                self.pump(lambda:tools.last_selection_status=='no_text_selection')
                snapshot.assert_not_called()
            self.assertFalse(tools.selection_bar.isVisible());model.assert_not_called()

    def test_stale_text_or_geometry_must_cover_the_release_point(self):
        from ui.screen_tools import ScreenTools
        event=dict(x=300,y=200)
        self.assertFalse(ScreenTools.valid_selection_text({'text':'接口'},event))
        self.assertFalse(ScreenTools.valid_selection_text({'text':'接口','bounds':[20,20,40,20]},event))
        self.assertTrue(ScreenTools.valid_selection_text({'text':'接口','bounds':[250,180,100,30]},event))

    def test_text_toolbar_has_explain_and_screenshot_analysis(self):
        from PyQt5.QtWidgets import QPushButton
        labels=[b.text() for b in self.pet._screen_tools.selection_bar.findChildren(QPushButton)]
        self.assertIn('解释',labels);self.assertIn('截图分析',labels);self.assertNotIn('翻译',labels)

    def test_pet_menu_exposes_natural_videos_and_drops_legacy_shapes(self):
        from PyQt5.QtWidgets import QMenu
        menu=self.pet._ensure_pet_menu()
        texts={a.text() for m in menu.findChildren(QMenu) for a in m.actions()}
        texts.update(a.text() for a in menu.actions())
        self.assertIn('困倦打盹',texts);self.assertIn('双手比心',texts)
        self.assertFalse({'摸下巴思考','挠挠头','转圈'}&texts)

    def test_selection_screenshot_analysis_uses_cached_image_without_saving(self):
        tools=self.pet._screen_tools
        with patch('core.screen_question.explain',return_value='这里是接口定义') as model:
            tools.selection_bar.present(dict(image_url=image_uri(self.image())),QPoint(100,100))
            tools.selection_bar.pick('analyze');self.pump(lambda:tools.popup is not None and not tools.popup.pending)
            self.assertIn('截图分析',tools.popup.windowTitle())
            self.assertIn('分析这张',model.call_args.args[0][-1]['content'])
        tools.popup.close()
    def test_new_click_cancels_a_pending_selection_capture(self):
        tools=self.pet._screen_tools;tools.selection_bar.dismiss()
        with patch('ui.selection_snapshot.snapshot') as snapshot:
            tools._selection_candidate(dict(hwnd=123,selection_gesture=True))
            tools._selection_candidate(dict(kind='dismiss'))
            until=time.monotonic()+.08
            while time.monotonic()<until:APP.processEvents();time.sleep(.005)
            snapshot.assert_not_called()
    def test_selection_source_is_the_mouse_down_window_not_late_foreground(self):
        import ctypes,os
        from core.selection_watcher import SelectionWatcher,MouseInfo
        watcher=SelectionWatcher();info=MouseInfo();info.pt.x=100;info.pt.y=150;info.time=1000
        def external_pid(hwnd,pointer):ctypes.cast(pointer,ctypes.POINTER(ctypes.c_ulong)).contents.value=os.getpid()+1
        with patch('ctypes.windll.user32.WindowFromPoint',return_value=42),patch('ctypes.windll.user32.GetAncestor',return_value=123),patch('ctypes.windll.user32.GetForegroundWindow',return_value=999),patch('ctypes.windll.user32.GetWindowThreadProcessId',side_effect=external_pid),patch('ctypes.windll.user32.CallNextHookEx',return_value=0):
            watcher.callback(0,0x0201,ctypes.addressof(info))
            info.pt.x=220;info.time=1200;watcher.callback(0,0x0202,ctypes.addressof(info))
        self.assertEqual(watcher.queue[-1]['hwnd'],123)
        self.assertEqual(watcher.queue[-1]['start_x'],100);self.assertEqual(watcher.queue[-1]['x'],220)
    def test_clipboard_fallback_refuses_a_switched_source(self):
        from ui.selection_clipboard import SelectionCopy
        reader=SelectionCopy();results=[];reader.done.connect(results.append)
        with patch('ctypes.windll.user32.IsWindow',return_value=True),patch('ctypes.windll.user32.GetForegroundWindow',return_value=321),patch('core.computer_control._send_keys') as keys:
            reader.read(123)
        self.assertFalse(results[-1]['ok']);keys.assert_not_called();self.assertFalse(reader.busy)
    def test_toolbar_focus_is_restored_to_the_recorded_source_before_copy(self):
        import os,ctypes
        from ui.selection_clipboard import SelectionCopy
        reader=SelectionCopy();results=[];reader.done.connect(results.append)
        def same_process(hwnd,pointer):ctypes.cast(pointer,ctypes.POINTER(ctypes.c_ulong)).contents.value=os.getpid()
        with patch('ctypes.windll.user32.IsWindow',return_value=True),patch('ctypes.windll.user32.GetForegroundWindow',return_value=321),patch('ctypes.windll.user32.GetWindowThreadProcessId',side_effect=same_process),patch('core.computer_control._attach_focus',return_value=True) as restore,patch.object(reader,'copy') as copy:
            reader.read(123);restore.assert_called_once_with(123);copy.assert_called_once();self.assertEqual(results,[])
            reader.stop()
    def test_plain_question_uses_answer_worker_without_task_heartbeat(self):
        p=self.panel
        with patch.object(p.answer,'start') as answer,patch.object(p.agent,'start') as agent:
            p.send('接口是什么？')
        answer.assert_called_once();agent.assert_not_called();self.assertEqual(answer.call_args.kwargs['effort'],'quick')
        self.assertFalse(p._task_heartbeat_timer.isActive());self.assertEqual(p._run_kind,'answer')
    def test_short_voice_reply_uses_original_tts_and_personality(self):
        p=self.panel
        with patch.object(p.answer,'start') as answer:
            p._short_transcript('你好，咕嘎')
        self.assertTrue(answer.call_args.kwargs['read_aloud'])
        with patch.object(self.pet,'_say_with_expression') as legacy,patch.object(self.pet,'_show_agent_bubble') as show:
            p._completed(dict(kind='answer',conversation_id=p.active_id,ok=True,text='饲养员，本鹅在呢。',expression='happy',action='none',read_aloud=True))
            legacy.assert_not_called()
            show.assert_not_called()
            self.assertEqual(p.active_agent_id,'001')
            self.assertIsNotNone(p._pending_tts_display)
            p._local_tts_playback_started('')
            show.assert_called_once()
            self.assertEqual(show.call_args.args[0],'饲养员，本鹅在呢。')

    def test_desktop_bubble_hold_to_talk_is_wired_to_short_voice(self):
        p=self.panel;p.busy=True;p._run_kind='dsh'
        with patch.object(p,'start_bubble_short_voice',return_value=True) as start,patch.object(p,'finish_bubble_short_voice') as finish:
            self.pet._agent_bubble.talk_started.emit();self.pet._agent_bubble.talk_stopped.emit(False)
        start.assert_called_once();finish.assert_called_once_with(False)
        p.busy=False;p._run_kind=None

    def test_text_waits_for_local_audio_playback_and_progress_is_spoken(self):
        p=self.panel;p.voice_active=False;p._pending_tts_display=None
        self.pet._agent_bubble.hide()
        with patch.object(self.pet._tts,'speak') as speak:
            p._say_active_reply('同步显示的回答',speak=True,spoken_text='同步显示的回答')
            speak.assert_called_once()
            self.assertFalse(self.pet._agent_bubble.isVisible())
            self.pet._tts.playback_started.emit('')
            APP.processEvents()
            self.assertIn('同步显示的回答',self.pet._agent_bubble.full_text)
        from core.task_speech import TaskSpeechQueue
        p._task_speech=TaskSpeechQueue(clock=lambda:100)
        with patch.object(self.pet._tts,'speak') as speak:
            p._flush_task_speech();p._queue_task_speech('progress-test','本鹅正在核对文件，任务还没完成。')
            speak.assert_called_once();self.assertNotIn('正在核对',self.pet._agent_bubble.full_text)
            self.pet._tts.playback_started.emit('');APP.processEvents()
            self.assertIn('正在核对',self.pet._agent_bubble.full_text)

    def test_realtime_vad_fallback_injects_local_transcript(self):
        from core.realtime_agent import AgentRealtimeVoice
        voice=AgentRealtimeVoice();voice._thread=MagicMock();voice._thread.is_alive.return_value=True;voice._stop.clear()
        self.assertTrue(voice.submit_user_text('本地识别补充'))
        with patch.object(voice,'_send') as send,patch.object(voice,'_request_audio_response') as request:
            voice._process_command(voice._commands.get_nowait())
        create=next(c.args[0] for c in send.call_args_list if c.args[0].get('type')=='conversation.item.create')
        self.assertEqual(create['item']['content'][0]['text'],'本地识别补充');request.assert_called_once()
    def test_selection_from_cancelled_capture_is_not_redisplayed(self):
        tools=self.pet._screen_tools;tools.selection_bar.dismiss();old=tools.selection_capture_sequence
        tools.selection_capture_sequence+=1
        with patch('ui.selection_snapshot.snapshot') as snapshot:tools._cache_selection(dict(hwnd=123),old)
        snapshot.assert_not_called();self.assertFalse(tools.selection_bar.isVisible())
    def test_task_signals_reach_guga_body_and_cancellation_never_celebrates(self):
        from core.task_animation import TaskAnimationDirector
        p=self.panel;a=self.pet._anim2d;clock=[0.]
        a._reference_clips_enabled=True;a._load_task_clips()
        a._task_motion=TaskAnimationDirector(lambda:clock[0]);a._context_expression=None
        p._run_kind='task';p.busy=True;p.voice_active=False
        a.set_work_state('thinking','turn:'+p.active_id)
        self.pet._agent_panel=p
        p.agent.progress.emit(p.active_id,dict(phase='tool_start',summary='执行中',name='local_computer',arguments={'action':'read'}))
        self.assertEqual(a._task_motion.state,'working')
        clock[0]=2.;a.action='none';a._clip=None;a._speaking=False;a.mouth_open=0.;a.expression='normal'
        a._tick_task_motion();self.assertEqual(a._clip,'task:working')
        p.agent.cancel_event.set()
        p.agent.completed.emit(dict(conversation_id=p.active_id,ok=True,text='不可误判为成功',expression='normal',action='none'))
        self.assertFalse(a._task_motion.active)
        self.assertFalse((a._clip or '').startswith('task:'))
        self.assertNotEqual(a._task_motion.state,'success');p.agent.cancel_event.clear();a.action='none'

    def test_screenshot_button_directly_sends_without_crop_or_second_click(self):
        tools=self.pet._screen_tools;p=self.panel;p.editor.setPlainText('解释当前页面')
        with patch.object(tools,'_snapshot_current',return_value=self.image()),patch.object(p.answer,'start') as model:
            tools.begin('ask');self.pump(lambda:model.called)
            self.assertEqual(model.call_args.args[0],p.active_id)
            self.assertIsNotNone(model.call_args.kwargs['image_url'])
        self.assertIsNone(tools.capture);self.assertIsNone(p._pending_image);p.busy=False;p._task_heartbeat_timer.stop()


if __name__=='__main__':unittest.main()
