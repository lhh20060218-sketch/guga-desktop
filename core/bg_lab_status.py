"""Small read-only training summary exposed to the pet; never loads policy weights."""
import json
from pathlib import Path

MANIFEST = Path(__file__).resolve().parents[1]/'runtime/bg-lab/training-status.json'

def training_status(path=None):
    path=Path(path) if path else MANIFEST
    base=dict(available=False,active_for_live_decisions=False)
    try:
        if path.stat().st_size>100_000:return dict(base,error='Training manifest exceeds size limit')
        data=json.loads(path.read_text(encoding='utf-8'))
        if data.get('schema')!=1 or not isinstance(data.get('candidates'),list):
            return dict(base,error='Training manifest schema mismatch')
        champion=data.get('champion') if isinstance(data.get('champion'),dict) else None
        # No manifest field may switch the live executor to obsolete lab rules.
        return dict(available=True,active_for_live_decisions=False,
                    profile=str(data.get('profile',''))[:100],
                    summary=str(data.get('summary',''))[:1200],
                    candidates=[{k:c.get(k) for k in ('name','games','mean_placement','top4_rate','lab_pass',
                                                        'independent_games','independent_mean_placement',
                                                        'independent_top4_rate','independent_baseline_mean',
                                                        'independent_baseline_top4')}
                                for c in data['candidates'][:4]],
                    next_step=str(data.get('next_step',''))[:400],
                    champion=({k:champion.get(k) for k in
                               ('name','independent_games','mean_placement','top4_rate',
                                'baseline_mean_placement','baseline_top4_rate','lab_pass',
                                'live_deployable','reason')} if champion else None))
    except FileNotFoundError:
        return base
    except (OSError,ValueError,TypeError,AttributeError):
        return dict(base,error='Training manifest unavailable')
