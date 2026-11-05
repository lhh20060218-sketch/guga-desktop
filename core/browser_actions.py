"""Close precisely one selected browser tab, with identity-based verification."""
import hashlib
import time


def _failure(code,error,**values):
    return dict(ok=False,code=code,error=error,action_sent=values.pop('action_sent',False),**values)


def select_window(windows):
    foreground=[w for w in windows if w.get('foreground')]
    if len(foreground)==1:return foreground[0]
    return None


class BrowserTabs:
    def __init__(self):
        from core.uia_backend import UIABackend
        self.backend=UIABackend()
        from System.Windows.Automation import ControlType,PropertyCondition
        self.condition=PropertyCondition(self.backend.AutomationElement.ControlTypeProperty,ControlType.TabItem)

    def snapshot(self,hwnd):
        b=self.backend;root=b._root(hwnd)
        tabs=root.FindAll(b.TreeScope.Descendants,self.condition)
        if tabs.Count>200:raise RuntimeError('标签超过200个，本次没有发送关闭操作')
        result=[]
        for tab in tabs:
            if tab.Current.IsOffscreen:continue
            pattern=tab.GetCurrentPattern(b.Patterns['select'].Pattern)
            result.append(dict(id=hashlib.sha256(str(list(tab.GetRuntimeId())).encode()).hexdigest()[:20],
                               selected=bool(pattern.Current.IsSelected)))
        return result


def close_current_tab():
    import win32gui
    from core.window_inventory import list_windows
    from core.computer_control import ComputerControl,_send_keys,_attach_focus
    from core.desktop_access import DesktopAccess
    if not DesktopAccess().enabled:
        return _failure('access_disabled','完整访问未开启，尚未发送关闭操作。请在软件权限中开启完整访问')
    windows=list_windows('浏览器',200)
    window=select_window(windows)
    if not window:
        return _failure('target_ambiguous' if len(windows)>1 else 'target_not_foreground' if windows else 'target_missing',
            '当前前台没有唯一的浏览器目标；尚未发送操作。请先切到要关闭的浏览器页面' if windows else
            '没有找到浏览器窗口；尚未发送操作。请先打开或聚焦要关闭的浏览器页面',action_sent=False)
    hwnd=window['hwnd'];sent=False;stage='tab_observation'
    try:
        tabs=BrowserTabs();before=tabs.snapshot(hwnd)
        selected=[t for t in before if t['selected']]
        if len(selected)!=1:
            return _failure('tab_unavailable','无法唯一识别当前标签页；尚未发送关闭操作。请先切到目标浏览器页面')
        identity=selected[0]['id']
        stage='window_focus'
        try:ComputerControl().execute(dict(action='focus',hwnd=hwnd))
        except RuntimeError:
            # SetForegroundWindow may silently do nothing rather than raising.
            if not _attach_focus(hwnd):raise
        # Re-read after focus: the user may have changed tabs while we observed.
        stage='target_recheck';current=tabs.snapshot(hwnd)
        if [t['id'] for t in current if t['selected']]!=[identity] or win32gui.GetForegroundWindow()!=hwnd:
            return _failure('target_changed','观察后目标或焦点发生变化；尚未发送关闭操作。请重新指定当前页面')
        stage='close_input';sent=True;_send_keys([0x11,0x57])
        stage='close_verification'
        for _ in range(8):
            time.sleep(.15)
            if not win32gui.IsWindow(hwnd):
                return dict(ok=True,verified=True,action_sent=True,code='tab_closed',message='当前页面已关闭，浏览器窗口也已退出',evidence='target_window_gone')
            after=tabs.snapshot(hwnd)
            # Absence plus count reduction rules out a mere tab switch/title change.
            if after and identity not in {t['id'] for t in after} and len(after)==len(before)-1:
                return dict(ok=True,verified=True,action_sent=True,code='tab_closed',message='当前标签页已关闭',evidence='selected_tab_removed')
        return _failure('close_unverified','已发送一次关闭快捷键，但未核验到目标标签消失；可能有确认提示，原因尚未确定。请查看浏览器提示，不要重复关闭',action_sent=True,verification='pending')
    except Exception as exc:
        from core.desktop_access import redact
        detail=redact(str(exc)).splitlines()[0][:200] if str(exc) else type(exc).__name__
        return _failure('close_unverified' if sent else 'tab_observation_failed',
            ('已尝试一次关闭操作，但未完成核验；请查看目标页面，不要重复关闭。' if sent else
             '读取浏览器标签或获取焦点失败，尚未发送关闭操作。请先切到目标浏览器页面。')+
            '失败步骤：'+stage+'；原因：'+detail,action_sent=sent,stage=stage,exception_type=type(exc).__name__)


def bounded_close():
    """UIA lives in a disposable process; a blocked browser cannot freeze Qt."""
    import json,os,subprocess,sys
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    interpreter=Path(sys.executable).with_name('python.exe')
    if getattr(sys,'frozen',False) or not interpreter.is_file():
        return _failure('runtime_unavailable','当前运行环境没有可隔离的 Python 标签页执行器；尚未发送关闭操作')
    try:
        result=subprocess.run([str(interpreter),'-m','core.browser_actions'],cwd=str(root),
            env=dict(os.environ,PYTHONIOENCODING='utf-8'),capture_output=True,text=True,encoding='utf-8',
            timeout=7,creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode!=0:return _failure('worker_failed','标签页执行器异常退出；无法确认是否已发送操作，请检查页面后再继续',action_sent=None)
        return json.loads(result.stdout)
    except subprocess.TimeoutExpired:
        return _failure('worker_timeout','标签页执行器7秒内没有返回，已终止该执行器；无法确认是否已发送关闭操作，请查看页面，不能自动重试',action_sent=None)
    except (OSError,ValueError):
        return _failure('worker_failed','标签页执行器未返回有效回执；无法确认操作结果，请先查看目标页面',action_sent=None)


if __name__=='__main__':
    import json
    print(json.dumps(close_current_tab(),ensure_ascii=False))
