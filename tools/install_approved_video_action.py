"""Install the exact locally previewed clip explicitly accepted by the user."""
import json
import shutil
from pathlib import Path
from core.avatar_review import frames_digest, approved_action

ROOT=Path(__file__).resolve().parents[1]


def main():
    source=ROOT/'runtime/video-action-review-20261102/look-up-step-v3'
    base=ROOT/'resources/actions/task-motion'
    target=base/'look-up-step'
    expected=frames_digest(source/'frames')
    if target.exists():
        if not (target/'frames').is_dir() or frames_digest(target/'frames') != expected:
            raise RuntimeError('Existing installed bundle differs; preserve it for review')
    else:
        shutil.copytree(source/'frames',target/'frames')
    review=dict(schema=2,status='approved',reviewer='user / local transition preview',
                playback='once',frames_sha256=expected,
                checks=dict(identity=False,identity_variation_accepted=True,
                            continuous_motion=True,no_ghosts=True,anatomy=True,
                            loop_seam=False,transition_variation_accepted=True),
                user_approval=dict(by='user',quote='执行吧，这个动作层面我觉得是ok的',
                                   scope='look-up-step-v3 including the displayed resident transition'),
                notes=['Appearance variation was shown and accepted; no claim of exact identity',
                       'One-shot only: different endpoints must never be labelled a seamless loop'])
    (target/'visual-review.json').write_text(json.dumps(review,ensure_ascii=False,indent=2),encoding='utf-8')
    provenance=json.loads((source/'metadata.json').read_text(encoding='utf-8'))
    provenance.update(installed=True,states=['thinking','working'],
                      attribution='AF小钢 / 哔哩哔哩：咕咕嘎嘎跳舞纯享版',
                      redistribution='not_verified; local installation only')
    # Keep only source/processing facts; no machine paths are needed at runtime.
    for key in ('source','reused_masks'):provenance.pop(key,None)
    (target/'source.json').write_text(json.dumps(provenance,ensure_ascii=False,indent=2),encoding='utf-8')
    if not approved_action(target/'frames'):raise RuntimeError('Installed approval does not match frame content')
    manifest=json.loads((base/'manifest.json').read_text(encoding='utf-8'))
    for state in ('thinking','working'):
        manifest['states'][state]=dict(frames='look-up-step/frames',native_fps=30)
    manifest['note']='用户已接受本段动作及形象差异；54原生帧/30fps，单次播放。任务间隔10秒，语音、拖拽、困倦和取消优先。'
    (base/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(installed=True,frames=54,fps=30,states=['thinking','working'],one_shot=True)))


if __name__=='__main__':main()
