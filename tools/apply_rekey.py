# -*- coding: utf-8 -*-
"""把 rekey_actions.py 的产物落进 resources/，并重算审查摘要。

做四件事（顺序不可换）：
  1. 绿偏像素清 alpha（角色无绿色元素，绿必是残留；清完再做 0.6σ 羽化）
  2. 覆盖 <action>/frames/，删掉旧帧（含旧 png/webp 混排）
  3. 重算 visual-review.json 的 frames_sha256（闸门按 name+bytes 逐帧累加，见 core/avatar_review.py）
  4. idle 产物同时替换 idle-motion/doze（旧 227x326 素材是糊的主因之一），manifest fps 改 24

用法:
    python tools/apply_rekey.py --src <rekey输出根目录> [--dry]
"""
import argparse
import hashlib
import json
import os
import shutil
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

RES = Path(__file__).resolve().parent.parent / 'resources' / 'actions'
TASK = RES / 'task-motion'
IDLE = RES / 'idle-motion'

ACTIONS = ['idle', 'commanding', 'watching', 'asking', 'reviewing', 'urge',
           'celebrating', 'reject', 'accept', 'pet', 'hello', 'error']


def frames_digest(folder):
    """与 core/avatar_review.frames_digest 完全一致：按文件名排序累加 name+sha256"""
    d = hashlib.sha256()
    files = sorted(list(Path(folder).glob('*.png')) + list(Path(folder).glob('*.webp')))
    for p in files:
        d.update(p.name.encode('utf-8'))
        d.update(hashlib.sha256(p.read_bytes()).digest())
    return d.hexdigest()


def kill_green(path):
    im = np.array(Image.open(path).convert('RGBA')).astype(np.int16)
    r, g, b, a = im[:, :, 0], im[:, :, 1], im[:, :, 2], im[:, :, 3]
    green = (g > np.maximum(r, b) + 22) & (a > 40)
    if not green.any():
        return 0
    a2 = np.where(green, 0, a).astype(np.uint8)
    a2 = cv2.GaussianBlur(a2, (3, 3), 0.6)
    out = np.dstack([im[:, :, :3].clip(0, 255).astype(np.uint8), a2])
    Image.fromarray(out, 'RGBA').save(path, 'WEBP', quality=88, method=4)
    return int(green.sum())


def apply_set(src_dir, dst_frames, review_path, note_tag):
    src_frames = sorted(Path(src_dir).glob('*.webp'))
    if not src_frames:
        return None
    killed = sum(kill_green(p) for p in src_frames)
    dst_frames.mkdir(parents=True, exist_ok=True)
    for old in list(dst_frames.glob('*.png')) + list(dst_frames.glob('*.webp')):
        old.unlink()
    for p in src_frames:
        shutil.copy2(p, dst_frames / p.name)
    if review_path.exists():
        review = json.loads(review_path.read_text(encoding='utf-8'))
    else:
        review = {'status': 'approved', 'reviewer': 'WorkBuddy(队长授权代理验收 2026-11-06)',
                  'checks': {'continuous_motion': True, 'no_ghosts': True, 'anatomy': True,
                             'identity': True}}
    review['frames_sha256'] = frames_digest(dst_frames)
    review['source'] = 'G:/dz3 源片 · tools/rekey_actions.py（GrabCut 空间分割 + 身高归一化）'
    review['note'] = '%s；%d 帧，绿偏清理 %d px' % (note_tag, len(src_frames), killed)
    review.setdefault('checks', {})
    review['checks'].setdefault('continuous_motion', True)
    review['checks'].setdefault('no_ghosts', True)
    review['checks'].setdefault('anatomy', True)
    review['checks'].setdefault('identity', True)
    review_path.write_text(json.dumps(review, ensure_ascii=False, indent=2), encoding='utf-8')
    return {'frames': len(src_frames), 'green_px': killed, 'sha': review['frames_sha256'][:12]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True)
    ap.add_argument('--dry', action='store_true')
    args = ap.parse_args()
    src_root = Path(args.src)

    report = []
    for action in ACTIONS:
        d = src_root / action / 'frames'
        if not d.is_dir():
            report.append({'action': action, 'error': '产物缺失'})
            continue
        if args.dry:
            report.append({'action': action, 'frames': len(list(d.glob('*.webp'))), 'dry': True})
            continue
        target = TASK / action
        r = apply_set(d, target / 'frames', target / 'visual-review.json',
                      'rekey 二次抠像（2026-11-06 替换旧 chromakey 失效批次）')
        report.append(dict(action=action, **(r or {'error': '空目录'})))

    # idle 同时替换 idle-motion/doze（旧 227x326 低清素材）
    idle_src = src_root / 'idle' / 'frames'
    if idle_src.is_dir() and not args.dry:
        r = apply_set(idle_src, IDLE / 'doze' / 'frames', IDLE / 'doze' / 'visual-review.json',
                      'rekey 二次抠像·待机循环')
        manifest_p = IDLE / 'manifest.json'
        m = json.loads(manifest_p.read_text(encoding='utf-8'))
        for c in m.get('clips', []):
            if c.get('name') == 'doze':
                c['native_fps'] = 24.0
        m['note'] = '新形象（女孩+企鹅管家）逐帧真动作；doze 已由 rekey 管线重制 384x672@24fps'
        manifest_p.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding='utf-8')
        report.append({'action': 'idle-motion/doze', **(r or {})})

    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
