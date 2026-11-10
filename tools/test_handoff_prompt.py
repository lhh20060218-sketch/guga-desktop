# -*- coding: utf-8 -*-
"""回归：复合任务的上游正文不能被固定模板顶掉。

现场（20261110 s4）：第 1 步豆包交回 2230 字 PPT 提示词，第 2 步派给 WorkBuddy 时
输入框里回读 2392 字全部正确，但旧组装把正文放进独立“参考资料”块、末尾再挂一段
“本步要求：生成PPT（规则）”；WorkBuddy 的 PPT 流程只取最后一段，2230 字正文被整段
丢弃，成品变成无关的《本周工作复盘》。

单独执行：python tools/test_handoff_prompt.py
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core import adapter_chain  # noqa: E402
from core import handoff_prompt  # noqa: E402
from core.handoff_prompt import HandoffError, assert_embedded, compose  # noqa: E402

DOUBAO = """## PPT 生成提示词
**主题**：OWASP Top 10（2025）视角下的 Web 漏洞挖掘入门——以 SRC 授权测试为例
**基本信息**：共 16 页，16:9，中文。
**P1 封面**：主标题“OWASP Top 10（2025）视角下的 Web 漏洞挖掘入门”。
**P2 目录**：注入类、失效的访问控制、加密机制失效、不安全设计、安全配置错误。
**P5 注入类漏洞**：SQL 注入、命令注入、模板注入的触发路径与授权测试边界。
**P9 跨站脚本 XSS**：反射型、存储型、DOM 型三类的触发路径差异与修复建议。
**P12 组件漏洞**：依赖版本核查、CVE 匹配、升级窗口与回归验证。
**P16 总结**：授权边界、检测清单与复测闭环。
"""
LONG_BODY = (DOUBAO.rstrip() + '\n' + '\n'.join(
    '**P%d**：第 %d 页要点，包含攻击面、验证方法与修复建议（编号 %d）。' % (i, i, i)
    for i in range(20, 220))).strip()          # >2000 字且尾部唯一，贴近现场 2230 字


class ComposeTests(unittest.TestCase):
    def test_long_chinese_handoff_is_kept_verbatim(self):
        prompt = compose('生成PPT', {'name': '豆包', 'text': LONG_BODY}, wants_file=True)
        self.assertGreater(len(prompt), len(LONG_BODY))
        self.assertIn(LONG_BODY, prompt)                    # 正文一个字都没少
        self.assertTrue(prompt.startswith('请严格按下面这份 PPT 提示词产出 PPT'))
        self.assertNotIn('以下是上一步', prompt)            # 不再是可被跳过的“参考资料”
        self.assertNotIn('本步要求：', prompt)              # 不再留可被单独取走的末段
        self.assertNotIn('\n\n', prompt)
        self.assertTrue(assert_embedded(prompt, LONG_BODY))

    def test_general_step_puts_body_after_instruction(self):
        body = '本周完成接口联调与回归测试，剩余一个兼容性问题待修，需要写明影响范围与下一步计划。'
        prompt = compose('写一份周报', {'name': '豆包', 'text': body})
        self.assertLess(prompt.index('本步要求：写一份周报'), prompt.index(body))
        self.assertTrue(prompt.endswith('也不要执行与本步无关的操作。）'))
        self.assertIn(body, prompt)

    def test_empty_handoff_raises_missing(self):
        for text in ('', '   \n\t '):
            with self.assertRaises(HandoffError) as ctx:
                compose('生成PPT', {'name': '豆包', 'text': text}, wants_file=True)
            self.assertEqual(ctx.exception.code, 'handoff_missing')
            self.assertIn('豆包', ctx.exception.missing)

    def test_short_handoff_raises_too_short(self):
        with self.assertRaises(HandoffError) as ctx:
            compose('生成PPT', {'name': '豆包', 'text': '好的，收到'}, wants_file=True)
        self.assertEqual(ctx.exception.code, 'handoff_too_short')
        self.assertIn('5 字', ctx.exception.missing)

    def test_newlines_and_special_chars_survive(self):
        body = ('第一段【重点】\n<<<\n保留 “引号”、\\反斜杠、<标签> 与 —— 破折号\n'
                '第二段末尾不能丢：P16 总结（完）')
        prompt = compose('生成PPT', {'name': '豆包', 'text': body}, wants_file=True)
        self.assertIn(body, prompt)
        self.assertIn('<<<', prompt)
        self.assertTrue(assert_embedded(prompt, body))

    def test_template_only_prompt_is_rejected(self):
        template = compose('生成PPT', None, wants_file=True)   # 第一步允许只有模板
        with self.assertRaises(HandoffError) as ctx:
            assert_embedded(template, LONG_BODY)
        self.assertEqual(ctx.exception.code, 'handoff_not_embedded')

    def test_truncated_prompt_is_rejected(self):
        prompt = compose('生成PPT', {'name': '豆包', 'text': LONG_BODY}, wants_file=True)
        broken = prompt[:len(prompt) // 2]
        with self.assertRaises(HandoffError) as ctx:
            assert_embedded(broken, LONG_BODY)
        self.assertEqual(ctx.exception.code, 'handoff_not_embedded')

    def test_second_step_without_handoff_is_rejected(self):
        # 现场界面上只看到“生成PPT（规则）（只要正文…）”，正是第 2 步 previous=None 的形态
        with self.assertRaises(HandoffError) as ctx:
            adapter_chain._prompt_for({'index': 2, 'instruction': '生成PPT'}, None)
        self.assertEqual(ctx.exception.code, 'handoff_missing')
        self.assertIn('交接链断了', ctx.exception.detail)

    def test_first_step_has_no_handoff_requirement(self):
        prompt = compose('写一段产品介绍', None)
        self.assertTrue(prompt.startswith('写一段产品介绍'))
        self.assertTrue(prompt.endswith('也不要执行与本步无关的操作。）'))


class _FakeAdapter:
    def __init__(self, result=None):
        self.result = result or {}
        self.calls = []

    def ask(self, prompt, **kwargs):
        self.calls.append(prompt)
        return self.result


class ChainAbortTests(unittest.TestCase):
    def _run(self, first_text, deck_path):
        first = _FakeAdapter(dict(ok=True, text=first_text,
                                  evidence=dict(artifact=deck_path),
                                  source=dict(label='桩')))
        second = _FakeAdapter(dict(ok=True, text='不该被调用'))
        from core.adapters import dispatch
        old = dispatch.adapter_for
        dispatch.adapter_for = lambda key: (
            ('stub_a', first) if str(key) in ('stub_a', '桩A') else ('stub_b', second))
        old_log, old_save, old_disk = adapter_chain._log, adapter_chain._save_step, adapter_chain._find_pptx
        adapter_chain._log = lambda *a, **k: None
        adapter_chain._save_step = lambda *a, **k: ''
        adapter_chain._find_pptx = lambda since: ''
        try:
            chain = dict(steps=[
                dict(index=1, app_id='stub_a', name='桩A', instruction='写一段产品介绍'),
                dict(index=2, app_id='stub_b', name='WorkBuddy', instruction='生成PPT'),
            ])
            result = adapter_chain.run(chain)
        finally:
            dispatch.adapter_for = old
            adapter_chain._log, adapter_chain._save_step = old_log, old_save
            adapter_chain._find_pptx = old_disk
        return result, second

    def test_empty_handoff_aborts_before_dispatch(self):
        with tempfile.TemporaryDirectory() as folder:
            deck = Path(folder) / 'stub.pptx'
            deck.write_bytes(b'PK\x03\x04')
            result, second = self._run('', str(deck))
        self.assertFalse(result['ok'])
        self.assertEqual(result['code'], 'handoff_missing')
        self.assertEqual(second.calls, [])                 # 没有拿模板-only 去派单
        self.assertIn('缺什么', result['error'])
        self.assertIn('交付的正文', result['missing'])

    def test_short_handoff_aborts_with_own_code(self):
        with tempfile.TemporaryDirectory() as folder:
            deck = Path(folder) / 'stub.pptx'
            deck.write_bytes(b'PK\x03\x04')
            result, second = self._run('好的', str(deck))
        self.assertFalse(result['ok'])
        self.assertEqual(result['code'], 'handoff_too_short')
        self.assertEqual(second.calls, [])
        self.assertIn('2 字', result['error'])


class PlainTextDeliveryTests(unittest.TestCase):
    """20261110w 现场：豆包把正文产出成在线文档卡片，对话里只有摘要。
    投递口径增加形态约束：要求直接在对话里以纯文本输出全文；不改写用户原句。
    """

    def test_doubao_step_gets_plain_text_rule_without_rewriting(self):
        step = dict(index=1, app_id='doubao', name='豆包',
                    instruction='用豆包生成PPT提示词')
        prompt = adapter_chain._prompt_for(step, None)
        self.assertTrue(prompt.startswith('用豆包生成PPT提示词'))
        self.assertIn('用豆包生成PPT提示词', prompt)
        self.assertIn('纯文本输出完整全文', prompt)
        self.assertIn('不要生成在线文档、卡片、图片或附件', prompt)

    def test_non_doubao_step_has_no_plain_text_rule(self):
        prompt = compose('生成PPT', None, wants_file=True)
        self.assertNotIn('纯文本输出完整全文', prompt)


if __name__ == '__main__':
    unittest.main(verbosity=2)
