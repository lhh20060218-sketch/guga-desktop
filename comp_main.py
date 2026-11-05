#! python
# -*- coding: utf-8 -*-
"""参赛版入口 — 管家 + 六员工, 干净产品形态

启动: python comp_main.py
原版开发窗体仍用 main.py 启动, 两者互不影响.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from launcher import _prepare_qt
_prepare_qt()

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt


def main():
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName("咕嘎管家(参赛版)")
    app.setQuitOnLastWindowClosed(False)

    # 第一步: 启动自检闸门 —— 先查旧进程(会抢单顶号的旧值守程序)/缺失依赖/
    # 屏幕环境, 全部过目后才进配置向导和应用. 问题在第一秒暴露, 不等派单才炸.
    from ui.startup_gate import run_startup_gate
    run_startup_gate()

    # 第二步: 首次配置向导 —— 检测不到有效 ai_config.json 时自动弹出,
    # 图形化选平台/填 Key/测试连接, 小白全程不碰 JSON.
    from ui.first_run import ensure_config
    if not ensure_config():
        sys.exit(0)

    from ui.comp_window import CompWindow
    window = CompWindow()
    window.show()
    window.raise_()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
