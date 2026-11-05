import unittest
from unittest.mock import patch
from pathlib import Path
from core.fast_commands import match,execute
from core.wechat_demo import phrase_boxes,is_self_message_request
from core.execution_contract import ExecutionLedger

class DemoTests(unittest.TestCase):
    def test_discussing_failed_send_never_triggers_direct_send(self):
        self.assertFalse(is_self_message_request('为什么给文件传输助手发送失败'))
        self.assertFalse(is_self_message_request('文件传输助手发送失败了，检查原因'))
        self.assertTrue(is_self_message_request('帮我给文件传输助手发一段自我介绍'))
    def test_default_browser_beats_installed_edge(self):
        with patch('core.browser_launch.default_executable',return_value=Path('C:/Doubao.exe')),patch('core.fast_commands.subprocess.Popen') as launch:
            result=execute(match('打开浏览器'))
        self.assertTrue(result['ok']);self.assertFalse(result['verified_running'])
        self.assertEqual(launch.call_args.args[0],[str(Path('C:/Doubao.exe')),'about:blank'])
    def test_compound_search_keeps_query_and_requests_report(self):
        command=match('打开默认浏览器搜索量子计算，并汇报结果')
        self.assertTrue(command['matched']);self.assertEqual(command['report_query'],'量子计算')
    def test_plain_typing_is_not_misrouted_to_search(self):
        self.assertFalse(match('打开浏览器输入一段自我介绍')['matched'])
    def test_browser_close_is_a_local_fast_command(self):
        command=match('关闭浏览器')
        self.assertTrue(command['matched'])
        self.assertEqual(command['action'],'close_browser')
        self.assertEqual(command['priority'],'fast')
    def test_singing_only_on_request_defaults_to_qingtian(self):
        self.assertEqual(match('唱歌')['target'],'晴天')
        self.assertFalse(match('我觉得晴天很好听')['matched'])
        self.assertEqual(match('暂停唱歌')['kind'],'music_pause')
        self.assertEqual(match('继续唱歌')['kind'],'music_resume')
    def test_gestures_are_local_without_model(self):
        self.assertFalse(match('转圈')['matched'])
        self.assertEqual(match('比心')['target'],'idle_heart')
        self.assertEqual(match('困倦打盹')['target'],'idle_doze')
        self.assertEqual(match('暗中观察')['target'],'sneak_peek')
    def test_chinese_ocr_single_char_words_and_bounds(self):
        ocr=dict(lines=[dict(words=[dict(text='发',x=20,y=30,width=12,height=15),dict(text='送',x=33,y=30,width=12,height=15)])])
        boxes=phrase_boxes(ocr,'发送');self.assertEqual(len(boxes),1)
        self.assertEqual(boxes[0]['width'],25)
        self.assertEqual(phrase_boxes(ocr,'接收人'),[])
    def test_failed_send_cannot_pass_completion_gate(self):
        ledger=ExecutionLedger();ledger.record('wechat_send_self',{},dict(ok=False,error='未找到对象'))
        self.assertTrue(ledger.blockers())
        ledger.record('wechat_send_self',{},dict(ok=True,verified_message_visible=True))
        self.assertFalse(ledger.blockers())
if __name__=='__main__':unittest.main()
