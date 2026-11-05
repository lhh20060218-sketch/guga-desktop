"""Offline regression: context expressions survive idle/mood/voice events."""
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from launcher import _prepare_qt
_prepare_qt()
from PyQt5.QtWidgets import QApplication
from ui.sprite_animator import SpriteAnimator
from core.realtime_agent import AgentRealtimeVoice
app=QApplication.instance() or QApplication([])

class ExpressionTests(unittest.TestCase):
    def make(self):return SpriteAnimator(str(ROOT/'resources'),250)
    def ticks(self,a,n):
        with patch('ui.sprite_animator.random.random',return_value=.9):
            for _ in range(n):a._tick()

    def test_all_context_faces_survive_30_seconds_and_mood_reset(self):
        for expr in ('sleepy','sad','surprised','playful'):
            a=self.make();a.set_expression(expr);self.ticks(a,900)
            a.update_mood('😊');self.ticks(a,60)
            self.assertEqual(a.expression,expr)

    def test_idle_overlay_returns_to_context_and_cannot_replace_sleepy(self):
        a=self.make();a.set_expression('happy');a._idle_expr_countdown=100
        self.assertTrue(a.temporary_expression('surprised',.2));self.ticks(a,15)
        self.assertEqual(a.expression,'happy')
        a.set_expression('sleepy')
        self.assertFalse(a.temporary_expression('happy',2));self.assertEqual(a.expression,'sleepy')

    def test_explicit_face_cancels_pending_idle_restoration(self):
        a=self.make();a.temporary_expression('sleepy',.2);a.set_expression('sad')
        self.ticks(a,60);self.assertEqual(a.expression,'sad')
        a.set_expression('normal');self.assertIsNone(a._context_expression)
        self.assertEqual(a.expression,'normal')

    def test_talking_does_not_reset_context(self):
        a=self.make();a.set_expression('sleepy');a.mouth_open=.5
        self.ticks(a,180);self.assertEqual(a.expression,'sleepy')

    def test_sleepy_rejects_autonomous_expression_updates(self):
        a=self.make();a.set_expression('sleepy')
        for expr in ('normal','happy','surprised','sad','playful'):
            a.set_expression(expr)
            self.assertEqual(a.expression,'sleepy')

    def test_only_user_interaction_wakes_sleepy_and_can_request_sleep_again(self):
        a=self.make();a.set_expression('sleepy');a.look_at(.8,-.5)
        self.ticks(a,120);self.assertEqual(a.expression,'sleepy')
        self.assertTrue(a.user_interaction());self.assertEqual(a.expression,'happy')
        self.ticks(a,90);self.assertEqual(a.expression,'happy')
        a.set_expression('sleepy');self.ticks(a,90)
        self.assertEqual(a.expression,'sleepy')

    def test_idle_sleepy_is_also_latched(self):
        a=self.make();a._idle_expr_countdown=100
        with patch('ui.sprite_animator.random.random',return_value=0):a._tick()
        self.assertEqual(a.expression,'sleepy')
        self.ticks(a,900);self.assertEqual(a.expression,'sleepy')
        a.user_interaction();self.assertEqual(a.expression,'happy')

    def test_native_voice_expression_tool_reaches_visual_layer(self):
        a=self.make();v=AgentRealtimeVoice();v.expression_requested.connect(a.set_expression)
        with patch.object(v,'resolve_task') as resolve:
            v._accept_call(dict(call_id='face-1',name='set_expression',arguments=json.dumps({'name':'sleepy'})))
            self.assertEqual(a.expression,'sleepy');resolve.assert_called_once()
        self.ticks(a,300);self.assertEqual(a.expression,'sleepy')
        self.assertIn('set_expression',[t['name'] for t in v._session_settings()['tools']])

if __name__=='__main__':unittest.main()
