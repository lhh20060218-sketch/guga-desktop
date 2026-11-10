"""Read-only window inventory shared by software discovery and computer tools."""
import ntpath
import time

# Cross-app steps often ask for the same window list several times in a row.
# A very short cache avoids repeated psutil/EnumWindows sweeps while staying
# fresh enough for launch and focus verification.
_CACHE={'time':0.0,'windows':[]}
_CACHE_TTL=0.6

ALIASES = {
    '微信': ('weixin', 'wechat'), 'wechat': ('weixin', 'wechat'),
    '豆包': ('doubao',), '豆包浏览器': ('doubao',),
    '记事本': ('notepad',), '计算器': ('calculatorapp', 'calc'),
    '文件资源管理器': ('explorer',), '资源管理器': ('explorer',),
    '浏览器': ('msedge', 'chrome', 'firefox', 'doubao', 'brave'),
}


def matching_windows(windows, query=''):
    query = str(query).strip().casefold()
    if not query:
        return list(windows)
    terms = {query, *ALIASES.get(query, ())}
    def matches_process(window):
        process = str(window.get('process_name', '')).casefold()
        executable = str(window.get('executable', '')).casefold()
        stem = ntpath.splitext(ntpath.basename(query))[0]
        # A full path identifies its executable; do not match arbitrary directories.
        if ('\\' in query or '/' in query) and executable == query:
            return True
        return any(term in process or term == ntpath.splitext(ntpath.basename(executable))[0]
                   for term in terms) or (query.endswith('.exe') and process == stem + '.exe')
    processes = [window for window in windows if matches_process(window)]
    # Prefer executable identity over an unrelated document merely mentioning the app.
    # A known app identity must not degrade into a title substring: 企业微信
    # and a document mentioning 微信 are not the Weixin/WeChat application.
    if processes or query in ALIASES:return processes
    return [window for window in windows if query in str(window.get('title','')).casefold()]


def list_windows(query='', limit=100):
    now=time.monotonic()
    if _CACHE['windows'] and now-_CACHE['time']<_CACHE_TTL:
        windows=_CACHE['windows']
    else:
        windows=_enumerate_windows()
        _CACHE.update(time=now,windows=windows)
    # Filter after enumeration so a matching app is not lost behind unrelated windows.
    return matching_windows(windows, query)[:max(1, min(int(limit), 200))]


def _enumerate_windows():
    import psutil
    import win32gui
    import win32process
    windows = []
    processes = {}
    foreground = win32gui.GetForegroundWindow()
    def collect(hwnd, _):
        try:
            title = win32gui.GetWindowText(hwnd)
            if not win32gui.IsWindowVisible(hwnd):
                return
            # 注意：不跳过空标题——WorkBuddy/Chrome_WidgetWin_1 在某些状态下标题为空，
            # 但进程名是 workbuddy.exe，后续 matching_windows 按进程名能正确匹配。
            pid = win32process.GetWindowThreadProcessId(hwnd)[1]
            if pid not in processes:
                metadata = dict(pid=pid, process_name='', executable='')
                try:
                    process = psutil.Process(pid)
                    metadata.update(process_name=process.name(), executable=process.exe())
                except (psutil.Error, OSError):
                    pass
                processes[pid] = metadata
            windows.append(dict(hwnd=hwnd, title=title, rect=win32gui.GetWindowRect(hwnd),
                window_class=win32gui.GetClassName(hwnd), minimized=bool(win32gui.IsIconic(hwnd)),
                foreground=hwnd == foreground, **processes[pid]))
        except OSError:
            pass  # A window may close during enumeration.
    win32gui.EnumWindows(collect, None)
    return windows
