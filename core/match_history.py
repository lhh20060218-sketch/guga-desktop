# -*- coding: utf-8 -*-
"""咕嘎企鹅·酒馆战棋战绩记忆（最近5场，只记结果）+ 调侃台词

记录：对局结束时由 pet_window._on_game_over 调用 record_result
     （吃鸡/出局/投降 + 名次近似），只记最终结果，不记对局细节。
持久化：data/match_history.json（重启不丢，最多保留 5 场）
调侃：build_roast() 按最近战绩（连胜/连败/吃鸡/名次）生成"可爱不刻薄"的调侃，
     供对局结束播报 / 右键查看 / 聊天注入三种场景复用。
"""
import json
import os
import time

_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'match_history.json')
MAX_KEEP = 5

_cache = None  # {'history': [...]} 内存缓存（首次读取后常驻）


def _load():
    global _cache
    if _cache is None:
        try:
            with open(_PATH, 'r', encoding='utf-8') as f:
                _cache = json.load(f)
        except Exception:
            _cache = {'history': []}
    return _cache


def _save():
    try:
        os.makedirs(os.path.dirname(_PATH), exist_ok=True)
        with open(_PATH, 'w', encoding='utf-8') as f:
            json.dump(_cache, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def record_result(result: str = 'loss', place: int = None, turns: int = None,
                  game_key: str = None) -> list:
    """记一场战绩（result: win/loss/concede；place: 名次可空；turns: 回合数可空）。
    返回裁剪后的最近战绩列表。"""
    data = _load()
    if game_key and any(x.get('game_key') == game_key for x in data.get('history', [])):
        return data['history'][-MAX_KEEP:]
    item = {'result': result, 'place': place, 'turns': turns,
            'ts': int(time.time())}
    if game_key:
        item['game_key'] = game_key
    data['history'].append(item)
    data['history'] = data['history'][-MAX_KEEP:]
    _save()
    return data['history']


def recent(n: int = MAX_KEEP) -> list:
    """最近 n 场战绩（旧→新）"""
    return list(_load()['history'][-n:])


def stats(history: list = None) -> dict:
    """战绩统计：总场数/吃鸡数/连胜连败/平均名次"""
    h = history if history is not None else recent()
    wins = sum(1 for x in h if x.get('result') == 'win')
    streak_win = 0
    for x in reversed(h):
        if x.get('result') == 'win':
            streak_win += 1
        else:
            break
    streak_loss = 0
    for x in reversed(h):
        if x.get('result') != 'win':
            streak_loss += 1
        else:
            break
    places = [x['place'] for x in h if x.get('place')
              and not (x.get('place') == 1 and x.get('result') != 'win')]
    return {'total': len(h), 'wins': wins, 'losses': len(h) - wins,
            'streak_win': streak_win, 'streak_loss': streak_loss,
            'avg_place': round(sum(places) / len(places), 1) if places else None}


def format_line(history: list = None) -> str:
    """一行战绩：第1、第2、第5…（吃鸡记第1，没名次记出局）"""
    h = history if history is not None else recent()
    out = []
    for x in h:
        if x.get('result') == 'win':
            out.append('第1')
        elif x.get('place') and not (x.get('place') == 1 and x.get('result') != 'win'):
            out.append(f"第{x['place']}")
        else:
            out.append('出局')
    return '、'.join(out) if out else '（暂无）'


def build_roast(history: list = None) -> str:
    """按最近战绩生成调侃台词（可爱不刻薄）；无战绩返回 None"""
    h = history if history is not None else recent()
    if not h:
        return None
    s = stats(h)
    last = h[-1]
    line = format_line(h[-3:])  # 播报最近3场更贴近
    if last.get('result') == 'win':
        if s['streak_win'] >= 3:
            return f"咕嘎嘎！{s['streak_win']}连胜！最近战绩 {line}，本鹅军师功劳占一半，剩下一半是你运气好！"
        if s['streak_win'] == 2:
            return f"咕嘎～两连胜！最近战绩 {line}，饲养员手气不错嘛，本鹅勉强夸你一句！"
        return f"咕嘎～吃鸡！最近战绩 {line}，再接再厉，别下一把就原形毕露！"
    # 出局/投降
    if s['streak_loss'] >= 3:
        return f"咕嘎…{s['streak_loss']}连败，最近战绩 {line}，饲养员的手残属性藏不住了，要不要本鹅教教你站位？"
    if s['streak_loss'] == 2:
        return f"咕嘎…两连败，最近战绩 {line}，本鹅不是说你菜，是说你这运气…（才怪，就是菜）。"
    return f"咕嘎…这局出局了，最近战绩 {line}。不气馁！下一把按本鹅说的买，稳的！"


def chat_context(text: str) -> str:
    """聊天命中"战绩"类关键词 → 返回最近战绩摘要（供 AI 调侃），否则返回 ''"""
    if not any(k in (text or '') for k in ('战绩', '最近', '连胜', '连败', '吃鸡', '出局', '第几')):
        return ''
    h = recent()
    if not h:
        return '【最近战绩】还没有记录（桌宠只记完整对局的最终结果，先打完一把再来问）'
    s = stats(h)
    if s['streak_win']:
        streak = f"当前{s['streak_win']}连胜"
    elif s['streak_loss']:
        streak = f"当前{s['streak_loss']}连败"
    else:
        streak = '无连胜连败'
    avg = f"，平均名次第{s['avg_place']}" if s.get('avg_place') else ''
    return f"【最近战绩】{format_line(h)}（{s['total']}场，吃鸡{s['wins']}次，{streak}{avg}）"


if __name__ == '__main__':
    import sys
    import io
    import tempfile
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)
    # 用临时文件自测，不污染真实战绩
    tmp = os.path.join(tempfile.gettempdir(), 'guga_match_history_test.json')
    globals()['_PATH'] = tmp
    globals()['_cache'] = None
    if os.path.exists(tmp):
        os.remove(tmp)
    # 模拟 7 场（超过 5 场应裁剪保留最近 5 场）
    seq = [('loss', 8), ('loss', 7), ('win', 1), ('loss', 5), ('win', 1), ('win', 1), ('win', 1)]
    for r, p in seq:
        record_result(result=r, place=p, turns=8)
    h = recent()
    print('裁剪后场数:', len(h), '| 战绩:', format_line(h))
    assert len(h) == 5 and h[-1]['result'] == 'win'
    s = stats(h)
    print('统计:', s, '| 三连胜调侃:', build_roast(h))
    assert s['streak_win'] == 3
    # 连败场景
    for r, p in [('loss', 6), ('loss', 8)]:
        record_result(result=r, place=p)
    print('连败调侃:', build_roast())
    assert stats()['streak_loss'] == 2
    # 聊天上下文
    print('chat_context("我最近战绩怎么样"):', chat_context('我最近战绩怎么样'))
    print('chat_context("你好"):', repr(chat_context('你好')))
    os.remove(tmp)
    _cache = None
    print('=== match_history 自测全部通过 ===')
