"""Offline regression for local, two-step task cancellation."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.task_control import TaskControlGate


class TaskControlGateTests(unittest.TestCase):
    def test_stop_starts_confirmation_without_cancelling(self):
        gate = TaskControlGate()
        result = gate.observe("停下目前的任务", busy=True, now=10)
        self.assertEqual(result["action"], "ask_stop")
        self.assertTrue(gate.pending)

    def test_explicit_yes_cancels_only_after_confirmation(self):
        gate = TaskControlGate()
        gate.observe("停止任务", busy=True, now=10)
        self.assertEqual(gate.observe("对，停止", busy=True, now=12)["action"], "cancel")
        self.assertFalse(gate.pending)

    def test_no_keeps_task_running(self):
        gate = TaskControlGate()
        gate.observe("先停一下", busy=True, now=10)
        self.assertEqual(gate.observe("不用，继续", busy=True, now=12)["action"], "continue")
        self.assertFalse(gate.pending)

    def test_unrelated_request_does_not_cancel_while_confirmation_is_pending(self):
        gate = TaskControlGate()
        gate.observe("停止任务", busy=True, now=10)
        self.assertEqual(gate.observe("打开浏览器", busy=True, now=12)["action"], "pending")
        self.assertTrue(gate.pending)

    def test_negative_future_action_is_not_stop_intent(self):
        gate = TaskControlGate()
        result = gate.observe("准备一条消息先不要发送", busy=True, now=10)
        self.assertEqual(result["action"], "none")
        self.assertFalse(gate.pending)

    def test_music_and_call_stop_are_handled_elsewhere(self):
        gate = TaskControlGate()
        for text in ("停止唱歌", "停止音乐", "停止对话", "结束语音通话"):
            self.assertEqual(gate.observe(text, busy=True, now=10)["action"], "none")

    def test_pending_confirmation_expires(self):
        gate = TaskControlGate(expiry_seconds=5)
        gate.observe("停止任务", busy=True, now=10)
        self.assertEqual(gate.observe("对", busy=True, now=16)["action"], "none")
        self.assertFalse(gate.pending)

    def test_idle_state_clears_pending(self):
        gate = TaskControlGate()
        gate.observe("停止任务", busy=True, now=10)
        self.assertEqual(gate.observe("对", busy=False, now=12)["action"], "none")
        self.assertFalse(gate.pending)


if __name__ == "__main__":
    unittest.main()
