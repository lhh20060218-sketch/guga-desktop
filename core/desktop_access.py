"""User-enabled local access: file tools, recoverable writes and bounded process jobs."""
import ast
import ctypes
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT/'runtime/chat/local_access.json'


def redact(text):
    text = re.sub(r'\b(?:oc_sk_[A-Za-z0-9_-]{16,}|sk-[A-Za-z0-9_-]{20,})', '[REDACTED]', str(text))
    return re.sub(r'(?i)(["\x27]?(?:api_key|access_token|authorization|password|secret)["\x27]?\s*[:=]\s*)["\x27][^"\x27\r\n]+["\x27]',r'\1"[REDACTED]"',text)


def redact_value(value):
    if isinstance(value,dict):
        return {k:('[REDACTED]' if str(k).lower() in {'api_key','access_token','authorization','password','secret'} else redact_value(v)) for k,v in value.items()}
    if isinstance(value,list):
        return [redact_value(v) for v in value]
    return redact(value) if isinstance(value,str) else value


class DesktopAccess:
    def __init__(self, state_path=None):
        self.state_path = Path(state_path or STATE)

    @property
    def enabled(self):
        try:
            return json.loads(self.state_path.read_text(encoding='utf-8')).get('full_access') is True
        except FileNotFoundError:
            return self.state_path==STATE
        except (OSError,ValueError,AttributeError):
            return False

    def set_enabled(self, enabled):
        self.state_path.parent.mkdir(parents=True,exist_ok=True)
        temporary=self.state_path.with_suffix('.tmp')
        temporary.write_text(json.dumps(dict(full_access=bool(enabled))),encoding='utf-8')
        temporary.replace(self.state_path)

    def status(self):
        return dict(full_access=self.enabled,administrator=bool(ctypes.windll.shell32.IsUserAnAdmin()) if os.name=='nt' else False,
                    source_root=str(ROOT),command_timeout_max_seconds=300)

    def execute(self, args, cancel=None):
        if not self.enabled:
            raise ValueError('本机完整访问未开启；可在软件权限中设置')
        cancel=cancel or threading.Event()
        if cancel.is_set():
            raise RuntimeError('任务已取消')
        action=args.get('action')
        if action=='run':
            return self.run(str(args.get('command','')),args.get('cwd') or str(ROOT),args.get('seconds',30),cancel)
        path=Path(args.get('path') or ROOT).expanduser().resolve()
        if action=='list':
            return dict(path=str(path),entries=[dict(name=p.name,directory=p.is_dir()) for p in sorted(path.iterdir())[:200]])
        if action=='read':
            if path.stat().st_size>512_000:
                raise ValueError('单次读取上限512 KB，请使用命令选择所需片段')
            return dict(path=str(path),content=redact(path.read_text(encoding='utf-8-sig')))
        if action=='write':
            content=args.get('content')
            if not isinstance(content,str) or len(content.encode('utf-8'))>200_000:
                raise ValueError('写入内容需要是200 KB以内的文本')
            if path.suffix.lower()=='.py':
                ast.parse(content,filename=str(path))
            elif path.suffix.lower()=='.json':
                json.loads(content)
            backup=None
            if path.exists():
                backup=ROOT/'runtime/self-updates'/uuid.uuid4().hex/path.name
                backup.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(path,backup)
            if cancel.is_set():
                raise RuntimeError('已取消写入')
            path.parent.mkdir(parents=True,exist_ok=True)
            temporary=path.with_name(path.name+'.guga-'+uuid.uuid4().hex+'.tmp')
            try:
                temporary.write_text(content,encoding='utf-8')
                temporary.replace(path)
            finally:
                if temporary.exists():temporary.unlink()
            return dict(path=str(path),written=True,backup=str(backup) if backup else None,
                        syntax_checked=path.suffix.lower()=='.py',
                        message='文件已写入；仍需运行相关测试，Python模块更新需重启生效')
        raise ValueError('未知本机操作')

    def run(self, command, cwd, seconds, cancel):
        if not command.strip() or len(command)>12000:
            raise ValueError('命令需要1—12000字')
        if type(seconds) is not int or not 1<=seconds<=300:
            raise ValueError('命令预算需要1—300秒')
        cwd=Path(cwd).expanduser().resolve(strict=True)
        if not cwd.is_dir():raise ValueError('工作目录不是文件夹')
        output_root=ROOT/'runtime/agent-jobs'
        output_root.mkdir(parents=True,exist_ok=True)
        job=None;proc=None
        with tempfile.TemporaryDirectory(dir=str(output_root),prefix='job-') as folder:
            assert Path(folder).resolve().parent==output_root.resolve()
            with open(Path(folder)/'stdout','w+b') as stdout,open(Path(folder)/'stderr','w+b') as stderr:
                try:
                    import win32job,win32api
                    job=win32job.CreateJobObject(None,'guga-agent-'+uuid.uuid4().hex)
                    limits=win32job.QueryInformationJobObject(job,win32job.JobObjectExtendedLimitInformation)
                    limits['BasicLimitInformation']['LimitFlags'] |= win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
                    win32job.SetInformationJobObject(job,win32job.JobObjectExtendedLimitInformation,limits)
                    prefix='[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false); $OutputEncoding = [Console]::OutputEncoding; '
                    proc=subprocess.Popen(['powershell.exe','-NoProfile','-NonInteractive','-Command',prefix+command],
                        cwd=str(cwd),stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr,
                        creationflags=subprocess.CREATE_NO_WINDOW)
                    win32job.AssignProcessToJobObject(job,int(proc._handle))
                    deadline=time.monotonic()+seconds
                    stopped=None
                    while proc.poll() is None:
                        if cancel.is_set():stopped='cancelled'
                        elif time.monotonic()>=deadline:stopped='timeout'
                        elif os.fstat(stdout.fileno()).st_size+os.fstat(stderr.fileno()).st_size>1_000_000:stopped='output_limit'
                        if stopped:
                            win32job.TerminateJobObject(job,1);break
                        cancel.wait(.05)
                    proc.wait(timeout=3)
                    # Also terminate a command's leftover background children.
                    win32api.CloseHandle(job);job=None
                    stdout.seek(0);stderr.seek(0)
                    def decode(data):
                        try:return data.decode('utf-8')
                        except UnicodeError:return data.decode('gb18030',errors='replace')
                    return dict(exit_code=proc.returncode,stopped=stopped,
                                stdout=redact(decode(stdout.read(64000))),stderr=redact(decode(stderr.read(16000))),
                                stdout_truncated=os.fstat(stdout.fileno()).st_size>64000,
                                stderr_truncated=os.fstat(stderr.fileno()).st_size>16000)
                finally:
                    if job is not None:
                        import win32api
                        win32api.CloseHandle(job)
                    if proc and proc.poll() is None:
                        proc.kill();proc.wait(timeout=3)
