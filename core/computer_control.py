"""Windows observation/input tools. No per-application allowlist in full access mode."""
import base64
import ctypes
from ctypes import wintypes
import io
import threading
import time
import uuid

try:
    from core import input_guard
except Exception:                       # 独立运行电脑控制模块时保持原行为
    input_guard = None

def _gate(hwnd=None):
    """发键鼠事件前的统一闸；hwnd 有值就登记为目标窗口，供恢复时复核。"""
    if input_guard is None:
        return
    if hwnd:
        input_guard.note_target(hwnd)
    input_guard.assert_active()


DIALOG_CLASS = '#32770'
_WM_COMMAND = 0x0111

#: 滚轮一格。20261110ac 真机实测（豆包对话区，UIA 行 rect 位移）：
#: ``+120`` 所有行向下移 → 看到更早的内容；``-120`` 所有行向上移 → 看到更后的内容。
#: 全仓只在这里做“意图 → delta”的转换，禁止调用方各自写正负号。
WHEEL_NOTCH = 120
_WHEEL_INTENTS = {
    "later": -WHEEL_NOTCH, "down": -WHEEL_NOTCH, "forward": -WHEEL_NOTCH,
    "next": -WHEEL_NOTCH, "bottom": -WHEEL_NOTCH,
    "往下": -WHEEL_NOTCH, "向下": -WHEEL_NOTCH, "更后": -WHEEL_NOTCH,
    "earlier": WHEEL_NOTCH, "up": WHEEL_NOTCH, "back": WHEEL_NOTCH,
    "previous": WHEEL_NOTCH, "top": WHEEL_NOTCH,
    "往上": WHEEL_NOTCH, "向上": WHEEL_NOTCH, "更早": WHEEL_NOTCH,
}


def wheel_delta(intent):
    """滚动意图 → ``MOUSEEVENTF_WHEEL`` 的 dwData。

    ``later``/``down``（往下翻、看更后）返回 -120；``earlier``/``up`` 返回 +120。
    """
    key = str(intent or "").strip().lower()
    if key not in _WHEEL_INTENTS:
        raise ValueError("未知滚动意图: %r（只支持 later/down 或 earlier/up）" % (intent,))
    return _WHEEL_INTENTS[key]


def wheel_notches(intent, notches=1):
    """把意图展开成每格一次的 delta 列表，便于调用方逐格发送。"""
    count = max(1, int(notches))
    return [wheel_delta(intent)] * count


class ModalBlocked(RuntimeError):
    """模态弹窗清不掉：交还人工，禁止继续盲试。"""
    code = 'modal_blocked'

    def __init__(self, message, detail=None):
        super().__init__('manual_required: ' + str(message))
        self.detail = detail or {}
        self.manual_required = True


def _owner_of(hwnd):
    """弹窗的 owner（Win32 消息框 owner 指向主窗口，不一定等于 parent）。"""
    try:
        import win32con
        import win32gui
        owner = int(win32gui.GetWindow(hwnd, win32con.GW_OWNER) or 0)
        return owner if owner and owner != hwnd else int(win32gui.GetParent(hwnd) or 0)
    except Exception:
        return 0


def _process_dialogs(main_hwnd):
    """同进程可见的 #32770；owner 指向主窗口的排前面。"""
    import win32gui
    import win32process
    try:
        pid = win32process.GetWindowThreadProcessId(main_hwnd)[1]     # [1] 才是进程 id
    except Exception:
        return []
    found = []
    def visit(window, _):
        try:
            if (win32gui.IsWindowVisible(window) and win32gui.GetClassName(window) == DIALOG_CLASS
                    and win32process.GetWindowThreadProcessId(window)[1] == pid):
                found.append(window)
        except Exception:
            pass
        return True
    win32gui.EnumWindows(visit, None)
    owned = [h for h in found if _owner_of(h) == main_hwnd]
    return owned + [h for h in found if h not in owned]


def _modal_of(target):
    """主路径：IsWindowEnabled(主窗口)==0 + 同进程 #32770 且 owner 指向主窗口。

    不再依赖 GetLastActivePopup（实测它返回主窗口自己，拿不到弹窗）。
    """
    if not target:
        return None
    import win32gui
    if not win32gui.IsWindow(target):
        return None
    try:
        if win32gui.GetClassName(target) == DIALOG_CLASS:
            main = _owner_of(target) or target
            return dict(main=main, dialog=target,
                        main_enabled=bool(win32gui.IsWindowEnabled(main)))
        # 只认“主窗口被禁用”这一个实测签名：模态弹窗打开时 IsWindowEnabled(主窗口)==0。
        # 主窗口仍可用时，同进程里可见的 #32770 可能只是非模态浮层/工具面板，不能算挡路，
        # 否则会把正常输入误判成 modal_blocked，反复对用户抛错。
        if not win32gui.IsWindowEnabled(target):
            dialogs = _process_dialogs(target)
            return dict(main=target, dialog=dialogs[0] if dialogs else 0, main_enabled=False)
    except Exception:
        pass
    return None


def _scan_modal_anywhere():
    """hwnd 缺省时的兜底：找 owner 已被禁用的可见 #32770，不再只看前台窗口。"""
    import win32gui
    found = []
    def visit(window, _):
        try:
            if win32gui.IsWindowVisible(window) and win32gui.GetClassName(window) == DIALOG_CLASS:
                owner = _owner_of(window)
                if owner and win32gui.IsWindow(owner) and not win32gui.IsWindowEnabled(owner):
                    found.append(dict(main=owner, dialog=window, main_enabled=False))
        except Exception:
            pass
        return True
    win32gui.EnumWindows(visit, None)
    return found[0] if found else None


def _buttons_of(dialog):
    import win32gui
    buttons = []
    def visit(window, _):
        try:
            if win32gui.IsWindowVisible(window) and win32gui.GetClassName(window) == 'Button':
                buttons.append(dict(hwnd=window, text=str(win32gui.GetWindowText(window) or '')[:80],
                                    enabled=bool(win32gui.IsWindowEnabled(window))))
        except Exception:
            pass
        return True
    win32gui.EnumChildWindows(dialog, visit, None)
    return buttons


_DIALOG_OK_WORDS = ('确定', '好', 'ok', '知道了', '关闭', '知道了', '是', 'yes', '允许', 'allow', '继续')


def _pick_button(dialog, wanted=''):
    import re
    def fold(value):
        return re.sub(r'\W', '', str(value or '')).casefold()
    buttons = [b for b in _buttons_of(dialog) if b['enabled']]
    if not buttons:
        return 0
    target = fold(wanted)
    if target:
        exact = [b for b in buttons if fold(b['text']) == target]
        if exact:
            return exact[0]['hwnd']
        part = [b for b in buttons if target and target in fold(b['text'])]
        if part:
            return part[0]['hwnd']
        return 0
    for word in _DIALOG_OK_WORDS:
        hit = [b for b in buttons if fold(word) and fold(word) in fold(b['text'])]
        if hit:
            return hit[0]['hwnd']
    return 0


def _wait_dialog_closed(dialog, cancel, timeout=1.4):
    import win32gui
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if not win32gui.IsWindow(dialog) or not win32gui.IsWindowVisible(dialog):
                return True
        except Exception:
            return True
        if cancel is not None and cancel.wait(.05):
            raise RuntimeError('验证已取消')
        time.sleep(.05)
    return False


def _wait_main_enabled(main, cancel, timeout=.8):
    import win32gui
    if not main:
        return True
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if win32gui.IsWindowEnabled(main):
                return True
        except Exception:
            return False
        if cancel is not None and cancel.wait(.05):
            raise RuntimeError('验证已取消')
        time.sleep(.05)
    return False


def _modal_blocks(hwnd):
    """输入动作预检：只有目标是被模态挡住的主窗口才拦；目标本身是弹窗时放行。"""
    import win32gui
    try:
        if not hwnd or not win32gui.IsWindow(hwnd):
            return None
        if win32gui.GetClassName(hwnd) == DIALOG_CLASS:
            return None                      # 正在操作弹窗本身
        return _modal_of(hwnd)
    except Exception:
        return None

class _KI(ctypes.Structure):
    _fields_=[('vk',wintypes.WORD),('scan',wintypes.WORD),('flags',wintypes.DWORD),('time',wintypes.DWORD),('extra',ctypes.c_size_t)]
class _MI(ctypes.Structure):
    _fields_=[('dx',wintypes.LONG),('dy',wintypes.LONG),('data',wintypes.DWORD),('flags',wintypes.DWORD),('time',wintypes.DWORD),('extra',ctypes.c_size_t)]
class _U(ctypes.Union):_fields_=[('ki',_KI),('mi',_MI)]
class _INPUT(ctypes.Structure):_fields_=[('type',wintypes.DWORD),('value',_U)]

# 派单侧用私有 DLL 实例 + 每次调用显式绑定本模块的结构签名：即使别的模块（含启动自检）
# 给 ctypes.windll.user32 设过 POINTER(INPUT)，这里也不会串味。
_USER32_KEYS=ctypes.WinDLL('user32',use_last_error=True)
_USER32_TEXT=ctypes.WinDLL('user32',use_last_error=True)

def _bind_sendinput(user,packet):
    """幂等绑定 SendInput 签名；失败不影响原有调用路径。"""
    try:
        user.SendInput.argtypes=[wintypes.UINT,ctypes.POINTER(packet),ctypes.c_int]
        user.SendInput.restype=wintypes.UINT
    except Exception:
        pass


def _attach_focus(hwnd):
    """Windows foreground handoff, bounded to the requested existing window."""
    import win32gui,win32process,win32api
    user=ctypes.windll.user32;attached=[]
    try:
        target_thread=win32process.GetWindowThreadProcessId(hwnd)[0]
        foreground=win32gui.GetForegroundWindow()
        foreground_thread=win32process.GetWindowThreadProcessId(foreground)[0] if foreground else 0
        current=win32api.GetCurrentThreadId()
        if not target_thread:return False
        for thread in set((target_thread,foreground_thread))-{0,current}:
            if user.AttachThreadInput(current,thread,True):attached.append(thread)
        win32gui.BringWindowToTop(hwnd)
        win32gui.SetForegroundWindow(hwnd)
        return win32gui.GetForegroundWindow()==hwnd
    except Exception:return False
    finally:
        for thread in reversed(attached):user.AttachThreadInput(current,thread,False)


def _root(hwnd):
    """顶层窗口句柄。Electron/Chromium 应用（WorkBuddy、JoyCode、豆包、Trae）
    内部是子窗口，点击后前台句柄会变成父窗口；直接比原句柄会误判“前台已改变”。"""
    import win32gui
    try:
        return int(win32gui.GetAncestor(int(hwnd), 2) or hwnd)
    except Exception:
        return int(hwnd or 0)


def _ensure_foreground(hwnd,timeout=.7):
    """Best-effort focus recovery for cross-app automation.

    Windows may hand focus to another window between steps (the pet, a toast,
    or the user's own click).  Give the target one bounded chance to come back
    instead of failing the whole action immediately.
    """
    import win32gui
    hwnd=int(hwnd);deadline=time.monotonic()+max(0,float(timeout));last=0.0
    while True:
        if win32gui.GetForegroundWindow()==hwnd:return True
        if not win32gui.IsWindow(hwnd):return False
        now=time.monotonic()
        if now-last>=.15:
            last=now
            try:
                win32gui.ShowWindow(hwnd,9)
                win32gui.SetForegroundWindow(hwnd)
            except Exception:
                _attach_focus(hwnd)
        if time.monotonic()>=deadline:break
        time.sleep(.05)
    return win32gui.GetForegroundWindow()==hwnd

def _coerce_hwnd(args, observation=None):
    """把模型给的目标窗口解析成 hwnd：数字句柄 → 窗口标题/软件名 → 最近观察 → 0。

    模型经常把窗口标题塞进 uia_id/window/query 而漏掉 hwnd；只剩前台窗口时，
    前台往往就是咕嘎自己的对话窗，直接拿它当目标会观察/输入到错误窗口。
    """
    import win32gui
    raw=args.get('hwnd')
    try:hwnd=int(raw) if raw not in (None,'',0) else 0
    except (TypeError,ValueError):hwnd=0
    if hwnd and win32gui.IsWindow(hwnd):return hwnd
    needle=''
    for key in ('window','title','name','target','query','uia_id'):
        value=str(args.get(key) or '').strip()
        if value and not value.isdigit() and len(value)<=60:
            needle=value;break
    if needle:
        try:
            import re as _re
            from core.window_inventory import list_windows
            tokens=[t for t in _re.split(r'[\s·\-_/的]+',needle.casefold()) if len(t)>=3]
            best=0;best_hwnd=0
            for item in list_windows(''):
                candidate=int(item.get('hwnd') or 0)
                if not candidate or not win32gui.IsWindow(candidate) or win32gui.IsIconic(candidate):
                    continue
                # Electron 会有 64×64/105×105 的隐藏辅助窗口，标题同样是软件名，
                # 按标题匹配时必须跳过这些“假主窗口”，否则观察到的是一块小黑块。
                rect=item.get('rect') or (0,0,0,0)
                if (rect[2]-rect[0])<300 or (rect[3]-rect[1])<200:
                    continue
                title=str(item.get('title') or '').casefold()
                proc=str(item.get('process_name') or '').casefold()
                score=4 if needle.casefold() in title else 0
                for token in tokens:
                    if token in proc:score+=2
                    if token in title:score+=3
                    if title.strip()==token:score+=3      # 标题正好等于关键词（如标题“Agent”）
                if score>best:best,best_hwnd=score,candidate
            if best_hwnd:return best_hwnd
        except Exception:pass
    if observation:
        candidate=int(observation.get('hwnd') or 0)
        if candidate and win32gui.IsWindow(candidate):return candidate
    return 0


def _send_keys(values):
    user=_USER32_KEYS;_bind_sendinput(user,_INPUT)
    pressed=[]
    def send(code,up=False):
        extended=code in (33,34,35,36,37,38,39,40,45,46,91,92)
        packet=_INPUT(1,_U(ki=_KI(code,user.MapVirtualKeyW(code,0),int(extended)|(2 if up else 0),0,0)))
        if user.SendInput(1,ctypes.byref(packet),ctypes.sizeof(_INPUT))!=1:raise RuntimeError('Windows拒绝快捷键输入')
    try:
        for code in values:
            _gate()                 # 每个键按下前先查暂停；暂停就一个键都不发
            send(code);pressed.append(code)
    finally:
        # 只抬已按下的键：暂停时既不留卡住的修饰键，也不额外发出无关事件
        for code in reversed(pressed):send(code,True)


class ComputerControl:
    def __init__(self, access=None):
        from core.desktop_access import DesktopAccess
        self.access=access or DesktopAccess()
        self.observation=None
        self.target_hint=''          # 点名软件的窗口线索（self_agent 派单时写入）
        self._uia_backend=None
        self._uia_weak={}

    def _uia(self):
        if self._uia_backend is None:
            from core.uia_service import shared_service
            self._uia_backend=shared_service()
        return self._uia_backend

    def _grab(self,hwnd):
        import win32gui
        from PIL import ImageGrab
        rect=win32gui.GetWindowRect(hwnd)
        if rect[2]<=rect[0] or rect[3]<=rect[1]:raise ValueError('窗口没有可见区域')
        return ImageGrab.grab(bbox=rect,all_screens=True).convert('RGB'),rect

    @staticmethod
    def _fingerprint(frame):
        import base64
        small=frame.convert('L').resize((48,32))
        return base64.b64encode(bytes(small.getdata())).decode()

    @staticmethod
    def _diff_ratio(frame,baseline):
        import base64
        small=frame.convert('L').resize((48,32));data=bytes(small.getdata())
        base=base64.b64decode(baseline)
        if len(base)!=len(data):raise ValueError('baseline 与当前画面尺寸不符')
        return sum(1 for a,b in zip(data,base) if abs(a-b)>=10)/len(data)

    @staticmethod
    def _ocr_words(frame, script=None):
        """Windows OCR with per-word boxes normalized to the captured frame.

        OCR 不可用时抛 ``OcrUnavailableError``（code=ocr_unavailable），带缺什么/
        去哪补/下一步和 PowerShell 原文；调用方据此降级，不再抛裸 RuntimeError。
        """
        import tempfile
        from pathlib import Path

        from core import ocr_engine
        with tempfile.TemporaryDirectory(prefix='guga-gui-') as folder:
            image=Path(folder)/'frame.png'
            frame.save(image,format='PNG')
            outcome=ocr_engine.run_on_image(image, script=script)
            if not outcome.get('ok'):
                raise ocr_engine.error_from(outcome)
            data=outcome.get('data') or {}
        width,height=frame.size
        words=[]
        for line in data.get('lines') or []:
            for word in line.get('words') or []:
                try:
                    words.append(dict(text=str(word.get('text') or ''),
                        x=round(float(word['x'])/width,4),y=round(float(word['y'])/height,4),
                        w=round(float(word['width'])/width,4),h=round(float(word['height'])/height,4)))
                except (KeyError,TypeError,ValueError,ZeroDivisionError):continue
        return dict(text=str(data.get('text') or '')[:3000],words=words)

    @staticmethod
    def _crop_region(frame,region):
        """Crop by normalized x/y/w/h; returns cropped frame and the offset for remapping."""
        width,height=frame.size
        left=max(0,min(width-1,int(float(region.get('x',0))*width)))
        top=max(0,min(height-1,int(float(region.get('y',0))*height)))
        right=min(width,left+max(1,int(float(region.get('w',1))*width)))
        bottom=min(height,top+max(1,int(float(region.get('h',1))*height)))
        return frame.crop((left,top,right,bottom)),dict(left=left,top=top,width=width,height=height)

    def _ocr_crop(self,frame,region):
        """OCR a window region; small UI text often needs a crop. Cache unchanged frames."""
        import json
        crop,base=self._crop_region(frame,region) if region else (frame,None)
        stamp=self._fingerprint(crop)
        key=(stamp,json.dumps(region or {},sort_keys=True))
        cache=getattr(self,'_ocr_cache',None)
        if cache is None:cache={};self._ocr_cache=cache
        hit=cache.get(key)
        if hit and time.monotonic()-hit[1]<8:return hit[0]
        result=self._ocr_words(crop)
        if base:
            width,height=base['width'],base['height']
            for word in result['words']:
                word['x']=round((base['left']+word['x']*crop.width)/width,4)
                word['y']=round((base['top']+word['y']*crop.height)/height,4)
                word['w']=round(word['w']*crop.width/width,4);word['h']=round(word['h']*crop.height/height,4)
        cache[key]=(result,time.monotonic())
        if len(cache)>8:
            oldest=min(cache,key=lambda item:cache[item][1])
            cache.pop(oldest,None)
        return result

    def _press_modal(self,main_hwnd=0,dialog_hwnd=0,button_text='',cancel=None,max_rounds=5,reentry_wait=.25):
        """点掉原生模态弹窗：#32770 按钮走 WM_COMMAND(BN_CLICKED)。

        - 不抢前台：PostMessage 发到对话框，不用鼠标点；BM_CLICK 对这类消息框无效。
        - 连续重入：关掉一个后短等再查，最多 max_rounds 轮，超限交还人工。
        - 关掉后复验主窗口恢复 enabled，没恢复也算没清掉。
        """
        import win32gui
        user=ctypes.windll.user32
        main_hwnd=int(main_hwnd or 0)
        dialog_hwnd=int(dialog_hwnd or 0)
        pressed=[];rounds=0
        while rounds<max_rounds:
            # 有明确主窗口时只认这个进程的弹窗，绝不扫描/点击别的程序
            info=_modal_of(main_hwnd or dialog_hwnd) if (main_hwnd or dialog_hwnd) else _scan_modal_anywhere()
            # 连续重入：关掉一个后可能立刻再弹一个，给一个很短的窗口期再判定“清完了”
            if (not info or not info.get('dialog')) and pressed and reentry_wait>0:
                deadline=time.monotonic()+min(max(float(reentry_wait),0),1.0)
                while time.monotonic()<deadline:
                    time.sleep(.04)
                    info=(_modal_of(main_hwnd or dialog_hwnd) if (main_hwnd or dialog_hwnd)
                          else _scan_modal_anywhere())
                    if info and info.get('dialog'):
                        break
            dialog=int((info or {}).get('dialog') or 0)
            if not dialog:
                break
            if dialog_hwnd and dialog!=dialog_hwnd:
                dialog_hwnd=0                       # 第一个目标已处理，后续按当前重入弹窗走
            rounds+=1
            button=_pick_button(dialog,button_text)
            title=str(win32gui.GetWindowText(dialog) or dialog)
            if not button:
                raise ModalBlocked('弹窗「%s」里没有可点的确认按钮'%(title[:60]),
                    dict(main=main_hwnd,dialog=dialog,rounds=rounds,buttons=_buttons_of(dialog)))
            _gate(main_hwnd or dialog)              # 点之前也查暂停；暂停就一个事件都不发
            ctrl_id=int(win32gui.GetDlgCtrlID(button) or 0)
            # WM_COMMAND: wParam=MAKELONG(控件ID, BN_CLICKED=0)，lParam=按钮句柄
            posted=bool(user.PostMessageW(dialog,_WM_COMMAND,ctrl_id,button))
            pressed.append(dict(dialog=dialog,button=button,control_id=ctrl_id,
                text=str(win32gui.GetWindowText(button) or '')[:60],title=title[:80],posted=posted))
            if not _wait_dialog_closed(dialog,cancel,1.4):
                raise ModalBlocked('弹窗「%s」点了「%s」仍未关闭'%(title[:60],pressed[-1]['text']),
                    dict(main=main_hwnd,dialog=dialog,rounds=rounds,pressed=pressed))
            if int((info or {}).get('main') or 0):
                main_hwnd=int((info or {}).get('main') or main_hwnd)
        else:
            raise ModalBlocked('模态弹窗连续重入超过 %d 轮，先交还人工处理'%max_rounds,
                dict(main=main_hwnd,dialog=dialog_hwnd,rounds=rounds,pressed=pressed))
        if not pressed:
            info=_modal_of(main_hwnd) if main_hwnd else _scan_modal_anywhere()
            if info and info.get('dialog'):
                raise ModalBlocked('检测到模态弹窗但没能处理',
                    dict(main=main_hwnd,dialog=int(info.get('dialog') or 0),buttons=[]))
        enabled=_wait_main_enabled(main_hwnd,cancel,.8) if main_hwnd else True
        if not enabled:
            raise ModalBlocked('弹窗已关闭但主窗口仍未恢复可用（可能还有隐藏模态）',
                dict(main=main_hwnd,rounds=rounds,pressed=pressed))
        return dict(ok=True,action='dialog_dismiss',input_sent=True,verified=True,
            method='WM_COMMAND(BN_CLICKED)',rounds=rounds,main_hwnd=main_hwnd,
            main_enabled=True,pressed=pressed,
            message='已点掉 %d 个模态弹窗并复验主窗口恢复可用；继续前先重新 observe'%len(pressed))

    def _perceive_action(self,action,args,cancel):
        """统一无 API 界面感知：UIA 元素优先，OCR/视觉只做兜底。"""
        import json
        import win32gui
        import win32process
        started=time.perf_counter()
        hwnd=_coerce_hwnd(args,self.observation) or int(win32gui.GetForegroundWindow() or 0)
        if not hwnd or not win32gui.IsWindow(hwnd):raise ValueError('窗口不存在，先 computer(action=windows) 查找')
        timings={}
        import re
        def key(value):return re.sub(r'\W','',str(value or '')).casefold()
        if action=='dialog':
            # 主路径：主窗口被禁用 + 同进程 #32770 且 owner 指向主窗口；
            # hwnd 缺省时兜底扫“owner 被禁用”的可见弹窗，不再只认前台窗口。
            info=_modal_of(hwnd)
            if info is None:
                info=_scan_modal_anywhere()
            target=int((info or {}).get('dialog') or 0)
            main_hwnd=int((info or {}).get('main') or 0)
            if not target:
                return dict(dialog=False,hint='当前没有检测到标准对话框；若用户说屏幕上弹了确认框，先 computer(action=observe) 看画面再判断',elapsed_ms=int((time.perf_counter()-started)*1000))
            uia_started=time.perf_counter()
            try:snapshot=self._uia().snapshot(target,60)
            except Exception as exc:snapshot={};timings['uia_error']=type(exc).__name__
            timings['uia_ms']=int((time.perf_counter()-uia_started)*1000)
            elements=snapshot.get('elements',[])
            options=[]
            for item in elements:
                kind=key(item.get('type'))
                if not any(word in kind for word in ('button','radiobutton','checkbox','listitem','menuitem','combobox','hyperlink')):
                    continue
                if item.get('offscreen'):continue
                options.append(dict(ref=item.get('ref'),name=str(item.get('name') or '')[:160],
                    type=item.get('type'),enabled=bool(item.get('enabled',True))))
            texts=[]
            for item in elements:
                name=str(item.get('name') or '').strip()
                if name and name not in [option['name'] for option in options] and name not in texts:texts.append(name[:160])
                if len(texts)>=12:break
            result=dict(dialog=True,hwnd=target,main_hwnd=main_hwnd,
                main_enabled=bool(win32gui.IsWindowEnabled(main_hwnd)) if win32gui.IsWindow(main_hwnd) else None,
                title=win32gui.GetWindowText(target),
                class_name=win32gui.GetClassName(target),buttons=_buttons_of(target),
                options=options,texts=texts,
                uia=bool(options),hint='选项交给模型按语义选择；用 computer(action=uia, hwnd=弹窗, uia_name) 点按钮（走 WM_COMMAND，不抢前台），随后 verify 确认弹窗已关闭')
            if not options:
                ocr_started=time.perf_counter()
                try:
                    frame,_=self._grab(target)
                    ocr=self._ocr_words(frame);result['ocr_text']=ocr['text'][:1000];result['words']=ocr['words'][:60]
                except Exception as exc:result['ocr_error']=type(exc).__name__
                timings['ocr_ms']=int((time.perf_counter()-ocr_started)*1000)
                result['hint']='UIA 未枚举到按钮，只能依据 ocr_text/画面；选项无法确定时先向用户确认，禁止随机点'
            result['timings']=timings;result['elapsed_ms']=int((time.perf_counter()-started)*1000)
            return result
        if action=='ocr':
            grab_started=time.perf_counter();frame,rect=self._grab(hwnd)
            timings['grab_ms']=int((time.perf_counter()-grab_started)*1000)
            region=args.get('region') if isinstance(args.get('region'),dict) else None
            ocr_started=time.perf_counter();ocr=self._ocr_crop(frame,region)
            timings['ocr_ms']=int((time.perf_counter()-ocr_started)*1000)
            return dict(hwnd=hwnd,title=win32gui.GetWindowText(hwnd),image_size=frame.size,
                region=region,text=ocr['text'],words=ocr['words'][:120],
                coordinates='words的x/y/w/h都是相对整张截图0..1；可直接用coordinate_space=ratio输入；小字号先传region裁剪',
                timings=timings,elapsed_ms=int((time.perf_counter()-started)*1000))
        if action=='locate':
            query=str(args.get('query_text') or args.get('query') or '').strip()
            if not query:raise ValueError('locate 需要 query_text')
            uia_started=time.perf_counter();elements=[]
            chromium=win32gui.GetClassName(hwnd) in ('Chrome_WidgetWin_0','Chrome_WidgetWin_1')
            # Chromium/Electron 的元素树基本是无名 Pane；扫一次要 2s+，直接把 UIA 让给 OCR/视觉。
            if chromium and not args.get('force_uia'):
                timings['uia_skipped']='chromium surface; OCR/vision preferred'
            elif self._uia_weak.get(hwnd,0)>time.monotonic():
                timings['uia_skipped']='recent snapshot had no named controls'
            else:
                try:
                    snapshot=self._uia().snapshot(hwnd,int(args.get('limit',160)))
                    elements=snapshot.get('elements',[])
                    if not any(item.get('name') for item in elements):self._uia_weak[hwnd]=time.monotonic()+20
                except Exception as exc:timings['uia_error']=type(exc).__name__
            timings['uia_ms']=int((time.perf_counter()-uia_started)*1000)
            matches=[item for item in elements if not item.get('offscreen') and key(query) in key(item.get('name'))]
            exact=[item for item in matches if key(item.get('name'))==key(query)]
            picked=(exact or matches)
            if picked:
                item=picked[0];rect=item.get('rect') or {}
                left,top,right,bottom=(float(rect.get(k,0)) for k in ('left','top','right','bottom'))
                win_left,win_top,win_right,win_bottom=win32gui.GetWindowRect(hwnd)
                ratio=None
                if right>left and bottom>top and win_right>win_left and win_bottom>win_top:
                    ratio=dict(x=round((((left+right)/2)-win_left)/(win_right-win_left),4),
                               y=round((((top+bottom)/2)-win_top)/(win_bottom-win_top),4))
                return dict(found=True,source='uia',query=query,ratio=ratio,
                    control=dict(ref=item.get('ref'),name=item.get('name'),type=item.get('type'),
                        enabled=item.get('enabled'),patterns=item.get('patterns')),
                    hint='source=uia：优先用 uia_ref 执行，不点像素。ratio给出全屏比例，仅作视觉兜底。',
                    timings=timings,elapsed_ms=int((time.perf_counter()-started)*1000))
            ocr_started=time.perf_counter()
            region=args.get('region') if isinstance(args.get('region'),dict) else None
            try:
                frame,_=self._grab(hwnd);ocr=self._ocr_crop(frame,region)
                hits=[word for word in ocr['words'] if key(query) in key(word['text'])]
                timings['ocr_ms']=int((time.perf_counter()-ocr_started)*1000)
                if hits:
                    left=min(word['x'] for word in hits);top=min(word['y'] for word in hits)
                    right=max(word['x']+word['w'] for word in hits);bottom=max(word['y']+word['h'] for word in hits)
                    return dict(found=True,source='ocr',query=query,
                        point=dict(x=round((left+right)/2,4),y=round((top+bottom)/2,4)),
                        bbox=dict(x=left,y=top,w=round(right-left,4),h=round(bottom-top,4)),
                        image_size=frame.size,
                        hint='source=ocr：先observe拿observation_id，再按ratio换算x/y（ratio×image_size）或传coordinate_space=ratio；点击后必须verify',
                        timings=timings,elapsed_ms=int((time.perf_counter()-started)*1000))
            except Exception as exc:timings['ocr_error']=type(exc).__name__
            vision_started=time.perf_counter()
            try:
                from core.ai_chat import AIChatEngine
                from core.bg_live import _vision_json
                frame,_=self._grab(hwnd)
                reply=_vision_json(frame,'在窗口截图中找到文字“'+query+'”。只返回JSON：'
                    '{"found":true/false,"x":0到1的小数,"y":0到1的小数,"label":"看到的文字"}。'
                    'x/y是目标中心相对整张截图的比例坐标；找不到就found=false，不要猜。',
                    AIChatEngine._load_config(),300)
                if reply.get('found') and 0<=float(reply.get('x',-1))<=1 and 0<=float(reply.get('y',-1))<=1:
                    return dict(found=True,source='vision',query=query,
                        point=dict(x=round(float(reply['x']),4),y=round(float(reply['y']),4)),
                        label=str(reply.get('label') or '')[:120],
                        hint='source=vision：视觉估计，低置信；先observe再按比例点击，点击后必须verify，必要时向用户确认',
                        timings=timings,elapsed_ms=int((time.perf_counter()-started)*1000))
            except Exception as exc:timings['vision_error']=type(exc).__name__[:120]
            timings['vision_ms']=int((time.perf_counter()-vision_started)*1000)
            return dict(found=False,source='none',query=query,
                hint='UIA/OCR/视觉都没定位到；不要猜坐标，先observe看画面或向用户确认',
                timings=timings,elapsed_ms=int((time.perf_counter()-started)*1000))
        if action=='verify':
            baseline=str(args.get('baseline') or '')
            if not baseline and self.observation and int(self.observation.get('hwnd') or 0)==hwnd:
                baseline=self.observation.get('baseline') or ''
            expect=str(args.get('expect_text') or '')
            wait_ms=min(max(int(args.get('wait_ms',900)),200),4000)
            deadline=time.monotonic()+wait_ms/1000;changed=0.0;frame=None
            while True:
                frame,rect=self._grab(hwnd)
                if baseline:
                    try:changed=max(changed,self._diff_ratio(frame,baseline))
                    except ValueError:baseline=''
                if changed>=.004 or time.monotonic()>=deadline:break
                if cancel.wait(.08):raise RuntimeError('验证已取消')
            verify_started=time.perf_counter();text_hit=None
            region=args.get('region') if isinstance(args.get('region'),dict) else None
            if expect:
                try:text_hit=key(expect)[:8] in key(self._ocr_crop(frame,region)['text'])
                except Exception as exc:timings['ocr_error']=type(exc).__name__
            timings['ocr_ms']=int((time.perf_counter()-verify_started)*1000)
            closed=None
            if args.get('expect_closed'):closed=not win32gui.IsWindowVisible(hwnd)
            verified=bool(changed>=.004 or text_hit or closed)
            return dict(verified=verified,changed_ratio=round(changed,4),text_found=text_hit,
                dialog_closed=closed,image_size=frame.size,region=region,
                hint=('已检测到画面变化；再核对具体文字/控件内容' if verified else
                      '没有检测到变化；不要重复输入，先observe确认是焦点变化还是未生效，失败则改道'),
                timings=timings,elapsed_ms=int((time.perf_counter()-started)*1000))
        raise ValueError('未知感知操作')

    def _verify_change(self,hwnd,baseline,cancel,wait_ms=600,expect_text='',expect_closed=False,region=None):
        """动作后回读证据：画面差异 / OCR文字 / 窗口关闭；轮询，不靠固定 sleep。"""
        import win32gui
        baseline=str(baseline or '');expect=str(expect_text or '')
        wait_ms=min(max(int(wait_ms),150),2000)
        started=time.perf_counter();deadline=time.monotonic()+wait_ms/1000
        changed=0.0;frame=None;polls=0;grab_ms=0;closed=False
        import re
        def fold(value):return re.sub(r'\W','',str(value or '')).casefold()
        while True:
            try:
                if expect_closed and (not win32gui.IsWindow(hwnd) or not win32gui.IsWindowVisible(hwnd)):
                    closed=True;break
                at=time.perf_counter();frame,_=self._grab(hwnd)
                grab_ms+=int((time.perf_counter()-at)*1000);polls+=1
            except Exception:
                closed=True;break
            if baseline:
                try:changed=max(changed,self._diff_ratio(frame,baseline))
                except ValueError:baseline=''
            if changed>=.004 or time.monotonic()>=deadline:break
            if cancel.wait(.08):raise RuntimeError('验证已取消')
        text_hit=None;ocr_ms=None
        if expect and frame is not None:
            at=time.perf_counter()
            try:text_hit=fold(expect)[:8] in fold(self._ocr_crop(frame,region)['text'])
            except Exception:pass
            ocr_ms=int((time.perf_counter()-at)*1000)
        verified=bool(closed or changed>=.004 or text_hit)
        return dict(verified=verified,changed_ratio=round(changed,4),dialog_closed=closed,
            expect_text=expect or None,text_found=text_hit,
            timings=dict(polls=polls,grab_ms=grab_ms,ocr_ms=ocr_ms,
                total_ms=int((time.perf_counter()-started)*1000)),
            hint=('已回读到变化；继续核对具体文字/控件内容' if verified else
                '画面暂未变化；不要原样重复输入，先 observe 核对焦点和实际内容，仍失败就改道'))

    def _screen_size(self):
        import win32api
        return int(win32api.GetSystemMetrics(0)),int(win32api.GetSystemMetrics(1))

    def execute(self,args,cancel=None):
        # Match screenshot and input coordinates on mixed-DPI monitors without
        # changing Qt's UI-thread coordinate system.
        user=ctypes.windll.user32
        setter=getattr(user,'SetThreadDpiAwarenessContext',None)
        previous=None
        if setter:
            setter.restype=ctypes.c_void_p;setter.argtypes=[ctypes.c_void_p]
            previous=setter(ctypes.c_void_p(-4))
        try:return self._execute(args,cancel)
        finally:
            if setter and previous:setter(previous)

    def _execute(self,args,cancel=None):
        if not self.access.enabled:raise ValueError('屏幕与输入需要开启完整访问')
        cancel=cancel or threading.Event()
        if cancel.is_set():raise RuntimeError('已停止屏幕操作')
        import win32gui
        action=args.get('action')
        if action in ('screenshot','snapshot','capture','see'):
            action='observe'                     # 常见口语写法，统一当成观察
            args['action']='observe'             # 账本也要按观察来记账
        if action=='uia' and not any(args.get(k) for k in ('uia_name','uia_id','uia_type','uia_ref')) \
                and str(args.get('query_text') or '').strip():
            # 模型常把“按文字找控件”写成 uia+query_text；这本来就是 locate 的语义。
            # 必须改掉 action，否则账本会把这次只读查找当成“已输入”。
            args['action']='locate'
            return self._perceive_action('locate',args,cancel)
        if action=='editor_context':
            import json,os
            from pathlib import Path
            from urllib.parse import urlparse,unquote
            query=str(args.get('query','')).replace(' ','').casefold()
            entries=[]
            for product in ('Trae CN','Trae','Code','Cursor','Code - Insiders'):
                folder=Path(os.getenv('APPDATA',''))/product/'User/workspaceStorage'
                if not folder.is_dir():continue
                files=sorted(folder.glob('*/workspace.json'),key=lambda p:p.stat().st_mtime,reverse=True)[:80]
                for path in files:
                    try:
                        data=json.loads(path.read_text(encoding='utf-8-sig'))
                        uri=data.get('folder') or data.get('workspace','')
                        parsed=urlparse(uri)
                        if parsed.scheme!='file':continue
                        target=unquote(parsed.path).lstrip('/')
                        if query and query not in target.replace(' ','').casefold():continue
                        entries.append(dict(editor=product,path=target,exists=Path(target).exists(),source='workspace.json',updated=path.stat().st_mtime))
                    except (OSError,ValueError,TypeError):continue
            return dict(workspaces=sorted(entries,key=lambda e:e['updated'],reverse=True)[:30],
                note='编辑器最近工作区元数据；结合窗口标题核对，不能只凭最近记录判断当前文件。')
        if action=='windows':
            from core.window_inventory import list_windows
            return dict(windows=list_windows(args.get('query','')),
                note='这是已经运行的窗口，包含最小化窗口；按进程和标题共同识别。选定后focus恢复，再observe/accessibility。')
        if action=='foreground':
            hwnd=int(args.get('hwnd') or 0)
            current=int(win32gui.GetForegroundWindow() or 0)
            return dict(foreground=current,is_target=bool(hwnd) and current==hwnd,
                title=win32gui.GetWindowText(current) if current else '')
        if action=='focus':
            hwnd=_coerce_hwnd(args,self.observation)
            if not hwnd:hwnd=int(win32gui.GetForegroundWindow() or 0)
            if not hwnd:raise ValueError('focus 缺少 hwnd：先 computer(action=windows) 列出窗口，把目标窗口的 hwnd 传进来')
            modal=_modal_blocks(hwnd)
            if modal and modal.get('dialog'):
                raise ModalBlocked('目标窗口正被模态弹窗「%s」挡住，先点掉弹窗再聚焦'%
                    (win32gui.GetWindowText(modal['dialog']) or modal['dialog'])[:60],modal)
            if not win32gui.IsWindow(hwnd):raise ValueError('窗口已关闭，请重新列出')
            if not _ensure_foreground(hwnd,.8):
                raise RuntimeError('Windows未允许切换到目标窗口；尚未发送输入，请检查窗口状态或请用户聚焦目标窗口')
            self.observation=None
            return dict(focused=True,needs_observe=True)
        if action=='observe':
            started=time.perf_counter()
            # 前台常是咕嘎自己的对话窗，不能默认当成任务目标；先按显式 hwnd/标题，
            # 再退回最近观察过的窗口，最后才用前台。
            hwnd=_coerce_hwnd(args,self.observation)
            own=str(win32gui.GetWindowText(hwnd) or '') if hwnd else ''
            if not hwnd:
                hwnd=int(win32gui.GetForegroundWindow())
                own=str(win32gui.GetWindowText(hwnd) or '')
            if '咕嘎' in own:
                # 抓到自己是定位错了，不是“目标不成立”。目标是软件时按名字找窗口，
                # 找到就聚焦后继续观察，绝不在这里收工。
                hint=str(args.get('query') or args.get('target')
                         or getattr(self,'target_hint','') or '').strip()
                if hint:
                    from core.window_inventory import list_windows
                    for row in list_windows(hint):
                        target=int(row.get('hwnd') or 0)
                        if not target or '咕嘎' in str(row.get('title') or ''):
                            continue
                        if _ensure_foreground(target,.6):
                            hwnd=target
                            break
                if '咕嘎' in str(win32gui.GetWindowText(hwnd) or ''):
                    raise ValueError('当前前台是咕嘎自己的窗口，不能当成任务目标；'
                                     '目标是哪个软件就 computer(action=focus, query=软件名) 定位它，再 observe')
            if hwnd!=win32gui.GetForegroundWindow():
                if not _ensure_foreground(hwnd,.5):
                    raise ValueError('先 focus 目标窗口再观察，避免遮挡误认')
            grab_started=time.perf_counter()
            frame,rect=self._grab(hwnd)
            grab_ms=int((time.perf_counter()-grab_started)*1000)
            frame.thumbnail((1600,1200))
            baseline=self._fingerprint(frame)
            output=io.BytesIO();frame.save(output,format='JPEG',quality=78)
            token=uuid.uuid4().hex
            self.observation=dict(id=token,hwnd=hwnd,rect=rect,image_size=frame.size,
                time=time.monotonic(),baseline=baseline)
            return dict(observation_id=token,hwnd=hwnd,title=win32gui.GetWindowText(hwnd),
                desktop_rect=rect,image_size=frame.size,
                coordinates='默认传截图内的相对像素坐标，与image_size一致；也可传coordinate_space=ratio（0..1）完全避开分辨率/DPI。仅明确有桌面物理坐标时用desktop。',
                timings=dict(grab_ms=grab_ms,encode_ms=int((time.perf_counter()-grab_started)*1000)-grab_ms,
                    total_ms=int((time.perf_counter()-started)*1000)),
                _image_url='data:image/jpeg;base64,'+base64.b64encode(output.getvalue()).decode())
        if action=='accessibility':
            hwnd=_coerce_hwnd(args,self.observation) or int(win32gui.GetForegroundWindow())
            if not win32gui.IsWindow(hwnd):raise ValueError('窗口已关闭')
            from core.uia_backend import UIAUnavailable
            try:return self._uia().snapshot(hwnd,args.get('limit',240))
            except Exception:pass   # UIA 超时/不可用（Electron 常见）时退回 PowerShell 枚举，别让纯文本模型无控件可依
            script='''Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$rootElement=[System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]HWND_VALUE)
$nodes=$rootElement.FindAll([System.Windows.Automation.TreeScope]::Descendants,[System.Windows.Automation.Condition]::TrueCondition)
$items=for($i=0;$i -lt [Math]::Min($nodes.Count,150);$i++) {
  try {$c=$nodes.Item($i).Current; if($c.Name -or $c.AutomationId) {
    [pscustomobject]@{name=$c.Name;id=$c.AutomationId;type=$c.ControlType.ProgrammaticName;enabled=$c.IsEnabled;bounds=$c.BoundingRectangle.ToString()}
  }} catch {}
}
ConvertTo-Json -InputObject @($items) -Compress -Depth 3'''.replace('HWND_VALUE',str(hwnd))
            from core.desktop_access import ROOT
            output=self.access.run(script,str(ROOT),6,cancel)
            if output.get('exit_code')==0:
                import json
                try:items=json.loads(output.get('stdout') or '[]')
                except ValueError:items=None
                if isinstance(items,dict):items=[items]
                if isinstance(items,list):
                    return dict(hwnd=hwnd,elements=items[:150],
                        hint='优先按 name/id/type 调用 computer(action=uia)，操作后重新读取验证')
            return output
        if action=='uia':
            hwnd=_coerce_hwnd(args,self.observation) or int(win32gui.GetForegroundWindow())
            if not win32gui.IsWindow(hwnd):raise ValueError('窗口已关闭')
            name=str(args.get('uia_name',''))[:200]
            automation_id=str(args.get('uia_id',''))[:200]
            control_type=str(args.get('uia_type',''))[:80]
            value=str(args.get('uia_value',''))
            operation=str(args.get('uia_operation',''))
            if not any((name,automation_id,control_type,args.get('uia_ref'))) or operation not in ('invoke','set_value','focus','click'):
                raise ValueError('uia 需要 ref/Name/AutomationId/ControlType 之一，以及合法操作')
            # 弹窗按钮优先走 WM_COMMAND：不抢前台，实测比 UIA/BM_CLICK 都稳
            modal=_modal_of(hwnd)
            if modal and modal.get('dialog') and operation in ('invoke','click'):
                dialog=int(modal['dialog'])
                if name and _pick_button(dialog,name):
                    return self._press_modal(int(modal.get('main') or 0),dialog,
                        button_text=name,cancel=cancel)
                if win32gui.GetClassName(hwnd)!=DIALOG_CLASS:
                    raise ModalBlocked('目标窗口正被模态弹窗「%s」挡住，本轮未发送控件操作'%
                        (win32gui.GetWindowText(dialog) or dialog)[:60],
                        dict(main=hwnd,dialog=dialog,buttons=_buttons_of(dialog)))
            elif _root(win32gui.GetForegroundWindow())!=_root(hwnd) and not _ensure_foreground(hwnd,.5):
                raise ValueError('先 focus 目标窗口再执行控件操作')
            if args.get('verify',True) and operation in ('invoke','click'):
                try:verify_baseline=self._fingerprint(self._grab(hwnd)[0])
                except Exception:verify_baseline=None
            try:
                result=self._uia().act(hwnd,operation,ref=args.get('uia_ref'),name=name,
                    automation_id=automation_id,control_type=control_type,value=value)
                if result.pop('fallback',False):
                    rect=result.pop('rect',None)
                    if not rect:raise RuntimeError('UIA控件没有可点击区域')
                    _gate(hwnd)
                    user.SetCursorPos(int((rect['left']+rect['right'])/2),int((rect['top']+rect['bottom'])/2))
                    user.mouse_event(2,0,0,0,0);user.mouse_event(4,0,0,0,0)
                    result['method']='MouseFallback';result['input_sent']=True
                else:result.pop('rect',None)
                self.observation=None
                if verify_baseline is not None:
                    result['verification']=self._verify_change(hwnd,verify_baseline,cancel,
                        args.get('verify_wait_ms',600),str(args.get('expect_text','')),bool(args.get('expect_closed')))
                return result
            except ValueError:raise
            except Exception as backend_error:
                if '进程内 UIAutomation 不可用' not in str(backend_error):raise
            def pstr(value):return "'"+value.replace("'","''")+"'"
            if len(value)>4000:raise ValueError('uia_value 最多4000字')
            script='''Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$root=[System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]HWND_VALUE)
$nodes=$root.FindAll([System.Windows.Automation.TreeScope]::Descendants,[System.Windows.Automation.Condition]::TrueCondition)
$target=$null;$match=@{};$name=NAME_VALUE;$id=ID_VALUE;$type=TYPE_VALUE
for($i=0;$i -lt $nodes.Count;$i++){try{$c=$nodes.Item($i).Current
  if(($name -eq '' -or $c.Name -eq $name) -and ($id -eq '' -or $c.AutomationId -eq $id) -and ($type -eq '' -or $c.ControlType.ProgrammaticName -eq ('ControlType.'+$type))){$target=$nodes.Item($i);break}}catch{}}
if($null -eq $target){throw 'UIA target not found'}
$c=$target.Current;$performed=$false;$method=''
if(OPERATION_VALUE -eq 'invoke'){
  $p=$null;if($target.TryGetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern,[ref]$p)){$p.Invoke();$performed=$true;$method='InvokePattern'}
  elseif($target.TryGetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern,[ref]$p)){$p.Select();$performed=$true;$method='SelectionItemPattern'}
}elseif(OPERATION_VALUE -eq 'set_value'){
  $p=$null;if($target.TryGetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern,[ref]$p)){$p.SetValue(VALUE_VALUE);$performed=$true;$method='ValuePattern'}
}elseif(OPERATION_VALUE -eq 'focus'){
  $target.SetFocus();$performed=$true;$method='SetFocus'
}
$r=$c.BoundingRectangle
[pscustomobject]@{name=$c.Name;id=$c.AutomationId;type=$c.ControlType.ProgrammaticName;enabled=$c.IsEnabled;
  left=$r.Left;top=$r.Top;right=$r.Right;bottom=$r.Bottom;performed=$performed;method=$method} | ConvertTo-Json -Compress'''
            script=script.replace('HWND_VALUE',str(hwnd)).replace('NAME_VALUE',pstr(name)).replace('ID_VALUE',pstr(automation_id))
            script=script.replace('TYPE_VALUE',pstr(control_type)).replace('OPERATION_VALUE',pstr(operation)).replace('VALUE_VALUE',pstr(value))
            from core.desktop_access import ROOT
            output=self.access.run(script,str(ROOT),8,cancel)
            if output.get('exit_code')!=0:raise RuntimeError((output.get('stderr') or 'UIA控件操作失败').strip()[:300])
            import json
            try:result=json.loads(output.get('stdout') or '{}')
            except ValueError:raise RuntimeError('UIA返回格式无效；未发送鼠标输入') from None
            if not result.get('enabled',False):raise RuntimeError('UIA目标控件不可用')
            method=str(result.get('method',''))
            if operation=='click' or not result.get('performed'):
                left,top,right,bottom=(float(result.get(k,0)) for k in ('left','top','right','bottom'))
                if right<=left or bottom<=top:raise RuntimeError('UIA目标没有可点击区域')
                _gate(hwnd)
                user.SetCursorPos(int((left+right)/2),int((top+bottom)/2))
                user.mouse_event(2,0,0,0,0);user.mouse_event(4,0,0,0,0)
                method='MouseFallback'
            self.observation=None
            return dict(input_sent=True,action='uia',needs_observe=True,method=method,
                control=dict(name=result.get('name'),id=result.get('id'),type=result.get('type')),
                message='UIA操作已执行；仍需 accessibility 或 observe 验证结果')
        if action=='uia_read':
            hwnd=int(args.get('hwnd') or win32gui.GetForegroundWindow())
            return self._uia().read(hwnd,ref=args.get('uia_ref'),name=args.get('uia_name',''),
                automation_id=args.get('uia_id',''),control_type=args.get('uia_type',''))
        if action=='uia_wait':
            hwnd=_coerce_hwnd(args,self.observation) or int(win32gui.GetForegroundWindow())
            if not win32gui.IsWindow(hwnd):raise ValueError('窗口已关闭')
            name=str(args.get('uia_name',''))[:200];automation_id=str(args.get('uia_id',''))[:200]
            control_type=str(args.get('uia_type',''))[:80];ref=args.get('uia_ref')
            if not any((name,automation_id,control_type,ref)):raise ValueError('uia_wait 需要控件条件')
            state=str(args.get('uia_state') or args.get('uia_wait') or 'exists')
            if state not in ('exists','enabled','offscreen'):raise ValueError('未知等待状态')
            return self._uia().wait(hwnd,args.get('uia_timeout_ms',5000)/1000,ref=ref,name=name,
                automation_id=automation_id,control_type=control_type,state=state,
                expected=args.get('uia_expected',True))
        if action in ('dialog','ocr','locate','verify'):
            return self._perceive_action(action,args,cancel)
        observed=self.observation
        # 只校验“最近一次观察是否还新鲜”，不再比对模型回传的 ID：
        # 模型经常复用上一轮的旧 ID，一个字符不差却永远对不上，导致动作全部空转。
        # 窗口/前台/位置在下一步仍会复核，30 秒窗口也会兜底。
        if not observed or time.monotonic()-observed['time']>30:
            raise ValueError('观察 ID 已消耗或过期；先 observe 取得新 ID。若刚点击过输入框，只需用新 ID 执行 type，不要再次点击；也可一次 fill 完成定位与输入')
        if _root(win32gui.GetForegroundWindow())!=_root(observed['hwnd']):
            if not _ensure_foreground(observed['hwnd'],.45) or win32gui.GetWindowRect(observed['hwnd'])!=observed['rect']:
                self.observation=None
                raise ValueError('前台窗口或位置已改变，先重新观察')
        # 输入动作前的模态预检：主窗口被弹窗挡住时一个事件都不发，直接交还人工清弹窗
        modal=_modal_blocks(observed['hwnd'])
        if modal and modal.get('dialog'):
            raise ModalBlocked('目标窗口正被模态弹窗「%s」挡住，本轮未发送任何键鼠事件'%
                (win32gui.GetWindowText(modal['dialog']) or modal['dialog'])[:60],modal)
        # 点击后不清观察：模型自然流程是 observe → click → type，
        # 清掉会让紧接着的 type 报“观察 ID 已过期”，只能再 observe，陷入死循环。
        # 前台/位置变化已在上方拦截，过期仍由 30 秒窗口兜底。
        observed['time']=time.monotonic()
        def finish(result):
            # Every input action returns the picture evidence the model needs to
            # decide whether the step actually worked; the action is never
            # reported as success just because keys were sent.
            if args.get('verify',True) and observed.get('baseline'):
                try:
                    result['verification']=self._verify_change(observed['hwnd'],observed.get('baseline'),cancel,
                        args.get('verify_wait_ms',600),str(args.get('expect_text','')),bool(args.get('expect_closed')),
                        args.get('region') if isinstance(args.get('region'),dict) else None)
                except RuntimeError:raise
                except Exception as exc:result['verification']=dict(verified=None,error=type(exc).__name__)
                if result['verification'].get('verified') is False:
                    result['message']='输入已发送，但画面暂未检测到变化；不要重复输入，先 observe 核对焦点和实际内容，必要时改道'
            return result
        def mapped(x,y):
            left,top,right,bottom=observed['rect']
            space=args.get('coordinate_space','screenshot')
            if space=='ratio':
                if not 0<=float(x)<=1 or not 0<=float(y)<=1:raise ValueError('ratio 坐标必须在0..1之间')
                x=left+float(x)*(right-left);y=top+float(y)*(bottom-top)
            elif space=='screenshot':
                width,height=observed.get('image_size',(right-left,bottom-top))
                if not 0<=x<width or not 0<=y<height:raise ValueError('坐标超出截图范围')
                x=left+x*(right-left)/width;y=top+y*(bottom-top)/height
            x,y=int(x),int(y)
            if not left<=x<right or not top<=y<bottom:raise ValueError('输入坐标超出刚才观察的窗口')
            return x,y
        def position(x,y):
            x,y=mapped(x,y)
            _gate(observed['hwnd'])
            ctypes.windll.user32.SetCursorPos(x,y)
        user=_USER32_TEXT
        requested_action=action
        if action=='fill':
            # One bounded transaction: there is no model round trip between
            # selecting the field and typing, and the observation is consumed once.
            text=str(args.get('text',''))
            if not text or len(text)>4000:raise ValueError('fill 需要1—4000字的 text')
            keys=str(args.get('keys','')).lower().replace(' ','')
            has_position='x' in args or 'y' in args
            if has_position and ('x' not in args or 'y' not in args):raise ValueError('fill 坐标需要同时提供 x、y')
            if keys and has_position:raise ValueError('fill 用坐标或快捷键定位，不能同时提供')
            if keys and keys not in ('ctrl+l','alt+d','ctrl+a'):raise ValueError('fill 仅支持 ctrl+l、alt+d、ctrl+a 定位')
            if has_position:
                position(args['x'],args['y'])
                _gate(observed['hwnd'])
                user.mouse_event(2,0,0,0,0);user.mouse_event(4,0,0,0,0)
            elif keys:
                _send_keys({'ctrl+l':[17,76],'alt+d':[18,68],'ctrl+a':[17,65]}[keys])
            if cancel.is_set() or _root(win32gui.GetForegroundWindow())!=_root(observed['hwnd']):
                raise RuntimeError('输入已取消或前台窗口改变；未继续打字')
            action='type'
        if action in ('click','double_click','move','drag'):
            position(args['x'],args['y'])
            if action in ('click','double_click'):
                down,up=(8,16) if args.get('button')=='right' else (2,4)
                for _ in range(2 if action=='double_click' else 1):
                    _gate(observed['hwnd'])
                    user.mouse_event(down,0,0,0,0);user.mouse_event(up,0,0,0,0)
            elif action=='drag':
                # Validate destination before holding the button.
                end_x,end_y=mapped(args['end_x'],args['end_y'])
                start_x,start_y=mapped(args['x'],args['y'])
                _gate(observed['hwnd'])
                user.mouse_event(2,0,0,0,0)
                try:
                    for step in range(1,13):
                        if cancel.wait(.02):raise RuntimeError('拖动已取消')
                        _gate(observed['hwnd'])
                        user.SetCursorPos(int(start_x+(end_x-start_x)*step/12),int(start_y+(end_y-start_y)*step/12))
                finally:user.mouse_event(4,0,0,0,0)
        elif action=='scroll':
            delta=int(args.get('delta',-3))
            if not -20<=delta<=20:raise ValueError('滚动量需要-20到20')
            if delta==0:raise ValueError('滚动量不能是0')
            _gate(observed['hwnd'])
            for value in wheel_notches('later' if delta<0 else 'earlier', abs(delta)):
                user.mouse_event(0x800,0,0,value,0)
        elif action=='hotkey':
            keys=str(args.get('keys','')).lower().split('+')
            aliases={'return':'enter','escape':'esc','control':'ctrl','control_l':'ctrl','control_r':'ctrl',
                'ctrl_l':'ctrl','alt_l':'alt','alt_r':'alt','shift_l':'shift','shift_r':'shift','super_l':'win','deleteforward':'delete'}
            keys=[aliases.get(k.strip(),k.strip()) for k in keys]
            codes={'ctrl':17,'alt':18,'shift':16,'win':91,'enter':13,'tab':9,'esc':27,'backspace':8,'delete':46,
                'up':38,'down':40,'left':37,'right':39,'home':36,'end':35,'space':32}
            values=[codes[k] if k in codes else ord(k.upper()) if len(k)==1 and k.isascii() else 111+int(k[1:]) if k.startswith('f') and k[1:].isdigit() and 1<=int(k[1:])<=12 else 0 for k in keys]
            if not values or len(values)>5 or 0 in values:raise ValueError('不支持的组合键；请用ctrl/alt/shift、enter、tab、esc、home、end及字母，例如ctrl+g、enter、ctrl+shift+end')
            _send_keys(values)
        elif action=='editor_select_tail':
            line=int(args.get('line',0))
            if not 1<=line<=200000:raise ValueError('需要有效的编辑器行号')
            if not any(name in win32gui.GetWindowText(observed['hwnd']).lower() for name in ('trae','code','cursor')):
                raise ValueError('仅在已观察的代码编辑器窗口使用')
            def chord(values):
                if cancel.is_set() or _root(win32gui.GetForegroundWindow())!=_root(observed['hwnd']):raise RuntimeError('选区操作已取消或窗口切换')
                _send_keys(values)
                cancel.wait(.15)
            chord([27]);chord([17,71]);chord([17,65])
            for char in str(line):chord([ord(char)])
            chord([13]);chord([36]);chord([17,16,35])
            return dict(input_sent=True,selection_requested=True,line=line,needs_observe=True,message='已请求选择此行至文件末尾；先observe核对选区后再输入，不能假定选择正确')
        elif action=='type':
            text=str(args.get('text',''))
            if len(text)>4000:raise ValueError('单次输入最多4000字')
            if '\n' in text and self._paste_multiline(text,observed['hwnd'],cancel):
                return finish(dict(input_sent=True,action=action,needs_observe=True,
                    message='多行文本已粘贴；请观察缩进并验证，剪贴板已恢复'))
            # KEYEVENTF_UNICODE; preserves the user's clipboard.
            class KI(ctypes.Structure):
                _fields_=[('vk',wintypes.WORD),('scan',wintypes.WORD),('flags',wintypes.DWORD),('time',wintypes.DWORD),('extra',ctypes.c_size_t)]
            class MI(ctypes.Structure):
                _fields_=[('dx',wintypes.LONG),('dy',wintypes.LONG),('data',wintypes.DWORD),('flags',wintypes.DWORD),('time',wintypes.DWORD),('extra',ctypes.c_size_t)]
            class U(ctypes.Union):_fields_=[('ki',KI),('mi',MI)]
            class INPUT(ctypes.Structure):_fields_=[('type',wintypes.DWORD),('value',U)]
            _bind_sendinput(user,INPUT)
            # Batch keystrokes for long text; short input keeps the exact
            # per-unit behaviour (surrogate pairs are never split).
            encoded=text.encode('utf-16-le')
            scans=[int.from_bytes(encoded[i:i+2],'little') for i in range(0,len(encoded),2)]
            chunk_size=64 if len(scans)>32 else 1
            offset=0
            while offset<len(scans):
                end=min(len(scans),offset+chunk_size)
                if chunk_size>1 and end>offset+1 and end<len(scans) and 0xD800<=scans[end-1]<=0xDBFF:
                    end-=1  # keep a surrogate pair in one batch
                if cancel.is_set():raise RuntimeError('文字输入已取消')
                if win32gui.GetForegroundWindow()!=observed['hwnd']:
                    # Typing is already partial; never re-target it silently.
                    raise RuntimeError('打字期间前台窗口改变，已停止后续输入；部分文字可能已输入，请观察核对')
                packets=[]
                for scan in scans[offset:end]:
                    _gate(observed['hwnd'])      # 逐字符拦：暂停后这段一个字都不再发
                    packets.append(INPUT(1,U(ki=KI(0,scan,4,0,0))))
                    packets.append(INPUT(1,U(ki=KI(0,scan,6,0,0))))
                inputs=(INPUT*len(packets))(*packets)
                _gate(observed['hwnd'])
                if user.SendInput(len(packets),inputs,ctypes.sizeof(INPUT))!=len(packets):
                    raise RuntimeError('Windows 拒绝输入；检查实际进程权限')
                offset=end
        else:raise ValueError('未知屏幕操作')
        return finish(dict(input_sent=True,action=requested_action,needs_observe=True,
            next_action='observe',message='输入已发送；只需重新 observe 验证效果，不要重复刚才的点击或输入'))

    @staticmethod
    def _paste_multiline(text,hwnd,cancel):
        import win32clipboard as clip
        import win32con,win32gui
        saved=[]
        opened=False
        for _ in range(8):
            try:
                clip.OpenClipboard();opened=True;break
            except Exception:time.sleep(.08)
        if not opened:return False
        try:
            fmt=0
            while True:
                fmt=clip.EnumClipboardFormats(fmt)
                if not fmt:break
                try:value=clip.GetClipboardData(fmt)
                except Exception:continue          # 个别格式读不出来就跳过，不阻断粘贴
                if isinstance(value,(bytes,str)) and len(value)<=10_000_000:
                    saved.append((fmt,value))
            clip.EmptyClipboard();clip.SetClipboardData(win32con.CF_UNICODETEXT,text)
        finally:
            try:clip.CloseClipboard()
            except Exception:pass
        try:
            # 上一步软件的产物预览窗常在这里冒出来抢前台，导致“窗口已切换”；
            # 目标被抢走时把目标窗口重新抬回来再试，绝不往别的窗口里粘贴。
            for _ in range(3):
                if cancel.is_set():
                    raise RuntimeError('已取消，未粘贴')
                if win32gui.GetForegroundWindow()==hwnd:
                    break
                try:
                    win32gui.ShowWindow(hwnd,win32con.SW_RESTORE)
                    win32gui.BringWindowToTop(hwnd)
                    win32gui.SetForegroundWindow(hwnd)
                except Exception:
                    pass
                time.sleep(.35)
            if win32gui.GetForegroundWindow()!=hwnd:raise RuntimeError('窗口已切换，未粘贴')
            _send_keys([17,86])
            cancel.wait(.3)
            return True
        finally:
            reopened=False
            for _ in range(8):
                try:
                    clip.OpenClipboard();reopened=True;break
                except Exception:time.sleep(.08)
            if reopened:
                try:
                    if clip.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT) and clip.GetClipboardData(win32con.CF_UNICODETEXT)==text:
                        clip.EmptyClipboard()
                        for fmt,value in saved:
                            try:clip.SetClipboardData(fmt,value)
                            except Exception:pass
                finally:
                    try:clip.CloseClipboard()
                    except Exception:pass
