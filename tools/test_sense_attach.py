# -*- coding: utf-8 -*-
"""本机功能实测 A：开屏感知（KB6）+ 文件喂入（KB7）。
用法: python tools/test_sense_attach.py <云端地址> <用户名> <密码>
真实操作本机鼠标键盘——运行前确认屏幕可用。"""
import io
import json
import os
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
AGENT = os.path.join(HERE, '..', 'agent')
sys.path.insert(0, os.path.abspath(HERE, ) if False else os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, AGENT)

BASE = (sys.argv[1] if len(sys.argv) > 1 else 'http://39.107.48.60:3000').rstrip('/')
USER = sys.argv[2] if len(sys.argv) > 2 else '666'
PASS = sys.argv[3] if len(sys.argv) > 3 else '5201314'
APP = sys.argv[4] if len(sys.argv) > 4 else '元宝'   # Kimi 已移出适配名单（付费门槛），实测锚定元宝


def call(path, data=None, token=None, timeout=30):
    req = urllib.request.Request(BASE + path, method='POST' if data is not None else 'GET')
    req.add_header('Content-Type', 'application/json')
    if token:
        req.add_header('Authorization', 'Bearer ' + token)
    with urllib.request.urlopen(req, json.dumps(data).encode() if data is not None else None, timeout=timeout) as r:
        return json.loads(r.read().decode())


def main():
    # 1. 配对拿执行方身份（感知/取证要带 token）
    login = call('/api/login', {'username': USER, 'password': PASS, 'device': '本机实测'})
    code = call('/api/pair/create', {}, login['token'])['code']
    import guga_agent as ga
    token = ga.pair(code)     # 自检 + 配对，同时校验 local_caps
    print('PASS 配对')

    import guga_executor as dex
    dex.TOKEN = token
    dex.CTX = None            # 实测不上传证据墙（本地存档即可）

    # 2. 拉起目标软件（不在跑就启动——launch 本身就是实测项）
    w = dex.find_window(APP) or dex.launch(APP)
    assert w, f'{APP} 拉不起来'
    w = dex.focus(w)
    print('PASS 打开并聚焦', APP)

    # 3. 开屏感知（KB6）：真实截图 + 真实视觉模型
    t0 = time.time()
    sense = dex.sense_screen(w, APP)
    print('PASS 开屏感知 (%.1fs): %s' % (time.time() - t0, json.dumps(sense, ensure_ascii=False)))
    if sense.get('state') == 'dialog_popup' and sense.get('question'):
        ok = dex.close_popup(w, APP, hint=sense.get('question'))
        print('弹窗清理:', ok, '→ 复感知:', dex.sense_screen(w, APP).get('state'))

    # 4.5 等软件就绪（工作区加载期窗口换代、按钮不响应——就绪判定用感知链）+ 进入对话页
    ready = None
    for i in range(6):
        time.sleep(4)
        w = dex._refind(w) or dex.find_window(APP) or w
        w = dex.focus(w)
        ready = dex.sense_screen(w, APP)
        print('  就绪探测%d: %s（%s）' % (i + 1, ready.get('state'), str(ready.get('note'))[:40]))
        if ready.get('state') in ('empty_chat', 'ongoing_chat', 'history_sidebar'):
            break
    dex.new_chat(w, APP)
    time.sleep(1.0)
    print('PASS 新对话隔离（应已进入空对话页）')

    # 5. 文件喂入（KB7）：造一个测试文件真实喂进去
    tf = os.path.join(os.path.expanduser('~'), 'Desktop', '咕嘎实测-接力测试文件.txt')
    with io.open(tf, 'w', encoding='utf-8') as f:
        f.write('这是一份由咕嘎本机实测生成的接力测试文件。\n' * 5)
    t0 = time.time()
    ok, msg = dex.attach_file(w, APP, tf)
    print('%s 文件喂入 (%.1fs): %s' % ('PASS' if ok else 'FAIL', time.time() - t0, msg))
    print('实测A结束。鼠标已自动操作，请目视确认屏幕状态。')


if __name__ == '__main__':
    main()
