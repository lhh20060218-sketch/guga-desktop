"""Resolve the actual Windows HTTP default instead of guessing Edge/Chrome."""
import os,re,subprocess
from pathlib import Path

def default_executable():
    if os.name!='nt':return None
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,r'Software\Microsoft\Windows\Shell\Associations\UrlAssociations\https\UserChoice') as key:
            progid=winreg.QueryValueEx(key,'ProgId')[0]
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT,progid+r'\shell\open\command') as key:
            command=os.path.expandvars(winreg.QueryValue(key,None))
        match=re.match(r'\s*(?:"([^"]+\.exe)"|(.+?\.exe))(?:\s|$)',command,re.I)
        if match:
            path=Path(match.group(1) or match.group(2))
            if path.is_file():return path
    except OSError:pass
    return None

def launch_arguments(executable,url):
    """Preserve the registered handler flags (e.g. Doubao --single-argument)."""
    fallback=[str(executable),url]
    if os.name!='nt':return fallback
    import ctypes
    from ctypes import wintypes
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,r'Software\Microsoft\Windows\Shell\Associations\UrlAssociations\https\UserChoice') as key:
            progid=winreg.QueryValueEx(key,'ProgId')[0]
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT,progid+r'\shell\open\command') as key:
            command=os.path.expandvars(winreg.QueryValue(key,None))
        parse=ctypes.windll.shell32.CommandLineToArgvW
        parse.argtypes=[wintypes.LPCWSTR,ctypes.POINTER(ctypes.c_int)]
        parse.restype=ctypes.POINTER(wintypes.LPWSTR)
        count=ctypes.c_int();pointer=parse(command,ctypes.byref(count))
        if not pointer:return fallback
        try:args=[pointer[i] for i in range(count.value)]
        finally:
            free=ctypes.windll.kernel32.LocalFree
            free.argtypes=[ctypes.c_void_p];free.restype=ctypes.c_void_p
            free(pointer)
        if not args or os.path.normcase(os.path.abspath(args[0]))!=os.path.normcase(os.path.abspath(str(executable))):return fallback
        replaced=any(re.search(r'%(?:1|l)',a,re.I) for a in args[1:])
        args=[re.sub(r'%(?:1|l)',lambda _:url,a,flags=re.I) for a in args if a!='%*']
        if not replaced:args.append(url)
        return args
    except (OSError,ValueError):return fallback

def launch(url):
    executable=default_executable()
    if executable:
        subprocess.Popen(launch_arguments(executable,url),creationflags=0x08000000)
        return dict(kind='url',target=url,browser=executable.stem,launch_requested=True,
                    verified_running=False,message='已向默认浏览器提交网址；尚未验证页面加载')
    import webbrowser
    if not webbrowser.open(url,new=2):raise RuntimeError('Windows 未接受默认浏览器启动请求')
    return dict(kind='url',target=url,launch_requested=True,verified_running=False,
                message='已向默认浏览器提交网址；尚未验证页面加载')
