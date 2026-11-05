# -*- coding: utf-8 -*-
"""参赛版桌宠窗口 — 只保留产品本体: 管家 + 六员工召唤 + 对话 + 提醒

与原版 pet_window(开发原理验证, 含战棋/唱歌/多智能体等)完全隔离:
  - 形象: 当前为占位帧(企鹅), 队友素材到位后由 import_video.py 替换
  - 菜单: 召唤/召回 + 添加提醒 + 待办 + 退出, 无任何开发期功能
  - 对话: 点击桌宠打开输入条, 回复走 ButlerHub(员工知识库+人设)

被 comp_main.py 启动. 原版 main.py 不受影响.
"""
import logging
import time

from PyQt5.QtCore import Qt, QPoint, QTimer
from PyQt5.QtGui import QPainter, QColor, QFont
from PyQt5.QtWidgets import QWidget, QMenu, QLineEdit, QApplication

from ui.sprite_animator import SpriteAnimator
from ui.tts_engine import TTSEngine
from core.ai_chat import AIChatEngine
from ui.butler_attach import ButlerRuntime
from core.butler_cloud import (ButlerCloud, looks_like_device_task,
                               task_overall, task_progress)
from core.local_agent import LocalAgent
from ui.task_panel import TaskPanel
from ui.control_badge import ControlBadge

logger = logging.getLogger(__name__)

WIN_W, WIN_H = 320, 430          # 窗体尺寸(容纳 260px 显示宽的立绘)
BUBBLE_SECS = 8                  # 气泡停留秒数


class CompWindow(QWidget):
    """参赛版: 极简桌宠窗体(管家中枢)."""

    def __init__(self):
        super().__init__()
        # --- 无边框/透明/置顶/工具窗(不占任务栏) ---
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                            | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedSize(WIN_W, WIN_H)

        # --- 表现层: 占位立绘(素材到位后整体替换) ---
        self._anim = SpriteAnimator(str(_res_dir()), display_width=260)
        self._anim_offset = QPoint(10, 60)
        self._pet_scale = 1.0

        # --- 大脑/语音 ---
        self._ai = AIChatEngine(self)
        self._ai.reply_ready.connect(self._on_reply)
        self._ai.failed.connect(self._on_fail)
        self._tts = TTSEngine()

        # --- 管家系统(召唤/检索链/提醒/报幕/菜单注入) ---
        self._butler = ButlerRuntime(self)

        # --- 台账面板(先建, 云端信号回调要写状态行) ---
        self._panel = TaskPanel()
        self._panel.hide()

        # --- 屏幕级接管标识: 只在派单/操控/异常时出现, 空闲不占屏 ---
        self._badge = ControlBadge()

        # --- 云端大脑(监工闭环: 拆解/派单/台账/验收; 未配置则静默跳过) ---
        self._cloud = ButlerCloud(self)
        self._cloud.login_ok.connect(self._on_cloud_login)
        self._cloud.login_fail.connect(
            lambda e: (self.show_bubble('少爷，云端大脑连不上：%s' % e[:60]),
                       self._panel.set_status('云端未登录 · 检查 ai_config.json 的 cloud 段'),
                       self._badge.set_state('error', '云端未登录 · ' + e[:60])))
        self._cloud.dispatch_ok.connect(self._on_task_created)
        self._cloud.dispatch_fail.connect(
            lambda e: (self.show_bubble('派单没成：%s' % e[:80]),
                       self._panel.set_status('派单失败 · 详情见台账'),
                       self._badge.set_state('error', '派单失败 · ' + e[:60])))
        self._cloud.poll_error.connect(
            lambda e: (self._panel.set_status('云端断线 · 自动重试中'),
                       self._badge.set_state('error', '云端断线 · 自动重试中')))
        self._cloud.state_updated.connect(self._on_state)
        self._cloud.announce.connect(
            lambda line: (self.show_bubble(line), self._tts.speak(line)))
        self._cloud.start()

        # --- 内嵌本机执行方（合一第二步: 桌宠自己领单干活, 无需独立值守程序） ---
        self._agent = None

        # --- 气泡与重绘 ---
        self._bubble_text = ''
        self._bubble_until = 0.0
        self._repaint = QTimer(self)
        self._repaint.setInterval(33)
        self._repaint.timeout.connect(self.update)
        self._repaint.start()

        # --- 拖动 ---
        self._drag_off = None

        # --- 待机: 管家占位循环(素材到位后自动被新素材覆盖) ---
        QTimer.singleShot(300, self._start_idle)
        self.move_to_default()

    # ==================== 素材/启动 ====================

    def _start_idle(self):
        # 优先播 120 帧新形象待机(idle-motion/doze), 而不是 armor/butler/doze
        # 的 8 帧旧占位 —— 后者 30fps 下 0.27s 一循环, 肉眼看就是静止.
        try:
            if 'idle:doze' in self._anim.clips:
                self._anim.play_clip('idle:doze', loop=True)
                logger.info('comp idle started: 120-frame idle:doze')
                return
        except Exception:
            logger.exception('idle:doze failed, fallback to armor doze')
        try:
            res = self._butler.mm._resolver
            if res and res.load_into(self._anim, 'doze', namespace='idle',
                                     clip_key='idle:comp_butler'):
                self._anim.play_clip('idle:comp_butler', loop=True)
                logger.info('comp idle started: armor doze fallback')
        except Exception:
            logger.exception('idle start failed')

    def move_to_default(self):
        screen = QApplication.primaryScreen()
        if screen:
            g = screen.availableGeometry()
            self.move(g.right() - WIN_W - 40, g.bottom() - WIN_H - 20)

    # ==================== ButlerRuntime 需要的接口 ====================

    def _ensure_pet_menu(self):
        menu = getattr(self, '_comp_menu', None)
        if menu is not None:
            return menu
        menu = QMenu(None)
        self._comp_menu = menu
        menu.addAction('💬 对话(点击形象也可)').triggered.connect(self.open_input)
        menu.addSeparator()
        if self._cloud.enabled:
            menu.addAction('🗣️ 派个任务…').triggered.connect(self.open_dispatch)
            menu.addAction('📋 任务台账').triggered.connect(self._panel.toggle)
        menu.addAction('❌ 退出').triggered.connect(QApplication.instance().quit)
        return menu

    def _say_with_expression(self, text, expression='normal', action=None):
        self.show_bubble(text)

    # ==================== 交互 ====================

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag_off = e.globalPos() - self.frameGeometry().topLeft()
        elif e.button() == Qt.RightButton:
            self._ensure_pet_menu().exec_(e.globalPos())

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.open_input()

    def mouseMoveEvent(self, e):
        if self._drag_off is not None and e.buttons() & Qt.LeftButton:
            self.move(e.globalPos() - self._drag_off)

    def mouseReleaseEvent(self, e):
        self._drag_off = None

    # ==================== 对话 ====================

    def open_input(self):
        if getattr(self, '_input', None) is not None:
            self._input.raise_()
            self._input.activateWindow()
            return
        box = QLineEdit(self)
        box.setPlaceholderText('少爷请吩咐…(Enter 发送, Esc 关闭)')
        box.setStyleSheet("""
            QLineEdit { background: rgba(255,255,255,235); color: #202124;
                        border: 1px solid #b8bcc7; border-radius: 10px;
                        padding: 6px 12px; font-size: 13px;
                        font-family: "Microsoft YaHei UI"; }""")
        box.setFixedSize(WIN_W - 40, 34)
        box.move(20, WIN_H - 44)
        box.returnPressed.connect(lambda: self._send(box))
        box.installEventFilter(self)
        box.show()
        box.raise_()
        box.activateWindow()
        box.setFocus()
        self._input = box
        self.show_bubble('少爷，请讲。')

    def eventFilter(self, obj, event):
        from PyQt5.QtCore import QEvent
        if obj is getattr(self, '_input', None) and event.type() == QEvent.KeyPress:
            if event.key() == Qt.Key_Escape:
                self._close_input()
                return True
        return super().eventFilter(obj, event)

    def _close_input(self):
        box = getattr(self, '_input', None)
        if box is not None:
            box.deleteLater()
            self._input = None

    def _send(self, box):
        text = box.text().strip()
        if not text:
            return
        self._close_input()
        # 意图路由: 话里出现目标软件(豆包/Kimi/记事本…) = 要咕嘎指挥那个软件真机干活,
        # 转派单链路——绝不能让咕嘎自己的 API 代写冒充(那等于演剧本).
        if self._cloud.enabled and looks_like_device_task(text):
            self._dispatch_from_chat(text)
            return
        self.show_bubble('……')
        self._ai.ask(text)

    def _dispatch_from_chat(self, text):
        """对话里的任务请求 → 云端拆解派单(优先本机执行方)."""
        if not self._cloud.logged_in:
            self._panel.set_status('云端未登录 · 本单未派出')
            self.show_bubble('少爷，这单要真机执行，但云端大脑还没连上——'
                             '请检查 ai_config.json 的 cloud 账号段，重启后我再派。')
            try:
                self._tts.speak('少爷，云端大脑没连上，这单派不出去。')
            except Exception:
                pass
            return
        if self._agent is not None and not self._agent.active:
            self.show_bubble('本机执行方还没就绪（配对中或失败）。这单我会照常派出，'
                             '若云端拒绝会告诉你原因。')
        self.show_bubble('少爷，这是要动真机的活——我来拆解派单，过程您在本机亲眼看到。')
        try:
            self._tts.speak('收到，这是真机任务，我来派单并监工。')
        except Exception:
            pass
        self._cloud.dispatch(text)

    def _on_reply(self, content, expression, action):
        self.show_bubble(content)

    def _on_fail(self, error):
        self.show_bubble('( connection: %s )' % error[:60])

    # ==================== 云端监工（合一的管家一面） ====================

    def _on_cloud_login(self, username):
        self._panel.set_status('已连接 · 账号 %s' % username)
        self.show_bubble('少爷，云端大脑连上了（%s）。说个目标，我去派活监工。' % username)
        self._play_task_anim('hello')
        self.refresh_state()
        self._start_local_agent()

    def _start_local_agent(self):
        """登录成功后自动把本机注册为执行方（合一: 桌宠既是主人端又是执行端）."""
        if self._agent is not None:
            return
        try:
            self._agent = LocalAgent(self._cloud, self)
            self._agent.paired.connect(self._on_agent_paired)
            self._agent.pair_fail.connect(
                lambda e: self.show_bubble('本机执行方没配成：%s（不影响派单给其他设备）' % e[:60]))
            self._agent.job_started.connect(self._on_agent_job)
            self._agent.job_finished.connect(self._on_agent_done)
            self._agent.start()
        except Exception:
            logger.exception('local agent start failed')

    def _play_task_anim(self, name):
        """事件动画直触（accept/reject/celebrating/error/hello…），clip 不在则静默。"""
        clip = 'task:' + name
        if clip in self._anim.clips:
            self._anim.play_clip(clip, loop=False)

    def _on_agent_paired(self, device):
        self.show_bubble('本机执行方已就位（%s）。派给本机的活，我自己就能干。' % device)
        try:
            self._tts.speak('少爷，本机执行方就位，派给我的活我自己干。')
        except Exception:
            pass

    def _on_agent_job(self, job):
        self.show_bubble('领到单了：「%s」——开始指挥本机%s干活。'
                         % (job.get('name', '子任务'), job.get('app', '豆包')))
        self._badge.set_state(
            'control',
            '「%s」· %s' % (job.get('name', '子任务'), job.get('app', '豆包')))
        self._anim.set_work_state('working', str(job.get('taskId') or 'main'))
        try:
            self._tts.speak('接到子任务 %s，我开始指挥本机%s。'
                            % (job.get('name', ''), job.get('app', '豆包')))
        except Exception:
            pass

    def _on_agent_done(self, ok, note):
        self.show_bubble(note or ('执行结束' if ok else '执行异常'))
        self._badge.set_state('done' if ok else 'error',
                             (note or '执行结束')[:70])
        # 即时事件动画: 成功庆祝 / 出错挠头, 然后回空闲（不等 TaskAnimationDirector 的 1.2s 起步延迟）
        self._play_task_anim('celebrating' if ok else 'error')
        self._anim.set_work_state('idle')
        if not ok:
            try:
                self._tts.speak('少爷，这一单没干成，原因我已如实上报。')
            except Exception:
                pass

    def open_dispatch(self):
        """菜单"派个任务": 输入目标 → 云端拆解派单 → 台账可见."""
        if not self._cloud.logged_in:
            self.show_bubble('少爷，先在 ai_config.json 里配好 cloud 账号，我才能连云端大脑。')
            return
        from PyQt5.QtWidgets import QInputDialog
        goal, ok = QInputDialog.getText(
            self, '派个任务', '告诉咕嘎目标（如: 把本周实验数据整理成周报）:')
        if not ok or not goal.strip():
            return
        self.show_bubble('少爷，接单了。我拆拆看……')
        self._cloud.dispatch(goal.strip())

    def _on_task_created(self, task):
        subs = task.get('subtasks') or []
        self._panel.set_status('派单中 · %d 个子任务，进度看台账' % len(subs))
        self._badge.set_state('dispatch',
                             '已拆成 %d 个子任务 · 等待执行方领单' % len(subs),
                             '子任务 0/%d' % len(subs))
        names = '、'.join(s.get('name', '') for s in subs[:3])
        self.show_bubble('少爷，拆解完了：%d 个子任务（%s%s）——已派单，进度在台账里盯。'
                         % (len(subs), names, '…' if len(subs) > 3 else ''))
        self._play_task_anim('accept')
        self._anim.set_work_state('waiting', str(task.get('id') or 'main'))
        try:
            self._tts.speak('少爷，任务已拆成 %d 个子任务并派单，我来监工。' % len(subs))
        except Exception:
            pass

    def _on_state(self, tasks):
        """台账刷新: 面板与状态行一起更新, 任何情况下都不留过期文案."""
        self._panel.set_tasks(tasks)
        # 打回检测: 新出现 failed 的子任务 → 播打回动画（差分, 每个子任务只报一次）
        try:
            failed_now = set()
            for t in tasks or []:
                for s in t.get('subtasks') or []:
                    if s.get('status') == 'failed':
                        failed_now.add(str(s.get('id') or s.get('name')))
            seen = getattr(self, '_seen_failed', None)
            if seen is None:
                self._seen_failed = failed_now      # 首刷只建基线, 历史失败不播动画
            else:
                if (failed_now - seen) and self._cloud.logged_in:
                    self._play_task_anim('reject')
                self._seen_failed = failed_now
        except Exception:
            pass
        if tasks and self._badge.isVisible():
            subs = tasks[0].get('subtasks') or []
            if subs:
                done = sum(1 for s in subs if s.get('status') == 'done')
                self._badge.set_progress('子任务 %d/%d' % (done, len(subs)))
        if self._cloud.logged_in:
            self._panel.set_status('已连接 · 账号 %s · %d 条任务'
                                   % (self._cloud.user or '?', len(tasks)))
        else:
            self._panel.set_status('未连接云端大脑 · 检查 cloud 配置')

    def refresh_state(self):
        if self._cloud.logged_in:
            self._cloud.refresh_state()

    # ==================== 气泡/绘制 ====================

    def show_bubble(self, text):
        self._bubble_text = str(text)
        self._bubble_until = time.time() + BUBBLE_SECS

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        self._anim.draw(p, self._anim_offset.x(), self._anim_offset.y())
        # 气泡(管家/员工说话)
        if self._bubble_text and time.time() < self._bubble_until:
            self._draw_bubble(p)
        elif self._bubble_text:
            self._bubble_text = ''

    def _draw_bubble(self, p):
        text = self._bubble_text
        font = QFont('Microsoft YaHei UI', 10)
        p.setFont(font)
        fm = p.fontMetrics()
        max_w = WIN_W - 60
        # 简易换行
        lines, line = [], ''
        for ch in text:
            if fm.horizontalAdvance(line + ch) > max_w or ch == '\n':
                lines.append(line)
                line = '' if ch == '\n' else ch
            else:
                line += ch
        if line:
            lines.append(line)
        lines = lines[:5]
        bw = max(fm.horizontalAdvance(t) for t in lines) + 28
        bh = fm.height() * len(lines) + 20
        bx, by = (WIN_W - bw) // 2, 6
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 242))
        p.drawRoundedRect(bx, by, bw, bh, 12, 12)
        p.setPen(QColor('#202124'))
        ty = by + 10 + fm.ascent()
        for t in lines:
            p.drawText(bx + 14, ty, t)
            ty += fm.height()


def _res_dir():
    from pathlib import Path
    return Path(__file__).resolve().parent.parent / 'resources'
