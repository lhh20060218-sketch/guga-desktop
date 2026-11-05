# -*- coding: utf-8 -*-
"""嘴部补丁可行性检测：各帧喙部/嘴部位置与尺寸对比（决定能否对齐贴片）"""
import os
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)
from PIL import Image

SRC = os.environ.get('GUGA_TALK_FRAMES', 'samples/talk-frames')
EXCLUDE = ('041507d1', '7771be0b')


def find_beak(img):
    """黄色喙部 bbox + 嘴部深色区域"""
    w, h = img.size
    px = img.load()
    beak_pts = []
    dark_pts = []
    for y in range(int(h * 0.30), int(h * 0.75)):
        for x in range(int(w * 0.20), int(w * 0.80)):
            r, g, b, a = px[x, y]
            if a < 40:
                continue
            if r > 185 and g > 135 and b < 145:
                beak_pts.append((x, y))
            elif r < 110 and g < 90 and b < 90:
                dark_pts.append((x, y))
    def bb(pts):
        if not pts:
            return None
        xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
        return (min(xs), min(ys), max(xs), max(ys))
    return bb(beak_pts), bb(dark_pts)


for f in sorted(os.listdir(SRC)):
    if not f.lower().endswith('.png') or any(f.startswith(e) for e in EXCLUDE):
        continue
    img = Image.open(os.path.join(SRC, f)).convert('RGBA')
    beak, dark = find_beak(img)
    if beak:
        bx = (beak[0] + beak[2]) / 2
        by = (beak[1] + beak[3]) / 2
        print(f'{f[:8]} 喙部中心=({bx:.0f},{by:.0f}) 尺寸={beak[2]-beak[0]}x{beak[3]-beak[1]}'
              + (f' 深色嘴区={dark}' if dark else ''))
    else:
        print(f'{f[:8]} 未找到黄色喙部! 深色区={dark}')
