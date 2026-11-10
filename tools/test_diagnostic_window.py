# -*- coding: utf-8 -*-
"""诊断包必须带上失败任务时段的日志与 result.json（不能只取最近 30 分钟）。

单独运行：
    python tools\test_diagnostic_window.py
"""
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core import diagnostic_export as dx  # noqa: E402


class DiagnosticWindowTests(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='guga-diag-'))

    def test_task_result_forced_into_package(self):
        old = datetime.now() - timedelta(hours=5)
        folder = self.tmp / 'doubao-20260101'
        folder.mkdir()
        result = folder / 'result.json'
        result.write_text('{"code": "injection_failed"}', encoding='utf-8')
        stamp = old.timestamp()
        os.utime(str(result), (stamp, stamp))
        used, skipped = set(), []
        with patch.object(dx, '_evidence_candidates',
                          return_value=[('doubao_evidence', self.tmp)]):
            cutoff = dx._task_window_start(dict(recent=[dict(
                started=old.strftime('%Y-%m-%d %H:%M:%S'))]))
            rows, payloads = dx._collect_task_results(cutoff, used, skipped)
        self.assertTrue(rows, '任务时段内的 result.json 必须进包')
        self.assertIn('task-results/doubao_evidence/', rows[0]['arcname'])
        self.assertIn(b'injection_failed', payloads[0][1])

    def test_log_window_extended_to_task_start(self):
        log = self.tmp / 'adapter_chain.log'
        stamp = (datetime.now() - timedelta(minutes=90)).strftime('%Y-%m-%d %H:%M:%S')
        log.write_text('%s step_failed code=send_not_confirmed\n' % stamp,
                       encoding='utf-8')
        with patch.object(dx, '_log_source_paths', return_value=[log]):
            used, skipped = set(), []
            rows_default, _ = dx._collect_logs(30, used, skipped)
            self.assertFalse(rows_default, '30 分钟窗口内不应包含 90 分钟前的日志')
            used, skipped = set(), []
            rows_ext, payloads_ext = dx._collect_logs(
                30, used, skipped, task_since=datetime.now() - timedelta(hours=2))
        self.assertTrue(rows_ext, '任务时段窗口必须把 90 分钟前的失败日志带上')
        self.assertIn(b'send_not_confirmed', payloads_ext[0][1])


if __name__ == '__main__':
    unittest.main(verbosity=2)
