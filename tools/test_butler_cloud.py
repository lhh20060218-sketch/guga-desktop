# -*- coding: utf-8 -*-
"""管家云端客户端连通性测试（不启动 GUI）

用法:
    python tools/test_butler_cloud.py <base_url> <username> <password>

验证三件事:
  1. /api/login 能拿到 token（同账号跨设备的入口）
  2. /api/state 能拉到台账
  3. core/butler_cloud 的状态聚合/播报去重逻辑对真实数据不出错
不派真单（派单会真实消耗 LLM 额度，联调时再手动验）。
"""
import io
import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from core.butler_cloud import (ButlerCloud, load_cloud_cfg,  # noqa: E402
                               task_overall, task_progress)


def main():
    if len(sys.argv) >= 4:
        base, user, pwd = sys.argv[1:4]
    else:
        cfg = load_cloud_cfg()
        if not cfg:
            print('FAIL 未提供参数且 ai_config.json 无 cloud 段')
            return 2
        base, user, pwd = cfg['base_url'], cfg['username'], cfg['password']
    base = base.rstrip('/')

    import urllib.request
    req = urllib.request.Request(base + '/api/login', method='POST')
    req.add_header('Content-Type', 'application/json')
    body = json.dumps({'username': user, 'password': pwd,
                       'device': 'cloud-client-test'}).encode()
    with urllib.request.urlopen(req, body, timeout=20) as r:
        login = json.loads(r.read().decode())
    token = login.get('token', '')
    assert token, '登录未返回 token'
    print('PASS login user=%s token=%s...' % (login.get('username'), token[:8]))

    req = urllib.request.Request(base + '/api/state')
    req.add_header('Authorization', 'Bearer ' + token)
    with urllib.request.urlopen(req, timeout=20) as r:
        state = json.loads(r.read().decode())
    tasks = state.get('tasks') or []
    print('PASS state tasks=%d' % len(tasks))

    # 聚合函数对真实数据跑一遍, 不抛错即算过
    for t in tasks:
        task_overall(t), task_progress(t)
    cloud = ButlerCloud()
    for t in tasks:
        cloud._remember_sig(t)
        cloud._describe_change(t, cloud._sig(t))
    print('PASS aggregate %d tasks (overall/progress/describe no-throw)' % len(tasks))
    print('OK 全部通过')
    return 0


if __name__ == '__main__':
    sys.exit(main())
