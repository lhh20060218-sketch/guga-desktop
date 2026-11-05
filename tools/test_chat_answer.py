"""No real API, microphone or song: check Q&A isolation and speech routing."""
import os,json,sys,threading,time,unittest
from pathlib import Path
from unittest.mock import MagicMock,patch
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from launcher import _prepare_qt
_prepare_qt()
from PyQt5.QtWidgets import QApplication
from core.chat_answer import AnswerWorker,request_payload,uses_task
from core.short_voice import ShortVoice
from core.music_stop import is_stop_phrase
APP=QApplication.instance() or QApplication([])


class AnswerTests(unittest.TestCase):
    def setUp(self):
        self.search=patch('core.search_results.search',return_value=dict(ok=False,results=[])).start()
        self.addCleanup(patch.stopall)
    def pump(self,predicate,seconds=2):
        until=time.monotonic()+seconds
        while not predicate() and time.monotonic()<until:APP.processEvents();time.sleep(.005)
        self.assertTrue(predicate())

    def test_effort_payload_has_no_tools_and_quick_is_explicitly_off(self):
        cfg=dict(base_url='https://opencode.ai/zen/go/v1')
        for effort in ('quick','low','high','max'):
            p=request_payload(cfg,[],effort);self.assertNotIn('tools',p)
            self.assertEqual(p['thinking']['type'],'disabled' if effort=='quick' else 'enabled')
            self.assertEqual(p['reasoning_effort'],'none' if effort=='quick' else effort)
        self.assertNotIn('reasoning_effort',request_payload(dict(base_url='https://api.deepseek.com'),[],'quick'))

    def test_questions_and_execution_have_independent_routes(self):
        self.assertFalse(uses_task('解释截图里的接口是什么意思',image=True))
        self.assertFalse(uses_task('帮我写一段简短的自我介绍'))
        self.assertTrue(uses_task('打开微信给小军发送自我介绍'))
        self.assertFalse(uses_task('打开微信','chat'));self.assertTrue(uses_task('你好','task'))

    def test_stream_returns_only_answer_not_hidden_reasoning(self):
        worker=AnswerWorker(config=dict(api_key='offline',base_url='https://opencode.ai/zen/go/v1'))
        results=[];draft=[];worker.completed.connect(results.append);worker.partial.connect(lambda ident,generation,text:draft.append(text))
        response=MagicMock(status_code=200)
        response.iter_lines.return_value=[('data: '+json.dumps(dict(choices=[dict(delta=d)]))).encode() for d in
            [dict(reasoning_content='HIDDEN_REASONING'),dict(content='happy|none|'),dict(content='咕嘎～这是程序之间的入口。')]]+[b'data: [DONE]']
        with patch('core.chat_answer.requests.post',return_value=response) as api:
            worker.start('offline-session',[],'接口是什么',effort='quick');self.pump(lambda:bool(results))
        self.assertTrue(results[0]['ok']);self.assertIn('咕嘎～这是程序之间的入口。',results[0]['text'])
        self.assertNotIn('HIDDEN_REASONING',str(draft));self.assertNotIn('tools',api.call_args.kwargs['json'])
        response.close.assert_called_once()

    def test_http_error_is_truthful_and_never_echoes_response_body(self):
        worker=AnswerWorker(config=dict(api_key='offline'));results=[];worker.completed.connect(results.append)
        response=MagicMock(status_code=429);response.text='DO_NOT_LEAK_PROVIDER_BODY'
        with patch('core.chat_answer.requests.post',return_value=response):
            worker.start('offline',[],'你好');self.pump(lambda:bool(results))
        self.assertFalse(results[0]['ok']);self.assertIn('429',results[0]['error']);self.assertNotIn('DO_NOT_LEAK',str(results))

    def test_cancel_ignores_late_stream_completion(self):
        entered=threading.Event();release=threading.Event()
        response=MagicMock(status_code=200)
        def lines(**kw):
            entered.set();release.wait(2);yield b'data: [DONE]'
        response.iter_lines.side_effect=lines
        worker=AnswerWorker(config=dict(api_key='offline'));results=[];worker.completed.connect(results.append)
        with patch('core.chat_answer.requests.post',return_value=response):
            worker.start('offline',[],'你好');self.assertTrue(entered.wait(1));worker.cancel();release.set();APP.processEvents()
            self.assertFalse(worker.active);self.assertEqual(len(results),1);self.assertFalse(results[0]['ok'])

    def test_short_voice_records_offline_and_does_not_start_realtime(self):
        recorder=MagicMock(available=True,error=None);recorder.stop.return_value='接口是什么'
        voice=ShortVoice(factory=lambda:recorder);results=[];states=[]
        voice.transcript.connect(results.append);voice.state.connect(states.append)
        voice.start();self.pump(lambda:'recording' in states);voice.stop();self.pump(lambda:bool(results))
        self.assertEqual(results,['接口是什么']);recorder.start.assert_called_once();recorder.stop.assert_called_once()

    def test_short_voice_cancel_discards_late_transcript(self):
        recorder=MagicMock(available=True,error=None);recorder.stop.return_value='不应发送'
        voice=ShortVoice(factory=lambda:recorder);results=[];states=[]
        voice.transcript.connect(results.append);voice.state.connect(states.append)
        voice.start();self.pump(lambda:'recording' in states);voice.stop(cancel=True);self.pump(lambda:not voice.active)
        self.assertEqual(results,[])

    def test_music_local_stop_phrases_do_not_trigger_on_song_mentions(self):
        self.assertTrue(is_stop_phrase('咕嘎 停止 唱歌'));self.assertTrue(is_stop_phrase('别唱了'))
        self.assertFalse(is_stop_phrase('晴天这首歌真好听'));self.assertFalse(is_stop_phrase('继续唱歌'))

    def test_stop_listener_gets_raw_pcm_while_cloud_echo_input_stays_gated(self):
        from core.realtime_agent import AgentRealtimeVoice
        voice=AgentRealtimeVoice();voice._cfg=dict(headphones=False);voice._external_playing=True
        voice._music_stop_listener=MagicMock();pcm=b'\x01\x01'*640
        voice._capture(pcm,640,None,None)
        voice._music_stop_listener.feed.assert_called_once_with(pcm)
        self.assertEqual(voice._input.get_nowait(),bytes(len(pcm)))


if __name__=='__main__':unittest.main()
