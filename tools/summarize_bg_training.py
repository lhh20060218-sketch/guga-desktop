"""Publish a read-only training summary to the pet; never activate weights."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core.bg_selfplay import PROFILE


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--report',action='append',required=True)
    p.add_argument('--independent',action='append',default=[])
    p.add_argument('--output',required=True)
    p.add_argument('--summary',required=True)
    p.add_argument('--next-step',required=True)
    args=p.parse_args()
    candidates=[]
    for name in args.report:
        path=Path(name);data=json.loads(path.read_text(encoding='utf-8'))
        if data.get('status')!='complete' or data.get('profile')!=PROFILE:
            raise ValueError('Only completed matching-profile reports are accepted')
        ppo=data['evaluations']['ppo'];base=data['evaluations']['heuristic']
        checkpoint=path.parent/'ppo.pt'
        if not checkpoint.is_file():raise FileNotFoundError(checkpoint)
        candidates.append(dict(name=path.parent.name,games=ppo['games'],
            mean_placement=ppo['mean_placement'],top4_rate=ppo['top4_rate'],
            baseline_mean_placement=base['mean_placement'],baseline_top4_rate=base['top4_rate'],
            lab_pass=False,diagnostic_only=True,
            checkpoint_sha256=hashlib.sha256(checkpoint.read_bytes()).hexdigest()))
    independent={}
    for name in args.independent:
        path=Path(name);data=json.loads(path.read_text(encoding='utf-8'))
        if data.get('status')=='complete':
            independent[data.get('checkpoint_sha256')]=dict(
                path=str(path),comparison=data.get('comparison'))
    for candidate in candidates:
        gate=independent.get(candidate['checkpoint_sha256'])
        if gate:
            candidate['independent_gate']=gate
            comparison=gate.get('comparison') or {}
            candidate['lab_pass']=bool(comparison.get('lab_pass'))
            candidate['independent_games']=comparison.get('games')
            candidate['independent_mean_placement']=(comparison.get('candidate') or {}).get('mean_placement')
            candidate['independent_top4_rate']=(comparison.get('candidate') or {}).get('top4_rate')
            candidate['independent_baseline_mean']=(comparison.get('baseline') or {}).get('mean_placement')
            candidate['independent_baseline_top4']=(comparison.get('baseline') or {}).get('top4_rate')
    candidates.sort(key=lambda c:(not c['lab_pass'],c['mean_placement'],-c['top4_rate']))
    payload=dict(schema=1,profile=PROFILE,active_for_live_decisions=False,
                 candidates=candidates,summary=args.summary,next_step=args.next_step,
                 disclosure='Diagnostic results are not independent certification or live ladder strength')
    target=Path(args.output);target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    print(dict(candidates=len(candidates),best=candidates[0]['name'],active=False))

if __name__=='__main__':main()
