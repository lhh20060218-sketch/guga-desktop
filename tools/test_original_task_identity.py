import os,unittest
from pathlib import Path
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from launcher import _prepare_qt
_prepare_qt()
from PyQt5.QtWidgets import QApplication
from ui.sprite_animator import SpriteAnimator
from core.task_animation import TaskAnimationDirector
APP=QApplication.instance() or QApplication([])
ROOT=Path(__file__).resolve().parents[1]

class OriginalIdentityTests(unittest.TestCase):
    def test_real_task_and_voice_never_select_an_alternate_task_movie(self):
        now=[0.];a=SpriteAnimator(str(ROOT/'resources'),250);a._task_motion=TaskAnimationDirector(lambda:now[0])
        try:
            self.assertFalse(a._reference_clips_enabled)
            self.assertFalse(any(x.startswith('task:') for x in a.clips))
            for state in ('thinking','working','waiting'):
                a.action='none';a.set_work_state(state,'test');now[0]+=12;a._tick_task_motion()
                self.assertFalse((a._clip or '').startswith('task:'))
            a.trigger_action('look_up_step');self.assertFalse((a._clip or '').startswith('task:'))
            a.set_speaking(True);self.assertFalse((a._clip or '').startswith('task:'))
        finally:a.stop()

if __name__=='__main__':unittest.main()
