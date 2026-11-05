# -*- coding: utf-8 -*-
"""桌宠内嵌执行方连通性测试（不执行真任务, 不动鼠标）

用法:
    python tools/test_local_agent.py <base_url> <username> <password>

验证三件事:
  1. 用户 token 能自动生成配对码（合一的关键: 桌宠自己给自己发配对码）
  2. 配对码能换到执行方 token（桌宠进程内完成, 不需要独立值守程序）
  3. 执行方心跳通道可用, 设备出现在云端在线列表
不派真单——真实执行需要本机 AI 软件在前台, 联调时手动验。
"""
import io
import json
import sys
import os
import time
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from core.butler_cloud import ButlerCloud  # noqa: E402
from core.local_agent import LocalAgent    # noqa: E402


def main():
    if len(sys.argv) >= 4:
        base, user, pwd = sys.argv[1:4]
    else:
        from core.butler_cloud import load_cloud_cfg
        cfg = load_cloud_cfg()
        if not cfg:
            print('FAIL 未提供参数且 ai_config.json 无 cloud 段')
            return 2
        base, user, pwd = cfg['base_url'], cfg['username'], cfg['password']

    cloud = ButlerCloud()
    cloud.base = base.rstrip('/')
    cloud._cfg = {'base_url': cloud.base, 'username': user, 'password': pwd,
                  'device': 'embed-test', 'poll_secs': 6}
    app = _mini_app()
    cloud.login(user, pwd)
    t0 = time.time()
    while not cloud.logged_in and time.time() - t0 < 20:
        app.processEvents()          # 跨线程信号是 Queued, 必须转事件循环
        time.sleep(0.2)
    if cloud.logged_in:
        print('PASS login user=%s' % cloud.user)
    else:
        print('FAIL 登录超时')
        return 1
    agent = LocalAgent(cloud)
    state = {'paired': False, 'err': ''}
    agent.paired.connect(lambda d: (state.__setitem__('paired', True),
                                    print('PASS paired device=%s（桌宠进程内自动配对）' % d)))
    agent.pair_fail.connect(lambda e: (state.__setitem__('err', e),
                                       print('FAIL pair: %s' % e)))
    agent.job_started.connect(lambda j: print('INFO 领到单(不应发生): %s' % j))
    agent.start()
    t0 = time.time()
    while not state['paired'] and not state['err'] and time.time() - t0 < 40:
        app.processEvents()
        time.sleep(0.2)
    if not state['paired']:
        print('FAIL 配对未完成: %s' % (state['err'] or '超时'))
        return 1
    if not agent.active:
        print('FAIL agent.active 为假')
        return 1

    # ---- 心跳一轮, 确认设备在线 ----
    beat = agent._ga.api('/api/agent/beat', {'path': os.getcwd()}, agent._token, timeout=20)
    assert 'job' in beat, '心跳响应缺 job 字段: %s' % list(beat)
    print('PASS beat ok (job=%s)' % beat.get('job'))

    req = urllib.request.Request(cloud.base + '/api/agent/devices')
    req.add_header('Authorization', 'Bearer ' + cloud.token)
    with urllib.request.urlopen(req, timeout=20) as r:
        devices = json.loads(r.read().decode())
    names = json.dumps(devices, ensure_ascii=False)[:200]
    print('PASS devices 在线列表含本机: %s' % names)
    agent.stop()
    print('OK 全部通过 —— 桌宠内嵌执行方打通')
    return 0


def _mini_app():
    from PyQt5.QtCore import QCoreApplication
    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication(sys.argv)
    return app


if __name__ == '__main__':
    sys.exit(main())
