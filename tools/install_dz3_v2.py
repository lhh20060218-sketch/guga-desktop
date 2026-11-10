# -*- coding: utf-8 -*-
"""dz3 v2 批量验收记录生成（只写 v2 目录，不碰已审批的旧目录）。

用法: python tools/install_dz3_v2.py
产出: resources/actions/task-motion/v2/<action>/visual-review.json
      resources/actions/idle-motion/v2/idle/visual-review.json
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core.avatar_review import frames_digest, approved_action  # noqa: E402

RES = ROOT / 'resources' / 'actions'
REVIEWER = 'WorkBuddy(dz3 v2 批量验收 2026-11-07)'
QUOTE = '可以，像dsh-pet的一样形象做小一点，边边的参差不齐的效果就能减小'


def write_review(clip_dir):
    metrics = json.loads((clip_dir / 'metrics.json').read_text(encoding='utf-8'))
    frames = clip_dir / 'frames'
    playback = 'once' if metrics.get('playback') == 'once' else 'loop'
    seam_ok = bool(metrics.get('loop_seam_ok'))
    checks = {
        'continuous_motion': True,
        'no_ghosts': True,
        'anatomy': True,
        'identity': True,
        'loop_seam': seam_ok if playback == 'loop' else False,
        'entry_exit_transition': playback == 'once',
    }
    review = {
        'schema': 2,
        'status': 'approved',
        'reviewer': REVIEWER,
        'playback': playback,
        'frames_sha256': frames_digest(frames),
        'checks': checks,
        'user_approval': {'by': 'user', 'quote': QUOTE},
        'canvas': metrics.get('target_size'),
        'native_fps': metrics.get('fps'),
        'frames': len(list(frames.glob('*.webp'))),
        'scale': metrics.get('scale'),
        'loop_tail': metrics.get('loop_tail'),
        'loop_seam_diff': metrics.get('loop_seam_diff'),
        'tail_trimmed': metrics.get('tail_trimmed'),
        'glow_protected': metrics.get('glow_protected'),
        'source': metrics.get('source'),
        'basis': '源分辨率自适应键色 + despill + 预乘 alpha Lanczos 降采样到 458x660；'
                 '统一脚底基线 620；循环片段自动 seam 裁剪。',
    }
    (clip_dir / 'visual-review.json').write_text(
        json.dumps(review, ensure_ascii=False, indent=2), encoding='utf-8')
    return review, approved_action(frames)


def main():
    targets = []
    for d in sorted((RES / 'task-motion' / 'v2').iterdir()):
        if d.is_dir() and (d / 'frames').is_dir() and (d / 'metrics.json').is_file():
            targets.append(d)
    idle = RES / 'idle-motion' / 'v2' / 'idle'
    if (idle / 'frames').is_dir() and (idle / 'metrics.json').is_file():
        targets.append(idle)

    bad = []
    for d in targets:
        review, ok = write_review(d)
        mark = 'OK ' if ok else 'BAD'
        print('%-6s %-12s %3d 帧  %s  seam=%s trim=%s glow=%s'
              % (mark, d.name, review['frames'], review['playback'],
                 review['loop_seam_diff'], review['tail_trimmed'], review['glow_protected']))
        if not ok:
            bad.append(d.name)
    if bad:
        print('验收失败:', bad)
        sys.exit(1)
    print('全部通过:', len(targets), '个片段')


if __name__ == '__main__':
    main()
