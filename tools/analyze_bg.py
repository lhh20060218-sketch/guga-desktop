# -*- coding: utf-8 -*-
"""分析企鹅原图：找出背景板颜色、水印位置，评估裁剪策略"""
import os
import sys
import io
from collections import Counter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)
from PIL import Image

SRC = os.environ.get('GUGA_IMAGE_LIBRARY', 'samples')

for name in sorted(os.listdir(SRC)):
    if not name.lower().endswith('.png'):
        continue
    img = Image.open(os.path.join(SRC, name)).convert('RGB')
    w, h = img.size
    px = img.load()

    # 1) 四角颜色（背景候选）
    corners = [px[0, 0], px[w - 1, 0], px[0, h - 1], px[w - 1, h - 1]]
    print(f'=== {name[:8]}  {w}x{h} ===')
    print('  四角颜色:', corners)

    # 2) 统计主要颜色（量化到 16 级）
    small = img.resize((64, 64))
    q = small.quantize(colors=12)
    counts = Counter(q.getdata())
    top = q.getpalette()
    print('  主要色块:')
    for idx, cnt in counts.most_common(8):
        r, g, b = top[idx * 3:idx * 3 + 3]
        print(f'    RGB({r},{g},{b}) x{cnt}')

    # 3) 边框一圈是否有非背景像素（水印常在角落）
    edge = []
    for x in range(0, w, 3):
        edge.append(px[x, 0]); edge.append(px[x, h - 1])
    for y in range(0, h, 3):
        edge.append(px[0, y]); edge.append(px[w - 1, y])
    ec = Counter(edge)
    print('  边框主色:', ec.most_common(3))
    print()
