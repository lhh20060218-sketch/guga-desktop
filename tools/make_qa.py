# -*- coding: utf-8 -*-
"""棋盘格合成质检图"""
import os
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)
from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'resources', 'expressions')
OUT = os.path.join(ROOT, 'tools', 'qa')
os.makedirs(OUT, exist_ok=True)

for name in ['happy_transparent.png', 'surprised_transparent.png', 'playful_transparent.png', 'sad_transparent.png', 'sleepy_transparent.png']:
    im = Image.open(os.path.join(SRC, name)).convert('RGBA')
    w, h = im.size
    chk = Image.new('RGBA', (w, h))
    dr = ImageDraw.Draw(chk)
    for y in range(0, h, 20):
        for x in range(0, w, 20):
            c = (200, 200, 200, 255) if (x // 20 + y // 20) % 2 == 0 else (255, 255, 255, 255)
            dr.rectangle([x, y, x + 19, y + 19], fill=c)
    chk.alpha_composite(im)
    chk.save(os.path.join(OUT, name))
    print('saved', name, im.size)
