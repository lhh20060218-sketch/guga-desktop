# -*- coding: utf-8 -*-
"""状态系统 — 饱食度/心情/精力 + 衰减计时器"""
from PyQt5.QtCore import QObject, QTimer, pyqtSignal


class StatusSystem(QObject):
    status_changed = pyqtSignal(dict)  # {hunger, happy, energy, mood}
    mood_changed = pyqtSignal(str)      # emoji

    TICK_MS = 20000  # 20 秒 tick

    def __init__(self, parent=None):
        super().__init__(parent)
        self._hunger = 85.0
        self._happy = 75.0
        self._energy = 90.0
        self._sleeping = False

        self._timer = QTimer(self)
        self._timer.setInterval(self.TICK_MS)
        self._timer.timeout.connect(self._tick)

    # ---- 属性 ----
    @property
    def hunger(self) -> float:
        return self._hunger
    @hunger.setter
    def hunger(self, v: float):
        self._hunger = max(0.0, min(100.0, v))

    @property
    def happy(self) -> float:
        return self._happy
    @happy.setter
    def happy(self, v: float):
        self._happy = max(0.0, min(100.0, v))

    @property
    def energy(self) -> float:
        return self._energy
    @energy.setter
    def energy(self, v: float):
        self._energy = max(0.0, min(100.0, v))

    @property
    def mood(self) -> str:
        # 企鹅版：阈值放宽，默认开心，只有极饿才难过
        if self._hunger < 10:
            return '😢'
        elif self._energy < 12:
            return '😴'
        elif self._hunger < 25:
            return '😕'
        elif self._happy > 60 and self._energy > 50:
            return '😄'
        else:
            return '😊'

    @property
    def sleeping(self) -> bool:
        return self._sleeping
    @sleeping.setter
    def sleeping(self, v: bool):
        self._sleeping = v

    def set_all(self, hunger=None, happy=None, energy=None):
        if hunger is not None:
            self.hunger = hunger
        if happy is not None:
            self.happy = happy
        if energy is not None:
            self.energy = energy
        self._emit()

    def snapshot(self) -> dict:
        return {
            "hunger": self._hunger,
            "happy": self._happy,
            "energy": self._energy,
        }

    # ---- 生命周期 ----
    def start(self):
        self._timer.start()

    def stop(self):
        self._timer.stop()

    # ---- 衰减逻辑 ----
    def _tick(self):
        if self._sleeping:
            self.energy = min(100.0, self._energy + 1.5)
        else:
            self.hunger = max(0.0, self._hunger - 0.4)
            self.happy = max(0.0, self._happy - 0.3)
            self.energy = max(0.0, self._energy - 0.3)
        self._emit()

    def _emit(self):
        self.status_changed.emit(self.snapshot())
        self.mood_changed.emit(self.mood)
