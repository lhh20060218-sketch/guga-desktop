# -*- coding: utf-8 -*-
"""把 cogview 生成的连拍精灵表切成帧 → 透明 GIF → stickers 目录"""
import os
import sys
import io
from collections import deque

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHEET = os.path.join(ROOT, 'resources', 'stickers', 'jump_sheet.png')
OUT = os.path.join(ROOT, 'resources', 'stickers', 'jump_sheet.gif')


def remove_bg(img):
    """白底→透明（边缘泛洪）"""
    w, h = img.size
    px = img.load()
    bg = bytearray(w * h)
    q = deque()
    for x in range(w):
        q.append((x, 0)); q.append((x, h - 1))
    for y in range(h):
        q.append((0, y)); q.append((w - 1, y))
    seen = bytearray(w * h)
    while q:
        x, y = q.popleft()
        if seen[y * w + x]:
            continue
        seen[y * w + x] = 1
        r, g, b = px[x, y][:3]
        if r < 225 or g < 225 or b < 225:
            continue
        bg[y * w + x] = 1
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < w and 0 <= ny < h and not seen[ny * w + nx]:
                q.append((nx, ny))
    out = img.convert('RGBA')
    opx = out.load()
    for y in range(h):
        for x in range(w):
            if bg[y * w + x]:
                opx[x, y] = (opx[x, y][0], opx[x, y][1], opx[x, y][2], 0)
    return out


def main():
    if not os.path.exists(SHEET):
        print('精灵表不存在，跳过:', SHEET)
        return
    sheet = Image.open(SHEET).convert('RGB')
    w, h = sheet.size
    n = 4
    fw = w // n
    frames = []
    for i in range(n):
        frame = sheet.crop((i * fw, 0, (i + 1) * fw, h))
        frame = remove_bg(frame)
        # 裁剪透明边
        bbox = frame.getbbox()
        if bbox:
            frame = frame.crop(bbox)
        # 统一尺寸（以最大为准，透明居中）
        frames.append(frame)
    maxw = max(f.size[0] for f in frames)
    maxh = max(f.size[1] for f in frames)
    unified = []
    for f in frames:
        c = Image.new('RGBA', (maxw, maxh), (0, 0, 0, 0))
        c.alpha_composite(f, ((maxw - f.size[0]) // 2, maxh - f.size[1]))
        unified.append(c)
    # 缩放显示尺寸并转 GIF
    scale = min(1.0, 250 / maxw)
    unified = [u.resize((int(u.width * scale), int(u.height * scale))) for u in unified]
    unified[0].save(OUT, save_all=True, append_images=unified[1:],
                    duration=120, loop=0, disposal=2)
    print('已生成 GIF:', OUT, len(unified), '帧', unified[0].size)


if __name__ == '__main__':
    main()
