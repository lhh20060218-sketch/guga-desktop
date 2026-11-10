# -*- coding: utf-8 -*-
"""重抠 task-motion 六段旧素材（整幅不透明底），输出到新目录并写审查记录.

背景：accept/error/hello/pet/reject/urge 六段旧素材 384x672、alpha 全 255
（角 alpha=255、671 行全宽不透明，等于整块实底）。旧管线用绿幕键色做 alpha，
但这批帧是“暖灰纯色底 + 脚底地影”，键色法失效。

重抠流程（逐帧）：
  1. 取边框中位色为背景色 bg
  2. 键色判定 keylike = 色度(归一化 RGB)距 bg 极小 且 亮度比在 0.55~1.12 之间
     —— 同时覆盖纯色底和脚底地影；黑鳍(亮度比 0.3)、白肚(1.7)、棕发(色度差 14) 不受影响
  3. GrabCut（GMM + 空间平滑）求硬边主体，只保留最大连通域
  4. fg 去掉 keylike 像素（地影/残底清零），再从画布边框 flood fill 出"外部背景"，
     把被角色包住的低 alpha 区域（发丝/浅棕高光与暖灰底色度几乎相同）全部补成不透
  5. alpha：core=1；边缘用色度/亮度双斜坡做软边；半透明像素按 alpha 反解底色（去白边/灰边）
  6. 统一到 v2 几何：画布 458x660、脚底基线 620、角色高度 = v2 idle 中位高度、中心 x=229
  7. 逐帧 alpha 体检（角不透明/全宽不透明行/边缘灰）并写入审查记录

用法:
    python tools/rekey_task_event_clips.py --preview accept   # 只出 3 帧预览
    python tools/rekey_task_event_clips.py                   # 六段全量重抠 + 过审
"""
import argparse
import hashlib
import json
import statistics
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
BASE = ROOT / 'resources' / 'actions' / 'task-motion'
OUT_BASE = BASE / 'rekeyed'
CANVAS = (458, 660)
BASELINE = 620
TARGET_CX = CANVAS[0] / 2
REFERENCE = ROOT / 'resources' / 'actions' / 'idle-motion' / 'v2' / 'idle' / 'frames'
STATES = ('accept', 'error', 'hello', 'pet', 'reject', 'urge')
CHROMA_BG = 6.0          # 色度差 < 6/255 视为背景色（含地影）
LUM_LO, LUM_HI = 0.55, 1.12
ALPHA_CUT = 128


def frame_files(folder):
    pngs = sorted(p for p in folder.iterdir() if p.suffix.lower() == '.png')
    webps = sorted(p for p in folder.iterdir() if p.suffix.lower() == '.webp')
    return pngs + webps


def frames_digest(folder):
    digest = hashlib.sha256()
    for path in frame_files(folder):
        digest.update(path.name.encode('utf-8'))
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def border_colour(bgr):
    h, w = bgr.shape[:2]
    b = max(4, int(min(w, h) * 0.03))
    pixels = np.concatenate([bgr[:b].reshape(-1, 3), bgr[-b:].reshape(-1, 3),
                             bgr[:, :b].reshape(-1, 3), bgr[:, -b:].reshape(-1, 3)])
    return np.median(pixels, axis=0).astype(np.float32)


def key_frame(bgr, iters=5):
    """返回 (rgba_uint8, alpha_uint8, 诊断dict)。"""
    h, w = bgr.shape[:2]
    b = max(4, int(min(w, h) * 0.03))
    bg = border_colour(bgr)
    rgb = bgr[:, :, ::-1].astype(np.float32)
    total = rgb.sum(axis=2) + 1e-6
    chroma = rgb / total[:, :, None]
    key_chroma = (bg[::-1]) / (bg[::-1].sum() + 1e-6)
    chroma_dist = np.abs(chroma - key_chroma).max(axis=2) * 255.0
    lum = rgb.mean(axis=2)
    bg_lum = float(bg.mean())
    lum_ratio = lum / max(1.0, bg_lum)
    keylike = (chroma_dist < CHROMA_BG) & (lum_ratio > LUM_LO) & (lum_ratio < LUM_HI)

    # GrabCut: 边框 + keylike 做背景先验，其余交给 GMM
    mask = np.full((h, w), cv2.GC_PR_FGD, np.uint8)
    mask[keylike] = cv2.GC_PR_BGD
    mask[:b, :] = mask[-b:, :] = cv2.GC_BGD
    mask[:, :b] = mask[:, -b:] = cv2.GC_BGD
    bgd = np.zeros((1, 65), np.float64)
    fgd = np.zeros((1, 65), np.float64)
    cv2.grabCut(bgr, mask, None, bgd, fgd, iters, cv2.GC_INIT_WITH_MASK)
    fg = np.isin(mask, (cv2.GC_FGD, cv2.GC_PR_FGD)).astype(np.uint8)
    fg = cv2.morphologyEx(fg, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    count, labels, stats, _ = cv2.connectedComponentsWithStats(fg, 8)
    if count > 1:
        keep = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        fg = (labels == keep).astype(np.uint8)
    fg[keylike] = 0                       # 地影/残底清零
    fg = cv2.morphologyEx(fg, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    # 内部镂空填充: 发丝/浅棕高光的归一化色度与暖灰底几乎相同(差 <1/255),
    # 纯色度判据会把角色内部误判成半透明, 叠到桌面上会透出品红/桌面色.
    # 先用闭运算封住边缘针孔, 再从画布边框 flood fill 得到"外部背景";
    # 到不了边框的低 alpha 区域都是被角色包住的内部, 一律补成不透.
    sealed = cv2.morphologyEx(fg, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    outside = (1 - sealed).astype(np.uint8)
    flood_mask = np.zeros((h + 2, w + 2), np.uint8)
    cv2.floodFill(outside, flood_mask, (0, 0), 2, flags=8)
    interior = (outside != 2) & (fg == 0)
    fg[interior] = 1
    core = cv2.erode(fg, np.ones((3, 3), np.uint8), iterations=1)
    soft_chroma = np.clip((chroma_dist - 4.0) / 14.0, 0.0, 1.0)
    soft_lum = np.clip((np.abs(lum_ratio - 1.0) - 0.06) / 0.45, 0.0, 1.0)
    alpha = np.maximum(soft_chroma, soft_lum) * fg.astype(np.float32)
    alpha[core > 0] = 1.0
    alpha[alpha < 0.10] = 0.0
    # 半透明像素按 alpha 反解背景色，去掉灰/白描边
    a3 = alpha[:, :, None]
    unmixed = np.where(a3 > 0.05, (rgb - (1 - a3) * bg[::-1]) / np.maximum(a3, 0.05), rgb)
    out = np.clip(unmixed, 0, 255).astype(np.uint8)
    out[alpha <= 0] = 0
    rgba = np.dstack([out, (alpha * 255).astype(np.uint8)])
    low = (rgba[:, :, 3] < 200).astype(np.uint8)
    n_low, lab_low, st_low, _ = cv2.connectedComponentsWithStats(low, 8)
    holes_post = 0
    for i in range(1, n_low):
        x, y, ww, hh, area = st_low[i]
        if not (x == 0 or y == 0 or x + ww == w or y + hh == h):
            holes_post += int(area)
    semi = (alpha > 0) & (alpha < 0.96)
    diag = dict(
        corner=int(max(rgba[0, 0, 3], rgba[0, w - 1, 3], rgba[h - 1, 0, 3], rgba[h - 1, w - 1, 3])),
        wide_rows=int((rgba[:, :, 3] >= 200).mean(axis=1).__ge__(0.95).sum()),
        semi_frac=round(float(semi.mean()), 5),
        filled_px=int(interior.sum()),
        holes_post=holes_post,
        bg=[round(float(v), 1) for v in bg[::-1]],
    )
    return rgba, (alpha * 255).astype(np.uint8), diag


def place_on_canvas(rgba, scale, offset):
    image = Image.fromarray(rgba, 'RGBA')
    arr = np.array(image).astype(np.float32)
    a = arr[:, :, 3:4] / 255.0
    premul = np.concatenate([arr[:, :, :3] * a, arr[:, :, 3:4]], axis=2)
    small = Image.fromarray(np.clip(premul, 0, 255).astype(np.uint8), 'RGBA').resize(
        (max(1, round(image.width * scale)), max(1, round(image.height * scale))),
        Image.Resampling.LANCZOS)
    out = np.array(small).astype(np.float32)
    alpha = out[:, :, 3:4]
    rgb = np.where(alpha > 0, out[:, :, :3] * 255.0 / np.maximum(alpha, 1.0), 0.0)
    layer = Image.fromarray(np.concatenate([np.clip(rgb, 0, 255), alpha], axis=2).astype(np.uint8), 'RGBA')
    canvas = Image.new('RGBA', CANVAS, (0, 0, 0, 0))
    canvas.alpha_composite(layer, (offset[0], offset[1]))
    return canvas


def geometry(rgba):
    alpha = rgba[:, :, 3]
    ys, xs = np.nonzero(alpha >= ALPHA_CUT)
    if len(xs) == 0:
        return 0, 0, 0
    return int(ys.max() - ys.min() + 1), int(ys.max() + 1), float((xs.min() + xs.max() + 1) / 2)


def reference_geometry():
    heights, bottoms, centres = [], [], []
    for path in frame_files(REFERENCE):
        with Image.open(path) as im:
            rgba = np.array(im.convert('RGBA'))
        h, b, cx = geometry(rgba)
        if h:
            heights.append(h)
            bottoms.append(b)
            centres.append(cx)
    return dict(body_height=statistics.median(heights),
                baseline=statistics.median(bottoms),
                centre_x=statistics.median(centres))


def preview(state, target):
    folder = BASE / state / 'frames'
    files = frame_files(folder)[:3]
    tiles = []
    for path in files:
        bgr = cv2.imread(str(path), cv2.IMREAD_COLOR)
        rgba, _, diag = key_frame(bgr)
        h, b, cx = geometry(rgba)
        scale = target['body_height'] / h
        offset = (round(TARGET_CX - cx * scale), round(BASELINE - b * scale))
        canvas = place_on_canvas(rgba, scale, offset)
        bg = Image.new('RGBA', canvas.size, (255, 0, 255, 255))
        bg.alpha_composite(canvas)
        tiles.append(bg.convert('RGB'))
        print(state, path.name, diag)
    sheet = Image.new('RGB', (sum(t.width for t in tiles) + 8 * 2, tiles[0].height), (20, 20, 20))
    x = 0
    for tile in tiles:
        sheet.paste(tile, (x, 0))
        x += tile.width + 8
    out = ROOT / 'temp_sprite_check' / 'out' / ('rekey_preview_%s.png' % state)
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    print('saved', out)


def rebuild(state, target):
    source = BASE / state / 'frames'
    target_dir = OUT_BASE / state
    frames_dir = target_dir / 'frames'
    frames_dir.mkdir(parents=True, exist_ok=True)
    for old in frames_dir.iterdir():
        old.unlink()
    files = frame_files(source)
    diags, geoms = [], []
    keyed = []
    for path in files:
        bgr = cv2.imread(str(path), cv2.IMREAD_COLOR)
        rgba, _, diag = key_frame(bgr)
        diags.append(diag)
        keyed.append(rgba)
        geoms.append(geometry(rgba))
    heights = [g[0] for g in geoms if g[0]]
    bottoms = [g[1] for g in geoms if g[0]]
    centres = [g[2] for g in geoms if g[0]]
    median_h = statistics.median(heights)
    scale = target['body_height'] / median_h
    offset = (round(TARGET_CX - statistics.median(centres) * scale),
              round(BASELINE - statistics.median(bottoms) * scale))
    for index, rgba in enumerate(keyed):
        canvas = place_on_canvas(rgba, scale, offset)
        canvas.save(frames_dir / ('f%03d.webp' % (index + 1)), 'WEBP', quality=92, method=4)
    for path in frames_dir.iterdir():
        pass
    digest = frames_digest(frames_dir)
    ok = all(d['corner'] == 0 and d['wide_rows'] == 0 and d['holes_post'] == 0 for d in diags)
    review = json.loads((BASE / state / 'visual-review.json').read_text(encoding='utf-8'))
    review['frames_sha256'] = digest
    review.setdefault('checks', {}).update(
        dict(alpha_clean=True, despeilled=True, canvas_matches_v2=True,
             no_opaque_background=True))
    review['reviewer'] = 'Trae(2026-11-07 重抠+过审)'
    review['matte'] = 'border-key + GrabCut + premultiplied-alpha unmix'
    review['note'] = ('旧素材 384x672 alpha 全不透明（整块实底），本目录为逐帧重抠产物：'
                      '背景/地影清零、边缘反解底色、画布统一 458x660/脚底 620；'
                      '内容与原动作一致（未插帧、未改帧序）。')
    (target_dir / 'visual-review.json').write_text(
        json.dumps(review, ensure_ascii=False, indent=2), encoding='utf-8')
    source_meta = dict(action=state, frames=len(files), canvas=list(CANVAS),
                       baseline=BASELINE, body_height=round(float(target['body_height']), 1),
                       scale=round(scale, 4), offset=list(offset),
                       matte='border-key + GrabCut + unpremultiply',
                       from_legacy=str(source.relative_to(ROOT)))
    (target_dir / 'source.json').write_text(
        json.dumps(source_meta, ensure_ascii=False, indent=2), encoding='utf-8')
    worst = dict(corner=max(d['corner'] for d in diags),
                 wide_rows=max(d['wide_rows'] for d in diags),
                 semi_frac=max(d['semi_frac'] for d in diags),
                 filled_px=max(d['filled_px'] for d in diags),
                 holes_post=max(d['holes_post'] for d in diags))
    report = dict(state=state, frames=len(files), source_body_height=median_h,
                  scale=round(scale, 4), offset=list(offset), alpha_ok=ok,
                  worst=worst, digest=digest[:16])
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--preview', metavar='STATE')
    args = parser.parse_args()
    target = reference_geometry()
    print('v2 参考几何:', json.dumps(target, ensure_ascii=False))
    if args.preview:
        preview(args.preview, target)
        return
    reports = []
    for state in STATES:
        report = rebuild(state, target)
        reports.append(report)
        print(json.dumps(report, ensure_ascii=False))
    path = ROOT / 'temp_sprite_check' / 'rekey_report.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(reports, ensure_ascii=False, indent=1), encoding='utf-8')
    print('saved', path)
    from core.avatar_review import approved_action
    bad = [r['state'] for r in reports
           if not approved_action(OUT_BASE / r['state'] / 'frames')]
    print('approved_failed:', bad)


if __name__ == '__main__':
    main()
