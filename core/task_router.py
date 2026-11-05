"""Local-first routing for desktop work.

The fast command parser handles deterministic one-shot commands before this
module.  Here, ordinary desktop tasks stay in Guga's visual/UI-automation
agent.  DSH is reserved for explicit code/project work or an explicit user
override. Routing itself does not depend on a model connection.
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.request


CODE_MARKERS = (
    '源码', '代码库', '仓库', '重构', '多文件', '单元测试', '集成测试', '编译',
    '前端项目', '后端项目', 'fastapi', 'django', 'react', 'vue', 'typescript',
    'python项目', '修复这个项目', '排查源码', '写一个程序', '开发一个项目',
    '实现一个功能', '改这个项目', '调试代码', '代码审查',
)
CODE_ACTIONS = ('写', '改', '修', '实现', '重构', '测试', '调试', '审查', '编译', '开发')

_MODEL_OFFLINE_UNTIL = 0.0


def _is_code_task(text):
    value = str(text or '').lower()
    # Reading a repository page or editing a line is ordinary desktop work.
    engineering=any(word in value for word in ('重构','调试','修复','开发','实现','编译','审查','测试','写'))
    code=any(word in value for word in ('代码','源码','程序','python','react','vue','typescript','前端','后端'))
    scope=any(word in value for word in ('项目','代码库','仓库','多文件','多个文件','多个源码','工程','完整程序'))
    deep=any(word in value for word in ('重构','跨模块','集成测试','端到端','多文件','多个源码'))
    return engineering and code and (scope or deep)


def _local_model_vote(text):
    """Optional advisory vote; disabled immediately when the service is down."""
    global _MODEL_OFFLINE_UNTIL
    endpoint = os.environ.get('GUGA_DECISION_URL', 'http://127.0.0.1:11435/api/decide')
    if time.monotonic() < _MODEL_OFFLINE_UNTIL:
        return None
    questions = {
        'route': {
            'type': 'choice',
            'instructions': 'Which executor should handle request?',
            'criteria': {
                'local_task': 'ordinary desktop task, browser, messaging or remembered workflow',
                'dsh_code': 'complex software repository, code creation or multi-file engineering',
                'chat': 'conversation with no computer action',
                'clarify': 'ambiguous request',
            },
        }
    }
    payload = json.dumps({'model': os.environ.get('GUGA_DECISION_MODEL', 'laya:multilingual'),
                          'state': {'request': str(text)[:4000]}, 'questions': questions},
                         ensure_ascii=False).encode('utf-8')
    try:
        request = urllib.request.Request(endpoint, data=payload,
            headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(request, timeout=.35) as response:
            result = json.load(response)
        answer = result['answers']['route']
        if float(answer.get('confidence', 0)) < .82:
            return None
        return str(answer.get('choice') or '')
    except Exception:
        _MODEL_OFFLINE_UNTIL = time.monotonic() + 30
        return None


def choose_task_route(prompt, image=False, backend='auto', workflow=None):
    """Return an inspectable route without executing any task."""
    backend = str(backend or 'auto').lower()
    if image:
        return dict(executor='local_agent', category='screenshot', reason='用户提供了截图')
    if backend == 'self':
        return dict(executor='local_agent', category='manual', reason='用户固定为本地智能体')
    if backend == 'dsh':
        return dict(executor='dsh', category='manual', reason='用户固定为 DSH')
    if re.search(r'(?:交给|使用|用|让|通过)\s*dsh(?![a-z0-9_])',str(prompt),re.I):
        return dict(executor='dsh',category='explicit',reason='用户明确要求使用 DSH')
    if workflow:
        return dict(executor='local_agent', category='workflow', reason='命中已保存工作流',
                    workflow_id=workflow.get('id'))
    if _is_code_task(prompt):
        return dict(executor='dsh', category='code', reason='涉及代码、项目或多文件工程')
    return dict(executor='local_agent', category='local_task',
                reason='日常电脑操作由咕嘎直接执行，失败后再考虑升级')
