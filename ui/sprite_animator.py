# -*- coding: utf-8 -*-
"""咕嘎企鹅精灵动画器 — 多表情图 + alpha 过渡 + 企鹅专属动作

表情: normal/happy/sleepy/surprised/sad/playful（5张素材，happy兼任normal）
动作: bounce(开心蹦) / shake(受惊抖) / point(指点江山-战棋军师)
      peek(偷偷看我) / tsundere(傲娇摇头)
"""
import math
import random
import os
import time
from collections import OrderedDict
from ui.avatar_motion import AvatarMotion
from PyQt5.QtCore import Qt, QPointF, QRectF, QTimer
from PyQt5.QtGui import QPixmap, QPainter, QColor, QPen, QPainterPath, QRadialGradient, QLinearGradient


def adaptive_display_width(min_w=140, max_w=205, height_ratio=0.249):
    """按主屏可用高度自适应形象显示宽（对齐 dsh-pet 观感再降一档）.

    dsh-pet 实测: 角色显示高约 244px(@1080p)。这里显示宽占屏约 17.3%
    (1080p 可用 1040 → 180)；新素材画布 458x660 按显示框等比留白，
    角色身高约 207px，比 dsh 再小一档，边缘参差在小画布上被重采样糊平。
    1080p → 180; 2K → 205 封顶; 768 小屏 → 140 兜底.

    2026-11-07 修"同分辨率换缩放就变尺寸": 比例项本身是物理像素，
    但 140/205 的上下限原来夹在逻辑像素上——同屏 100%/125%/150% 会得到
    180/180/210(1080p)、205/249/249(2K) 三种物理大小。改为统一按物理
    像素夹，再用屏幕 DPR 换回逻辑宽，保证同一分辨率下观感不变.
    """
    try:
        from PyQt5.QtGui import QGuiApplication
        scr = QGuiApplication.primaryScreen()
        if scr is None:
            return max_w
        dpr = max(1.0, float(scr.devicePixelRatio() or 1.0))
        h = scr.availableGeometry().height()
        phys_w = round(h * dpr * height_ratio / 1.44)
        phys_w = max(min_w, min(max_w, phys_w))
        return max(1, round(phys_w / dpr))
    except Exception:
        return max_w


class LazyFrameSequence:
    """Sequential frame cache with per-clip policy (M0).

    max_cached 语义:
      None/'auto' -> min(len(paths), DEFAULT_CACHE)
      'full'/0    -> 全量缓存(不淘汰), 适合短动作
      int         -> 有界 LRU, 适合长动作
    loop_frames=N -> 只暴露前 N 帧(循环截断), 适合长动作循环段.
    预缩放: loader 返回的 QPixmap 已按显示尺寸缩放(_pil_to_pixmap),
    缓存中是小图, 256 帧上限内存开销可控.
    """
    DEFAULT_CACHE = 256

    def __init__(self, paths, loader, max_cached=None, loop_frames=None):
        self.paths = list(paths)
        if loop_frames and int(loop_frames) > 0:
            self.paths = self.paths[:int(loop_frames)]
        self.loader = loader
        if max_cached in (None, 'auto'):
            self.max_cached = min(len(self.paths), self.DEFAULT_CACHE)
        elif max_cached in ('full', 0, '0'):
            self.max_cached = max(1, len(self.paths))
        else:
            self.max_cached = max(1, int(max_cached))
        self.cache = OrderedDict()

    def __len__(self): return len(self.paths)

    def clear(self):
        """释放本段已解码帧（切到别的片段时调用，避免十几段同时驻留显存）."""
        self.cache.clear()

    def __getitem__(self, index):
        index = int(index)
        if index < 0: index += len(self.paths)
        if not 0 <= index < len(self.paths): raise IndexError(index)
        if index in self.cache:
            self.cache.move_to_end(index); return self.cache[index]
        try:
            pixmap = self.loader(self.paths[index])
        except Exception:
            # 单帧损坏/文件被占用时返回空 pixmap(drawPixmap 对 null 是 no-op),
            # 不让异常冒泡到 QTimer/paintEvent 槽里把整个进程 abort.
            pixmap = QPixmap()
        self.cache[index] = pixmap
        while len(self.cache) > self.max_cached: self.cache.popitem(last=False)
        return pixmap


def _cache_max(paths, cache_spec):
    """M0: 根据 manifest clip 条目的 cache 字段计算 max_cached 参数.

    2026-11-06 治"卡顿": 旧策略 loop 片段只缓存 48 帧、段长 96~98 帧，
    播到第 49 帧开始每帧都 cache miss —— 实测每帧在绘制回调里现解码 6ms，
    paint 从 0.12ms 涨到 8.4ms。短片段(<=160 帧)直接全量常驻，长片段才 LRU。
    """
    n = len(paths)
    if not cache_spec:
        return 'full' if n <= LazyFrameSequence.DEFAULT_CACHE else 'auto'
    strategy = str(cache_spec.get('strategy', 'auto')).lower()
    if strategy == 'full':
        return 'full'
    if strategy == 'lru':
        if n <= 160:
            return 'full'
        mf = cache_spec.get('max_frames')
        return int(mf) if mf else 'auto'
    return 'full' if n <= LazyFrameSequence.DEFAULT_CACHE else 'auto'


class SpriteAnimator:
    EXPRESSIONS = ["normal", "happy", "sleepy", "surprised", "sad", "playful"]
    DANCE_CLIP = "dance:joy_sway"
    LEGACY_DANCE_CLIP = "dance:eyes_shake"

    FILE_MAP = {
        "normal":    "normal",
        "happy":     "happy",
        "sleepy":    "sleepy",
        "surprised": "surprised",
        "sad":       "sad",
        "playful":   "playful",
    }

    ACTIONS = ("idle_doze", "idle_heart", "look_up_step", "none", "bounce", "shake", "point", "peek", "tsundere", "head_shake", "nod", "tilt", "wave", "sunglasses", "remove_sunglasses", "dance", "stop_dance", "sneak_peek")

    def __init__(self, res_dir: str, display_width: int = 260):
        self._res_dir = res_dir
        self._presence = AvatarMotion()
        from core.task_animation import TaskAnimationDirector
        self._task_motion=TaskAnimationDirector()
        self._being_dragged=False
        self._speaking=False
        self._hand_blend=0.
        self._hand_releasing=False
        self._tap_elapsed = 1.0
        self._tap_amount = .92
        self._dw = display_width
        try:
            from PyQt5.QtGui import QGuiApplication
            _scr = QGuiApplication.primaryScreen()
            self._dpr = max(1.0, float(_scr.devicePixelRatio())) if _scr else 1.0
        except Exception:
            self._dpr = 1.0

        self._sprites = {}
        self._src_size = None
        for expr in self.EXPRESSIONS:
            file_key = self.FILE_MAP.get(expr, expr)
            paths = [
                os.path.join(res_dir, "expressions", f"{file_key}_transparent.png"),
                os.path.join(res_dir, "expressions", f"{file_key}.png"),
            ]
            for path in paths:
                if os.path.exists(path):
                    pm = QPixmap(path)
                    if not pm.isNull():
                        self._sprites[expr] = pm
                        if self._src_size is None:
                            self._src_size = (pm.width(), pm.height())
                        break

        if not self._sprites:
            raise FileNotFoundError(f"No penguin sprite images found in {res_dir}")
        if "normal" not in self._sprites:
            self._sprites["normal"] = self._sprites[list(self._sprites.keys())[0]]
        for expr in self.EXPRESSIONS:
            if expr not in self._sprites:
                self._sprites[expr] = self._sprites["normal"]

        ref_w, ref_h = self._src_size
        self._scale = display_width / ref_w
        ref_pm = self._sprites["normal"]
        ref_w = int(ref_pm.width() * self._scale)
        ref_h = int(ref_pm.height() * self._scale)
        self.width = ref_w
        self.height = ref_h
        self._dw, self._dh = ref_w, ref_h

        self._scaled = {}
        dpr = self._dpr
        # 2026-11-06 修糊: 源图只重采样一次到"物理像素"尺寸(逻辑尺寸×DPR),
        # 再用 setDevicePixelRatio 标记——杜绝旧实现的"源→逻辑→DPR 再拉伸"双重采样.
        # 源小于物理目标时保持源尺寸不放大(交给 GPU 一次采样), 避免放大糊上叠糊.
        for expr, pm in self._sprites.items():
            phys_w, phys_h = max(1, round(ref_w * dpr)), max(1, round(ref_h * dpr))
            # 2026-11-06 二次修: 恒定缩放到物理目标(源小时平滑上采一次, 交给单次插值),
            # 保证逻辑尺寸恒等于 _dw/_dh——源图原样保留会造成画布溢出→头部被裁.
            scaled = pm.scaled(phys_w, phys_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            # 2026-11-07 修"换机器变大/裁脚": scaled 由 pm.scaled() 生成, DPR 仍是 1.
            # 画进已标记 DPR 的画布时会被再放大 dpr 倍并被画布裁掉下半身. 必须先标记.
            scaled.setDevicePixelRatio(dpr)
            s_lw, s_lh = round(scaled.width() / dpr), round(scaled.height() / dpr)
            canvas = QPixmap(phys_w, phys_h)
            canvas.fill(Qt.transparent)
            canvas.setDevicePixelRatio(dpr)
            cp = QPainter(canvas)
            cp.setRenderHint(QPainter.SmoothPixmapTransform, True)
            x = (ref_w - s_lw) // 2
            y = (ref_h - s_lh) // 2
            cp.drawPixmap(x, y, scaled)
            cp.end()
            self._scaled[expr] = canvas

        # ---- 动画状态 ----
        self.frame = 0
        self._time = 0.0
        self.on_update = None

        self.expression = "normal"
        self._context_expression = None
        self._ambient_expression = 'normal'
        self._temporary_expression = None
        self._temporary_until = 0.0
        self._prev_expression = "normal"
        self._transition = 1.0
        self._transition_speed = 0.06

        # 企鹅动画参数
        self.breath_y = 0.0
        self.body_sway_x = 0.0        # 身体微摆
        self.wing_twitch = 0.0        # 翅膀抖动
        self.eye_open = 1.0
        self.body_squash = 1.0
        self.body_squash_target = 1.0
        self.mouth_open = 0.0

        # 动作叠加
        self.anim_rotate = 0.0
        self.anim_offset = QPointF(0, 0)
        self.anim_scale_x = 1.0
        self.anim_scale_y = 1.0
        self.action = "none"
        self._action_timer = 0.0
        self._action_phase = 0.0
        self._peek_side = 1
        self.head_yaw = self.head_nod = self.head_tilt = 0.0
        self.sunglasses = False
        self._sunglasses_until = 0.0
        self._music_stage_active = False
        self._dancing = False
        self.dance_bpm = 110.0

        # 眨眼 / 翅膀抖
        self._blink_countdown = random.uniform(2.5, 6.0)
        self._blink_closing = False
        self._wing_twitch_countdown = random.uniform(3.0, 9.0)
        self._wing_twitch_active = False
        self._wing_twitch_duration = 0.0
        self._wing_twitch_phase = 0.0

        # 动画系统：关键帧轨道（驱动身体位移/挤压/旋转，不替换表情）
        # type=track: frames=[(dy, squash, rot)] 参数帧；type=frames: 真实图片帧（GIF表情包）
        self.clips = {}
        self._clip = None
        self._clip_frame = 0.0
        self._clip_started_at = None
        # 切片段交叉淡入（dsh-pet 双缓冲同款 .18s）：旧画面盖在新画面上淡出
        self._fade_prev = None
        self._fade_at = -1.
        self._fade_matrix = None
        # M0: clip 自然播完(非循环)时回调, 供 ModeManager 监听变身片段结束
        self.on_clip_finished = None
        self._track_dy = 0.0
        self._track_squash = 1.0
        self._track_rot = 0.0
        self._build_tracks()
        self._load_stickers(os.path.join(res_dir, 'stickers'))
        self._load_action_frames(self.LEGACY_DANCE_CLIP,
                                 os.path.join(res_dir, 'actions', 'eyes_shake_dance', 'frames'),
                                 fps=24.0)
        self._load_action_frames(self.DANCE_CLIP,
                                 os.path.join(res_dir, 'actions', 'joy_sway_dance', 'frames'),
                                 fps=25.0)
        self.idle_motion_clips=[]
        # 2026-11-06: 桌宠形象已按用户要求整体更换为新管家,
        # 旧的「用户拒绝替代形象」口径作废; 打开任务片段让逐帧真动作参与状态表现.
        self._reference_clips_enabled=True
        # These two clips are supplied and explicitly requested by the user for
        # natural idle playback. Keep that scope separate from task-video policy.
        self._idle_motion_enabled=True
        self._load_idle_clips()
        self._load_task_clips()   # 原实现只有定义、全项目零调用 -> task: 片段恒为空

        # 常态表情来回切换
        self._idle_expr_countdown = random.uniform(4.0, 9.0)
        self._idle_expr_pick = None
        self._idle_expr_until = 0.0

        # 随机小动作（让企鹅"活"起来）
        self._idle_action_countdown = random.uniform(0.6, 1.4)

        # 2026-11-06 治"卡顿": 实测 Windows 上 33ms 粗定时器实际只到 ~21fps
        # (源素材 24~30fps, 等于每 10 帧丢 3 帧); 16ms + PreciseTimer 实测
        # ~59fps, 帧推进跟得上源帧率. 空闲不再降帧(dsh-pet 同款策略: 压成本而非降帧).
        self._timer = QTimer()
        self._timer.setTimerType(Qt.PreciseTimer)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)
        self._last_tick=time.monotonic()
        self._active_interval_ms=16
        self._idle_interval_ms=16

    @property
    def _src(self):
        return self._scaled.get(self.expression, self._scaled["normal"])

    def start(self):
        self._timer.start()

    def stop(self):
        self._timer.stop()

    def look_at(self, x, y):
        self._presence.look_at(x, y)

    def set_dragging(self, active, speed=0.0):
        # Movement is handled by the window; no shaking/tilt animation on drag.
        self._being_dragged=bool(active)
        if active and (self._clip or '').startswith('task:'):self.stop_clip()
        self._presence.set_dragging(False, 0.)
        if active and (self._clip or '').startswith('idle:'):self.stop_clip()

    def set_work_state(self,state,task_id='main'):
        if state in ('thinking','working','waiting','result','success','error') and (self._clip or '').startswith('idle:'):
            self.stop_clip()
        applied=self._task_motion.update(state,task_id)
        if state in ('idle','cancelled','success','error','result') and not self._task_motion.jobs:
            self._hand_releasing=True
            if state in ('idle','cancelled') and (self._clip or '').startswith('task:'):self.stop_clip()
        return applied

    def set_speaking(self,active):
        self._speaking=bool(active)
        if active:self._hand_releasing=True
        if active and (self._clip or '').split(':',1)[0] in ('task','idle'):self.stop_clip()

    def set_music_stage(self,active):
        """Singing latches the accessory until the real audio state ends."""
        self._music_stage_active=bool(active)
        if active:
            if (self._clip or '').startswith('idle:'):self.stop_clip()
            self.sunglasses=True
            self._sunglasses_until=0.
        else:
            self.sunglasses=False

    def play_idle_motion(self,name):
        clip='idle:'+str(name)
        if name not in {n for n,_ in self.idle_motion_clips} or clip not in self.clips:return False
        self._dancing=False;self.action='none'
        self.play_clip(clip,loop=False)
        return self._clip==clip

    def _load_task_clips(self):
        """A source manifest may only point to reviewed native-rate PNG bundles.
        2026-11-06: states 不再限 GESTURES——除 poll 六态外, accept/reject/urge/pet/hello
        等事件 clip 也在此加载, 由 comp_window 按云端事件直触 play_clip。
        2026-11-06 治卡顿: lazy=True 但当前片段短(<=160帧)全量常驻, 切片段时
        释放其它片段缓存, 保证播放期零解码、内存只占一段。"""
        import json
        from pathlib import Path
        base=Path(self._res_dir)/'actions/task-motion'
        try:
            manifest=json.loads((base/'manifest.json').read_text(encoding='utf-8'))
            loaded={}
            for state,spec in manifest.get('states',{}).items():
                folder=(base/spec['frames']).resolve();fps=float(spec['native_fps'])
                if not folder.is_relative_to(base.resolve()) or not 20<=fps<=60:continue
                name='task:'+state;key=(str(folder),fps)
                if key in loaded:
                    # State aliases share decoded pixels, not mutable playback flags.
                    self.clips[name]=dict(self.clips[loaded[key]])
                else:
                    self._load_action_frames(name,str(folder),fps,lazy=True,cache_spec=spec.get('cache'))
                    if name in self.clips:loaded[key]=name
        except (OSError,ValueError,TypeError,KeyError):return

    def _load_idle_clips(self):
        import json
        from pathlib import Path
        base=Path(self._res_dir)/'actions/idle-motion'
        try:
            manifest=json.loads((base/'manifest.json').read_text(encoding='utf-8'))
            for spec in manifest.get('clips',[]):
                name=str(spec.get('name','')).strip();folder=(base/spec['frames']).resolve();fps=float(spec['native_fps'])
                if not name or not folder.is_relative_to(base.resolve()) or not 20<=fps<=60:continue
                clip='idle:'+name;self._load_action_frames(clip,str(folder),fps,lazy=True,cache_spec=spec.get('cache'))
                if clip in self.clips:self.idle_motion_clips.append((name,max(.01,float(spec.get('weight',1)))))
        except (OSError,ValueError,TypeError,KeyError):return

    def _tick_task_motion(self):
        blocked=(self.expression=='sleepy' or self._context_expression not in (None,'happy') or
                 self.dancing or self._speaking or self.mouth_open>.05 or self._being_dragged or
                 self.action!='none' or self._clip not in (None,'idle','talk'))
        event=self._task_motion.poll(blocked)
        if event:
            clip='task:'+event['state']
            if self._reference_clips_enabled and clip in self.clips:self.play_clip(clip,loop=False)
            else:self.trigger_action({'thinking':'tilt','waiting':'peek'}.get(event['state'],event['gesture']))

    def task_animation_status(self):
        return dict(version='2026-11-02.idle-video.1',active_clip=self._clip,
                    frame=int(self._clip_frame),director=self._task_motion.snapshot(),
                    loaded={name[5:]:dict(frames=len(clip['frames']),fps=clip['fps'],
                                        one_shot=bool(clip.get('one_shot_only')))
                            for name,clip in self.clips.items() if name.startswith('task:')},
                    idle_motion=dict(active=self._clip if (self._clip or '').startswith('idle:') else None,
                        loaded={name:dict(frames=len(self.clips['idle:'+name]['frames']),fps=self.clips['idle:'+name]['fps'],
                                         one_shot=bool(self.clips['idle:'+name].get('one_shot_only')))
                                for name,_ in self.idle_motion_clips if 'idle:'+name in self.clips}))

    def tap(self, amount=.92):
        if (self._clip or '').startswith('idle:'):self.stop_clip()
        self._tap_elapsed = 0.
        self._tap_amount = max(.88, min(.98, amount))

    def set_expression(self, expr: str):
        """An intentional expression persists until the next explicit choice.

        Idle expressions and mood updates must never undo a model/user choice.
        Explicit `normal` releases other held expressions; sleepy requires
        user_interaction() first.
        """
        if expr not in self.EXPRESSIONS:
            return
        if expr not in ('normal','happy') and (self._clip or '').startswith('idle:'):self.stop_clip()
        # Sleep is latched: autonomous replies, gestures and stale callbacks
        # cannot wake the pet. Only an actual user input releases this state.
        if self._context_expression == 'sleepy' and expr != 'sleepy':
            return
        if expr not in ('normal','happy') and (self._clip or '').startswith('task:'):self.stop_clip()
        self._context_expression = None if expr == 'normal' else expr
        if expr == 'normal': self._ambient_expression = 'normal'
        self._temporary_expression = None
        self._temporary_until = 0.0
        self._display_expression(expr)

    def user_interaction(self):
        """Wake on user speech/message/click, never on pointer tracking."""
        if self.expression != 'sleepy':
            return False
        self._context_expression = None
        self.set_expression('happy')
        return True

    def _display_expression(self, expr):
        if expr not in self.EXPRESSIONS or expr == self.expression:
            return
        self._prev_expression = self.expression
        self.expression = expr
        self._transition = 0.0

    def temporary_expression(self, expr, seconds=2.0):
        if expr not in self.EXPRESSIONS or self._context_expression not in (None, 'happy'):
            return False
        self._temporary_expression = expr
        self._temporary_until = self._time + max(.1,float(seconds))
        self._display_expression(expr)
        return True

    def _restore_expression(self):
        self._temporary_expression = None
        self._temporary_until = 0.0
        self._display_expression(self._context_expression or self._ambient_expression)

    def _set_expression_fast(self, expr: str):
        """立即切换表情（不做 blend）——用于说话时的口型闪烁"""
        if expr not in self.EXPRESSIONS or expr == self.expression:
            return
        self.set_expression(expr)
        self._transition = 1.0

    def update_mood(self, mood_emoji: str):
        mapping = {
            '😄': 'happy', '😊': 'happy', '😴': 'sleepy',
            '😢': 'sad', '😕': 'sad',
        }
        self._ambient_expression = mapping.get(mood_emoji, 'normal')
        if self._context_expression is None and self._temporary_expression is None:
            self._display_expression(self._ambient_expression)

    def trigger_bounce(self):
        self.body_squash_target = 0.86

    def set_talking(self, talking: bool):
        self.set_speaking(talking)

    # ==================== 动画关键帧轨道 ====================

    def _build_tracks(self):
        """身体动画轨道（只驱动位移/挤压/旋转，表情由 expression 决定）"""
        # (dy 位移, squash 挤压(1=正常), rot 旋转)
        self.clips['idle'] = {'type': 'track', 'loop': True, 'fps': 6.0,
                              'frames': [(-1, 1.02, 0), (-3, 1.0, 0), (-2, 0.985, 0), (-1, 1.0, 0)]}
        self.clips['talk'] = {'type': 'track', 'loop': True, 'fps': 8.0,
                              # 极轻微脉动（几乎不可见，仅示意"在说话"）
                              'frames': [(0, 1.0, 0), (-1, 1.006, 0), (0, 1.0, 0), (-1, 1.006, 0)]}
        self.clips['jump'] = {'type': 'track', 'loop': False, 'fps': 15.0,
                              'frames': [(0, 1.04, 0), (-8, 0.95, 0), (-14, 0.9, 0),
                                         (-8, 0.95, 0), (0, 1.0, 0), (2, 1.08, 0)]}
        self.clips['wave'] = {'type': 'track', 'loop': False, 'fps': 8.0,
                              'frames': [(0, 1.0, -6), (0, 1.0, 0), (0, 1.0, 6), (0, 1.0, 0)]}

    def _snapshot_frame(self):
        """当前正在显示的画面（片段帧或基础立绘），用于切换时的交叉淡入。"""
        entry = self.clips.get(self._clip) if self._clip else None
        if entry is not None:
            frames = entry.get('frames')
            if frames and (entry.get('type') == 'frames' or (self._clip or '').startswith('task:')):
                try:
                    return frames[min(int(self._clip_frame), len(frames) - 1)]
                except (IndexError, TypeError, ValueError):
                    return None
        try:
            return self._src
        except Exception:
            return None

    def _begin_clip_fade(self):
        snap = self._snapshot_frame()
        if snap is not None and not snap.isNull():
            self._fade_prev = snap
            self._fade_at = time.monotonic()

    def play_clip(self, name, loop=None):
        if name.startswith('task:') and not self._reference_clips_enabled:return
        if name.startswith('idle:') and not self._idle_motion_enabled:return
        if name not in self.clips:
            return
        if loop is not None:
            self.clips[name]['loop'] = bool(loop) and not self.clips[name].get('one_shot_only',False)
        if self._clip != name:
            self._begin_clip_fade()   # 先拍快照（趁旧片段缓存还在），再释放非活跃缓存
        self._release_inactive_caches(name)
        self._clip = name
        self._clip_frame = 0.0
        self._clip_started_at = time.monotonic()

    def _release_inactive_caches(self, active):
        """只让当前片段常驻解码帧：短片段全量缓存约 10MB/段，十几段全驻留会吃 100MB+.

        注意: track 片段的 frames 是普通 list(每帧一个姿态元组), 不能清空,
        否则切回 track 时 n=0 → frames[-1] 抛 IndexError, PyQt 槽内未捕获异常
        会直接 abort 进程(表现为桌宠在动作播完后"突然没了").
        """
        active_frames = (self.clips.get(active) or {}).get('frames')
        for name, clip in self.clips.items():
            if name == active:
                continue
            frames = clip.get('frames')
            if isinstance(frames, LazyFrameSequence) and frames is not active_frames:
                frames.clear()

    def stop_clip(self):
        if self._clip is not None:
            self._begin_clip_fade()
        self._clip = None
        self._clip_frame = 0.0
        self._clip_started_at = None
        self._track_dy = 0.0
        self._track_squash = 1.0
        self._track_rot = 0.0

    @property
    def active_clip(self):
        return self._clip

    def _load_stickers(self, stickers_dir):
        """GIF 表情包 → 剪辑（名称为 sticker:<文件名>）"""
        if not os.path.isdir(stickers_dir):
            return
        try:
            from PIL import Image as PILImage
        except ImportError:
            return
        for f in sorted(os.listdir(stickers_dir)):
            if not f.lower().endswith('.gif'):
                continue
            try:
                im = PILImage.open(os.path.join(stickers_dir, f))
                # 2026-11-07: 未抠底的 GIF（四角不透明/成排整行不透明）一律不加载,
                # 否则切过去就是一块不透明方块底。旧表情包素材均属此类。
                im.seek(0)
                probe = im.convert('RGBA').getchannel('A')
                pw, ph = probe.size
                if max(probe.getpixel((0, 0)), probe.getpixel((pw - 1, 0)),
                       probe.getpixel((0, ph - 1)), probe.getpixel((pw - 1, ph - 1))) >= 200:
                    continue
                box = getattr(PILImage, 'BOX', None) or PILImage.Resampling.BOX
                row_alpha = probe.resize((1, ph), box).getdata()
                if sum(1 for value in row_alpha if value >= 191) >= 8:
                    continue
                frames = []
                idx = 0
                while True:
                    im.seek(idx)
                    frames.append(self._pil_to_pixmap(im.convert('RGBA')))
                    idx += 1
                    try:
                        im.seek(idx)
                    except EOFError:
                        break
                if frames:
                    self.clips[f'sticker:{os.path.splitext(f)[0]}'] = {
                        'type': 'frames', 'frames': frames, 'fps': 12.0, 'loop': True,
                    }
            except Exception:
                continue

    def _load_action_frames(self, name, frames_dir, fps=15.0, lazy=False, cache_spec=None):
        """Load a transparent PNG animation without GIF palette loss.

        cache_spec (M0, 可选, 来自 manifest clip 条目的 "cache" 字段):
          {"strategy": "full"|"lru", "max_frames": int, "loop_frames": int}
          无 cache_spec 时按帧数自动: <=256 全量, >256 LRU(256).
        """
        if not os.path.isdir(frames_dir):
            return
        from core.avatar_review import approved_action
        if not approved_action(frames_dir):
            return
        try:
            from PIL import Image as PILImage
        except ImportError:
            return
        paths=[os.path.join(frames_dir,filename) for filename in sorted(os.listdir(frames_dir))
               if filename.lower().endswith(('.png', '.webp'))]
        def load_path(path):
            with PILImage.open(path) as source:
                return self._pil_to_pixmap(source.convert('RGBA'))
        if lazy:
            frames=LazyFrameSequence(paths,load_path,
                                     max_cached=_cache_max(paths,cache_spec),
                                     loop_frames=(cache_spec or {}).get('loop_frames'))
        else:
            frames=[]
            for path in paths:
                try:frames.append(load_path(path))
                except Exception:continue
        if frames:
            import json
            from pathlib import Path
            review=json.loads((Path(frames_dir).parent/'visual-review.json').read_text(encoding='utf-8'))
            once=review.get('playback')=='once'
            self.clips[name] = {'type': 'frames', 'frames': frames,
                                'fps': float(fps), 'loop': not once,'one_shot_only':once}

    def _pil_to_pixmap(self, pil_img):
        from PyQt5.QtGui import QImage
        data = pil_img.tobytes('raw', 'RGBA')
        qimg = QImage(data, pil_img.width, pil_img.height, QImage.Format_RGBA8888)
        pm = QPixmap.fromImage(qimg)
        # 2026-11-06 修糊: 只重采样一次到物理像素(逻辑×DPR)并标记 DPR,
        # 屏幕上 1:1 物理呈现; 恒定缩放保证逻辑尺寸=_dw/_dh(防画布溢出裁头).
        dpr = self._dpr
        phys_w, phys_h = max(1, round(self._dw * dpr)), max(1, round(self._dh * dpr))
        scale = min(phys_w / max(1, pm.width()), phys_h / max(1, pm.height()))
        pm = pm.scaled(int(pm.width() * scale), int(pm.height() * scale),
                       Qt.KeepAspectRatio, Qt.SmoothTransformation)
        pm.setDevicePixelRatio(dpr)
        return pm

    def play_sticker(self, name):
        self.play_clip(f'sticker:{name}')

    @property
    def sticker_names(self):
        return [n[8:] for n in self.clips if n.startswith('sticker:')]

    @property
    def dancing(self):
        return self._dancing

    @dancing.setter
    def dancing(self, active):
        self._dancing = bool(active)
        if self._dancing and self.DANCE_CLIP in self.clips:
            self.action = 'none'
            if self._clip != self.DANCE_CLIP:
                self.play_clip(self.DANCE_CLIP, loop=True)
        elif not self._dancing and self._clip == self.DANCE_CLIP:
            self.stop_clip()

    # ==================== 动作控制 ====================

    def trigger_action(self, action: str):
        from core.embodiment import ALIASES
        action=ALIASES.get(action,action)
        if action!='none' and (self._clip or '').startswith('idle:'):self.stop_clip()
        if action in ('idle_doze','idle_heart'):
            if self.expression!='sleepy' and not self._speaking and not self._being_dragged:
                self.play_idle_motion(action[5:])
            return
        if action=='look_up_step':
            if not self._reference_clips_enabled:
                self.trigger_action('tilt');return
            if self.expression!='sleepy' and not self._speaking and not self._being_dragged and not self.dancing:
                self.action='none';self.play_clip('task:thinking',loop=False)
            return
        if action in ('sunglasses','remove_sunglasses'):
            self.sunglasses=action=='sunglasses'
            self._sunglasses_until=self._time+8 if self.sunglasses else 0
            return
        if action in ('dance','stop_dance'):
            self.dancing=action=='dance'
            if not self.dancing:self.stop_clip()
            return
        if action in self.ACTIONS and action != "none":
            self.action = action
            self._action_timer = 0.0
            self._action_phase = 0.0
            if action in ('think_chin','scratch_head'):
                self._hand_blend=0.;self._hand_releasing=False
                self.temporary_expression('surprised',3.4)
                # These source expressions have slightly different silhouettes;
                # avoid ghosting the whole body during an articulated gesture.
                self._transition=1.
            if action == "bounce":
                self.body_squash_target = 0.86
                self.play_clip('jump', loop=False)   # 跳跃真动画
            if action == "peek":
                self._peek_side = random.choice([-1, 1])

    def _tick(self):
        """定时器槽的兜底壳.

        2026-11-06: PyQt5 对槽/虚函数里漏出的 Python 异常会直接 abort 进程,
        观感就是桌宠"突然消失"(0xC0000409). 单帧状态坏掉时在此复位回静态形象,
        下一帧继续跑, 而不是把整个进程带走.
        """
        try:
            self._tick_impl()
        except Exception:
            self._clip = None
            self._clip_frame = 0.0
            self._clip_started_at = None
            self._track_dy = 0.0
            self._track_squash = 1.0
            self._track_rot = 0.0
            self.action = 'none'
            if self.on_update:
                try:
                    self.on_update()
                except Exception:
                    pass

    def _tick_impl(self):
        now=time.monotonic();dt=max(.001,min(.12,now-self._last_tick));self._last_tick=now
        self._tap_elapsed += dt
        self.frame += 1
        t = self._time = self._time + dt
        if self._temporary_expression is not None and (
                t >= self._temporary_until or self.mouth_open > .05):
            self._restore_expression()

        # ---- 呼吸（圆滚滚企鹅，起伏小）----
        breath = math.sin(t * 2 * math.pi / 4.0) * 0.75
        self.breath_y = -breath * 1.5

        # ---- 身体微摆 ----
        self.body_sway_x = math.sin(t * 0.7 + 0.4) * 1.1 + math.sin(t * 2.2 + 1.3) * 0.25

        # ---- 翅膀抖动 ----
        self._wing_twitch_countdown -= dt
        if self._wing_twitch_countdown <= 0 and not self._wing_twitch_active:
            self._wing_twitch_active = True
            self._wing_twitch_phase = 0.0
            self._wing_twitch_duration = random.uniform(0.25, 0.5)
            self._wing_twitch_countdown = random.uniform(5.0, 12.0)
        if self._wing_twitch_active:
            self._wing_twitch_phase += dt
            if self._wing_twitch_phase >= self._wing_twitch_duration:
                self._wing_twitch_active = False
                self.wing_twitch = 0.0
            else:
                env = math.sin(self._wing_twitch_phase / self._wing_twitch_duration * math.pi)
                self.wing_twitch = env * abs(math.sin(self._wing_twitch_phase * 26))

        # ---- 表情过渡 ----
        if self._transition < 1.0:
            t_ease = 1 - (1 - self._transition) ** 3
            self._transition = min(1.0, self._transition + (self._transition_speed + t_ease * 0.02)*dt*30)

        # ---- 眨眼（normal/happy）----
        if self.expression in ("normal", "happy") and self._transition > 0.5:
            self._blink_countdown -= dt
            if self._blink_countdown <= 0 and not self._blink_closing:
                self._blink_closing = True
            if self._blink_closing:
                self.eye_open -= 6.0*dt
                if self.eye_open <= 0:
                    self.eye_open = 0
                    self._blink_closing = False
                    self._blink_countdown = -random.uniform(0.05, 0.15)
            else:
                if self._blink_countdown < 0:
                    self.eye_open = min(1.0, self.eye_open + random.uniform(3.6, 6.6)*dt)
                    if self.eye_open >= 1.0:
                        self._blink_countdown = random.uniform(3.0, 8.0)
        else:
            self.eye_open = 1.0

        # ---- 身体挤压回弹 ----
        if self.body_squash < self.body_squash_target:
            self.body_squash = min(self.body_squash_target, self.body_squash + .9*dt)
        elif self.body_squash > self.body_squash_target:
            self.body_squash = max(self.body_squash_target, self.body_squash - .75*dt)
        if self.body_squash == self.body_squash_target and self.body_squash_target < 1.0:
            self.body_squash_target = 1.0

        # ---- 动作动画 ----
        self._tick_task_motion()
        self._tick_action(dt)
        # A stale TTS lip-sync frame must not suppress idle videos forever.
        if not self._speaking and self.mouth_open>.05:
            self._stale_mouth_frames=getattr(self,'_stale_mouth_frames',0)+1
            self._stale_mouth_seconds=getattr(self,'_stale_mouth_seconds',0.)+dt
            if self._stale_mouth_frames>=60 or self._stale_mouth_seconds>=2.0:
                self.mouth_open=0.;self._stale_mouth_frames=0;self._stale_mouth_seconds=0.
                if self._clip=='talk':self.stop_clip()
        else:self._stale_mouth_frames=0;self._stale_mouth_seconds=0.
        presence = self._presence.advance(dt)
        self.head_yaw += presence.head_yaw / 36
        self.head_nod += presence.head_pitch / 24
        self.anim_rotate += presence.roll
        self.head_tilt += presence.head_roll / 24

        # ---- 动画剪辑帧推进 ----
        if self._clip is not None:
            c = self.clips[self._clip]
            if c.get('one_shot_only') and self._clip_started_at is not None:
                self._clip_frame = max(0.,time.monotonic()-self._clip_started_at)*c['fps']
            else:self._clip_frame += dt * c['fps']
            n = len(c['frames'])
            if n <= 0:
                # 资源缺失/被清空时不能让 n-1 = -1 进索引: 直接结束该片段并回到静态形象.
                self._clip = None
                self._clip_frame = 0.0
                self._clip_started_at = None
            elif self._clip_frame >= n:
                if c['loop']:
                    self._clip_frame %= n
                else:
                    finished = self._clip
                    self._clip = None
                    self._clip_frame = 0.0
                    self._clip_started_at = None
                    # 2026-11-06 治"不动": idle 动画链——一条播完歇 0.5~1.2s
                    # 就接下一条(加权随机)。旧值 1.5~4s 的空档里只剩程序性呼吸,
                    # 实测观感就是"卡住不动"; dsh-pet 的 idle 链几乎无缝接续.
                    if finished.startswith('idle:'):
                        self._idle_action_countdown = random.uniform(0.5, 1.2)
                    if self.on_clip_finished:
                        try: self.on_clip_finished(finished)
                        except Exception: pass
            if c.get('type') == 'track' and n > 0:
                idx = min(int(self._clip_frame), n - 1)
                dy, sq, rt = c['frames'][idx]
                self._track_dy, self._track_squash, self._track_rot = dy, sq, rt
        else:
            self._track_dy = 0.0
            self._track_squash = 1.0
            self._track_rot = 0.0

        # 说话 → 表情动作完全不变，只保留极轻微的身体脉动（talk 轨道已调至几乎不可见）
        if self._clip is None:
            if self.mouth_open > 0.05:
                self.play_clip('talk', loop=True)
            elif self.action == 'none':
                self.play_clip('idle', loop=True)

        # ---- 常态表情来回切换（空闲时偶尔换脸再换回来）----
        if (not self._task_motion.active and self.action == "none" and self.mouth_open <= 0.05 and
                self._clip in (None,'idle') and self._context_expression in (None, 'happy')):
            self._idle_expr_countdown -= dt
            if self._idle_expr_countdown <= 0:
                self._idle_expr_countdown = random.uniform(6.0, 14.0)
                self.temporary_expression(random.choice(['playful', 'surprised', 'happy']),
                                          random.uniform(1.0, 2.2))

        # ---- 随机小憩: 旧逻辑 set_expression('sleepy') 会闩死到用户点击为止
        # (sleep is latched)——测试机观感就是"挂机后永远不动". 改为 6~10s
        # 自恢复小憩, 且频率减半. ----
        if (not self._task_motion.active and random.random() < 0.012*dt and self.expression == "normal" and
                self.action == "none" and self._clip in (None,'idle')):
            self.temporary_expression('sleepy', random.uniform(6.0, 10.0))

        # 随机小动作：空闲时偶尔蹦一下/偷看（保持动态）
        if (not self._task_motion.active and self.expression != 'sleepy' and
                self._context_expression in (None,'happy') and self._temporary_expression is None and
                self.action == "none" and self.mouth_open <= 0.05 and self._clip in (None, 'idle')):
            self._idle_action_countdown -= dt
            if self._idle_action_countdown <= 0:
                # 2026-11-06: 空闲链以 idle 动画为主(78%), 且两次动作之间最多歇 2.5s.
                self._idle_action_countdown = random.uniform(1.0, 2.5)
                r = random.random()
                if r < .78 and self.idle_motion_clips:
                    names=[name for name,_ in self.idle_motion_clips];weights=[weight for _,weight in self.idle_motion_clips]
                    self.play_clip('idle:'+random.choices(names,weights=weights,k=1)[0],loop=False)
                elif r < 0.86:
                    self.trigger_action('bounce')
                elif r < 0.92:
                    self.trigger_action('peek')
                elif r < 0.97:
                    self.trigger_action('tsundere')
                elif self.DANCE_CLIP in self.clips:
                    # Occasional one full choreography, then return to normal
                    # instead of leaving an unattended pet dancing forever.
                    self.play_clip(self.DANCE_CLIP, loop=False)

        energetic=bool(self._speaking or self.mouth_open>.05 or self.action!='none' or self.dancing or
            self._task_motion.active or self._temporary_expression is not None or self._being_dragged or
            self._transition<1 or self._clip not in (None,'idle') or self._tap_elapsed<1.0)
        target=self._active_interval_ms if energetic else self._idle_interval_ms
        if self._timer.interval()!=target:self._timer.setInterval(target)
        if self.on_update:
            self.on_update()

    def _tick_action(self,dt=1/30):
        self._action_timer += dt
        self._action_phase += dt
        a = self.action
        self.anim_rotate = 0.0
        self.anim_offset = QPointF(0, 0)
        self.anim_scale_x = 1.0
        self.anim_scale_y = 1.0
        self._point_active = 0.0
        self.head_yaw = self.head_nod = self.head_tilt = 0.0
        if self._sunglasses_until and self._time>=self._sunglasses_until:
            self.sunglasses=False;self._sunglasses_until=0
        if self._music_stage_active:
            self.sunglasses=True;self._sunglasses_until=0.

        if self.dancing and a=='none' and self._clip != self.DANCE_CLIP:
            beat=self._time*self.dance_bpm/60*math.pi*2
            # Temporary original-art sway, not advertised as full choreography.
            self.anim_rotate=2.5*math.sin(beat/2)
            self.anim_offset=QPointF(self._dw*.008*math.sin(beat/2),0)
            return

        if a in ('spin','sneak_peek'):
            duration=1.8 if a=='spin' else 2.6
            phase=min(1,self._action_timer/duration)
            if phase>=1:self.action='none';return
            envelope=math.sin(math.pi*phase)
            if a=='spin':
                angle=phase*math.pi*2
                self.anim_scale_x=math.copysign(max(.14,abs(math.cos(angle))),math.cos(angle))
                self.anim_offset=QPointF(math.sin(angle)*self._dw*.035,-envelope*self._dh*.025)
                self.head_yaw=.35*math.sin(angle)
            else:
                self.anim_offset=QPointF(self._dw*.09*envelope,self._dh*.035*envelope)
                self.head_yaw=.8*envelope;self.head_tilt=-.35*envelope
            return

        if a == "none":
            return

        if a in ('think_chin','scratch_head'):
            blocked=(self._speaking or self._being_dragged or self.expression=='sleepy' or self.dancing)
            target=0. if self._hand_releasing or blocked or self._action_timer>2.6 else 1.
            self._hand_blend+=(target-self._hand_blend)*(1-math.exp(-9*dt))
            self.head_tilt=.14*self._hand_blend
            if target==0 and self._hand_blend<.008:
                self.action='none';self._hand_blend=0.
                if self._temporary_expression:
                    self._restore_expression();self._transition=1.
            return

        if a in ('head_shake','nod','tilt','wave'):
            duration=1.35
            phase=min(1,self._action_timer/duration)
            if phase>=1:
                self.action='none';return
            envelope=math.sin(math.pi*phase)**.7
            if a=='head_shake':self.head_yaw=math.sin(phase*math.pi*5)*envelope
            elif a=='nod':self.head_nod=math.sin(phase*math.pi*4)*envelope
            elif a=='tilt':self.head_tilt=envelope
            elif a=='wave':
                self.anim_rotate=3*math.sin(phase*math.pi*6)*envelope
                self.anim_offset=QPointF(0,-2*envelope)
            return

        if a == "bounce":
            if self._action_timer > 0.45:
                self.action = "none"
                return
            pr = math.sin(self._action_phase * math.pi / 0.45)
            self.anim_offset = QPointF(0, -9 * pr)
            return

        if a == "shake":
            if self._action_timer > 0.5:
                self.action = "none"
                return
            amp = 5 * (1 - self._action_timer / 0.5)
            self.anim_offset = QPointF(amp * math.sin(self._action_phase * math.pi * 5), 0)
            self.anim_rotate = 2 * math.sin(self._action_phase * math.pi * 5)
            return

        if a == "tsundere":  # 傲娇摇头：慢摆 + 昂头
            dur = 1.4
            if self._action_timer > dur:
                self.action = "none"
                return
            amp = 4.5 * math.sin(self._action_phase / dur * math.pi)
            self.anim_rotate = -2.5 + amp * math.sin(self._action_phase * math.pi * 2.2)
            self.anim_offset = QPointF(0, -1.5)
            return

        if a == "point":  # 指点江山：前倾 + 指点手臂
            dur = 1.6
            if self._action_timer > dur:
                self.action = "none"
                return
            env = math.sin(self._action_timer / dur * math.pi)
            self.anim_rotate = 5 * env
            self.anim_offset = QPointF(0, -2 * env)
            self._point_active = env
            return

        if a == "peek":  # 偷偷看我：轻轻侧移探头偷看（不歪斜不压扁）
            dur = 1.1
            if self._action_timer > dur:
                self.action = "none"
                return
            side = self._peek_side
            if self._action_timer < 0.3:
                k = self._action_timer / 0.3
            elif self._action_timer > dur - 0.3:
                k = (dur - self._action_timer) / 0.3
            else:
                k = 1.0
            # 只做轻微横移 + 2.5 度内小倾（像探头偷看），保持正常比例
            self.anim_scale_x = 1.0
            self.anim_scale_y = 1.0
            self.anim_offset = QPointF(side * self._dw * 0.12 * k, -self._dh * 0.03 * k)
            self.anim_rotate = side * 2.5 * k
            return

        self.action = "none"

    @property
    def point_active(self):
        return getattr(self, "_point_active", 0.0)

    # ==================== 绘制 ====================

    def _draw_clip_fade(self, p, x, y):
        """交叉淡入：旧画面以递减透明度盖在新画面上（180ms 内淡出）。"""
        if self._fade_prev is None:
            return
        age = time.monotonic() - self._fade_at
        if age >= .18:
            self._fade_prev = None
            return
        pm = self._fade_prev
        if pm.isNull():
            self._fade_prev = None
            return
        lw, lh = self._logical_size(pm)
        p.save()
        if self._fade_matrix is not None:
            p.setWorldTransform(self._fade_matrix)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        p.setOpacity(1 - age / .18)
        p.drawPixmap(int(x + (self._dw - lw) / 2), int(y + self._dh - lh), pm)
        p.restore()

    def draw(self, p: QPainter, x: int, y: int):
        p.save()
        self._fade_matrix = p.worldTransform()
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        p.setRenderHint(QPainter.Antialiasing, True)

        self._draw_shadow(p, x, y)

        # Finished source choreography owns its motion. Never add the procedural
        # head/body deformation that made the previous assembled dance strange.
        if (self._clip or '').startswith('task:'):
            frames=(self.clips.get(self._clip) or {}).get('frames') or []
            if len(frames) > 0:
                pm=frames[min(int(self._clip_frame),len(frames)-1)]
                lw,lh=self._logical_size(pm)
                p.drawPixmap(int(x+(self._dw-lw)/2),int(y+self._dh-lh),pm)
                self._draw_clip_fade(p, x, y)
                if self.sunglasses:self._draw_sunglasses(p,x,y)
                p.restore();return
            self._clip = None

        cx = x + self._dw / 2
        cy = y + self._dh / 2
        sx = 2 - self.body_squash
        sy = self.body_squash
        if self._tap_elapsed < .22:
            from ui.pet_physics import squash_scale
            touch = squash_scale(self._tap_elapsed/.22, self._tap_amount)
            sx *= 1+(1-touch)*.5
            sy *= touch
        breath_scale = 1.0 + math.sin(self._time * 2 * math.pi / 4.0) * 0.009

        # 说话时轻微点头（增加真实感）
        talk_bob = self.mouth_open * 1.6

        p.translate(cx + self.anim_offset.x(), cy + self.breath_y + self.anim_offset.y()
                    + talk_bob + self._track_dy)
        p.rotate(self.body_sway_x * 0.25 + self.anim_rotate + self._track_rot)
        sq = self._track_squash
        p.scale(breath_scale * sx * self.anim_scale_x * (2 - sq),
                breath_scale * sy * self.anim_scale_y * sq)
        p.translate(-cx, -cy)

        # GIF 表情包（真实图片帧）优先绘制；轨道动画不替换表情
        _clip_entry = self.clips.get(self._clip) if self._clip is not None else None
        if _clip_entry is not None and _clip_entry.get('type') == 'frames':
            frames = _clip_entry.get('frames')
            if frames:
                idx = min(int(self._clip_frame), len(frames) - 1)
                pm = frames[idx]
                lw, lh = self._logical_size(pm)
                p.drawPixmap(int(x + (self._dw - lw) / 2),
                             int(y + self._dh - lh), pm)
                self._draw_clip_fade(p, x, y)
                if self.sunglasses:
                    self._draw_sunglasses(p, x, y)
                p.restore()
                return

        if self._transition < 1.0:
            old_pm = self._scaled.get(self._prev_expression, self._scaled["normal"])
            new_pm = self._scaled.get(self.expression, self._scaled["normal"])
            p.setOpacity(1.0 - self._transition)
            self._draw_sprite(p,x,y,old_pm)
            p.setOpacity(self._transition)
            self._draw_sprite(p,x,y,new_pm)
            p.setOpacity(1.0)
        else:
            self._draw_sprite(p,x,y,self._src)

        if self.sunglasses:self._draw_sunglasses(p,x,y)

        # 说话动嘴：原画自带嘴部，不再叠画（避免黑线），只保留轻微点头真实感

        # 指点江山手臂
        if self.action == "point" and self.point_active > 0.05:
            self._draw_pointing_arm(p, x, y)

        self._draw_clip_fade(p, x, y)
        p.restore()

    def _draw_sunglasses(self,p,x,y):
        """Vector accessory anchored to the existing character's eyes."""
        w,h=self._dw,self._dh
        p.save()
        p.translate(x+self.head_yaw*w*.038,y+self.head_nod*h*.017)
        p.setPen(QPen(QColor('#171d29'),max(2,w*.014)))
        p.setBrush(QColor('#111824'))
        for left in (.268,.518):
            p.drawRoundedRect(QRectF(w*left,h*.318,w*.215,h*.085),w*.026,w*.026)
        p.drawLine(QPointF(w*.48,h*.339),QPointF(w*.522,h*.339))
        p.drawLine(QPointF(w*.27,h*.328),QPointF(w*.225,h*.309))
        p.drawLine(QPointF(w*.73,h*.328),QPointF(w*.775,h*.309))
        p.setPen(QPen(QColor(152,216,245,200),max(1,w*.008)))
        for left in (.305,.555):
            p.drawLine(QPointF(w*left,h*.338),QPointF(w*(left+.04),h*.373))
        p.restore()

    def _logical_size(self, pm):
        """DPR 感知的逻辑尺寸（DPR 标记图的 width() 是物理像素）"""
        d = pm.devicePixelRatio() or 1.0
        return max(1, round(pm.width() / d)), max(1, round(pm.height() / d))

    def _draw_sprite(self,p,x,y,pm):
        # 2026-11-07 录屏兜底: 基础立绘若大于显示框(旧构建用原图/DPR 回归), 会画成
        # 被矩形裁掉头胸的"大特写". 这里宁可等比缩回框内, 也不让形象越界.
        lw, lh = self._logical_size(pm)
        if lw > self._dw or lh > self._dh:
            ratio = min(self._dw / lw, self._dh / lh)
            tw, th = max(1, round(lw * ratio)), max(1, round(lh * ratio))
            p.save()
            p.setRenderHint(QPainter.SmoothPixmapTransform, True)
            p.drawPixmap(QRectF(x + (self._dw - tw) / 2, y + self._dh - th, tw, th),
                         pm, QRectF(0, 0, pm.width(), pm.height()))
            p.restore()
            return
        if self.action in ('think_chin','scratch_head') and self._hand_blend>.008:
            # Keep the source face/body intact; replace only the right flipper.
            # This is a native articulated limb, not generated/interpolated art.
            p.save()
            w,h=self._logical_size(pm)
            area=QPainterPath();area.addRect(QRectF(x,y,w,h))
            cut=QPainterPath();cut.moveTo(x+w*.805,y+h*.576)
            cut.cubicTo(x+w*1.18,y+h*.585,x+w*1.15,y+h*.85,x+w*.965,y+h*.85)
            cut.cubicTo(x+w*.90,y+h*.81,x+w*.845,y+h*.737,x+w*.805,y+h*.655)
            cut.closeSubpath();p.setClipPath(area.subtracted(cut),Qt.IntersectClip)
            p.drawPixmap(x,y,pm);p.restore()
            self._draw_thinking_flipper(p,x,y,w,h)
            return
        if max(abs(self.head_yaw),abs(self.head_nod),abs(self.head_tilt))<.001:
            p.drawPixmap(x,y,pm);return
        # Continuous mesh warp: head moves, deformation fades through the neck,
        # and the lower body remains anchored. Uses the existing transparent art.
        width,height=self._logical_size(pm)
        _pd = pm.devicePixelRatio() or 1.0  # 源矩形按设备像素取, 目标矩形按逻辑坐标
        for row in range(0,height,2):
            ratio=row/height
            weight=1.0 if ratio<.39 else max(0,min(1,(.66-ratio)/.27))
            weight=weight*weight*(3-2*weight)
            if weight==0:
                p.drawPixmap(QRectF(x,y+row,width,height-row),pm,
                             QRectF(0,row*_pd,pm.width(),(height-row)*_pd))
                break
            dx=self.head_yaw*width*.038*weight+self.head_tilt*(height*.34-row)*.10*weight
            dy=self.head_nod*height*.017*weight
            scale=1-.055*abs(self.head_yaw)*weight
            target=QRectF(x+dx+width*(1-scale)/2,y+row+dy,width*scale,min(3,height-row))
            p.drawPixmap(target,pm,QRectF(0,row*_pd,pm.width(),min(3,height-row)*_pd))

    def _draw_thinking_flipper(self,p,x,y,w,h):
        blend=self._hand_blend
        # Smooth raising/settling; small repetitive scratch only after arrival.
        rest=(.945,.745)
        touch=(.675,.515) if self.action=='think_chin' else (.855,.287)
        motion=math.sin(self._action_timer*17)*.009*blend**4 if self.action=='scratch_head' else 0.
        tx=x+w*(rest[0]+(touch[0]-rest[0])*blend)
        ty=y+h*(rest[1]+(touch[1]-rest[1])*blend+motion)
        sx,sy=x+w*.80,y+h*.616
        limb=QPainterPath(QPointF(sx,sy))
        limb.cubicTo(x+w*(.90-.035*blend),y+h*(.65-.095*blend),
                     tx+w*.06*blend,ty+h*.05,tx,ty)
        gradient=QLinearGradient(sx-w*.05,sy,tx+w*.07,ty)
        gradient.setColorAt(0,QColor('#141b20'));gradient.setColorAt(.5,QColor('#343e45'))
        gradient.setColorAt(1,QColor('#20282e'))
        p.save();p.setPen(QPen(gradient,w*.105,Qt.SolidLine,Qt.RoundCap,Qt.RoundJoin))
        p.setBrush(Qt.NoBrush);p.drawPath(limb);p.restore()

    def _draw_shadow(self, p: QPainter, ox: int, oy: int):
        dw, dh = self._dw, self._dh
        shadow_w = dw * 0.5
        shadow_h = 11
        shadow_x = ox + (dw - shadow_w) / 2
        shadow_y = oy + dh - 8
        grad = QRadialGradient(shadow_x + shadow_w / 2, shadow_y, shadow_w / 2)
        grad.setColorAt(0, QColor(0, 0, 0, 40))
        grad.setColorAt(0.6, QColor(0, 0, 0, 16))
        grad.setColorAt(1, QColor(0, 0, 0, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(grad)
        p.drawEllipse(QRectF(shadow_x, shadow_y - shadow_h / 2, shadow_w, shadow_h))

    def _draw_mouth(self, p: QPainter, ox: int, oy: int):
        """说话小嘴（脸部位置动嘴弧线）"""
        dw, dh = self._dw, self._dh
        mx = ox + dw * 0.50
        my = oy + dh * 0.66
        open_ = 1.0 + self.mouth_open * 3
        pen = QPen(QColor(40, 30, 30), 2.0)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        path = QPainterPath()
        path.moveTo(mx - 6, my)
        path.quadTo(mx, my + open_, mx + 6, my)
        p.drawPath(path)

    def _draw_pointing_arm(self, p: QPainter, ox: int, oy: int):
        """指点江山：右侧伸出的指点手臂（黄手臂+小拳头+指向箭头）"""
        dw, dh = self._dw, self._dh
        env = self.point_active
        arm_x = ox + dw * 0.86
        arm_y = oy + dh * 0.42 + math.sin(self._action_phase * math.pi * 3) * 2.5 * env

        pen = QPen(QColor(245, 180, 60), 7)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        path = QPainterPath()
        path.moveTo(arm_x - 26, arm_y + 20)
        path.quadTo(arm_x - 8, arm_y + 6, arm_x, arm_y)
        p.drawPath(path)

        p.setPen(Qt.NoPen)
        p.setBrush(QColor(245, 190, 70))
        p.drawEllipse(QPointF(arm_x, arm_y), 10, 10)

        arrow = QPainterPath()
        arrow.moveTo(arm_x + 18, arm_y - 8)
        arrow.lineTo(arm_x + 18, arm_y + 8)
        arrow.lineTo(arm_x + 30, arm_y)
        arrow.closeSubpath()
        p.setBrush(QColor(255, 120, 60))
        p.drawPath(arrow)

    def _draw_blink_eyes(self, p: QPainter, ox: int, oy: int):
        dw, dh = self._dw, self._dh
        for fx in (0.40, 0.60):
            cx = ox + dw * fx
            cy = oy + dh * 0.48
            eye_w = dw * 0.07
            pen = QPen(QColor(20, 20, 25), 2.0)
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            path = QPainterPath()
            path.moveTo(cx - eye_w / 2, cy)
            path.quadTo(cx, cy + 2.2, cx + eye_w / 2, cy)
            p.drawPath(path)
