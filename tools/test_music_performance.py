import os,sys,tempfile,json,wave
from pathlib import Path
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from launcher import _prepare_qt
_prepare_qt()
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QImage,QPainter
from PyQt5.QtCore import Qt
from core.fast_commands import match
from core.music_performance import MusicPerformance
from ui.sprite_animator import SpriteAnimator
APP=QApplication.instance() or QApplication([])
class MusicTests(unittest.TestCase):
 def test_explicit_song_and_stop_are_local_commands(self):
  self.assertEqual(match('帮我唱一首《跳楼机》')['target'],'跳楼机')
  self.assertEqual(match('停止唱歌')['kind'],'music_stop')
  self.assertFalse(match('你喜欢跳楼机这首歌吗')['matched'])
  self.assertEqual(match('戴上墨镜')['target'],'sunglasses')
  for request in ('唱歌','给我唱首歌吧','我想听你唱歌','你能不能唱一首歌'):
   self.assertEqual(match(request)['target'],'晴天')
 def test_multi_agent_summon_and_discussion_commands(self):
  self.assertEqual(match('召唤002')['kind'],'summon')
  self.assertEqual(match('召唤大肥鱼')['target'],'002')
  self.assertEqual(match('叫出Dora')['target'],'003')
  self.assertEqual(match('叫出两个咕嘎')['kind'],'summon_pair')
  item=match('让001和002讨论要不要先备份')
  self.assertEqual(item['action'],'multiagent');self.assertEqual(item['target'],'001,002');self.assertEqual(item['topic'],'要不要先备份')
  self.assertEqual(match('让001与003商量一下')['kind'],'discuss_ask')

 def test_native_voice_music_tool_uses_direct_player_route_and_deduplicates(self):
  from core.realtime_agent import AgentRealtimeVoice
  voice=AgentRealtimeVoice();commands=[];voice.fast_command.connect(commands.append)
  item=dict(call_id='song',name='perform_music',arguments='{"action":"sing"}')
  voice._accept_call(item);voice._accept_call(item)
  self.assertEqual(len(commands),1);self.assertEqual(commands[0]['target'],'晴天')
  self.assertEqual(commands[0]['kind'],'sing')
  voice._fast_jobs.clear();voice._accept_call(dict(call_id='pause',name='perform_music',arguments='{"action":"pause"}'))
  self.assertEqual(commands[-1]['kind'],'music_pause')

 def test_packaged_song_relative_path_is_resolved_at_library(self):
  with tempfile.TemporaryDirectory() as d,patch('core.music_performance.MUSIC',Path(d)):
   folder=Path(d);path=folder/'song.wav'
   with wave.open(str(path),'wb') as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(16000);w.writeframes(b'\0\0'*16000)
   (folder/'library.json').write_text(json.dumps({'晴天':dict(path='song.wav',pipeline_version=2,verified_full_length=True)}),encoding='utf-8')
   music=MusicPerformance()
   with patch.object(music.player,'play'),patch.object(music.playlist,'addMedia',return_value=True) as media:
    self.assertTrue(music.sing('晴天')['ok'])
    resolved=Path(media.call_args.args[0].canonicalUrl().toLocalFile())
    self.assertTrue(resolved.samefile(path))
    from PyQt5.QtMultimedia import QMediaPlaylist,QMediaPlayer
    self.assertEqual(music.playlist.playbackMode(),QMediaPlaylist.CurrentItemInLoop)
    self.assertTrue(music.status()['repeat'])
    music._state(QMediaPlayer.PlayingState);self.assertFalse(music.interaction.isActive())
    music.stop();self.assertFalse(music.repeat);self.assertFalse(music.requested)
 def test_missing_song_is_failure_not_fake_tts(self):
  with tempfile.TemporaryDirectory() as d,patch('core.music_performance.MUSIC',Path(d)):
   music=MusicPerformance()
   self.assertFalse(music.sing('跳楼机')['ok']);self.assertFalse(music.playing)
 def test_gesture_accessory_and_dance_are_independent(self):
  a=SpriteAnimator(str(ROOT/'resources'),250)
  a.trigger_action('sunglasses');a.trigger_action('dance')
  self.assertTrue(a.sunglasses);self.assertTrue(a.dancing)
  # The reviewed dance asset remains rejected; motion must not resurrect it.
  self.assertNotEqual(a.active_clip,a.DANCE_CLIP)
  a.trigger_action('stop_dance');a._tick_action();self.assertFalse(a.dancing);self.assertTrue(a.sunglasses)
  self.assertIsNone(a.active_clip)
  a.trigger_action('remove_sunglasses');self.assertFalse(a.sunglasses)
 def test_singing_glasses_are_latched_even_after_long_interaction(self):
  a=SpriteAnimator(str(ROOT/'resources'),250)
  a.set_music_stage(True);self.assertTrue(a.sunglasses)
  a.trigger_action('remove_sunglasses');a._tick_action()
  self.assertTrue(a.sunglasses);self.assertEqual(a._sunglasses_until,0)
  a._time=100.;a._tick_action();self.assertTrue(a.sunglasses)
  a.set_music_stage(False);self.assertFalse(a.sunglasses)
 def test_stage_resync_is_change_only_and_repairs_a_missed_event(self):
  music=MusicPerformance();events=[];music.performance_event.connect(events.append)
  music._sync_stage();self.assertEqual(events,[])
  music.playing=True;music.title='晴天';music._sync_stage();music._sync_stage()
  self.assertEqual([(x['type'],x['title']) for x in events],[('playing','晴天')])
 def test_glasses_change_actual_rendered_pixels(self):
  a=SpriteAnimator(str(ROOT/'resources'),250)
  def frame():
   im=QImage(a.width,a.height,QImage.Format_ARGB32);im.fill(Qt.transparent);p=QPainter(im);a.draw(p,0,0);p.end();return im
  normal=frame();a.trigger_action('sunglasses');self.assertNotEqual(normal,frame())
 def test_stop_invalidates_stale_conversion_result(self):
  music=MusicPerformance();generation=music.generation;music.stop()
  with patch.object(music,'sing') as play:
   music._prepared(dict(generation=generation,ok=True,title='跳楼机'))
   play.assert_not_called()
 def test_source_does_not_match_song_so_conversion_does_not_start(self):
  with tempfile.TemporaryDirectory() as d,patch('core.music_performance.MUSIC',Path(d)):
   folder=Path(d);(folder/'source.json').write_text(json.dumps(dict(title='其他歌曲',path='missing')))
   music=MusicPerformance();self.assertFalse(music.prepare('跳楼机')['ok']);self.assertFalse(music.preparing)
if __name__=='__main__':unittest.main()
