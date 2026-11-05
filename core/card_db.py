# -*- coding: utf-8 -*-
"""酒馆战棋卡牌数据库 — cardId → 中文名/种族/亡语token

数据源：hearthstonejson.com 官方 zhCN 卡牌库（data/cards_zhcn.json，9.7MB）。
用途：
1. 显示中文卡名（不再输出 BG25_008 这种 ID，AI 分析也读得懂）
2. 亡语召唤 token 解析 → 蒙特卡洛模拟器可用（BobsBuddy 同源思路）
"""
import json
import os
import re

_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'cards_zhcn.json')
_CURRENT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'bg_agent', 'cards_37.json')

# 亡语召唤：召唤一只2/3并具有嘲讽的龟 / 召唤一个6/6并具有嘲讽的僵尸
_RE_SUMMON = re.compile(r'召唤(?:一[只个])?(\d+)/(\d+)(?:并具有(?:<b>)?([^<。]+?)(?:</b>)?)?(?:的)?[^。]*[。]?')
_RE_TOKEN = re.compile(r'召唤(?:一[只个])?(\d+)/(\d+)')

_CACHE = None  # {cardId: {'name','race','atk','hp','deathrattle'|None}}


def _load():
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    _CACHE = {}
    try:
        with open(_DB_PATH, 'r', encoding='utf-8') as f:
            cards = json.load(f)
    except Exception:
        return _CACHE
    for c in cards:
        cid = c.get('id', '')
        if not cid.startswith('BG'):
            continue
        if c.get('type') != 'MINION':
            continue
        atk = c.get('attack') or 0
        hp = c.get('health') or 0
        if not atk and not hp:
            continue
        entry = {
            'name': c.get('name', cid),
            'race': c.get('race'),
            'atk': atk,
            'hp': hp,
            'tech_level': c.get('techLevel') or 0,
            'deathrattle': None,
        }
        text = c.get('text') or ''
        # 亡语：召唤固定身材 token（如 "召唤一只2/3并具有嘲讽的龟"）
        if '亡语' in text:
            m = _RE_SUMMON.search(text)
            if m:
                token = {'atk': int(m.group(1)), 'hp': int(m.group(2))}
                kw = m.group(3) or ''
                token['taunt'] = '嘲讽' in kw
                token['divine_shield'] = '圣盾' in kw
                token['reborn'] = '复生' in kw
                entry['deathrattle'] = token
        _CACHE[cid] = entry
    # Overlay the pinned current-client BG definitions. This database is used
    # for names, races and board summaries; it is not an executable ruleset.
    try:
        with open(_CURRENT_PATH, 'r', encoding='utf-8') as f:
            current = json.load(f)
        for cid, card in current.get('cards', {}).items():
            if card.get('type') != 'minion':
                continue
            prior = _CACHE.get(cid, {})
            entry = dict(prior)
            entry['name'] = card.get('name') or entry.get('name') or cid
            entry['race'] = card.get('race') or entry.get('race')
            for source, target in (('attack', 'atk'), ('health', 'hp'), ('tier', 'tech_level')):
                if isinstance(card.get(source), int):
                    entry[target] = card[source]
            if not entry.get('atk') and not entry.get('hp'):
                continue
            text = card.get('text') or card.get('text_en') or ''
            entry.setdefault('deathrattle', None)
            if '亡语' in text:
                match = _RE_SUMMON.search(text)
                if match:
                    token = {'atk': int(match.group(1)), 'hp': int(match.group(2))}
                    keywords = match.group(3) or ''
                    token['taunt'] = '嘲讽' in keywords
                    token['divine_shield'] = '圣盾' in keywords
                    token['reborn'] = '复生' in keywords
                    entry['deathrattle'] = token
            _CACHE[cid] = entry
    except (OSError, ValueError, TypeError):
        pass
    return _CACHE


def lookup(card_id: str):
    """返回 {name, race, atk, hp, tech_level, deathrattle|None} 或 None"""
    return _load().get(card_id)


def name_of(card_id: str) -> str:
    e = _load().get(card_id)
    return e['name'] if e else card_id


def race_of(card_id: str) -> str:
    e = _load().get(card_id)
    if not e or not e.get('race'):
        return ''
    return {'BEAST': '野兽', 'MECH': '机械', 'MECHANICAL': '机械', 'MURLOC': '鱼人', 'DEMON': '恶魔',
            'DRAGON': '龙', 'ELEMENTAL': '元素', 'NAGA': '娜迦', 'PIRATE': '海盗',
            'QUILBOAR': '野猪人', 'UNDEAD': '亡灵', 'ALL': '全种族',
            'TOTEM': '图腾', 'HYDRA': '双头蛇'}.get(e['race'], e['race'])


def minions_at_tier(tier: int):
    """酒馆等级池：返回该等级可刷出的随从卡 id 列表（用于假想对手生成）"""
    out = []
    for cid, e in _load().items():
        tl = e.get('tech_level', 0)
        if 1 <= tl <= tier:
            out.append(cid)
    return out


if __name__ == '__main__':
    import sys
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)
    print('库加载完成，酒馆随从数:', len(_load()))
    for cid in ('BG25_008', 'BG28_309', 'BG26_174', 'BG19_010'):
        e = lookup(cid)
        if e:
            print(f'{cid} = {e["name"]}（{race_of(cid)}）{e["atk"]}-{e["hp"]}'
                  f' 亡语token={e["deathrattle"]}')
