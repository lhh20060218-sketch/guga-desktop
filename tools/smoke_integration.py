# -*- coding: utf-8 -*-
"""集成冒烟测试：复刻 pet_window 战斗/招募两条入口的完整调用链（无 GUI）
运行：QT_QPA_PLATFORM=offscreen python tools/smoke_integration.py
"""
import sys
import io
import random
import os

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # 项目根

from core import card_db
from core.battle_sim import win_rate, format_rate, minion_from_log, analyze_matchup, format_matchup_insight
from core.log_reader import format_board
from core.comp_analysis import summarize_opponent
from core.lineup_planner import project_lineup, format_outlook

rng = random.Random(7)
_db = card_db._load()
_pool_ids = [cid for cid, e in _db.items() if e.get('tech_level', 9) <= 4]


def mk_random_team(n=6, tier=4):
    """从真实卡池随机取 n 个随从（模拟 log_reader 的输出格式，name=卡ID）"""
    pool = [cid for cid, e in _db.items() if e.get('tech_level', 9) <= tier]
    return [{'name': cid, 'atk': _db[cid]['atk'] + 2, 'hp': _db[cid]['hp'] + 2,
             'taunt': False, 'divine_shield': False, 'windfury': False,
             'poison': False, 'reborn': False, 'golden': False, 'zone_pos': i}
            for i, cid in enumerate(rng.sample(pool, min(n, len(pool))))]


def mk_beast_start():
    """野兽/亡灵雏形（带复生+嘲讽+亡语信号）"""
    return [
        {'name': 'BG26_174', 'atk': 4, 'hp': 5, 'taunt': False, 'divine_shield': False,
         'windfury': False, 'poison': False, 'reborn': True, 'golden': False, 'zone_pos': 0},
        {'name': 'BG25_008', 'atk': 3, 'hp': 4, 'taunt': True, 'divine_shield': False,
         'windfury': False, 'poison': False, 'reborn': False, 'golden': False, 'zone_pos': 1},
        {'name': 'BG28_309', 'atk': 2, 'hp': 3, 'taunt': False, 'divine_shield': False,
         'windfury': False, 'poison': False, 'reborn': False, 'golden': False, 'zone_pos': 2},
    ]


# ---- 战斗阶段调用链（对应 _on_board_from_log 战斗分支）----
board = {'tier': 4, 'gold': 8, 'hp': 30, 'armor': 0, 'turn': 8,
         'mine': mk_beast_start(), 'theirs': mk_random_team(6, 4), 'fresh': True}
board_text = format_board(board)
mine = [minion_from_log(m) for m in board['mine']]
theirs = [minion_from_log(m) for m in board['theirs']]
r = win_rate(mine, theirs, n=2000)
rate_text = format_rate(r)
m = analyze_matchup(mine, theirs, n=2000)
insight = format_matchup_insight(m)
opp_text = summarize_opponent(theirs)
prompt = (f"棋盘:\n{board_text}\n预测:{rate_text}\n解读:{insight}\n对手分析:{opp_text}")
print('[战斗链] OK')
print('  ' + rate_text)
print('  ' + insight)
print('  ' + opp_text)

# ---- 招募阶段调用链（对应 _on_board_from_log 招募分支 + _lineup_outlook）----
board2 = {'tier': 4, 'gold': 7, 'hp': 28, 'armor': 0, 'turn': 7,
          'mine': mk_beast_start(), 'theirs': [], 'fresh': True}
outlook = project_lineup(board2)
outlook_text = format_outlook(outlook)
print('[招募展望链] OK')
print('  ' + outlook_text)
print('  direction:', outlook.get('direction'), '| 缺:', outlook.get('missing_cores'))

print()
print('=== 集成冒烟全部通过 ===')
