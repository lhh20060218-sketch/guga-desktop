# -*- coding: utf-8 -*-
"""单测：技能/模式污染防护（豆包 / WorkBuddy / JoyCode 共用一套判定）。

现场来源（20261110u 真机 e2e）：豆包输入框挂着「帮我写作 ×」技能标签，
正文注入与回读都对（expected_len=45 / got_len=45），但提交后被渲染成
“生成图片：…”，页面显示“正在生成图片”，文字量不增反降（grew=-66），
旧实现只看字数 → 连续重试三次后误报 send_not_confirmed。

全部用 mock，不启动任何第三方软件、不碰真实剪贴板、不做界面自动化。
单独执行：python tools/test_paste_mode_guard.py
"""
import os
import sys
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core import paste_verify  # noqa: E402
from core.paste_verify import (  # noqa: E402
    chip_label, ensure_plain_mode, input_verified, sent_mode_check)


class MockClipboard:
    def __init__(self, text='用户原来复制的内容'):
        self.text = text

    def save(self):
        return self

    def restore(self):
        return True

    def read_text(self):
        return self.text

    def write_text(self, text):
        self.text = str(text)
        return True


class FakeClip:
    """input_verified 只用到 read_text / write_text。"""

    def __init__(self, text=''):
        self.text = text

    def read_text(self):
        return self.text

    def write_text(self, text):
        self.text = str(text)
        return True


class ChipDriver:
    """模拟挂着技能标签的输入框；removable=False 表示点不掉。"""

    def __init__(self, chip='帮我写作', removable=True, clip=None):
        self.chip = chip
        self.removable = removable
        self.clip = clip or FakeClip()
        self.composer = ''
        self.clear_calls = 0
        self.write_calls = 0
        self.clear_mode_calls = 0

    def mode(self):
        if not self.chip:
            return dict(plain=True, label='')
        return dict(plain=False, label=self.chip)

    def clear_mode(self, label=''):
        self.clear_mode_calls += 1
        if not self.removable:
            raise RuntimeError('点不到关闭按钮')
        self.chip = ''

    def clear(self):
        self.clear_calls += 1
        self.composer = ''

    def write(self, text):
        self.write_calls += 1
        self.composer = str(text)

    def read(self):
        return self.composer


class ChipDetectionTests(unittest.TestCase):
    def test_chip_needs_close_marker(self):
        # 常驻快捷栏（对话 / PPT 生成 / 图像生成…）没有 ×，不能算激活
        self.assertEqual(chip_label('对话    PPT 生成    图像生成    帮我写作    更多'), '')
        self.assertEqual(chip_label('帮我写作 ×'), '帮我写作')
        self.assertEqual(chip_label('图像生成 ✕'), '图像生成')

    def test_wrong_mode_marker(self):
        self.assertEqual(sent_mode_check('豆包正在生成图片')['code'], 'wrong_skill')
        self.assertTrue(sent_mode_check('正在生成幻灯片，请稍候')['marker'])
        self.assertTrue(sent_mode_check('普通回答正文')['ok'])


class InputModeGuardTests(unittest.TestCase):
    def test_chip_removed_then_send_ok(self):
        driver = ChipDriver('帮我写作', removable=True)
        logs = []
        result = input_verified('生成PPT提示词，主题由你来定。', driver,
                                clipboard=MockClipboard(),
                                log=lambda tag, payload: logs.append((tag, payload)))
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['mode']['changed'], True)
        self.assertEqual(driver.clear_mode_calls, 1)
        self.assertEqual(driver.chip, '')                 # 移除后回读确认已回普通态
        self.assertEqual(driver.write_calls, 1)           # 普通态下正常发送
        self.assertEqual(driver.composer, '生成PPT提示词，主题由你来定。')
        self.assertIn('mode_guard', [row[0] for row in logs])

    def test_chip_stuck_blocks_send(self):
        driver = ChipDriver('帮我写作', removable=False)
        result = input_verified('生成PPT提示词，主题由你来定。', driver,
                                clipboard=MockClipboard())
        self.assertFalse(result['ok'])
        self.assertEqual(result['code'], 'skill_chip_present')
        self.assertEqual(result['attempts'], 0)
        self.assertEqual(driver.write_calls, 0)           # 零发送
        self.assertEqual(driver.clear_calls, 0)           # 连清空都不做
        self.assertIn('帮我写作', result['missing'])
        self.assertIn('不是 OCR 问题', result['missing'])

    def test_plain_mode_untouched(self):
        driver = ChipDriver(chip='', removable=True)
        result = input_verified('随便一句', driver, clipboard=MockClipboard())
        self.assertTrue(result['ok'], result)
        self.assertEqual(driver.clear_mode_calls, 0)

    def test_ensure_plain_mode_without_probe(self):
        class NoProbe:
            def clear(self):
                pass

            def write(self, text):
                pass

            def read(self):
                return ''

        self.assertTrue(ensure_plain_mode(NoProbe())['ok'])


class WorkBuddyNoRetryTests(unittest.TestCase):
    """发送后出现“正在生成图片”：判 wrong_skill，只按一次回车、不重试。"""

    def test_wrong_skill_single_attempt(self):
        from core import workbuddy_bridge as wb

        keys = []
        state = {'attempts': 0}

        def fake_input_verified(text, driver, attempts=3, log=None):
            state['attempts'] += 1
            return dict(ok=True, code='', attempts=1, records=[], conflicts=0, text=text)

        with mock.patch.object(wb, '_uia_focus', lambda hwnd: object()), \
                mock.patch.object(wb, '_uia_value', lambda bridge: wb._SENTINEL), \
                mock.patch.object(wb, '_paste', lambda hwnd, text, cancel: True), \
                mock.patch.object(wb, 'input_verified', fake_input_verified), \
                mock.patch.object(wb, 'ensure_plain_mode', lambda driver, log=None: dict(ok=True, mode='plain')), \
                mock.patch('core.computer_control._send_keys',
                           lambda keys_: keys.append(list(keys_))), \
                mock.patch.object(wb, '_grab', lambda hwnd: '豆包正在生成图片'), \
                mock.patch.object(wb, '_composer_state', lambda hwnd, target, bridge: 'holds_prompt'), \
                mock.patch.object(wb, '_artifact_sig', lambda: 'sig'), \
                mock.patch.object(wb, '_copy_page', lambda hwnd: ''), \
                mock.patch.object(wb, '_log', lambda *a, **k: None):
            page, _sent_at, meta = wb._submit_locked(1, '把这段提示词做成 PPT', None, attempts=3)

        self.assertEqual(meta['error'], 'wrong_skill')
        self.assertIn('正在生成图片', meta['missing'])
        self.assertEqual(meta['wrong_marker'], '正在生成图片')
        self.assertEqual(keys.count([13]), 1)             # 只按一次回车
        self.assertEqual(state['attempts'], 1)            # 没有第二次尝试


class DoubaoHookTests(unittest.TestCase):
    """豆包：等待回答时走共用 sent_mode_check，遇到生图回合立刻判 wrong_skill。"""

    def test_doubao_uses_shared_hook(self):
        from core.adapters import doubao_adapter as da

        adapter = object.__new__(da.DoubaoAdapter)
        adapter._decl = lambda *args, **kwargs: kwargs.get('default')
        adapter._capture_words = lambda hwnd, path=None: (None, [], '豆包正在生成图片')
        adapter._generating = lambda words, text: False
        calls = []
        real = da.sent_mode_check

        def recorder(page_text, log=None):
            calls.append(page_text)
            return real(page_text, log=log)

        with mock.patch.object(da, 'sent_mode_check', recorder):
            result = adapter._wait_done(1, '提示词', 5, __import__('pathlib').Path('.'), lambda *a, **k: None)

        self.assertTrue(calls, '豆包的等待回合没有调用共用钩子')
        self.assertEqual(result['code'], 'wrong_skill')
        self.assertEqual(result['next_action'], '移除技能标签后重派')


class JoyCodeHookTests(unittest.TestCase):
    """JoyCode：发送后同样走共用钩子，命中就直接抛 wrong_skill（不回车上重试）。"""

    def test_joycode_uses_shared_hook(self):
        from core.adapters import joycode_ui as ju

        class DummyGuard:
            def __enter__(self):
                return None

            def __exit__(self, *exc):
                return False

        ui = object.__new__(ju.JoyCodeUI)
        ui._hwnd = 1
        ui._check_cancel = lambda: None
        ui.focus_composer = lambda: dict(point=(0.5, 0.9), page='chat', focus=dict(chars=0))
        ui._clear_composer = lambda: dict(clean=True, rounds=1)
        ui._read_composer = lambda: ''
        ui._clear_clipboard = lambda: None
        ui._act = lambda *a, **k: None
        ui._visible_fresh = lambda *a, **k: False
        ui._panel_text = lambda: '正在生成图片'
        calls = []
        real = ju.sent_mode_check

        def recorder(page_text, log=None):
            calls.append(page_text)
            return real(page_text, log=log)

        with mock.patch.object(ju, '_ClipboardGuard', DummyGuard), \
                mock.patch.object(ju, 'input_verified',
                                  lambda *a, **k: dict(ok=True, code='', text='命令',
                                                       records=[], conflicts=0, attempts=1)), \
                mock.patch.object(ju, 'sent_mode_check', recorder), \
                mock.patch.object(ju, '_log', lambda *a, **k: None):
            with self.assertRaises(ju.JoyCodeUIError) as ctx:
                ui.submit_command('执行本轮任务')

        self.assertTrue(calls, 'JoyCode 的发送确认没有调用共用钩子')
        self.assertEqual(ctx.exception.code, 'wrong_skill')
        self.assertIn('移除技能标签', ctx.exception.detail.get('next_action', ''))


class EmitCompatTests(unittest.TestCase):
    """20261110v 真机现场：豆包侧日志回调是 step(name, **fields)，_emit 用位置参调用
    → TypeError 被静默吞掉，mode_guard 一条都没落盘。"""

    def setUp(self):
        paste_verify.EMIT_ERRORS.clear()

    def test_mode_guard_lands_on_step_style_logger(self):
        events = []

        def step(name, **fields):
            events.append((name, fields))

        ensure_plain_mode(ChipDriver(chip='', removable=True), log=step)
        names = [name for name, _fields in events]
        self.assertIn('mode_guard', names)
        row = dict(events)['mode_guard']
        for key in ('ok', 'code', 'mode', 'label', 'changed', 'missing'):
            self.assertIn(key, row)

    def test_input_guard_lands_on_step_style_logger(self):
        events = []

        def step(name, **fields):
            events.append((name, fields))

        result = input_verified('随便一句', ChipDriver(chip='', removable=True),
                                clipboard=MockClipboard(), log=step)
        self.assertTrue(result['ok'], result)
        names = [name for name, _fields in events]
        self.assertIn('mode_guard', names)
        self.assertIn('input_guard', names)

    def test_log_failure_is_recorded_not_silent(self):
        def broken(*args, **kwargs):
            raise RuntimeError('日志文件被占用')

        ensure_plain_mode(ChipDriver(chip='', removable=True), log=broken)
        self.assertTrue(paste_verify.EMIT_ERRORS)
        self.assertEqual(paste_verify.EMIT_ERRORS[-1]['tag'], 'mode_guard')
        self.assertIn('日志文件被占用', paste_verify.EMIT_ERRORS[-1]['errors'][0])


if __name__ == '__main__':
    unittest.main(verbosity=2)
