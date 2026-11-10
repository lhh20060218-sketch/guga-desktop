# -*- coding: utf-8 -*-
"""回归：UIA 元素 rect 是字典形态时，豆包输入框定位不得抛 KeyError。

现场（20261110r，第 1/2 步豆包约 2.8 秒失败）：
    core/adapters/doubao_adapter.py line 1031, in _uia_input_anchor
        if len(rect) != 4 or rect[2] <= 0 or rect[3] <= 0:
    KeyError: 2
根因：uia_service.snapshot() 的元素 rect 是
    {"left":131.0,"top":0.0,"right":1337.0,"bottom":720.0}
len(dict) == 4 让长度检查失效，随后 rect[2] 抛 KeyError。

单独执行：python tools/test_doubao_rect.py
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core import ocr_engine  # noqa: E402
from core.adapters.doubao_adapter import (  # noqa: E402
    OCR_DEPENDENT_CODES, RETRYABLE, TARGET_WINDOW_CODE, DoubaoAdapter, _rect_box)


class RectBoxTests(unittest.TestCase):
    def test_dict_rect(self):
        self.assertEqual(
            _rect_box({"left": 131.0, "top": 0.0, "right": 1337.0, "bottom": 720.0}),
            (131.0, 0.0, 1337.0, 720.0))

    def test_list_rect(self):
        self.assertEqual(_rect_box([10, 20, 110, 220]), (10.0, 20.0, 110.0, 220.0))
        self.assertEqual(_rect_box((10, 20, 110, 220)), (10.0, 20.0, 110.0, 220.0))

    def test_empty_or_none(self):
        for value in (None, {}, [], (), [1, 2], {"left": 1, "top": 2}):
            self.assertIsNone(_rect_box(value), value)

    def test_zero_size(self):
        self.assertIsNone(_rect_box({"left": 50, "top": 50, "right": 50, "bottom": 90}))
        self.assertIsNone(_rect_box({"left": 50, "top": 50, "right": 90, "bottom": 50}))
        self.assertIsNone(_rect_box([50, 50, 50, 90]))
        self.assertIsNone(_rect_box([0, 0, 0, 0]))


class UiaInputAnchorTests(unittest.TestCase):
    @staticmethod
    def _adapter():
        # 只测定位函数，不走 __init__（避免创建 ComputerControl / 读配置）
        return DoubaoAdapter.__new__(DoubaoAdapter)

    def test_dict_rect_anchor_does_not_raise(self):
        snapshot = {"elements": [
            {"type": "Document", "rect": {"left": 0, "top": 0, "right": 900, "bottom": 780}},
            {"type": "Edit", "ref": "r1", "value": "hi",
             "rect": {"left": 100.0, "top": 500.0, "right": 900.0, "bottom": 540.0}},
        ]}
        service = type("S", (), {"snapshot": lambda self, hwnd, **kw: snapshot})()
        with patch("core.uia_service.shared_service", return_value=service), \
             patch("core.adapters.doubao_adapter.win32gui.GetWindowRect",
                   return_value=(0, 0, 1000, 800)):
            anchor = self._adapter()._uia_input_anchor(123)
        self.assertIsNotNone(anchor)
        self.assertEqual(anchor.get("ref"), "r1")
        self.assertAlmostEqual(anchor["x"], 0.5)
        self.assertAlmostEqual(anchor["y"], 0.65)

    def test_invalid_rect_is_skipped_not_raised(self):
        snapshot = {"elements": [
            {"type": "Edit", "ref": "bad", "rect": {"left": 10, "top": 10, "right": 10, "bottom": 10}},
            {"type": "Edit", "ref": "good",
             "rect": {"left": 100.0, "top": 500.0, "right": 900.0, "bottom": 540.0}},
        ]}
        service = type("S", (), {"snapshot": lambda self, hwnd, **kw: snapshot})()
        with patch("core.uia_service.shared_service", return_value=service), \
             patch("core.adapters.doubao_adapter.win32gui.GetWindowRect",
                   return_value=(0, 0, 1000, 800)):
            anchor = self._adapter()._uia_input_anchor(123)
        self.assertEqual(anchor.get("ref"), "good")


class FailureCodeTests(unittest.TestCase):
    """s2：失败码分层——真实停因不被 OCR 文案顶掉，空文本有独立码。"""

    def test_send_not_confirmed_not_ocr_dependent(self):
        self.assertNotIn("send_not_confirmed", OCR_DEPENDENT_CODES)
        self.assertNotIn(TARGET_WINDOW_CODE, OCR_DEPENDENT_CODES)
        self.assertIn("ocr_empty", RETRYABLE)

    @staticmethod
    def _adapter():
        adapter = DoubaoAdapter.__new__(DoubaoAdapter)
        adapter.tool = "doubao"
        adapter.name = "豆包"
        adapter.evidence_root = Path(tempfile.mkdtemp(prefix="guga-ut-"))
        adapter._ocr_unavailable = True
        adapter._ocr_error = {"kind": "no_language", "missing": "中文 OCR 语言包",
                              "where": "设置 → 可选功能", "next_action": "装完重启咕嘎"}
        adapter._last_ocr_empty = False
        adapter._release_topmost = lambda: None
        adapter._dump_log = lambda *a, **k: None
        return adapter

    def test_real_stop_reason_survives_ocr_unavailable(self):
        adapter = self._adapter()
        record = {"ok": False, "code": "send_not_confirmed",
                  "hint": "文字已经打进去，但没有出现新回合；先重启豆包再派单。",
                  "evidence": {"send": {"ok": True}}}
        with patch.object(DoubaoAdapter, "_ui_attempt", return_value=record):
            result = adapter.ask("写一句话", retry=0, prefer_mcp=False)
        self.assertEqual(result["code"], "send_not_confirmed")
        self.assertEqual(result["hint"], record["hint"])
        self.assertNotIn("OCR 不可用", result["hint"])
        self.assertNotIn("missing", result)  # 不再挂 OCR 的“缺语言包”

    def test_target_window_code_and_evidence_reach_result(self):
        adapter = self._adapter()
        abnormal = {"detail": "页面停在 chrome://doubao-chat/chat/skills，不是对话页",
                    "url": "chrome://doubao-chat/chat/skills",
                    "rect": (1398, 227, 2604, 695),
                    "screen": (0, 0, 1920, 1080), "blank": True, "onscreen_ratio": 0.43}
        record = {"ok": False, "code": TARGET_WINDOW_CODE,
                  "hint": "豆包窗口当前不可用：%s。下一步：重启豆包后重新派单。"
                          % abnormal["detail"],
                  "missing": "正常渲染的豆包对话窗口",
                  "where": "重启豆包", "next_action": "重启豆包后重新派单",
                  "restart_required": True,
                  "evidence": {"target_window": abnormal}}
        with patch.object(DoubaoAdapter, "_ui_attempt", return_value=record):
            result = adapter.ask("写一句话", retry=0, prefer_mcp=False)
        self.assertEqual(result["code"], TARGET_WINDOW_CODE)
        self.assertIn("chrome://doubao-chat/chat/skills", result["hint"])
        self.assertIn("重启豆包", result["hint"])
        self.assertEqual(result["evidence"]["target_window"]["url"], abnormal["url"])
        self.assertTrue(result["restart_required"])

    def test_empty_ocr_text_has_own_kind(self):
        with tempfile.NamedTemporaryFile(suffix=".ps1", delete=False) as handle:
            handle.write(b"# fake")
            script = handle.name
        fake = type("R", (), {"returncode": 0, "stdout": b'{"text": ""}', "stderr": b""})()
        with patch.object(ocr_engine, "script_path", return_value=Path(script)), \
             patch.object(ocr_engine.subprocess, "run", return_value=fake):
            result = ocr_engine.run_on_image("dummy.png")
        try:
            os.unlink(script)
        except OSError:
            pass
        self.assertFalse(result["ok"])
        self.assertEqual(result["kind"], "empty_text")
        self.assertIn("0 行", result["missing"])

    def test_target_window_abnormal_detects_non_chat_page(self):
        adapter = self._adapter()
        frame = object()
        with patch.object(DoubaoAdapter, "_frame_blank", return_value=True), \
             patch.object(DoubaoAdapter, "_uia_page_url",
                          return_value="chrome://doubao-chat/chat/skills"), \
             patch("core.adapters.doubao_adapter.win32gui.GetWindowRect",
                   return_value=(1398, 227, 2604, 695)), \
             patch("win32api.GetSystemMetrics", side_effect=[0, 0, 1920, 1080]):
            abnormal = adapter._target_window_abnormal(123, frame)
        self.assertIsNotNone(abnormal)
        self.assertIn("不是对话页", abnormal["detail"])
        self.assertIn("chrome://doubao-chat/chat/skills", abnormal["detail"])
        self.assertIn("在屏幕外", abnormal["detail"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
