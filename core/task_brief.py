"""DSH-owned task state projected into concise, speakable answers.

This is an executive brief, not a second planner: every fact originates in a
DSH lifecycle event or tool receipt.  It lets the voice shell answer while the
worker is busy without guessing what the worker is doing.
"""
from __future__ import annotations

import time

from core.agent_memory import safe_text


_STATUS_TERMS = (
    '进度', '进展', '做到哪', '怎么样了', '在做什么', '在干什么', '忙什么',
    '为什么', '怎么回事', '卡住', '卡在', '失败', '没动', '不行', '还要多久',
    '下一步', '计划', '任务是什么', '理解', '汇报', '总结', '当前任务',
    '听得到', '还在吗', '完成了吗', '做完没', '什么情况',
)

_TOOL = {
    'computer': '操作桌面界面', 'local_computer': '读取或运行本机任务',
    'applications': '打开或切换软件', 'browser': '打开网页并核对',
    'media_workflow': '处理视频和字幕', 'wechat': '操作微信',
    'web_search': '查询公开资料', 'task_plan': '更新任务计划',
}


class DshTaskBrief:
    """Thread-safe-enough UI model: DSH events and Qt reads share one loop."""

    def __init__(self, job_id='', goal='', clock=None):
        self.clock = clock or time.monotonic
        self.job_id = str(job_id)
        self.goal = safe_text(goal)[:500]
        self.started = self.clock()
        self.updated = self.started
        self.last_checkin = self.started
        self.beat = 0
        self.active = True
        self.phase = '已受理，等待 DSH 返回第一个步骤'
        self.summary = ''
        self.last_operation = ''
        self.last_ok = None
        self.last_receipt_at = None
        self.report_state = ''
        self.blockers = []
        self.receipt_count = 0
        self.error_count = 0
        self.milestone_count = 0

    def _touch(self):
        self.updated = self.clock()

    def observe(self, event):
        if not isinstance(event, dict):
            return
        self._touch()
        kind = event.get('type')
        phase = event.get('phase')
        if kind == 'status':
            if phase in ('turn_start', 'step_start', 'step_end'):
                self.phase = {
                    'turn_start': '正在规划任务',
                    'step_start': '正在执行下一步',
                    'step_end': '正在核对这一步的结果',
                }[phase]
            reason = event.get('reason') or {}
            if isinstance(reason, dict) and reason.get('kind') == 'error':
                self.blockers = [safe_text(reason.get('error') or reason)[:600]]
        elif kind == 'tool_receipt':
            receipt = event.get('receipt') or {}
            self._receive(receipt.get('name'), receipt.get('arguments') or {}, receipt.get('result') or {})
        elif kind in ('tool_result', 'tool_call'):
            self.phase = '正在操作 ' + str(event.get('name') or event.get('toolName') or '工具')
        elif kind == 'report':
            self.report_state = str(event.get('state') or '')
            self.summary = safe_text(event.get('summary') or '')[:1200]
            blockers = event.get('blockers') or []
            self.blockers = [safe_text(x)[:500] for x in blockers if str(x).strip()][:3]
            if event.get('milestone'):
                self.milestone_count += 1
            self.phase = {
                'progress': '按 DSH 的重要阶段报告继续推进',
                'ready': 'DSH 已交付，等待核对',
                'blocked': 'DSH 报告任务受阻',
                'failed': 'DSH 报告这一步失败',
                'needs_input': '等待你的决定',
            }.get(self.report_state, self.phase)

    def _receive(self, name, args, result):
        label = _TOOL.get(str(name), str(name or '工具'))
        action = str(args.get('action') or '').strip()
        if action:
            label += '（' + action[:40] + '）'
        ok = result.get('ok') is True if isinstance(result, dict) else None
        self.receipt_count += 1
        self.last_receipt_at = self.clock()
        self.last_ok = ok
        self.last_operation = label + ('已完成，等待下一步' if ok else '未完成')
        self.phase = self.last_operation
        if ok is False:
            self.error_count += 1
            error = result.get('error') if isinstance(result, dict) else ''
            if error:
                self.blockers = [safe_text(error)[:600]]

    def complete(self, ok=False, state='failed', summary=''):
        self.active = False
        self.report_state = str(state or '')
        if summary:
            self.summary = safe_text(summary)[:1200]
        self.phase = {
            'awaiting_review': 'DSH 已交付，仍需独立核验',
            'needs_input': '等待你的决定',
            'cancelled': '已停止',
            'failed': '未完成',
            'verified': '已验收',
        }.get(self.report_state, 'DSH 已返回结果' if ok else 'DSH 未完成')
        self._touch()

    def elapsed(self, now=None):
        return max(0, int((self.clock() if now is None else now) - self.started))

    def answer(self, question=''):
        """Return an immediate factual answer, or None for an unrelated request."""
        value = str(question or '').strip()
        if not value or not any(term in value for term in _STATUS_TERMS):
            return None
        elapsed = self.elapsed()
        minutes, seconds = divmod(elapsed, 60)
        age = (f'已经进行 {minutes} 分 {seconds} 秒' if minutes else f'已经进行 {seconds} 秒')
        goal = self.goal or '当前任务'
        parts = [f'我正在负责“{goal}”，{age}。']
        if self.report_state == 'needs_input':
            parts.append('目前停在一个需要你决定的问题上。')
        elif self.report_state in ('blocked', 'failed'):
            parts.append('目前这一步没有通过。')
        elif not self.active:
            parts.append('DSH 已经结束这一轮。')
        if self.summary:
            parts.append('最新进展：' + self.summary)
        if self.last_operation:
            parts.append('最近一次真实操作是：' + self.last_operation + '。')
        elif self.phase:
            parts.append('当前状态：' + self.phase + '。')
        if self.blockers:
            parts.append('已知卡点：' + '；'.join(self.blockers))
        elif any(term in value for term in ('为什么', '卡住', '失败', '没动', '不行')):
            parts.append('目前还没有收到 DSH 明确报出的错误原因，我不会把“等待回执”说成已经查明。')
        if self.report_state == 'needs_input':
            parts.append('我在等你回复后才能继续，没有擅自重放操作。')
        elif self.active:
            parts.append('任务尚未完成；我会继续盯着 DSH 的回执，重要变化会主动告诉你。')
        return ''.join(parts)[:1200]

    def watchdog(self, now=None, interval=30):
        """Produce one honest update per interval, including genuine stalls."""
        now = self.clock() if now is None else float(now)
        if not self.active or self.report_state == 'needs_input':
            return None
        if now - self.last_checkin < float(interval):
            return None
        self.last_checkin = now
        self.beat += 1
        elapsed = self.elapsed(now)
        goal = self.goal or '当前任务'
        parts = [f'本鹅报个进展：已经 {elapsed} 秒，“{goal}”还在处理。']
        if self.summary:
            parts.append('执行器最新报告：' + self.summary)
        elif self.last_operation:
            parts.append('最近一次操作：' + self.last_operation + '。')
        else:
            parts.append('目前还没有收到可核验的步骤回执。')
        if self.blockers:
            parts.append('卡点：' + '；'.join(self.blockers))
        elif self.last_receipt_at is None:
            parts.append('暂时看不出是否卡住，原因还不能确认。')
        elif now - self.last_receipt_at >= interval:
            parts.append(f'大约 {int(now-self.last_receipt_at)} 秒没有新的操作回执，原因还不能确认。')
        else:
            parts.append('目前没有新的明确错误回执。')
        if self.blockers:
            parts.append('我的判断是先核对失败步骤和已有结果，再根据新回执调整，避免重复已经做过的操作。')
        else:
            parts.append('接下来等执行结果并核验；这期间咱们可以继续聊。')
        if self.active:
            parts.append('任务尚未完成。')
        return ''.join(parts)[:800]
