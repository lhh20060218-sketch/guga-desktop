# -*- coding: utf-8 -*-
"""
咕嘎动作素材管线：绿幕源视频 → 统一规格透明帧序列（桌宠 sprite_animator 直用）

对照 dsh-pet 素材链的裁剪版（抠像+归一化+统一规格）：
  1. 解码（兼容 HEVC/H.264 混合交付）
  2. chromakey 色键抠像（0x00FF00，相似度 0.18/混合 0.08，实测本批素材一次到位）
  3. despill 去绿边（绿溢出中和）
  4. 统一 768×1344 @24fps（1080×1920@60 降采样；1.6% 纵横比差异直接缩放，肉眼不可辨）
  5. 输出 PNG 帧序列 + 质检报告（帧数/时长/循环类首尾相似度）

用法:
    python tools/make_action_pack.py <源视频目录> <输出根目录>
输出:
    <输出根目录>/<动作名>/frames/f001.png ...
    <输出根目录>/_质检报告.md
"""
import io
import os
import shutil
import subprocess
import sys

FFMPEG = r"C:/Users/l/AppData/Local/Programs/Python/Python312/Lib/site-packages/imageio_ffmpeg/binaries/ffmpeg-win-x86_64-v9.0.2.exe"
HERE = os.path.dirname(os.path.abspath(__file__))

# 源文件名（不含扩展名）→ (桌宠动作名, 循环类型)  循环类型: loop=循环播放 oneshot=播一次即止
ACTIONS = {
    'butler_idle':        ('idle',        'loop'),
    'butler_commanding':  ('commanding',  'loop'),
    'butler_watching':    ('watching',    'loop'),
    'butler_asking':      ('asking',      'loop'),
    'butler_reviewing':   ('reviewing',   'loop'),
    'butler_urge':        ('urge',        'loop'),
    'butler_celebrating': ('celebrating', 'oneshot'),
    'butler_reject':      ('reject',      'oneshot'),
    'butler_accept':      ('accept',      'oneshot'),
    'butler_pet':         ('pet',         'oneshot'),
    'butler_hello':       ('hello',       'oneshot'),
    'butler_error':       ('error',       'oneshot'),
}

TARGET_W, TARGET_H, TARGET_FPS = 384, 672, 24   # 显示宽260的1.5倍；WebP 有损：12动作≈30MB（PNG 768宽要691MB）
# 色键参数: 色值 / 相似度 / 混合度 —— 2026-11-06 对 dz3 批实测一次到位，动过需重验边缘
CHROMA = 'chromakey=0x00FF00:0.18:0.08'
DESPILL = 'despill=type=green'


def probe(path):
    """返回 (宽, 高, fps, 时长秒)——解析失败返回 None 项。"""
    r = subprocess.run([FFMPEG, '-i', path], capture_output=True, text=True, encoding='utf-8', errors='ignore')
    import re
    info = r.stderr
    m = re.search(r'(\d{2,4})x(\d{2,4}).*?([\d.]+) fps', info)
    d = re.search(r'Duration: (\d+):(\d+):([\d.]+)', info)
    if not m or not d:
        return None
    w, h, fps = int(m.group(1)), int(m.group(2)), float(m.group(3))
    dur = int(d.group(1)) * 3600 + int(d.group(2)) * 60 + float(d.group(3))
    return w, h, fps, dur


def frame_tail_similarity(dirpath, n):
    """循环类首尾相似度: 末帧与首帧灰度平均差(0-255)，<8 视为衔接良好。"""
    try:
        from PIL import Image
        import numpy
        a = numpy.asarray(Image.open(os.path.join(dirpath, 'f001.webp')).convert('L'), dtype=numpy.int16)
        b = numpy.asarray(Image.open(os.path.join(dirpath, 'f%03d.webp' % n)).convert('L'), dtype=numpy.int16)
        return float(numpy.abs(a - b).mean())
    except Exception as e:
        return -1.0


def main(src_dir, out_root):
    report = ['# 动作素材管线质检报告', '', '| 源 | 规格 | 动作 | 类型 | 帧数 | 时长s | 首尾差 | 判定 |', '|---|---|---|---|---|---|---|---|']
    names = sorted(os.listdir(src_dir))
    for name in names:
        stem, ext = os.path.splitext(name)
        if ext.lower() not in ('.mp4', '.mov', '.webm'):
            continue
        stem = stem.split('_v')[0]           # 去 _v2 之类后缀
        if stem not in ACTIONS:
            print('跳过（无映射）:', name)
            continue
        action, kind = ACTIONS[stem]
        src = os.path.join(src_dir, name)
        spec = probe(src)
        outdir = os.path.join(out_root, action, 'frames')
        if os.path.exists(outdir):
            shutil.rmtree(outdir)
        os.makedirs(outdir)
        vf = '%s,%s,scale=%d:%d,fps=%d' % (CHROMA, DESPILL, TARGET_W, TARGET_H, TARGET_FPS)
        r = subprocess.run([FFMPEG, '-y', '-i', src, '-vf', vf,
                            '-c:v', 'libwebp', '-lossless', '0', '-q:v', '82',
                            os.path.join(outdir, 'f%03d.webp')],
                           capture_output=True, text=True, encoding='utf-8', errors='ignore')
        n = len([f for f in os.listdir(outdir) if f.endswith('.webp')])
        if n == 0:
            report.append('| %s | %s | %s | %s | 0 | - | - | ❌ 抠像失败 |' % (name, spec, action, kind))
            continue
        tail = frame_tail_similarity(outdir, n) if kind == 'loop' else None
        if kind == 'loop':
            judge = '✅ 循环衔接良好' if 0 <= tail < 8 else ('⚠️ 首尾差异大(%0.1f) 需复核' % tail if tail >= 0 else '⚠️ 未能计算')
            tail_txt = '%0.1f' % tail if tail >= 0 else 'n/a'
        else:
            judge, tail_txt = '✅ 一次性动作', 'n/a'
        dur = n / float(TARGET_FPS)
        report.append('| %s | %dx%d@%g | %s | %s | %d | %.2f | %s | %s |' %
                      (name, spec[0], spec[1], spec[2], action, kind, n, dur, tail_txt, judge))
        print('%-24s -> %-12s %3d 帧  %s' % (name, action, n, judge))
    with io.open(os.path.join(out_root, '_质检报告.md'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(report) + '\n')
    print('\n报告:', os.path.join(out_root, '_质检报告.md'))


if __name__ == '__main__':
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])
