"""Copy an independently verified laboratory policy into a versioned champion slot."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core.bg_selfplay import ENGINE_REVISION, PROFILE


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--report',required=True);p.add_argument('--checkpoint',required=True)
    p.add_argument('--output-dir',required=True);args=p.parse_args()
    data=json.loads(Path(args.report).read_text(encoding='utf-8'))
    checkpoint=Path(args.checkpoint);digest=hashlib.sha256(checkpoint.read_bytes()).hexdigest()
    if data.get('status')!='complete' or data.get('profile')!=PROFILE \
            or data.get('engine_revision')!=ENGINE_REVISION:
        raise ValueError('Rule profile or engine revision mismatch')
    if digest!=data.get('checkpoint_sha256'):raise ValueError('Checkpoint hash mismatch')
    comparison=data.get('comparison') or {}
    if not comparison.get('lab_pass'):raise PermissionError('Independent laboratory gate did not pass')
    output=Path(args.output_dir);output.mkdir(parents=True,exist_ok=False)
    shutil.copyfile(checkpoint,output/'champion.pt')
    manifest=dict(schema=1,profile=PROFILE,engine_revision=ENGINE_REVISION,
                  checkpoint_sha256=digest,independent_report_sha256=hashlib.sha256(
                      Path(args.report).read_bytes()).hexdigest(),comparison=comparison,
                  scope='offline laboratory champion only',live_adapter='not enabled')
    (output/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print(dict(promoted=True,output=str(output),live_adapter='not enabled'))

if __name__=='__main__':main()
