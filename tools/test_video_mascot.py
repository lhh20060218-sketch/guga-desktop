"""Real VP9-alpha decode, bounded workers and sleep/interaction regression."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import hashlib
import json
import threading
import time
import unittest
from pathlib import Path
from launcher import _prepare_qt
_prepare_qt()
from PyQt5.QtCore import QPoint
from PyQt5.QtWidgets import QApplication,QWidget
from ui.video_mascot import VideoMascotAnimator,PACK
from ui.pet_physics import release_velocity,squash_scale,DesktopPetPhysics
APP=QApplication.instance() or QApplication([])


class VideoTests(unittest.TestCase):
    def setUp(self):
        self.anim=VideoMascotAnimator(180)
    def tearDown(self):
        self.anim.stop()

    def wait_frame(self,timeout=2.):
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            APP.processEvents()
            if self.anim._video_frame is not None:return self.anim._video_frame
            time.sleep(.01)
        self.fail('real video frame was not delivered')

    def test_real_decode_preserves_alpha_and_worker_queue_is_bounded(self):
        self.anim.start();im=self.wait_frame()
        self.assertEqual(im.pixelColor(0,0).alpha(),0)
        self.assertGreater(im.pixelColor(im.width()//2,im.height()//2).alpha(),150)
        self.assertLessEqual(self.anim._queue.qsize(),6)
        self.assertFalse(self.anim.decode_error)

    def test_all_assets_are_original_and_declared_actions_exist(self):
        manifest=self.anim.pack
        self.assertEqual(len(manifest['assets']),109)
        for name,digest in manifest['assets'].items():
            self.assertEqual(hashlib.sha256((PACK/name).read_bytes()).hexdigest(),digest,name)
        for category in self.anim.pools['categories']:
            for name in category['actions']:self.assertTrue((PACK/(name+'.webm')).is_file(),name)

    def test_sleep_has_start_loop_wake_and_background_cannot_wake(self):
        self.anim.start();self.anim.set_expression('sleepy')
        self.assertEqual(self.anim._mode,'sleep_start')
        self.anim._ended();self.assertEqual(self.anim._mode,'sleep_loop')
        self.assertFalse(self.anim.set_expression('happy'))
        self.assertFalse(self.anim.set_work_state('working'))
        self.anim.set_speaking(True)
        self.assertEqual(self.anim._mode,'sleep_loop')
        self.anim.user_interaction();self.assertEqual(self.anim._mode,'wake')
        self.assertEqual(self.anim.expression,'happy')

    def test_drag_and_named_actions_use_source_clips(self):
        self.anim.start();before=self.anim.current_clip;self.anim.set_dragging(True,9999)
        self.assertEqual(self.anim.current_clip,before)
        self.assertFalse(self.anim._presence.dragging)
        self.anim.set_dragging(False);self.anim.trigger_action('spin')
        self.assertEqual(self.anim.current_clip,'小幅度原地360度旋转展示')
        self.anim.set_expression('eating');self.assertEqual(self.anim.current_clip,'吃白饭')
        self.anim._ended();self.assertEqual(self.anim._mode,'held')

    def test_rapid_switches_cancel_old_workers_and_close_releases_them(self):
        self.anim.start()
        for name in ('吃白饭','点击回应-元气挥手','东张西望')*3:self.anim.play_clip(name)
        self.wait_frame();self.anim.stop()
        self.assertFalse(self.anim._workers)

    def test_speech_and_work_animation_do_not_need_model_or_dsh(self):
        self.anim.start();self.anim.set_speaking(True)
        self.assertEqual(self.anim._mode,'speech')
        self.assertFalse(self.anim.set_work_state('working'))
        self.anim.set_speaking(False);self.anim.set_work_state('working')
        self.assertEqual(self.anim.current_clip,'工作状态-忙碌点按')
        generation=self.anim._generation;self.anim.set_work_state('working')
        self.assertEqual(self.anim._generation,generation)


class PhysicsTests(unittest.TestCase):
    def test_click_curve_is_continuous_and_preserves_face_shape(self):
        self.assertAlmostEqual(squash_scale(0),1)
        self.assertAlmostEqual(squash_scale(.45),.90)
        self.assertAlmostEqual(squash_scale(1),1)
        for i in range(101):self.assertTrue(.9<=squash_scale(i/100)<=1.04)

    def test_slow_drag_or_paused_release_does_not_throw(self):
        self.assertIsNone(release_velocity([(0,0,0),(.1,10,0)],.1))
        self.assertIsNone(release_velocity([(0,0,0),(.1,200,0)],.3))
        vx,vy=release_velocity([(0,0,0),(.1,200,0)],.1)
        self.assertTrue(500<vx<3600);self.assertEqual(vy,0)

    def test_fast_drag_release_stays_where_dropped_and_has_no_inertia(self):
        w=QWidget();w.resize(100,100);w.move(100,100)
        physics=DesktopPetPhysics(w,object())
        physics.samples.extend([(time.monotonic()-.1,0,0),(time.monotonic(),200,0)])
        before=w.pos()
        self.assertFalse(physics.release(True))
        self.assertFalse(physics.timer.isActive());self.assertEqual(w.pos(),before)
        physics.press(QPoint(200,200));self.assertFalse(physics.timer.isActive())
        w.close()

if __name__=='__main__':unittest.main()
