"""Paired offline evaluation; a laboratory result never certifies live rules."""
import random
from core.bg_selfplay import top4_credit


def compare(baseline, candidate, *, seed=8241):
    if not baseline or len(baseline) != len(candidate):
        raise ValueError('Matched seed/seat results required')
    for a, b in zip(baseline, candidate):
        if (a['seed'], a['seat']) != (b['seed'], b['seat']):
            raise ValueError('Evaluation schedule mismatch')
    gains = [a['placements'][a['seat']]-b['placements'][b['seat']]
             for a,b in zip(baseline,candidate)]
    n = len(gains)
    rng = random.Random(seed)
    bootstrap = sorted(sum(rng.choice(gains) for _ in gains)/n for _ in range(2000))
    def stats(rows):
        return dict(mean_placement=sum(r['placements'][r['seat']] for r in rows)/n,
                    top4_rate=sum(top4_credit(r['placements'],r['seat']) for r in rows)/n)
    a, b = stats(baseline), stats(candidate)
    lower, upper = bootstrap[49], bootstrap[1949]
    top4_gain = b['top4_rate']-a['top4_rate']
    return dict(games=n, baseline=a, candidate=b, mean_placement_gain=sum(gains)/n,
                paired_bootstrap_95=[lower,upper], top4_gain=top4_gain,
                lab_pass=n >= 64 and lower > 0 and top4_gain >= .05,
                live_deployable=False,
                limitation='Old restricted rules and heuristic opponents; not a ladder strength estimate')
