"""Non-activating, clickable speech above the pet; does not own audio lifetime."""
from PyQt5.QtCore import Qt, QEvent, QTimer, pyqtSignal
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QApplication


class PetSpeechBubble(QFrame):
    clicked = pyqtSignal()
    end_call = pyqtSignal()
    talk_started = pyqtSignal()
    talk_stopped = pyqtSignal(bool)

    def __init__(self, pet):
        super().__init__(pet, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus)
        self.pet = pet
        self.call_active = False
        self.speaking = False
        self._recording = False
        self._voice_state = 'idle'
        self._wave_index = 0
        self.conversation_id = None
        self.full_text = ''
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setCursor(Qt.PointingHandCursor)
        self.setFont(QFont('Microsoft YaHei UI', 10))
        self.setFixedWidth(326)
        self.setObjectName('SpeechBubble')
        self.setStyleSheet('''
            QFrame#BubbleCard { background:#fffdf8; border:1px solid #d9d7e7; border-radius:16px; }
            QLabel { color:#30334b; background:transparent; border:none; }
            QLabel#BubbleTitle { color:#70628d; font-size:12px; font-weight:600; }
            QLabel#BubbleHint { color:#9793a5; font-size:10px; }
            QPushButton { color:#927b84; background:transparent; border:none; padding:2px 5px; font-size:11px; }
            QPushButton:hover { color:#b6415c; background:#fbeef0; border-radius:6px; }
            QFrame#TalkDock { background:#f3f6ff; border:1px solid #dce5ff; border-radius:19px; }
            QFrame#TalkDock[recording="true"] { background:#5b86ff; border:1px solid #4b79f5; }
            QLabel#TalkWave { color:#7692d8; font-size:15px; letter-spacing:2px; }
            QFrame#TalkDock[recording="true"] QLabel#TalkWave { color:#ffffff; }
            QLabel#TalkHint { color:#7180a0; font-size:11px; }
            QFrame#TalkDock[recording="true"] QLabel#TalkHint { color:#ffffff; }
            QPushButton#TalkCancel { min-width:30px; max-width:30px; min-height:30px; max-height:30px;
                background:#e3e9f8; color:#526689; border-radius:15px; font-size:16px; padding:0; }
            QPushButton#TalkSend { min-width:34px; max-width:34px; min-height:34px; max-height:34px;
                background:#dce7ff; color:#315fd0; border-radius:17px; font-size:18px; padding:0; }
            QFrame#TalkDock[recording="true"] QPushButton#TalkCancel,
            QFrame#TalkDock[recording="true"] QPushButton#TalkSend { background:#ffffff; color:#416def; }
        ''')
        outer = QVBoxLayout(self); outer.setContentsMargins(3,3,3,8)
        card = QFrame(self); card.setObjectName('BubbleCard')
        layout = QVBoxLayout(card); layout.setContentsMargins(16,12,16,12); layout.setSpacing(7)
        header = QHBoxLayout()
        self.title = QLabel('咕嘎'); self.title.setObjectName('BubbleTitle')
        self.title.setAttribute(Qt.WA_TransparentForMouseEvents)
        header.addWidget(self.title,1)
        self.stop_button = QPushButton('结束通话')
        self.stop_button.setFocusPolicy(Qt.NoFocus)
        self.stop_button.clicked.connect(self.end_call)
        self.stop_button.hide()
        header.addWidget(self.stop_button)
        layout.addLayout(header)
        self.text = QLabel(); self.text.setWordWrap(True); self.text.setTextFormat(Qt.PlainText)
        self.text.setAttribute(Qt.WA_TransparentForMouseEvents)
        layout.addWidget(self.text)
        hint = QLabel('按住 ↑ 说话 · 右键展开完整对话'); hint.setObjectName('BubbleHint')
        hint.setAttribute(Qt.WA_TransparentForMouseEvents)
        layout.addWidget(hint)
        self.talk_dock=QFrame();self.talk_dock.setObjectName('TalkDock')
        self.talk_dock.setProperty('recording',False)
        talk=QHBoxLayout(self.talk_dock);talk.setContentsMargins(4,3,4,3);talk.setSpacing(7)
        self.cancel_button=QPushButton('×');self.cancel_button.setObjectName('TalkCancel')
        self.cancel_button.setFocusPolicy(Qt.NoFocus);self.cancel_button.setToolTip('取消录音；未录音时收起气泡')
        self.cancel_button.clicked.connect(self.cancel_talk);talk.addWidget(self.cancel_button)
        self.wave=QLabel('▁▂▃▄▃▂▁');self.wave.setObjectName('TalkWave')
        self.wave.setAttribute(Qt.WA_TransparentForMouseEvents);talk.addWidget(self.wave,1)
        self.talk_hint=QLabel('按住说话');self.talk_hint.setObjectName('TalkHint')
        self.talk_hint.setAttribute(Qt.WA_TransparentForMouseEvents);talk.addWidget(self.talk_hint)
        self.talk_button=QPushButton('↑');self.talk_button.setObjectName('TalkSend')
        self.talk_button.setFocusPolicy(Qt.NoFocus);self.talk_button.setToolTip('按住说话，松开发送；识别后咕嘎会用语音回答')
        self.talk_button.pressed.connect(self._begin_talk);self.talk_button.released.connect(self._finish_talk)
        talk.addWidget(self.talk_button)
        layout.addWidget(self.talk_dock)
        outer.addWidget(card)
        self.timer = QTimer(self); self.timer.setSingleShot(True); self.timer.timeout.connect(self._expire)
        self.wave_timer=QTimer(self);self.wave_timer.setInterval(130);self.wave_timer.timeout.connect(self._wave_tick)
        pet.installEventFilter(self)

    def set_call_active(self, active, conversation_id=None):
        self.call_active = bool(active)
        if conversation_id:
            self.conversation_id = conversation_id
        self.stop_button.setVisible(self.call_active)
        self.talk_dock.setVisible(True)
        self.title.setText('咕嘎 · 正在听' if active else '咕嘎')
        if active:
            self.show_text('我在听，可以直接和我说话。', self.conversation_id)
        elif self.isVisible():
            self.show_text('通话已结束。', self.conversation_id)
            self.timer.start(4000)

    def set_call_reconnecting(self, conversation_id=None):
        """Transient WS gap: never claim the call ended; the worker reconnects."""
        if conversation_id:
            self.conversation_id = conversation_id
        self.call_active = True
        self.stop_button.setVisible(True)
        self.talk_dock.setVisible(True)
        self.title.setText('咕嘎 · 正在重连')
        self.show_text('语音连接中断，正在自动重连…（点“结束通话”或说“闭嘴”可停止）', self.conversation_id)
        self.timer.stop()

    def show_text(self, text, conversation_id=None):
        self.full_text = str(text).strip()
        if not self.full_text:
            return
        if conversation_id:
            self.conversation_id = conversation_id
        # Readable on the desktop without opening the conversation window.
        screen = QApplication.screenAt(self.pet.frameGeometry().center()) or QApplication.primaryScreen()
        available = screen.availableGeometry().width() if screen else 1200
        self.setFixedWidth(max(380, min(620, available - 48)))
        preview = self.full_text if len(self.full_text)<=1600 else self.full_text[:1598].rstrip()+'…'
        self.text.setText(preview)
        self.talk_dock.setVisible(True)
        self.setToolTip('按住 ↑ 说话；完整对话请从右键菜单展开')
        self.adjustSize()
        self.follow_pet()
        if self.pet.isVisible():
            try:
                import ctypes
                ctypes.windll.user32.SetWindowDisplayAffinity(int(self.winId()),0)
            except Exception:pass
            self.show()
        if not self.speaking:
            self.timer.start(12000)

    def set_speaking(self, speaking):
        self.speaking = bool(speaking)
        self.title.setText('咕嘎 · 正在回答' if speaking else ('咕嘎 · 正在听' if self.call_active else '咕嘎'))
        if speaking:
            self.timer.stop()
        elif self.isVisible():
            self.timer.start(12000)

    def _set_dock_state(self, recording=False, hint='按住说话', title='咕嘎', wave=None):
        self.talk_dock.setProperty('recording',bool(recording))
        self.talk_dock.style().unpolish(self.talk_dock);self.talk_dock.style().polish(self.talk_dock)
        for widget in (self.cancel_button,self.wave,self.talk_hint,self.talk_button):
            widget.style().unpolish(widget);widget.style().polish(widget)
        self.talk_hint.setText(hint);self.title.setText(title)
        if wave is not None:self.wave.setText(wave)
        self.adjustSize();self.follow_pet()

    def set_voice_state(self,state):
        self._voice_state=str(state or 'idle')
        if self._voice_state=='preparing':
            self._set_dock_state(True,'准备麦克风','咕嘎 · 正在听','● ● ●')
        elif self._voice_state=='recording':
            self._recording=True;self.wave_timer.start();self.timer.stop()
            self._set_dock_state(True,'松开发送','咕嘎 · 正在听')
        elif self._voice_state=='transcribing':
            self._recording=False;self.wave_timer.stop();self.timer.stop()
            self._set_dock_state(True,'正在识别','咕嘎 · 正在听','▃▃▃▃▃')
        else:
            self._recording=False;self.wave_timer.stop()
            self._set_dock_state(False,'按住说话','咕嘎' if not self.speaking else '咕嘎 · 正在回答','▁▂▃▄▃▂▁')
            if self.isVisible():self.timer.start(15000)

    def _wave_tick(self):
        patterns=('▁▂▃▄▃▂▁','▂▄▆▃▅▂▄','▄▂▅▇▃▁▂','▃▅▂▄▆▃▅','▂▃▅▇▅▃▂')
        self._wave_index=(self._wave_index+1)%len(patterns);self.wave.setText(patterns[self._wave_index])

    def _begin_talk(self):
        if self._voice_state in ('preparing','recording','transcribing'):return
        self._recording=True;self.timer.stop();self._voice_state='recording';self.wave_timer.start()
        self._set_dock_state(True,'松开发送','咕嘎 · 正在听','▂▃▅▇▅▃▂')
        self.talk_started.emit()

    def _finish_talk(self):
        if not self._recording or self._voice_state=='transcribing':return
        self._recording=False;self._voice_state='transcribing';self.wave_timer.stop()
        self._set_dock_state(True,'正在识别','咕嘎 · 正在听','▃▃▃▃▃')
        self.talk_stopped.emit(False)

    def cancel_talk(self):
        if self._recording or self._voice_state in ('preparing','transcribing'):
            self._recording=False;self.wave_timer.stop();self._voice_state='idle'
            self._set_dock_state(False,'按住说话','咕嘎')
            self.talk_stopped.emit(True)
        else:self.hide()

    def _expire(self):
        if self._recording or self._voice_state in ('preparing','transcribing'):return
        if self.call_active:
            self.text.setText('正在听你说话…')
            self.adjustSize(); self.follow_pet()
        else:
            self.hide()

    def follow_pet(self):
        center = self.pet.frameGeometry().center()
        screen = QApplication.screenAt(center) or QApplication.primaryScreen()
        if not screen:
            return
        area = screen.availableGeometry()
        x = center.x()-self.width()//2
        y = self.pet.frameGeometry().top()-self.height()+22
        # At the top screen edge, keep the bubble visible beside the pet.
        if y<area.top():
            y = self.pet.frameGeometry().top()
            x = self.pet.frameGeometry().right()+8
        x = max(area.left(),min(x,area.right()-self.width()+1))
        y = max(area.top(),min(y,area.bottom()-self.height()+1))
        self.move(x,y)

    def eventFilter(self, obj, event):
        if obj is self.pet:
            if event.type() in (QEvent.Move,QEvent.Resize):
                self.follow_pet()
            elif event.type()==QEvent.Hide:
                self.hide()
            elif event.type()==QEvent.Show and self.call_active:
                self.follow_pet(); self.show()
        return super().eventFilter(obj,event)

    def mouseReleaseEvent(self, event):
        if event.button()==Qt.LeftButton:
            self.clicked.emit(); event.accept()
        else:
            super().mouseReleaseEvent(event)
