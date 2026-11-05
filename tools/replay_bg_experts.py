"""Reconstruct expert inputs from saved legal actions, without any API calls."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core.bg_cloud_policy import DeepSeekSeat
from core.bg_selfplay import Arena, load_engine, save_json, PROFILE, ENGINE_REVISION

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--engine',required=True);p.add_argument('--battles',required=True)
    p.add_argument('--output',required=True);p.add_argument('--worker',action='store_true',help=argparse.SUPPRESS)
    args=p.parse_args()
    source=Path(args.battles);data=json.loads(source.read_text(encoding='utf-8'))
    if len(data['games'])!=1:raise ValueError('Replay one saved eight-seat match at a time')
    game=data['games'][0]
    if game['profile']!=PROFILE or game['engine_revision']!=ENGINE_REVISION:
        raise ValueError('Saved game uses different rules')
    if not args.worker:
        env=os.environ.copy();env['PYTHONHASHSEED']=str(game['seed'] % 2**32)
        return subprocess.run([sys.executable,*sys.argv,'--worker'],env=env,timeout=45).returncode
    if Path(args.output).exists():raise FileExistsError('Choose a new replay output')
    class Replay:
        index=0
        observations=[]
        def pick(self,observation):
            if self.index>=len(data['cloud']['records']):return None
            record=data['cloud']['records'][self.index]
            digest=hashlib.sha256(json.dumps(observation,sort_keys=True,ensure_ascii=False).encode()).hexdigest()[:24]
            if digest!=record['state_id']:raise ValueError('Replay diverged before expert action')
            self.observations.append(dict(record=record,observation=observation))
            self.index+=1
            return record if record['ok'] else None
    replay=Replay()
    result=Arena(load_engine(args.engine)).run([DeepSeekSeat(replay,i) for i in range(8)],game['seed'])
    if result['placements']!=game['placements'] or replay.index!=len(data['cloud']['records']):
        raise ValueError('Saved match did not reproduce')
    save_json(args.output,dict(source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                              profile=PROFILE,engine_revision=ENGINE_REVISION,
                              placements_verified=True,api_calls=0,observations=replay.observations))
    print(dict(replayed_expert_states=replay.index,placements_verified=True,api_calls=0))
    return 0

if __name__=='__main__':sys.exit(main())
