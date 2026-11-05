# -*- coding: utf-8 -*-
"""咕嘎素材视频批量裁剪工具
背景: AI 视频工具最低生成 4 秒, 但桌宠状态动画需要 1~3 秒。
队友交付 4 秒原片, 本工具按清单自动裁剪到有效动作时长:
  - loop   循环类: 自动寻找"动作回到起始姿势"的帧, 裁出干净的一轮循环
  - oneshot 一次性: 裁到指定时长 (动作做完为止的节奏由素材本身保证)
用法:
  python tools/trim_video.py <素材目录> [-o 输出目录]
输出: <输出目录>/同名文件 (默认 <素材目录>/processed/)
依赖: imageio-ffmpeg (自带 ffmpeg), Pillow
"""
import os
import shutil
import subprocess
import sys
import tempfile

from PIL import Image

import imageio_ffmpeg

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
FPS = 24

# 每条素材的处理配置 (对照素材要求 v2 的清单)
# mode: loop=找回位帧裁一轮循环; oneshot=裁到 secs 秒
# secs: oneshot 的目标时长; loop 模式忽略
# max_scan: loop 模式最多扫描前多少秒找回位帧 (循环要求 4s 内至少完整一轮)
PLAN = {
    'butler_idle.mp4':       {'mode': 'loop', 'min_secs': 3.0},
    'butler_commanding.mp4': {'mode': 'loop', 'min_secs': 2.0},
    'butler_watching.mp4':   {'mode': 'loop', 'min_secs': 2.0},
    'butler_asking.mp4':     {'mode': 'loop', 'min_secs': 2.0},
    'butler_reviewing.mp4':  {'mode': 'loop', 'min_secs': 2.0},
    'butler_celebrating.mp4': {'mode': 'oneshot', 'secs': 2.0},
    'butler_urge.mp4':       {'mode': 'loop', 'min_secs': 1.5},
    'butler_reject.mp4':     {'mode': 'oneshot', 'secs': 2.0},
    'butler_accept.mp4':     {'mode': 'oneshot', 'secs': 1.5},
    'butler_pet.mp4':        {'mode': 'oneshot', 'secs': 1.0},
    'butler_hello.mp4':      {'mode': 'oneshot', 'secs': 1.0},
    'butler_error.mp4':      {'mode': 'oneshot', 'secs': 1.5},
}


def probe_duration(path):
    r = subprocess.run([FFMPEG, '-i', path], capture_output=True, text=True, errors='ignore')
    for line in r.stderr.splitlines():
        if 'Duration' in line:
            h, m, s = line.split('Duration:')[1].strip().split(',')[0].split(':')
            return int(h) * 3600 + int(m) * 60 + float(s)
    return None


def extract_frames(path, out_dir, limit_secs=None):
    """抽帧为 png, 返回帧文件列表(按时间序)."""
    cmd = [FFMPEG, '-y', '-i', path]
    if limit_secs:
        cmd += ['-t', str(limit_secs)]
    cmd += [os.path.join(out_dir, 'f%04d.png')]
    subprocess.run(cmd, capture_output=True, check=True)
    return sorted(f for f in os.listdir(out_dir) if f.endswith('.png'))


def frame_sig(png_path, size=(32, 56)):
    """帧指纹: 缩小+灰度的像素元组, 用于回位帧比对."""
    im = Image.open(png_path).convert('L').resize(size)
    return list(im.getdata())


def sig_dist(a, b):
    return sum(abs(x - y) for x, y in zip(a, b))


def find_loop_point(frames_dir, frames, min_secs):
    """从 min_secs 之后找与首帧最像的帧 -> 动作回位点."""
    first = frame_sig(os.path.join(frames_dir, frames[0]))
    start = max(1, int(min_secs * FPS))
    best_i, best_d = None, None
    for i in range(start, len(frames)):
        d = sig_dist(first, frame_sig(os.path.join(frames_dir, frames[i])))
        if best_d is None or d < best_d:
            best_d, best_i = d, i
    return best_i, best_d


def reencode(src, dst, cut_secs):
    """裁剪并重编码 H.264 yuv420p (去掉源若含 hevc/奇怪参数的风险)."""
    cmd = [FFMPEG, '-y', '-i', src, '-t', str(cut_secs),
           '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-an',
           '-movflags', '+faststart', dst]
    subprocess.run(cmd, capture_output=True, check=True)


def process(path, out_dir, report):
    name = os.path.basename(path)
    cfg = PLAN.get(name)
    dur = probe_duration(path)
    if cfg is None:
        report.append(('SKIP', name, '清单里没有, 原样复制'))
        shutil.copy2(path, os.path.join(out_dir, name))
        return
    mode = cfg['mode']
    if dur is None:
        report.append(('FAIL', name, '读不到时长'))
        return
    if dur <= (cfg.get('secs') or cfg.get('min_secs') or 0) + 0.05:
        # 已经够短, 原样转码
        reencode(path, os.path.join(out_dir, name), dur)
        report.append(('OK', name, '原片已短(%.2fs), 直接转码' % dur))
        return

    with tempfile.TemporaryDirectory() as td:
        if mode == 'loop':
            frames = extract_frames(path, td)
            idx, dist = find_loop_point(td, frames, cfg['min_secs'])
            # 保险: 相似距离过大 = 动作没有真正回位, 硬裁会切出跳变
            # 阈值按经验: 32x56 灰度指纹总像素 1792, 每像素平均差 >12 视为不像
            if dist > 1792 * 12:
                report.append(('WARN', name, '未找到可靠回位帧(距离%d>21400), 保留原片人工确认' % dist))
                shutil.copy2(path, os.path.join(out_dir, name))
                return
            cut = idx / FPS
            reencode(path, os.path.join(out_dir, name), cut)
            report.append(('OK', name, 'loop: 回位帧 %.2fs (相似距离%d), 裁后 %.2fs' % (cut, dist, cut)))
        else:
            cut = cfg['secs']
            reencode(path, os.path.join(out_dir, name), cut)
            report.append(('OK', name, 'oneshot: 裁到 %.2fs (原片 %.2fs)' % (cut, dur)))


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('-')]
    if not args:
        print(__doc__)
        return 1
    src = os.path.abspath(args[0])
    out_dir = os.path.join(src, 'processed')
    if '-o' in sys.argv:
        out_dir = os.path.abspath(sys.argv[sys.argv.index('-o') + 1])
    os.makedirs(out_dir, exist_ok=True)
    report = []
    for f in sorted(os.listdir(src)):
        if f.lower().endswith('.mp4'):
            process(os.path.join(src, f), out_dir, report)
    print('=' * 56)
    for status, name, msg in report:
        print('[%s] %s\n       %s' % (status, name, msg))
    ok = sum(1 for r in report if r[0] == 'OK')
    print('=' * 56)
    print('完成 %d/%d, 输出: %s' % (ok, len(report), out_dir))
    return 0


if __name__ == '__main__':
    sys.exit(main())
