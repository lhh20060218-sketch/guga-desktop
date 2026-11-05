#! python
# -*- coding: utf-8 -*-
"""黑猫桌宠 — 入口文件"""
import sys
import os

# 将项目根目录加入 Python 路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from launcher import _prepare_qt
_prepare_qt()

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt, QTimer
from ui.pet_window import PetWindow


def main():
    # 高 DPI 支持
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName("咕嘎企鹅桌宠")
    app.setOrganizationName("BlackCatPet")
    # This is a tray companion. Closing a transient menu/dialog must not end
    # the desktop process; the existing explicit Quit action still does that.
    app.setQuitOnLastWindowClosed(False)

    # 创建并显示窗口
    window = PetWindow()
    if '--summon-fish' in sys.argv:
        QTimer.singleShot(400, lambda:window._multi_agent.summon('002'))
    # Only an explicit launch flag starts capture; normal startup stays quiet.
    if '--voice' in sys.argv:
        QTimer.singleShot(300, window._open_agent_voice)
    if '--bg-live' in sys.argv:
        QTimer.singleShot(300, window._open_bg_live)

    # 管家系统: 员工召唤 + 知识库检索链 + 事务提醒语音播报 (--no-butler 关闭)
    if '--no-butler' not in sys.argv:
        QTimer.singleShot(600, _attach_butler(window))

    sys.exit(app.exec_())


def _attach_butler(window):
    def _do():
        try:
            from ui.butler_attach import attach_butler
            attach_butler(window)
        except Exception as exc:      # 装配失败不阻塞桌宠本体
            print('[butler] attach failed: %s' % exc)
    return _do


if __name__ == "__main__":
    main()
