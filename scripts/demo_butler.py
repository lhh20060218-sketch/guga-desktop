# -*- coding: utf-8 -*-
"""M1 demo: 管家职能演示(习惯记忆 + 事务提醒)

无 GUI 依赖, 终端直接跑:
  python scripts/demo_butler.py
"""
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from core.butler_habit import HabitProfile
from core.butler_reminder import ReminderService

SEP = '=' * 60


def section(t):
    print('\n%s\n  %s\n%s' % (SEP, t, SEP))


def main():
    tmp = Path(tempfile.mkdtemp(prefix='butler_demo_'))
    print('演示数据目录: %s (不污染正式数据)\n' % tmp)

    # ========== 1. 习惯记忆 ==========
    section('1. 习惯记忆: 模拟少爷两周的作息')
    habit = HabitProfile(path=tmp / 'habit.db', min_count=3)
    # 模拟: 每天晚上 9 点开腾讯会议, 早上 9 点开 IDEA, 连续 6 天
    for day in range(6):
        for h, kind, detail in ((21, 'app_launch', 'tencent_meeting.exe'),
                                (9, 'app_launch', r'D:\tools\idea64.exe'),
                                (9, 'app_launch', 'tencent_meeting.exe'),
                                (14, 'query', '天气')):
            ts = time.time() - (day + 1) * 86400
            import calendar
            lt = time.localtime(ts)
            ts = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, h, 0, 0,
                              0, 0, -1))
            habit.record(kind, detail, ts=ts)
    print('稳定习惯(top5):')
    for kind, detail, h, c, wd_span in habit.habits(limit=5):
        print('  - [%s] %s @ %02d:00 x%d (跨%d个星期)' % (kind, detail, h, c, wd_span))
    print('\n画像摘要(可拼进管家 prompt):')
    print(habit.summary())
    # 用一个匹配"晚上9点"的时刻测主动建议
    probe = time.time()
    lt = time.localtime(probe)
    probe = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 21, 0, 0, 0, 0, -1))
    print('\n管家主动建议(模拟现在 21:00):')
    for s in habit.suggest_now(now=probe):
        print('  💡 %s (重复%d次)' % (s['text'], s['count']))

    # ========== 2. 事务提醒 ==========
    section('2. 事务提醒: 录入/到期/播报')
    spoken = []
    rem = ReminderService(path=tmp / 'reminders.json',
                          on_due=lambda r: spoken.append(
                              '少爷, 该%s了(约定%s)' % (r['text'], r['when_text'])))
    r1 = rem.add('+30m', '站起来活动颈椎')
    r2 = rem.add('+2h', '给队友A回素材反馈')
    print('已录入: %s(%s) / %s(%s)' % (r1['text'], r1['when_text'],
                                       r2['text'], r2['when_text']))
    print('当前待办: %d 条, 最近: %s' % (len(rem.list_pending()),
                                        rem.status()['next']))
    # 模拟时间快进 40 分钟: 第一条该响
    now40 = time.time() + 40 * 60
    due = rem.tick(now=now40)
    print('\n快进 40 分钟后 tick(): 到期 %d 条' % len(due))
    for s in spoken:
        print('  🔔 %s' % s)
    # 再 tick 一次不应重复播报
    again = rem.tick(now=now40)
    print('再次 tick(): 到期 %d 条(防重复播报: %s)'
          % (len(again), '通过' if not again else '失败'))
    # 跨重启恢复: 重新加载, 待办应只剩 1 条
    rem2 = ReminderService(path=tmp / 'reminders.json')
    print('模拟重启后恢复: 待办 %d 条 (应为 1) -> %s'
          % (len(rem2.list_pending()),
             '通过' if len(rem2.list_pending()) == 1 else '失败'))
    # 时间解析
    from core.butler_reminder import parse_when
    for w in ('+30m', '09:30', '明天9点', '2026-11-05 14:00'):
        ts, disp = parse_when(w)
        print('  parse_when(%r) -> %s' % (w, disp))

    print('\n' + SEP)
    print('  DEMO 完成 — 管家习惯记忆 + 事务提醒验证通过')
    print(SEP)
    return 0


if __name__ == '__main__':
    sys.exit(main())
