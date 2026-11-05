"""Single browser steps, native UIA targeting, and honest local verification."""
import os
from pathlib import Path
import queue
import sys
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch,PropertyMock

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from core.fast_commands import match,command_key
from core.browser_interaction import BrowserInteraction
from core.uia_backend import UIABackend
from core.execution_contract import ExecutionLedger


class BrowserStepTests(unittest.TestCase):
    def test_everyday_browser_phrasing_stays_local(self):
        for text,action in (('你帮我点一下上面的搜索框','click'),('点击那个搜索框好吗','click'),
                ('点开这个页面的登录按钮','click'),('往搜索框里输入“猫，保留标点。”','fill_named'),
                ('进入我的收藏空间','click'),('点击网页上的收藏空间','click')):
            with self.subTest(text=text):
                parsed=match(text)
                self.assertEqual(parsed.get('action'),'browser_step')
                self.assertEqual(parsed.get('browser_action'),action)
        self.assertEqual(match('你帮我点一下上面的搜索框')['target'],'搜索框')
        self.assertEqual(match('往搜索框里输入“猫，保留标点。”')['text'],'猫，保留标点。')
        self.assertEqual(match('进入我的收藏空间')['target'],'收藏空间')
        self.assertEqual(match('点击网页上的收藏空间')['target'],'收藏空间')

    def test_search_field_fill_uses_page_semantics_instead_of_exact_placeholder(self):
        obj=self.interaction();obj.uia.page_input.return_value=dict(element=dict(ref='search'))
        with patch('core.desktop_access.DesktopAccess.enabled',new_callable=PropertyMock,return_value=True):
            result=obj.execute(match('往搜索框里输入“猫，保留标点。”'))
        self.assertTrue(result['ok']);obj.uia.page_input.assert_called_once_with(123,search=True)
        obj.uia.read.assert_not_called();self.assertEqual(obj.uia.act.call_args.kwargs['value'],'猫，保留标点。')

    def test_common_instructions_route_locally(self):
        for text,action in (('点击搜索按钮','click'),('请帮我点击验收输入','click'),('输入“你好，世界。”','fill'),
                ('向下滚动','scroll_down'),('返回上一页','back'),('刷新页面','refresh'),
                ('下一个标签页','next_tab'),('按回车','enter'),('追加输入你好','append')):
            with self.subTest(text=text):
                parsed=match(text)
                self.assertEqual(parsed.get('action'),'browser_step')
                self.assertEqual(parsed['browser_action'],action)
        self.assertEqual(match('输入“你好，世界。”')['target'],'你好，世界。')
        self.assertEqual(match('在搜索框里输入“ＡＢＣ，保留  空格。”')['text'],'ＡＢＣ，保留  空格。')

    def test_distinct_navigation_and_field_writes_never_share_dedupe_key(self):
        self.assertNotEqual(command_key(match('刷新')),command_key(match('返回上一页')))
        self.assertNotEqual(command_key(match('在搜索框输入ABC')),command_key(match('在搜索框输入abc')))
        self.assertEqual(command_key(match('点击搜索')),command_key(match('请点击搜索')))

    def test_questions_negation_and_multiple_clicks_are_not_atomic_steps(self):
        for text in ('不要点击搜索','输入法怎么切换','输入框是什么','点击登录然后点击支付','怎么点击这个按钮'):
            self.assertFalse(match(text)['matched'],text)

    def interaction(self):
        obj=BrowserInteraction();obj.uia=Mock();obj._guard=Mock(return_value=123)
        obj.uia.focused.return_value=dict(element=dict(ref='field',value='原有内容',type='Edit'))
        obj.uia.act.return_value=dict(verified=True)
        return obj

    def test_current_field_write_has_exact_readback(self):
        obj=self.interaction()
        with patch('core.desktop_access.DesktopAccess.enabled',new_callable=PropertyMock,return_value=True):
            result=obj.execute(match('输入新内容'))
        self.assertTrue(result['ok']);self.assertTrue(result['verified'])
        obj.uia.act.assert_called_once_with(123,'set_value',ref='field',value='新内容')

    def test_append_never_loses_the_existing_value(self):
        obj=self.interaction()
        with patch('core.desktop_access.DesktopAccess.enabled',new_callable=PropertyMock,return_value=True):
            self.assertTrue(obj.execute(match('追加输入新增'))['ok'])
        self.assertEqual(obj.uia.act.call_args.kwargs['value'],'原有内容新增')

    def test_failed_readback_is_not_reported_as_success(self):
        obj=self.interaction();obj.uia.act.return_value=dict(verified=False)
        with patch('core.desktop_access.DesktopAccess.enabled',new_callable=PropertyMock,return_value=True):
            result=obj.execute(match('输入新内容'))
        self.assertFalse(result['ok']);self.assertIsNone(result['action_sent'])
        self.assertEqual(obj.uia.act.call_count,1)

    def test_focus_change_blocks_action(self):
        obj=self.interaction();obj._guard.side_effect=[123,RuntimeError('前台已变化')]
        with patch('core.desktop_access.DesktopAccess.enabled',new_callable=PropertyMock,return_value=True):
            result=obj.execute(match('输入测试'))
        self.assertFalse(result['ok']);self.assertFalse(result['action_sent']);obj.uia.act.assert_not_called()

    def test_busy_executor_does_not_queue_a_late_click(self):
        obj=self.interaction();obj.lock.acquire()
        try:
            result=obj.execute(match('点击提交'))
            self.assertFalse(result['ok']);obj._guard.assert_not_called()
        finally:obj.lock.release()

    def test_successful_step_does_not_start_ack_audio_that_mutes_next_input(self):
        from core.realtime_agent import AgentRealtimeVoice
        voice=AgentRealtimeVoice();commands=[];voice.fast_command.connect(commands.append)
        voice._dispatch_fast(match('输入测试'))
        with patch.object(voice,'notify_battleground') as notice:
            voice.complete_fast_command(commands[0]['fast_id'],dict(ok=True,verified=True,message='已填写'))
        notice.assert_not_called()

    def test_manual_steps_suppress_queued_and_new_proactive_speech(self):
        from core.realtime_agent import AgentRealtimeVoice
        voice=AgentRealtimeVoice();voice._thread=Mock();voice._thread.is_alive.return_value=True
        voice._last_activity=time.monotonic()-10
        self.assertTrue(voice.notify_proactive('before','旧的主动搭话'))
        voice._dispatch_fast(match('点击搜索'))
        self.assertFalse(voice.notify_proactive('during','新的主动搭话'))
        with patch.object(voice,'_send') as send,patch.object(voice,'_request_audio_response') as audio:
            voice._process_command(voice._commands.get_nowait())
        send.assert_not_called();audio.assert_not_called()
        self.assertFalse(voice._proactive_notices)


class NativeTargetingTests(unittest.TestCase):
    def test_unique_search_input_accepts_a_content_placeholder(self):
        b=self.backend();doc=object()
        item=dict(ref='search',name='今天想看什么',type='Edit',enabled=True,password=False)
        b._find.side_effect=[[(doc,dict(rect={}))],[(object(),item)]]
        self.assertEqual(b.page_input(7,search=True)['element']['ref'],'search')

    def test_multiple_non_search_inputs_stay_ambiguous(self):
        b=self.backend();doc=object()
        items=[(object(),dict(name=name,enabled=True,password=False)) for name in ('用户名','留言')]
        b._find.side_effect=[[(doc,dict(rect={}))],items]
        with self.assertRaisesRegex(RuntimeError,'不唯一'):b.page_input(7,search=True)

    def backend(self):
        b=UIABackend.__new__(UIABackend);b.lock=threading.RLock();b.elements={};b.ttl=30;b.cache=object()
        b._find=Mock(return_value=[(object(),dict(ref='unique'))]);b.snapshot=Mock(side_effect=AssertionError('no full-tree scan'))
        return b

    def test_exact_name_does_not_rebuild_tree(self):
        b=self.backend();element,item=b._resolve(7,name='保存')
        self.assertEqual(item['ref'],'unique');b.snapshot.assert_not_called()

    def test_ambiguous_name_never_selects_first(self):
        b=self.backend();b._find.return_value=[(object(),{}),(object(),{})]
        with self.assertRaisesRegex(RuntimeError,'不唯一'):b._resolve(7,name='保存')

    def test_expired_ref_does_not_guess_by_name(self):
        b=self.backend();b.elements['stale']=(object(),time.monotonic()-31,7)
        with self.assertRaisesRegex(RuntimeError,'过期'):b._resolve(7,ref='stale',name='保存')
        b._find.assert_not_called()

    def test_cache_hit_still_checks_constraints(self):
        b=self.backend();element=Mock();element.GetUpdatedCache.return_value=element
        b.elements['ref']=(element,time.monotonic(),7);b._entry=Mock(return_value=(dict(ref='ref',name='其他',id='',type='Button',offscreen=False),element))
        with self.assertRaisesRegex(RuntimeError,'名称已变化'):b._resolve(7,ref='ref',name='保存')

    def test_invoke_error_does_not_fall_back_to_second_action(self):
        b=self.backend();element=Mock();element.Current.IsEnabled=True;element.Current.IsPassword=False
        pattern=Mock();pattern.Invoke.side_effect=OSError('provider failed after action')
        element.GetCurrentPattern.return_value=pattern
        b._resolve=Mock(return_value=(element,{}));b.Patterns={'invoke':SimpleNamespace(Pattern='invoke'),'select':SimpleNamespace(Pattern='select')}
        with self.assertRaisesRegex(RuntimeError,'未自动重试'):b.act(7,'invoke',name='保存')
        self.assertEqual(element.GetCurrentPattern.call_count,1);pattern.Invoke.assert_called_once()

    def test_wait_queries_only_target(self):
        b=self.backend();b._resolve=Mock(return_value=(object(),dict(name='就绪',enabled=True)))
        result=b.wait(7,.1,name='就绪')
        self.assertTrue(result['met']);b.snapshot.assert_not_called()

    def test_generic_input_stays_inside_web_document(self):
        b=self.backend();document=object()
        b._find.side_effect=[[(document,dict(rect=dict(left=0,top=0,right=100,bottom=100)))],
                             [(object(),dict(ref='page-field',enabled=True,password=False,name='搜索'))]]
        self.assertEqual(b.page_input(7,search=True)['element']['ref'],'page-field')
        self.assertIs(b._find.call_args.kwargs['root'],document)

    def test_generic_input_refuses_ambiguous_page_fields(self):
        b=self.backend();b._find.side_effect=[[(object(),{})],
            [(object(),dict(enabled=True,password=False)),(object(),dict(enabled=True,password=False))]]
        with self.assertRaisesRegex(RuntimeError,'不唯一'):b.page_input(7)

    def test_offscreen_wait_can_resolve_invisible_target(self):
        b=self.backend();b._resolve=Mock(return_value=(object(),dict(offscreen=True)))
        self.assertTrue(b.wait(7,.1,name='隐藏',state='offscreen',expected=True)['met'])
        self.assertTrue(b._resolve.call_args.kwargs['include_offscreen'])


class VerificationTests(unittest.TestCase):
    def test_locally_verified_value_needs_no_extra_model_observation(self):
        ledger=ExecutionLedger()
        ledger.record('computer',dict(action='uia',hwnd=7),dict(ok=True,result=dict(verified=True,
            verification=dict(kind='value_equals',matched=True))))
        self.assertFalse(ledger.blockers())

    def test_click_still_needs_effect_verification(self):
        ledger=ExecutionLedger()
        ledger.record('computer',dict(action='uia',hwnd=7),dict(ok=True,result=dict(verified=False,input_sent=True)))
        self.assertTrue(ledger.blockers())
        ledger.record('computer',dict(action='uia_read',hwnd=8),dict(ok=True,result=dict(hwnd=8)))
        self.assertTrue(ledger.blockers(),'a different window must not verify the click')
        ledger.record('computer',dict(action='uia_read',hwnd=7),dict(ok=True,result=dict(hwnd=7)))
        self.assertFalse(ledger.blockers())

    def test_ui_thread_is_not_required_for_native_provider(self):
        from core.uia_service import UIAService
        service=UIAService();service._start=Mock();service.process=Mock();service.replies=queue.Queue()
        with self.assertRaisesRegex(RuntimeError,'超时或中断'):service.call('read',7,timeout=.01,name='慢控件')
        self.assertIsNone(service.process)
        service.close()


if __name__=='__main__':unittest.main(verbosity=2)
