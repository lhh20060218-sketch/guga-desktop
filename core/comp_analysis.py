# -*- coding: utf-8 -*-
"""咕嘎企鹅·酒馆战棋阵容分析（对手/己方）— 纯规则零依赖（轨道④）

输入随从 dict：{name(卡ID或中文名), atk, hp, taunt, divine_shield, poison,
reborn, deathrattle, golden, windfury}，字段可缺省。
输出：种族分布 / 关键词统计 / 核心卡命中 / 流派判定（置信度）/ 人话总结。
"""
from core import card_db

# 中文种族关键词（匹配顺序即优先级，与 card_db.race_of 的中文映射一致）
RACE_NAMES = ('野兽', '机械', '鱼人', '恶魔', '龙', '元素', '海盗', '娜迦', '野猪人', '亡灵')

# 核心卡→流派信号表：(关键词元组, 流派, 权重(流派专属3/通用组件2), 展示名)
# 匹配对象为中文卡名（子串命中）；'AOE威胁' 仅用于 key_cards 提示，不参与流派判定
_KEY_RULES = [
    (('瑞文', '男爵'), '亡语流', 3, '瑞文戴尔男爵'),
    (('鹦鹉',), '亡语流', 2, '巨大的金刚鹦鹉'),
    (('小黄', '无私的英雄'), '亡语流', 2, '无私的英雄'),
    (('鱼饵',), '野兽流', 3, '鱼饵'),
    (('狼群领袖',), '野兽流', 3, '狼群领袖'),
    (('上锁宝箱', '宝箱'), '海盗流', 3, '上锁宝箱'),
    (('饥饿', '饲料'), '恶魔流', 3, '饥饿的魔蝠'),
    (('多彩幼龙',), '龙流', 3, '多彩幼龙'),
    (('诺米', '熔岩'), '元素流', 3, '诺米'),
    (('毒鳍', '军备', '幼鳞'), '鱼人流', 3, '毒鳍鱼人'),
    (('死神', '狂战'), 'AOE威胁', 3, '死神4000型'),
]

# 流派弱点（summarize_opponent 用；'未成型' 兜底）
_WEAKNESS = {
    '野兽流': ('怕AOE清场', '鱼饵怕被集火'),
    '机械流': ('怕烈毒', '怕AOE清场'),
    '鱼人流': ('怕圣盾挡毒', '烈毒单场限一次'),
    '恶魔流': ('怕烈毒与圣盾', '核心怕被秒'),
    '海盗流': ('成型前身板脆', '怕经济被断'),
    '元素流': ('怕前期节奏被打断', '成型慢'),
    '龙流': ('成型慢吃资源', '怕中期断牌'),
    '亡灵流': ('怕全场AOE', '怕瑞文先手被秒'),
    '野猪人流': ('吃资源成型慢', '怕前期被压制'),
    '娜迦流': ('吃资源成型慢', '怕前期被压制'),
    '亡语流': ('怕AOE清场', '瑞文怕先手被秒'),
    '未成型': ('尚未成型缺核心',),
}


def _f(m, key, default=None):
    """取随从字段：兼容 dict（日志/视觉 JSON）与 Minion dataclass 对象"""
    if isinstance(m, dict):
        return m.get(key, default)
    return getattr(m, key, default)


def cn_name(name: str) -> str:
    """卡 ID（BG 开头）→ 中文卡名；中文名原样返回；空返回 ''"""
    if not name:
        return ''
    if name.startswith('BG'):
        return card_db.name_of(name)
    return name


def race_of(name: str) -> str:
    """卡 ID（BG 开头）→ card_db.race_of；中文名 → 中文关键词匹配；匹配不到返回 ''"""
    if not name:
        return ''
    if name.startswith('BG'):
        return card_db.race_of(name)
    for r in RACE_NAMES:
        if r in name:
            return r
    return ''


def match_key_card(cn_name_str: str):
    """中文卡名命中核心卡信号表 → (流派, 权重, 展示名)；未命中返回 None"""
    if not cn_name_str:
        return None
    for kws, stream, weight, disp in _KEY_RULES:
        if any(k in cn_name_str for k in kws):
            return (stream, weight, disp)
    return None


def core_cards_for(stream: str) -> list:
    """某流派的展示用核心卡名列表（按信号表推导，去重保序）"""
    return list(dict.fromkeys(disp for _kws, s, _w, disp in _KEY_RULES if s == stream))


def core_present(display_name: str, names: list) -> bool:
    """核心卡（展示名）是否已在阵容中：按信号表关键词子串匹配任意随从名"""
    for kws, _s, _w, disp in _KEY_RULES:
        if disp != display_name:
            continue
        return any(any(k in cn_name(n) for k in kws) for n in names)
    return False


def _scan(minions: list):
    """扫描阵容 → (races, keywords, hits) 供各公开函数复用
    hits: [(流派, 权重, 展示名)] 按展示名去重"""
    races = {}
    keywords = {'烈毒': 0, '圣盾': 0, '嘲讽': 0, '复生': 0, '亡语': 0, '风怒': 0}
    hits = []
    seen = set()
    for m in minions:
        name = _f(m, 'name', '') or ''
        r = race_of(name)
        if r:
            races[r] = races.get(r, 0) + 1
        if _f(m, 'poison'):
            keywords['烈毒'] += 1
        if _f(m, 'divine_shield'):
            keywords['圣盾'] += 1
        if _f(m, 'taunt'):
            keywords['嘲讽'] += 1
        if _f(m, 'reborn'):
            keywords['复生'] += 1
        if _f(m, 'deathrattle'):
            keywords['亡语'] += 1
        if _f(m, 'windfury'):
            keywords['风怒'] += 1
        hit = match_key_card(cn_name(name))
        if hit and hit[2] not in seen:
            seen.add(hit[2])
            hits.append(hit)
    return races, keywords, hits


def detect_archetype(minions: list):
    """流派判定：种族随从数×2 + 核心卡信号加权（专属3/通用2）中的最高分；
    archetype_score = 最高分/(最高分+次高分+0.001)。
    返回 (流派名, 置信度0-1)；无随从或全平/无信号 → ('未成型', 0)。"""
    if not minions:
        return ('未成型', 0)
    scores = {}
    for m in minions:
        r = race_of(_f(m, 'name', '') or '')
        if r in RACE_NAMES:
            key = f'{r}流'
            scores[key] = scores.get(key, 0) + 2
        hit = match_key_card(cn_name(_f(m, 'name', '') or ''))
        if hit and hit[0] != 'AOE威胁':  # AOE 是威胁信号，不是流派
            scores[hit[0]] = scores.get(hit[0], 0) + hit[1]
    if not scores:
        return ('未成型', 0)
    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    top, second = ranked[0], (ranked[1] if len(ranked) > 1 else None)
    if top[1] <= 0 or (second and top[1] == second[1]):  # 无信号或全平 → 未成型
        return ('未成型', 0)
    conf = top[1] / (top[1] + (second[1] if second else 0) + 0.001)
    return (top[0], conf)


def _archetype_display(races: dict, hits: list, arch: str) -> str:
    """组合流派名：主流派 + 次级核心卡方向，如 野兽流·亡语铺场"""
    if arch == '未成型':
        return arch
    sub = None
    for s, w, _d in sorted(hits, key=lambda x: -x[1]):
        if s != 'AOE威胁' and s != arch:
            sub = s
            break
    if not sub:
        return arch
    flavor = {'亡语流': '亡语铺场'}.get(sub, sub)
    return f'{arch}·{flavor}'


def _weakness_list(arch: str, hits: list) -> list:
    """弱点：核心卡命中流派优先（瑞文怕先手被秒等），其次主流派，最多2条"""
    streams = [s for s, _w, _d in hits if s != 'AOE威胁' and s != arch] + [arch]
    out = []
    for s in streams:
        for w in _WEAKNESS.get(s, _WEAKNESS['未成型']):
            if w not in out:
                out.append(w)
        if len(out) >= 2:
            break
    return out[:2]


def _counter_list(arch: str, keywords: dict, hits: list) -> list:
    """应对建议：按 AOE→集火瑞文→圣盾挡毒 的顺序给出"""
    out = []
    if any('AOE' in w for w in _weakness_list(arch, hits)):
        out.append('站位分散')
    if arch == '亡语流' or any(s == '亡语流' for s, _w, _d in hits):
        out.append('优先集火瑞文')
    if keywords.get('烈毒'):
        out.append('留圣盾挡毒')
    return out or ['集火核心随从']


def _summary(races: dict, keywords: dict, arch: str, score: float) -> str:
    race_part = '、'.join(f'{c}个{r}' for r, c in races.items()) or '无明确种族'
    kw_part = '、'.join(f'{c}个{k}' for k, c in keywords.items() if c) or '无明显关键词'
    return f'{race_part}，{kw_part}；疑似{arch}（置信{score * 100:.0f}%）'


def analyze_team(minions: list) -> dict:
    """阵容分析 → {'races','keywords','key_cards','archetype','archetype_score','summary'}
    输入支持 dict 或 Minion 对象（有 name/atk 等属性的对象）"""
    minions = [m for m in (minions or []) if m]
    races, keywords, hits = _scan(minions)
    arch, score = detect_archetype(minions)
    key_cards = [h[2] for h in hits]
    return {'races': races, 'keywords': keywords, 'key_cards': key_cards,
            'archetype': arch, 'archetype_score': score,
            'summary': _summary(races, keywords, arch, score)}


def summarize_opponent(minions: list) -> str:
    """对手阵容分析人话：流派/置信、核心、威胁、弱点、应对；无随从返回固定提示
    输入支持 dict 或 Minion 对象"""
    minions = [m for m in (minions or []) if m]
    if not minions:
        return '对手随从不可见'
    races, keywords, hits = _scan(minions)
    arch, score = detect_archetype(minions)
    parts = [f'对手疑似【{_archetype_display(races, hits, arch)}】（置信{score * 100:.0f}%）']
    core = [h[2] for h in hits if h[0] != 'AOE威胁']
    if core:
        parts.append('核心' + '、'.join(core))
    threats = [f'{keywords[k]}个{k}' for k in ('烈毒', '圣盾', '风怒', '复生') if keywords.get(k)]
    if threats:
        parts.append('威胁：' + '+'.join(threats))
    weak = _weakness_list(arch, hits)
    if weak:
        parts.append('弱点：' + '、'.join(weak))
    parts.append('应对：' + '、'.join(_counter_list(arch, keywords, hits)))
    return '；'.join(parts)


def summarize_team(minions: list) -> str:
    """己方阵容摘要（analyze_team.summary 扩展：补核心卡与种族分布）；输入支持 dict 或 Minion 对象"""
    minions = [m for m in (minions or []) if m]
    if not minions:
        return '己方场上无随从'
    t = analyze_team(minions)
    extra = []
    if t['key_cards']:
        extra.append('核心：' + '、'.join(t['key_cards']))
    if t['races']:
        extra.append('种族：' + '、'.join(f'{r}×{c}' for r, c in t['races'].items()))
    return f"己方阵容：{t['summary']}" + (f"；{'；'.join(extra)}" if extra else '')


if __name__ == '__main__':
    import sys
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)

    def mk(name, **kw):
        m = {'name': name, 'atk': 1, 'hp': 1}
        m.update(kw)
        return m

    # 样例1：野兽流雏形（瑞文+鹦鹉+鱼饵+狼群领袖+2只野兽；混入卡ID走 card_db 种族路径）
    beasts = [mk('瑞文戴尔男爵', atk=2, hp=5), mk('巨大的金刚鹦鹉', atk=5, hp=4),
              mk('鱼饵', atk=3, hp=2), mk('狼群领袖', atk=2, hp=3),
              mk('BG19_010', atk=2, hp=2, deathrattle=[{'atk': 1, 'hp': 1}]),
              mk('BG19_010', atk=2, hp=2)]
    t1 = analyze_team(beasts)
    print('野兽流样例:', t1['archetype'], f"置信{t1['archetype_score']:.2f}",
          '| 核心:', t1['key_cards'], '| 种族:', t1['races'])
    print('  summarize_opponent:', summarize_opponent(beasts))
    print('  summarize_team    :', summarize_team(beasts))
    # 样例2：机械流
    mechs = [mk('机械地精', divine_shield=True), mk('机械士兵', taunt=True, divine_shield=True),
             mk('机械坦克', atk=5, hp=6)]
    t2 = analyze_team(mechs)
    print('机械流样例:', t2['archetype'], f"置信{t2['archetype_score']:.2f}",
          '| 关键词:', {k: v for k, v in t2['keywords'].items() if v})
    # 样例3：烈毒鱼人
    fish = [mk('毒鳍鱼人', poison=True), mk('军备鱼人', poison=True), mk('幼鳞鱼人', taunt=True)]
    t3 = analyze_team(fish)
    print('鱼人流样例:', t3['archetype'], f"置信{t3['archetype_score']:.2f}",
          '| 关键词:', {k: v for k, v in t3['keywords'].items() if v})
    print('  summarize_opponent:', summarize_opponent(fish))
    # 样例4：卡 ID 输入不崩溃（三种族各1 → 全平应判未成型）
    ids = [mk('BG25_008'), mk('BG19_010'), mk('BG21_020')]
    print('卡ID输入:', analyze_team(ids)['archetype'], '|', summarize_opponent(ids))
    # 样例5：空阵容
    print('空阵容:', analyze_team([])['archetype'], '|', summarize_opponent([]))
    # 样例6：Minion dataclass 对象输入（pet_window 集成路径，防回归）
    try:
        from core.battle_sim import Minion
        mobjs = [Minion(name='瑞文戴尔男爵', atk=2, hp=5), Minion(name='巨大的金刚鹦鹉', atk=5, hp=4),
                 Minion(name='鱼饵', atk=3, hp=2, poison=False)]
        t6 = analyze_team(mobjs)
        print('Minion对象输入:', t6['archetype'], f"置信{t6['archetype_score']:.2f}",
              '| 核心:', t6['key_cards'], '|', summarize_opponent(mobjs))
    except Exception as e:
        print('Minion对象输入 异常:', e)
