"""Small SendInput mouse transport; no foreground window/PID dependency."""
import ctypes
import time
from contextlib import contextmanager, nullcontext


@contextmanager
def physical_dpi_context():
    """Keep Win32 geometry, metrics and cursor readings in physical pixels."""
    user = ctypes.WinDLL('user32', use_last_error=True)
    setter = user.SetThreadDpiAwarenessContext
    setter.argtypes = (ctypes.c_void_p,)
    setter.restype = ctypes.c_void_p
    previous = setter(ctypes.c_void_p(-4))
    if not previous:
        raise RuntimeError('无法切换线程到物理像素 DPI 上下文；未发送输入')
    try:
        yield
    finally:
        setter(previous)

DWORD = ctypes.c_uint32
LONG = ctypes.c_int32
WORD = ctypes.c_uint16
ULONG_PTR = ctypes.c_size_t


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [('dx', LONG), ('dy', LONG), ('mouseData', DWORD),
                ('dwFlags', DWORD), ('time', DWORD), ('dwExtraInfo', ULONG_PTR)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [('wVk', WORD), ('wScan', WORD), ('dwFlags', DWORD),
                ('time', DWORD), ('dwExtraInfo', ULONG_PTR)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [('uMsg', DWORD), ('wParamL', WORD), ('wParamH', WORD)]


class _PAYLOAD(ctypes.Union):
    _fields_ = [('mi', MOUSEINPUT), ('ki', KEYBDINPUT), ('hi', HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ('payload',)
    _fields_ = [('type', DWORD), ('payload', _PAYLOAD)]


class SendInputMouse:
    def __init__(self, user32=None):
        self.user = user32 if user32 is not None else ctypes.WinDLL('user32', use_last_error=True)
        if user32 is None:
            self.user.SendInput.argtypes = (ctypes.c_uint, ctypes.POINTER(INPUT), ctypes.c_int)
            self.user.SendInput.restype = ctypes.c_uint
            self.user.GetSystemMetrics.argtypes = (ctypes.c_int,)
            self.user.GetSystemMetrics.restype = ctypes.c_int
        self.attempted = 0
        self.accepted = 0
        self.last_move = None
        self._dpi = physical_dpi_context if user32 is None else nullcontext

    def _send(self, flags, x=0, y=0):
        packet = INPUT(type=0)
        packet.mi = MOUSEINPUT(x, y, 0, flags, 0, 0)
        self.attempted += 1
        count = self.user.SendInput(1, ctypes.byref(packet), ctypes.sizeof(INPUT))
        self.accepted += int(count)
        if count != 1:
            code = ctypes.get_last_error() if hasattr(ctypes, 'get_last_error') else 0
            raise RuntimeError(f'SendInput 未接受鼠标事件（accepted={count}/1, win32_error={code}）；不能视为游戏已收到')

    def move(self, point):
        with self._dpi():
            return self._physical_move(point)

    def _physical_move(self, point):
        left, top, width, height = (self.user.GetSystemMetrics(k) for k in (76, 77, 78, 79))
        x, y = point
        if width < 2 or height < 2 or not (left <= x < left+width and top <= y < top+height):
            raise RuntimeError('鼠标坐标超出有效虚拟桌面；未发送')
        x = round((x-left)*65535/(width-1))
        y = round((y-top)*65535/(height-1))
        self._send(0x0001 | 0x8000 | 0x4000, x, y)

    def cursor_position(self):
        class POINT(ctypes.Structure):
            _fields_ = [('x', LONG), ('y', LONG)]
        with self._dpi():
            point = POINT()
            if not self.user.GetCursorPos(ctypes.byref(point)):
                raise RuntimeError('无法读取物理像素光标位置；未按下鼠标')
            return point.x, point.y

    def move_verified(self, point, timeout=.15):
        """Wait only for cursor arrival, before any button can be pressed."""
        self.move(point)
        deadline = time.monotonic() + timeout
        while True:
            actual = self.cursor_position()
            arrived = max(abs(actual[i]-point[i]) for i in (0, 1)) <= 1
            self.last_move = dict(requested_physical=list(point), actual_physical=list(actual), arrived=arrived)
            if arrived:
                return self.last_move
            if time.monotonic() >= deadline:
                raise RuntimeError(f'光标未到达物理像素目标；未按下鼠标（target={point}, actual={actual}）')
            time.sleep(.005)

    def left_down(self):
        self._send(0x0002)

    def left_up(self):
        self._send(0x0004)
