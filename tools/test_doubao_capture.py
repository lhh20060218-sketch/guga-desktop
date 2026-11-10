# -*- coding: utf-8 -*-
"""回归：豆包取正文的两道坎——滚到底判定、复制锚点三级兜底、capture_empty 缺失文案。

s3 现场（20261110s3，19:28）：
    固定滚 10 格没到底（09_after_scroll.png 右下“回到底部”箭头还在），
    复制锚点只认 OCR 里的「免」/「今 HH:MM」，一个都没命中，两条复制路径都没触发，
    最终 capture_empty，但“缺什么”只填了失败码。

单独执行：python tools/test_doubao_capture.py
"""
import ctypes
import contextlib
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core import adapter_chain  # noqa: E402
from core.adapters import doubao_adapter  # noqa: E402
from core.adapters.doubao_adapter import DoubaoAdapter  # noqa: E402


def _frame(level):
    return Image.new("RGB", (80, 60), (level, level, level))


class _FakeUser:
    """替掉 ctypes.windll.user32：只记录滚轮/光标，不真的动系统。"""

    def __init__(self):
        self.wheels = 0
        self.cursor = None
        self.history = []

    def SetCursorPos(self, x, y):
        self.cursor = (x, y)
        self.history.append((x, y))

    def mouse_event(self, *args):
        self.wheels += 1


def _words(*rows):
    """构造 OCR 词表：每行 (text, x, y, w)，高度固定 0.02（归一化坐标）。"""
    return [{"text": text, "x": x, "y": y, "w": w, "h": 0.02}
            for text, x, y, w in rows]


ANSWER_WORDS = _words(("正文第一段", 0.40, 0.30, 0.30),
                      ("正文第二段", 0.40, 0.45, 0.30),
                      ("正文第三段", 0.40, 0.60, 0.30))


class ScrollToBottomTests(unittest.TestCase):
    @staticmethod
    def _adapter():
        adapter = DoubaoAdapter.__new__(DoubaoAdapter)
        adapter._point_is_target = staticmethod(lambda *a, **k: True)
        return adapter

    def _run(self, frames, max_rounds=12, uia=None, words=None):
        adapter = self._adapter()
        user = _FakeUser()
        events = []

        def step(name, **kw):
            events.append(dict(event=name, **kw))

        with patch.object(ctypes.windll, "user32", user), \
             patch("core.adapters.doubao_adapter.win32gui.GetWindowRect",
                   return_value=(0, 0, 1000, 800)), \
             patch.object(doubao_adapter.time, "sleep", lambda *a, **k: None), \
             patch.object(DoubaoAdapter, "_uia_scroll_state",
                          return_value=uia or {"available": False}), \
             patch.object(DoubaoAdapter, "_capture_words", side_effect=frames):
            result = adapter._scroll_to_bottom(1, max_rounds=max_rounds,
                                               step=step, words=words)
        return result, user, events

    def test_marker_gone_means_bottom(self):
        result, user, _ = self._run([(_frame(10), [], "回到底部"), (_frame(10), [], "正文")])
        self.assertEqual(result["reason"], "marker_gone")
        self.assertEqual(result["state"], doubao_adapter.SCROLL_AT_BOTTOM)
        self.assertEqual(result["rounds"], 2)
        self.assertGreater(user.wheels, 0)

    def test_unchanged_page_means_bottom(self):
        # 先真滚动一次（视口变化），之后连续 SCROLL_STABLE_ROUNDS 轮哈希不变 → 到底。
        frames = [(_frame(10), [], "正文")] + [(_frame(20), [], "正文")] * 4
        result, _, _ = self._run(frames)
        self.assertEqual(result["reason"], "page_stable")
        self.assertEqual(result["state"], doubao_adapter.SCROLL_AT_BOTTOM)
        self.assertEqual(result["rounds"], doubao_adapter.SCROLL_STABLE_ROUNDS + 2)
        self.assertTrue(result["stable"])

    def test_hard_cap_prevents_endless_scroll(self):
        frames = [(_frame(level), [], "第%s段" % level) for level in (10, 20, 30, 40)]
        result, _, _ = self._run(frames, max_rounds=3)
        self.assertEqual(result["reason"], "budget_exhausted")
        self.assertEqual(result["state"], doubao_adapter.SCROLL_STILL_MOVING)
        self.assertEqual(result["rounds"], 3)

    def test_uia_scroll_pattern_at_bottom_is_at_bottom(self):
        result, user, _ = self._run([], uia={"available": True, "percent": 100.0,
                                            "view": 20.0, "at_bottom": True})
        self.assertEqual(result["state"], doubao_adapter.SCROLL_AT_BOTTOM)
        self.assertEqual(result["reason"], "uia_scroll_pattern")
        self.assertEqual(result["rounds"], 0)
        self.assertEqual(user.wheels, 0)

    def test_stable_but_uia_says_not_bottom_is_stuck(self):
        frames = [(_frame(10), [], "正文")] + [(_frame(20), [], "正文")] * 4
        result, _, _ = self._run(frames, uia={"available": True, "percent": 40.0,
                                             "view": 20.0, "at_bottom": False})
        self.assertEqual(result["state"], doubao_adapter.SCROLL_STUCK)
        self.assertEqual(result["reason"], "stable_but_uia_not_bottom")

    def test_pointer_moves_from_dead_point_to_body_then_scroll_succeeds(self):
        # ① 落点无效（页面不动）→ 换正文区另一个位置 → 内容变化 → 成功判到底。
        dead = (_frame(10), [], "开头")
        moved = (_frame(20), [], "中段")
        frames = [dead, dead, dead, moved, moved, moved, moved]
        result, user, events = self._run(frames, max_rounds=8, words=ANSWER_WORDS)
        self.assertEqual(result["state"], doubao_adapter.SCROLL_AT_BOTTOM)
        self.assertEqual(result["reason"], "page_stable")
        self.assertGreaterEqual(result["pointer"]["switches"], 1)
        self.assertGreaterEqual(len(set(user.history)), 2)   # 光标真的换了位置
        pointers = [row for row in events if row["event"] == "scroll_pointer"]
        self.assertTrue(pointers)
        for row in pointers:
            self.assertIn("target_rect", row)
            self.assertIn("center", row)
            self.assertIn("moved_from", row)
            # 落点必须在回答区矩形内（正文中心 0.40~0.70 × 0.30~0.62）
            cx, cy = row["center"]
            self.assertTrue(0.40 * 1000 <= cx <= 0.70 * 1000)
            self.assertTrue(0.30 * 800 <= cy <= 0.62 * 800)

    def test_all_targets_ineffective_is_wrong_target_not_bottom(self):
        # ② 连续无效 → scroll_wrong_target，不能被记成 at_bottom / scroll_stuck。
        frames = [(_frame(10), [], "正文")] * 8
        result, _, events = self._run(frames, words=ANSWER_WORDS)
        self.assertEqual(result["state"], doubao_adapter.SCROLL_WRONG_TARGET)
        self.assertNotEqual(result["state"], doubao_adapter.SCROLL_AT_BOTTOM)
        self.assertNotEqual(result["state"], doubao_adapter.SCROLL_STUCK)
        self.assertEqual(result["reason"], "all_targets_ineffective")
        switches = [row for row in events if row["event"] == "scroll_pointer_switch"]
        self.assertEqual(len(switches), 2)          # center → upper → lower

    def test_pointer_restored_after_scroll(self):
        # ④ 结束时光标回到操作前坐标（断言 SetCursorPos 参数等于 before）。
        frames = [(_frame(10), [], "正文")] + [(_frame(20), [], "正文")] * 4
        adapter = self._adapter()
        user = _FakeUser()
        events = []

        def step(name, **kw):
            events.append(dict(event=name, **kw))

        with patch.object(ctypes.windll, "user32", user), \
             patch("core.adapters.doubao_adapter.win32gui.GetWindowRect",
                   return_value=(0, 0, 1000, 800)), \
             patch("core.adapters.doubao_adapter.win32gui.GetCursorPos",
                   return_value=(7, 9)), \
             patch.object(doubao_adapter.time, "sleep", lambda *a, **k: None), \
             patch.object(DoubaoAdapter, "_uia_scroll_state",
                          return_value={"available": False}), \
             patch.object(DoubaoAdapter, "_capture_words", side_effect=frames):
            adapter._scroll_to_bottom(1, step=step)
        self.assertEqual(user.cursor, (7, 9))
        self.assertEqual(user.history[-1], (7, 9))
        restores = [row for row in events if row["event"] == "pointer_restore"]
        self.assertEqual(len(restores), 1)
        self.assertEqual(restores[0]["before"], [7, 9])
        self.assertTrue(restores[0]["restored"])

    def test_bottom_marker_visible(self):
        self.assertTrue(DoubaoAdapter._bottom_marker_visible([], "回到底部"))
        self.assertTrue(DoubaoAdapter._bottom_marker_visible(
            [{"text": "回", "x": 0.9, "y": 0.9, "w": 0.02, "h": 0.02},
             {"text": "到底部", "x": 0.92, "y": 0.9, "w": 0.06, "h": 0.02}], ""))
        self.assertFalse(DoubaoAdapter._bottom_marker_visible([], "正文"))

    def test_frame_signature_ignores_tiny_noise(self):
        sig = DoubaoAdapter._frame_signature(_frame(10))
        self.assertEqual(DoubaoAdapter._frame_delta(sig, sig), 0.0)
        other = DoubaoAdapter._frame_signature(_frame(200))
        self.assertGreater(DoubaoAdapter._frame_delta(sig, other), 2.0)


class CopyFallbackTests(unittest.TestCase):
    PROMPT = "写一句话"
    COPIED = "写一句话\n这是豆包的回答内容，足够长可以校验。"
    PAGE = COPIED

    @staticmethod
    def _adapter():
        adapter = DoubaoAdapter.__new__(DoubaoAdapter)
        adapter._ocr_unavailable = False
        adapter.evidence_root = Path(tempfile.mkdtemp(prefix="guga-cap-"))
        return adapter

    def _call(self, adapter, page=None):
        step = MagicMock()
        evidence = Path(tempfile.mkdtemp(prefix="guga-ev-"))
        with patch.object(DoubaoAdapter, "_capture_words",
                          return_value=(None, [], self.PAGE if page is None else page)), \
             patch.object(DoubaoAdapter, "_scroll_to_bottom",
                          return_value={"scrolled": True, "rounds": 2,
                                        "reason": "page_stable", "words": [],
                                        "page_text": self.PAGE, "marker": False,
                                        "stable": True}):
            return adapter._capture_answer(1, self.PROMPT, evidence, step)

    def test_uia_button_is_first_level(self):
        adapter = self._adapter()
        adapter._copy_via_action_bar = MagicMock(return_value="")
        adapter._copy_via_uia_button = MagicMock(return_value=self.COPIED)
        adapter._copy_via_answer_button = MagicMock(return_value="")
        adapter._copy_via_more_menu = MagicMock(return_value="")
        adapter._copy_via_select_all = MagicMock(return_value="")
        result = self._call(adapter)
        self.assertTrue(result["ok"])
        self.assertEqual(result["copied_from"], "uia_button")
        adapter._copy_via_answer_button.assert_not_called()
        self.assertEqual([item["path"] for item in result["copy_paths"]],
                         ["action_bar", "uia_button"])

    def test_falls_back_to_select_all(self):
        adapter = self._adapter()
        adapter._copy_via_action_bar = MagicMock(return_value="")
        adapter._copy_via_uia_button = MagicMock(return_value="")
        adapter._copy_via_answer_button = MagicMock(return_value="")
        adapter._copy_via_more_menu = MagicMock(return_value="")
        adapter._copy_via_select_all = MagicMock(return_value=self.COPIED)
        result = self._call(adapter)
        self.assertTrue(result["ok"])
        self.assertEqual(result["copied_from"], "select_all")
        self.assertEqual([item["path"] for item in result["copy_paths"]],
                         ["action_bar", "uia_button", "ocr_anchor", "ocr_more_menu",
                          "select_all"])

    def test_all_levels_empty_reports_concrete_missing(self):
        adapter = self._adapter()
        for name in ("_copy_via_action_bar", "_copy_via_uia_button",
                     "_copy_via_answer_button", "_copy_via_more_menu",
                     "_copy_via_select_all"):
            setattr(adapter, name, MagicMock(return_value=""))
        result = self._call(adapter)
        self.assertFalse(result["ok"])
        self.assertEqual(result["code"], "capture_empty")
        self.assertIn("UIA 结构里没找到", result["missing"])
        self.assertIn("Ctrl+A/Ctrl+C", result["missing"])
        self.assertIn("缺什么：", result["hint"])
        self.assertNotIn("。。", result["hint"])
        self.assertEqual(len(result["copy_paths"]), 5)

    def test_copied_but_not_visible_reports_visible_missing(self):
        adapter = self._adapter()
        adapter._copy_via_action_bar = MagicMock(return_value="")
        adapter._copy_via_uia_button = MagicMock(return_value="")
        adapter._copy_via_answer_button = MagicMock(return_value="")
        adapter._copy_via_more_menu = MagicMock(return_value="")
        adapter._copy_via_select_all = MagicMock(
            return_value="ZZZZZZZZZZZZZZZZQQQQQQQQQQQQQQQQ")
        result = self._call(adapter)
        self.assertFalse(result["ok"])
        self.assertIn("能与回答区 OCR 对上", result["missing"])
        self.assertNotIn("。。", result["hint"])


class CapturePathTimeoutTests(unittest.TestCase):
    """20261110t 真机现场：第 2 次取正文时 UIA 复制路径永久阻塞，链路既不出结果也不报错。

    修法：每一档复制路径跑在 daemon 线程里并带 join(timeout)，单档超时只丢这一档，
    整体超时后统一返回 capture_empty；日志里每档都有 path/started/elapsed/result。
    """

    PROMPT = "写一句话"
    COPIED = "写一句话\n这是豆包的回答内容，足够长可以校验。"
    PAGE = COPIED

    @staticmethod
    def _adapter():
        adapter = DoubaoAdapter.__new__(DoubaoAdapter)
        adapter._ocr_unavailable = False
        adapter.evidence_root = Path(tempfile.mkdtemp(prefix="guga-cap-"))
        return adapter

    def _call(self, adapter):
        step = MagicMock()
        evidence = Path(tempfile.mkdtemp(prefix="guga-ev-"))
        with patch.object(DoubaoAdapter, "_capture_words",
                          return_value=(None, [], self.PAGE)), \
             patch.object(DoubaoAdapter, "_scroll_to_bottom",
                          return_value={"scrolled": True, "rounds": 2,
                                        "reason": "page_stable", "words": [],
                                        "page_text": self.PAGE, "marker": False,
                                        "stable": True}):
            result = adapter._capture_answer(1, self.PROMPT, evidence, step)
        return result, step

    @staticmethod
    def _hang(*_args, **_kwargs):
        time.sleep(3)          # 复现“既不返回也不抛异常”的阻塞档
        return ""

    def test_all_paths_hang_returns_capture_empty_without_blocking(self):
        adapter = self._adapter()
        for name in ("_copy_via_action_bar", "_copy_via_uia_button",
                     "_copy_via_answer_button", "_copy_via_more_menu",
                     "_copy_via_select_all"):
            setattr(adapter, name, self._hang)
        timeout = dict(action_bar=0.15, uia_button=0.15, ocr_anchor=0.15,
                       ocr_more_menu=0.15, select_all=0.15)
        begin = time.time()
        with patch.object(doubao_adapter, "CAPTURE_PATH_TIMEOUT", timeout), \
             patch.object(doubao_adapter, "CAPTURE_TOTAL_TIMEOUT", 0.9):
            result, step = self._call(adapter)
        elapsed = time.time() - begin

        self.assertLess(elapsed, 2.0, "调用方被挂住的档拖住了")
        self.assertFalse(result["ok"])
        self.assertEqual(result["code"], "capture_empty")
        self.assertEqual(len(result["copy_paths"]), 5)
        self.assertEqual({item["result"] for item in result["copy_paths"]}, {"timeout"})
        self.assertIn("均超时", result["missing"])
        self.assertIn("最后一条是第 5 档 select_all", result["missing"])
        self.assertEqual(result["capture_timeouts"], 5)
        self.assertGreaterEqual(result["leftover_threads"], 1)
        logged = [call for call in step.call_args_list
                  if call.args and call.args[0] == "copy_path"]
        self.assertEqual(len(logged), 5)
        for call in logged:
            fields = call.kwargs
            self.assertIn(fields["path"], timeout)
            self.assertTrue(fields["started"])
            self.assertGreaterEqual(fields["elapsed"], 0)
            self.assertEqual(fields["result"], "timeout")

    def test_second_path_timeout_third_succeeds(self):
        adapter = self._adapter()
        adapter._copy_via_action_bar = MagicMock(return_value="")
        adapter._copy_via_uia_button = MagicMock(return_value="")
        adapter._copy_via_answer_button = self._hang
        adapter._copy_via_more_menu = MagicMock(return_value=self.COPIED)
        adapter._copy_via_select_all = MagicMock(return_value="")
        timeout = dict(action_bar=2.0, uia_button=2.0, ocr_anchor=0.15,
                       ocr_more_menu=2.0, select_all=2.0)
        begin = time.time()
        with patch.object(doubao_adapter, "CAPTURE_PATH_TIMEOUT", timeout), \
             patch.object(doubao_adapter, "CAPTURE_TOTAL_TIMEOUT", 5.0):
            result, _step = self._call(adapter)
        elapsed = time.time() - begin

        self.assertLess(elapsed, 2.0)
        self.assertTrue(result["ok"])
        self.assertEqual(result["copied_from"], "ocr_more_menu")
        self.assertEqual([item["result"] for item in result["copy_paths"]],
                         ["empty", "empty", "timeout", "ok"])
        self.assertEqual(result["capture_timeouts"], 1)
        adapter._copy_via_select_all.assert_not_called()

    def test_total_budget_skips_remaining_paths(self):
        adapter = self._adapter()
        for name in ("_copy_via_action_bar", "_copy_via_uia_button",
                     "_copy_via_answer_button", "_copy_via_more_menu",
                     "_copy_via_select_all"):
            setattr(adapter, name, self._hang)
        timeout = dict(action_bar=5.0, uia_button=5.0, ocr_anchor=5.0,
                       ocr_more_menu=5.0, select_all=5.0)
        with patch.object(doubao_adapter, "CAPTURE_PATH_TIMEOUT", timeout), \
             patch.object(doubao_adapter, "CAPTURE_TOTAL_TIMEOUT", 0.3):
            result, _step = self._call(adapter)
        self.assertFalse(result["ok"])
        self.assertEqual(result["copy_paths"][0]["result"], "timeout")
        self.assertEqual([item["result"] for item in result["copy_paths"][1:]],
                         ["skipped", "skipped", "skipped", "skipped"])
        self.assertIn("均未取到正文", result["missing"])
        self.assertIn("最后一条是第 5 档 select_all", result["missing"])


class UiaCopyButtonTests(unittest.TestCase):
    def test_lowest_copy_and_more_buttons(self):
        snapshot = {"elements": [
            {"type": "Button", "name": "复制", "offscreen": False,
             "rect": {"left": 10, "top": 300, "right": 50, "bottom": 340}},
            {"type": "Button", "name": "复制", "offscreen": False,
             "rect": {"left": 10, "top": 600, "right": 50, "bottom": 640}},
            {"type": "Button", "name": "复制链接", "offscreen": False,
             "rect": {"left": 10, "top": 660, "right": 50, "bottom": 700}},
            {"type": "Button", "name": "更多", "offscreen": False,
             "rect": {"left": 60, "top": 600, "right": 100, "bottom": 640}},
        ]}
        service = type("S", (), {"snapshot": lambda self, hwnd, **kw: snapshot})()
        with patch("core.uia_service.shared_service", return_value=service), \
             patch("core.adapters.doubao_adapter.win32gui.GetWindowRect",
                   return_value=(0, 0, 1000, 800)):
            targets = DoubaoAdapter._uia_copy_buttons(1)
        self.assertAlmostEqual(targets["copy"]["y"], 620 / 800.0)
        self.assertAlmostEqual(targets["more"]["y"], 620 / 800.0)
        self.assertNotEqual(targets["copy"]["y"], 320 / 800.0)


class BubbleTextTests(unittest.TestCase):
    def test_sentence_strips_trailing_period(self):
        self.assertEqual(adapter_chain._sentence("复制失败。"), "复制失败")
        self.assertEqual(adapter_chain._sentence("复制失败"), "复制失败")

    def test_missing_comes_from_hint(self):
        receipt = {"hint": "豆包失败。缺什么：正文复制锚点：UIA 没找到「复制」按钮。下一步：x"}
        self.assertEqual(adapter_chain._missing_of(receipt),
                         "正文复制锚点：UIA 没找到「复制」按钮")
        self.assertEqual(adapter_chain._missing_of(
            {"missing": "具体项", "hint": "缺什么：不该用这个"}), "具体项")

    def test_bubble_has_no_double_period(self):
        hint = "豆包有回复但没能复制出正文。"
        missing = "正文复制锚点：UIA 没找到「复制」按钮。"
        text = ("第 1/2 步（豆包）失败：%s。缺什么：%s。下一步：%s。"
                % (adapter_chain._sentence(hint), adapter_chain._sentence(missing),
                   adapter_chain._sentence("重试。")))
        self.assertNotIn("。。", text)


class ComposerPlaceholderTests(unittest.TestCase):
    """20261110aa 现场：空输入框读回的占位是“发消息或按住空格说话...”（13 字），
    旧占位清单没有这版文案，input_verified 误判“清空后仍有残留”，三次都不写入，
    报 input_verify_failed。这里锁定新版占位必须被剔成空串。"""

    def test_speaking_placeholder_is_stripped(self):
        text = "发消息或按住空格说话...\n"
        self.assertEqual(doubao_adapter._strip_composer_placeholder(text), "")

    def test_variants_and_real_text_kept(self):
        self.assertEqual(
            doubao_adapter._strip_composer_placeholder("按住空格说话..."), "")
        self.assertEqual(
            doubao_adapter._strip_composer_placeholder("发消息或创建任务"), "")
        self.assertEqual(
            doubao_adapter._strip_composer_placeholder("第一页：封面\n按住空格说话..."),
            "第一页：封面")

    def test_user_text_starting_with_similar_words_kept(self):
        self.assertEqual(
            doubao_adapter._strip_composer_placeholder("发消息给我一份 PPT 提示词"),
            "发消息给我一份 PPT 提示词")


class UiaCopyStepSignatureTests(unittest.TestCase):
    """20261110v 现场：step(name, **fields) 与 step(..., name=...) 撞车，UIA 复制档 100% 抛
    TypeError，白耗 2.3s 后降级。这里用真实签名的 step 跑一遍，断言不再抛异常。"""

    COPIED = "## 标题\n1. 第一页\n- 要点\n" + "正文内容" * 20

    @staticmethod
    def _adapter(targets):
        adapter = DoubaoAdapter.__new__(DoubaoAdapter)
        adapter._uia_copy_buttons = lambda hwnd: targets
        adapter._click = lambda hwnd, x, y: None
        adapter._send = lambda keys: None
        return adapter

    def _run(self, targets):
        events = []

        def step(event, **fields):        # 与 _ui_attempt 内部签名一致
            events.append((event, fields))

        adapter = self._adapter(targets)
        with patch.object(doubao_adapter, "_write_clipboard", lambda text: True), \
             patch.object(doubao_adapter, "_read_clipboard", lambda: self.COPIED), \
             patch.object(doubao_adapter.time, "sleep", lambda *a, **k: None):
            text = adapter._copy_via_uia_button(1, Path("."), step)
        return text, events

    def test_copy_button_path_no_typeerror(self):
        text, events = self._run(
            {"copy": {"x": 0.5, "y": 0.5, "name": "复制"}, "more": None})
        self.assertEqual(text, self.COPIED)
        self.assertEqual(events[0][0], "copy_uia_button")
        self.assertEqual(events[0][1]["target"], "复制")

    def test_more_menu_path_no_typeerror(self):
        targets = {"copy": None,
                   "more": {"x": 0.6, "y": 0.5, "name": "更多"}}
        adapter = self._adapter(targets)
        events = []

        def step(event, **fields):
            events.append((event, fields))

        # 第一次快照返回“只有更多按钮”，点开后菜单里出现“复制”
        snapshots = [targets, {"copy": {"x": 0.6, "y": 0.7, "name": "复制"}, "more": None}]
        adapter._uia_copy_buttons = lambda hwnd: snapshots.pop(0)
        with patch.object(doubao_adapter, "_write_clipboard", lambda text: True), \
             patch.object(doubao_adapter, "_read_clipboard", lambda: self.COPIED), \
             patch.object(doubao_adapter.time, "sleep", lambda *a, **k: None):
            text = adapter._copy_via_uia_button(1, Path("."), step)
        self.assertEqual(text, self.COPIED)
        names = [event for event, _fields in events]
        self.assertIn("copy_uia_more", names)
        self.assertIn("copy_uia_more_item", names)


class CaptureRegionTests(unittest.TestCase):
    """OCR 区域限定到回答块：长回答只有最后一屏在视口里，覆盖率方向要反过来算。"""

    ROWS = ["%d. 第%d页 企业级 AI Agent 落地实践" % (i, i) for i in range(1, 10)]

    def _region(self):
        words = [
            {"text": "豆包", "x": 0.02, "y": 0.03, "w": 0.05, "h": 0.02},
            {"text": "侧栏会话列表", "x": 0.04, "y": 0.66, "w": 0.10, "h": 0.02},
            {"text": "复制 重新生成 分享", "x": 0.3, "y": 0.7, "w": 0.2, "h": 0.02},
            {"text": "发消息", "x": 0.5, "y": 0.9, "w": 0.2, "h": 0.02},
        ]
        for index, text in enumerate(self.ROWS):
            words.append({"text": text, "x": 0.3, "y": 0.25 + index * 0.04,
                          "w": 0.45, "h": 0.03})
        return DoubaoAdapter._answer_region(words, "提示词")

    def test_region_excludes_chrome_and_action_row(self):
        region = self._region()
        self.assertIsNotNone(region)
        self.assertIn("第1页", region["text"])
        self.assertNotIn("侧栏", region["text"])
        self.assertNotIn("发消息", region["text"])
        self.assertNotIn("复制", region["text"])
        self.assertGreaterEqual(region["lines"], 9)

    def test_region_coverage_is_high_for_visible_answer(self):
        answer = "\n".join(self.ROWS) + "\n" + "更早的正文在视口之外" * 20
        region = self._region()
        check = DoubaoAdapter._answer_visible_in_page(answer, "无关页面文字", region["text"])
        self.assertEqual(check["region"], "answer_block")
        self.assertGreaterEqual(check["ratio"], 0.9)
        self.assertTrue(check["ratio"] >= 0.6 or check["windows"] >= 2)

    def test_empty_text_stays_empty(self):
        check = DoubaoAdapter._answer_visible_in_page("", "", None)
        self.assertEqual(check["ratio"], 0.0)
        self.assertEqual(check["windows"], 0)


class CaptureDegradeTests(unittest.TestCase):
    """覆盖率低时只有“复制来源可确认 + 长度合理 + 结构像正文”三者全满才降级放行。"""

    PROMPT = "写一句话"
    PAGE = "完全无关的另一段页面文字，OCR 识别到的内容与剪贴板并不相同。"
    LONG = ("## 2026 企业级 AI Agent 落地实践\n"
            "1. 第一页：趋势与背景\n"
            "2. 第二页：技术架构\n"
            "- 要点一：模型能力\n"
            "- 要点二：工程落地\n") + "正文内容" * 40

    @staticmethod
    def _adapter(copied, method="uia_button"):
        adapter = DoubaoAdapter.__new__(DoubaoAdapter)
        adapter._ocr_unavailable = False
        adapter.evidence_root = Path(tempfile.mkdtemp(prefix="guga-cap-"))
        for name in ("_copy_via_uia_button", "_copy_via_answer_button",
                     "_copy_via_more_menu", "_copy_via_select_all"):
            setattr(adapter, name, MagicMock(return_value=""))
        setattr(adapter, {"uia_button": "_copy_via_uia_button",
                          "ocr_anchor": "_copy_via_answer_button",
                          "ocr_more_menu": "_copy_via_more_menu",
                          "select_all": "_copy_via_select_all"}[method],
                MagicMock(return_value=copied))
        return adapter

    def _call(self, adapter):
        step = MagicMock()
        evidence = Path(tempfile.mkdtemp(prefix="guga-ev-"))
        with patch.object(DoubaoAdapter, "_capture_words",
                          return_value=(None, [], self.PAGE)), \
             patch.object(DoubaoAdapter, "_scroll_to_bottom",
                          return_value={"scrolled": True, "rounds": 2,
                                        "reason": "page_stable", "words": [],
                                        "page_text": self.PAGE, "marker": False,
                                        "stable": True}):
            return adapter._capture_answer(1, self.PROMPT, evidence, step)

    def test_low_coverage_with_all_three_conditions_is_degraded(self):
        result = self._call(self._adapter(self.LONG, "uia_button"))
        self.assertTrue(result["ok"], result.get("missing"))
        check = result["copy_checks"][0]
        self.assertLess(float(check["ratio"]), 0.6)
        self.assertIn("OCR 覆盖不足降级放行", check["degrade_reason"])
        self.assertTrue(check["visible_in_page"])
        self.assertEqual(result["copied_from"], "uia_button")

    def test_low_coverage_without_copy_button_source_stays_empty(self):
        result = self._call(self._adapter(self.LONG, "select_all"))
        self.assertFalse(result["ok"])
        self.assertEqual(result["code"], "capture_empty")
        self.assertEqual(result["copy_checks"][0]["degrade_reason"], "")

    def test_low_coverage_fragment_stays_empty(self):
        short = "这是一段很短的残片。"
        result = self._call(self._adapter(short, "uia_button"))
        self.assertFalse(result["ok"])
        self.assertEqual(result["code"], "capture_empty")
        self.assertEqual(result["copy_checks"][0]["degrade_reason"], "")

    def test_low_coverage_without_structure_stays_empty(self):
        flat = "普通回答没有标题也没有编号列表" * 20
        result = self._call(self._adapter(flat, "uia_button"))
        self.assertFalse(result["ok"])
        self.assertEqual(result["code"], "capture_empty")
        self.assertEqual(result["copy_checks"][0]["degrade_reason"], "")


class FakeClipboard:
    """最小剪贴板替身：只实现本模块用到的 6 个接口。"""

    def __init__(self, rows=None):
        self.rows = dict(rows or {})
        self.fail_open = 0
        self.always_fail_open = False

    def OpenClipboard(self):
        if self.always_fail_open:
            raise RuntimeError("剪贴板被占用")
        if self.fail_open > 0:
            self.fail_open -= 1
            raise RuntimeError("剪贴板被占用")

    def CloseClipboard(self):
        pass

    def EmptyClipboard(self):
        self.rows = {}

    def EnumClipboardFormats(self, fmt):
        for key in sorted(self.rows):
            if key > fmt:
                return key
        return 0

    def GetClipboardData(self, fmt):
        return self.rows[fmt]

    def SetClipboardData(self, fmt, value):
        self.rows[fmt] = value


class ClipboardRestoreTests(unittest.TestCase):
    """20261110v 现场：豆包“复制”留下 7 个格式，恢复函数返回 false 就退出了，污染留存。"""

    ORIGINAL = {13: "用户原文", 49161: "<html>用户原文</html>".encode("utf-8")}
    POLLUTED = {1: "豆包正文", 7: "豆包正文", 13: "豆包正文", 16: "zh-CN".encode("utf-8"),
                49161: "<html>豆包正文</html>".encode("utf-8"),
                49351: b"token", 49370: b"url"}

    def test_restore_after_seven_format_pollution(self):
        clip = FakeClipboard(self.ORIGINAL)
        with patch.object(doubao_adapter, "_clip", clip):
            snapshot = doubao_adapter._snapshot_clipboard()
            clip.rows = dict(self.POLLUTED)
            result = doubao_adapter._restore_clipboard(snapshot)
        self.assertTrue(result["restore_ok"], result)
        self.assertEqual(result["attempts"], 1)
        self.assertEqual(result["leftover_formats"], [])
        self.assertEqual(clip.rows, self.ORIGINAL)

    def test_restore_retries_after_first_failure(self):
        clip = FakeClipboard(self.ORIGINAL)
        with patch.object(doubao_adapter, "_clip", clip), \
             patch.object(doubao_adapter.time, "sleep", lambda *a, **k: None):
            snapshot = doubao_adapter._snapshot_clipboard()
            clip.rows = dict(self.POLLUTED)
            clip.fail_open = 1
            result = doubao_adapter._restore_clipboard(snapshot)
        self.assertTrue(result["restore_ok"], result)
        self.assertEqual(result["attempts"], 2)
        self.assertEqual(clip.rows, self.ORIGINAL)

    def test_restore_failure_is_reported_not_silent(self):
        clip = FakeClipboard(self.ORIGINAL)
        with patch.object(doubao_adapter, "_clip", clip), \
             patch.object(doubao_adapter.time, "sleep", lambda *a, **k: None):
            snapshot = doubao_adapter._snapshot_clipboard()
            clip.rows = dict(self.POLLUTED)
            clip.always_fail_open = True
            result = doubao_adapter._restore_clipboard(snapshot)
        self.assertFalse(result["restore_ok"])
        self.assertEqual(result["attempts"], 4)
        self.assertIn("剪贴板被占用", result["error"])

    def test_capture_exception_still_restores_clipboard(self):
        adapter = DoubaoAdapter.__new__(DoubaoAdapter)
        adapter._ocr_unavailable = False
        adapter.evidence_root = Path(tempfile.mkdtemp(prefix="guga-cap-"))
        clip = FakeClipboard(self.ORIGINAL)
        events = []

        def step(event, **fields):
            events.append((event, fields))

        def boom(hwnd, path=None):
            doubao_adapter._write_clipboard("豆包正文")   # 触发懒快照并写入
            clip.rows = dict(self.POLLUTED)              # 模拟复制留下 7 个格式
            raise RuntimeError("复制后页面崩了")

        evidence = Path(tempfile.mkdtemp(prefix="guga-ev-"))
        with patch.object(doubao_adapter, "_clip", clip), \
             patch.object(DoubaoAdapter, "_capture_words", side_effect=boom), \
             patch.object(doubao_adapter.time, "sleep", lambda *a, **k: None):
            with self.assertRaises(RuntimeError):
                adapter._capture_answer(1, "提示词", evidence, step)

        self.assertEqual(clip.rows, self.ORIGINAL)
        names = [event for event, _fields in events]
        self.assertIn("clipboard_restore", names)
        restored = dict(events)["clipboard_restore"]
        self.assertTrue(restored["restore_ok"])


class ClipboardCrossThreadTests(unittest.TestCase):
    """20261110w 现场：复制跑在 doubao-capture-* 工作线程里，快照盒是 threading.local，
    主线程看不到 worker 的 tried 标记 → 恢复被跳过还谎报 restore_ok=true。

    修法：快照盒跨线程共享（普通 dict + 锁），恢复由真正写剪贴板的线程在 finally 里做，
    restore_ok 由恢复后的实际格式集合比对得出。
    """

    ORIGINAL = {13: "用户原文", 49161: "<html>用户原文</html>".encode("utf-8")}
    POLLUTED = {1: "豆包正文", 7: "豆包正文", 13: "豆包正文", 16: "zh-CN".encode("utf-8"),
                49161: "<html>豆包正文</html>".encode("utf-8"),
                49351: b"token", 49370: b"url"}
    PROMPT = "写一句话"
    COPIED = "写一句话\n这是豆包的回答内容，足够长可以校验。"
    PAGE = COPIED

    @staticmethod
    def _adapter():
        adapter = DoubaoAdapter.__new__(DoubaoAdapter)
        adapter._ocr_unavailable = False
        adapter.evidence_root = Path(tempfile.mkdtemp(prefix="guga-cap-"))
        return adapter

    def _capture(self, adapter, copy_func, clip):
        """跑完整 _capture_answer：复制函数在 doubao-capture-* 工作线程里执行。"""
        step = MagicMock()
        evidence = Path(tempfile.mkdtemp(prefix="guga-ev-"))
        adapter._copy_via_uia_button = copy_func
        adapter._copy_via_answer_button = MagicMock(return_value="")
        adapter._copy_via_more_menu = MagicMock(return_value="")
        adapter._copy_via_select_all = MagicMock(return_value="")
        with patch.object(doubao_adapter, "_clip", clip), \
             patch.object(DoubaoAdapter, "_capture_words",
                          return_value=(None, [], self.PAGE)), \
             patch.object(DoubaoAdapter, "_scroll_to_bottom",
                          return_value={"scrolled": True, "rounds": 2,
                                        "reason": "page_stable", "words": [],
                                        "page_text": self.PAGE, "marker": False,
                                        "stable": True}):
            result = adapter._capture_answer(1, self.PROMPT, evidence, step)
        return result, step

    def test_worker_write_is_restored_and_snapshot_shared_across_threads(self):
        """① worker 写剪贴板、主流程正常结束 → 恢复且校验通过；主线程能读到 worker 写的快照。"""
        adapter = self._adapter()
        clip = FakeClipboard(self.ORIGINAL)
        seen = {}

        def copy(hwnd, evidence_dir, step):
            seen["thread"] = threading.current_thread().name
            seen["box"] = doubao_adapter._clip_session_box()
            doubao_adapter._write_clipboard("豆包正文")
            clip.rows = dict(self.POLLUTED)          # 模拟复制留下 7 个格式
            return self.COPIED

        box_ref = {}
        real_begin = doubao_adapter._clip_session_begin

        def begin():
            box = real_begin()
            box_ref["box"] = box                      # 主线程建盒
            return box

        with patch.object(doubao_adapter, "_clip_session_begin", begin):
            result, _step = self._capture(adapter, copy, clip)

        # 跨线程证明：worker 拿到的是主线程建的那一份 dict，且主线程事后能看到 worker 写的快照
        self.assertIs(seen["box"], box_ref["box"])
        self.assertTrue(seen["thread"].startswith("doubao-capture-"))
        self.assertTrue(box_ref["box"]["tried"])
        self.assertEqual(box_ref["box"]["formats"], sorted(self.ORIGINAL))
        self.assertEqual(box_ref["box"]["restore"]["restored_in"], seen["thread"])
        self.assertTrue(result["ok"])
        self.assertTrue(result["clipboard_restore"]["restore_ok"])
        self.assertFalse(result["clipboard_restore"]["skipped"])
        self.assertEqual(clip.rows, self.ORIGINAL)

    def test_worker_exception_still_restores(self):
        """② worker 抛异常 → 仍恢复。"""
        adapter = self._adapter()
        clip = FakeClipboard(self.ORIGINAL)
        box = doubao_adapter._clip_session_begin()
        try:
            def boom():
                doubao_adapter._write_clipboard("豆包正文")
                clip.rows = dict(self.POLLUTED)
                raise RuntimeError("复制后页面崩了")

            with patch.object(doubao_adapter, "_clip", clip), \
                 patch.object(doubao_adapter.time, "sleep", lambda *a, **k: None):
                info, text = adapter._run_capture_path("uia_button", boom, (), 2.0)
        finally:
            doubao_adapter._clip_session_end(box)

        self.assertEqual(text, "")
        self.assertEqual(info["result"], "error")
        self.assertEqual(clip.rows, self.ORIGINAL)
        self.assertTrue(box["restore"]["restore_ok"], box["restore"])
        self.assertTrue(box["restore"]["restored_in"].startswith("doubao-capture-"))

    def test_restore_retries_inside_worker_and_succeeds(self):
        """③ 恢复第一次失败 → 重试成功（仍在 worker 线程里完成）。"""
        adapter = self._adapter()
        clip = FakeClipboard(self.ORIGINAL)
        box = doubao_adapter._clip_session_begin()
        try:
            def flaky():
                doubao_adapter._write_clipboard("豆包正文")
                clip.rows = dict(self.POLLUTED)
                clip.fail_open = 1                  # 只让恢复的第一次 OpenClipboard 失败
                return "正文"

            with patch.object(doubao_adapter, "_clip", clip), \
                 patch.object(doubao_adapter.time, "sleep", lambda *a, **k: None):
                adapter._run_capture_path("uia_button", flaky, (), 2.0)
        finally:
            doubao_adapter._clip_session_end(box)

        restore = box["restore"]
        self.assertTrue(restore["restore_ok"], restore)
        self.assertEqual(restore["attempts"], 2)
        self.assertEqual(clip.rows, self.ORIGINAL)

    def test_restore_failure_sets_warning_in_result(self):
        """④ 始终失败 → 告警字段出现且 restore_ok=false（禁止静默或谎报）。"""
        adapter = self._adapter()
        clip = FakeClipboard(self.ORIGINAL)

        def copy(hwnd, evidence_dir, step):
            doubao_adapter._write_clipboard("豆包正文")
            clip.rows = dict(self.POLLUTED)
            clip.always_fail_open = True            # 写入之后才坏，保证 tried/wrote 为真
            return self.COPIED

        result, step = self._capture(adapter, copy, clip)

        self.assertTrue(result["ok"])
        self.assertFalse(result["clipboard_restore"]["restore_ok"])
        self.assertEqual(result["clipboard_restore"]["attempts"], 4)
        self.assertIn("clipboard_restore_warning", result)
        warning = result["clipboard_restore_warning"]
        self.assertFalse(warning["restore_ok"])
        names = [call.args[0] for call in step.call_args_list if call.args]
        self.assertIn("clipboard_restore_warning", names)

    def test_no_write_is_skipped_and_clipboard_untouched(self):
        """⑤ 本轮未写入 → skipped=true 且剪贴板确实没动。"""
        adapter = self._adapter()
        clip = FakeClipboard(self.ORIGINAL)
        result, _step = self._capture(adapter, MagicMock(return_value=""), clip)

        self.assertFalse(result["ok"])
        restore = result["clipboard_restore"]
        self.assertTrue(restore["skipped"])
        self.assertTrue(restore["restore_ok"])
        self.assertEqual(restore["attempts"], 0)
        self.assertEqual(clip.rows, self.ORIGINAL)


class DocumentCardTests(unittest.TestCase):
    """20261110w 现场：豆包把 18 页正文放进“在线文档卡片”，对话里只剩约 100 字摘要，
    还弹出“暂不支持当前场景打开”，四档复制全落空，却被报成 capture_empty。
    """

    PROMPT = "用豆包生成PPT提示词"
    SUMMARY = "这是在线文档摘要，正文在卡片里。"
    COPIED = ("# 2026 企业级 AI Agent 落地实践\n"
              "1. 趋势判断：企业从单点试点转向流程级编排。\n"
              "2. 落地路径：先做知识库，再做工具调用，最后做多 Agent 协作。\n"
              "3. 治理：权限、审计、评测三件套必须同步建设。\n"
              "## P1 封面\n2026 企业级 AI Agent 落地实践\n"
              "## P2 目录\n趋势、路径、治理、案例、路线图。\n")

    @staticmethod
    def _adapter():
        adapter = DoubaoAdapter.__new__(DoubaoAdapter)
        adapter._ocr_unavailable = False
        adapter.evidence_root = Path(tempfile.mkdtemp(prefix="guga-card-"))
        return adapter

    def _run(self, adapter, words, page, doc_copy, dismiss=None):
        step = MagicMock()
        evidence = Path(tempfile.mkdtemp(prefix="guga-card-ev-"))
        adapter._capture_words = MagicMock(return_value=(None, words, page))
        adapter._scroll_to_bottom = MagicMock(return_value=dict(
            scrolled=True, rounds=2, reason="page_stable", words=words,
            page_text=page, marker=False, stable=True))
        adapter._copy_via_document_card = doc_copy
        adapter._copy_via_action_bar = MagicMock(return_value="")
        adapter._copy_via_uia_button = MagicMock(return_value="")
        adapter._copy_via_answer_button = MagicMock(return_value="")
        adapter._copy_via_more_menu = MagicMock(return_value="")
        adapter._copy_via_select_all = MagicMock(return_value="")
        if dismiss is not None:
            adapter._dismiss_card_overlay = dismiss
        result = adapter._capture_answer(1, self.PROMPT, evidence, step)
        return result, step

    def test_card_with_overlay_closes_then_copies(self):
        """① 卡片+浮层 → 关浮层 → 点卡片复制成功。"""
        adapter = self._adapter()
        initial_words = [dict(text="在线文档", x=0.2, y=0.3, w=0.2, h=0.03),
                         dict(text="暂不支持当前场景打开", x=0.2, y=0.5, w=0.4, h=0.03),
                         dict(text=self.SUMMARY, x=0.1, y=0.35, w=0.6, h=0.03)]
        fresh_words = [dict(text="在线文档", x=0.2, y=0.3, w=0.2, h=0.03),
                       dict(text="查看文档", x=0.2, y=0.5, w=0.2, h=0.03),
                       dict(text=self.SUMMARY, x=0.1, y=0.35, w=0.6, h=0.03)]
        dismiss = MagicMock(return_value=(True, fresh_words, self.COPIED))
        doc_copy = MagicMock(return_value=self.COPIED)

        result, step = self._run(adapter, initial_words, self.SUMMARY,
                                 doc_copy, dismiss=dismiss)

        dismiss.assert_called_once()
        doc_copy.assert_called_once()
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["copied_from"], "document_card")
        names = [call.args[0] for call in step.call_args_list if call.args]
        self.assertIn("document_card", names)
        card_call = [call for call in step.call_args_list
                     if call.args and call.args[0] == "document_card"][0]
        self.assertTrue(card_call.kwargs.get("overlay"))   # 浮层被识别到并触发关闭

    def test_card_without_copy_entry_returns_document_card_code(self):
        """② 卡片但无复制入口 → reply_in_card，不是 capture_empty，零误报。"""
        adapter = self._adapter()
        words = [dict(text="在线文档", x=0.2, y=0.3, w=0.2, h=0.03),
                 dict(text="查看文档", x=0.2, y=0.5, w=0.2, h=0.03),
                 dict(text=self.SUMMARY, x=0.1, y=0.35, w=0.6, h=0.03)]
        result, _step = self._run(adapter, words, self.SUMMARY, MagicMock(return_value=""))

        self.assertFalse(result["ok"])
        self.assertEqual(result["code"], "reply_in_card")
        self.assertNotEqual(result["code"], "capture_empty")
        self.assertTrue(result["document_card"]["present"])
        self.assertIn("文档卡片", result["missing"])
        self.assertIn("不是 OCR 问题", result["hint"])
        self.assertIn("不是模型问题", result["hint"])

    def test_plain_answer_is_not_misdetected_as_card(self):
        """③ 普通对话文本 → 不被卡片识别误伤（负例）。"""
        adapter = self._adapter()
        words = [dict(text="这是关于文档写作的普通回答", x=0.1, y=0.2, w=0.6, h=0.03),
                 dict(text=self.COPIED.splitlines()[0], x=0.1, y=0.24, w=0.6, h=0.03)]
        check = DoubaoAdapter._document_card_state(words, self.COPIED)
        self.assertFalse(check["present"])
        self.assertFalse(check["overlay"])

        doc_copy = MagicMock(return_value=self.COPIED)
        adapter_copy = MagicMock(return_value=self.COPIED)
        step = MagicMock()
        evidence = Path(tempfile.mkdtemp(prefix="guga-card-neg-"))
        adapter._capture_words = MagicMock(return_value=(None, words, self.COPIED))
        adapter._scroll_to_bottom = MagicMock(return_value=dict(
            scrolled=True, rounds=2, reason="page_stable", words=words,
            page_text=self.COPIED, marker=False, stable=True))
        adapter._copy_via_document_card = doc_copy
        adapter._copy_via_uia_button = adapter_copy
        adapter._copy_via_answer_button = MagicMock(return_value="")
        adapter._copy_via_more_menu = MagicMock(return_value="")
        adapter._copy_via_select_all = MagicMock(return_value="")
        result = adapter._capture_answer(1, self.PROMPT, evidence, step)

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["copied_from"], "uia_button")
        doc_copy.assert_not_called()          # 普通回答不会走卡片分支


class SendConfirmationTests(unittest.TestCase):
    """20261110z 现场：发送其实成功（气泡已出现），字数因页面滚动 -406 被误判未发送，
    于是补发了第二遍。发送确认改为“用户气泡新增”为主，字数只作说明。
    """

    def test_user_bubble_confirms_even_when_chars_drop(self):
        """① 气泡 2→3、字数 -406 → 确认成功，信号 user_bubble。"""
        ok, signal, detail = DoubaoAdapter._send_confirmation(dict(
            bubble_before=2, bubble_after=3, tail_after=3, composer_before=True,
            still_in_composer=False, button_state="unknown", grew=-406))
        self.assertTrue(ok)
        self.assertEqual(signal, "user_bubble")
        self.assertIn("2→3", detail)

    def test_chars_growth_alone_never_confirms(self):
        """② 没有气泡、输入框仍留原文 → 字数 +80 也不判已发送。"""
        ok, signal, detail = DoubaoAdapter._send_confirmation(dict(
            bubble_before=2, bubble_after=2, tail_after=2, composer_before=True,
            still_in_composer=True, button_state="unknown", grew=80))
        self.assertFalse(ok)
        self.assertEqual(signal, "")
        self.assertIn("仅作辅助", detail)

    def test_input_cleared_is_strong_evidence(self):
        """③ 输入框清空回占位文案 → 确认，信号 input_cleared。"""
        ok, signal, _detail = DoubaoAdapter._send_confirmation(dict(
            bubble_before=0, bubble_after=0, composer_before=True,
            still_in_composer=False, button_state="unknown", grew=-30))
        self.assertTrue(ok)
        self.assertEqual(signal, "input_cleared")

    def test_stop_button_is_strong_evidence(self):
        """④ 发送键变成“停止生成” → 确认，信号 send_button_state。"""
        ok, signal, _detail = DoubaoAdapter._send_confirmation(dict(
            bubble_before=0, bubble_after=0, composer_before=True,
            still_in_composer=True, button_state="stop", grew=0))
        self.assertTrue(ok)
        self.assertEqual(signal, "send_button_state")

    def test_send_result_carries_confirm_signal(self):
        """结果里显式标注用的是哪条信号。"""
        adapter = DoubaoAdapter.__new__(DoubaoAdapter)
        adapter._obs = MagicMock()
        adapter._capture_words = MagicMock(return_value=(None, [], "页面正文"))
        adapter._turn_markers = MagicMock(return_value=2)
        adapter._bubble_hits = MagicMock(side_effect=[(2, 2, None), (3, 3, 0.55)])
        adapter._press_send = MagicMock()
        adapter._composer_has_prompt = MagicMock(return_value=False)
        adapter._generating = MagicMock(return_value=True)
        evidence = Path(tempfile.mkdtemp(prefix="guga-send-"))
        with patch.object(doubao_adapter, "sent_mode_check",
                          return_value={"ok": True}), \
             patch.object(doubao_adapter.time, "sleep", lambda *a, **k: None):
            result = adapter._send_and_confirm(1, "问题", evidence, MagicMock())
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["confirm_signal"], "user_bubble")
        self.assertEqual(result["bubble_before"], 2)
        self.assertEqual(result["bubble_after"], 3)

    def test_send_result_marks_input_cleared_when_no_bubble(self):
        adapter = DoubaoAdapter.__new__(DoubaoAdapter)
        adapter._obs = MagicMock()
        adapter._capture_words = MagicMock(side_effect=[
            (None, [], "短页面"), (None, [], "页面正文字数足够多" * 8)])
        adapter._turn_markers = MagicMock(return_value=None)
        adapter._bubble_hits = MagicMock(return_value=(0, 0, None))
        adapter._press_send = MagicMock()
        adapter._composer_has_prompt = MagicMock(side_effect=[True, False])
        adapter._generating = MagicMock(return_value=False)
        adapter._send_button_state = MagicMock(return_value="unknown")
        evidence = Path(tempfile.mkdtemp(prefix="guga-send-"))
        with patch.object(doubao_adapter, "sent_mode_check",
                          return_value={"ok": True}), \
             patch.object(doubao_adapter.time, "sleep", lambda *a, **k: None):
            result = adapter._send_and_confirm(1, "问题", evidence, MagicMock())
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["confirm_signal"], "input_cleared")


class ViewportTests(unittest.TestCase):
    """20261110x 根因：咕嘎没有“窗口视口大小”概念，小窗口里长回答只显示开头。"""

    BEFORE = [100, 80, 900, 680]
    WORK = (1920, 1080)

    def _adapter(self):
        adapter = DoubaoAdapter.__new__(DoubaoAdapter)
        adapter._work_area = staticmethod(lambda: self.WORK)
        adapter._window_state = staticmethod(lambda hwnd: "normal")
        return adapter

    def test_small_window_enlarged_then_restored(self):
        """① 小窗口 → 放大 → 操作后恢复原 rect（restore 参数等于 before_rect）。"""
        adapter = self._adapter()
        state = {"rect": list(self.BEFORE)}
        clients = [(600, 420), (1830, 1000), (1830, 1000)]

        def get_rect(_hwnd):
            return tuple(state["rect"])

        def apply_rect(_hwnd, rect):
            state["rect"] = list(rect)

        adapter._client_size = staticmethod(lambda hwnd: clients.pop(0))
        adapter._apply_window_rect = MagicMock(side_effect=apply_rect)
        with patch("core.adapters.doubao_adapter.win32gui.GetWindowRect",
                   side_effect=get_rect), \
             patch("core.adapters.doubao_adapter.win32gui.ShowWindow"), \
             patch("core.adapters.doubao_adapter.win32gui.IsIconic",
                   return_value=False), \
             patch.object(DoubaoAdapter, "_is_maximized", return_value=False), \
             patch.object(doubao_adapter.time, "sleep", lambda *a, **k: None):
            info = adapter._adapt_viewport(1)
            restore = adapter._restore_viewport(1, info)
        self.assertTrue(info["adjusted"], info)
        self.assertEqual(info["reason"], "maximize")
        self.assertEqual(info["before_rect"], self.BEFORE)
        self.assertEqual(info["ratio"], {"w": 0.312, "h": 0.389})
        self.assertGreater(info["after_ratio"]["w"], 0.6)
        self.assertTrue(restore["restored"])
        self.assertTrue(restore["restore_ok"], restore)
        adapter._apply_window_rect.assert_called_once_with(1, self.BEFORE)
        self.assertFalse(adapter._small_viewport)

    def test_enlarge_rejected_uses_small_viewport_mode(self):
        """② 放大被拒 → viewport_adjusted=false 且走小视口模式，不整体失败。"""
        adapter = self._adapter()
        adapter._client_size = staticmethod(lambda hwnd: (600, 420))
        with patch("core.adapters.doubao_adapter.win32gui.GetWindowRect",
                   return_value=tuple(self.BEFORE)), \
             patch("core.adapters.doubao_adapter.win32gui.ShowWindow",
                   side_effect=OSError("系统不允许改尺寸")), \
             patch.object(DoubaoAdapter, "_apply_window_rect",
                          side_effect=OSError("系统不允许改尺寸")), \
             patch.object(doubao_adapter.time, "sleep", lambda *a, **k: None):
            info = adapter._adapt_viewport(1)
        self.assertFalse(info["adjusted"], info)
        self.assertTrue(info["small_viewport"], info)
        self.assertIn("enlarge_failed", info["reason"])
        self.assertTrue(adapter._small_viewport)


class ScrollStateCodeTests(unittest.TestCase):
    """滚动三态各自成码：已到底 / 仍在滚动 / 滚不动但未到底，不混成 capture_empty。"""

    PROMPT = "写一段"
    PAGE = "正文"

    def _call(self, state):
        adapter = DoubaoAdapter.__new__(DoubaoAdapter)
        adapter._ocr_unavailable = False
        adapter.evidence_root = Path(tempfile.mkdtemp(prefix="guga-cap-"))
        for name in ("_copy_via_uia_button", "_copy_via_answer_button",
                     "_copy_via_more_menu", "_copy_via_select_all"):
            setattr(adapter, name, MagicMock(return_value=""))
        with patch.object(DoubaoAdapter, "_capture_words",
                          return_value=(None, [], self.PAGE)), \
             patch.object(DoubaoAdapter, "_scroll_to_bottom",
                          return_value={"scrolled": True, "rounds": 8,
                                        "reason": "stable_but_uia_not_bottom",
                                        "state": state, "words": [],
                                        "page_text": self.PAGE, "marker": False,
                                        "stable": True}):
            return adapter._capture_answer(1, self.PROMPT,
                                           Path(tempfile.mkdtemp(prefix="guga-ev-")),
                                           MagicMock())

    def test_stuck_not_bottom_gets_own_code(self):
        result = self._call(doubao_adapter.SCROLL_STUCK)
        self.assertFalse(result["ok"])
        self.assertEqual(result["code"], "scroll_stuck")
        self.assertIn("滚不动但未到底", result["missing"])

    def test_still_scrolling_gets_own_code(self):
        result = self._call(doubao_adapter.SCROLL_STILL_MOVING)
        self.assertFalse(result["ok"])
        self.assertEqual(result["code"], "scroll_incomplete")
        self.assertIn("仍在滚动", result["missing"])


class SmallViewportAcceptTests(unittest.TestCase):
    """视口只显示开头、但复制到完整正文 → 接受，不判空。"""

    PROMPT = "用豆包生成PPT提示词"
    PAGE = "开头两三行"
    FULL = "# 产品发布会\n" + "\n".join(
        "1. 第%d页要点：市场与用户增长策略，含竞品对照与关键指标拆解" % i
        for i in range(1, 9))

    def test_beginning_only_viewport_with_full_copy_is_accepted(self):
        adapter = DoubaoAdapter.__new__(DoubaoAdapter)
        adapter._ocr_unavailable = False
        adapter._small_viewport = True
        adapter.evidence_root = Path(tempfile.mkdtemp(prefix="guga-cap-"))
        adapter._copy_via_uia_button = MagicMock(return_value=self.FULL)
        adapter._copy_via_answer_button = MagicMock(return_value="")
        adapter._copy_via_more_menu = MagicMock(return_value="")
        adapter._copy_via_select_all = MagicMock(return_value="")
        with patch.object(DoubaoAdapter, "_capture_words",
                          return_value=(None, [], self.PAGE)), \
             patch.object(DoubaoAdapter, "_scroll_to_bottom",
                          return_value={"scrolled": True, "rounds": 8,
                                        "reason": "stable_but_uia_not_bottom",
                                        "state": doubao_adapter.SCROLL_STUCK,
                                        "words": [], "page_text": self.PAGE,
                                        "marker": False, "stable": True}), \
             patch.object(DoubaoAdapter, "_degrade_reason", return_value=""):
            result = adapter._capture_answer(1, self.PROMPT,
                                             Path(tempfile.mkdtemp(prefix="guga-ev-")),
                                             MagicMock())
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["copied_from"], "uia_button")
        self.assertTrue(result["copy_checks"][0]["visible_in_page"])
        self.assertIn("小视口/滚动受限放行",
                      result["copy_checks"][0]["degrade_reason"])


class SubmitGuardTests(unittest.TestCase):
    """硬规则：发送确认一旦成立，同一句话绝不允许再注入/回车。"""

    PROMPT = "问题"

    @staticmethod
    def _adapter():
        adapter = DoubaoAdapter.__new__(DoubaoAdapter)
        adapter._submit_state = ""
        adapter._ocr_unavailable = False
        adapter.evidence_root = Path(tempfile.mkdtemp(prefix="guga-send-"))
        return adapter

    def _ev(self):
        return Path(tempfile.mkdtemp(prefix="guga-send-ev-"))

    def test_confirmed_then_three_read_failures_never_resends(self):
        """① 发送确认成功后读取失败 3 次 → 写/回车调用次数仍为 1。"""
        adapter = self._adapter()
        adapter._obs = MagicMock()
        adapter._capture_words = MagicMock(return_value=(None, [], "页面正文"))
        adapter._turn_markers = MagicMock(return_value=2)
        adapter._bubble_hits = MagicMock(side_effect=[(1, 1, None), (2, 2, 0.55)])
        press = MagicMock()
        adapter._press_send = press
        adapter._composer_has_prompt = MagicMock(return_value=False)
        adapter._generating = MagicMock(return_value=False)
        adapter._inject = MagicMock()
        with patch.object(doubao_adapter, "sent_mode_check",
                          return_value={"ok": True}), \
             patch.object(doubao_adapter.time, "sleep", lambda *a, **k: None):
            first = adapter._send_and_confirm(1, self.PROMPT, self._ev(), MagicMock())
        self.assertTrue(first["ok"], first)
        self.assertEqual(press.call_count, 1)
        self.assertEqual(adapter._submit_state, "sent_confirmed")

        adapter._find_window = MagicMock(return_value={"hwnd": 1})
        adapter._restore_window = MagicMock()
        adapter._raise_window = MagicMock()
        adapter._adapt_viewport = MagicMock(return_value={"adjusted": False})
        adapter._restore_viewport = MagicMock()
        adapter._ocr_state = MagicMock(return_value={})
        adapter._capture_words = MagicMock(return_value=(None, [], "页面正文"))
        adapter._is_blank = MagicMock(return_value=False)
        adapter._dismiss_modal = MagicMock(return_value=False)
        adapter._wait_done = MagicMock(return_value={"ok": True})
        adapter._capture_answer = MagicMock(
            return_value={"ok": False, "code": "capture_empty", "hint": "没抓到"})
        with patch.object(doubao_adapter, "_dpi_aware", contextlib.nullcontext), \
             patch("core.adapters.doubao_adapter.win32gui.GetForegroundWindow",
                   return_value=1), \
             patch.object(doubao_adapter.time, "sleep", lambda *a, **k: None):
            for _ in range(3):
                out = adapter._ui_capture_retry(self.PROMPT, self._ev(), 30)
                self.assertFalse(out["ok"])
        self.assertEqual(press.call_count, 1)
        adapter._inject.assert_not_called()

    def test_unconfirmed_allows_single_resend_and_logs_reason(self):
        """② 无新气泡且输入框仍留原文 → 允许补发一次，且记录原因。"""
        adapter = self._adapter()
        adapter._obs = MagicMock()
        adapter._capture_words = MagicMock(return_value=(None, [], "页面正文"))
        adapter._turn_markers = MagicMock(return_value=2)
        adapter._bubble_hits = MagicMock(return_value=(0, 0, None))
        press = MagicMock()
        adapter._press_send = press
        adapter._composer_has_prompt = MagicMock(return_value=True)
        adapter._generating = MagicMock(return_value=False)
        adapter._send_button_state = MagicMock(return_value="unknown")
        adapter._click = MagicMock()
        step = MagicMock()
        with patch.object(doubao_adapter, "sent_mode_check",
                          return_value={"ok": True}), \
             patch.object(doubao_adapter.time, "sleep", lambda *a, **k: None):
            result = adapter._send_and_confirm(1, self.PROMPT, self._ev(), step)
        self.assertFalse(result["ok"])
        self.assertEqual(press.call_count, 2)      # 首发 1 次 + 唯一一次补发
        adapter._click.assert_not_called()
        reasons = [call.kwargs.get("reason") for call in step.call_args_list
                   if call.args and call.args[0] == "resend"]
        self.assertEqual(reasons, ["no_bubble_composer_keeps_text"])

    def test_resend_needs_composer_keeps_text(self):
        """③ 气泡没新增但输入框已空 → 不许补发（只允许继续读）。"""
        adapter = self._adapter()
        adapter._obs = MagicMock()
        adapter._capture_words = MagicMock(return_value=(None, [], "页面正文"))
        adapter._turn_markers = MagicMock(return_value=2)
        adapter._bubble_hits = MagicMock(return_value=(0, 0, None))
        press = MagicMock()
        adapter._press_send = press
        # 发送前也没有回读到原文 → 不能凭“输入框空”判已发，也不能补发。
        adapter._composer_has_prompt = MagicMock(return_value=False)
        adapter._generating = MagicMock(return_value=False)
        adapter._send_button_state = MagicMock(return_value="unknown")
        adapter._click = MagicMock()
        with patch.object(doubao_adapter, "sent_mode_check",
                          return_value={"ok": True}), \
             patch.object(doubao_adapter.time, "sleep", lambda *a, **k: None):
            result = adapter._send_and_confirm(1, self.PROMPT, self._ev(), MagicMock())
        self.assertFalse(result["ok"])
        self.assertEqual(press.call_count, 1)
        adapter._click.assert_not_called()

    def test_sent_confirmed_rejects_any_resend_entry(self):
        """④ submit_state=sent_confirmed 时任何重发入口直接拒绝并记日志。"""
        adapter = self._adapter()
        adapter._submit_state = "sent_confirmed"
        press = MagicMock()
        adapter._press_send = press
        step = MagicMock()
        result = adapter._send_and_confirm(1, self.PROMPT, self._ev(), step)
        self.assertTrue(result["ok"])
        self.assertTrue(result["reused"])
        press.assert_not_called()
        self.assertIn("resend_rejected",
                      [call.args[0] for call in step.call_args_list])


class InjectFocusTests(unittest.TestCase):
    """注入层：焦点确认 + 同源回读 + 错位检测（20261110y 真机 48 字误判残留）。

    现场：豆包输入框截图是空的，回读却 3 次都是 48 字——恰好等于用户原句
    “用豆包生成PPT提示词…work Buddy生成PPT”去掉空格的长度，说明键鼠落到了
    咕嘎自己的输入条，旧 read() 用 Ctrl+A/Ctrl+C 读到的是“当前焦点窗口”的文本。
    """

    PROMPT = "第 1 步：先给 12 页 PPT 提示词，包含主题、每页标题与要点，全部用纯文本。"
    GUGA_TEXT = "用豆包生成PPT提示词，PPT主题由你来定，再把生成的PPT提示词给workBuddy生成PPT"

    def _adapter(self, foreground):
        adapter = DoubaoAdapter.__new__(DoubaoAdapter)
        adapter._decl = MagicMock(return_value=2)          # focus_attempts
        adapter._send = MagicMock()
        adapter._click = MagicMock(return_value=(0, 0))
        user = MagicMock()
        user.GetForegroundWindow.return_value = foreground
        return adapter, user

    @staticmethod
    def _step(steps):
        return lambda tag, **kw: steps.append(dict(event=tag, **kw))

    def test_not_foreground_means_target_not_focused_and_zero_writes(self):
        """① 目标窗口不在前台 → target_not_focused，且一个键/一次点击都不发。"""
        adapter, user = self._adapter(foreground=999)
        steps = []
        with patch.object(ctypes.windll, "user32", user), \
             patch.object(doubao_adapter, "ensure_plain_mode", return_value={"ok": True}), \
             patch.object(doubao_adapter, "_ensure_foreground", lambda *a, **k: None), \
             patch.object(doubao_adapter, "_read_clipboard", return_value=""), \
             patch("core.uia_service.shared_service") as shared:
            result = adapter._inject(1, {"x": 0.5, "y": 0.9}, self.PROMPT, None, self._step(steps))
        self.assertEqual(result["code"], "target_not_focused")
        self.assertEqual(adapter._send.call_count, 0)
        self.assertEqual(adapter._click.call_count, 0)
        self.assertEqual(shared.return_value.act.call_count, 0)
        self.assertTrue([row for row in steps if row["event"] == "inject_focus"])

    def test_read_not_same_element_is_composer_not_found(self):
        """② 回读控件不是写入控件（同一 element 取不到）→ composer_not_found，不拿别处文本通过。"""
        adapter, user = self._adapter(foreground=1)
        steps = []
        service = MagicMock()
        # z 起 service 有显式 composer：这里让它失败，退回 page_input 的唯一输入框。
        service.composer.side_effect = RuntimeError("没有找到可编辑的富文本输入框")
        service.page_input.return_value = {"element": {"ref": "A", "runtime_id": [42],
                                                       "name": "发消息", "id": "composer"}}

        def act(_hwnd, operation, **kw):
            if operation == "focus":
                return {"verified": True, "control": {"ref": "A"}}
            raise RuntimeError("控件不支持该UIA操作")     # set_value 不可用
        service.act.side_effect = act
        # 同一个 element 的 TextPattern/ValuePattern 都取不到（控件已失效）
        service.text_of.side_effect = RuntimeError("UIA引用已过期或失效")
        service.value.side_effect = RuntimeError("UIA引用已过期或失效")
        with patch.object(ctypes.windll, "user32", user), \
             patch.object(doubao_adapter, "ensure_plain_mode", return_value={"ok": True}), \
             patch("core.paste_verify.ensure_plain_mode", return_value={"ok": True,
                                                                       "mode": "plain",
                                                                       "missing": ""}), \
             patch.object(doubao_adapter, "_read_clipboard", return_value="前台窗口的别的文本"), \
             patch("core.uia_service.shared_service", return_value=service):
            result = adapter._inject(1, {"x": 0.5, "y": 0.9}, self.PROMPT, None, self._step(steps))
        self.assertEqual(result["code"], "composer_not_found")
        self.assertFalse(result["ok"])
        service.text_of.assert_called()
        self.assertNotIn("前台窗口的别的文本", str(result))

    def test_readback_equals_guga_composer_is_written_elsewhere(self):
        """③ 回读恰好等于咕嘎自己输入条内容 → input_written_elsewhere，不判通过。"""
        adapter, user = self._adapter(foreground=1)
        steps = []
        service = MagicMock()
        service.composer.side_effect = RuntimeError("没有找到可编辑的富文本输入框")
        service.page_input.return_value = {
            "element": {"ref": "A", "runtime_id": [42], "name": "发消息",
                        "id": "composer", "patterns": ["ValuePattern"]}}
        service.act.return_value = {"verified": True, "control": {"ref": "A"}}
        service.value.return_value = self.GUGA_TEXT
        with patch.object(ctypes.windll, "user32", user), \
             patch.object(doubao_adapter, "ensure_plain_mode", return_value={"ok": True}), \
             patch.object(doubao_adapter, "_read_clipboard", return_value=self.GUGA_TEXT), \
             patch("core.uia_service.shared_service", return_value=service):
            result = adapter._inject(1, {"x": 0.5, "y": 0.9}, self.PROMPT, None, self._step(steps))
        self.assertEqual(result["code"], "input_written_elsewhere")
        self.assertIn("别的窗口或控件", result["missing"])

    def test_same_element_write_read_verified(self):
        """④ 正常同源写入回读一致 → 通过，mode=uia_value，ref 与注入控件一致。"""
        adapter, user = self._adapter(foreground=1)
        steps = []
        service = MagicMock()
        service.composer.side_effect = RuntimeError("没有找到可编辑的富文本输入框")
        service.page_input.return_value = {
            "element": {"ref": "A", "runtime_id": [42], "name": "发消息",
                        "id": "composer", "patterns": ["ValuePattern"]}}
        service.act.return_value = {"verified": True, "control": {"ref": "A"}}
        service.value.return_value = self.PROMPT
        with patch.object(ctypes.windll, "user32", user), \
             patch.object(doubao_adapter, "ensure_plain_mode", return_value={"ok": True}), \
             patch.object(doubao_adapter, "_read_clipboard", return_value=""), \
             patch("core.uia_service.shared_service", return_value=service):
            result = adapter._inject(1, {"x": 0.5, "y": 0.9}, self.PROMPT, None, self._step(steps))
        self.assertTrue(result["ok"])
        self.assertEqual(result["mode"], "uia_value")
        self.assertEqual(result["ref"], "A")
        self.assertEqual(adapter._send.call_count, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)

