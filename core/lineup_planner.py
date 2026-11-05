# -*- coding: utf-8 -*-
"""咕嘎企鹅·酒馆战棋招募阶段未来阵容展望（轨道⑤）— 纯规则零依赖

运行时读取 knowledge/battlegrounds/comps.json 中 category=='流派' 的模板，
结合当前局面（种族分布/核心卡命中/等级/铸币/血量/回合）给出流派方向、
置信度、依据、缺口与下一步建议。模板字段（core_pieces/blueprint/weakness/
maturity）可能缺失，全部容错。
"""
import json
import os

from core import comp_analysis

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_COMP_PATH = os.path.join(_ROOT, 'knowledge', 'battlegrounds', 'comps.json')

# 内容关键词 → 加分（模板 content 提到该词且场上有对应关键词随从时）
_CONTENT_KWS = {'亡语': 2, '圣盾': 2, '烈毒': 2, '复生': 2, '风怒': 1, '嘲讽': 1}
_KW_FIELD = {'亡语': 'deathrattle', '圣盾': 'divine_shield', '烈毒': 'poison',
             '复生': 'reborn', '风怒': 'windfury', '嘲讽': 'taunt'}


def _f(m, key, default=None):
    """取随从字段：兼容 dict（日志/视觉 JSON）与 Minion dataclass 对象"""
    if isinstance(m, dict):
        return m.get(key, default)
    return getattr(m, key, default)


def templates() -> list:
    """运行时读取 comps.json 的流派模板（category=='流派'），字段缺失容错"""
    out = []
    try:
        with open(_COMP_PATH, encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        return out
    chunks = data.get('chunks', []) if isinstance(data, dict) else (data or [])
    for c in chunks:
        if not isinstance(c, dict) or c.get('category') != '流派':
            continue
        out.append({'tags': list(c.get('tags') or []),
                    'content': c.get('content') or '',
                    'core_pieces': list(c.get('core_pieces') or []),
                    'blueprint': c.get('blueprint') or '',
                    'weakness': c.get('weakness') or '',
                    'maturity': c.get('maturity') or ''})
    return out


def _stream_name(t: dict) -> str:
    """模板的流派名：tags 中首个种族名 + '流'，否则取首个 tag"""
    for tag in t['tags']:
        if tag in comp_analysis.RACE_NAMES:
            return f'{tag}流'
    return (t['tags'] or ['未成型'])[0]


def _piece_on_board(piece: str, mine: list) -> bool:
    """core_pieces 条目是否已在场上（双向子串匹配中文名）"""
    for m in mine:
        cn = comp_analysis.cn_name(_f(m, 'name', '') or '')
        if piece in cn or (cn and cn in piece):
            return True
    return False


def _board_has_kw(mine: list, kw: str) -> bool:
    f = _KW_FIELD.get(kw)
    return bool(f) and any(_f(m, f) for m in mine)


def _extract_blueprint(content: str) -> str:
    """模板无 blueprint 字段时，从 content 提取第一句作为蓝图"""
    for sep in ('。', '！', '？', '；'):
        idx = content.find(sep)
        if idx > 0:
            return content[:idx + 1]
    return content


def _missing_cores(t: dict, stream: str, mine: list) -> list:
    """缺口核心：模板 core_pieces 中不在场上的；无 core_pieces 则从信号表推导"""
    if t['core_pieces']:
        return [f'还缺: {p}' for p in t['core_pieces'] if not _piece_on_board(p, mine)]
    names = [_f(m, 'name', '') or '' for m in mine]
    return [f'还缺: {disp}' for disp in comp_analysis.core_cards_for(stream)
            if not comp_analysis.core_present(disp, names)]


def _advice(stream: str, missing: list, gold: int, tier: int, hp: int) -> str:
    """下一步建议：结合血量/铸币/等级与缺口"""
    miss = '、'.join(x.replace('还缺: ', '') for x in missing)
    if hp < 15:
        return '血量低于15：优先买即时战力保命成型，暂缓搜核心'
    if missing:
        if gold >= 6 and tier <= 4:
            return f'铸币充足且等级低：建议升酒馆找核心（还缺{miss}）'
        race = stream[:-1] if stream.endswith('流') else '对应'
        return f'建议刷/买{race}随从找核心（还缺{miss}）'
    return '核心基本齐备：建议补身材/圣盾/烈毒，为决赛站位做准备'


def _pivot_hint(confidence: float, turn: int, hp: int) -> str:
    """转型提示：置信低且回合深 → 考虑转型；血量低 → 优先保命"""
    hints = []
    if confidence < 0.4 and turn >= 7:
        hints.append('当前方向置信低且回合已深（≥7），可考虑转型')
    if hp < 15:
        hints.append('血量低：优先保命（买战力、防针对站位）')
    return '；'.join(hints)


def project_lineup(board: dict) -> dict:
    """招募阶段展望：board={'mine':[随从dict同analyze_team格式],'tier','gold','hp','turn'}
    返回 {'direction','confidence','signals','missing_cores','blueprint',
          'advice','pivot_hint','weakness','maturity'}"""
    mine = [m for m in (board.get('mine') or []) if m]
    tier = int(board.get('tier') or 1)
    gold = int(board.get('gold') or 0)
    hp = int(board.get('hp') or 30)
    turn = int(board.get('turn') or 1)
    empty = {'direction': '未成型', 'confidence': 0.0, 'signals': [], 'missing_cores': [],
             'blueprint': '', 'advice': '先按当前等级买随从定方向', 'pivot_hint': '',
             'weakness': '', 'maturity': ''}
    if not mine:
        return empty

    # ① 己方种族分布 + 核心卡命中（AOE威胁 只作提示不参与方向）
    races = {}
    key_hits = []  # [(展示名, 流派)]
    for m in mine:
        r = comp_analysis.race_of(_f(m, 'name', '') or '')
        if r:
            races[r] = races.get(r, 0) + 1
        hit = comp_analysis.match_key_card(comp_analysis.cn_name(_f(m, 'name', '') or ''))
        if hit and hit[0] != 'AOE威胁' and hit[2] not in [h[0] for h in key_hits]:
            key_hits.append((hit[2], hit[0]))

    # ② 每个流派模板打分：tags 种族×3 + core_pieces 命中×4 + 内容关键词加权
    best, total = None, 0.0
    for t in templates():
        score = 0.0
        for tag in t['tags']:
            if tag in comp_analysis.RACE_NAMES:
                score += races.get(tag, 0) * 3
        for piece in t['core_pieces']:
            if _piece_on_board(piece, mine):
                score += 4
        for kw, w in _CONTENT_KWS.items():
            if kw in t['content'] and _board_has_kw(mine, kw):
                score += w
        total += score
        if best is None or score > best[0]:
            best = (score, t)
    if not best or best[0] <= 0:
        empty['advice'] = '方向不明显：按当前等级买同种族随从，先定流派'
        empty['signals'] = [f'场上有{c}个{r}随从' for r, c in races.items()]
        return empty

    stream = _stream_name(best[1])
    confidence = best[0] / (total + 0.001)
    signals = ([f'场上有{c}个{r}随从' for r, c in races.items()]
               + [f'命中核心卡{disp}' for disp, _s in key_hits])
    signals = [f'依据{i}: {s}' for i, s in enumerate(signals, 1)]
    missing = _missing_cores(best[1], stream, mine)
    return {'direction': stream, 'confidence': confidence, 'signals': signals,
            'missing_cores': missing,
            'blueprint': best[1]['blueprint'] or _extract_blueprint(best[1]['content']),
            'advice': _advice(stream, missing, gold, tier, hp),
            'pivot_hint': _pivot_hint(confidence, turn, hp),
            'weakness': best[1]['weakness'], 'maturity': best[1]['maturity']}


def format_outlook(o: dict) -> str:
    """展望 dict → 60-100 字人话摘要（字段缺失容错）"""
    parts = [f"展望：{o.get('direction', '未成型')}方向（置信{o.get('confidence', 0) * 100:.0f}%）"]
    sig = [s.split(':', 1)[-1].strip() for s in (o.get('signals') or [])]
    if sig:
        parts.append('；'.join(sig))
    miss = [s.replace('还缺: ', '') for s in (o.get('missing_cores') or [])]
    if miss:
        parts.append('还差' + '、'.join(miss))
    if o.get('maturity'):
        parts.append(f"成型约{o['maturity']}")
    if o.get('weakness'):
        w = o['weakness']
        parts.append(w if w.startswith('怕') else f'怕{w}')
    if o.get('advice'):
        parts.append(f"建议：{o['advice']}")
    return '；'.join(parts)


if __name__ == '__main__':
    import sys
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)

    def mk(name, **kw):
        m = {'name': name, 'atk': 1, 'hp': 1}
        m.update(kw)
        return m

    # 样例1：tier4 野兽雏形（瑞文+鱼饵+野兽，缺狼群领袖/鹦鹉/熊妈妈；混入卡ID走种族路径）
    board = {'mine': [mk('瑞文戴尔男爵', atk=2, hp=5), mk('鱼饵', atk=3, hp=2),
                      mk('BG19_010', atk=2, hp=2, deathrattle=[{'atk': 1, 'hp': 1}]),
                      mk('陆行鸟', atk=2, hp=2)],
             'tier': 4, 'gold': 8, 'hp': 32, 'turn': 7}
    o = project_lineup(board)
    assert o['direction'] == '野兽流', o['direction']
    assert o['confidence'] > 0 and o['missing_cores'] and o['advice'] and o['signals']
    assert o['blueprint'] and o['pivot_hint'] == ''
    print('展望样例:', format_outlook(o))
    print('  direction:', o['direction'], '| confidence:', f"{o['confidence']:.2f}")
    print('  missing_cores:', o['missing_cores'], '| pivot_hint:', o['pivot_hint'] or '(无)')
    # 样例2：空场 → 未成型
    e = project_lineup({'mine': [], 'tier': 2, 'gold': 5, 'hp': 20, 'turn': 3})
    assert e['direction'] == '未成型' and e['advice'] == '先按当前等级买随从定方向'
    print('空场:', e['direction'], '|', e['advice'])
    # 样例3：卡 ID 输入 + 低血量（触发保命建议与转型提示）
    o2 = project_lineup({'mine': [mk('BG25_008'), mk('BG19_010')],
                         'tier': 3, 'gold': 4, 'hp': 12, 'turn': 8})
    assert o2['direction'] and o2['advice'] and o2['pivot_hint']
    print('低血量卡ID输入:', format_outlook(o2))
