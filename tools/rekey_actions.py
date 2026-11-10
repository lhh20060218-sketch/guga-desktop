# -*- coding: utf-8 -*-
"""动作素材二次抠像管线（替代 chromakey 色键，治"灰底板/灰块/糊"）

背景诊断（2026-11-06 实测）：
  G:/dz3 源视频背景是 (136,174,122) 中明度灰绿，不是纯 #00FF00。
  旧管线 chromakey=0x00FF00:0.18 对该色完全不命中 -> 背景原样保留；
  despill 把绿去饱和成灰褐 -> 桌宠上出现灰底板、脸部灰块。

本管线改用空间分割，不依赖背景色：
  1. 24fps 抽帧（兼容 H.264/HEVC）
  2. GrabCut（半分辨率；每 KEY_EVERY 帧重算，其余帧用上一帧掩膜传递）
  3. 掩膜填洞（防脸部/肚子被误判出洞）+ 边缘羽化
  4. 按"角色身高"归一化：头顶->脚底映射到固定高度，水平按包围盒中心居中
     （各动作构图远近不同，按身高归一才能保证动作切换不跳大小）
  5. despill 压绿 + WebP 输出 384x672 @24fps

用法:
    python tools/rekey_actions.py --src G:/dz3 --out <输出根目录> [--only accept,reject]
输出:
    <out>/<action>/frames/0000.webp ...
    <out>/_rekey_report.json
"""
import argparse
import glob
import json
import os
import subprocess
import sys
import tempfile

import cv2
import numpy as np
from PIL import Image

FFMPEG = r"C:/Users/l/AppData/Local/Programs/Python/Python312/Lib/site-packages/imageio_ffmpeg/binaries/ffmpeg-win-x86_64-v9.0.2.exe"

ACTIONS = {
    'butler_idle': 'idle', 'butler_commanding': 'commanding', 'butler_watching': 'watching',
    'butler_asking': 'asking', 'butler_reviewing': 'reviewing', 'butler_urge': 'urge',
    'butler_celebrating': 'celebrating', 'butler_reject': 'reject', 'butler_accept': 'accept',
    'butler_pet': 'pet', 'butler_hello': 'hello', 'butler_error': 'error',
}

OUT_W, OUT_H = 384, 672
BODY_H = 640       # 角色身高(头顶->脚底)占画布高
FEET_PAD = 8       # 脚底距画布底
KEY_EVERY = 8      # 每 N 帧重算 GrabCut
FPS = 24


def extract_frames(video, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    subprocess.run([FFMPEG, '-y', '-v', 'error', '-i', video,
                    '-vf', 'fps=%d' % FPS, os.path.join(out_dir, '%04d.png')], check=True)
    return sorted(glob.glob(os.path.join(out_dir, '*.png')))


def grabcut_mask(bgr, prev=None):
    h, w = bgr.shape[:2]
    half = cv2.resize(bgr, (w // 2, h // 2), interpolation=cv2.INTER_AREA)
    hh, ww = half.shape[:2]
    bgd = np.zeros((1, 65), np.float64)
    fgd = np.zeros((1, 65), np.float64)
    m = np.zeros((hh, ww), np.uint8)
    if prev is None:
        cv2.grabCut(half, m, (4, 4, ww - 8, hh - 8), bgd, fgd, 5, cv2.GC_INIT_WITH_RECT)
    else:
        m = cv2.resize(prev, (ww, hh), interpolation=cv2.INTER_NEAREST)
        # 上一帧的 0/255 前景图要转成 GC_* 常量域，否则 grabCut 报 checkMask
        m = np.where(m > 127, cv2.GC_FGD, cv2.GC_BGD).astype(np.uint8)
        cv2.grabCut(half, m, None, bgd, fgd, 2, cv2.GC_INIT_WITH_MASK)
    fg = np.where((m == cv2.GC_FGD) | (m == cv2.GC_PR_FGD), 255, 0).astype(np.uint8)
    fg = cv2.morphologyEx(fg, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    return fg


def fill_holes(mask):
    ff = mask.copy()
    h, w = mask.shape
    pad = np.zeros((h + 2, w + 2), np.uint8)
    cv2.floodFill(ff, pad, (0, 0), 255)
    return cv2.bitwise_or(mask, cv2.bitwise_not(ff))


def process(action, video, out_root):
    tmp = tempfile.mkdtemp(prefix='rekey_')
    frames = extract_frames(video, tmp)
    if not frames:
        return {'action': action, 'error': '抽帧失败'}

    masks, boxes = [], []
    prev = None
    for i, f in enumerate(frames):
        bgr = cv2.imread(f)
        if bgr is None:
            continue
        fg = grabcut_mask(bgr, None if (prev is None or i % KEY_EVERY == 0) else prev)
        prev = fg
        ys, xs = np.where(fg > 0)
        if len(xs):
            boxes.append((xs.min() * 2, ys.min() * 2, xs.max() * 2, ys.max() * 2))
        masks.append(fg)
    if not boxes:
        return {'action': action, 'error': '未检出前景'}

    tops = np.array([b[1] for b in boxes])
    bots = np.array([b[3] for b in boxes])
    cxs = np.array([(b[0] + b[2]) / 2 for b in boxes])
    top_med, bot_med, cx_med = float(np.median(tops)), float(np.median(bots)), float(np.median(cxs))
    body = max(1.0, bot_med - top_med)
    scale = BODY_H / body

    dst = os.path.join(out_root, action, 'frames')
    os.makedirs(dst, exist_ok=True)
    for old in glob.glob(os.path.join(dst, '*')):
        os.remove(old)

    x0 = cx_med - (OUT_W / 2) / scale
    y0 = bot_med - (OUT_H - FEET_PAD) / scale
    M = np.array([[scale, 0, -x0 * scale], [0, scale, -y0 * scale]], np.float32)
    flag = cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC

    for i, (f, fg) in enumerate(zip(frames, masks)):
        bgr = cv2.imread(f)
        src_h, src_w = bgr.shape[:2]
        soft = cv2.resize(fg, (src_w, src_h), interpolation=cv2.INTER_LINEAR)
        soft = cv2.GaussianBlur(soft, (5, 5), 1.0).astype(np.float32) / 255.0
        img_s = cv2.warpAffine(bgr, M, (OUT_W, OUT_H), flags=flag, borderValue=(0, 0, 0))
        a_s = cv2.warpAffine(soft, M, (OUT_W, OUT_H), flags=cv2.INTER_LINEAR, borderValue=0)
        b = img_s.astype(np.float32)
        g, r, bb = b[:, :, 1], b[:, :, 2], b[:, :, 0]
        lim = np.maximum(r, bb)
        b[:, :, 1] = np.where(g > lim, lim + (g - lim) * 0.12, g)
        # 绿偏清除: 角色身上没有绿色元素, g 明显高于 r/b 的必然是绿幕残留
        # (深色轮廓边缘尤甚), 直接清 alpha; 比杀背景色安全, 不会误伤头发高光.
        green = (b[:, :, 1] > np.maximum(b[:, :, 2], b[:, :, 0]) + 22) & (a_s * 255 > 40)
        a_s = np.where(green, 0.0, a_s).astype(np.float32)
        a_s = cv2.GaussianBlur(a_s, (3, 3), 0.6)
        rgba = np.dstack([b[:, :, 2], b[:, :, 1], b[:, :, 0], a_s * 255]).clip(0, 255).astype(np.uint8)
        Image.fromarray(rgba, 'RGBA').save(
            os.path.join(dst, '%04d.webp' % i), 'WEBP', quality=88, method=4)

    size = sum(os.path.getsize(p) for p in glob.glob(os.path.join(dst, '*')))
    return {'action': action, 'frames': len(masks), 'body_px': round(body),
            'scale': round(scale, 3), 'mb': round(size / 1048576, 2)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', default='G:/dz3')
    ap.add_argument('--out', required=True)
    ap.add_argument('--only', default='')
    args = ap.parse_args()

    only = {s.strip() for s in args.only.split(',') if s.strip()}
    report = []
    for stem, action in ACTIONS.items():
        if only and action not in only:
            continue
        video = os.path.join(args.src, stem + '.mp4')
        if not os.path.exists(video):
            report.append({'action': action, 'error': '源视频缺失'})
            continue
        r = process(action, video, args.out)
        report.append(r)
        print(json.dumps(r, ensure_ascii=False), flush=True)

    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, '_rekey_report.json'), 'w', encoding='utf-8') as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    print('完成:', len([r for r in report if 'error' not in r]), '/', len(report))


if __name__ == '__main__':
    sys.exit(main())
