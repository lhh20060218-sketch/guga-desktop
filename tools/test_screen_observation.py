"""Offline checks for the structured screen observation bus (task handoff)."""
import os
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from launcher import _prepare_qt
_prepare_qt()
from PyQt5.QtWidgets import QApplication
from core.screen_share import ScreenShareController
from core.self_agent import screen_observation_instructions

APP = QApplication.instance() or QApplication([])


def make_controller():
    controller = ScreenShareController(None)
    now = time.monotonic()
    controller._active = True
    controller._seq = 5
    controller._last_at = now - 1
    controller._last_change = 0.0
    controller._context = '页面 A：有登录按钮和搜索框'
    controller._context_at = now - 1
    controller._context_frame_at = 0.0
    controller._foreground = dict(hwnd=11, process='chrome.exe', title='页面 A')
    controller._context_foreground = dict(hwnd=11, process='chrome.exe', title='页面 A')
    controller._frame_size = dict(width=1280, height=800, original_width=2560, original_height=1600)
    return controller


class ScreenObservationTests(unittest.TestCase):
    def test_usable_observation_carries_id_and_evidence_rules(self):
        controller = make_controller()
        observation = controller.observation()
        self.assertTrue(observation['usable'])
        self.assertEqual(observation['reason'], '')
        self.assertTrue(observation['observation_id'].startswith('obs-share-5-'))
        self.assertEqual(observation['foreground']['hwnd'], 11)
        self.assertFalse(observation['context_trusted'])
        self.assertIn('observation_id', observation['rule'])
        self.assertLessEqual(observation['frame_age_seconds'], 2)
        self.assertIn('usable=false', observation['rule'])

    def test_new_frame_yields_new_observation_id(self):
        controller = make_controller()
        first = controller.observation()['observation_id']
        controller._seq = 6
        controller._last_at = time.monotonic()
        second = controller.observation()['observation_id']
        self.assertNotEqual(first, second)

    def test_stale_frame_is_not_usable(self):
        controller = make_controller()
        controller._last_at = time.monotonic() - 30
        controller._context_at = time.monotonic() - 30
        observation = controller.observation(max_age=12)
        self.assertFalse(observation['usable'])
        self.assertEqual(observation['reason'], 'frame_stale')
        self.assertGreater(observation['frame_age_seconds'], 12)

    def test_foreground_change_invalidates_observation(self):
        controller = make_controller()
        controller._foreground = dict(hwnd=22, process='notepad.exe', title='另一个窗口')
        observation = controller.observation()
        self.assertFalse(observation['usable'])
        self.assertEqual(observation['reason'], 'foreground_changed')
        self.assertFalse(observation['context_matches_foreground'])

    def test_inactive_share_has_no_observation_id(self):
        controller = make_controller()
        controller._active = False
        observation = controller.observation()
        self.assertFalse(observation['usable'])
        self.assertIsNone(observation['observation_id'])
        self.assertEqual(observation['reason'], 'screen_share_inactive')

    def test_instructions_bind_actions_to_the_observation(self):
        controller = make_controller()
        observation = controller.observation()
        text = screen_observation_instructions(observation)
        self.assertIn(observation['observation_id'], text)
        self.assertIn('usable=false', text)
        self.assertIn('重新观察', text)
        self.assertIn('旧 observation_id 的坐标作废', text)
        self.assertEqual(screen_observation_instructions(None), '')


if __name__ == '__main__':
    unittest.main(verbosity=2)
