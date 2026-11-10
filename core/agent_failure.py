"""Evidence-based failure reports that remain available when the model is down."""
import os
import re
from urllib.parse import urlsplit

import requests

from core import model_endpoint
from core.failure_report import format_failure, redact_body, redact_raw

FAILURE_CONTRACT = '''
【执行与失败协议】
先区分用户想达到的目标、实际观察到的状态、可用工具。关闭一个页面、切换窗口、读写单个文件是日常操作，不因口语重复、代词或两三步操作就变成复杂任务。
每次操作前确认目标；操作后用目标特有的证据验证。关闭标签页必须核对该标签消失，不能用关闭整个浏览器代替，也不能仅凭快捷键已发出就说完成。
工具失败后读取 error/code/verification 和回执：明确是目标不明、控件不可用、权限拒绝、工具超时、模型连接或结果未验证。先选另一种有证据支持的方法；相同失败条件最多一次改法，不盲目重复点击、关闭、发送、删除，不为了掩盖失败升级到DSH。
最终无法完成时，用自然中文说明：目标尚未完成；失败发生在哪一步；确切证据和已完成/未完成的操作；已尝试的恢复；可执行的下一步。原因不确定就说尚不能确定，禁止把连接异常归咎于用户软件、权限或不存在的接口。不要只说“失败/稍后重试”。
解释是可核对的简短决策依据，不输出隐藏思维链。模型服务本身断开时，宿主会根据工具回执生成说明，不能依赖再次调用已断开的模型才能解释失败。
'''


def proxy_snapshot():
    """记录进程实际会走的代理（requests 默认 trust_env=True，代理也能返回 405）。"""
    found = {}
    for name in ('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'NO_PROXY'):
        value = str(os.environ.get(name) or '').strip()
        if value:
            found[name] = re.sub(r'(?i)(://)[^/@]+@', r'\1***@', value)[:160]
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r'Software\Microsoft\Windows\CurrentVersion\Internet Settings') as key:
            enabled, _ = winreg.QueryValueEx(key, 'ProxyEnable')
            server, _ = winreg.QueryValueEx(key, 'ProxyServer')
        if int(enabled or 0) and server:
            found['WindowsProxy'] = str(server)[:160]
    except Exception:
        pass
    return found


def _safe_endpoint(url):
    """诊断里只保留 scheme://host:port/path，丢掉 userinfo 与 query（可能带 Key）。"""
    try:
        parts = urlsplit(str(url or ''))
        host = parts.hostname or ''
        if not host:
            return ''
        port = ':%s' % parts.port if parts.port else ''
        return '%s://%s%s%s' % (parts.scheme or 'https', host, port, parts.path or '')
    except Exception:
        return ''


def exception_evidence(exc, base_url='', *, stage='model_request', elapsed_ms=0, request_index=0,
                       model='', attempts=None, credential=None):
    """保留类型/errno/状态码；上游响应体先脱敏再截断 240 字，绝不落 Authorization。"""
    queue=[exc];seen=set();names=[];codes=[]
    while queue and len(seen)<16:
        item=queue.pop(0)
        if not isinstance(item,BaseException) or id(item) in seen:continue
        seen.add(id(item));names.append(type(item).__name__)
        for attr in ('errno','winerror'):
            value=getattr(item,attr,None)
            if isinstance(value,int):codes.append(value)
        queue.extend([item.__cause__,item.__context__,getattr(item,'reason',None)])
        queue.extend(x for x in item.args if isinstance(x,BaseException))
    kinds=set(names)
    response = getattr(exc, 'response', None)
    # 401/403 需要区分“Key 无效 / 无模型权限 / 额度用尽”：取上游响应体但先打码、
    # 再截断 240 字。requests.Response.text 一定是字符串；测试桩的 Mock 不是，
    # 不能用 str(Mock) 污染诊断，所以只接受真正的 str。
    raw_body = getattr(response, 'text', '')
    detail = redact_body(raw_body, 240) if isinstance(raw_body, str) else ''
    status = getattr(response, 'status_code', None)
    actual_url = _safe_endpoint(getattr(response, 'url', ''))
    if isinstance(exc,requests.exceptions.ProxyError) or 'ProxyError' in kinds:
        code='proxy';reason='模型请求在代理连接层失败';next_step='核对咕嘎进程使用的代理及代理服务状态'
    elif isinstance(exc,requests.exceptions.SSLError) or any('SSL' in x for x in kinds):
        code='tls';reason='模型请求的 TLS 安全连接失败';next_step='核对系统时间、证书和代理 TLS 配置，不关闭证书校验'
    elif 'NameResolutionError' in kinds or 'gaierror' in kinds:
        code='dns';reason='模型服务域名解析失败';next_step='核对网络和该模型服务域名的 DNS 解析'
    elif isinstance(exc,requests.ConnectTimeout):
        code='connect_timeout';reason='连接模型服务超时，尚未收到 HTTP 响应';next_step='检查模型服务可达性，再重试未完成的步骤'
    elif isinstance(exc,requests.ReadTimeout):
        code='read_timeout';reason='模型请求已发出，但读取响应超时';next_step='恢复连接后先核对现场，再继续未完成的步骤'
    elif isinstance(exc,requests.ConnectionError):
        code='connection';reason='模型连接被中断，现有异常不足以确定远端根因';next_step='检查模型服务与网络状态；不能据此判断浏览器连接失败'
    elif isinstance(exc,requests.HTTPError):
        status=int(status or 0)
        info=model_endpoint.http_failure(status, base_url, model=model, detail=detail)
        code='http'
        reason=info.get('title') or ('模型服务返回 HTTP '+str(status))
        next_step=info.get('next_step') or '核对模型服务状态和请求格式'
        next_step=str(next_step or '').rstrip('。')
        examples=info.get('examples') or []
        if examples:
            next_step += '。已验证可用：' + '；'.join(examples)
        trail=[str(item) for item in (attempts or [])
               if isinstance(item,(dict,str))]
        if trail:
            next_step += '。本次请求记录：' + '；'.join(trail)
        proxy=proxy_snapshot()
        if proxy and status in (405,404,400):
            next_step += '。检测到代理设置（%s）；若接口地址确认正确仍报此错，405 很可能来自代理，' \
                         '请把该域名加入 NO_PROXY / 直连名单，或暂时关闭代理后重试' % (
                             '，'.join('%s=%s' % item for item in proxy.items()))
        if status==405 and getattr(getattr(exc,'response',None),'guga_proxy_bypass',False):
            next_step += '。本次已自动绕过系统代理重发一次，仍是 405，说明不是代理改写方法导致，请优先核对 base_url 最终地址与网关是否允许 POST'
    else:
        code='executor';reason='执行器异常：'+type(exc).__name__;next_step='根据任务记录核对最后一步，保留已完成的操作'
    return dict(code=code,stage=stage,reason=reason,next_step=next_step,
        exception_types=names,os_error_codes=sorted(set(codes)),
        http_status=status,
        request_url=actual_url or _safe_endpoint(model_endpoint.request_url(base_url)),
        request_method='POST' if status else '',
        attempts=list(attempts or []), proxy=proxy_snapshot(), model=str(model or ''),
        service_host=urlsplit(actual_url or base_url).hostname,elapsed_ms=round(elapsed_ms,1),
        request_index=request_index, detail=detail, credential=dict(credential or {}))


def explain_failure(error, *, diagnostic=None, operations=0, events=(), blockers=(),last_tool_failure=None):
    diagnostic=diagnostic or {}
    last_tool_failure=last_tool_failure or {}
    # 适配器失败带真实 code/stage/raw/next_action：直接输出四段，不再拼无信息占位。
    if last_tool_failure:
        return format_failure(
            last_tool_failure.get('code'), last_tool_failure.get('stage'),
            last_tool_failure.get('raw') or last_tool_failure.get('error'),
            last_tool_failure.get('next_action'),
            app=last_tool_failure.get('app') or None)
    reason=diagnostic.get('reason') or last_tool_failure.get('error') or str(error or '执行器没有提供明确原因')
    if reason == '执行器报告失败':
        reason = '旧版执行器没有记录失败码或原始异常'
    # Non-transport errors are already redacted by the task executor.
    reason=re.sub(r'\s+',' ',reason).strip()[:240]
    if not operations:
        impact='尚未调用任何操作工具，没有执行关闭、点击或文件修改。'
    else:
        # 工具调用次数只说明“发出过多少输入”，不是进展；汇报必须说目标本身到哪了。
        impact='目标本身还没有产出可验收的成品。'
        if last_tool_failure:
            failure_type=str(last_tool_failure.get('exception_type') or '工具失败')
            raw_text=redact_raw(last_tool_failure.get('error') or reason)
            first_line=re.sub(r'^[A-Za-z_][\w.]*(?:Error|Exception|Failure|Timeout)[：:]\s*',
                              '', raw_text)[:120]
            impact+='最后一次失败的是%s（未归类：%s: %s）。' % (
                str(last_tool_failure.get('tool') or '未知工具'),
                failure_type, first_line or '没有异常消息')
    next_step=diagnostic.get('next_step') or (
        '请先切到要操作的目标页面，我再重新观察后继续' if last_tool_failure.get('code') in
        ('target_ambiguous','target_not_foreground','target_missing','tab_unavailable') else
        '先重新观察目标并核对最后一步，再处理尚未完成的部分')
    # 凭据指纹：长度 + 前四 + 后四 + 来源（main/fallback/legacy），不输出完整 Key。
    # 用户拿这段和“昨晚能通的那份配置”直接对比，就能确认究竟换没换 Key。
    credential=diagnostic.get('credential') or {}
    if credential:
        next_step=(str(next_step).rstrip('。') + '。本次凭据：长度 %s · 前四 %s … 后四 %s · 来源 %s'
                   % (credential.get('length', 0), credential.get('head') or '—',
                      credential.get('tail') or '—', credential.get('source') or 'main'))
    return f'这次未完成。{reason.rstrip("。")}。{impact}下一步：{str(next_step).rstrip("。")}。'
