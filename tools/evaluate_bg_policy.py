"""Finite, fresh-seed paired evaluation of a fixed laboratory checkpoint."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core.bg_selfplay import Arena, KINDS, PROFILE, load_engine, save_json, teacher_policy
from core.bg_training_gate import compare


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--engine',required=True)
    p.add_argument('--checkpoint',required=True)
    p.add_argument('--output',required=True)
    p.add_argument('--games',type=int,default=64)
    p.add_argument('--seed',type=int,default=2041000)
    p.add_argument('--baseline-report',help='Reuse the exact completed baseline schedule; no new baseline games')
    p.add_argument('--max-seconds',type=int,default=330)
    p.add_argument('--worker',action='store_true',help=argparse.SUPPRESS)
    args=p.parse_args()
    if not 8 <= args.games <= 128 or not 30 <= args.max_seconds <= 600:
        p.error('Evaluation budget out of range')
    if not args.worker:
        env=os.environ.copy();env['PYTHONHASHSEED']=str(args.seed % 2**32)
        try:
            return subprocess.run([sys.executable,*sys.argv,'--worker'],env=env,
                                  timeout=args.max_seconds+10).returncode
        except subprocess.TimeoutExpired:
            print('Evaluation worker terminated at budget',file=sys.stderr)
            return 124
    output=Path(args.output)
    if output.exists():raise FileExistsError('Evaluation output already exists')
    import torch
    from core.bg_policy import LabPolicy
    torch.set_num_threads(2)
    model=LabPolicy.load(args.checkpoint)
    arena=Arena(load_engine(args.engine))
    report=dict(checkpoint_sha256=hashlib.sha256(Path(args.checkpoint).read_bytes()).hexdigest(),
                profile=PROFILE,engine_revision=arena.e['revision'],
                schedule=dict(seed=args.seed,games=args.games),results={},status='running',
                live_deployable=False)
    started=time.monotonic()
    try:
        schedule=[('heuristic',teacher_policy),('candidate',model.choose)]
        if args.baseline_report:
            raw=Path(args.baseline_report).read_bytes()
            previous=json.loads(raw)
            if (previous.get('status')!='complete' or previous.get('profile')!=PROFILE or
                    previous.get('engine_revision')!=arena.e['revision'] or
                    previous.get('schedule')!=report['schedule']):
                raise ValueError('Baseline rules or seed schedule mismatch')
            baseline=previous['results']['heuristic']
            if [(r['seed'],r['seat']) for r in baseline['games']] != [(args.seed+i,i%8) for i in range(args.games)]:
                raise ValueError('Incomplete baseline schedule')
            report['results']['heuristic']=baseline
            report['baseline_report_sha256']=hashlib.sha256(raw).hexdigest()
            schedule=schedule[1:]
        for name,policy in schedule:
            rows=[];mistakes=decisions=0
            def counted(x,teacher):
                nonlocal mistakes,decisions
                chosen=policy(x,teacher);decisions+=1
                mistakes+=bool(x[chosen][KINDS.index("END")] == 1 and
                               x[teacher][KINDS.index("PLAY")] == 1)
                return chosen
            for i in range(args.games):
                if time.monotonic()-started > args.max_seconds:raise TimeoutError('Evaluation stage budget')
                seat=i%8;policies=[teacher_policy]*8;policies[seat]=counted
                result=arena.run(policies,args.seed+i)
                if not result['finished'] or result['action_limit_hits']:
                    raise RuntimeError('Incomplete evaluation game')
                rows.append(dict(seed=result['seed'],seat=seat,placements=result['placements']))
                report['results'][name]=dict(games=rows,decisions=decisions,
                                             ends_with_playable_minion=mistakes)
                save_json(output,report)
            print(f'{name}: {len(rows)} games; avoidable ends={mistakes}',flush=True)
        report['comparison']=compare(report['results']['heuristic']['games'],
                                     report['results']['candidate']['games'])
        report['status']='complete'
    except Exception as exc:
        report.update(status='failed',error=type(exc).__name__+': '+str(exc))
        raise
    finally:
        report['elapsed_seconds']=round(time.monotonic()-started,2)
        save_json(output,report)
    print(report['comparison'],flush=True)
    return 0

if __name__=='__main__':sys.exit(main())
