import os
import subprocess
import time
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import numpy as np

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from core.fast_commands import match,execute
from core.speaker_gate import LocalSpeakerGate,SpeakerGate,SAMPLE_RATE,threshold_from_pairs


class FastCommandTests(unittest.TestCase):
    def setUp(self):
        patcher=patch("core.browser_launch.default_executable",return_value=None);patcher.start();self.addCleanup(patcher.stop)

    def test_polite_browser_and_website_requests_use_same_local_route(self):
        for text in ('帮我打开浏览器','请帮我打开浏览器','咕嘎，帮我打开一下浏览器','打开默认浏览器吧'):
            with self.subTest(text=text):
                command=match(text)
                self.assertTrue(command['matched']);self.assertEqual(command['kind'],'app')
                with patch('core.fast_commands._browser_executable',return_value=None), \
                     patch('core.fast_commands.webbrowser.open',return_value=True) as opened, \
                     patch('core.authorized_apps.AuthorizedApps.open') as scan:
                    result=execute(command)
                    opened.assert_called_once_with('https://www.baidu.com',new=2)
                    scan.assert_not_called()
                    self.assertTrue(result['ok']);self.assertFalse(result['verified_running'])
        for text in ('帮我打开百度','请打开 GitHub','咕嘎，打开b站一下'):
            self.assertEqual(match(text)['kind'],'url')

    def test_launch_failure_is_returned_instead_of_throwing_or_claiming_success(self):
        for effect in (False,OSError('default handler missing')):
            kwargs=dict(side_effect=effect) if isinstance(effect,Exception) else dict(return_value=effect)
            with patch('core.fast_commands._browser_executable',return_value=None),patch('core.fast_commands.webbrowser.open',**kwargs):
                result=execute(match('帮我打开浏览器'))
            self.assertFalse(result['ok']);self.assertIn('error',result)
        self.assertEqual(match('帮我打开浏览器然后搜索天气')['target'],'https://www.baidu.com/s?wd=%E5%A4%A9%E6%B0%94')
        self.assertFalse(match('不要打开浏览器')['matched'])

    def test_generic_browser_can_open_a_real_window_without_default_http_handler(self):
        with patch('core.fast_commands._browser_executable',return_value=Path('C:/Browser/msedge.exe')), \
             patch('core.fast_commands.subprocess.Popen') as launch,patch('core.fast_commands.webbrowser.open') as association:
            result=execute(match('帮我打开浏览器'))
        self.assertTrue(result['ok'])
        launch.assert_called_once_with(['C:\\Browser\\msedge.exe','about:blank'])
        association.assert_not_called()

    def test_stop_and_url_are_parsed_without_llm(self):
        self.assertEqual(match('停止对话')['action'],'stop_call')
        self.assertEqual(match('打开 github')['target'],'https://github.com')
        self.assertEqual(match('访问 example.com')['target'],'https://example.com')
        self.assertEqual(match('搜索 Python 教程')['action'],'web_search')

    def test_execution_uses_browser_or_app_without_model(self):
        with patch('webbrowser.open') as browser:
            result=execute(dict(matched=True,action='open_url',kind='url',target='https://example.com'))
            browser.assert_called_once_with('https://example.com',new=2)
        self.assertTrue(result['ok'])
        with patch('os.startfile') as start:
            result=execute(dict(matched=True,action='open_app',kind='app',target='记事本'))
            start.assert_called_once_with('notepad.exe')
        self.assertTrue(result['ok'])


class SpeakerGateTests(unittest.TestCase):
    def local_gate(self,score=1.):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        profile=Path(temp.name)/'owner.npy';np.save(profile,np.array([1.,0.],dtype=np.float32))
        with patch('core.speaker_gate._get_extractor'):
            gate=LocalSpeakerGate(profile_path=profile,threshold=.46)
        gate.embedding=lambda samples:np.array([score,np.sqrt(1-score*score)],dtype=np.float32)
        return gate

    def test_natural_pauses_preserve_every_owner_sample_once(self):
        gate=self.local_gate()
        # Distinct blocks detect both missing prefixes and duplicate release.
        blocks=[np.full(640,400+i,dtype=np.int16).tobytes() for i in range(10)]
        blocks += [bytes(1280)]*5  # 200 ms pause inside a sentence
        blocks += [np.full(640,500+i,dtype=np.int16).tobytes() for i in range(30)]
        output=b''.join(gate.process_pcm(raw,now=10+i*.04) for i,raw in enumerate(blocks))
        self.assertEqual(gate.state,'owner')
        self.assertEqual(output,b''.join(blocks))

    def test_low_confidence_prefix_is_retained_for_longer_comparison(self):
        gate=self.local_gate()
        scores=iter([np.array([0.,1.]),np.array([0.,1.]),np.array([1.,0.])])
        gate.embedding=lambda samples:next(scores,np.array([1.,0.]))
        blocks=[np.full(640,400+i,dtype=np.int16).tobytes() for i in range(45)]
        output=b''.join(gate.process_pcm(raw,now=10+i*.04) for i,raw in enumerate(blocks))
        self.assertEqual(output,b''.join(blocks))

    def test_foreign_speech_never_leaks_and_buffer_is_bounded(self):
        gate=self.local_gate(score=0.)
        voice=np.full(640,1000,dtype=np.int16).tobytes()
        blocks=[voice]*90+[bytes(1280)]*20
        out=b''.join(gate.process_pcm(raw,now=10+i*.04) for i,raw in enumerate(blocks))
        self.assertFalse(any(out))
        self.assertEqual(len(out),sum(map(len,blocks)))
        self.assertFalse(gate.pending)

    def test_identity_expires_before_next_speaker(self):
        gate=self.local_gate()
        voice=np.full(640,1000,dtype=np.int16).tobytes()
        for i in range(25):gate.process_pcm(voice,now=10+i*.04)
        self.assertTrue(gate.verified)
        for i in range(20):gate.process_pcm(bytes(1280),now=11+i*.04)
        self.assertFalse(gate.verified)
        gate.embedding=lambda samples:np.array([0.,1.])
        out=b''.join(gate.process_pcm(voice,now=12+i*.04) for i in range(30))
        self.assertFalse(any(out))

    def test_playback_and_mute_discard_pending_identity(self):
        gate=self.local_gate()
        voice=np.full(640,1000,dtype=np.int16).tobytes()
        for i in range(10):gate.process_pcm(voice,now=10+i*.04)
        self.assertTrue(gate.pending)
        self.assertEqual(gate.process_pcm(bytes(1280),now=10.4,blocked=True),bytes(1280))
        self.assertFalse(gate.pending)
        self.assertFalse(gate.verified)

    def test_owner_threshold_follows_model_scale(self):
        self.assertGreaterEqual(threshold_from_pairs([.25,.30,.34]),.24)
        self.assertLessEqual(threshold_from_pairs([.25,.30,.34]),.46)
        self.assertEqual(threshold_from_pairs([]),.30)
    def test_owner_audio_unlocks_and_foreign_audio_is_gated(self):
        owner=np.sin(np.arange(SAMPLE_RATE*2)*.06).astype(np.float32)*.08
        raw=(np.clip(owner,-1,1)*32767).astype(np.int16).tobytes()
        with tempfile.TemporaryDirectory() as folder:
            profile=Path(folder)/'owner.npy'
            code=("import numpy as np;from core.speaker_gate import _embedding;"
                  "a=np.sin(np.arange(32000)*.06).astype(np.float32)*.08;v=_embedding(a);v/=np.linalg.norm(v);"
                  f"np.save(r'{profile}',v)")
            subprocess.run([sys.executable,'-X','utf8','-c',code],cwd=str(ROOT),check=True)
            outputs=[];gate=SpeakerGate(profile_path=profile,threshold=.5,emit=outputs.append)
            try:
                for i in range(8):
                    gate.submit(raw[i*4000:(i+1)*4000]);time.sleep(.06)
                deadline=time.monotonic()+3
                while len(outputs)<8 and time.monotonic()<deadline:time.sleep(.05)
                self.assertEqual(gate.state,'owner')
                self.assertEqual(b''.join(outputs),raw[:32000])
                self.assertEqual(gate.stats['input_bytes'],32000)
                self.assertEqual(gate.stats['output_bytes'],32000)
            finally:gate.close()
            foreign=(np.random.default_rng(3).normal(0,.08,SAMPLE_RATE).clip(-1,1)*32767).astype(np.int16).tobytes()
            outputs=[];gate=SpeakerGate(profile_path=profile,threshold=.85,emit=outputs.append)
            try:
                states=[]
                for i in range(12):
                    gate.submit(foreign[(i%8)*4000:((i%8)+1)*4000]);time.sleep(.1);states.append(gate.state)
                deadline=time.monotonic()+.5
                while time.monotonic()<deadline:states.append(gate.state);time.sleep(.05)
                self.assertIn('rejected',states)
            finally:gate.close()


if __name__=='__main__':unittest.main()
