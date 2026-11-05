"""Regressions for companion sprite switching, sleep latch and motion framing."""
import json,os,sys,tempfile,unittest
from pathlib import Path
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from launcher import _prepare_qt
_prepare_qt()
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QImage,QPainter,QColor
from PyQt5.QtWidgets import QApplication
from ui.mascot_animator import MascotAnimator
APP=QApplication.instance() or QApplication([])

class MascotTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.folder=Path(self.temp.name)
        expressions={}
        for name,color in [('normal','blue'),('happy','yellow'),('sad','cyan'),('sleepy','gray'),('angry','red')]:
            image=QImage(160,200,QImage.Format_ARGB32);image.fill(Qt.transparent)
            p=QPainter(image);p.fillRect(4,4,152,192,QColor(color));p.end()
            image.save(str(self.folder/(name+'.png')));expressions[name]=name+'.png'
        self.manifest=self.folder/'manifest.json'
        self.manifest.write_text(json.dumps(dict(schema=1,expressions=expressions,fallbacks={'playful':'angry'})))
        self.anim=MascotAnimator('dora',225,self.manifest)
    def tearDown(self):self.anim.stop();self.temp.cleanup()
    def render(self):
        image=QImage(self.anim.width,self.anim.height,QImage.Format_ARGB32);image.fill(Qt.transparent)
        p=QPainter(image);self.anim.draw(p,0,0);p.end();return image
    def test_expression_changes_actual_texture_without_resizing_window(self):
        before=(self.anim.width,self.anim.height)
        self.anim.set_expression('sad');self.anim.advance(.1);self.anim.advance(.1)
        self.assertEqual(Path(self.anim.path).name,'sad.png')
        image=self.render()
        self.assertEqual(image.pixelColor(image.width()//2,image.height()//2),QColor('cyan'))
        self.assertEqual(before,(self.anim.width,self.anim.height))
    def test_sleep_survives_background_reply_gaze_and_actions_until_user_interacts(self):
        self.anim.set_expression('sleepy')
        for _ in range(300):
            self.anim.look_at(1,-1);self.anim.set_expression('happy');self.anim.advance(.1)
        self.anim.trigger_action('wave');self.anim.advance(.1)
        self.assertEqual(self.anim.expression,'sleepy')
        self.assertEqual(Path(self.anim.path).name,'sleepy.png')
        self.assertTrue(self.anim.user_interaction());self.assertEqual(self.anim.expression,'happy')
    def test_no_idle_restore_undoes_an_intentional_face(self):
        self.anim.set_expression('sad')
        for _ in range(600):self.anim.advance(.1)
        self.assertEqual(self.anim.expression,'sad')
        self.anim.set_expression('angry');self.assertEqual(Path(self.anim.path).name,'angry.png')
    def test_missing_expression_uses_declared_texture_fallback(self):
        self.anim.set_expression('playful');self.assertEqual(Path(self.anim.path).name,'angry.png')
    def test_bad_bundle_cannot_load_outside_resource_folder(self):
        self.manifest.write_text(json.dumps(dict(schema=1,expressions={'normal':'../outside.png'})))
        with self.assertRaises(ValueError):MascotAnimator('dora',225,self.manifest)
    def test_actions_keep_complete_silhouette_inside_fixed_window(self):
        for action in ('bounce','spin','shake','sneak_peek','wave','nod','dance'):
            self.anim.trigger_action(action)
            for _ in range(25):
                self.anim.advance(.1);image=self.render();w,h=image.width(),image.height()
                for x,y in [(x,0) for x in range(w)]+[(x,h-1) for x in range(w)]+[(0,y) for y in range(h)]+[(w-1,y) for y in range(h)]:
                    self.assertEqual(image.pixelColor(x,y).alpha(),0,(action,x,y))
        self.anim.trigger_action('stop_dance')
    def test_legacy_avatar_still_opens_without_bundle(self):
        legacy=MascotAnimator('guga',225);self.assertTrue(legacy._frames);legacy.stop()


class ReviewedAssetTests(unittest.TestCase):
    def test_runtime_loads_eight_distinct_transparent_full_body_sources(self):
        from PIL import Image
        import hashlib
        hashes=set()
        for who in ('dora','dafish'):
            a=MascotAnimator(who,225)
            self.assertEqual(len(a.available_expressions),4)
            for frames,durations,path in a._bundles.values():
                self.assertIn('v2',str(path))
                hashes.add(hashlib.sha256(Path(path).read_bytes()).hexdigest())
                with Image.open(path) as image:
                    self.assertEqual(image.mode,'RGBA')
                    self.assertGreaterEqual(min(image.size),1200)
                    alpha=image.getchannel('A')
                    self.assertEqual(alpha.getextrema(),(0,255))
                    bbox=alpha.point(lambda x:255 if x>=20 else 0).getbbox()
                    self.assertTrue(bbox[0]>0 and bbox[1]>0 and bbox[2]<image.width and bbox[3]<image.height)
            a.stop()
        self.assertEqual(len(hashes),8)

    def test_companion_voice_exposes_new_expressions_without_changing_guga(self):
        from core.realtime_agent import AgentRealtimeVoice,EXPRESSION_TOOL
        def names(voice):
            tool=next(t for t in voice._session_settings()['tools'] if t['name']=='set_expression')
            return tool['parameters']['properties']['name']['enum']
        original=list(EXPRESSION_TOOL['parameters']['properties']['name']['enum'])
        voice=AgentRealtimeVoice();self.assertNotIn('angry',names(voice))
        voice.agent_profile=dict(agent_id='003',display_name='Dora')
        self.assertIn('angry',names(voice));self.assertIn('eating',names(voice))
        self.assertEqual(EXPRESSION_TOOL['parameters']['properties']['name']['enum'],original)

    def test_native_voice_expression_callback_changes_dora_actual_sprite(self):
        from unittest.mock import patch
        from core.realtime_agent import AgentRealtimeVoice
        a=MascotAnimator('dora',225);voice=AgentRealtimeVoice()
        voice.agent_profile=dict(agent_id='003',display_name='Dora')
        voice.expression_requested.connect(a.set_expression)
        with patch.object(voice,'resolve_task'):
            voice._accept_call(dict(call_id='dora-angry',name='set_expression',arguments=json.dumps({'name':'angry'})))
        self.assertEqual(Path(a.path).name,'angry.png');self.assertEqual(a.expression,'angry');a.stop()

if __name__=='__main__':unittest.main()
