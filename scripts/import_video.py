# -*- coding: utf-8 -*-
"""M0.1 素材导入工具: 队友视频 -> 员工素材目录 (接口的最后一公里)

用法:
  # 从 mp4 导入(自动抽帧+抠绿幕+缩放)
  python scripts/import_video.py butler_to_scholar.mp4 scholar summon

  # 从已抽好的 PNG 目录导入(跳过 ffmpeg)
  python scripts/import_video.py --from-pngs D:\\frames_dir scholar summon

  # 人工审看过帧后批准(审核链要求, 批准后动画才会被播放)
  python scripts/import_video.py --approve 队友A scholar summon

行为:
  1. ffmpeg 定位: 环境变量 FFMPEG_PATH > PATH > imageio_ffmpeg > C:\ffmpeg\bin
  2. 抽帧: chromakey 抠纯绿 #00FF00 -> 透明 PNG, 默认 24fps
  3. 写 visual-review.json (status=pending, frames_sha256 自动计算)
  4. 登记 armor-manifest.json (cache=full, one_shot 按片段类型推断)
  5. 导入后运行 scripts/demo_armor_switch.py 验证回退链与播放
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RES = REPO / 'resources'
sys.path.insert(0, str(REPO))
from core.avatar_review import frames_digest  # noqa: E402

VALID_ARMORS = ('butler', 'scholar', 'tactician', 'steward',
                'navigator', 'medic', 'artisan')
ONE_SHOT_HINTS = ('summon', 'to_', 'happy', 'angry', 'hello')  # 非循环片段


def find_ffmpeg():
    env = os.environ.get('FFMPEG_PATH')
    if env and Path(env).is_file():
        return env
    found = shutil.which('ffmpeg')
    if found:
        return found
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        pass
    for cand in (r'C:\ffmpeg\bin\ffmpeg.exe',
                 r'C:\Program Files\ffmpeg\bin\ffmpeg.exe'):
        if Path(cand).is_file():
            return cand
    return None


def extract_frames(ffmpeg, mp4, frames_dir, fps, scale=None):
    """抠绿幕抽帧: 纯绿 #00FF00 -> alpha 透明."""
    frames_dir.mkdir(parents=True, exist_ok=True)
    vf = 'chromakey=0x00FF00:0.25:0.08'
    if scale:
        vf += ',scale=%s' % scale
    cmd = [ffmpeg, '-y', '-i', str(mp4), '-vf', vf,
           '-r', str(fps), '-vsync', '0',
           str(frames_dir / 'frame_%04d.png')]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        sys.exit('ffmpeg 失败:\n%s' % proc.stderr[-1500:])
    n = len(list(frames_dir.glob('*.png')))
    if n == 0:
        sys.exit('抽帧结果为空, 检查 mp4 与 chromakey 参数')
    return n


def import_pngs(src_dir, frames_dir):
    frames_dir.mkdir(parents=True, exist_ok=True)
    n = 0
    for png in sorted(Path(src_dir).glob('*.png')):
        shutil.copy2(png, frames_dir / png.name)
        n += 1
    if n == 0:
        sys.exit('源目录没有 PNG: %s' % src_dir)
    return n


def write_review(clip_dir, one_shot, approve_reviewer=None):
    review = {
        'status': 'approved' if approve_reviewer else 'pending',
        'reviewer': approve_reviewer or '',
        'checks': {
            'continuous_motion': bool(approve_reviewer),
            'no_ghosts': bool(approve_reviewer),
            'anatomy': bool(approve_reviewer),
            'identity': bool(approve_reviewer),
            'loop_seam': bool(approve_reviewer) and not one_shot,
            'entry_exit_transition': bool(approve_reviewer) and one_shot,
        },
        'playback': 'once' if one_shot else 'loop',
        'frames_sha256': frames_digest(clip_dir / 'frames'),
        'note': '导入工具生成; approve 表示人工逐帧审看过(动作连贯/无残影/无崩坏/形象一致)'
    }
    (clip_dir / 'visual-review.json').write_text(
        json.dumps(review, ensure_ascii=False, indent=2), encoding='utf-8')


def register_manifest(armor_id, clip_name, fps, one_shot):
    man_path = RES / 'armor' / 'armor-manifest.json'
    manifest = json.loads(man_path.read_text(encoding='utf-8'))
    clips = manifest.setdefault('armor_clips', {}).setdefault(armor_id, {})
    clips[clip_name] = {
        'frames': '%s/frames' % clip_name,
        'native_fps': float(fps),
        'weight': 1.0,
        'source': 'armor',
        'cache': {'strategy': 'full'},
        'one_shot': one_shot,
    }
    man_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                        encoding='utf-8')


def main():
    args = [a for a in sys.argv[1:]]
    from_pngs = None
    approve = None
    fps = 24.0
    one_shot_hint = None
    if '--from-pngs' in args:
        i = args.index('--from-pngs')
        from_pngs = args[i + 1]
        del args[i:i + 2]
    if '--approve' in args:
        i = args.index('--approve')
        approve = args[i + 1]
        del args[i:i + 2]
    if '--fps' in args:
        i = args.index('--fps')
        fps = float(args[i + 1])
        del args[i:i + 2]
    if '--one-shot' in args:
        i = args.index('--one-shot')
        one_shot_hint = True
        del args[i:i + 1]
    if not args:
        sys.exit(__doc__)
    # approve-only 模式: 重新批准已导入的片段(不重新导入)
    approve_only = bool(approve) and not from_pngs and len(args) == 2 \
        and not str(args[0]).lower().endswith(('.mp4', '.mov', '.webm'))
    if from_pngs:
        src = None
        if len(args) < 2:
            sys.exit('用法: --from-pngs <png目录> <armor_id> <clip_name>')
        armor_id, clip_name = args[0], args[1]
    elif approve_only:
        armor_id, clip_name = args[0], args[1]
    else:
        if len(args) < 3:
            sys.exit('用法: <mp4> <armor_id> <clip_name> [--fps N] [--one-shot]')
        src = args[0]
        armor_id, clip_name = args[1], args[2]
    if armor_id not in VALID_ARMORS:
        sys.exit('非法员工 id: %s (合法: %s)' % (armor_id, ', '.join(VALID_ARMORS)))

    clip_dir = RES / 'armor' / armor_id / clip_name
    frames_dir = clip_dir / 'frames'
    if approve_only:
        print('[0/3] 批准模式: 不重新导入, 仅更新审核状态')
    elif from_pngs:
        n = import_pngs(from_pngs, frames_dir)
        print('[1/3] 已复制 %d 帧 <- %s' % (n, from_pngs))
    else:
        ffmpeg = find_ffmpeg()
        if not ffmpeg:
            sys.exit('未找到 ffmpeg; 安装后重试, 或用 --from-pngs 导入已抽帧目录')
        n = extract_frames(ffmpeg, src, frames_dir, fps)
        print('[1/3] ffmpeg 抽帧+抠绿幕: %d 帧 (%s, %sfps)' % (n, ffmpeg, fps))

    one_shot = one_shot_hint if one_shot_hint is not None \
        else any(h in clip_name for h in ONE_SHOT_HINTS)
    write_review(clip_dir, one_shot, approve)
    print('[2/3] visual-review.json: status=%s (one_shot=%s)'
          % ('approved' if approve else 'pending', one_shot))

    register_manifest(armor_id, clip_name, fps, one_shot)
    print('[3/3] armor-manifest.json 已登记: %s/%s' % (armor_id, clip_name))

    print('\n完成. 后续:')
    if not approve:
        print('  - 逐帧审看 %s 后执行: python scripts/import_video.py --approve 审看人 %s %s'
              % (frames_dir, armor_id, clip_name))
    print('  - 验证: python scripts/demo_armor_switch.py')
    print('  - 播放: ArmorPack.animation.summon_clip/idle_clip 填 %r 即生效'
          % clip_name)


if __name__ == '__main__':
    main()
