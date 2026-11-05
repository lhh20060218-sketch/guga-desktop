# -*- coding: utf-8 -*-
"""Bongo Cat 风格键盘面板 — QPainter 自绘"""
from PyQt5.QtCore import Qt, QRect, QTimer
from PyQt5.QtGui import QPainter, QColor, QFont, QPen
from PyQt5.QtWidgets import QWidget


KEY_LAYOUT = [
    ['`', '1', '2', '3', '4', '5', '6', '7', '8', '9', '0', '-', '='],
    ['q', 'w', 'e', 'r', 't', 'y', 'u', 'i', 'o', 'p', '[', ']', '\\'],
    ['a', 's', 'd', 'f', 'g', 'h', 'j', 'k', 'l', ';', "'"],
    ['z', 'x', 'c', 'v', 'b', 'n', 'm', ',', '.', '/'],
]

# 空格键单独
SPACE_KEY = ' '


class BongoPanel(QWidget):
    """自绘键盘面板，不创建大量 QLabel"""

    KEY_SIZE = 26
    KEY_GAP = 2
    ROW_GAP = 2
    PADDING = 8

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pressed = set()  # 当前按下的键字符
        self._layout_cache = []  # [(char, QRect), ...]
        self._space_rect = QRect()
        self._build_layout()
        self.setAttribute(Qt.WA_TranslucentBackground)

        # 高亮清理定时器
        self._clear_timer = QTimer(self)
        self._clear_timer.setInterval(120)
        self._clear_timer.setSingleShot(True)
        self._clear_timer.timeout.connect(self._clear_all)

        # 计算面板高度
        rows = len(KEY_LAYOUT) + 1  # +1 空格行
        h = rows * (self.KEY_SIZE + self.ROW_GAP) + self.PADDING * 2 - self.ROW_GAP
        max_w = max(len(r) for r in KEY_LAYOUT) * (self.KEY_SIZE + self.KEY_GAP) + self.PADDING * 2 - self.KEY_GAP
        self.setFixedSize(max_w, h)

    def _build_layout(self):
        """预计算每个键的矩形位置"""
        x0 = self.PADDING
        y0 = self.PADDING
        for row in KEY_LAYOUT:
            x = x0
            for ch in row:
                r = QRect(x, y0, self.KEY_SIZE, self.KEY_SIZE)
                self._layout_cache.append((ch, r))
                x += self.KEY_SIZE + self.KEY_GAP
            y0 += self.KEY_SIZE + self.ROW_GAP
        # 空格
        sx = self.PADDING + (self.KEY_SIZE + self.KEY_GAP) * 4
        self._space_rect = QRect(sx, y0, self.KEY_SIZE * 6 + self.KEY_GAP * 5, self.KEY_SIZE)

    # ---- 按键响应 ----
    def press_key(self, vk_or_char):
        """由 keyboard_hook 驱动"""
        if isinstance(vk_or_char, int):
            from core.keyboard_hook import KeyboardHook
            ch = KeyboardHook.vk_to_char(vk_or_char)
        else:
            ch = vk_or_char
        if not ch:
            return
        ch = ch.lower()
        self._pressed.add(ch)
        self.update()
        # 延迟清理
        self._clear_timer.start()

    def _clear_all(self):
        self._pressed.clear()
        self.update()

    # ---- 绘画 ----
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # 绘制所有按键
        for ch, rect in self._layout_cache:
            active = ch in self._pressed
            self._draw_key(painter, rect, ch.upper(), active)

        # 空格
        active = SPACE_KEY in self._pressed
        self._draw_key(painter, self._space_rect, '␣', active)

    def _draw_key(self, p, rect, label, active):
        """画一个键"""
        if active:
            bg = QColor(255, 255, 255, 45)
            text_c = QColor(255, 255, 255, 220)
            border_c = QColor(255, 255, 255, 50)
        else:
            bg = QColor(255, 255, 255, 10)
            text_c = QColor(255, 255, 255, 60)
            border_c = QColor(255, 255, 255, 10)

        r = rect.adjusted(1, 1, -1, -1)
        p.setPen(QPen(border_c, 0.5))
        p.setBrush(bg)
        p.drawRoundedRect(r, 3, 3)

        # 文字
        p.setPen(text_c)
        font = QFont("Consolas", 8) if label != '␣' else QFont("Segoe UI", 8)
        p.setFont(font)
        p.drawText(r, Qt.AlignCenter, label)
