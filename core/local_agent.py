# -*- coding: utf-8 -*-
"""桌宠内嵌本机执行方 — 合一架构的最后一块

合一前: 云端派单 → 独立值守程序 GUGA-Agent.exe 领单 → 指挥本机 AI 软件
合一后: 云端派单 → 桌宠进程内的 LocalAgent 直接领单 → 同一套执行器干活
        （桌宠既是主人端, 又是执行端; 独立值守程序不再是必需品）

自动配对原理（用户全程无感）:
  桌宠已持有用户 token(ButlerCloud 登录来的) → 调 /api/pair/create 生成 6 位配对码
  → 立刻用该码走 /api/agent/pair 换取执行方 token → 桌宠以执行方身份心跳领单
  （等价于网页生成配对码 + 值守程序手动输入, 只是把两步缩进同一进程）

执行逻辑零复制: 直接复用 agent/guga_agent.py 的 run_job（其内部 import
guga_executor 的视觉定位/窗口管理/取证全套能力）, 本模块只做三件事:
  ① 把 BASE 指到云端大脑  ② 自动配对拿执行方 token  ③ 心跳领单 + 线程派活

安全边界不变: FAILSAFE（鼠标甩左上角急停）、剪贴板还原、新对话隔离、
执行全程截图取证回传证据墙。
"""
import os
import sys
import threading

from PyQt5.QtCore import QObject, QTimer, pyqtSignal

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
AGENT_DIR = os.path.join(REPO, 'agent')


class LocalAgent(QObject):
    """桌宠内置执行方. 用法:
        agent = LocalAgent(cloud, self)   # cloud: core.butler_cloud.ButlerCloud(已登录)
        agent.paired.connect(...)         # 配对成功(设备名)
        agent.job_started.connect(...)    # 领到单(子任务名/目标软件)
        agent.job_finished.connect(...)   # 执行结束(ok, 摘要)
        agent.start()                     # 自动配对并开始值守
    """

    paired = pyqtSignal(str)
    pair_fail = pyqtSignal(str)
    job_started = pyqtSignal(dict)        # {name, app, attempt, goal}
    job_finished = pyqtSignal(bool, str)  # (ok, 摘要)
    announce = pyqtSignal(str)

    def __init__(self, cloud, parent=None):
        super().__init__(parent)
        self._cloud = cloud
        self._token = ''
        self._device = ''
        self._busy = False
        self._timer = None
        self._ga = None        # guga_agent 模块（首次 start 时注入 path 再 import）
        self._import_err = ''

    # ---------- 状态 ----------

    @property
    def active(self):
        return bool(self._token)

    @property
    def busy(self):
        return self._busy

    # ---------- 启动: 注入路径 + 自动配对 ----------

    def start(self):
        if self._token or self._busy:
            return
        threading.Thread(target=self._bootstrap, daemon=True).start()

    def _import_agent(self):
        """把 agent/ 目录加进 path, 复用现成执行器（一次性）."""
        if self._ga is not None:
            return True
        try:
            if AGENT_DIR not in sys.path:
                sys.path.insert(0, AGENT_DIR)
            import guga_agent as ga
            self._ga = ga
            self._ga.BASE = self._cloud.base    # 执行器模块级 API 地址 → 云端大脑
            return True
        except Exception as e:
            self._import_err = str(e)
            return False

    def _bootstrap(self):
        if not self._import_agent():
            self.pair_fail.emit('执行器缺失: %s' % self._import_err[:80])
            return
        try:
            # ① 用户身份生成配对码（cloud._call 自带 Bearer 用户 token）
            r = self._cloud._call('/api/pair/create', {})
            code = str(r.get('code', ''))
            if not code.isdigit():
                self.pair_fail.emit('配对码生成失败')
                return
            # ② 立刻用配对码换执行方 token（guga_agent.pair 内部会跑本机自检并上传）
            token = self._ga.pair(code)
            self._token = token
            self._device = os.environ.get('COMPUTERNAME', 'PC')
            self.paired.emit(self._device)
            # ③ 启动心跳领单（QTimer 在主线程, 回调里起线程, 绝不卡 UI）
            QTimer.singleShot(0, self._start_beat)
        except Exception as e:
            self.pair_fail.emit(str(e)[:120])

    # ---------- 心跳领单 ----------

    def _start_beat(self):
        if self._timer is not None:
            return
        self._timer = QTimer(self)
        self._timer.setInterval(4000)          # 与独立值守程序同拍
        self._timer.timeout.connect(self._beat)
        self._timer.start()
        self._beat()

    def _beat(self):
        if not self._token or self._ga is None:
            return
        if self._busy:
            threading.Thread(target=self._beat_keepalive, daemon=True).start()
            return
        threading.Thread(target=self._beat_poll, daemon=True).start()

    def _beat_keepalive(self):
        """干活期间的保活心跳: 只报平安不领新单（防误判离线, 也防一机双单）."""
        try:
            self._ga.api('/api/agent/beat',
                         {'path': AGENT_DIR, 'busy': True}, self._token, timeout=15)
        except Exception:
            pass

    def _beat_poll(self):
        try:
            b = self._ga.api('/api/agent/beat',
                             {'path': AGENT_DIR}, self._token, timeout=20)
            job = b.get('job')
        except Exception:
            return                              # 心跳暂时不通: 下一拍再试, 不打扰桌宠
        if not job or self._busy:
            return
        self._busy = True
        self.job_started.emit({'name': job.get('name', ''),
                               'app': job.get('app', '豆包'),
                               'attempt': job.get('attempt', 1),
                               'goal': job.get('goal', '')})
        threading.Thread(target=self._run_job, args=(job,), daemon=True).start()

    # ---------- 执行（复用 guga_agent.run_job 全套） ----------

    def _run_job(self, job):
        ok, note = False, ''
        try:
            # run_job 内部: 指挥本机 AI 软件 → 每轮请示大脑 → 回传 → 网页验收
            self._ga.run_job(job, self._token)
            ok, note = True, '子任务「%s」执行完毕，云端验收中' % job.get('name', '')
        except Exception as e:
            note = '执行异常: %s' % str(e)[:120]
            try:
                self._ga.api('/api/agent/result',
                             {'taskId': job['taskId'], 'stId': job['stId'],
                              'ok': False, 'note': note[:200]}, self._token)
            except Exception:
                pass
        finally:
            self._busy = False
            self.job_finished.emit(ok, note)

    # ---------- 停止 ----------

    def stop(self):
        if self._timer is not None:
            self._timer.stop()
            self._timer = None
        self._token = ''
