# -*- coding: utf-8 -*-
"""启动自检闸门 — 桌宠启动的第一步（在配置向导之前）

顺序: 双击 exe → 本闸门（查旧进程/查依赖/查环境）→ 配置向导 → 桌宠

三项检查（小白口径，每项给"要不要管"的结论）:
  ① 旧进程: 找残留的 GUGA-Agent 值守程序 / 其他桌宠实例——
     旧值守程序会和新桌宠的内嵌执行方抢单/顶号，必须清掉
  ② 依赖体检: 内嵌执行方四件套(pyautogui/pyperclip/pygetwindow/PIL)
     缺一个, 真机执行就废——提前暴露, 不等派单时才失败
  ③ 环境: 屏幕缩放非 100% 会影响点击精度, 提前提醒

结果处理: 旧进程默认勾选"结束它们"（用户可取消勾选保留）;
依赖缺失给出补法; 全绿直接点"继续"进应用, 停留约 2 秒。
"""
import os
import sys

from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                             QCheckBox, QPushButton, QProgressBar, QApplication,
                             QGroupBox, QGridLayout)

SELF_PID = os.getpid()


def _find_old_processes():
    """找旧执行程序/旧桌宠实例（排除自身）. 返回 [(pid, 名称, 来源描述)]."""
    found = []
    try:
        import psutil
    except Exception:
        return found, False
    for p in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if p.info['pid'] == SELF_PID:
                continue
            name = (p.info['name'] or '').lower()
            cmd = ' '.join(p.info['cmdline'] or []).lower()
            hit = None
            if 'guga-agent' in name:
                hit = '旧版值守程序（新桌宠自带执行方，它会抢单/顶号）'
            elif 'guga-desktop' in name:
                hit = '另一个桌宠实例'
            elif 'guga_agent.py' in cmd and ('python' in name or 'pythonw' in name):
                hit = '脚本方式运行的旧值守程序'
            if hit:
                found.append((p.info['pid'], p.info['name'], hit, p))
        except Exception:
            continue
    return found, True


def _check_deps():
    """内嵌执行方依赖. 返回 [(模块, OK?, 用途)]."""
    out = []
    for mod, use in [('PyQt5', '界面'), ('PIL', '截图取证'),
                     ('pyautogui', '真实鼠标键盘操作'),
                     ('pyperclip', '剪贴板写入/还原'),
                     ('pygetwindow', '找到并置前目标软件窗口')]:
        try:
            __import__(mod)
            out.append((mod, True, use))
        except Exception:
            out.append((mod, False, use))
    return out


class _CheckThread(QThread):
    """逐项跑检查, 每完成一项发一个信号, UI 实时亮灯."""
    item = pyqtSignal(str, bool, str)      # 名称, ok, 详情
    finished_all = pyqtSignal(list, list)  # (旧进程列表, 缺失依赖列表)

    def run(self):
        self.item.emit('旧进程扫描', True, '扫描中…')
        procs, psutil_ok = _find_old_processes()
        if not psutil_ok:
            self.item.emit('旧进程扫描', True, 'psutil 未装，跳过（不影响使用）')
        elif procs:
            names = '；'.join('#%d %s' % (pid, desc) for pid, _n, desc, _p in procs)
            self.item.emit('旧进程扫描', False, '发现 %d 个需清理：%s' % (len(procs), names))
        else:
            self.item.emit('旧进程扫描', True, '干净，无旧值守程序/重复实例')

        self.item.emit('依赖体检', True, '检查中…')
        deps = _check_deps()
        missing = [m for m, ok, _u in deps if not ok]
        if missing:
            self.item.emit('依赖体检', False,
                           '缺 %s —— 真机执行将不可用（对话/台账不受影响）' % '、'.join(missing))
        else:
            self.item.emit('依赖体检', True, '齐全，真机执行链路就绪')

        self.item.emit('环境检查', True, '检查中…')
        try:
            scr = QApplication.primaryScreen()
            dpi = int(scr.logicalDotsPerInch())
            if dpi != 96:
                self.item.emit('环境检查', False,
                               '屏幕缩放 %d%%（非 100%），点击定位精度会受影响，'
                               '演示时建议设回 100%%' % round(dpi / 96 * 100))
            else:
                self.item.emit('环境检查', True, '屏幕缩放 100%，定位精度最佳')
        except Exception:
            self.item.emit('环境检查', True, '无法读取（不影响使用）')

        self.finished_all.emit(procs, missing)


class StartupGate(QDialog):
    """自检窗口: 三项灯逐个亮, 底部按钮决定继续与否."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle('咕嘎 · 启动自检')
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setFixedSize(540, 400)
        self._procs = []
        self._missing = []
        self._done = False

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 12)
        title = QLabel('启动自检：先查旧进程、缺依赖、环境，再进应用')
        title.setStyleSheet('font-size:14px; font-weight:bold; color:#1a1c20;')
        root.addWidget(title)

        box = QGroupBox('检查项')
        grid = QGridLayout(box)
        self._rows = {}
        for i, name in enumerate(['旧进程扫描', '依赖体检', '环境检查']):
            lbl_name = QLabel(name)
            lbl_name.setStyleSheet('font-weight:bold;')
            lbl_state = QLabel('等待中…')
            lbl_state.setStyleSheet('color:#8a8f98;')
            lbl_state.setWordWrap(True)
            grid.addWidget(lbl_name, i, 0, Qt.AlignTop)
            grid.addWidget(lbl_state, i, 1)
            self._rows[name] = lbl_state
        grid.setColumnStretch(1, 1)
        root.addWidget(box)

        # 旧进程清理勾选区（发现旧进程时才显示）
        self._kill_box = QCheckBox('结束上面发现的旧进程（推荐——否则会和新桌宠抢活）')
        self._kill_box.setChecked(True)
        self._kill_box.setVisible(False)
        root.addWidget(self._kill_box)

        self._bar = QProgressBar()
        self._bar.setRange(0, 3)
        self._bar.setValue(0)
        self._bar.setTextVisible(False)
        root.addWidget(self._bar)

        btns = QHBoxLayout()
        self._btn_go = QPushButton('继续 → 进咕嘎')
        self._btn_go.setEnabled(False)
        self._btn_go.setStyleSheet(
            'QPushButton{background:#2f7cf6;color:white;padding:8px 20px;'
            'border-radius:6px;font-weight:bold;}'
            'QPushButton:hover{background:#2468d9;}'
            'QPushButton:disabled{background:#b9c2d0;}')
        self._btn_go.clicked.connect(self._go)
        btns.addStretch(1)
        btns.addWidget(self._btn_go)
        btns.addStretch(1)
        root.addLayout(btns)

        self._thread = _CheckThread()
        self._thread.item.connect(self._on_item)
        self._thread.finished_all.connect(self._on_done)

    def run_checks(self):
        self._thread.start()

    def _on_item(self, name, ok, detail):
        lbl = self._rows.get(name)
        if lbl is None:
            return
        lbl.setText(('✅ ' if ok else '⚠ ') + detail)
        lbl.setStyleSheet('color:%s;' % ('#1d7a3e' if ok else '#b36b00'))
        idx = list(self._rows).index(name) + 1
        self._bar.setValue(idx)

    def _on_done(self, procs, missing):
        self._done = True
        self._procs, self._missing = procs, missing
        if procs:
            self._kill_box.setVisible(True)
            self._btn_go.setText('清理旧进程并继续 →')
        elif missing:
            self._btn_go.setText('仍然继续（真机执行受限） →')
        else:
            self._btn_go.setText('全部通过，继续 →')
        self._btn_go.setEnabled(True)

    def _go(self):
        """结束勾选的旧进程, 然后关闭闸门进应用."""
        if self._procs and self._kill_box.isChecked():
            for pid, _n, _d, proc in self._procs:
                try:
                    proc.terminate()
                except Exception:
                    pass
        self.accept()


def run_startup_gate():
    """comp_main 启动入口调用: 弹自检窗并等用户确认. 无 GUI 环境直接放行."""
    from PyQt5.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        return
    gate = StartupGate()
    gate.run_checks()
    gate.exec_()
