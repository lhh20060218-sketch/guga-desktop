# -*- coding: utf-8 -*-
"""说话动画 v3：嘴部补丁法
身体固定用闭嘴帧（70da9472，姿势一致），从开口帧抠"喙+嘴"补丁贴上去。
补丁按喙部锚点对齐 + 边缘羽化，保证身体零晃动、只有嘴在动。
"""
import os
import sys
import io
from collections import deque

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)
from PIL import Image, ImageFilter

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.environ.get('GUGA_TALK_FRAMES', 'samples/talk-frames')
OUT_GIF = os.path.join(PROJECT, 'resources', 'stickers', 'talk.gif')
EXCLUDE = ('041507d1', '7771be0b')

BG_THRESHOLD = 205
MIN_BLOB_RATIO = 0.015


def clean(img):
    w, h = img.size
    px = img.load()
    bg = bytearray(w * h)
    visited = bytearray(w * h)
    q = deque()
    for x in range(w):
        q.append((x, 0)); q.append((x, h - 1))
    for y in range(h):
        q.append((0, y)); q.append((w - 1, y))
    for p in q:
        visited[p[1] * w + p[0]] = 1

    def is_bg(x, y):
        r, g, b = px[x, y][:3]
        return r >= BG_THRESHOLD and g >= BG_THRESHOLD and b >= BG_THRESHOLD

    while q:
        x, y = q.popleft()
        if not is_bg(x, y):
            continue
        bg[y * w + x] = 1
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < w and 0 <= ny < h and not visited[ny * w + nx]:
                visited[ny * w + nx] = 1
                q.append((nx, ny))

    keep = bytearray(w * h)
    min_size = w * h * MIN_BLOB_RATIO
    seen = bytearray(w * h)
    for y in range(h):
        for x in range(w):
            if bg[y * w + x] or seen[y * w + x]:
                continue
            cq = deque([(x, y)])
            seen[y * w + x] = 1
            blob = []
            while cq:
                cx, cy = cq.popleft()
                blob.append((cx, cy))
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = cx + dx, cy + dy
                    if 0 <= nx < w and 0 <= ny < h and not bg[ny * w + nx] and not seen[ny * w + nx]:
                        seen[ny * w + nx] = 1
                        cq.append((nx, ny))
            if len(blob) >= min_size:
                for bx, by in blob:
                    keep[by * w + bx] = 1

    out = img.convert('RGBA')
    opx = out.load()
    for y in range(h):
        for x in range(w):
            if not keep[y * w + x]:
                opx[x, y] = (opx[x, y][0], opx[x, y][1], opx[x, y][2], 0)
    return out


def find_beak(img):
    w, h = img.size
    px = img.load()
    pts = []
    for y in range(int(h * 0.30), int(h * 0.75)):
        for x in range(int(w * 0.20), int(w * 0.80)):
            r, g, b, a = px[x, y]
            if a > 40 and r > 185 and g > 135 and b < 145:
                pts.append((x, y))
    if len(pts) < 40:
        return None
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    return (min(xs), min(ys), max(xs), max(ys))


def mouth_patch(src, src_beak, dst_beak):
    """从 src 抠"喙+嘴"补丁，缩放到目标喙部尺寸"""
    bw = dst_beak[2] - dst_beak[0]
    scale = bw / (src_beak[2] - src_beak[0])
    s = src.resize((int(src.width * scale), int(src.height * scale)))
    sb = (src_beak[0] * scale, src_beak[1] * scale, src_beak[2] * scale, src_beak[3] * scale)
    cx = (sb[0] + sb[2]) / 2
    cy = (sb[1] + sb[3]) / 2
    bh = sb[3] - sb[1]
    pw = int(bw * 2.1)
    ph = int(bh * 2.4)
    x0 = int(cx - pw / 2)
    y0 = int(cy - bh * 0.55)  # 从喙上部开始，覆盖下方嘴部
    patch = s.crop((max(0, x0), max(0, y0), min(s.width, x0 + pw), min(s.height, y0 + ph)))
    # 羽化边缘（透明度渐隐）
    mask = Image.new('L', patch.size, 255)
    mpx = mask.load()
    for y in range(patch.height):
        for x in range(patch.width):
            edge = min(x, patch.width - 1 - x, y, patch.height - 1 - y)
            if edge < 8:
                mpx[x, y] = int(255 * max(0.15, edge / 8))
    patch.putalpha(mask)
    return patch, (x0, y0)


def paste_patch(base, patch, pos, dst_beak):
    """把补丁贴到 base 的喙部位置（对齐补丁内喙中心与目标喙中心）"""
    out = base.copy()
    # 补丁内喙中心（我们已知补丁是从 src 以喙中心裁剪的，偏移后就是补丁中心附近）
    patch_cx = patch.width / 2
    patch_cy = patch.height * 0.55  # 喙中心在补丁内的位置（裁剪起点=cy-0.55bh，喙中心=cy）
    dst_cx = (dst_beak[0] + dst_beak[2]) / 2
    dst_cy = (dst_beak[1] + dst_beak[3]) / 2
    ox = int(dst_cx - patch_cx)
    oy = int(dst_cy - patch_cy)
    out.alpha_composite(patch, (ox, oy))
    return out


def main():
    files = [f for f in sorted(os.listdir(SRC)) if f.lower().endswith('.png')
             and not any(f.startswith(e) for e in EXCLUDE)]
    cleaned = {f[:8]: clean(Image.open(os.path.join(SRC, f)).convert('RGB')) for f in files}
    beaks = {k: find_beak(v) for k, v in cleaned.items()}

    base_name = '70da9472'  # 闭嘴微笑、姿势一致
    base = cleaned[base_name]
    base_beak = beaks[base_name]
    if base_beak is None:
        print('基准帧无喙部'); return
    print(f'基准: {base_name} 喙={base_beak}', flush=True)

    # 开口帧来源（排除基准）
    sources = [k for k in cleaned if k != base_name and beaks[k]]
    patches = {}
    for k in sources:
        patch, _ = mouth_patch(cleaned[k], beaks[k], base_beak)
        # 张度 = 补丁与基准嘴部区域的差异
        diff = sum(1 for x in range(min(patch.width, base.width))
                   for y in range(min(patch.height, base.height))
                   if patch.getpixel((x, y)) != base.getpixel((x, y)))
        patches[k] = (patch, diff)
        print(f'[补丁] {k} 差异={diff}', flush=True)

    # 取差异最大(嘴张最大)和最接近的两个作为张开帧
    ranked = sorted(patches.items(), key=lambda t: -t[1][1])
    open1 = ranked[0][1][0] if ranked else None
    open2 = ranked[1][1][0] if len(ranked) > 1 else open1
    if open1 is None:
        print('没有可用开口补丁'); return

    # 帧序：闭 → 微张 → 大张 → 微张 → 闭
    frames = []
    for patch in (open1, open2):
        f = paste_patch(base, patch, None, base_beak)
        frames.append(f)
    frames = [base] + frames + frames[::-1][1:] + [base]

    # 统一裁剪 + 缩放 + GIF
    xs = [f.getbbox() for f in frames]
    x0 = max(b[0] for b in xs); y0 = max(b[1] for b in xs)
    x1 = min(b[2] for b in xs); y1 = min(b[3] for b in xs)
    frames = [f.crop((x0, y0, x1, y1)) for f in frames]
    scale = min(1.0, 250 / frames[0].width)
    frames = [f.resize((int(f.width * scale), int(f.height * scale))) for f in frames]
    frames[0].save(OUT_GIF, save_all=True, append_images=frames[1:],
                   duration=110, loop=0, disposal=2)
    print(f'[完成] {OUT_GIF} {len(frames)}帧 {frames[0].size}', flush=True)

    # 质检：帧间差异（应只在嘴部区域）
    for i in range(len(frames) - 1):
        a, b = frames[i], frames[i + 1]
        diff = sum(1 for x in range(a.width) for y in range(a.height)
                   if a.getpixel((x, y)) != b.getpixel((x, y)))
        print(f'  帧{i}->{i+1} 差异: {diff / (a.width * a.height) * 100:.1f}%', flush=True)

    # 保存一张 5 帧横向预览供检查
    preview = Image.new('RGBA', (frames[0].width * len(frames), frames[0].height), (255, 255, 255, 255))
    for i, f in enumerate(frames):
        preview.alpha_composite(f, (i * frames[0].width, 0))
    prev_path = os.path.join(PROJECT, 'tools', 'qa', 'talk_preview.png')
    os.makedirs(os.path.dirname(prev_path), exist_ok=True)
    preview.convert('RGB').save(prev_path)
    print('预览图:', prev_path, flush=True)


if __name__ == '__main__':
    main()
