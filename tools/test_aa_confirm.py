# -*- coding: utf-8 -*-
"""20261110aa：发送确认结构判据 / 禁补发 / hint 话术闸 / 四类事件落盘。

覆盖：
  一、用户气泡计数（按指纹次数，不按整页字数）
  二、发送确认三信号优先级（user_bubble > input_cleared > send_button_state），字数不参与判定
  三、hint/失败卡片与聊天回复共用禁用话术闸（adapter 的 hint 通道）
  四、composer / inject / done / timeout 四类事件写进同一个 adapter_chain.log

单独运行：
    python tools\\test_aa_confirm.py
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core import adapter_chain, guga_paths, reply_guard, run_log  # noqa: E402
from core.adapters import doubao_adapter  # noqa: E402

PROMPT = '用豆包生成PPT提示词，PPT主题由你来定，再把生成的PPT提示词给work Buddy生成PPT'


def _word(text, y, x=0.1):
    return dict(text=text, x=x, y=y, w=0.6, h=0.03)


class BubbleHitTests(unittest.TestCase):
    """气泡判定按“本步正文指纹在对话区出现的次数”，不按整页字数。"""

    def _adapter(self):
        adapter = doubao_adapter.DoubaoAdapter.__new__(doubao_adapter.DoubaoAdapter)
        adapter._obs = lambda *a, **k: None
        return adapter

    def test_counts_bubbles_above_composer_only(self):
        adapter = self._adapter()
        words = [_word(PROMPT, 0.40), _word(PROMPT, 0.55), _word(PROMPT, 0.93)]
        head, _tail = adapter._fingerprint(PROMPT)
        count, _tail_hits, first_y = adapter._bubble_hits(words, PROMPT)
        self.assertEqual(head, doubao_adapter._key(PROMPT)[:14])
        self.assertEqual(count, 2)          # 输入框那条（y=0.93）不算
        self.assertEqual(first_y, 0.4)

    def test_no_bubble_is_zero(self):
        adapter = self._adapter()
        count, tail_hits, first_y = adapter._bubble_hits(
            [_word('豆包说：这是回答', 0.4)], PROMPT)
        self.assertEqual((count, tail_hits, first_y), (0, 0, None))


class ConfirmSignalTests(unittest.TestCase):
    """三信号任一强证据成立即确认；字数只作说明。"""

    def test_priority_user_bubble(self):
        ok, signal, _ = doubao_adapter.DoubaoAdapter._send_confirmation(dict(
            bubble_before=1, bubble_after=2, tail_after=2, composer_before=True,
            still_in_composer=False, button_state="stop", grew=-406))
        self.assertTrue(ok)
        self.assertEqual(signal, "user_bubble")

    def test_input_cleared_requires_prompt_present_before_send(self):
        ok, signal, _ = doubao_adapter.DoubaoAdapter._send_confirmation(dict(
            bubble_before=0, bubble_after=0, composer_before=False,
            still_in_composer=False, button_state="unknown", grew=0))
        self.assertFalse(ok)
        self.assertEqual(signal, "")

    def test_negative_chars_do_not_fail_when_bubble_new(self):
        ok, signal, detail = doubao_adapter.DoubaoAdapter._send_confirmation(dict(
            bubble_before=2, bubble_after=3, composer_before=True,
            still_in_composer=False, button_state="unknown", grew=-405))
        self.assertTrue(ok)
        self.assertEqual(signal, "user_bubble")
        self.assertIn("-405", detail)       # 只记录，不据此判失败


class HintGuardTests(unittest.TestCase):
    """失败卡片 / hint 与聊天回复共用禁用清单，不许把操作推回用户。"""

    OLD_HINT = ('文字已经打进去，但回车/点发送后没有出现新回合（页面字数停在 688，'
                '发送前基线 871）；多半是页面没在对话页或有弹窗挡住。'
                '到豆包窗口点一下输入框手动发一次；仍不行就先重启豆包再派单。')

    def test_old_hint_is_stripped(self):
        cleaned, hits = reply_guard.sanitize_hint(self.OLD_HINT)
        self.assertTrue(hits)
        self.assertEqual(reply_guard.banned_hits(cleaned), [])
        self.assertNotIn('手动发一次', cleaned)
        self.assertNotIn('点一下输入框', cleaned)

    def test_new_adapter_hint_is_clean(self):
        hint = doubao_adapter._send_unconfirmed_hint(dict(
            bubble_before=2, bubble_after=2, still_in_composer=True,
            button_state="unknown"))
        self.assertEqual(reply_guard.banned_hits(hint), [])
        self.assertIn('没有确认到', hint)
        self.assertIn('send_not_confirmed', hint)

    def test_chain_gate_sanitizes_hint(self):
        ok, code, hint = adapter_chain.gate(dict(
            ok=False, code="send_not_confirmed", hint=self.OLD_HINT))
        self.assertFalse(ok)
        self.assertEqual(code, "send_not_confirmed")
        self.assertEqual(reply_guard.banned_hits(hint), [])

    def test_all_adapter_hints_have_no_manual_push(self):
        """适配器里出现的 hint 文案（新写的这批）不得再带手动操作。"""
        texts = [
            doubao_adapter._send_unconfirmed_hint({}),
            "没找到豆包输入框；缺什么：一个可见的对话输入框。下一步：我会重新枚举控件再定位一次，仍找不到就报 input_not_found。",
            "写入后同源回读不一致；未确认。下一步：重新定位同一个控件再写一次，仍不一致就报 readback_mismatch。",
        ]
        for text in texts:
            self.assertEqual(reply_guard.banned_hits(text), [], text)

    #: 失败码映射里的历史 hint（线上卡片直接读这批文案）。
    LEGACY_HINTS = (
        '没找到输入框，请把豆包切到“对话”页并手动点一下输入框。',
        '粘贴后回读不一致，通常是焦点没在输入框；点一下输入框再重试。',
        '回复没复制出来，点一下回答正文后重试。',
        '装了豆包但没能打开窗口：手动启动一次，确认能打开并登录后再派。',
        '输入框回读与要发的正文不一致，已清空重试 3 次仍未通过校验，'
        '本次没有按回车发送；请点一下豆包输入框后重试。',
        '缺什么：滚动到底后的完整正文。下一步：把豆包窗口放大/手动滚到本轮回答末尾后重试。',
        '下一步：要求豆包“直接在对话里用纯文本输出全文”，或手动点开卡片复制正文后再派单。',
        '多半是页面没在对话页或有弹窗挡住。到豆包窗口点一下输入框手动发一次；仍不行就先重启豆包再派单。',
    )

    def test_legacy_hints_are_sanitized_clean(self):
        """历史 hint 过闸后不得残留任何禁用句式（adapter_chain.gate 走的就是这条）。"""
        for text in self.LEGACY_HINTS:
            cleaned, hits = reply_guard.sanitize_hint(text)
            self.assertTrue(hits, text)
            self.assertEqual(reply_guard.banned_hits(cleaned), [], cleaned)

    def test_adapter_failure_hint_is_clean_by_source(self):
        """input_verify_failed 这句源头已改成自查式，不依赖事后清洗。"""
        hint = ('输入框回读与要发的正文不一致（期望 105 字，回读 13 字），'
                '已清空重试 3 次仍未通过校验，本次没有按回车发送。'
                '下一步：我会重新定位同一个输入控件再写一次；仍对不上就停在这里'
                '报 input_verify_failed，不重复发送。')
        self.assertEqual(reply_guard.banned_hits(hint), [])
        self.assertIn('不重复发送', hint)


class ObservabilityTests(unittest.TestCase):
    """四类事件必须落在同一个 adapter_chain.log。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='guga-obs-'))
        self._old_runtime = guga_paths.RUNTIME
        guga_paths.RUNTIME = self.tmp

    def tearDown(self):
        guga_paths.RUNTIME = self._old_runtime

    def _lines(self):
        path = self.tmp / 'adapter_chain.log'
        self.assertTrue(path.is_file(), 'adapter_chain.log 没生成')
        return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]

    def test_four_events_same_file(self):
        run_log.emit('composer', stage='locate', ref='e97e34d1', attempts=2)
        run_log.emit('inject', stage='write', expected=105, got=105, attempts=1)
        run_log.emit('done', stage='wait', done_signal='stable_2s', elapsed_ms=18322)
        run_log.emit('timeout', stage='send_poll', detail='capture timeout')
        rows = self._lines()
        self.assertEqual([row['event'] for row in rows],
                         ['composer', 'inject', 'done', 'timeout'])
        self.assertEqual(rows[1]['expected'], 105)
        self.assertEqual(rows[2]['done_signal'], 'stable_2s')

    def test_adapter_obs_uses_same_file(self):
        adapter = doubao_adapter.DoubaoAdapter.__new__(doubao_adapter.DoubaoAdapter)
        adapter.tool = 'doubao'
        adapter._obs('composer', stage='locate', ref='e97e34d1b44636eaa49c',
                     attempts=2, expected=105, got=105)
        adapter._obs('inject', stage='write', ref='e97e34d1b44636eaa49c',
                     expected=105, got=105, attempts=1, matched=True)
        adapter._obs('done', stage='wait', done_signal='stop_button_gone',
                     elapsed_ms=12000)
        adapter._obs('timeout', stage='poll', detail='13.0s')
        rows = self._lines()
        self.assertEqual(len(rows), 4)
        self.assertEqual(rows[0]['ref'], 'e97e34d1b44636eaa49c')
        self.assertEqual(rows[1]['tool'], 'doubao')
        self.assertEqual(rows[2]['done_signal'], 'stop_button_gone')

    def test_chain_log_and_adapter_obs_share_file(self):
        adapter_chain._log('step_prompt', step=1, total=2, prompt_chars=105)
        adapter = doubao_adapter.DoubaoAdapter.__new__(doubao_adapter.DoubaoAdapter)
        adapter.tool = 'doubao'
        adapter._obs('inject', stage='write', expected=105, got=105, attempts=1)
        rows = self._lines()
        self.assertEqual([row['event'] for row in rows], ['step_prompt', 'inject'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
