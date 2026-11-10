# -*- coding: utf-8 -*-
"""
咕嘎 12 动作素材自适应抠像管线（逐片取键色 + 软边 alpha + despill + 统一画布锚点）

设计要点:
  1. 逐帧从画面四周 4% 边框采样绿占优像素的中位色作为该帧键色；边框被道具遮挡时回落到整片键色。
  2. alpha 用"绿溢出量"(G - max(R,B)) 相对本片键色的比例生成软边，天然容忍同一视频内底色轻微不均。
  3. 阴影抑制: 与键色同色相但明显更暗的像素(脚下投影)直接判为背景，避免桌面上挂一团绿影。
  4. despill: 绿溢出中和，只压绿通道，保留角色白肚/浅色边。
  5. 统一 458x660 画布（与桌宠显示框 180x258.5 同比例，留出举手/道具空间）；
     按"头顶到脚底"的稳健身高归一化缩放，脚底锚点统一到同一条基线，
     片段内保留原始运动，切片段不跳位。
  6. 抠像全程在源分辨率(1080x1920)完成，再用 Lanczos 预乘 alpha 降采样到小画布，
     边缘参差被重采样糊平，观感接近 dsh-pet。
  7. 循环片段自动检测首尾 seam，裁掉回不到起点的尾巴，保证 loop 无缝。
  8. WebP 帧序列 + 24fps + f001.webp 命名，符合 ui/sprite_animator.py / core/avatar_review.py 约定。

用法:
    python tools/key_action_pack.py --src G:\\dz3 --out <输出根> --clip butler_idle
    python tools/key_action_pack.py --src G:\\dz3 --out <输出根>            # 全部 12 个
只读取源目录，不写入源目录。
"""
import argparse
import json
import os
import subprocess
import sys
from collections import OrderedDict

import cv2
import numpy as np
from PIL import Image, ImageDraw
import imageio_ffmpeg

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()

# 源文件名 -> (动作名, 播放类型)
ACTIONS = OrderedDict([
    ('butler_idle',        ('idle',        'loop')),
    ('butler_commanding',  ('commanding',  'loop')),
    ('butler_watching',    ('watching',    'loop')),
    ('butler_asking',      ('asking',      'loop')),
    ('butler_reviewing',   ('reviewing',   'loop')),
    ('butler_urge',        ('urge',        'loop')),
    ('butler_celebrating', ('celebrating', 'once')),
    ('butler_reject',      ('reject',      'once')),
    ('butler_accept',      ('accept',      'once')),
    ('butler_pet',         ('pet',         'once')),
    ('butler_hello',       ('hello',       'once')),
    ('butler_error',       ('error',       'once')),
])

TARGET_W, TARGET_H, TARGET_FPS = 458, 660, 24
TARGET_SPAN = 529          # 头顶->脚底目标像素高（458x660 下占比 0.801）
BASELINE_Y = 620           # 脚底基线（画布内 y，620/660≈0.939）
WEBP_QUALITY = 88


def run_ffmpeg_frames(path, fps):
    """按目标 fps 解码为 RGB24 帧生成器。"""
    w, h = probe_size(path)
    p = subprocess.Popen([FFMPEG, '-hide_banner', '-loglevel', 'error', '-i', path,
                          '-vf', 'fps=%g' % fps, '-an', '-pix_fmt', 'rgb24',
                          '-f', 'rawvideo', '-'], stdout=subprocess.PIPE)
    n = w * h * 3
    try:
        while True:
            buf = p.stdout.read(n)
            if len(buf) < n:
                break
            yield np.frombuffer(buf, dtype=np.uint8, count=n).reshape(h, w, 3)
    finally:
        try:
            p.stdout.close()
        except OSError:
            pass
        p.wait()


def probe_size(path):
    import re
    r = subprocess.run([FFMPEG, '-hide_banner', '-i', path], capture_output=True,
                       text=True, encoding='utf-8', errors='ignore')
    m = re.search(r'Video:.*?(\d{2,4})x(\d{2,4})', r.stderr)
    return int(m.group(1)), int(m.group(2))


def frame_key(rgb, fallback=None):
    """单帧边框键色。返回 (K, green_excess, 边框绿像素占比)。"""
    h, w = rgb.shape[:2]
    b = max(3, int(min(w, h) * 0.04))
    border = np.concatenate([
        rgb[:b].reshape(-1, 3), rgb[-b:].reshape(-1, 3),
        rgb[:, :b].reshape(-1, 3), rgb[:, -b:].reshape(-1, 3),
    ]).astype(np.int16)
    ge = border[:, 1] - np.maximum(border[:, 0], border[:, 2])
    mask = (ge > 5) & (border[:, 1] > 40)
    ratio = float(mask.mean())
    if ratio < 0.05:
        return fallback, None, ratio
    k = np.median(border[mask], axis=0)
    return k.astype(np.float32), float(k[1] - max(k[0], k[2]), ), ratio


def make_alpha(rgb, key, gk):
    """软边 alpha + 发光保护 + despill。

    返回 alpha(float32), despilled rgb(uint8), 受保护的发光像素数,
    与键色的色度距离(用于识别地面投影/背景残底).
    """
    rgb16 = rgb.astype(np.int16)
    ge = rgb16[:, :, 1] - np.maximum(rgb16[:, :, 0], rgb16[:, :, 2])
    ge_f = ge.astype(np.float32)
    t_full = max(2.5, 0.06 * gk)
    t_zero = max(t_full + 4.0, 0.80 * gk)
    alpha = np.clip((t_zero - ge_f) / (t_zero - t_full), 0.0, 1.0)

    # 发光保护: 纯绿幕片里亮黄绿(高 R-B/G-B)的道具光效会被当作绿溢出压暗/抠掉。
    # 只提升这些像素的 alpha 到 1，颜色仍走 despill(压成中性暖光)，避免留绿雾。
    glow_px = 0
    if gk >= 120:
        bright = ((rgb16[:, :, 1] >= 150) & (rgb16[:, :, 0] >= 80) &
                  ((rgb16[:, :, 0] - rgb16[:, :, 2]) >= 60) &
                  ((rgb16[:, :, 1] - rgb16[:, :, 2]) >= 80) &
                  (rgb16[:, :, 1] >= rgb16[:, :, 0]))
        glow_px = int(bright.sum())
        if glow_px >= 800:
            alpha[bright] = 1.0
        else:
            glow_px = 0

    # 与键色的色度距离: 用于区分"脚底以外的地影/残底"和角色本体
    sums = rgb16.sum(axis=2).astype(np.float32) + 1e-6
    cn = rgb16.astype(np.float32) / sums[:, :, None]
    kn = key / (float(key.sum()) + 1e-6)
    dist = np.abs(cn - kn).max(axis=2) * 255.0

    # despill: 绿通道压到 max(R,B)，完全中和绿溢出（半透明边缘也不留绿）
    out = rgb.copy()
    spill = ge > 0
    out[:, :, 1] = np.where(spill, np.maximum(rgb16[:, :, 0], rgb16[:, :, 2]), rgb16[:, :, 1]).astype(np.uint8)
    return alpha, out, glow_px, dist


def foot_line(alpha, dist, min_area=400, min_px=3):
    """脚底线: 角色本体(alpha>0.5 的最大连通域)内, 最靠下的一行"确定不是键色"的
    实体像素(脚掌/鞋); 排除绿幕地影(dist 很小)。

    加连通域限制是因为画面死角常有一小片亮绿反光, 只有两三像素宽却能被 alpha 判成
    实体, 会把脚底锚点抬高、同时把那片反光留在画面上。
    """
    body = (alpha > 0.5).astype(np.uint8)
    n, lab, st, _ = cv2.connectedComponentsWithStats(body, 8)
    if n < 2:
        return None, None
    i = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))
    if st[i, cv2.CC_STAT_AREA] < min_area:
        return None, None
    solid = (alpha > 0.5) & (dist > 22.0) & (lab == i)
    rows = np.flatnonzero(solid.sum(axis=1) >= min_px)
    if not len(rows):
        return None, None
    fb = int(rows.max())
    ys, xs = np.where(solid[max(0, fb - 6):fb + 1])
    return fb, (float(xs.mean()) if len(xs) else None)


def resize_rgba(rgb, alpha, dw, dh):
    """预乘 alpha -> Lanczos4 降采样 -> 反预乘，保软边、不产生绿边/黑边/白边。"""
    a = alpha.astype(np.float32)
    pm = rgb.astype(np.float32) * a[:, :, None]
    pm_s = cv2.resize(pm, (dw, dh), interpolation=cv2.INTER_LANCZOS4)
    a_s = cv2.resize(a, (dw, dh), interpolation=cv2.INTER_LANCZOS4)
    a_s = np.clip(a_s, 0.0, 1.0)
    safe = np.maximum(a_s[:, :, None], 1e-5)
    rgb_s = np.clip(pm_s / safe, 0, 255)
    rgba = np.dstack([rgb_s, a_s * 255.0]).astype(np.uint8)
    rgba[a_s < 1.0 / 255.0, :3] = 0
    return rgba


def _thumb(canvas):
    """循环 seam 检测用的小尺寸预乘缩略图。"""
    a = canvas[:, :, 3].astype(np.float32) / 255.
    pm = canvas[:, :, :3].astype(np.float32) * a[:, :, None]
    return cv2.resize(np.dstack([pm, a * 255.]), (24, 42), interpolation=cv2.INTER_AREA)


def _tdiff(x, y):
    return float(np.abs(x - y).mean()) / 255.0


def body_stats(rgba):
    """最大连通域的身高/脚底/脚底中心，用于尺度与锚点归一化。"""
    a = (rgba[:, :, 3] > 30).astype(np.uint8)
    a = cv2.morphologyEx(a, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(a, 8)
    if n < 2:
        return None
    i = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    x, y, cw, ch, area = stats[i]
    comp = lab == i
    rows = np.arange(y, y + ch)
    width = comp.sum(axis=1)[rows]
    # 头顶: 最上 12% 行中宽度 >= 最大宽度 30% 的行（避开单像素噪点/细天线）
    top_rows = rows[rows <= y + int(ch * 0.12)]
    valid = top_rows[width[top_rows - y] >= max(3, width.max() * 0.3)]
    top = int(valid.min()) if len(valid) else int(y)
    foot_rows = rows[rows >= y + ch - max(2, int(ch * 0.06))]
    row_mask = np.zeros(comp.shape[0], dtype=bool)
    row_mask[foot_rows] = True
    ys, xs = np.where(comp & row_mask[:, None])
    foot_cx = float(xs.mean()) if len(xs) else float(x + cw / 2)
    return dict(top=top, bottom=int(y + ch), foot_y=int(y + ch), foot_cx=foot_cx,
                span=int(y + ch - top), x=int(x), x2=int(x + cw), w=int(cw), area=int(area))


def pre_pass(path, fps, sample_count=12):
    """抽样若干帧估计整片尺度/脚底锚点（流式抽样，不驻留整片帧）。"""
    keys, stats, picks = [], [], []
    step = 8
    for idx, rgb in enumerate(run_ffmpeg_frames(path, fps)):
        if idx % step == 0 and len(picks) < sample_count:
            picks.append(rgb)
    if not picks:
        return None
    fallback = None
    for rgb in picks:
        k, gk, ratio = frame_key(rgb, fallback)
        if k is None:
            continue
        if fallback is None:
            fallback = k
        if gk is None:
            gk = float(k[1] - max(k[0], k[2]))
        keys.append(k.tolist())
        a, desp, _, dist = make_alpha(rgb, k, gk)
        fb, fcx = foot_line(a, dist)
        if fb is None:
            del a, desp, dist
            continue
        rgba = np.dstack([np.zeros_like(rgb), (a * 255.0).astype(np.uint8)])
        st = body_stats(rgba)
        if st:
            stats.append(dict(top=int(st['top']), bottom=int(fb), span=int(fb - st['top']),
                              foot_y=int(fb),
                              foot_cx=float(fcx if fcx is not None else st['foot_cx'])))
        del a, desp, rgba, dist
    if not stats:
        return None
    valid = [s for s in stats if s['top'] > 2 and s['foot_y'] < picks[0].shape[0] - 2]
    if len(valid) < max(3, len(stats) // 2):
        valid = stats
    span = float(np.percentile([s['span'] for s in valid], 25))
    foot_y = float(np.median([s['foot_y'] for s in valid]))
    foot_cx = float(np.median([s['foot_cx'] for s in valid]))
    return dict(key_median=np.median(np.array(keys), axis=0).tolist(),
                key_frames=keys, span=span, foot_y=foot_y, foot_cx=foot_cx,
                source=[int(picks[0].shape[1]), int(picks[0].shape[0])])


def process_clip(src, name, out_root, make_preview=True):
    action, kind = ACTIONS[name]
    path = os.path.join(src, name + '.mp4')
    pre = pre_pass(path, TARGET_FPS)
    if not pre:
        raise RuntimeError('无法解析: ' + path)
    sw, sh = pre['source']
    s = TARGET_SPAN / max(1.0, pre['span'])
    ox = TARGET_W / 2.0 - pre['foot_cx'] * s
    oy = BASELINE_Y - pre['foot_y'] * s
    cw, ch = int(round(sw * s)), int(round(sh * s))

    action_dir = os.path.join(out_root, action)
    frames_dir = os.path.join(action_dir, 'frames')
    os.makedirs(frames_dir, exist_ok=True)
    for old in os.listdir(frames_dir):
        if old.lower().endswith(('.webp', '.png')):
            os.remove(os.path.join(frames_dir, old))

    fallback = np.array(pre['key_median'], dtype=np.float32)
    metrics = dict(source=os.path.basename(path), action=action, playback=kind,
                   source_size=[sw, sh], target_size=[TARGET_W, TARGET_H], fps=TARGET_FPS,
                   key_median=[round(float(v), 1) for v in pre['key_median']],
                   scale=round(float(s), 5), span_raw=round(pre['span'], 1),
                   foot_raw=[round(pre['foot_y'], 1), round(pre['foot_cx'], 1)],
                   baseline=BASELINE_Y,
                   frames=0, key_drift=[0.0, 0.0, 0.0], alpha_cov=0.0, fringe_before=0.0, fringe_after=0.0,
                   loop_tail=dict(alpha=0.0, rgb=0.0))
    first_rgba = None
    last_rgba = None
    key_list = []
    cov_list = []
    fb_list = []
    glow_list = []
    thumbs = []
    tail = []
    for idx, rgb in enumerate(run_ffmpeg_frames(path, TARGET_FPS), start=1):
        k, gk, ratio = frame_key(rgb, fallback)
        if k is None:
            k, gk = fallback, float(fallback[1] - max(fallback[0], fallback[2]))
        if gk is None:
            gk = float(k[1] - max(k[0], k[2]))
        key_list.append(k.tolist())
        a, desp, glow_n, dist = make_alpha(rgb, k, gk)
        glow_list.append(glow_n)
        # 脚底以下只可能是绿幕地影: 整行清掉; 脚底上方 60px 内清"与键色色度接近
        # 且不比键色更暗"的残底(地影晕边), 深色描边(比键色更暗)保留.
        foot_b, _ = foot_line(a, dist)
        if foot_b is not None:
            ksum = float(np.array(k).sum())
            ksum2 = rgb.astype(np.int16).sum(axis=2)
            kill = np.zeros_like(dist, dtype=bool)
            band = max(0, foot_b - 60)
            kill[band:foot_b + 1] = (dist[band:foot_b + 1] < 22.0) & (ksum2[band:foot_b + 1] > 0.5 * ksum)
            kill[foot_b + 1:] = True
            # 有些绿幕的地面投影是"比键色更亮的低反差浅绿"且一直晕到脚踝上方,
            # 再按颜色特征清一段: 绿通道占优(G>=R+2) + 低反差(max-min<58) + 不暗于键色.
            # 角色本体是暖色(R 主导)、描边近黑或无彩、发光环高饱和(max-min>=58), 均不受影响.
            up = max(0, foot_b - 130)
            reg = slice(up, foot_b + 1)
            rv = rgb[reg].astype(np.int16)
            span = rv.max(axis=2) - rv.min(axis=2)
            shadowish = ((dist[reg] < 22.0) & (span < 58)
                         & (rv[:, :, 1] >= rv[:, :, 0] + 2)
                         & (rv.sum(axis=2) > 0.5 * ksum))
            # 更亮的绿幕反光/白晕(如 reject 右下角那块泛白光斑): 绿通道微占优、
            # 几乎无反差、比键色亮得多. 角色本体暖色(R 主导) / 发光环高饱和都不符合.
            glare = ((span < 30) & (rv[:, :, 1] >= rv[:, :, 0] + 5)
                     & (rv[:, :, 1] >= rv[:, :, 2] + 3)
                     & (rv.sum(axis=2) > 0.7 * ksum))
            kill[reg] |= shadowish | glare
            a[kill] = 0.0
        # 源视频最外 2px 常有编码亮边/反光, 会留下孤立小点; 直接清掉(内容从不贴边)
        a[:, :2] = 0.0
        a[:, -2:] = 0.0
        a[:2, :] = 0.0
        a[-2:, :] = 0.0
        ge_src = rgb.astype(np.int16)[:, :, 1] - np.maximum(rgb[:, :, 0].astype(np.int16), rgb[:, :, 2].astype(np.int16))
        ge_after = desp.astype(np.int16)[:, :, 1] - np.maximum(desp[:, :, 0].astype(np.int16), desp[:, :, 2].astype(np.int16))
        opaque = a > 0.5
        fringe_before = float((ge_src[opaque] > 10).mean()) if np.any(opaque) else 0.0
        fringe_after = float((ge_after[opaque] > 8).mean()) if np.any(opaque) else 0.0
        edge = (a > 0.08) & (a < 0.92)
        edge_green = float((ge_after[edge] > 8).mean()) if np.any(edge) else 0.0
        fb_list.append((fringe_before, fringe_after, edge_green))
        rgba_small = resize_rgba(desp, a, cw, ch)
        canvas = np.zeros((TARGET_H, TARGET_W, 4), dtype=np.uint8)
        ix, iy = int(round(ox)), int(round(oy))
        x0, y0 = max(0, ix), max(0, iy)
        x1, y1 = min(TARGET_W, ix + cw), min(TARGET_H, iy + ch)
        sx0, sy0 = x0 - ix, y0 - iy
        if x1 > x0 and y1 > y0:
            canvas[y0:y1, x0:x1] = rgba_small[sy0:sy0 + (y1 - y0), sx0:sx0 + (x1 - x0)]
        cov_list.append(float((canvas[:, :, 3] > 0).mean()))
        if idx == 1:
            first_rgba = canvas
        last_rgba = canvas
        thumbs.append(_thumb(canvas))
        tail.append(canvas)
        if len(tail) > 12:
            tail.pop(0)
        Image.fromarray(canvas, 'RGBA').save(
            os.path.join(frames_dir, 'f%03d.webp' % idx), 'WEBP',
            quality=WEBP_QUALITY, alpha_quality=95, method=4)
        metrics['frames'] = idx
        if idx % 30 == 0:
            print('  %s %d 帧' % (action, idx))

    n = metrics['frames']
    metrics['glow_protected'] = int(max(glow_list)) if glow_list else 0
    metrics['loop_seam_ok'] = None
    metrics['tail_trimmed'] = 0
    if kind == 'loop' and n >= 4:
        adj = [_tdiff(thumbs[i + 1], thumbs[i]) for i in range(n - 1)]
        thr = max(0.012, 2.2 * float(np.median(adj)))
        choose = n - 1
        if _tdiff(thumbs[n - 1], thumbs[0]) > thr:
            # 尾巴回不到起点 -> 在尾段里找最靠后的、与首帧足够接近的帧作为新尾帧
            floor = max(1, int(n * 0.25))
            for k2 in range(n - 2, floor - 1, -1):
                if _tdiff(thumbs[k2], thumbs[0]) <= thr:
                    choose = k2
                    break
        if choose < n - 1:
            for j in range(choose + 2, n + 1):
                p = os.path.join(frames_dir, 'f%03d.webp' % j)
                if os.path.exists(p):
                    os.remove(p)
            metrics['tail_trimmed'] = n - 1 - choose
            metrics['frames'] = choose + 1
            last_rgba = tail[choose - (n - len(tail))]
        seam = _tdiff(thumbs[choose], thumbs[0])
        metrics['loop_seam_diff'] = round(seam, 4)
        metrics['loop_seam_ok'] = bool(seam <= max(thr, 0.02))

    ka = np.array(key_list)
    metrics['key_drift'] = [round(float(v), 2) for v in ka.std(axis=0)]
    metrics['alpha_cov'] = round(float(np.mean(cov_list)), 4)
    fb = np.array(fb_list)
    metrics['fringe_before'] = round(float(fb[:, 0].mean()), 5)
    metrics['fringe_after'] = round(float(fb[:, 1].mean()), 5)
    metrics['edge_green_after'] = round(float(fb[:, 2].mean()), 5)
    if first_rgba is not None and last_rgba is not None:
        a1, a2 = first_rgba[:, :, 3].astype(np.float32) / 255., last_rgba[:, :, 3].astype(np.float32) / 255.
        metrics['loop_tail']['alpha'] = round(float(np.abs(a1 - a2).mean()), 4)
        m = (a1 > .1) & (a2 > .1)
        if np.any(m):
            metrics['loop_tail']['rgb'] = round(float(np.abs(first_rgba[:, :, :3][m].astype(np.int16) -
                                                          last_rgba[:, :, :3][m].astype(np.int16)).mean()), 2)

    with open(os.path.join(action_dir, 'metrics.json'), 'w', encoding='utf-8') as f:
        json.dump(metrics, f, ensure_ascii=False, indent=2)
    if make_preview:
        render_preview(action_dir, first_rgba, last_rgba)
    print('%-14s -> %-12s %3d 帧  %dx%d  缩放 %.3f  键色 %s  覆盖率 %.3f  边缘残绿 %.2f%%  seam %s'
          % (name, action, metrics['frames'], cw, ch, s, metrics['key_median'],
             metrics['alpha_cov'], metrics['fringe_after'] * 100,
             'n/a' if metrics['loop_seam_ok'] is None
             else ('%.4f/%s' % (metrics['loop_seam_diff'], 'ok' if metrics['loop_seam_ok'] else 'FAIL'))))
    return metrics


def render_preview(action_dir, first_rgba, last_rgba):
    """棋盘格接触表 + 浅/深底合成图，用于肉眼验收。"""
    pv = os.path.join(action_dir, 'preview')
    os.makedirs(pv, exist_ok=True)
    frames_dir = os.path.join(action_dir, 'frames')
    names = sorted(os.listdir(frames_dir))
    picks = [names[0], names[len(names) // 2], names[-1]]
    tiles = []
    for fn in picks:
        im = Image.open(os.path.join(frames_dir, fn)).convert('RGBA')
        tiles.append(im)
    W, H = tiles[0].size
    board = Image.new('RGB', (W * 3, H), (120, 120, 120))
    dr = ImageDraw.Draw(board)
    for y in range(0, H, 24):
        for x in range(0, W * 3, 24):
            if ((x // 24) + (y // 24)) % 2 == 0:
                dr.rectangle([x, y, x + 23, y + 23], fill=(160, 160, 160))
    for i, im in enumerate(tiles):
        board.paste(im, (i * W, 0), im)
    board.save(os.path.join(pv, 'contact_checker.png'))
    for bg, tag in (((235, 238, 242), 'light'), ((38, 42, 50), 'dark')):
        base = Image.new('RGB', (W * 3, H), bg)
        for i, im in enumerate(tiles):
            base.paste(im, (i * W, 0), im)
        base.save(os.path.join(pv, 'contact_%s.png' % tag))

    # 边缘放大: 头发左缘 / 脚下 / 手臂外缘 三处 x3
    im = tiles[len(tiles) // 2]
    arr = np.array(im)
    a = arr[:, :, 3]
    ys, xs = np.where(a > 30)
    if len(xs):
        x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
        crops = [
            ('head_left', max(0, x0 - 6), max(0, y0 + 40), min(W, x0 + 80), min(H, y0 + 150)),
            ('feet', max(0, (x0 + x1) // 2 - 70), max(0, y1 - 90), min(W, (x0 + x1) // 2 + 70), min(H, y1 + 8)),
            ('arm_right', max(0, x1 - 80), max(0, y0 + 180), min(W, x1 + 6), min(H, y0 + 320)),
        ]
        zooms = []
        for tag, cx0, cy0, cx1, cy1 in crops:
            if cx1 <= cx0 or cy1 <= cy0:
                continue
            crop = im.crop((cx0, cy0, cx1, cy1)).resize(((cx1 - cx0) * 3, (cy1 - cy0) * 3), Image.NEAREST)
            bgc = Image.new('RGB', crop.size, (235, 238, 242))
            bgc.paste(crop, (0, 0), crop)
            zooms.append((tag, bgc))
        if zooms:
            tw = sum(z.size[0] for _, z in zooms) + 12 * (len(zooms) - 1)
            th = max(z.size[1] for _, z in zooms)
            sheet = Image.new('RGB', (tw, th), (255, 255, 255))
            x = 0
            for _, z in zooms:
                sheet.paste(z, (x, 0))
                x += z.size[0] + 12
            sheet.save(os.path.join(pv, 'edges_zoom_x3.png'))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', default=r'G:\dz3')
    ap.add_argument('--out', required=True)
    ap.add_argument('--clip', action='append', default=None, help='可重复；缺省=全部 12 个')
    ap.add_argument('--no-preview', action='store_true')
    args = ap.parse_args()
    only = args.clip or list(ACTIONS.keys())
    os.makedirs(args.out, exist_ok=True)
    summary = {}
    for n in only:
        if n not in ACTIONS:
            print('跳过未知片段:', n)
            continue
        summary[n] = process_clip(args.src, n, args.out, make_preview=not args.no_preview)
    with open(os.path.join(args.out, '_summary.json'), 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print('完成 ->', args.out)


if __name__ == '__main__':
    main()
