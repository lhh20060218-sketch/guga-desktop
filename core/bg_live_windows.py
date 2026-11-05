"""Desktop application's Windows input backend; does not run at import time."""
import os
from pathlib import Path
import time
from contextlib import contextmanager


class HearthstoneWindow:
    def __init__(self):
        import win32api
        import win32con
        import win32gui
        import win32process
        self.api,self.con,self.gui,self.process=win32api,win32con,win32gui,win32process
        from core.bg_input import SendInputMouse
        self.mouse=SendInputMouse()
        self._binding=None
        self.last_input_receipt=None

    @contextmanager
    def physical_dpi(self):
        from core.bg_input import physical_dpi_context
        with physical_dpi_context():
            yield

    def find(self):
        binding=getattr(self,'_binding',None)
        if binding:
            hwnd,pid=binding
            if (self.gui.IsWindow(hwnd) and self.gui.IsWindowVisible(hwnd)
                    and self.process.GetWindowThreadProcessId(hwnd)[1]==pid):
                return hwnd
            self._binding=None
        found=[]
        def visit(hwnd,_):
            if not self.gui.IsWindowVisible(hwnd):
                return
            _,pid=self.process.GetWindowThreadProcessId(hwnd)
            handle=None
            try:
                handle=self.api.OpenProcess(0x1000,False,pid)
                import ctypes
                length=ctypes.c_ulong(2048)
                text=ctypes.create_unicode_buffer(2048)
                if ctypes.windll.kernel32.QueryFullProcessImageNameW(int(handle),0,text,ctypes.byref(length)) and Path(text.value).name.lower()=='hearthstone.exe':
                    found.append(hwnd)
            except Exception:
                pass
            finally:
                if handle:
                    handle.Close()
        self.gui.EnumWindows(visit,None)
        if len(found)!=1:
            raise RuntimeError('请先打开炉石并完成登录；需要唯一游戏窗口')
        hwnd=found[0]
        self._binding=(hwnd,self.process.GetWindowThreadProcessId(hwnd)[1])
        return hwnd

    def _request_activation(self,hwnd):
        """Best-effort focus, not a requirement of the input transport."""
        self.gui.ShowWindow(hwnd,self.con.SW_RESTORE)
        try:
            self.gui.SetForegroundWindow(hwnd)
        except Exception:
            pass
        deadline=time.monotonic()+.3
        while time.monotonic()<deadline:
            if self.gui.GetForegroundWindow()==hwnd:
                return True
            time.sleep(.03)
        return False

    def _owns_point(self,hwnd,point):
        hit=self.gui.WindowFromPoint(point)
        return bool(hit and (hit==hwnd or self.gui.GetAncestor(hit,2)==hwnd))

    @contextmanager
    def input_surface(self,hwnd):
        """Keep the intended surface visible for the whole input transaction."""
        was_topmost=bool(self.gui.GetWindowLong(hwnd,self.con.GWL_EXSTYLE)&self.con.WS_EX_TOPMOST)
        flags=self.con.SWP_NOMOVE|self.con.SWP_NOSIZE|self.con.SWP_SHOWWINDOW
        self.gui.SetWindowPos(hwnd,self.con.HWND_TOPMOST,0,0,0,0,flags)
        try:
            time.sleep(.03)
            yield
        finally:
            self.gui.SetWindowPos(hwnd,self.con.HWND_TOPMOST if was_topmost else self.con.HWND_NOTOPMOST,
                                  0,0,0,0,flags)

    def open(self):
        try:
            hwnd=self.find()
            activated=self._request_activation(hwnd)
            return ('已切回炉石；在主菜单中进入酒馆战棋后可执行' if activated else
                    '已请求恢复炉石窗口；尚未确认焦点，执行时将检查目标是否被遮挡')
        except RuntimeError:
            from core.log_reader import find_log_path
            path=find_log_path()
            launcher=Path(path).parents[2]/'Hearthstone Beta Launcher.exe' if path else None
            if not launcher or not launcher.is_file():
                raise RuntimeError('未找到本机炉石启动器，请先从战网打开一次')
            os.startfile(str(launcher))
            return '已打开炉石启动器；等待战网或游戏加载，登录由你完成'

    def cancelled(self):
        return bool(self.api.GetAsyncKeyState(self.con.VK_ESCAPE)&0x8000)

    def geometry(self,hwnd):
        # Callers include both GUI threads and short-lived CLI processes with
        # different DPI defaults. Always return physical pixels at this boundary.
        with self.physical_dpi():
            return self._physical_geometry(hwnd)

    def _physical_geometry(self,hwnd):
        left,top=self.gui.ClientToScreen(hwnd,(0,0))
        _,_,width,height=self.gui.GetClientRect(hwnd)
        if width<640 or height<400 or self.gui.IsIconic(hwnd):
            raise RuntimeError('游戏窗口太小或已最小化')
        return hwnd,left,top,width,height

    def capture(self):
        with self.physical_dpi():
            from PIL import ImageGrab
            hwnd=self.find()
            self.check_integrity(hwnd)
            self._request_activation(hwnd)
            geometry=self.geometry(hwnd)
            _,left,top,width,height=geometry
            # The desktop host can have an always-on-top window. Raise only the
            # verified game client for the duration of this single observation.
            was_topmost=bool(self.gui.GetWindowLong(hwnd,self.con.GWL_EXSTYLE)&self.con.WS_EX_TOPMOST)
            self.gui.SetWindowPos(hwnd,self.con.HWND_TOPMOST,0,0,0,0,
                self.con.SWP_NOMOVE|self.con.SWP_NOSIZE|self.con.SWP_SHOWWINDOW)
            try:
                time.sleep(.15)
                if not all(self._owns_point(hwnd,p) for p in (
                        (left+8,top+8),(left+width-8,top+8),(left+width//2,top+height//2),
                        (left+8,top+height-8),(left+width-8,top+height-8))):
                    raise RuntimeError('游戏截图区域被其他窗口遮挡；未使用该画面决策')
                return ImageGrab.grab(bbox=(left,top,left+width,top+height)),geometry
            finally:
                self.gui.SetWindowPos(hwnd,self.con.HWND_TOPMOST if was_topmost else self.con.HWND_NOTOPMOST,0,0,0,0,
                    self.con.SWP_NOMOVE|self.con.SWP_NOSIZE)

    def check_integrity(self,hwnd):
        import win32security
        _,pid=self.process.GetWindowThreadProcessId(hwnd)
        handle=self.api.OpenProcess(0x1000,False,pid)
        game_token=own_token=None
        try:
            game_token=win32security.OpenProcessToken(handle,8)
            own_token=win32security.OpenProcessToken(self.api.GetCurrentProcess(),8)
            game=win32security.GetTokenInformation(game_token,win32security.TokenElevation)
            own=win32security.GetTokenInformation(own_token,win32security.TokenElevation)
            if game and not own:
                raise RuntimeError('炉石以管理员运行；请手动以管理员启动咕嘎，或用普通权限重开炉石。当前未发送输入。')
        finally:
            if game_token:game_token.Close()
            if own_token:own_token.Close()
            handle.Close()

    def execute(self,grounding,action,geometry):
        with self.physical_dpi(),self.input_surface(geometry[0]):
            from core.bg_live import validate_grounding
            validate_grounding(grounding,action)
            hwnd,left,top,width,height=geometry
            if self.gui.IsIconic(hwnd):
                self._request_activation(hwnd)
                time.sleep(.12)
                if self.gui.IsIconic(hwnd):
                    raise RuntimeError('炉石窗口已最小化且无法恢复；未发送输入')
            attempted,accepted=self.mouse.attempted,self.mouse.accepted
            self.last_input_receipt=dict(transport='SendInput',attempted_events=0,accepted_events=0,
                                         input_sent=False,button_released=True,game_effect_verified=False)
            if self.find()!=hwnd or self.geometry(hwnd)!=geometry or self.cancelled():
                raise RuntimeError('窗口位置或停止状态已改变；未执行')
            def point(value):
                return left+round(value[0]*(width-1)),top+round(value[1]*(height-1))
            source=point(grounding['source'])
            destination=point(grounding['destination']) if action['kind'] in ('BUY','SELL','PLAY') else None
            if not self._owns_point(hwnd,source) or (destination and not self._owns_point(hwnd,destination)):
                raise RuntimeError('目标被其他窗口遮挡；未执行')
            down_attempted=False
            try:
                self.last_input_receipt['coordinate_space']='physical_pixels'
                self.last_input_receipt['source_physical']=list(source)
                self.mouse.move_verified(source)
                self.last_input_receipt['cursor_arrival']=dict(self.mouse.last_move)
                time.sleep(.035)
                if self.cancelled() or self.geometry(hwnd)!=geometry or not self._owns_point(hwnd,source):
                    raise RuntimeError('按下前窗口或目标已变化；未按下鼠标')
                down_attempted=True
                self.last_input_receipt['button_released']=False
                self.mouse.left_down()
                if destination:
                    time.sleep(.04)
                    target=destination
                    for i in range(1,17):
                        step=(round(source[0]+(target[0]-source[0])*i/16),
                              round(source[1]+(target[1]-source[1])*i/16))
                        if self.cancelled() or self.geometry(hwnd)!=geometry or not self._owns_point(hwnd,step):
                            raise RuntimeError('拖动被停止、窗口移动或目标遮挡；已请求释放鼠标，请检查局面')
                        self.mouse.move(step)
                        time.sleep(.02)
                else:
                    time.sleep(.05)
            finally:
                try:
                    if down_attempted:
                        self.mouse.left_up()
                        self.last_input_receipt['button_released']=True
                finally:
                    self.last_input_receipt.update(attempted_events=self.mouse.attempted-attempted,
                        accepted_events=self.mouse.accepted-accepted,
                        input_sent=self.mouse.accepted>accepted)
            return dict(self.last_input_receipt)
