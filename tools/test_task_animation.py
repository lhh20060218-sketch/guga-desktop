"""Real task events must reach Guga, without flashing, false success or voice cost."""
import os,json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from launcher import _prepare_qt
_prepare_qt()
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QImage,QColor
from core.task_animation import TaskAnimationDirector
from ui.sprite_animator import SpriteAnimator
from ui.mascot_animator import MascotAnimator
from ui.multi_agent_window import MultiAgentManager
APP=QApplication.instance() or QApplication([])
ROOT=Path(__file__).resolve().parents[1]


def reviewed_task_animator(width=250):
    anim=SpriteAnimator(str(ROOT/'resources'),width)
    anim._reference_clips_enabled=True;anim._load_task_clips()
    return anim


class TaskAnimationTests(unittest.TestCase):
    def setUp(self):
        self.now=0.;self.director=TaskAnimationDirector(lambda:self.now)

    def test_fast_command_never_flashes_a_delayed_pose(self):
        d=self.director;d.update('thinking');self.now=.1;d.update('success')
        self.now=2.;self.assertIsNone(d.poll());self.assertFalse(d.active)

    def test_real_phases_and_cooldown_not_timers_decide_the_state(self):
        d=self.director;d.update('thinking');self.now=1.3
        self.assertEqual(d.poll()['state'],'thinking')
        d.update('working');self.now=2.;self.assertIsNone(d.poll())
        self.now=4.;self.assertEqual(d.poll()['state'],'working')
        self.now=5.;self.assertIsNone(d.poll())
        d.update('error');self.now=7.;self.assertEqual(d.poll()['state'],'error')
        self.now=11.;self.assertIsNone(d.poll())

    def test_sidecar_running_prevents_parent_completion_celebration(self):
        d=self.director;d.update('working','parent');d.update('thinking','sidecar')
        self.now=4.;d.update('success','parent')
        self.assertEqual(d.poll()['state'],'thinking')
        self.now=8.;d.update('result','sidecar')
        self.assertEqual(d.poll()['state'],'result');self.assertFalse(d.jobs)

    def test_cancel_and_expired_blocked_terminal_never_celebrate(self):
        d=self.director;d.update('working');self.now=3.;d.update('cancelled')
        self.assertIsNone(d.poll())
        d.update('working');self.now=6.;d.update('success')
        self.assertIsNone(d.poll(blocked=True))
        self.now=12.;self.assertIsNone(d.poll())

    def test_guga_owner_route_reaches_actual_30hz_animator(self):
        a=reviewed_task_animator();a._task_motion=self.director
        manager=SimpleNamespace(owner=SimpleNamespace(_anim2d=a),companions={})
        self.assertTrue(MultiAgentManager.work_state(manager,'001','working','task'))
        self.now=2.;a._tick_task_motion()
        self.assertEqual(a._clip,'task:working');self.assertEqual(a._timer.interval(),33)
        count=self.director.count;a.set_speaking(True);self.now=20.;a.action='none';a._tick_task_motion()
        self.assertEqual(self.director.count,count);a.stop()

    def test_sleep_singing_and_drag_override_task_gestures(self):
        a=reviewed_task_animator();a._task_motion=self.director
        a.set_work_state('working');self.now=2.;a.set_expression('sleepy');a._tick_task_motion()
        self.assertEqual(a.expression,'sleepy');self.assertEqual(self.director.count,0)
        a.user_interaction();a.dancing=True;a._tick_task_motion();self.assertEqual(self.director.count,0)
        a.dancing=False;a.set_dragging(True);a._tick_task_motion();self.assertEqual(self.director.count,0)
        a.set_dragging(False);a._tick_task_motion();self.assertEqual(a._clip,'task:working');a.stop()

    def test_dora_route_uses_her_own_director(self):
        a=MascotAnimator('dora',140);a._task_motion=self.director
        manager=SimpleNamespace(owner=None,companions={'003':SimpleNamespace(profile={'appearance':'dora'},anim=a)})
        self.assertTrue(MultiAgentManager.work_state(manager,'003','thinking','dora-job'))
        self.now=2.;a.advance(.033);self.assertEqual(a.action,'tilt');a.stop()

    def test_thinking_uses_high_level_tilt_without_restarting_on_progress(self):
        d=self.director;d.update('thinking');self.now=2.
        self.assertEqual(d.poll()['gesture'],'tilt')
        for i in range(5):d.update('thinking')
        self.now=12.1;self.assertEqual(d.poll()['gesture'],'tilt')

    def test_legacy_spin_and_scratch_are_not_exposed(self):
        self.assertTrue({'spin','scratch_head','think_chin'}.isdisjoint(SpriteAnimator.ACTIONS))
        self.assertNotIn('spin',__import__('core.embodiment',fromlist=['ALIASES']).ALIASES)

    def test_approval_and_native_rate_are_both_required(self):
        from core.avatar_review import frames_digest
        a=SpriteAnimator(str(ROOT/'resources'),180)
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder)/'actions/task-motion';frames=base/'thinking/frames';frames.mkdir(parents=True)
            image=QImage(80,100,QImage.Format_ARGB32);image.fill(QColor('red'));image.save(str(frames/'00.png'))
            record=dict(status='approved',reviewer='isolated-test-fixture',frames_sha256=frames_digest(frames),
                checks={k:True for k in ('identity','continuous_motion','no_ghosts','anatomy','loop_seam')})
            (frames.parent/'visual-review.json').write_text(json.dumps(record),encoding='utf-8')
            a._res_dir=folder
            a.clips.pop('task:thinking',None)
            for rate,loaded in ((6,False),(24,True)):
                (base/'manifest.json').write_text(json.dumps({'states':{'thinking':{'frames':'thinking/frames','native_fps':rate}}}),encoding='utf-8')
                a._load_task_clips();self.assertEqual('task:thinking' in a.clips,loaded)
            self.assertEqual(a.clips['task:thinking']['fps'],24.)
        a.stop()

    def test_accepted_native_bundle_shares_pixels_and_never_loops(self):
        from core.avatar_review import approved_action
        self.assertTrue(approved_action(ROOT/'resources/actions/task-motion/look-up-step/frames'))
        a=reviewed_task_animator()
        first=a.clips['task:thinking'];second=a.clips['task:working']
        self.assertEqual(len(first['frames']),54);self.assertEqual(first['fps'],30)
        self.assertIs(first['frames'],second['frames']);self.assertIsNot(first,second)
        with patch('ui.sprite_animator.time.monotonic',return_value=100.) as clock:
            a.play_clip('task:thinking',loop=True)
            self.assertFalse(first['loop'])
            # A delayed GUI tick must not stretch 1.8 seconds into slow motion.
            clock.return_value=102.;a._tick()
        self.assertNotEqual(a._clip,'task:thinking');a.stop()

    def test_live_native_clip_stops_for_voice_drag_expression_and_cancel(self):
        a=reviewed_task_animator();a._task_motion=self.director
        for interruption in ('voice','drag','sleep','cancel'):
            a.set_speaking(False);a.set_dragging(False);a.user_interaction();a.set_expression('normal')
            a.set_work_state('working');a.play_clip('task:working',loop=False)
            if interruption=='voice':a.set_speaking(True)
            elif interruption=='drag':a.set_dragging(True)
            elif interruption=='sleep':a.set_expression('sleepy')
            else:a.set_work_state('cancelled')
            self.assertFalse((a._clip or '').startswith('task:'),interruption)
        a.stop()

    def test_single_shot_acceptance_is_specific_and_frame_bound(self):
        import shutil
        from core.avatar_review import approved_action
        source=ROOT/'resources/actions/task-motion/look-up-step'
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'clip';shutil.copytree(source,target)
            self.assertTrue(approved_action(target/'frames'))
            review=json.loads((target/'visual-review.json').read_text(encoding='utf-8'))
            review['user_approval']['quote']=''
            (target/'visual-review.json').write_text(json.dumps(review),encoding='utf-8')
            self.assertFalse(approved_action(target/'frames'))
            shutil.copy2(source/'visual-review.json',target/'visual-review.json')
            with (target/'frames/0000.png').open('ab') as handle:handle.write(b'changed')
            self.assertFalse(approved_action(target/'frames'))

if __name__=='__main__':unittest.main()
