"""Bounded NumPy inference for the trained offline Battlegrounds policy.

The 128-seed laboratory champion is used as an advisory prior for the current
legal live actions. Its old rule subset is not treated as live authority; the
current DeepSeek selector still chooses only observed client candidates, and the
action must pass log and vision acknowledgement.
"""
import hashlib
import json
import math
from pathlib import Path
import threading

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = ROOT / 'data/bg_agent/live_prior_20261020.json'
_CACHE = None
_LOCK = threading.Lock()
KEYWORDS = ('divine_shield', 'taunt', 'reborn', 'windfury', 'venomous', 'cleave',
            'battlecry', 'deathrattle')


def _load(path=None):
    global _CACHE
    target = Path(path or MODEL_PATH)
    with _LOCK:
        if _CACHE is not None and _CACHE['path'] == target:
            return _CACHE
        if target.stat().st_size > 10_000_000:
            raise ValueError('训练先验文件超过 10 MB')
        data = json.loads(target.read_text(encoding='utf-8'))
        if data.get('schema') != 1 or data.get('feature_dim') != 48:
            raise ValueError('训练先验结构不匹配')
        weights = {name: np.asarray(value, dtype=np.float32)
                   for name, value in data['weights'].items()}
        if weights['w1'].shape != (64, 48) or weights['w2'].shape != (64, 64) or weights['w3'].shape != (1, 64):
            raise ValueError('训练先验矩阵尺寸不匹配')
        _CACHE = dict(path=target, data=data, weights=weights)
        return _CACHE


def _number(value, default=0.):
    return float(value) if type(value) in (int, float) and math.isfinite(value) else float(default)


def _gold(state):
    res = state.get('resources') or {}
    return max(0., _number(res.get('RESOURCES')) - _number(res.get('RESOURCES_USED')) + _number(res.get('TEMP_RESOURCES')))


def _card_meta(card, metadata):
    card_id = str(card.get('CARD_ID') or '')
    meta = dict(metadata.get(card_id) or {})
    if not meta:
        try:
            from core.bg_current_knowledge import lookup
            meta = lookup(card_id) or {}
        except Exception:
            meta = {}
    return meta


def _card_stats(card, meta):
    atk = _number(card.get('ATK'), meta.get('attack') or 0)
    hp = _number(card.get('HEALTH'), meta.get('health') or 0) - _number(card.get('DAMAGE'))
    tier = _number(meta.get('tech_level') or meta.get('tier'), 1)
    keywords = {str(x).lower() for x in (meta.get('keywords') or [])}
    for key in KEYWORDS:
        if card.get(key.upper()) in (1, True):
            keywords.add(key)
    return atk, max(0., hp), tier, keywords


def features(state, actions, metadata=None):
    metadata = metadata or {}
    own = state.get('controller')
    entities = state.get('entities') or {}
    board = [e for e in entities.values() if e.get('CONTROLLER') == own and e.get('ZONE') == 'PLAY' and e.get('CARDTYPE') == 'MINION']
    hand = [e for e in entities.values() if e.get('CONTROLLER') == own and e.get('ZONE') == 'HAND']
    board_cards = [(_card_stats(e, _card_meta(e, metadata))) for e in board]
    strength = lambda values: values[0] + values[1] + (5 if 'divine_shield' in values[3] else 0)
    strengths = [strength(card) for card in board_cards]
    weak = min(strengths, default=0.)
    best = max([strength(_card_stats(entities.get(str(a.get('target') or a.get('entity_id')), {}), _card_meta(entities.get(str(a.get('target') or a.get('entity_id')), {}), metadata))) for a in actions], default=0.)
    races = [str(_card_meta(e, metadata).get('race') or '').upper() for e in board]
    races = [r for r in races if r and r not in ('ALL', 'NONE')]
    dominant = max(set(races), key=races.count) if races else ''
    dominant_share = races.count(dominant) / len(races) if dominant else 0.
    shop = [entities.get(str(a.get('target'))) for a in actions if a.get('kind') == 'BUY']
    shop = [x for x in shop if isinstance(x, dict)]
    shop_minions = sum(str(_card_meta(x, metadata).get('card_type') or 'minion') == 'minion' for x in shop)
    shop_spells = max(0, len(shop) - shop_minions)
    tier = _number(state.get('tier'), 1)
    state_row = [min(1., _number(state.get('round'), 1) / 20), min(1., _gold(state) / 10),
                 min(1., (_number(state.get('health')) + _number(state.get('armor'))) / 40), tier / 6,
                 min(1., _number(state.get('upgrade_cost'), min(10, tier + 6)) / 10), len(board) / 7,
                 len(hand) / 10, sum(strengths) / 200, shop_minions / 7, shop_spells / 7,
                 dominant_share, float(state.get('frozen') is True)]
    action_types = ('END', 'BUY', 'PLAY', 'BUY_SPELL', 'PLAY_SPELL', 'SELL', 'REFRESH', 'FREEZE', 'UPGRADE')
    rows = []
    for action in actions:
        kind = str(action.get('kind') or '')
        eid = str(action.get('target') or action.get('entity_id'))
        card = entities.get(eid, {})
        meta = _card_meta(card, metadata)
        atk, hp, card_tier, keywords = _card_stats(card, meta)
        card_strength = atk + hp + (5 if 'divine_shield' in keywords else 0)
        card_id = str(card.get('CARD_ID') or '')
        copies = sum(1 for x in board + hand if str(x.get('CARD_ID') or '') == card_id) / 3 if card_id else 0
        race = str(meta.get('race') or '').upper()
        synergy = float(bool(dominant and race in ('ALL', dominant)))
        position = _number(action.get('position'), 0) / 7 if action.get('position') is not None else 0
        values = [atk / 30, hp / 30, card_tier / 6,
                  *[float(x in keywords) for x in KEYWORDS], copies,
                  (card_strength - weak) / 30, (best - card_strength) / 30, position, synergy,
                  (card_tier - tier) / 6]
        bits = hashlib.blake2b((card_id or kind).encode(), digest_size=8).digest()
        identity = [float((int.from_bytes(bits, 'big') >> i) & 1) for i in range(10)]
        rows.append([float(kind == name) for name in action_types] + state_row + values + identity)
    if any(len(row) != 48 for row in rows):
        raise ValueError('训练先验特征维度错误')
    return rows


def rank(state, actions, metadata=None, path=None):
    if not actions:
        return dict(available=False, reason='没有合法候选', ranked=[])
    try:
        model = _load(path)
        from core.bg_version import client_patch
        live_patch=client_patch();training_patch=str(model['data'].get('training_patch',''))
        if not training_patch or training_patch!=live_patch:
            return dict(available=False,reason='version_mismatch',training_patch=training_patch,
                        live_patch=live_patch,ranked=[])
        x = np.asarray(features(state, actions, metadata), dtype=np.float32)
        a1 = np.tanh(x @ model['weights']['w1'].T + model['weights']['b1'])
        a2 = np.tanh(a1 @ model['weights']['w2'].T + model['weights']['b2'])
        logits = (a2 @ model['weights']['w3'].T + model['weights']['b3']).reshape(-1)
        logits = np.where(np.isfinite(logits), logits, -1e9)
        probability = np.exp(logits - logits.max())
        probability /= max(probability.sum(), 1e-12)
        order = np.argsort(-probability)[:min(3, len(actions))]
        ranked = [dict(action_id=actions[i]['action_id'], score=round(float(logits[i]), 6),
                       probability=round(float(probability[i]), 6)) for i in order]
        return dict(available=True, ranked=ranked, chosen_action_id=ranked[0]['action_id'],
                    training_patch=training_patch,
                    checkpoint=str(model['data'].get('checkpoint', '')),
                    limitation=str(model['data'].get('limitation', '')))
    except (OSError, ValueError, KeyError, IndexError) as exc:
        return dict(available=False, reason=type(exc).__name__, ranked=[])
