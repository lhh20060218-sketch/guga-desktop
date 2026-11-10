"""Browser capability for the reasoning agent, with actual post-action observation."""
from urllib.parse import urlsplit
import time


def execute(computer,args,cancel):
    if cancel.is_set():return dict(ok=False,error='任务已停止，未发送浏览器操作',action_sent=False)
    from core.browser_session import ACTIONS,BrowserSession
    if args.get('action') in ACTIONS:
        if not computer.access.enabled:
            return dict(ok=False,code='access_disabled',action_sent=False,
                        error='完整访问未开启，尚未操作浏览器。请到「软件权限」勾选“允许咕嘎完整访问本机”后再派单')
        session=getattr(computer,'browser_session',None)
        if session is None:session=computer.browser_session=BrowserSession()
        return session.execute(args,cancel)
    if args.get('action')=='close_tab':
        from core.browser_actions import bounded_close
        return bounded_close()
    if args.get('action')=='open':return open_page(computer,args['url'],cancel)
    raise ValueError('未知浏览器操作')

def validate_url(url):
    url=str(url).strip()
    parsed=urlsplit(url)
    if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('需要有效的 http/https 网址；网站名称先由模型解析或搜索')
    if len(url)>3000:raise ValueError('网址过长')
    return url

def open_page(computer,url,cancel):
    from core.browser_launch import launch,default_executable
    url=validate_url(url);executable=default_executable()
    receipt=launch(url)
    # Browser start-up is asynchronous; polling avoids a false "window not
    # found" that forced another model round and often caused a re-launch.
    deadline=time.monotonic()+3.5;candidates=[]
    target=str(executable).casefold() if executable else ''
    while True:
        candidates=[]
        if target:
            # window_inventory already resolved each pid's executable.
            candidates=[w for w in computer.execute(dict(action='windows'),cancel)['windows']
                        if str(w.get('executable','')).casefold()==target]
        else:
            from core.window_inventory import list_windows
            candidates=list_windows('浏览器',limit=20)
        candidates=[w for w in candidates if '浏览器' in w['title']] or candidates
        if candidates or cancel.wait(.25) or time.monotonic()>=deadline:break
    if not candidates:return dict(ok=False,launch_requested=True,error='浏览器已接受网址，但尚未定位窗口；使用 computer.windows 继续核对，不要重复启动')
    preferred=candidates
    window=preferred[0]
    try:
        computer.execute(dict(action='focus',hwnd=window['hwnd']),cancel)
        observation=computer.execute(dict(action='observe',hwnd=window['hwnd']),cancel)
        accessibility=computer.execute(dict(action='accessibility',hwnd=window['hwnd']),cancel)
    except (RuntimeError,ValueError,OSError) as exc:
        return dict(ok=False,launch_requested=True,error='网址已提交，但未完成页面验证：'+str(exc))
    return dict(ok=True,result=dict(observation,url_requested=url,launch_requested=True,
        page_verified=False,accessibility=accessibility,
        message='真实浏览器窗口已观察；请根据截图/地址栏复查目标网址和加载结果，不能仅凭启动回执声称打开成功'))
