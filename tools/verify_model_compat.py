"""回归验证：405 根因、qwen3-vl-plus 流式返回形态、轮数上限、视觉单模型、无 Key 开软件。

不联网、不需要真实 API Key：本机起临时 HTTP 服务模拟网关，
真实调用 core.model_endpoint.post / SelfAgent._request / fast_commands。

用法：python tools/verify_model_compat.py
退出码 0 表示全部通过；1 表示有失败项（JSON 里逐项给出证据）。
"""
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

os.environ.setdefault('NO_PROXY', '127.0.0.1,localhost')
os.environ.setdefault('no_proxy', '127.0.0.1,localhost')

CHAT_PATH = '/compatible-mode/v1/chat/completions'


def _json_bytes(payload):
    return json.dumps(payload, ensure_ascii=False).encode('utf-8')


def _sse(chunks):
    lines = []
    for item in chunks:
        lines.append('data: ' + json.dumps(item, ensure_ascii=False))
    lines.append('data: [DONE]')
    return ('\n\n'.join(lines) + '\n\n').encode('utf-8')


class _Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    calls = []
    chat_calls = 0
    lock = threading.Lock()

    def log_message(self, *args):
        pass

    def _send(self, code, body, ctype='application/json', extra=None):
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        # 复现旧行为：requests 自动跟随 302 后把 POST 改成 GET，只收 POST 的端点回 405。
        if self.path.startswith('/only-post'):
            self._send(405, _json_bytes(dict(error='method not allowed')))
            return
        self._send(404, _json_bytes(dict(error='not found')))

    def do_POST(self):
        # 代理收到的是绝对 URI（http://host/path）。企业代理对这类 POST 直接回 405，
        # 正是测试机上“独立验证 404/400、咕嘎却报 405”的来源。
        if self.path.startswith(('http://', 'https://')):
            self._send(405, _json_bytes(dict(error='proxy method not allowed')))
            return
        length = int(self.headers.get('Content-Length') or 0)
        raw = self.rfile.read(length) if length else b'{}'
        try:
            payload = json.loads(raw.decode('utf-8') or '{}')
        except ValueError:
            payload = {}
        with self.lock:
            self.calls.append(dict(path=self.path, payload=payload))
            if self.path.startswith(CHAT_PATH):
                _Handler.chat_calls += 1
            index = _Handler.chat_calls

        if self.path.startswith('/redirect'):
            self._send(302, b'', extra={'Location': '/only-post'})
            return
        if self.path.startswith('/only-post'):
            self._send(200, _json_bytes(dict(ok=True, method='POST')))
            return
        if self.path.startswith(CHAT_PATH):
            if index == 1:
                # 1) stream=False 但网关仍回 SSE：tool_calls 按 index 分片，夹带 reasoning_content。
                body = _sse([
                    dict(choices=[dict(delta=dict(reasoning_content='先确认要做什么。'))]),
                    dict(choices=[dict(delta=dict(tool_calls=[dict(
                        index=0, id='call_a', type='function',
                        function=dict(name='computer', arguments='{"action":'))]))]),
                    dict(choices=[dict(delta=dict(tool_calls=[dict(
                        index=0, function=dict(arguments='"windows"}'))]))]),
                    dict(choices=[dict(delta={}, finish_reason='tool_calls')]),
                ])
                self._send(200, body, 'text/event-stream; charset=utf-8')
                return
            if index == 2:
                # 2) 只有 reasoning_content 却声明 finish_reason=tool_calls：应触发同轮纠偏。
                body = _sse([
                    dict(choices=[dict(delta=dict(reasoning_content='我再想想。'))]),
                    dict(choices=[dict(delta={}, finish_reason='tool_calls')]),
                ])
                self._send(200, body, 'text/event-stream; charset=utf-8')
                return
            # 3) 纠偏后的正常正文。
            body = _sse([
                dict(choices=[dict(delta=dict(content='完成|normal|已确认窗口'))]),
                dict(choices=[dict(delta={}, finish_reason='stop')]),
            ])
            self._send(200, body, 'text/event-stream; charset=utf-8')
            return
        self._send(404, _json_bytes(dict(error='not found')))


def _start():
    server = ThreadingHTTPServer(('127.0.0.1', 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, name='verify-gateway', daemon=True)
    thread.start()
    return server, server.server_address[1]


def _check(items, name, ok, evidence):
    items.append(dict(name=name, ok=bool(ok), evidence=str(evidence)[:500]))
    return bool(ok)


def main():
    results = []
    server, port = _start()
    base = 'http://127.0.0.1:%d' % port
    try:
        # A. 405 根因：自动重定向会把 POST 改成 GET；我们的 post() 必须保持 POST。
        import requests
        from core import model_endpoint
        session = requests.Session()
        session.trust_env = False
        old = session.post(base + '/redirect', json=dict(a=1), allow_redirects=True, timeout=5)
        _check(results, '复现旧 405 根因（302 后 POST 被改成 GET）', old.status_code == 405,
               'requests 自动跟随重定向后 HTTP %s' % old.status_code)
        session.close()
        fixed = model_endpoint.post(base + '/redirect', json=dict(a=1), timeout=5)
        hops = getattr(fixed, 'guga_redirects', None)
        _check(results, 'post() 重定向后仍用 POST', fixed.status_code == 200,
               'HTTP %s，重定向记录 %s' % (fixed.status_code, hops))
        fixed.close()

        # A2. 云端 JSON POST（agent.guga_agent.api）走 urlopen_post：重定向后也必须仍是 POST。
        import urllib.request
        cloud_req = urllib.request.Request(base + '/redirect', method='POST')
        with model_endpoint.urlopen_post(cloud_req, b'{"a":1}', timeout=5) as cloud_resp:
            cloud_body = json.loads(cloud_resp.read().decode('utf-8'))
        _check(results, '云端 urlopen_post 重定向后仍用 POST',
               cloud_body.get('method') == 'POST',
               '响应 %s' % json.dumps(cloud_body, ensure_ascii=False))
        # 真实调用云端值守程序的 api()：它过去直接用 urllib.urlopen，302 后会变 GET。
        import importlib
        guga_agent = importlib.import_module('agent.guga_agent')
        guga_agent.BASE = base
        cloud_api = guga_agent.api('/redirect', {'a': 1}, timeout=5)
        _check(results, '云端值守 api() 重定向后仍用 POST',
               cloud_api.get('method') == 'POST',
               '响应 %s' % json.dumps(cloud_api, ensure_ascii=False))

        # B. base_url 归一化（qwen 网关常见两种填法）。
        for raw, expected in (
                ('https://maas.qianwenaiapi.com', 'https://maas.qianwenaiapi.com/compatible-mode/v1'),
                ('https://maas.qianwenaiapi.com/compatible-mode/v1/chat/completions',
                 'https://maas.qianwenaiapi.com/compatible-mode/v1')):
            got = model_endpoint.base_of(raw)
            _check(results, 'base_url 归一化：%s' % raw, got == expected,
                   '得到 %s' % got)

        # B2. 带查询串/结尾斜杠的完整端点也要还原成根地址（否则拼接后可能 404/405）。
        for raw, expected in (
                ('https://maas.qianwenaiapi.com/compatible-mode/v1/?foo=1',
                 'https://maas.qianwenaiapi.com/compatible-mode/v1'),
                ('https://maas.qianwenaiapi.com/compatible-mode/v1/chat/completions?x=1',
                 'https://maas.qianwenaiapi.com/compatible-mode/v1')):
            got = model_endpoint.base_of(raw)
            _check(results, 'base_url 去掉查询串/结尾斜杠：%s' % raw, got == expected,
                   '得到 %s' % got)

        # C. 405 文案必须能教用户改哪个字段，而不是只报状态码。
        text405 = model_endpoint.text_of(model_endpoint.http_failure(
            405, 'https://maas.qianwenaiapi.com/compatible-mode/v1', 'qwen3-vl-plus'))
        _check(results, '405 失败文案可自救', '405' in text405 and 'base_url' in text405,
               text405.replace('\n', ' ')[:300])

        # D. qwen3-vl-plus 流式分片 + reasoning_content + finish_reason。
        from core.self_agent import SelfAgent
        agent = SelfAgent(None, config=dict(
            base_url=base + '/compatible-mode/v1', api_key='offline',
            model='qwen3-vl-plus', request_timeout=10))
        first = agent._request([dict(role='user', content='列出窗口')], 'verify')
        calls = first.get('tool_calls') or []
        merged_args = calls[0].get('function', {}).get('arguments') if calls else ''
        _check(results, 'SSE 分片 tool_calls 已合并', len(calls) == 1 and merged_args == '{"action":"windows"}',
               'tool_calls=%s arguments=%s' % (len(calls), merged_args))
        second = agent._request([dict(role='user', content='继续')], 'verify')
        _check(results, 'reasoning_content 空轮自动纠偏', (second.get('content') or '').startswith('完成'),
               'content=%s，模型请求总数=%d' % ((second.get('content') or '')[:40],
                                                _Handler.chat_calls))
        _check(results, '纠正重试不消耗执行轮数', _Handler.chat_calls == 3,
               '服务端收到 %d 次模型请求（1 正常 + 1 推理空轮 + 1 纠偏）' % _Handler.chat_calls)

        # D2. 网关每个分片都重复完整工具名时，不能拼成 computercomputer；真正的分片仍要能拼。
        from core.self_agent import _merge_tool_calls, _message_from_payload
        repeated = _merge_tool_calls({}, [
            dict(index=0, function=dict(name='computer', arguments='{"action":')),
            dict(index=0, function=dict(name='computer', arguments='"windows"}'))])
        fragmented = _merge_tool_calls({}, [
            dict(index=0, function=dict(name='comp', arguments='{')),
            dict(index=0, function=dict(name='uter', arguments='}'))])
        _check(results, '分片重复完整工具名不产生 computercomputer',
               repeated[0]['function']['name'] == 'computer'
               and repeated[0]['function']['arguments'] == '{"action":"windows"}',
               'name=%s arguments=%s' % (repeated[0]['function']['name'],
                                         repeated[0]['function']['arguments']))
        _check(results, '真正的分段工具名仍能拼回 computer',
               fragmented[0]['function']['name'] == 'computer',
               'name=%s' % fragmented[0]['function']['name'])

        # D3. 标准 JSON 的 content 为分片数组时必须摊平成字符串，避免下一轮请求非法。
        msg, _finish = _message_from_payload(dict(choices=[dict(
            finish_reason='stop',
            message=dict(role='assistant', content=[
                dict(type='text', text='第一段'), dict(type='text', text='第二段')]))]))
        _check(results, '标准 JSON 的分片 content 已摊平成字符串',
               isinstance((msg or {}).get('content'), str)
               and msg.get('content') == '第一段第二段',
               'content=%r type=%s' % ((msg or {}).get('content'),
                                       type((msg or {}).get('content')).__name__))

        # E. 单模型（qwen3-vl-plus）能同时覆盖对话/拆解/截图理解；无需再配独立视觉模型。
        _check(results, '单模型 qwen3-vl-plus 可接收图片', agent._accepts_images() is True,
               '模型名含 -vl，视觉准入按真实探测/名称回退判定为可收图')

        # E2. 主模型是纯文本、另配视觉模型时，能力评估必须按视觉目标判定，
        #     不能继续用主模型“看不了截图”的结论误导用户。
        from core import model_capability as mc
        grade, detail = mc._vision_static(dict(
            model='text-only-model', vision_model='qwen3-vl-plus'))
        _check(results, '单独配置视觉模型后不再判定“看不了截图”',
               grade != 'fail' and '单独配置' in detail,
               'grade=%s detail=%s' % (grade, detail))
        target = mc._vision_target(dict(
            model='text-only-model', base_url='https://main.example/v1', api_key='main-key',
            vision_base_url='https://vision.example/v1', vision_model='qwen3-vl-plus',
            vision_api_key='vision-key'))
        _check(results, '视觉目标独立读取 Base URL / 模型名 / Key',
               target and target.get('base_url') == 'https://vision.example/v1'
               and target.get('model') == 'qwen3-vl-plus'
               and target.get('api_key') == 'vision-key',
               'target=%s' % json.dumps(
                   {k: target.get(k) for k in ('base_url', 'model', 'api_key')}
                   if target else target, ensure_ascii=False))

        # F. 例行任务轮数上限为 12，不是 4；检查点上限按 paused 处理（可“继续”）。
        import tempfile
        from core.agent_task import TaskJournal
        routine = SelfAgent(None, config=dict(api_key='offline'))
        seen = []
        routine.completed.connect(seen.append)
        counter = {'n': 0}

        def fake_request(*args, **kwargs):
            counter['n'] += 1
            return dict(role='assistant', tool_calls=[dict(
                id='w%d' % counter['n'], type='function',
                function=dict(name='computer',
                              arguments=json.dumps(dict(action='windows', query=str(counter['n'])))))])

        with tempfile.TemporaryDirectory() as folder:
            routine.journal = TaskJournal(folder)
            routine._request = fake_request
            routine.computer.execute = lambda arguments, cancel: dict(windows=[])
            routine._run('verify', [], '看看当前网页的控件', threading.Event(),
                         handoff=dict(_route=dict(category='local_task')))
        result = seen[0] if seen else {}
        _check(results, '例行任务第 4 轮不会误报上限（实测跑满 12 轮）',
               counter['n'] == 12 and '12轮' in str(result.get('error')),
               '模型轮数=%d，状态=%s，错误=%s' % (counter['n'], result.get('status') or
                                                ('paused' if result.get('paused') else 'failed'),
                                                str(result.get('error'))[:120]))
        _check(results, '检查点上限标记为 paused（可回复“继续”）', result.get('paused') is True,
               'paused=%s' % result.get('paused'))

        # F2. 真实网关单次调用有延迟时，12 轮不能在第 20 秒被“长任务预算”提前截断。
        slow = SelfAgent(None, config=dict(api_key='offline', task_budget_seconds=60))
        slow_seen = []
        slow.completed.connect(slow_seen.append)
        slow_counter = {'n': 0}

        def slow_request(*args, **kwargs):
            time.sleep(1.8)          # 12 轮约 21.6 秒，旧版 20 秒预算会在中途截断
            slow_counter['n'] += 1
            return dict(role='assistant', tool_calls=[dict(
                id='s%d' % slow_counter['n'], type='function',
                function=dict(name='computer', arguments=json.dumps(dict(
                    action='windows', query='slow-%d' % slow_counter['n']))))])

        with tempfile.TemporaryDirectory() as folder:
            slow.journal = TaskJournal(folder)
            slow._request = slow_request
            slow.computer.execute = lambda arguments, cancel: dict(
                windows=[dict(hwnd=1, title='目标窗口 %s' % arguments.get('query'))])
            started = time.monotonic()
            slow._run('verify-slow', [], '看看当前网页的控件', threading.Event(),
                      handoff=dict(_route=dict(category='local_task')))
            slow_elapsed = time.monotonic() - started
        slow_result = slow_seen[0] if slow_seen else {}
        _check(results, '20 秒后仍能继续跑满 12 轮（不被预算提前截断）',
               slow_counter['n'] == 12 and '12轮' in str(slow_result.get('error')),
               '轮数=%d 耗时=%.1fs 错误=%s' % (
                   slow_counter['n'], slow_elapsed, str(slow_result.get('error'))[:120]))

        # G. 无模型 Key 时“打开软件”走本地快速通道，且“打开软件”这种空目标不猜。
        from core import fast_commands
        opened = fast_commands.match('打开计算器')
        ambiguous = fast_commands.match('打开软件')
        no_target = fast_commands._open_app('软件') if ambiguous.get('matched') else {}
        _check(results, '无 Key 也能识别“打开计算器”', opened.get('matched') and opened.get('action') == 'open_app',
               json.dumps(opened, ensure_ascii=False)[:300])
        _check(results, '“打开软件”不猜目标、明确追问', no_target.get('code') == 'target_ambiguous',
               json.dumps(no_target, ensure_ascii=False)[:300])
        composite = fast_commands.match('打开豆包然后写一份周报')
        _check(results, '复合指令不吞掉后续动作（交回模型）', composite.get('matched') is False,
               json.dumps(composite, ensure_ascii=False)[:300])

        # H. 已收到 initialize、尚未 tools/list 时，自检不能反过来说“缺少/未接入”。
        from core import env_check, tool_advice
        from core.adapters import mcp_channels
        originals = (tool_advice.missing_tools, tool_advice.installed_names,
                     mcp_channels.channel_status)
        try:
            tool_advice.missing_tools = lambda: [dict(
                id='doubao', name='豆包', badge='推荐', install='安装豆包并启用连接器', why='')]
            tool_advice.installed_names = lambda: []
            mcp_channels.channel_status = lambda app_id, workspace=None: (
                dict(state='client_handshake_no_tools', client_unidentified=False)
                if app_id == 'doubao' else dict(state='not_configured'))
            item = env_check._tools_check()
            text = json.dumps(item, ensure_ascii=False)
            _check(results, '握手-only 状态不再被自检写成“缺少/未接入”',
                   '缺少 豆包' not in text and '已收到 MCP initialize' in text,
                   text[:300])
        finally:
            (tool_advice.missing_tools, tool_advice.installed_names,
             mcp_channels.channel_status) = originals

        # I. 视觉模型单独配置时也要归一化 Base URL；能力探测必须和主链路的
        #    SelfAgent._request 打到同一个 chat/completions 地址。
        normalized = model_endpoint.normalize_config(dict(
            base_url='https://maas.qianwenaiapi.com/compatible-mode/v1/chat/completions?x=1',
            vision_base_url='https://vision.example/v1/chat/completions'))
        _check(results, 'vision_base_url 随配置一起归一化',
               normalized.get('base_url') == 'https://maas.qianwenaiapi.com/compatible-mode/v1'
               and normalized.get('vision_base_url') == 'https://vision.example/v1',
               json.dumps({k: normalized.get(k) for k in ('base_url', 'vision_base_url')},
                          ensure_ascii=False))
        probe_cfg = dict(base_url=base + '/compatible-mode/v1/chat/completions',
                         api_key='offline', model='qwen3-vl-plus')
        vision_target = mc._vision_target(dict(
            model='text-only', base_url='https://main.example/v1',
            vision_base_url='https://vision.example/v1/chat/completions',
            vision_model='qwen3-vl-plus', vision_api_key='vk'))
        _check(results, '独立视觉目标也归一化 Base URL',
               vision_target and vision_target.get('base_url') == 'https://vision.example/v1',
               'base_url=%s' % (vision_target.get('base_url') if vision_target else None))
        before = len(_Handler.calls)
        probe_resp = mc._post(probe_cfg, dict(
            model='qwen3-vl-plus', messages=[dict(role='user', content='ping')]), 5)
        probe_path = _Handler.calls[before]['path'] if len(_Handler.calls) > before else ''
        _check(results, '能力探测与主链路打到同一 chat/completions 地址',
               probe_resp.status_code == 200 and probe_path == CHAT_PATH,
               'path=%s status=%s' % (probe_path, probe_resp.status_code))
        probe_resp.close()

        # A3. 代理对 POST 回 405 时，必须自动绕开代理重发一次，并且重发结果可用。
        chat_url = base + CHAT_PATH
        saved = {name: os.environ.get(name) for name in (
            'HTTP_PROXY', 'http_proxy', 'HTTPS_PROXY', 'https_proxy',
            'ALL_PROXY', 'all_proxy', 'NO_PROXY', 'no_proxy')}
        try:
            for name in ('NO_PROXY', 'no_proxy', 'ALL_PROXY', 'all_proxy'):
                os.environ.pop(name, None)
            os.environ['HTTP_PROXY'] = base
            os.environ['http_proxy'] = base
            bypass = model_endpoint.post(
                chat_url, json=dict(model='offline', messages=[]), timeout=5)
            bypassed = bool(getattr(bypass, 'guga_proxy_bypass', False))
            _check(results, '代理对 POST 回 405 时自动绕代理重发成功',
                   bypass.status_code == 200 and bypassed,
                   'HTTP %s proxy_bypass=%s' % (bypass.status_code, bypassed))
            bypass.close()
        finally:
            for name, value in saved.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value

        # J. 异常文本为空的“未归类异常”不能退化成“执行器没有提供明确原因”。
        class OddFailure(Exception):
            pass

        def boom(*args, **kwargs):
            raise OddFailure()

        unlucky = SelfAgent(None, config=dict(api_key='offline'))
        unlucky_seen = []
        unlucky.completed.connect(unlucky_seen.append)
        unlucky._request = boom
        unlucky._run('verify-odd', [], '输入并验证', threading.Event())
        odd = unlucky_seen[0] if unlucky_seen else {}
        _check(results, '空异常文本失败仍带异常类型',
               'OddFailure' in str(odd.get('error'))
               and '执行器没有提供明确原因' not in str(odd.get('error')),
               str(odd.get('error'))[:200])

        # K. 软件名查不到 / 完整访问未开启必须有统一失败码与可执行下一步，
        #    不能显示“未归类：未知异常类型”，也不能建议“重启目标软件”。
        import tempfile as _tempfile
        from types import SimpleNamespace
        from core.authorized_apps import AuthorizedApps, AppResolutionError
        from core.failure_report import format_failure, stage_for
        from core import browser_agent
        with _tempfile.TemporaryDirectory() as folder:
            apps = AuthorizedApps(__import__('pathlib').Path(folder) / 'apps.json')
            apps.access = SimpleNamespace(enabled=False)
            try:
                apps.open('Google Chrome')
                resolution = None
            except AppResolutionError as exc:
                resolution = exc
            code = getattr(resolution, 'code', '')
            message = str(resolution or '')
            text = format_failure(code, stage_for(code), 'AppResolutionError: ' + message, '', app='')
            _check(results, '软件名查不到时给出 app_not_found 四段，而不是“未归类”',
                   code == 'app_not_found' and '【失败码】app_not_found' in text
                   and '未归类' not in text and '接入面板' in message,
                   text.replace('\n', ' | ')[:400])
        gated = browser_agent.execute(
            SimpleNamespace(access=SimpleNamespace(enabled=False)),
            dict(action='snapshot'), threading.Event())
        gated_text = format_failure(
            gated.get('code'), stage_for(gated.get('code') or ''),
            'BrowserAccessError: ' + str(gated.get('error')), '', app='')
        _check(results, '完整访问未开启时给出 access_disabled 与开启位置',
               gated.get('code') == 'access_disabled'
               and '【失败码】access_disabled' in gated_text
               and '软件权限' in str(gated.get('error')),
               gated_text.replace('\n', ' | ')[:400])
    finally:
        server.shutdown()
        server.server_close()

    failed = [item for item in results if not item['ok']]
    print(json.dumps(dict(ok=not failed, passed=len(results) - len(failed),
                          failed=len(failed), items=results),
                     ensure_ascii=False, indent=2))
    return 0 if not failed else 1


if __name__ == '__main__':
    sys.exit(main())
