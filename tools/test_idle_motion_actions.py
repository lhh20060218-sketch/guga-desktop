"""The supplied idle clips load once, stay out of task/voice priority, and end."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import unittest
from pathlib import Path
from unittest.mock import patch
from launcher import _prepare_qt
_prepare_qt()
from PyQt5.QtWidgets import QApplication
from ui.sprite_animator import SpriteAnimator

APP=QApplication.instance() or QApplication([])
ROOT=Path(__file__).resolve().parents[1]


class IdleMotionTests(unittest.TestCase):
    def setUp(self):
        self.anim=SpriteAnimator(str(ROOT/'resources'),245);self.anim.stop()

    def tearDown(self):
        self.anim.stop()

    def test_both_native_clips_load_on_the_same_canvas(self):
        self.assertEqual({name for name,_ in self.anim.idle_motion_clips},{'doze','heart'})
        self.assertEqual(set(self.anim.task_animation_status()['idle_motion']['loaded']),{'doze','heart'})
        for name in ('doze','heart'):
            clip=self.anim.clips['idle:'+name]
            self.assertEqual(clip['fps'],24.)
            self.assertEqual(len(clip['frames']),239)
            self.assertTrue(clip['one_shot_only']);self.assertFalse(clip['loop'])
            sizes={(pm.width(),pm.height()) for pm in clip['frames']}
            self.assertEqual(len(sizes),1)
            width,height=next(iter(sizes))
            self.assertLessEqual(abs(width-self.anim._dw),1)
            self.assertLessEqual(abs(height-self.anim._dh),1)

    def test_startup_does_not_decode_hundreds_of_frames(self):
        for name in ('doze','heart'):
            frames=self.anim.clips['idle:'+name]['frames']
            self.assertEqual(len(frames.cache),0)
            first=frames[0];self.assertIs(first,frames[0]);self.assertEqual(len(frames.cache),1)
            for i in range(60):frames[i]
            self.assertLessEqual(len(frames.cache),36)

    def test_idle_render_drops_to_twenty_fps_and_interaction_restores_thirty(self):
        self.anim._timer.start()
        self.anim.set_speaking(False);self.anim.action='none';self.anim.dancing=False
        self.anim._task_motion.jobs.clear();self.anim._temporary_expression=None;self.anim._transition=1.
        self.anim._last_tick-=1
        self.anim._tick()
        self.assertEqual(self.anim._timer.interval(),50)
        self.anim.set_speaking(True);self.anim._last_tick-=1;self.anim._tick()
        self.assertEqual(self.anim._timer.interval(),33)
        self.anim._timer.stop()

    def test_priority_interruptions_stop_idle_video(self):
        cases=(
            ('voice',lambda:self.anim.set_speaking(True)),
            ('drag',lambda:self.anim.set_dragging(True)),
            ('task',lambda:self.anim.set_work_state('working')),
            ('music',lambda:self.anim.set_music_stage(True)),
            ('gesture',lambda:self.anim.trigger_action('nod')),
            ('tap',lambda:self.anim.tap()),
        )
        for label,interrupt in cases:
            with self.subTest(label=label):
                self.anim.set_speaking(False);self.anim.set_dragging(False);self.anim.set_music_stage(False)
                self.anim.set_work_state('idle');self.anim.action='none'
                self.anim.play_clip('idle:doze',loop=False);interrupt()
                self.assertFalse((self.anim._clip or '').startswith('idle:'))

    def test_menu_and_control_can_trigger_each_video_directly(self):
        for action,clip in (('idle_doze','idle:doze'),('idle_heart','idle:heart')):
            self.anim.trigger_action(action)
            self.assertEqual(self.anim._clip,clip)
            self.assertFalse(self.anim.dancing)

    def test_stale_tts_mouth_cannot_block_idle_forever(self):
        self.anim._speaking=False;self.anim.mouth_open=.4;self.anim._clip='talk'
        for _ in range(60):self.anim._tick()
        self.assertEqual(self.anim.mouth_open,0.)
        self.assertNotEqual(self.anim._clip,'talk')

    def test_idle_choice_uses_weights_and_one_shot_playback(self):
        with patch('ui.sprite_animator.random.random',return_value=.01),patch('ui.sprite_animator.random.choices',return_value=['heart']) as choose:
            self.anim._idle_action_countdown=0;self.anim._tick()
        self.assertEqual(self.anim._clip,'idle:heart');choose.assert_called_once()
        clip=self.anim.clips['idle:heart']
        with patch('ui.sprite_animator.time.monotonic',return_value=100.):self.anim.play_clip('idle:heart',loop=True)
        self.assertFalse(clip['loop'])
        with patch('ui.sprite_animator.time.monotonic',return_value=111.):self.anim._tick()
        self.assertFalse((self.anim._clip or '').startswith('idle:'))


if __name__=='__main__':unittest.main()
