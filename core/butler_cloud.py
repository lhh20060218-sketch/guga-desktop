# -*- coding: utf-8 -*-
"""管家云端大脑客户端 — 桌宠 ⇆ 云端监工服务（合一架构的"主人端"通道）

桌宠合一后的分工:
  - 拆解/调度/验收裁决: 云端大脑（需要 LLM，API Key 只放服务器）
  - 台账/设备/证据墙:   云端存储（同账号跨设备: 台式机派的活, 笔记本同账号可见）
  - 真实执行:           永远在桌宠所在的本机（executor:'local' 派给本机执行方）

用法(CompWindow):
    self._cloud = ButlerCloud(self)
    self._cloud.login_ok.connect(...)        # 登录成功(用户名)
    self._cloud.state_updated.connect(...)   # 台账刷新(任务列表)
    self._cloud.announce.connect(...)        # 需要语音播报的话
    self._cloud.start()                      # 读 ai_config.json 的 cloud 段自动登录

配置(ai_config.json 的 cloud 段, 见 ai_config.example.json):
    "cloud": {
        "base_url": "http://39.107.48.60:3000",
        "username": "666",
        "password": "……",
        "device":   "书房台式机",
        "poll_secs": 6
    }
"""
import io
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request

from PyQt5.QtCore import QObject, QTimer, pyqtSignal

DEFAULT_BASE = 'http://39.107.48.60:3000'
_CFG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'ai_config.json')

# ---------- 意图路由: 哪些话应该走"派单真机执行"而不是普通问答 ----------
# 与云端 server.js 的 LOCAL_APPS 词表对齐(桌宠本地一份, 离线也能判):
# 用户话里出现目标软件 = 要咕嘎指挥那个软件干活, 绝不能让咕嘎自己的 API 代写冒充.
_DEVICE_APPS_RE = re.compile(
    r'豆包|doubao|元宝|智谱|清言|deepseek|deep seek|记事本|notepad|计算器|'
    r'浏览器|chrome|edge|wps|word|excel|ppt|剪映|飞书|钉钉|腾讯会议|workbuddy|'
    r'wrokbuddy|wrorkbuddy|work\s*buddy|画图|修图',
    re.I)
# 询问/比较类保护: 提到软件名但只是问知识, 不该派单
_ASK_ONLY_RE = re.compile(r'哪个好|哪个强|区别|是什么|是什么公司|怎么样|比一比|谁更好|推荐')


def looks_like_device_task(text):
    """对话意图路由: 文本提到目标软件 → 应走派单真机执行(宁可误路由, 不可漏路由:
    误路由会被云端拆解/验收正常处理, 漏路由则变成咕嘎自己代写——那是演剧本)."""
    if not text or len(text) < 4:
        return False
    if _ASK_ONLY_RE.search(text):
        return False
    return bool(_DEVICE_APPS_RE.search(text))

# 子任务状态 → 中文播报词
ST_WORD = {
    'pending': '排队中', 'running': '进行中', 'review': '待验收',
    'done': '已完成', 'failed': '异常', 'paused': '已暂停',
}


def load_cloud_cfg():
    """读 ai_config.json 的 cloud 段; 未配置返回 None(桌宠照常跑, 只是没有云端能力)."""
    try:
        with io.open(_CFG_PATH, encoding='utf-8') as f:
            cfg = json.load(f)
        c = cfg.get('cloud') or {}
        if c.get('base_url') and c.get('username') and c.get('password'):
            c.setdefault('poll_secs', 6)
            c.setdefault('device', '桌宠本机')
            return c
    except Exception:
        pass
    return None


def task_overall(task):
    """把一条任务的子任务状态聚合成一个总状态（与云端语义一致）."""
    subs = task.get('subtasks') or []
    sts = [s.get('status', 'pending') for s in subs]
    if not sts:
        return 'pending'
    if any(s == 'failed' for s in sts):
        return 'failed'
    if all(s == 'done' for s in sts):
        return 'done'
    if any(s == 'review' for s in sts):
        return 'review'
    if any(s == 'running' for s in sts):
        return 'running'
    return 'pending'


def task_progress(task):
    """完成度 0~1（done 子任务占比）."""
    subs = task.get('subtasks') or []
    if not subs:
        return 0.0
    return sum(1 for s in subs if s.get('status') == 'done') / float(len(subs))


class _OnceCall(threading.Thread):
    """一次性后台调用（登录/派单）: 不卡 UI 线程, 结果走回调."""

    def __init__(self, fn, on_ok, on_fail):
        super().__init__(daemon=True)
        self._fn, self._ok, self._fail = fn, on_ok, on_fail

    def run(self):
        try:
            result = self._fn()
            self._ok(result)
        except Exception as e:
            self._fail(str(e) or e.__class__.__name__)


class ButlerCloud(QObject):
    """桌宠的云端大脑通道. 一个实例管: 登录、派单、台账轮询、播报去重."""

    login_ok = pyqtSignal(str)          # 用户名
    login_fail = pyqtSignal(str)        # 错误摘要
    dispatch_ok = pyqtSignal(dict)      # 新任务对象
    dispatch_fail = pyqtSignal(str)
    state_updated = pyqtSignal(list)    # 最新任务列表(最多30条)
    poll_error = pyqtSignal(str)        # 轮询异常(断线等, 面板提示用, 不打断桌宠)
    announce = pyqtSignal(str)          # 需要 TTS 播报的状态变化

    def __init__(self, parent=None):
        super().__init__(parent)
        cfg = load_cloud_cfg()
        self._cfg = cfg
        self.base = (cfg or {}).get('base_url', DEFAULT_BASE).rstrip('/')
        self.token = ''
        self.user = ''
        self._poll = None       # QTimer
        self._last_sig = {}     # task_id -> 子任务状态摘要(播报去重)
        self._net_fail = 0      # 连续失败计数(只报一次, 恢复时报一次)

    # ---------- 状态 ----------

    @property
    def enabled(self):
        return self._cfg is not None

    @property
    def logged_in(self):
        return bool(self.token)

    # ---------- 生命周期 ----------

    def start(self):
        """配置存在才启用: 自动登录 + 启动台账轮询. 未配置时静默跳过."""
        if not self.enabled:
            return False
        self.login(self._cfg['username'], self._cfg['password'],
                   self._cfg.get('device', '桌宠本机'))
        return True

    def stop(self):
        if self._poll is not None:
            self._poll.stop()
            self._poll = None

    # ---------- 底层 HTTP ----------

    def _call(self, path, data=None, timeout=25):
        req = urllib.request.Request(self.base + path,
                                     method='POST' if data is not None else 'GET')
        req.add_header('Content-Type', 'application/json')
        if self.token:
            req.add_header('Authorization', 'Bearer ' + self.token)
        body = json.dumps(data).encode('utf-8') if data is not None else None
        with urllib.request.urlopen(req, body, timeout=timeout) as r:
            return json.loads(r.read().decode('utf-8'))

    # ---------- 登录 ----------

    def login(self, username, password, device='桌宠本机'):
        def job():
            return self._call('/api/login',
                              {'username': username, 'password': password,
                               'device': device[:40]})
        _OnceCall(job, self._on_login, self.login_fail.emit).start()

    def _on_login(self, result):
        self.token = result.get('token', '')
        self.user = result.get('username', '')
        self.login_ok.emit(self.user)
        self._start_poll()

    def _start_poll(self):
        if self._poll is not None:
            return
        secs = int(self._cfg.get('poll_secs', 6))
        self._poll = QTimer(self)
        self._poll.setInterval(max(4, secs) * 1000)
        self._poll.timeout.connect(self.refresh_state)
        self._poll.start()
        self.refresh_state()

    # ---------- 派单 ----------

    def dispatch(self, goal, space='', prefer_local=True):
        """说目标 → 云端拆解派单. prefer_local: 涉及本机软件时优先派给本机执行方."""
        if not self.logged_in:
            self.dispatch_fail.emit('还没连上云端大脑，请先登录')
            return
        payload = {'goal': goal[:500], 'space': space}
        if prefer_local:
            payload['executor'] = 'local'
        _OnceCall(lambda: self._call('/api/tasks', payload),
                  self._on_dispatch, self.dispatch_fail.emit).start()

    def _on_dispatch(self, result):
        task = result.get('task') or {}
        self._remember_sig(task)
        self.dispatch_ok.emit(task)

    # ---------- 台账轮询 ----------

    def refresh_state(self):
        if not self.logged_in:
            return
        _OnceCall(lambda: self._call('/api/state'),
                  self._on_state, self._on_poll_fail).start()

    def _on_poll_fail(self, err):
        self._net_fail += 1
        if self._net_fail == 1:
            self.poll_error.emit(err)

    def _on_state(self, result):
        if self._net_fail:
            self._net_fail = 0
            self.announce.emit('少爷，云端大脑连上了。')
        tasks = result.get('tasks') or []
        self.state_updated.emit(tasks)
        self._diff_announce(tasks)

    # ---------- 状态变化 → 语音播报（去重: 只播新增变化） ----------

    @staticmethod
    def _sig(task):
        return tuple((s.get('id'), s.get('status')) for s in (task.get('subtasks') or []))

    def _remember_sig(self, task):
        self._last_sig[task.get('id')] = self._sig(task)

    def _diff_announce(self, tasks):
        """台账刷新后对比签名, 有变化才开口; 一轮最多播两条, 避免刷屏."""
        lines = []
        for task in tasks:
            tid = task.get('id')
            sig = self._sig(task)
            old = self._last_sig.get(tid)
            if old is None:
                self._remember_sig(task)      # 首次见到的历史任务不开口
                continue
            if sig == old:
                continue
            self._remember_sig(task)
            line = self._describe_change(task, old)
            if line:
                lines.append(line)
            if len(lines) >= 2:
                break
        for line in lines:
            self.announce.emit(line)

    def _describe_change(self, task, old_sig):
        subs = task.get('subtasks') or []
        old_map = {sid: st for sid, st in old_sig}
        # 找"刚变 done"的子任务优先播, 其次是打回/异常
        for s in subs:
            sid, st = s.get('id'), s.get('status')
            if st == 'done' and old_map.get(sid) not in (None, 'done'):
                return ('少爷，「%s」验收通过了。' % s.get('name', '子任务')
                        if task_overall(task) != 'done'
                        else '少爷，「%s」全部完成——%d 个子任务都验收通过。'
                             % (task.get('goal', '任务'), len(subs)))
        for s in subs:
            sid, st = s.get('id'), s.get('status')
            if st in ('failed', 'review') and old_map.get(sid) != st:
                if st == 'failed':
                    return '少爷，「%s」三次交付仍不达标，我如实上报，需要您亲自看一眼。' % s.get('name', '子任务')
                return '少爷，「%s」交付了，我正在按验收标准核对。' % s.get('name', '子任务')
        # 兜底: 总状态变了才播
        before = [old_map.get(s.get('id')) for s in subs]
        after = [s.get('status') for s in subs]
        if sorted(filter(None, before)) != sorted(filter(None, after)):
            return '少爷，「%s」有新进展，%s。' % (
                task.get('goal', '任务')[:24],
                '、'.join(sorted({ST_WORD.get(st, st) for st in after})))
        return ''
