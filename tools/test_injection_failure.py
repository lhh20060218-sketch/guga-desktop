# -*- coding: utf-8 -*-
"""注入层签名不匹配必须结构化：injection_failed / stage=inject / 四段式气泡。

现场：``ArgumentError: argument 2: TypeError: expected LP_INPUT instance
instead of INPUT_Array_122``（61 字符 × 2 次按键 = 122 元素数组）。
过去被外层 ``except Exception`` 兜成“未归类异常”，气泡没有失败码/阶段/原文。

单独运行：
    python tools\test_injection_failure.py
"""
import ctypes
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.agent_failure import explain_failure  # noqa: E402
from core.failure_report import classify_exception  # noqa: E402

SITE_MESSAGE = ('argument 2: TypeError: expected LP_INPUT instance '
                'instead of INPUT_Array_122')


def _last_tool_failure(exc):
    """与 self_agent 写入 journal 的字段保持一致。"""
    info = classify_exception(exc)
    return dict(tool='computer', action='type', code=info.get('code'),
                raw_code='', stage=info.get('stage'), raw=info.get('raw'),
                next_action=info.get('next_action'), app='',
                exception_type=type(exc).__name__, error=info.get('raw') or str(exc))


class InjectionFailureTests(unittest.TestCase):

    def test_argument_error_is_classified(self):
        info = classify_exception(ctypes.ArgumentError(SITE_MESSAGE))
        self.assertEqual(info.get('code'), 'injection_failed')
        self.assertEqual(info.get('stage'), 'inject')
        self.assertIn('expected LP_INPUT instance', info.get('raw') or '')

    def test_type_error_signature_mismatch_is_classified(self):
        info = classify_exception(TypeError(SITE_MESSAGE))
        self.assertEqual(info.get('code'), 'injection_failed')
        self.assertEqual(info.get('stage'), 'inject')

    def test_unrelated_exception_stays_unclassified(self):
        self.assertEqual(classify_exception(ValueError('普通参数错误')), {})

    def test_full_explain_failure_chain(self):
        exc = ctypes.ArgumentError(SITE_MESSAGE)
        text = explain_failure(None, operations=1,
                               last_tool_failure=_last_tool_failure(exc))
        self.assertIn('injection_failed', text)
        self.assertIn('stage=inject', text.replace('【阶段】', 'stage='))
        self.assertIn('expected LP_INPUT instance', text)
        self.assertIn('INPUT_Array_122', text)
        self.assertIn('输入框', text)
        self.assertIn('重试注入', text)
        self.assertNotIn('未归类', text)
        self.assertNotIn('执行器没有提供明确原因', text)


if __name__ == '__main__':
    unittest.main(verbosity=2)
