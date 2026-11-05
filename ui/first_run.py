# -*- coding: utf-8 -*-
"""首次配置向导 — 给完全不懂 JSON / 没碰过 API 的人用

设计原则（小白口径）:
  1. 桌宠启动时检测不到有效配置 → 自动弹出本向导（用户不需要知道任何文件名）
  2. 对话 API 用"选平台"代替"填地址"：下拉选 DeepSeek/智谱/通义/自定义，
     地址和模型名自动填好，用户只填一个 API Key
  3. 每一项都有"测试"按钮，现场调一次真实接口，绿勾才允许下一步——
     避免"配完跑不起来不知道哪错了"
  4. 云端大脑段可选：填了就有管家监工/跨设备，不填桌宠照样能跑
  5. 保存时 json.dump 生成合法 JSON，用户永远不手写引号和逗号

接入(comp_main.py): 启动前调 ui.first_run.ensure_config(parent=None)，
返回 True=配置就绪继续启动；False=用户关闭了向导（提示后退出）。
"""
import json
import os
import sys
import urllib.request

from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                             QComboBox, QLineEdit, QPushButton, QCheckBox,
                             QGroupBox, QGridLayout, QMessageBox, QFrame)

CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'ai_config.json')

# 平台预设: (显示名, base_url, model, 申请链接)
PRESETS = [
    ('智谱 GLM（推荐：有免费额度，注册最快）',
     'https://open.bigmodel.cn/api/paas/v4', 'glm-4-flash',
     'https://open.bigmodel.cn/usercenter/apikeys'),
    ('DeepSeek 官方',
     'https://api.deepseek.com', 'deepseek-chat',
     'https://platform.deepseek.com/api_keys'),
    ('通义千问（阿里）',
     'https://dashscope.aliyuan.com/compatible-mode/v1', 'qwen-plus',
     'https://bailian.console.aliyun.com/'),
    ('自定义（自己填地址和模型名）',
     '', '', ''),
]

DEFAULT_VISION_MODEL = 'glm-4.6v-flash'
DEFAULT_CLOUD = 'http://39.107.48.60:3000'


def config_ok(path=None):
    """配置是否已可用: 文件存在 + api_key/base_url/model 都非占位."""
    path = path or CONFIG_PATH
    try:
        with open(path, encoding='utf-8') as f:
            cfg = json.load(f)
        key = str(cfg.get('api_key', ''))
        url = str(cfg.get('base_url', ''))
        model = str(cfg.get('model', ''))
        return (bool(key) and 'YOUR_' not in key
                and url.startswith('http') and 'YOUR_' not in url
                and bool(model) and 'YOUR_' not in model)
    except Exception:
        return False


class _Probe(QThread):
    """后台探针: 调一次真实接口验证配置. done(ok, msg) 回主线程."""

    done = pyqtSignal(bool, str)

    def __init__(self, kind, base_url, api_key, model, extra=None):
        super().__init__()
        self.kind, self.base, self.key = kind, base_url.rstrip('/'), api_key
        self.model, self.extra = model, extra or {}

    def run(self):
        try:
            if self.kind == 'chat':
                body = {'model': self.model, 'messages': [
                    {'role': 'user', 'content': '回复"OK"两个字母即可'}],
                    'max_tokens': 8, 'stream': False}
                req = urllib.request.Request(self.base + '/chat/completions',
                                             method='POST')
                req.add_header('Content-Type', 'application/json')
                req.add_header('Authorization', 'Bearer ' + self.key)
                with urllib.request.urlopen(
                        req, json.dumps(body).encode(), timeout=25) as r:
                    resp = json.loads(r.read().decode())
                text = ((resp.get('choices') or [{}])[0].get('message') or {}
                        ).get('content', '')
                self.done.emit(True, '对话 API 连通，模型已回复：%s' % (text.strip()[:24] or '(空)'))
            elif self.kind == 'cloud':
                req = urllib.request.Request(self.base + '/api/login',
                                             method='POST')
                req.add_header('Content-Type', 'application/json')
                body = {'username': self.key, 'password': self.model}
                with urllib.request.urlopen(
                        req, json.dumps(body).encode(), timeout=20) as r:
                    resp = json.loads(r.read().decode())
                self.done.emit(True, '云端登录成功（账号 %s）' % resp.get('username', ''))
        except Exception as e:
            detail = ''
            if hasattr(e, 'read'):     # HTTPError 带服务端错误体
                try:
                    detail = json.loads(e.read().decode()).get('error', '')
                except Exception:
                    pass
            self.done.emit(False, (detail or str(e))[:120])


class FirstRunWizard(QDialog):
    """三段式配置窗口: 对话API(必填) / 云端大脑(可选) / 保存."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle('咕嘎 · 首次配置向导')
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setFixedSize(560, 620)
        self._probes = []
        self._chat_ok = False
        self._cloud_ok = False

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 12)

        title = QLabel('三步让咕嘎跑起来：① 选平台填 Key  ②（可选）填云端账号  ③ 保存')
        title.setStyleSheet('font-size:14px; font-weight:bold; color:#1a1c20;')
        root.addWidget(title)

        # ---------- ① 对话 API ----------
        g1 = QGroupBox('① 对话 API（必填 —— 咕嘎的大脑）')
        f1 = QGridLayout(g1)
        self._preset = QComboBox()
        for name, *_ in PRESETS:
            self._preset.addItem(name)
        self._preset.currentIndexChanged.connect(self._on_preset)
        f1.addWidget(QLabel('平台'), 0, 0)
        f1.addWidget(self._preset, 0, 1, 1, 2)
        self._url = QLineEdit()
        self._url.setPlaceholderText('https://…（选平台自动填，自定义才手填）')
        f1.addWidget(QLabel('接口地址'), 1, 0)
        f1.addWidget(self._url, 1, 1, 1, 2)
        self._model = QLineEdit()
        f1.addWidget(QLabel('模型名'), 2, 0)
        f1.addWidget(self._model, 2, 1, 1, 2)
        self._key = QLineEdit()
        self._key.setEchoMode(QLineEdit.Password)
        self._key.setPlaceholderText('粘贴你的 API Key（形如 sk-…）')
        f1.addWidget(QLabel('API Key'), 3, 0)
        f1.addWidget(self._key, 3, 1)
        self._key_vis = QCheckBox('显示')
        self._key_vis.toggled.connect(
            lambda on: self._key.setEchoMode(
                QLineEdit.Normal if on else QLineEdit.Password))
        f1.addWidget(self._key_vis, 3, 2)
        self._link = QLabel()
        self._link.setOpenExternalLinks(True)
        f1.addWidget(QLabel('申请 Key'), 4, 0)
        f1.addWidget(self._link, 4, 1, 1, 2)
        self._btn_chat = QPushButton('测试连接')
        self._btn_chat.clicked.connect(self._test_chat)
        f1.addWidget(self._btn_chat, 5, 1)
        self._lbl_chat = QLabel('未测试')
        self._lbl_chat.setStyleSheet('color:#8a8f98;')
        f1.addWidget(self._lbl_chat, 5, 2)
        root.addWidget(g1)

        # ---------- ② 云端大脑 ----------
        g2 = QGroupBox('② 云端大脑（可选 —— 不填则没有管家派单/跨设备，其余功能不受影响）')
        f2 = QGridLayout(g2)
        self._cbase = QLineEdit(DEFAULT_CLOUD)
        f2.addWidget(QLabel('服务地址'), 0, 0)
        f2.addWidget(self._cbase, 0, 1, 1, 2)
        self._cuser = QLineEdit()
        self._cuser.setPlaceholderText('作品材料里提供的演示账号')
        f2.addWidget(QLabel('账号'), 1, 0)
        f2.addWidget(self._cuser, 1, 1)
        self._cpass = QLineEdit()
        self._cpass.setEchoMode(QLineEdit.Password)
        f2.addWidget(QLabel('密码'), 2, 0)
        f2.addWidget(self._cpass, 2, 1)
        self._btn_cloud = QPushButton('测试登录')
        self._btn_cloud.clicked.connect(self._test_cloud)
        f2.addWidget(self._btn_cloud, 3, 1)
        self._lbl_cloud = QLabel('未填 = 跳过云端')
        self._lbl_cloud.setStyleSheet('color:#8a8f98;')
        f2.addWidget(self._lbl_cloud, 3, 2)
        root.addWidget(g2)

        # ---------- ③ 保存 ----------
        tip = QLabel('提示：API Key 只保存在本机 ai_config.json，不会上传，也不会进代码仓库。')
        tip.setStyleSheet('color:#8a8f98; font-size:11px;')
        root.addWidget(tip)
        row = QHBoxLayout()
        self._btn_save = QPushButton('保存并启动咕嘎')
        self._btn_save.setStyleSheet(
            'QPushButton{background:#2f7cf6;color:white;padding:8px 20px;'
            'border-radius:6px;font-weight:bold;}'
            'QPushButton:hover{background:#2468d9;}')
        self._btn_save.clicked.connect(self._save)
        row.addStretch(1)
        row.addWidget(self._btn_save)
        row.addStretch(1)
        root.addLayout(row)

        self._on_preset(0)

    # ---------- 交互 ----------

    def _on_preset(self, idx):
        name, url, model, link = PRESETS[idx]
        if url:
            self._url.setText(url)
            self._model.setText(model)
            self._url.setEnabled(False)
            self._model.setEnabled(False)
        else:
            self._url.clear()
            self._model.clear()
            self._url.setEnabled(True)
            self._model.setEnabled(True)
        self._link.setText('<a href="%s" style="color:#2f7cf6;">去申请 Key（注册后在控制台生成）</a>'
                           % link if link else '')

    def _test_chat(self):
        base, key, model = self._url.text().strip(), self._key.text().strip(), \
            self._model.text().strip()
        if not (base.startswith('http') and key and model):
            self._lbl_chat.setText('请先把平台、Key、模型名填全')
            self._lbl_chat.setStyleSheet('color:#c25b00;')
            return
        self._lbl_chat.setText('测试中…（最长 25 秒）')
        self._lbl_chat.setStyleSheet('color:#8a8f98;')
        self._btn_chat.setEnabled(False)
        p = _Probe('chat', base, key, model)
        p.done.connect(self._chat_result)
        self._probes.append(p)
        p.start()

    def _chat_result(self, ok, msg):
        self._btn_chat.setEnabled(True)
        self._chat_ok = ok
        self._lbl_chat.setText(('✅ ' if ok else '❌ ') + msg)
        self._lbl_chat.setStyleSheet('color:%s;' % ('#1d7a3e' if ok else '#b3261e'))

    def _test_cloud(self):
        base, user, pwd = self._cbase.text().strip(), self._cuser.text().strip(), \
            self._cpass.text()
        if not (base.startswith('http') and user and pwd):
            self._lbl_cloud.setText('地址/账号/密码没填全（不想填就留空整个②段）')
            self._lbl_cloud.setStyleSheet('color:#c25b00;')
            return
        self._lbl_cloud.setText('测试中…')
        self._btn_cloud.setEnabled(False)
        p = _Probe('cloud', base, user, pwd)
        p.done.connect(self._cloud_result)
        self._probes.append(p)
        p.start()

    def _cloud_result(self, ok, msg):
        self._btn_cloud.setEnabled(True)
        self._cloud_ok = ok
        self._lbl_cloud.setText(('✅ ' if ok else '❌ ') + msg)
        self._lbl_cloud.setStyleSheet('color:%s;' % ('#1d7a3e' if ok else '#b3261e'))

    def _save(self):
        if not self._chat_ok:
            box = QMessageBox(self)
            box.setWindowTitle('先测一下')
            box.setText('对话 API 还没测试通过，直接保存大概率跑不起来。\n'
                        '仍要保存吗？（之后可重新打开向导修改）')
            box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
            if box.exec_() != QMessageBox.Yes:
                return
        cfg = {}
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, encoding='utf-8') as f:
                    cfg = json.load(f)
            except Exception:
                cfg = {}
        cfg['api_key'] = self._key.text().strip()
        cfg['base_url'] = self._url.text().strip()
        cfg['model'] = self._model.text().strip()
        if self._cuser.text().strip() and self._cpass.text():
            cfg['cloud'] = {
                'base_url': self._cbase.text().strip(),
                'username': self._cuser.text().strip(),
                'password': self._cpass.text(),
                'device': os.environ.get('COMPUTERNAME', '桌宠本机'),
                'poll_secs': 6,
            }
        else:
            cfg.pop('cloud', None)
        try:
            with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
        except Exception as e:
            QMessageBox.critical(self, '保存失败', '写配置文件出错：%s' % e)
            return
        self.accept()


def ensure_config():
    """桌宠启动入口调用: 配置就绪返回 True; 否则弹向导, 用户保存后 True / 关闭后 False."""
    if config_ok():
        return True
    app = None
    if QThread.currentThread() is None:      # 理论不可达, 防御
        return False
    from PyQt5.QtWidgets import QApplication
    app = QApplication.instance()
    wizard = FirstRunWizard()
    wizard.exec_()
    return config_ok()
