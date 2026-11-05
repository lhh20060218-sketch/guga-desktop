"""Bounded motion tests; no desktop, microphone, API or game interaction."""
import math
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ui.avatar_motion import AvatarMotion


class MotionTests(unittest.TestCase):
    def advance(self, m, seconds, fps=60):
        for _ in range(round(seconds * fps)): m.advance(1/fps)
        return m.pose

    def test_spin_exposes_the_back_and_settles(self):
        m = AvatarMotion(); m.trigger_action('spin')
        p = self.advance(m, 1.1)
        self.assertAlmostEqual(p.yaw, 180, places=5)
        self.advance(m, 1.3)
        self.assertEqual(m.action, 'none')
        self.assertAlmostEqual(m.pose.yaw, 0)

    def test_time_not_frame_count_controls_actions(self):
        a, b = AvatarMotion(), AvatarMotion()
        for m in (a,b): m.trigger_action('spin')
        self.assertAlmostEqual(self.advance(a, .8, 30).yaw, self.advance(b, .8, 60).yaw, places=5)

    def test_peek_has_independent_head_and_body(self):
        m=AvatarMotion(); m.trigger_action('sneak_peek'); p=self.advance(m, 1.5)
        self.assertLess(p.roll, 0); self.assertGreater(p.head_roll, 0)
        self.assertGreater(p.head_yaw, 25)

    def test_singing_accessories_do_not_expire(self):
        m=AvatarMotion();m.dancing=True;m.sunglasses=True;m.sunglasses_until=0
        self.advance(m, 12)
        self.assertTrue(m.dancing and m.sunglasses)
        m.trigger_action('stop_dance');m.trigger_action('remove_sunglasses')
        self.assertFalse(m.dancing or m.sunglasses)

    def test_occasional_glasses_expire(self):
        m=AvatarMotion();m.trigger_action('sunglasses');self.advance(m, 8.2)
        self.assertFalse(m.sunglasses)

    def test_gaze_and_drag_settle_and_remain_finite(self):
        m=AvatarMotion();m.look_at(500,-500);m.set_dragging(True,10000)
        p=self.advance(m,1)
        self.assertLessEqual(abs(p.head_yaw),18.01)
        self.assertLessEqual(abs(p.roll),18.01)
        m.look_at(0,0);m.set_dragging(False);p=self.advance(m,3)
        self.assertLess(abs(p.roll),.01)
        self.assertLess(abs(p.head_yaw),.01)
        self.assertTrue(all(math.isfinite(v) for v in vars(p).values()))

    def test_wave_and_dance_have_independent_depth_and_foot_motion(self):
        m=AvatarMotion();m.trigger_action('wave');p=self.advance(m,.55)
        self.assertGreater(abs(p.wing_right_pitch),5)
        self.assertNotEqual(p.wing_right_pitch,p.wing_left_pitch)
        m=AvatarMotion();m.dancing=True
        poses=[m.advance(1/30) for _ in range(120)]
        self.assertGreater(max(abs(p.depth) for p in poses),.08)
        self.assertGreater(max(p.foot_left_lift for p in poses),.08)
        self.assertGreater(max(p.foot_right_lift for p in poses),.08)
        self.assertTrue(any(p.foot_left_lift>p.foot_right_lift+.04 for p in poses))
        self.assertTrue(any(p.foot_right_lift>p.foot_left_lift+.04 for p in poses))

    def test_head_turn_has_inertia_and_dance_fades_out(self):
        m=AvatarMotion();m.trigger_action('spin');p=self.advance(m,.8)
        self.assertLess(p.head_yaw,-5)
        self.advance(m,3)
        self.assertLess(abs(m.pose.head_yaw),.1)
        m=AvatarMotion();m.dancing=True;self.advance(m,.8)
        m.dancing=False;p=m.advance(1/60)
        self.assertGreater(abs(p.wing_left)+abs(p.wing_right),1)
        self.advance(m,2)
        self.assertLess(abs(m.pose.wing_left)+abs(m.pose.wing_right),.01)

    def test_drag_release_lift_is_continuous(self):
        m=AvatarMotion();m.set_dragging(True,100);p=self.advance(m,.7)
        before=p.lift;m.set_dragging(False);p=m.advance(1/60)
        self.assertLess(abs(p.lift-before),.035)


if __name__ == '__main__': unittest.main()
