# -*- coding: utf-8 -*-
"""单测：共用输入层「清空 → 粘贴 → 回读 → 重试 → 恢复剪贴板」。

全部用 mock，不启动任何第三方软件、不碰真实剪贴板、不做界面自动化。
单独执行：python tools/test_input_guard.py
"""
import os
import sys
import threading
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.paste_verify import input_verified  # noqa: E402

USER_CLIP = '用户原来复制的内容'


class MockClipboard:
    """模拟系统剪贴板：记录快照/恢复次数，便于断言用户数据不丢。"""

    def __init__(self, text=USER_CLIP):
        self.text = text
        self.saved = None
        self.restores = 0

    def save(self):
        self.saved = self.text
        return self

    def restore(self):
        self.text = self.saved if self.saved is not None else self.text
        self.restores += 1
        return True

    def read_text(self):
        return self.text

    def write_text(self, text):
        self.text = str(text)
        return True

    def __enter__(self):
        return self.save()

    def __exit__(self, *exc):
        self.restore()
        return False


class FakeDriver:
    """模拟输入框：粘贴时从剪贴板取内容。"""

    def __init__(self, clipboard, composer='', truncate=None, clear_after=0,
                 clipboard_hijack=None):
        self.clip = clipboard
        self.composer = composer
        self.truncate = truncate              # 只粘进前 N 字
        self.clear_after = clear_after        # 第 N 次 clear 才真正清空
        self.clipboard_hijack = clipboard_hijack
        self.clear_calls = 0
        self.write_calls = 0

    def clear(self):
        self.clear_calls += 1
        if self.clear_calls > self.clear_after:
            self.composer = ''

    def write(self, text):
        self.write_calls += 1
        if self.clipboard_hijack:
            self.clip.text = self.clipboard_hijack
            self.composer = self.clipboard_hijack
            return
        value = self.clip.read_text()
        self.composer = value[:self.truncate] if self.truncate else value

    def read(self):
        return self.composer


class InputVerifiedTests(unittest.TestCase):
    def test_exact_match_succeeds_first_attempt(self):
        clip = MockClipboard()
        driver = FakeDriver(clip, composer='上一步残留的文字')
        expected = '请生成 16 页 PPT，主题 OWASP Top 10，包含封面、目录、逐页要点与总结。'
        result = input_verified(expected, driver, clipboard=clip)
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['attempts'], 1)
        self.assertEqual(driver.clear_calls, 1)          # 先清空
        self.assertEqual(driver.composer, expected)      # 再粘贴
        self.assertEqual(clip.text, USER_CLIP)           # 用户剪贴板已恢复

    def test_half_paste_is_retried_until_match(self):
        clip = MockClipboard()
        expected = '第一段正文；第二段正文；第三段正文；第四段正文；第五段正文。'
        driver = FakeDriver(clip)
        writes = {'n': 0}

        def flaky_write(text):
            writes['n'] += 1
            driver.write_calls += 1
            driver.composer = clip.read_text()[:len(text) // 2] if writes['n'] < 3 else clip.read_text()

        driver.write = flaky_write
        result = input_verified(expected, driver, clipboard=clip)
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['attempts'], 3)
        self.assertEqual(driver.composer, expected)
        self.assertEqual(result['records'][0]['got_len'], len(expected) // 2)
        self.assertIn('head_diff', result['records'][0])
        self.assertEqual(clip.text, USER_CLIP)

    def test_residue_in_composer_is_not_pasted_over(self):
        clip = MockClipboard()
        expected = '本步要求：写一份周报，说明本周完成项与下周计划。'
        driver = FakeDriver(clip, composer='上一次没发出去的残留', clear_after=1)
        result = input_verified(expected, driver, clipboard=clip)
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['attempts'], 2)
        self.assertFalse(result['records'][0]['cleared'])
        self.assertIn('残留', result['records'][0]['detail'])
        self.assertEqual(driver.composer, expected)

    def test_three_failures_report_input_verify_failed(self):
        clip = MockClipboard()
        expected = '必须原样发出去的正文，不能被截断成半截。'
        driver = FakeDriver(clip, truncate=6)
        result = input_verified(expected, driver, clipboard=clip)
        self.assertFalse(result['ok'])
        self.assertEqual(result['code'], 'input_verify_failed')
        self.assertEqual(result['attempts'], 3)
        self.assertIn('期望 %d 字' % len(expected), result['missing'])
        self.assertIn('期望“', result['missing'])
        self.assertEqual(clip.text, USER_CLIP)           # 失败也要恢复用户剪贴板

    def test_clipboard_changed_by_third_party_reports_conflict(self):
        clip = MockClipboard()
        expected = '本步要粘贴的完整正文，任何字符都不能错。'
        driver = FakeDriver(clip, clipboard_hijack='用户临时复制的新内容')
        result = input_verified(expected, driver, clipboard=clip)
        self.assertFalse(result['ok'])
        self.assertEqual(result['code'], 'clipboard_conflict')
        self.assertEqual(result['conflicts'], 3)
        self.assertTrue(all(item.get('conflict') for item in result['records']))
        self.assertEqual(clip.text, USER_CLIP)           # 最终恢复用户原剪贴板
        self.assertEqual(clip.restores, 1)

    def test_newline_normalization(self):
        from core.paste_verify import normalize
        self.assertEqual(normalize('a\r\nb   \r\nc\r\n'), 'a\nb\nc')
        self.assertEqual(normalize('\ufeff第一行\u200b\n第二行'), '第一行\n第二行')
        clip = MockClipboard()
        expected = '第一行\n第二行\n第三行'
        driver = FakeDriver(clip)
        result = input_verified(expected, driver, clipboard=clip)
        self.assertTrue(result['ok'], result)

    def test_empty_expected_is_rejected_without_paste(self):
        clip = MockClipboard()
        driver = FakeDriver(clip)
        result = input_verified('   ', driver, clipboard=clip)
        self.assertFalse(result['ok'])
        self.assertEqual(result['code'], 'input_verify_failed')
        self.assertEqual(driver.write_calls, 0)
        self.assertEqual(clip.text, USER_CLIP)


class PauseGateTests(unittest.TestCase):
    """接入 paste_verify 后，「暂停状态下不许输入/点击」仍然生效。"""

    def setUp(self):
        from core import control_session, input_guard
        self.guard = input_guard
        self.session = control_session.session
        self.guard.reset()
        self.session.clear()
        self.session.begin(app='test', step='paste', total=1)

    def tearDown(self):
        self.session.clear()
        self.guard.reset()

    def test_stop_aborts_before_any_input(self):
        clip = MockClipboard()
        driver = FakeDriver(clip)
        self.session.request_stop('user')
        with self.assertRaises(self.guard.Stopped):
            input_verified('本步要发的正文，中止后一个事件都不许发。', driver, clipboard=clip)
        self.assertEqual(driver.clear_calls, 0)
        self.assertEqual(driver.write_calls, 0)
        self.assertEqual(clip.restores, 1)

    def test_pause_holds_every_input_until_resume(self):
        clip = MockClipboard()
        driver = FakeDriver(clip)
        resumed = threading.Event()
        seen = []
        real_clear = driver.clear

        def clear():
            seen.append(resumed.is_set())
            real_clear()

        driver.clear = clear
        self.assertTrue(self.guard.pause('用户叫停'))
        timer = threading.Timer(0.4, lambda: (self.guard.resume(), resumed.set()))
        timer.start()
        try:
            result = input_verified('暂停期间一个键鼠事件都不许发，恢复后才允许粘贴。',
                                    driver, clipboard=clip)
        finally:
            timer.cancel()
        self.assertTrue(result['ok'], result)
        self.assertEqual(seen, [True])        # 清空/粘贴只发生在恢复之后
        self.assertEqual(clip.text, USER_CLIP)

    def test_pyautogui_wrapper_still_gates_input(self):
        class FakePyAutoGUI:
            def __init__(self):
                self.calls = 0

            def click(self, *args, **kwargs):
                self.calls += 1

            def write(self, message, *args, **kwargs):
                self.calls += len(str(message))

        module = FakePyAutoGUI()
        self.assertTrue(self.guard.install_pyautogui(module))
        module.click()
        module.write('ab')
        self.assertEqual(module.calls, 3)
        self.session.request_stop('user')
        with self.assertRaises(self.guard.Stopped):
            module.click()
        self.assertEqual(module.calls, 3)     # 中止后一个事件都不再发
        self.session.begin(app='test', step='typing', total=1)
        self.session.request_stop('user')
        with self.assertRaises(self.guard.Stopped):
            module.write('cd')
        self.assertEqual(module.calls, 3)


if __name__ == '__main__':
    unittest.main(verbosity=2)
