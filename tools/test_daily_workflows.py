import json,os,subprocess,sys,tempfile,threading,time,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from core.daily_workflows import workflow_for
from core.media_workflow import MediaWorkflow,ffmpeg_path,inspect_video,validate_srt
from core.task_speech import TaskSpeechQueue


class PolicyTests(unittest.TestCase):
    def test_important_voice_notice_survives_user_barge_in(self):
        from core.realtime_agent import AgentRealtimeVoice
        from unittest.mock import patch
        voice=AgentRealtimeVoice();voice._user_speaking=True
        with patch.object(voice,'_send'):
            voice.notify_battleground('important','字幕已经生成，接下来预览成片。',during_task=True,persistent=True)
            voice._process_command(voice._commands.get_nowait())
            self.assertEqual(len(voice._notices),1)
            voice.interrupt();self.assertEqual(len(voice._notices),1)
            voice.clear_task_notices();self.assertFalse(voice._notices)
    def test_queued_important_notice_survives_epoch_but_not_task_cancellation(self):
        from core.realtime_agent import AgentRealtimeVoice
        from unittest.mock import patch
        voice=AgentRealtimeVoice();voice._user_speaking=True
        with patch.object(voice,'_send'):
            voice.notify_battleground('first','下载完成',during_task=True,persistent=True)
            pending=voice._commands.get_nowait();voice.interrupt();voice._process_command(pending)
            self.assertEqual(len(voice._notices),1)
            voice.notify_battleground('second','转写完成',during_task=True,persistent=True)
            pending=voice._commands.get_nowait();voice.clear_task_notices();voice._process_command(pending)
            self.assertFalse(voice._notices)
    def test_short_upload_command_expands_to_full_user_workflow(self):
        flow=workflow_for('帮我上传视频')
        self.assertEqual(flow['id'],'meeting-to-bilibili')
        self.assertTrue(flow['defaults']['publish_confirmation'])
        self.assertIn('底部时间进度条',flow['instructions']);self.assertIn('needs_input',flow['instructions'])
    def test_workflow_questions_do_not_grant_execution(self):
        self.assertIsNone(workflow_for('如何上传视频'))
        self.assertIsNone(workflow_for('上传视频的流程是什么'))
    def test_independent_review_requires_evidence_and_a_bounded_round(self):
        flow=workflow_for('帮我验收这个项目，再给workbuddy下一步计划')
        self.assertEqual(flow['id'],'agent-project-review');self.assertIn('真实操作',flow['instructions'])
        self.assertIn('单次只做一轮',flow['instructions'])
    def test_task_speech_is_sparse_and_does_not_interrupt(self):
        now=[0.];q=TaskSpeechQueue(lambda:now[0])
        q.offer('start','任务开始');self.assertIsNotNone(q.next())
        q.offer('step','文件已下载');self.assertIsNone(q.next())
        q.offer('ask','需要选择哪一段录制？',True)
        now[0]=11.;self.assertIsNone(q.next(busy=True));self.assertIn('选择',q.next()['text'])
        self.assertFalse(q.offer('ask','重复问题',True))
        q.offer('later','完成转写');now[0]=72.;self.assertIsNotNone(q.next())
    def test_critical_result_replaces_stale_progress(self):
        q=TaskSpeechQueue();q.offer('p','正在下载');q.offer('d','成片待验收',True)
        self.assertEqual(len(q.pending),1);self.assertEqual(q.next()['key'],'d')


class RealMediaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder=ROOT/'runtime/video-workflow-qa'/time.strftime('%Y%m%d-%H%M%S');cls.folder.mkdir(parents=True)
        cls.source=cls.folder/'test-original.mp4';cls.srt=cls.folder/'test-zh.srt'
        subprocess.run([ffmpeg_path(),'-v','error','-nostdin','-y','-f','lavfi','-i','color=c=0x384050:s=640x360:r=10:d=3',
                        '-f','lavfi','-i','sine=frequency=440:duration=3','-c:v','libx264','-threads','2','-c:a','aac','-shortest',str(cls.source)],
                       check=True,timeout=30,creationflags=subprocess.CREATE_NO_WINDOW)
        cls.srt.write_text('1\n00:00:00,200 --> 00:00:02,800\n咕嘎视频验收：中文字幕与时间进度条\n',encoding='utf-8')
    def test_reject_fake_or_out_of_range_subtitles(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'bad.srt';path.write_text('这不是同步字幕',encoding='utf-8')
            with self.assertRaises(ValueError):validate_srt(path,3)
            path.write_text('1\n00:00:00,000 --> 00:00:30,000\n超时',encoding='utf-8')
            with self.assertRaises(ValueError):validate_srt(path,3)
    def test_real_render_progress_bar_subtitles_and_submission_manifest(self):
        pipeline=MediaWorkflow(self.folder/'jobs');before=self.source.read_bytes()
        accepted=pipeline.execute(dict(action='render',path=str(self.source),subtitles=str(self.srt)),threading.Event())
        self.assertTrue(accepted['accepted']);pipeline.thread.join(45)
        if pipeline.thread.is_alive():pipeline.stop();pipeline.thread.join(5)
        state=pipeline.status();self.assertEqual(state['state'],'ready',state)
        self.assertEqual(before,self.source.read_bytes());self.assertLess(abs(inspect_video(state['output'])['seconds']-3),.2)
        frame=self.folder/'preview.png'
        subprocess.run([ffmpeg_path(),'-v','error','-y','-ss','1.5','-i',state['output'],'-frames:v','1',str(frame)],check=True,timeout=20,creationflags=subprocess.CREATE_NO_WINDOW)
        from PIL import Image
        with Image.open(frame) as im:
            left=im.getpixel((100,356));right=im.getpixel((550,356))
            self.assertGreater(left[2]-right[2],100)
        manifest=pipeline.execute(dict(action='submission',title='咕嘎视频处理验收',description='三秒合成测试，非真实会议录制'))
        self.assertEqual(manifest['state'],'prepared_not_uploaded');self.assertTrue(manifest['publish_requires_confirmation'])
        (self.folder/'result.json').write_text(json.dumps(dict(ok=True,output=state['output'],preview=str(frame),source_unchanged=True,
             progress_bar_pixels_verified=True,submission_state=manifest['state']),ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__':unittest.main()
