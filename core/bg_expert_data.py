"""Validate expert action labels from the matching offline simulator profile."""
import hashlib
import json
import math
from pathlib import Path

from core.bg_selfplay import ENGINE_REVISION, FEATURE_DIM, PROFILE


def load_expert_samples(path):
    path = Path(path)
    if path.stat().st_size > 50_000_000:
        raise ValueError('Expert trajectory exceeds 50 MB')
    raw = path.read_bytes()
    data = json.loads(raw)
    samples = []
    for game in data.get('games',[]):
        if game.get('profile') != PROFILE or game.get('engine_revision') != ENGINE_REVISION:
            raise ValueError('Expert profile or engine revision mismatch')
        if not game.get('finished') or game.get('action_limit_hits'):
            raise ValueError('Expert battle did not finish cleanly')
        for trajectory in game.get('trajectories',[]):
            for step in trajectory:
                if step.get('decision',{}).get('source') != 'deepseek_expert':
                    continue
                rows, action = step.get('x'), step.get('action')
                if (not isinstance(rows,list) or not rows or len(rows)>256 or type(action) is not int
                        or not 0 <= action < len(rows)):
                    raise ValueError('Expert label is outside its legal candidates')
                if any(not isinstance(row,list) or len(row)!=FEATURE_DIM or
                       any(type(v) not in (int,float) or not math.isfinite(v) for v in row) for row in rows):
                    raise ValueError('Expert features do not match the finite feature schema')
                samples.append(dict(x=rows,teacher=action,action=action,source='deepseek_expert'))
    if not samples:
        raise ValueError('No admitted DeepSeek expert action labels')
    return samples, dict(sha256=hashlib.sha256(raw).hexdigest(),samples=len(samples),
                         label_quality='legal choices only; strategic optimality not established')
