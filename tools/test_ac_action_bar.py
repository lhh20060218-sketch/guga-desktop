# -*- coding: utf-8 -*-
"""20261110ac：复制读取 / 操作栏判完成 / 滚轮方向 / 建议追问条剔除。"""
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import computer_control  # noqa: E402
from core.adapters import doubao_adapter as da  # noqa: E402


def _el(ref, kind, rect, name="", cls="", **extra):
    left, top, right, bottom = rect
    item = dict(ref=ref, type=kind, name=name, class_name=cls,
                rect=dict(left=left, top=top, right=right, bottom=bottom),
                text_pattern=False, enabled=True, keyboard_focusable=True,
                patterns=[])
    item.update(extra)
    return item


def _bar_elements(button_count=4):
    elements = [
        _el("composer", "Group", (300, 861, 900, 940), cls="tiptap ProseMirror"),
        _el("answer", "Text", (341, 540, 1100, 600), text_pattern=True,
            patterns=["TextPattern"]),
    ]
    lefts = [325, 359, 395, 429, 463, 497, 563, 597][:button_count]
    for index, left in enumerate(lefts):
        elements.append(_el("btn%d" % index, "Button",
                            (left, 613, left + (56 if index == 5 else 24), 637)))
    for index, top in enumerate((683, 729, 775)):
        elements.append(_el("chip%d" % index, "Text", (341, top, 729, top + 18),
                            text_pattern=True, patterns=["TextPattern"]))
    return elements


class FakeService:
    def __init__(self, elements, texts=None):
        self.elements = elements
        self.texts = texts or {}
        self.acted = []

    def snapshot(self, hwnd, limit=0, time_budget=0):
        return {"elements": self.elements}

    def text_of(self, hwnd, ref, limit=0):
        return {"text": self.texts.get(ref, "")}

    def act(self, hwnd, action, **kwargs):
        self.acted.append((action, kwargs))
        return {"ok": True}


class WheelDirectionTests(unittest.TestCase):
    def test_intent_to_delta_is_single_source(self):
        # 20261110ac 实测：往下翻（看更后）必须是负值。
        self.assertEqual(computer_control.wheel_delta("later"), -120)
        self.assertEqual(computer_control.wheel_delta("down"), -120)
        self.assertEqual(computer_control.wheel_delta("earlier"), 120)
        self.assertEqual(computer_control.wheel_delta("up"), 120)
        self.assertEqual(computer_control.wheel_notches("later", 3), [-120, -120, -120])
        with self.assertRaises(ValueError):
            computer_control.wheel_delta("sideways")


class ActionBarDetectTests(unittest.TestCase):
    def setUp(self):
        self.adapter = da.DoubaoAdapter()
        self.service = FakeService(_bar_elements(4), {
            "chip0": "推荐一些网络安全新手SRC挖洞入门与合规实践指南的PPT模板",
            "chip1": "如何快速学习PPT制作？",
            "chip2": "如何快速上手补天平台？"})

    def test_finds_leftmost_button_and_chips(self):
        with mock.patch.object(da, "win32gui") as fake_gui, \
                mock.patch("core.uia_service.shared_service", return_value=self.service):
            fake_gui.GetWindowRect.return_value = (0, 0, 1206, 881)
            bar = self.adapter._find_action_bar(1206, with_chips=True)
        self.assertTrue(bar["present"])
        self.assertEqual(bar["ref"], "btn0")
        self.assertEqual(len(bar["buttons"]), 4)
        self.assertEqual(bar["candidates"], 1)
        self.assertEqual(bar["chips"], [
            "推荐一些网络安全新手SRC挖洞入门与合规实践指南的PPT模板",
            "如何快速学习PPT制作？",
            "如何快速上手补天平台？"])

    def test_needs_three_buttons_in_one_row(self):
        service = FakeService(_bar_elements(2))
        with mock.patch.object(da, "win32gui") as fake_gui, \
                mock.patch("core.uia_service.shared_service", return_value=service):
            fake_gui.GetWindowRect.return_value = (0, 0, 1206, 881)
            bar = self.adapter._find_action_bar(1206)
        self.assertFalse(bar["present"])
        self.assertEqual(bar["candidates"], 0)


class CopyReadTests(unittest.TestCase):
    def test_invoke_copy_returns_text_and_restores_clipboard(self):
        adapter = da.DoubaoAdapter()
        service = FakeService(_bar_elements(4), {
            "chip0": "", "chip1": "", "chip2": ""})
        written, reads = [], ["__GUGA_COPY_SENTINEL__", "PPT提示词\n第 1 页 封面"]

        def fake_read():
            return reads.pop(0) if reads else "PPT提示词\n第 1 页 封面"

        restore_calls = []

        def fake_restore(box, attempts=4, only_owner=True):
            restore_calls.append(box)
            return {"restore_ok": True, "attempts": 1, "leftover_formats": [],
                    "missing_formats": [], "skipped": False, "restored_in": "test"}

        def fake_locked(hwnd, prompt, evidence_dir, step):
            da._write_clipboard("PPT提示词\n第 1 页 封面")
            return {"ok": True, "answer": "PPT提示词"}

        with mock.patch.object(da, "win32gui") as fake_gui, \
                mock.patch("core.uia_service.shared_service", return_value=service), \
                mock.patch.object(da, "_write_clipboard", side_effect=written.append), \
                mock.patch.object(da, "_read_clipboard", side_effect=fake_read), \
                mock.patch.object(da, "_clip_session_begin", return_value={"formats": []}), \
                mock.patch.object(da, "_restore_session_clipboard", side_effect=fake_restore), \
                mock.patch.object(da, "_clip_session_end"), \
                mock.patch.object(adapter, "_capture_answer_locked", side_effect=fake_locked):
            fake_gui.GetWindowRect.return_value = (0, 0, 1206, 881)
            result = adapter._capture_answer(1206, "用豆包生成PPT提示词", Path("."),
                                             lambda *a, **k: None)
        self.assertTrue(result["clipboard_restore"]["restore_ok"])
        self.assertEqual(restore_calls, [{"formats": []}])

    def test_copy_via_action_bar_records_chars_and_elapsed(self):
        adapter = da.DoubaoAdapter()
        service = FakeService(_bar_elements(4))
        copied = "PPT提示词\n第 1 页 封面：标题"
        reads = [da.COPY_SENTINEL, copied]
        steps = []
        with mock.patch.object(da, "win32gui") as fake_gui, \
                mock.patch("core.uia_service.shared_service", return_value=service), \
                mock.patch.object(da, "_write_clipboard"), \
                mock.patch.object(da, "_read_clipboard",
                                  side_effect=lambda: reads.pop(0) if reads else copied):
            fake_gui.GetWindowRect.return_value = (0, 0, 1206, 881)
            text = adapter._copy_via_action_bar(1206, Path("."),
                                                lambda tag, **kw: steps.append((tag, kw)))
        self.assertEqual(text, copied)
        self.assertEqual(adapter._last_action_bar["copy"]["chars"], len(copied))
        self.assertIn("action_bar_copy", [tag for tag, _ in steps])


class DoneActionBarTests(unittest.TestCase):
    def test_action_bar_is_done_signal_and_absent_while_generating(self):
        adapter = da.DoubaoAdapter()
        adapter._obs = mock.MagicMock()
        bars = [{"present": False, "candidates": 0},
                {"present": True, "candidates": 1, "rect": {"top": 613}}]
        generating = [True, False]
        frames = []

        def fake_capture(hwnd, path=None):
            frames.append(1)
            return (object(), [{"text": "PPT", "x": 0.3, "y": 0.5}],
                    "PPT 提示词 第 1 页 封面")

        with mock.patch.object(adapter, "_capture_words_timed", side_effect=fake_capture), \
                mock.patch.object(adapter, "_generating",
                                  side_effect=lambda words, text: generating.pop(0)), \
                mock.patch.object(adapter, "_find_action_bar", side_effect=lambda *a, **k: bars.pop(0)), \
                mock.patch.object(adapter, "_is_blank", return_value=False), \
                mock.patch.object(da, "sent_mode_check",
                                  return_value={"ok": True}), \
                mock.patch.object(da.time, "sleep", return_value=None):
            result = adapter._wait_done(1206, "用豆包生成PPT提示词", 30, Path("."),
                                        lambda *a, **k: None)
        self.assertTrue(result["ok"])
        self.assertEqual(result["done_signal"], "action_bar")
        self.assertEqual(result["bar_during_generate"]["present"], False)


class ChipFilterTests(unittest.TestCase):
    def test_suggestion_lines_are_dropped(self):
        adapter = da.DoubaoAdapter()
        text = ("PPT 提示词\n第 1 页 封面：标题与副标题\n"
                "如何快速学习PPT制作？\n如何快速上手补天平台？\n")
        answer = adapter._extract_answer(
            text, "用豆包生成PPT提示词",
            chips=["如何快速学习PPT制作？", "如何快速上手补天平台？"])
        self.assertIn("第 1 页 封面", answer)
        self.assertNotIn("如何快速学习", answer)
        self.assertNotIn("如何快速上手", answer)


if __name__ == "__main__":
    unittest.main(verbosity=2)
