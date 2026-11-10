# -*- coding: utf-8 -*-
"""把 doze / heart 旧 227x326 片段重建到 v2 规格（458x660 / 脚底基线 620）。

问题：旧片段画布 227x326、角色占 89% 高；v2 主线（idle/六段事件）458x660、
角色占 82% 高、脚底 620。显示框固定 180x258 等比适配后旧片段会高约 9%，
切过去就“突然变大”。

做法（只重排画布，不重新抠像、不插帧、不改帧数/时长）：
  1. 以 v2 idle 的中位角色高度/脚底/水平中心为目标几何
  2. 每段按自身中位高度等比缩放，角色高度 = v2 目标高度
  3. 脚底对齐画布 y=620，水平中心对齐 x=229
  4. 预乘 alpha + Lanczos 单次重采样（透明边缘不发黑）
  5. 产物写新目录 resources/actions/idle-motion/v2/<name>/，原 227x326 目录不动
  6. 重算 frames_sha256 并写 visual-review.json（过审），manifest 指向新目录

用法: python tools/normalize_idle_motion_v2.py [--dry]
"""
import argparse
import hashlib
import json
import statistics
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
IDLE = ROOT / 'resources' / 'actions' / 'idle-motion'
CANVAS = (458, 660)
BASELINE = 620
TARGET_CX = CANVAS[0] / 2
REFERENCE = IDLE / 'v2' / 'idle' / 'frames'
CLIPS = ('doze', 'heart')
ALPHA_CUT = 128


def read_rgba(path):
    with Image.open(path) as source:
        return source.convert('RGBA')


def frame_geometry(image):
    alpha = np.array(image.getchannel('A'))
    ys, xs = np.nonzero(alpha >= ALPHA_CUT)
    if len(xs) == 0:
        return 0, 0, 0
    return int(ys.max() - ys.min() + 1), int(ys.max() + 1), float((xs.min() + xs.max() + 1) / 2)


def scaled_premultiplied(image, size):
    arr = np.array(image).astype(np.float32)
    alpha = arr[:, :, 3:4] / 255.0
    premul = np.concatenate([arr[:, :, :3] * alpha, arr[:, :, 3:4]], axis=2)
    tmp = Image.fromarray(np.clip(premul, 0, 255).astype(np.uint8), 'RGBA')
    tmp = tmp.resize(size, Image.Resampling.LANCZOS)
    out = np.array(tmp).astype(np.float32)
    a = out[:, :, 3:4]
    rgb = np.where(a > 0, out[:, :, :3] * 255.0 / np.maximum(a, 1.0), 0.0)
    return Image.fromarray(np.concatenate([np.clip(rgb, 0, 255), a], axis=2).astype(np.uint8), 'RGBA')


def frames_digest(folder):
    digest = hashlib.sha256()
    pngs, webps = [], []
    for path in Path(folder).iterdir():
        low = path.name.lower()
        if low.endswith('.png'):
            pngs.append(path)
        elif low.endswith('.webp'):
            webps.append(path)
    for path in sorted(pngs) + sorted(webps):
        digest.update(path.name.encode('utf-8'))
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def reference_geometry():
    files = sorted(p for p in REFERENCE.iterdir() if p.suffix.lower() in ('.png', '.webp'))
    heights, bottoms, centres = [], [], []
    for path in files:
        h, b, cx = frame_geometry(read_rgba(path))
        if h:
            heights.append(h)
            bottoms.append(b)
            centres.append(cx)
    return dict(frames=len(files), body_height=statistics.median(heights),
                baseline=statistics.median(bottoms), centre_x=statistics.median(centres))


def rebuild(name, target, dry=False):
    source_dir = IDLE / name / 'frames'
    out_dir = IDLE / 'v2' / name / 'frames'
    files = sorted(p for p in source_dir.iterdir() if p.suffix.lower() in ('.png', '.webp'))
    metrics = [frame_geometry(read_rgba(p)) for p in files]
    heights = [m[0] for m in metrics if m[0]]
    bottoms = [m[1] for m in metrics if m[0]]
    centres = [m[2] for m in metrics if m[0]]
    median_h = statistics.median(heights)
    median_bottom = statistics.median(bottoms)
    median_cx = statistics.median(centres)
    scale = target['body_height'] / median_h
    offset_x = round(TARGET_CX - median_cx * scale)
    offset_y = round(BASELINE - median_bottom * scale)
    size = read_rgba(files[0]).size
    resized = (round(size[0] * scale), round(size[1] * scale))
    report = dict(clip=name, frames=len(files), source_canvas=list(size),
                  source_body_height=median_h, source_baseline=median_bottom,
                  scale=round(scale, 4), canvas=list(CANVAS),
                  body_height=round(target['body_height'], 1), baseline=BASELINE,
                  offset=[offset_x, offset_y],
                  clipped=bool(offset_x < 0 or offset_y < 0 or offset_x + resized[0] > CANVAS[0]
                               or offset_y + resized[1] > CANVAS[1]))
    if dry:
        return report, None
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.iterdir():
        old.unlink()
    for index, path in enumerate(files):
        image = scaled_premultiplied(read_rgba(path), resized)
        canvas = Image.new('RGBA', CANVAS, (0, 0, 0, 0))
        canvas.alpha_composite(image, (offset_x, offset_y))
        name_out = ('%04d.webp' % index)
        canvas.save(out_dir / name_out, 'WEBP', quality=92, method=4)
    review = json.loads((IDLE / name / 'visual-review.json').read_text(encoding='utf-8'))
    review['frames_sha256'] = frames_digest(out_dir)
    review['note'] = ('2026-11-07 统一到 v2 规格：画布 458x660、脚底基线 620、'
                      '角色高度 %.0f（仅重排画布，抠像/帧数/时长不变）' % target['body_height'])
    review.setdefault('checks', {})['canvas_matches_v2'] = True
    (out_dir.parent / 'visual-review.json').write_text(
        json.dumps(review, ensure_ascii=False, indent=2), encoding='utf-8')
    data = json.loads((IDLE / name / 'source.json').read_text(encoding='utf-8'))
    data['canvas'] = list(CANVAS)
    data['normalization'] = dict(source_canvas=list(size), source_body_height=median_h,
                                 source_baseline=median_bottom, scale=round(scale, 4),
                                 body_height=round(target['body_height'], 1),
                                 baseline=BASELINE, canvas=list(CANVAS),
                                 target_geometry='v2 idle 中位角色高度 / 脚底 620 / 中心 229')
    data['note'] = '2026-11-07 画布重建到 v2 规格（458x660, 脚底 620）'
    (out_dir.parent / 'source.json').write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    return report, review['frames_sha256']


def update_manifest():
    path = IDLE / 'manifest.json'
    data = json.loads(path.read_text(encoding='utf-8'))
    for clip in data['clips']:
        if clip['name'] in CLIPS:
            clip['frames'] = 'v2/%s/frames' % clip['name']
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    return path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry', action='store_true')
    args = parser.parse_args()
    target = reference_geometry()
    print('v2 参考几何:', json.dumps(target, ensure_ascii=False))
    reports = []
    for name in CLIPS:
        report, digest = rebuild(name, target, dry=args.dry)
        reports.append(report)
        print(json.dumps(report, ensure_ascii=False))
        if digest:
            print('  sha %s' % digest[:16])
    if args.dry:
        return
    path = update_manifest()
    print('manifest ->', path)
    from core.avatar_review import approved_action
    for name in CLIPS:
        ok = approved_action(IDLE / 'v2' / name / 'frames')
        print('%s approved=%s' % (name, ok))
        if not ok:
            raise SystemExit('%s 未过审' % name)


if __name__ == '__main__':
    main()
