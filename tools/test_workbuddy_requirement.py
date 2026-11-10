# -*- coding: utf-8 -*-
"""回归：第 2 步提示词必须整段进“要求”，不能被末段指令顶掉。

现场（20261110s4，19:58）：
    2345 字提问在聊天输入框里回读一致并发出，但 WorkBuddy 的 PPT 流程只取到
    末段“生成PPT + 两条规则”，生成的是无关的「本周工作复盘」8 页。

单独执行：python tools/test_workbuddy_requirement.py
"""
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core import adapter_chain  # noqa: E402
from core import workbuddy_bridge  # noqa: E402

DOUBAO = """## PPT 生成提示词
**主题**：OWASP Top 10（2025）视角下的 Web 漏洞挖掘入门——以 SRC 授权测试为例
**基本信息**：共 16 页，16:9，中文。
**P1 封面**
主标题“OWASP Top 10（2025）视角下的 Web 漏洞挖掘入门”。
**P9 跨站脚本 XSS**
反射型、存储型、DOM 型三类的触发路径差异。"""


class PromptForPptTests(unittest.TestCase):
    def test_ppt_step_keeps_body_inside_requirement(self):
        step = {'instruction': '生成PPT', 'index': 2}
        prompt = adapter_chain._prompt_for(step, {'name': '豆包', 'text': DOUBAO})
        self.assertIn('OWASP Top 10', prompt)          # 正文整段在要求里
        self.assertIn('16 页', prompt)
        self.assertNotIn('以下是上一步', prompt)        # 不再把正文标成“参考资料”
        self.assertNotIn('本步要求：', prompt)          # 不再留可被单独取走的末段
        self.assertTrue(prompt.startswith('请严格按下面这份 PPT 提示词产出 PPT'))
        self.assertTrue(prompt.endswith('不要执行与本步无关的操作。'))
        # 不许有空行把正文切成另一段（PPT 流程按段落取要求）
        self.assertNotIn('\n\n', prompt)

    def test_non_ppt_step_keeps_body_inside_requirement(self):
        step = {'instruction': '写一份周报', 'index': 2}
        prompt = adapter_chain._prompt_for(
            step, {'name': '豆包', 'text': '本周完成了接口联调与回归测试，剩余一个兼容性问题待修。'})
        self.assertIn('以下是上一步（豆包）交付的正文', prompt)
        self.assertIn('本步要求：写一份周报', prompt)
        # 正文必须位于“本步要求”之后、同一条要求内部，不能是可被单独取走的末段。
        self.assertLess(prompt.index('以下是上一步'), prompt.index('本周完成了接口联调'))
        self.assertTrue(prompt.endswith('也不要执行与本步无关的操作。）'))


class ProofTokenTests(unittest.TestCase):
    def test_tokens_come_from_body_not_wrapper(self):
        prompt = adapter_chain._prompt_for({'instruction': '生成PPT'},
                                           {'name': '豆包', 'text': DOUBAO})
        tokens = workbuddy_bridge._proof_tokens(prompt)
        self.assertIn('OWASP', tokens)
        self.assertNotIn('PPT', tokens)
        self.assertFalse(any('本步要求' in token for token in tokens))

    def test_proof_hit(self):
        tokens = ['OWASP', '跨站脚本']
        self.assertEqual(workbuddy_bridge._proof_in('封面 OWASP Top 10', tokens), 'OWASP')
        self.assertEqual(workbuddy_bridge._proof_in('P9 跨站脚本XSS', tokens), '跨站脚本')
        self.assertEqual(workbuddy_bridge._proof_in('本周工作复盘', tokens), '')

    def test_pptx_text_reads_slide_xml(self):
        with tempfile.TemporaryDirectory() as folder:
            deck = Path(folder) / 'x.pptx'
            with zipfile.ZipFile(deck, 'w') as zf:
                zf.writestr('ppt/slides/slide1.xml',
                            '<p:sld><a:t>OWASP Top 10 入门</a:t></p:sld>')
                zf.writestr('ppt/slides/slide2.xml', '<p:sld><a:t>跨站脚本 XSS</a:t></p:sld>')
            text = workbuddy_bridge._pptx_text(str(deck))
            self.assertIn('OWASP', text)
            self.assertIn('跨站脚本', text)


if __name__ == '__main__':
    unittest.main(verbosity=2)
