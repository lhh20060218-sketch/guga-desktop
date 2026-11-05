"""Read-only rules passport for the pinned external laboratory engine."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core.bg_selfplay import load_engine, PROFILE, save_json

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--engine',required=True)
    p.add_argument('--output',required=True)
    args=p.parse_args()
    if Path(args.output).exists():raise FileExistsError('Choose a new audit output')
    engine=load_engine(args.engine)
    root=engine['root']
    summary=json.loads((root/'data/bg_summary.json').read_text(encoding='utf-8'))
    result=subprocess.run([sys.executable,'-X','utf8',str(root/'tools/audit_card_registry_v2.py'),'--strict'],
                          cwd=root,capture_output=True,text=True,encoding='utf-8',timeout=30)
    report=dict(schema=1,profile=PROFILE,engine_revision=engine['revision'],
                data_patch=summary['patch'],full_current_rules=False,live_deployable=False,
                pool_summary=summary,registry_audit_exit=result.returncode,
                registry_audit=result.stdout,registry_error=result.stderr,
                data_sha256={f.name:hashlib.sha256(f.read_bytes()).hexdigest()
                             for f in sorted((root/'data').glob('bg_*.json'))},
                unsupported=['hero selection and powers','tavern spell decisions and generated spells',
                             'learned discover/targeting','board positioning','live tribe rotations',
                             'current deities/aberrations and complete seasonal rules'],
                excluded_minions=['BG33_319'],
                qualification='Registry presence does not prove effect semantics or combat accuracy')
    save_json(args.output,report)
    print(dict(profile=PROFILE,data_patch=summary['patch'],audit_exit=result.returncode,
               live_deployable=False))
    return 0

if __name__=='__main__':sys.exit(main())
