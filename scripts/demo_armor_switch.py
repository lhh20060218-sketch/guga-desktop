# -*- coding: utf-8 -*-
"""M0.1 demo: 七模式(管家+六位部门员工)召唤全链路演示

演示内容:
  1. ArmorAssetResolver 三级回退 (armor -> butler -> actions)
  2. ModeManager 启动默认 = 管家常驻 (静默, 无信号)
  3. 召唤: 召唤片段播完 -> mode_changed -> 新员工 idle
  4. 召回: summon 倒放(#rev) -> 回管家, 素材零成本
  5. 权限收敛钩子拒绝 + 缺素材回退链
  6. 素材替换零代码改动证明

无 GUI 依赖: MockAnimator 模拟 SpriteAnimator 的 clip 播放/回调.
运行: python scripts/demo_armor_switch.py
"""
import os
import sys
from pathlib import Path

REPO = os.environ.get('GUGA_DEMO_REPO') or str(Path(__file__).resolve().parents[1])
sys.path.insert(0, REPO)

from ui.asset_interface import ArmorAssetResolver
from core.mode_manager import ModeManager

RES = str(Path(REPO) / 'resources')
PACKS = str(Path(REPO) / 'armor_packs')

SEP = '=' * 62


class MockSeq:
    """模拟 LazyFrameSequence: 持有帧路径序列, 供倒放验证."""

    def __init__(self, paths):
        self.paths = list(paths)
        self.cache = {}


class MockAnimator:
    """模拟 SpriteAnimator: 记录 play_clip 调用, 手动触发 on_clip_finished."""

    def __init__(self):
        self.clips = {}
        self.play_log = []
        self.on_clip_finished = None

    def _load_action_frames(self, name, frames_dir, fps=15.0, lazy=False,
                            cache_spec=None):
        # 模拟按文件名排序后的帧序列
        self.clips[name] = {'frames': MockSeq(['f01.png', 'f02.png', 'f03.png']),
                            'fps': fps, 'loop': True}

    def play_clip(self, name, loop=False):
        self.play_log.append((name, loop))
        print('    [animator] play_clip(%r, loop=%s)' % (name, loop))

    def finish_clip(self, name):
        if self.on_clip_finished:
            print('    [animator] clip finished: %r' % name)
            self.on_clip_finished(name)


def section(title):
    print('\n' + SEP)
    print('  %s' % title)
    print(SEP)


def main():
    # ========== 1. 三级回退解析 ==========
    section('1. 三级回退: armor -> butler -> actions')
    resolver = ArmorAssetResolver(RES)
    print('启动默认解析目标: %s (管家)' % resolver.armor_id)

    resolver.set_armor('scholar')
    s = resolver.resolve_clip('heart')
    print('scholar + heart      -> source=%s' % s.source)
    s = resolver.resolve_clip('doze')
    print('scholar + doze       -> source=%s (scholar 无 doze, 回退管家)' % s.source)
    resolver.set_armor('medic')
    s = resolver.resolve_clip('doze')
    print('medic + doze         -> source=%s (回退管家)' % s.source)
    s = resolver.resolve_clip('look-up-step', namespace='task')
    print('medic + task 动作    -> source=%s (回退 actions)' % s.source)
    s = resolver.resolve_clip('nonexistent')
    print('medic + ???          -> %s (三级都未命中)' % s)
    bad = resolver.set_armor('officer')
    print('set_armor(officer)   -> %s (officer 已更名 steward, 非法 id 拒绝)' % bad)

    # ========== 2. 启动默认 = 管家常驻 ==========
    section('2. ModeManager 启动: 管家常驻中枢')
    animator = MockAnimator()
    mm = ModeManager(PACKS, animator=animator, resolver=resolver)
    print('已加载七模式: %s' % [m[0] for m in mm.list_modes()])
    print('启动 current = %s (应无条件为 butler, 无切换信号)' % mm.current_id)

    events = []
    mm.mode_changing.connect(lambda o, n: events.append('changing(%s->%s)' % (o, n)))
    mm.mode_changed.connect(lambda n: events.append('changed(%s)' % n))
    mm.mode_rejected.connect(lambda n, r: events.append('rejected(%s:%s)' % (n, r)))

    # ========== 3. 召唤(缺素材 = 立即切换回退链) ==========
    section('3. 召唤学者 (无召唤素材 -> 立即完成)')
    events.clear()
    mm.switch('scholar')
    print('信号: %s' % ' -> '.join(events))
    print('current = %s, resolver = %s' % (mm.current_id, resolver.armor_id))

    # ========== 4. 召唤片段衔接 + 召回倒放 ==========
    section('4. 召唤片段播完衔接 + 召回 = 倒放')
    events.clear()
    animator.play_log.clear()
    # 模拟素材入库: 军师甲的 summon 片段已抽帧登记('doze' 可经管家级回退解析)
    tact = mm.get_pack('tactician')
    tact.summon_clip = 'doze'
    resolver.set_armor('tactician')

    print('-- switch(tactician) [带 summon_clip] --')
    mm.switch('tactician')
    print('switch 返回后(片段未播完): %s' % (' -> '.join(events) if events else '(等待片段结束)'))
    print('current = %s (尚未完成切换)' % mm.current_id)
    animator.finish_clip('doze')
    print('片段播完后: %s' % ' -> '.join(events))
    print('current = %s' % mm.current_id)

    print('\n-- 召回管家: 倒放 tactician 的 summon 片段(素材零成本) --')
    events.clear()
    animator.play_log.clear()
    mm.switch('butler')
    if mm.current_id != 'butler':
        print('(召回片段播放中...) 模拟播完:')
        animator.finish_clip('doze#rev')
    print('信号: %s' % ' -> '.join(events))
    print('current = %s (管家)' % mm.current_id)
    seq = animator.clips.get('doze#rev', {}).get('frames')
    print('倒放注册: doze#rev in clips -> %s' % ('doze#rev' in animator.clips))
    print('倒放帧序: %s (正放为 f01->f02->f03)' % '->'.join(seq.paths) if seq else '无')

    # ========== 5. 权限收敛钩子 ==========
    section('5. 权限收敛钩子')
    events.clear()

    def permission_hook(old_pack, new_pack):
        diff = mm.permission_diff(old_pack, new_pack)
        print('    [hook] 权限变更字段: %s' % list(diff.keys()))
        if new_pack.id == 'steward':      # 事务官权限最宽, 演示拒绝路径
            print('    [hook] 拒绝: steward 权限过宽, 需二次确认')
            return False
        return True

    mm.set_permission_hook(permission_hook)
    result = mm.switch('steward')
    print('switch(steward) 返回: %s, 信号: %s' % (result, ' -> '.join(events)))
    result = mm.switch('navigator')
    print('switch(navigator) 返回: %s, current = %s' % (result, mm.current_id))

    # ========== 6. 零代码改动证明 ==========
    section('6. 素材替换零代码改动')
    print('召唤素材入库流程: 队友视频 -> 抽帧 -> armor/<id>/summon/frames/*.png')
    print('-> armor-manifest.json 登记 -> ArmorPack.summon_clip 填片段名')
    print('-> 召唤/召回自动生效, .py 零改动.')

    print('\n' + SEP)
    print('  DEMO 完成 — 七模式(管家+六甲)全链路验证')
    print(SEP)
    return 0


if __name__ == '__main__':
    sys.exit(main())
