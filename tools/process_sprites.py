# -*- coding: utf-8 -*-
"""咕嘎企鹅素材处理 v2：去背景板+去水印+去杂图案

流程：
1. 泛洪填充：从四边扩散，删除连通的"背景色"（白~浅灰，含底板）
2. 连通域分析：保留最大的几个连通块（企鹅主体），删除小孤岛
   （"AI生成"水印文字、散落图案等）
3. 边缘羽化 + 裁剪留白
"""
import os
import sys
import io
import shutil
from collections import deque

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)
from PIL import Image

SRC = os.environ.get('GUGA_IMAGE_LIBRARY', 'samples')
PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DST = os.path.join(PROJECT, 'resources', 'expressions')

# 文件前缀 → 表情名
EXPR_MAP = {
    '4fe3bb39': 'happy',
    '041507d1': 'surprised',
    '90d95e21': 'sleepy',
    '06e86cba': 'playful',   # 生气脸 → 傲娇/调皮
    '7771be0b': 'sad',       # 委屈
    # d91e7d63 是哭泣脸，不用于日常；日常 normal 由 happy 兼任（复制）
}

BG_THRESHOLD = 205          # 背景判定（白~浅灰底板）
MIN_BLOB_RATIO = 0.015      # 小于画面 1.5% 的连通块视为水印/杂物


def remove_bg_and_noise(img):
    """去背景 + 去小连通块"""
    w, h = img.size
    px = img.load()
    bg = bytearray(w * h)
    visited = bytearray(w * h)
    q = deque()

    for x in range(w):
        for y in (0, h - 1):
            q.append((x, y)); visited[y * w + x] = 1
    for y in range(h):
        for x in (0, w - 1):
            q.append((x, y)); visited[y * w + x] = 1

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

    # 非背景像素的连通域（4-连通），只保留大块
    keep = bytearray(w * h)
    comp_id = 0
    comps = {}  # id -> size
    for y in range(h):
        for x in range(w):
            if bg[y * w + x] or keep[y * w + x]:
                continue
            # 开始新连通域（BFS）
            comp_id += 1
            size = 0
            cq = deque([(x, y)])
            keep[y * w + x] = 1
            while cq:
                cx, cy = cq.popleft()
                size += 1
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = cx + dx, cy + dy
                    if 0 <= nx < w and 0 <= ny < h and not bg[ny * w + nx] and not keep[ny * w + nx]:
                        keep[ny * w + nx] = 1
                        cq.append((nx, ny))
            comps[comp_id] = size

    total_px = w * h
    min_size = total_px * MIN_BLOB_RATIO
    big_comps = {cid for cid, s in comps.items() if s >= min_size}

    # 构建透明图
    out = img.convert('RGBA')
    opx = out.load()
    # 二次遍历：标记最终保留像素（用另一张标记图记录 comp 归属）
    mark = bytearray(w * h)  # 0=背景, 1=保留, 2=删除(小岛)
    # 重新做一次连通域，这次直接记 mark
    mark_visited = bytearray(w * h)
    for y in range(h):
        for x in range(w):
            if bg[y * w + x] or mark_visited[y * w + x]:
                continue
            cq = deque([(x, y)])
            mark_visited[y * w + x] = 1
            blob = []
            while cq:
                cx, cy = cq.popleft()
                blob.append((cx, cy))
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = cx + dx, cy + dy
                    if 0 <= nx < w and 0 <= ny < h and not bg[ny * w + nx] and not mark_visited[ny * w + nx]:
                        mark_visited[ny * w + nx] = 1
                        cq.append((nx, ny))
            keep_this = len(blob) >= min_size
            for bx, by in blob:
                mark[by * w + bx] = 1 if keep_this else 2

    for y in range(h):
        for x in range(w):
            if mark[y * w + x] != 1:
                opx[x, y] = (opx[x, y][0], opx[x, y][1], opx[x, y][2], 0)
            else:
                r, g, b, a = opx[x, y]
                # 白边去污染（单遍）：纯白像素且邻接透明 → 直接裁掉
                # （不做半透明化，避免出现"白色方框"光晕）
                if r >= 248 and g >= 248 and b >= 248:
                    near_bg = any(
                        0 <= x + dx < w and 0 <= y + dy < h and mark[(y + dy) * w + (x + dx)] == 0
                        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
                    )
                    if near_bg:
                        opx[x, y] = (r, g, b, 0)
    return out


def trim(img):
    bbox = img.getbbox()
    return img.crop(bbox) if bbox else img


def main():
    os.makedirs(DST, exist_ok=True)
    report = []
    for prefix, expr in EXPR_MAP.items():
        names = [f for f in os.listdir(SRC) if f.startswith(prefix) and f.lower().endswith('.png')]
        if not names:
            print(f'[跳过] {expr}: 未找到 {prefix}*', flush=True)
            continue
        src_name = names[0]
        img = Image.open(os.path.join(SRC, src_name)).convert('RGB')
        out = trim(remove_bg_and_noise(img))
        path = os.path.join(DST, f'{expr}_transparent.png')
        out.save(path)
        print(f'[OK] {expr}: {img.size} -> {out.size}', flush=True)

    # normal = happy 副本
    import shutil
    shutil.copy(os.path.join(DST, 'happy_transparent.png'),
                os.path.join(DST, 'normal_transparent.png'))
    print('[OK] normal（=happy 副本，日常开心脸）', flush=True)

    # 质检
    print('--- 质检 ---', flush=True)
    for name in sorted(os.listdir(DST)):
        im = Image.open(os.path.join(DST, name)).convert('RGBA')
        w, h = im.size
        corners = [im.getpixel((0, 0))[3], im.getpixel((w - 1, 0))[3],
                   im.getpixel((0, h - 1))[3], im.getpixel((w - 1, h - 1))[3]]
        cx, cy = w // 2, h // 2
        center = im.getpixel((cx, cy))
        print(f'{name}: 角透明={corners} 中心={center[:3]}a={center[3]}', flush=True)
    print('完成', flush=True)


if __name__ == '__main__':
    main()
