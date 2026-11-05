"""Regression: rejected artwork must never become a live animation."""
import json,os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import numpy as np
from PIL import Image,ImageSequence
from launcher import _prepare_qt
_prepare_qt()
import unittest
from PyQt5.QtGui import QColor,QImage,QPainter
from PyQt5.QtWidgets import QApplication
from ui.sprite_animator import SpriteAnimator

ROOT=Path(__file__).resolve().parents[1]
ACTION=ROOT/'resources/actions/joy_sway_dance'
APP=QApplication.instance() or QApplication([])


class JoyDanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.anim=SpriteAnimator(str(ROOT/'resources'),display_width=250)
    @classmethod
    def tearDownClass(cls):cls.anim.stop()

    def test_metadata_and_all_frames_are_transparent_and_in_bounds(self):
        metadata=json.loads((ACTION/'metadata.json').read_text(encoding='utf-8'))
        frames=sorted((ACTION/'frames').glob('frame_*.png'))
        self.assertEqual(metadata['frames'],125);self.assertEqual(len(frames),125)
        self.assertEqual(metadata['fps'],25);self.assertFalse(metadata['clipped_frames'])
        baselines=[]
        for path in frames[::8]:
            with Image.open(path) as im:
                self.assertEqual(im.mode,'RGBA');a=np.asarray(im)[:,:,3];ys,xs=np.where(a>24)
                self.assertGreater(len(xs),40000)
                self.assertFalse((a[:3]>24).any() or (a[-3:]>24).any() or (a[:,:3]>24).any() or (a[:,-3:]>24).any())
                baselines.append(int(ys.max()))
        self.assertLessEqual(max(baselines)-min(baselines),24)

    def test_preview_is_a_real_multiframe_animation(self):
        with Image.open(ACTION/'preview.gif') as preview:
            self.assertGreater(preview.n_frames,60)
            self.assertEqual(preview.info.get('loop'),0)
            self.assertEqual(len({im.convert('RGB').tobytes() for im in ImageSequence.Iterator(preview)}),preview.n_frames)

    def test_voice_and_context_dance_preserves_original_art(self):
        from core.embodiment import ALIASES
        action=ALIASES.get('跳舞')
        self.assertEqual(action,'dance')
        self.anim.set_expression('sleepy');self.assertTrue(self.anim.user_interaction())
        self.anim.trigger_action(action)
        self.assertTrue(self.anim.dancing)
        self.assertNotIn(self.anim.DANCE_CLIP,self.anim.clips)
        self.assertNotIn(self.anim.LEGACY_DANCE_CLIP,self.anim.clips)
        self.assertNotEqual(self.anim._clip,self.anim.DANCE_CLIP)
        self.anim.trigger_action('stop_dance')
        self.assertFalse(self.anim.dancing);self.assertIsNone(self.anim._clip)

    def test_representative_renders_keep_full_silhouette(self):
        for index in (0,32,64,96,127):
            self.anim._time=index/30
            self.anim._tick_action()
            self.assertEqual(self.anim.anim_scale_x,1.)
            self.assertEqual(self.anim.anim_scale_y,1.)
            canvas=QImage(360,430,QImage.Format_ARGB32);canvas.fill(QColor('#edf2f6'))
            painter=QPainter(canvas);self.anim.draw(painter,0,0);painter.end()
            image=canvas.convertToFormat(QImage.Format_RGBA8888);ptr=image.bits();ptr.setsize(image.sizeInBytes())
            pixels=np.frombuffer(ptr,dtype=np.uint8).reshape(image.height(),image.width(),4)
            visual=(np.any(pixels[:,:,:3]<220,axis=2))
            ys,xs=np.where(visual)
            self.assertGreater(len(xs),18000);self.assertGreater(ys.max(),340)

    def test_review_is_required_and_bound_to_exact_frames(self):
        import tempfile
        from core.avatar_review import approved_action,frames_digest
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder);frames=base/'frames';frames.mkdir()
            path=frames/'000.png';Image.new('RGBA',(8,8),'red').save(path)
            self.assertFalse(approved_action(frames))
            review=dict(status='approved',reviewer='test-fixture',frames_sha256=frames_digest(frames),
                checks={key:True for key in ('identity','continuous_motion','no_ghosts','anatomy','loop_seam')})
            (base/'visual-review.json').write_text(json.dumps(review),encoding='utf-8')
            self.assertTrue(approved_action(frames))
            Image.new('RGBA',(8,8),'blue').save(path)
            self.assertFalse(approved_action(frames))

if __name__=='__main__':unittest.main()
