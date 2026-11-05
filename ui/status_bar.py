# -*- coding: utf-8 -*-
"""状态条 — 饱食度/心情/精力 三色渐变为条"""
from PyQt5.QtCore import Qt, QRect
from PyQt5.QtGui import QPainter, QColor, QFont, QLinearGradient
from PyQt5.QtWidgets import QWidget


class StatusBar(QWidget):
    """紧凑的三格状态条"""

    ITEM_W = 100
    HEIGHT = 20

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data = {"hunger": 85, "happy": 75, "energy": 90}
        self._labels = {"hunger": "🍖", "happy": "🎮", "energy": "⚡"}
        self.setFixedHeight(self.HEIGHT)
        self.setAttribute(Qt.WA_TranslucentBackground)

    def update_values(self, data: dict):
        self._data = data
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        font = QFont("Microsoft YaHei", 8)
        painter.setFont(font)

        keys = ["hunger", "happy", "energy"]
        total_w = self.ITEM_W * len(keys) + (len(keys) - 1) * 6
        offset = (self.width() - total_w) // 2

        for i, key in enumerate(keys):
            x = offset + i * (self.ITEM_W + 6)
            y = 0
            val = self._data.get(key, 50)
            self._draw_item(painter, x, y, self.ITEM_W, self.HEIGHT,
                           self._labels[key], val)
        painter.end()

    def _draw_item(self, p, x, y, w, h, icon, val):
        # 背景
        bg = QColor(0, 0, 0, 25)
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(x, y, w, h, 8, 8)
        p.fillRect(x, y, w, h, bg)

        # 进度条
        bar_w = w - 28
        bar_h = 4
        bar_x = x + 24
        bar_y = y + (h - bar_h) // 2

        # 背景条
        p.fillRect(bar_x, bar_y, bar_w, bar_h, QColor(255, 255, 255, 25))

        # 彩色填充
        fill_w = int(bar_w * val / 100)
        if fill_w > 0:
            grad = QLinearGradient(bar_x, 0, bar_x + bar_w, 0)
            if val > 60:
                grad.setColorAt(0, QColor(168, 224, 99))     # 绿
                grad.setColorAt(1, QColor(86, 171, 47))
            elif val > 30:
                grad.setColorAt(0, QColor(246, 211, 101))    # 橙
                grad.setColorAt(1, QColor(253, 160, 133))
            else:
                grad.setColorAt(0, QColor(255, 154, 158))    # 红
                grad.setColorAt(1, QColor(250, 208, 196))
            p.fillRect(bar_x, bar_y, fill_w, bar_h, grad)

        # emoji 图标
        p.setPen(QColor(255, 255, 255, 200))
        icon_font = QFont("Segoe UI Emoji", 10)
        p.setFont(icon_font)
        p.drawText(QRect(x + 2, y, 22, h), Qt.AlignCenter, icon)
        p.setFont(QFont("Microsoft YaHei", 8))
