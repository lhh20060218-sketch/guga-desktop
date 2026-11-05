# -*- coding: utf-8 -*-
"""实测 B：元宝真实会话页 → 加号 → 本地文件 → 系统文件框 → 喂入验证。
跳过新建对话歧义，直接用「最近」列表里的既有会话。"""
import io
import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'agent'))
BASE = 'http://39.107.48.60:3000'


def call(path, data=None, token=None, timeout=30):
    req = urllib.request.Request(BASE + path, method='POST' if data is not None else 'GET')
    req.add_header('Content-Type', 'application/json')
    if token:
        req.add_header('Authorization', 'Bearer ' + token)
    with urllib.request.urlopen(req, json.dumps(data).encode() if data is not None else None, timeout=timeout) as r:
        return json.loads(r.read().decode())


def main():
    login = call('/api/login', {'username': '666', 'password': '5201314'})
    code = call('/api/pair/create', {}, login['token'])['code']
    import guga_agent as ga
    import guga_executor as dex
    dex.TOKEN = ga.pair(code)
    dex.CTX = None
    print('PASS 配对')

    w = dex.find_window('元宝')
    w = dex.focus(w)
    w = dex.focus_window(w, '元宝') and w or w

    # 1. 点开「最近」里的既有会话（唯一文字，无相邻行歧义）
    p = dex.locate(w, '左侧「最近」列表里的会话条目「0722新对话」（第二项，带对话图标）')
    print('会话条目定位:', p)
    assert p, '没找到既有会话条目'
    import pyautogui
    pyautogui.click(p[0], p[1])
    time.sleep(2.0)
    w = dex.focus(w)
    page = dex.see(w, '当前是聊天对话页吗？输入框占位文字是什么？一句话')
    print('进入页面:', (page or '')[:80])
    dex.evidence(w, 'opened_chat')

    # 2. 点输入框「+」
    p = dex.locate_deep(w, '底部对话输入框左下角的「+」加号图标按钮（在「发送消息」占位文字左边）',
                        [(0.0, 0.62, 1.0, 0.38)])
    print('「+」定位:', p)
    assert p, '「+」没定位到'
    pyautogui.click(p[0], p[1])
    time.sleep(1.8)
    w = dex.focus(w)
    dex.evidence(w, 'popup_probe')

    # 3. 浮层里找「本地文件」
    p2 = dex.locate_deep(w, '弹出的菜单里的「本地文件」选项', [(0.0, 0.2, 1.0, 0.6)])
    print('「本地文件」定位:', p2)
    if not p2:
        menu = dex.see(w, '弹出菜单里有哪些选项？逐项原文列出')
        print('浮层内容:', (menu or '')[:250])
        pyautogui.press('esc')
        return
    pyautogui.click(p2[0], p2[1])

    # 4. 等系统文件框 → 贴路径 → 确认
    dlg = dex._wait_file_dialog(8.0)
    print('系统文件框:', '出现 ✓' if dlg else '没等到 ✗')
    if not dlg:
        dex.evidence(w, 'no_file_dialog')
        return
    tf = os.path.join(os.path.expanduser('~'), 'Desktop', '咕嘎实测-接力测试文件.txt')
    with io.open(tf, 'w', encoding='utf-8') as f:
        f.write('这是咕嘎本机实测生成的接力测试文件。\n' * 5)
    import pyperclip
    pyperclip.copy(tf)
    time.sleep(0.3)
    pyautogui.hotkey('ctrl', 'v')
    time.sleep(0.6)
    pyautogui.press('enter')
    time.sleep(3.0)
    w = dex.focus(w)
    verdict = dex.see(w, '窗口里是否出现了名为「咕嘎实测-接力测试文件.txt」的附件卡片/缩略图？只答 是 或 否')
    print('喂入验证:', verdict)
    dex.evidence(w, 'attach_final')


if __name__ == '__main__':
    main()
