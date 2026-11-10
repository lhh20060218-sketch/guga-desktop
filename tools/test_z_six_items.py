# -*- coding: utf-8 -*-
"""z 包六项修复的单元测试（每项都要有可复跑的断言）。

覆盖：
  一、按真实控件类型定位输入框 / 同源回读（不回退前台窗口或整窗 OCR）
  二、UIAService 接口对齐（first_edit / scroll_state / composer / text_of）
  三、完成判定 done.any 三信号（4 条）
  四、三处超时（PrintWindow / 每轮抓屏 / ask_once 看门狗）
  五、聊天读台账（存在 / 缺失）
  六、失败收口与禁话术

单独运行：
    python tools\\test_z_six_items.py
"""
import json
import os
import sys
import tempfile
import threading
import time
import types
import unittest
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core import adapter_chain, agent_task, reply_guard  # noqa: E402
from core.adapters import doubao_adapter  # noqa: E402
from core.uia_backend import UIABackend  # noqa: E402
from core.uia_service import UIAService  # noqa: E402


class _Clock:
    """把 _wait_done 的时间推进换成可预期的假时钟（不真等 10 秒）。"""

    def __init__(self):
        self.now = 1000.0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += max(0.01, float(seconds))


def _bare_adapter(declaration=None):
    adapter = doubao_adapter.DoubaoAdapter.__new__(doubao_adapter.DoubaoAdapter)
    adapter.declaration = declaration if declaration is not None else {
        "anchors": {"done": {"poll_seconds": 0.05, "stable_seconds": 0.2,
                             "max_wait_seconds": 10, "capture_timeout_seconds": 0.5}}}
    adapter._last_ocr_empty = False
    adapter._ocr_unavailable = False
    adapter.cc = None
    return adapter


def _run_wait_done(frames, limit=10.0, baseline=0, baseline_before=0):
    """frames: 每次轮询返回的文本列表（最后一个重复使用）。"""
    adapter = _bare_adapter()
    clock = _Clock()
    original_time = doubao_adapter.time
    index = {"i": 0}

    def capture(hwnd, save_path=None):
        i = min(index["i"], len(frames) - 1)
        index["i"] += 1
        return None, [], frames[i]

    adapter._capture_words = lambda hwnd, save_path=None: capture(hwnd, save_path)
    adapter._capture_words_timed = lambda hwnd, save_path=None, timeout=None: capture(hwnd, save_path)
    events = []
    doubao_adapter.time = clock
    try:
        result = adapter._wait_done(1, "问题", limit, Path("."), lambda e, **f: events.append((e, f)),
                                    baseline=baseline, baseline_before=baseline_before)
    finally:
        doubao_adapter.time = original_time
    return result, events


class LocateComposerTests(unittest.TestCase):
    """一：定位/回读只认同一个控件。"""

    def test_composer_filter_requires_prosemirror_focusable_text(self):
        # 真实豆包控件特征：Group + tiptap ProseMirror + 可聚焦 + TextPattern，无 ValuePattern。
        self.assertIn('prosemirror', ' '.join(UIABackend.COMPOSER_CLASS_HINTS).lower())
        self.assertIn('Group', UIABackend.COMPOSER_TYPES)
        self.assertNotIn('Edit', UIABackend.COMPOSER_TYPES[:1])

    def test_composer_driver_reads_same_element_textpattern(self):
        calls = []

        class FakeService:
            def text_of(self, hwnd, ref, limit=4000):
                calls.append((hwnd, ref))
                return {"text": "发消息或创建任务…\n/ 使用技能 @ 添加资料\n我要的正文"}

            def value(self, hwnd, ref):
                raise AssertionError("有 TextPattern 时不该走 ValuePattern")

            def text(self, hwnd, limit=6000):
                raise AssertionError("不允许回退到整页文本")

        driver = doubao_adapter._ComposerDriver(
            object(), 123, {"x": 0.55, "y": 0.87}, ref="ref-1",
            service=FakeService(), element={"text_pattern": True})
        self.assertEqual(driver.read(), "我要的正文")
        self.assertEqual(calls, [(123, "ref-1")])

    def test_composer_driver_never_falls_back(self):
        class FakeService:
            def text_of(self, hwnd, ref, limit=4000):
                raise RuntimeError("元素失效")

            def text(self, hwnd, limit=6000):
                return "整页 1916 字文本"

        driver = doubao_adapter._ComposerDriver(
            object(), 123, {}, ref="ref-1", service=FakeService(),
            element={"text_pattern": True})
        with self.assertRaises(doubao_adapter.ComposerNotFound):
            driver.read()

    def test_composer_driver_without_binding_refuses(self):
        driver = doubao_adapter._ComposerDriver(object(), 123, {})
        with self.assertRaises(doubao_adapter.ComposerNotFound):
            driver.read()


class ServiceInterfaceTests(unittest.TestCase):
    """二：backend 有的方法，service 必须显式暴露且调用同名 RPC。"""

    WRAPPERS = {
        'snapshot': (lambda s, h: s.snapshot(h), 'snapshot'),
        'read': (lambda s, h: s.read(h), 'read'),
        'focused': (lambda s, h: s.focused(h), 'focused'),
        'page_input': (lambda s, h: s.page_input(h), 'page_input'),
        'first_edit': (lambda s, h: s.first_edit(h), 'first_edit'),
        'composer': (lambda s, h: s.composer(h), 'composer'),
        'text_of': (lambda s, h: s.text_of(h, 'ref-1'), 'text_of'),
        'value': (lambda s, h: s.value(h, 'ref-1'), 'value'),
        'scroll_state': (lambda s, h: s.scroll_state(h), 'scroll_state'),
        'perceive': (lambda s, h: s.perceive(h), 'perceive'),
        'text': (lambda s, h: s.text(h), 'text'),
        'act': (lambda s, h: s.act(h, 'focus', ref='ref-1'), 'act'),
        'wait': (lambda s, h: s.wait(h, seconds=0), 'wait'),
    }

    def test_backend_methods_are_exposed_on_service(self):
        for name in self.WRAPPERS:
            self.assertTrue(hasattr(UIABackend, name), 'backend 缺 %s' % name)
            self.assertTrue(callable(getattr(UIAService, name, None)),
                            'service 缺显式方法 %s' % name)

    def test_service_wrappers_call_same_rpc_name(self):
        service = UIAService()
        seen = []

        def fake_call(method, hwnd=0, timeout=2.5, **arguments):
            seen.append(method)
            return {}

        service.call = fake_call
        for name, (invoke, expected) in self.WRAPPERS.items():
            invoke(service, 1)
            self.assertEqual(seen[-1], expected, '%s 调用了 %s' % (name, seen[-1]))
        service.close()


class DoneAnyTests(unittest.TestCase):
    """三：done.any 三信号 + 生成中否决。"""

    def test_short_answer_completes_after_stable_window(self):
        result, events = _run_wait_done(["这是一句很短的回复"], baseline=0, baseline_before=10)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["done_signal"], "stable_2s")
        self.assertLess(result["chars"], 120)          # 不再要求 >=120 字
        self.assertTrue(any(e == "done" and f.get("done_signal") == "stable_2s"
                            for e, f in events))

    def test_stop_button_gone_completes(self):
        result, _ = _run_wait_done(["停止生成  <<  正文", "正文已经出来了"])
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["done_signal"], "stop_button_gone")
        self.assertTrue(result["stop_seen"])

    def test_no_signal_hits_timeout_with_done_signal(self):
        result, events = _run_wait_done(["一直没有变化的页面"], baseline=0, baseline_before=0)
        self.assertFalse(result["ok"])
        self.assertEqual(result["code"], "timeout")
        self.assertEqual(result["done_signal"], "timeout")
        self.assertTrue(any(e == "done" and f.get("done_signal") == "timeout"
                            for e, f in events))

    def test_generating_and_growing_never_completes(self):
        frames = ["停止生成 " + "字" * n for n in range(1, 400)]
        result, _ = _run_wait_done(frames)
        self.assertFalse(result["ok"])
        self.assertEqual(result["done_signal"], "timeout")


class TimeoutTests(unittest.TestCase):
    """四：三处阻塞点都要在设定上限内返回。"""

    def test_grab_window_times_out(self):
        original = doubao_adapter._grab_window_sync
        doubao_adapter._grab_window_sync = lambda hwnd: time.sleep(5)
        try:
            started = time.monotonic()
            with self.assertRaises(doubao_adapter.CaptureTimeout):
                doubao_adapter._grab_window(1, timeout=0.3)
            self.assertLess(time.monotonic() - started, 2.0)
        finally:
            doubao_adapter._grab_window_sync = original

    def test_capture_words_round_times_out(self):
        adapter = _bare_adapter()
        adapter._capture_words = lambda hwnd, save_path=None: time.sleep(5)
        started = time.monotonic()
        with self.assertRaises(doubao_adapter.CaptureTimeout):
            adapter._capture_words_timed(1, None, timeout=0.3)
        self.assertLess(time.monotonic() - started, 2.0)

    def test_ask_once_watchdog_reports_step_timeout(self):
        class BlockingAdapter:
            def ask(self, *args, **kwargs):
                time.sleep(5)

        original = adapter_chain.adapter_for if hasattr(adapter_chain, 'adapter_for') else None
        from core.adapters import dispatch
        original_for = dispatch.adapter_for
        original_watchdog = adapter_chain.ask_watchdog_seconds
        dispatch.adapter_for = lambda name: ('doubao', BlockingAdapter())
        adapter_chain.ask_watchdog_seconds = lambda timeout_seconds: 0.3
        try:
            started = time.monotonic()
            outcome = adapter_chain.run(dict(steps=[dict(
                index=1, name='豆包', app_id='doubao',
                instruction='用豆包写一段一百字左右的自我介绍，直接给出正文')]))
            self.assertLess(time.monotonic() - started, 2.0)
        finally:
            dispatch.adapter_for = original_for
            adapter_chain.ask_watchdog_seconds = original_watchdog
            if original is not None:
                adapter_chain.adapter_for = original
        self.assertFalse(outcome['ok'])
        self.assertEqual(outcome['code'], 'step_failed')
        self.assertEqual(outcome['failure_code'], 'step_timeout')
        self.assertEqual(outcome['steps'][0]['code'], 'step_timeout')


class LedgerTests(unittest.TestCase):
    """五：回复前读台账；读不到就不许编。"""

    def _write(self, root, payload):
        path = Path(root) / ('%s.json' % payload['id'])
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
        return path

    def test_ledger_present_injects_real_steps(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._write(tmp, {
                'id': 'abc', 'conversation': 'c1', 'goal': '用豆包写提示词',
                'status': 'failed',
                'chain': {'total': 2, 'step': 1, 'status': 'failed'},
                'last_tool_failure': {'code': 'input_verify_failed', 'stage': 'inject',
                                      'error': '回读不一致', 'next_action': '切到豆包后重派'},
                'contract': {'evidence_count': 3},
                'updated': time.time(),
            })
            snap = agent_task.ledger_snapshot(root=tmp)
            self.assertTrue(snap['ok'])
            note = agent_task.ledger_note(snap)
            self.assertIn('第 1/2 步', note)
            self.assertIn('input_verify_failed', note)
            self.assertIn('证据条数：3', note)
            self.assertNotIn(agent_task.LEDGER_MISSING_PHRASE, note)

    def test_ledger_missing_says_cannot_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            empty = Path(tmp) / 'agent-tasks'
            empty.mkdir()
            snap = agent_task.ledger_snapshot(root=str(empty / 'not-exist'))
            note = agent_task.ledger_note(snap)
            self.assertFalse(snap['ok'])
            self.assertIn(agent_task.LEDGER_MISSING_PHRASE, note)
            self.assertNotIn('第 1/', note)
            disclosure = reply_guard.ledger_disclosure(snap, '任务做到哪一步了？')
            self.assertIn(agent_task.LEDGER_MISSING_PHRASE, disclosure)
            self.assertIn('未执行/未确认', disclosure)


class HonestyTests(unittest.TestCase):
    """六：失败收口 + 禁话术。"""

    def test_permission_and_manual_phrases_are_removed(self):
        text = '我没有操作电脑的权限，纯问答模式。请你手动打开豆包点一下。'
        cleaned, hits = reply_guard.sanitize(text, executable=True, has_evidence=False)
        self.assertTrue(hits)
        for phrase in ('没有操作电脑的权限', '纯问答模式', '请你手动打开', '点一下'):
            self.assertNotIn(phrase, cleaned)
        self.assertIn('未执行/未确认', cleaned)

    def test_phantom_progress_is_removed_without_evidence(self):
        text = '已转交后台，正在生成，后台每 5 秒同步一次。豆包那边马上就好。'
        cleaned, hits = reply_guard.sanitize(text, executable=True, has_evidence=False)
        self.assertTrue(hits)
        for phrase in ('已转交', '正在生成', '后台每'):
            self.assertNotIn(phrase, cleaned)
        self.assertIn('未执行/未确认', cleaned)

    def test_evidence_allows_real_progress_wording(self):
        text = '已经拿到回执，回答正文 312 字。'
        cleaned, hits = reply_guard.sanitize(text, executable=True, has_evidence=True)
        self.assertEqual(hits, [])
        self.assertEqual(cleaned, text)

    def test_failure_receipt_is_code_stop_and_next_action(self):
        from core.adapters import dispatch
        class FailingAdapter:
            def ask(self, *args, **kwargs):
                return dict(ok=False, code='composer_not_found',
                            hint='输入框定位失败', missing='豆包输入框控件',
                            next_action='切到豆包窗口后重派')

        original_for = dispatch.adapter_for
        dispatch.adapter_for = lambda name: ('doubao', FailingAdapter())
        try:
            outcome = adapter_chain.run(dict(steps=[dict(
                index=1, name='豆包', app_id='doubao',
                instruction='用豆包写一段一百字左右的自我介绍，直接给出正文')]))
        finally:
            dispatch.adapter_for = original_for
        self.assertFalse(outcome['ok'])
        self.assertEqual(outcome['failure_code'], 'composer_not_found')
        self.assertIn('composer_not_found', outcome['error'])
        self.assertIn('下一步', outcome['error'])
        self.assertEqual(len(outcome['steps']), 1)      # 失败即停，不再跑下一步
        for phrase in ('已转交', '正在生成', '后台每', '请你手动'):
            self.assertNotIn(phrase, outcome['error'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
