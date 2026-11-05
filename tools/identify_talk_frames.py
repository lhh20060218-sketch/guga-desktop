# -*- coding: utf-8 -*-
"""识别咕嘎说话动作文件夹里 5 张新图的口型/姿态"""
import subprocess
import sys
import os
import io
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)

NODE = os.environ.get('NODE_EXE', 'node')
CLIENT = os.environ.get('GLM_VISION_CLIENT', '')
KEY = os.environ.get('GLM_API_KEY', '')
IMGDIR = os.environ.get('GUGA_IMAGE_LIBRARY', 'samples/talk-frames')
if not CLIENT or not KEY:
    raise SystemExit('请设置 GLM_VISION_CLIENT 和 GLM_API_KEY 后再运行此开发工具')

# 只要新图（排除主表情库里已有的两张）
EXCLUDE = ('041507d1', '7771be0b')
files = [f for f in os.listdir(IMGDIR) if f.lower().endswith('.png')
         and not any(f.startswith(e) for e in EXCLUDE)]
files.sort()

env = dict(os.environ, GLM_API_KEY=KEY)
results = {}
for f in files:
    path = os.path.join(IMGDIR, f)
    print(f'===== {f[:8]}', flush=True)
    ok = False
    for attempt in range(8):
        p = subprocess.run(
            [NODE, CLIENT, path,
             '这是一张桌宠说话动画帧。用一句话回答：1)这只企鹅的嘴巴是什么状态（闭合/微张/张大/O型嘴/露出牙齿舌头）2)和普通闭嘴企鹅相比只有嘴巴不同，还是姿势也变了？'],
            capture_output=True, text=True, encoding='utf-8', errors='replace',
            env=env, timeout=180)
        out = p.stdout
        if '429' in out or '识别结果' not in out:
            print(f'  attempt{attempt+1} 限流，等20s…', flush=True)
            time.sleep(20)
            continue
        idx = out.find('=== 识别结果 ===')
        text = out[idx:].replace('=== 识别结果 ===', '').strip()
        results[f] = text
        print('  ' + text[:150].replace('\n', ' '), flush=True)
        ok = True
        break
    if not ok:
        results[f] = '(识别失败)'
        print('  识别失败', flush=True)
    time.sleep(8)

print()
print('===== 汇总 =====')
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'talk_frames_map.txt'), 'w', encoding='utf-8') as fo:
    for f, t in results.items():
        line = f'{f} => {t[:150]}'
        print(line, flush=True)
        fo.write(line + '\n')
