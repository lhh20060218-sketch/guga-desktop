# -*- coding: utf-8 -*-
"""全局键盘钩子 — Win32 WH_KEYBOARD_LL"""
import ctypes
import ctypes.wintypes
from collections import deque
from PyQt5.QtCore import QObject, QTimer, pyqtSignal

# Win32 常数
WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_SYSKEYDOWN = 0x0104

# 虚拟键码 → 显示字符映射
VK_MAP = {
    # 字母
    0x41: 'A', 0x42: 'B', 0x43: 'C', 0x44: 'D', 0x45: 'E',
    0x46: 'F', 0x47: 'G', 0x48: 'H', 0x49: 'I', 0x4A: 'J',
    0x4B: 'K', 0x4C: 'L', 0x4D: 'M', 0x4E: 'N', 0x4F: 'O',
    0x50: 'P', 0x51: 'Q', 0x52: 'R', 0x53: 'S', 0x54: 'T',
    0x55: 'U', 0x56: 'V', 0x57: 'W', 0x58: 'X', 0x59: 'Y', 0x5A: 'Z',
    # 数字
    0x30: '0', 0x31: '1', 0x32: '2', 0x33: '3', 0x34: '4',
    0x35: '5', 0x36: '6', 0x37: '7', 0x38: '8', 0x39: '9',
    # 符号
    0xBA: ';', 0xBB: '=', 0xBC: ',', 0xBD: '-', 0xBE: '.',
    0xBF: '/', 0xC0: '`', 0xDB: '[', 0xDC: '\\', 0xDD: ']', 0xDE: "'",
    # 功能
    0x09: '⇥', 0x0D: '↵', 0x08: '⌫', 0x1B: 'Esc',
    0x20: '␣',
    0x10: '⇧', 0x11: 'Ctrl', 0x12: 'Alt',
}

# 回调类型
HOOKPROC = ctypes.WINFUNCTYPE(
    ctypes.wintypes.LPARAM,
    ctypes.c_int, ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM
)


class KeyboardHook(QObject):
    """Win32 低级键盘钩子，捕获全局按键事件"""
    key_pressed = pyqtSignal(int)    # 虚拟键码

    def __init__(self, parent=None):
        super().__init__(parent)
        self._hook_id = None
        self._queue = deque(maxlen=32)
        self._active = False

        # 50ms 足够让快捷键响应保持即时，同时避免空闲时每秒唤醒60多次。
        self._timer = QTimer(self)
        self._timer.setInterval(50)
        self._timer.timeout.connect(self._flush)

    # ---- 安装/卸载 ----
    def start(self):
        if self._active:
            return
        self._proc = HOOKPROC(self._callback)
        self._hook_id = ctypes.windll.user32.SetWindowsHookExW(
            WH_KEYBOARD_LL,
            self._proc,
            ctypes.windll.kernel32.GetModuleHandleW(None),
            0
        )
        if self._hook_id:
            self._active = True
            self._timer.start()

    def stop(self):
        if not self._active:
            return
        self._timer.stop()
        if self._hook_id:
            ctypes.windll.user32.UnhookWindowsHookEx(self._hook_id)
            self._hook_id = None
        self._active = False

    @property
    def is_active(self) -> bool:
        return self._active

    # ---- 回调（系统级，必须极快） ----
    def _callback(self, nCode, wParam, lParam):
        if nCode >= 0 and wParam in (WM_KEYDOWN, WM_SYSKEYDOWN):
            vk = ctypes.cast(lParam, ctypes.POINTER(ctypes.c_ulong))[0] & 0xFF
            self._queue.append(vk)
        return ctypes.windll.user32.CallNextHookEx(None, nCode, wParam, lParam)

    # ---- 消费队列 ----
    def _flush(self):
        while self._queue:
            vk = self._queue.popleft()
            self.key_pressed.emit(vk)

    def __del__(self):
        self.stop()

    # ---- 工具 ----
    @staticmethod
    def vk_to_char(vk: int) -> str:
        """虚拟键码 → 显示字符"""
        return VK_MAP.get(vk, chr(vk) if 0x20 <= vk < 0x80 else '')
