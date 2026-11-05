# -*- coding: utf-8 -*-
"""分析处理后的精灵图：找残留的矩形框组件"""
import os
import sys
import io
from collections import deque

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)
from PIL import Image

DST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   'resources', 'expressions')


def components(img):
    """返回 [(size, bbox, fill_ratio, touches_border)]"""
    w, h = img.size
    px = img.load()
    visited = bytearray(w * h)
    comps = []
    for y in range(h):
        for x in range(w):
            if visited[y * w + x] or px[x, y][3] == 0:
                continue
            q = deque([(x, y)])
            visited[y * w + x] = 1
            blob = []
            while q:
                cx, cy = q.popleft()
                blob.append((cx, cy))
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = cx + dx, cy + dy
                    if 0 <= nx < w and 0 <= ny < h and not visited[ny * w + nx] and px[nx, ny][3] > 0:
                        visited[ny * w + nx] = 1
                        q.append((nx, ny))
            xs = [p[0] for p in blob]
            ys = [p[1] for p in blob]
            bbox = (min(xs), min(ys), max(xs), max(ys))
            bw = bbox[2] - bbox[0] + 1
            bh = bbox[3] - bbox[1] + 1
            fill = len(blob) / (bw * bh) if bw * bh else 0
            touch = (bbox[0] == 0 or bbox[1] == 0 or bbox[2] == w - 1 or bbox[3] == h - 1)
            comps.append((len(blob), bbox, round(fill, 2), touch))
    return sorted(comps, key=lambda c: -c[0])


for name in sorted(os.listdir(DST)):
    if not name.endswith('.png'):
        continue
    img = Image.open(os.path.join(DST, name)).convert('RGBA')
    w, h = img.size
    comps = components(img)
    print(f'=== {name} ({w}x{h}) ===')
    for c in comps[:6]:
        size, bbox, fill, touch = c
        print(f'  组件 size={size} bbox={bbox} 填充率={fill} 触边={touch}')
    print()
