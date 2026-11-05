"""Explicit bounded live-operation entry, separate from normal speech."""
from PyQt5.QtCore import QThread,pyqtSignal
from PyQt5.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QPlainTextEdit


class LiveWorker(QThread):
    message=pyqtSignal(str)

    def __init__(self,count,parent=None):
        super().__init__(parent)
        self.count=count
        self.session=None

    def run(self):
        try:
            from core.bg_live import LiveSession
            from core.bg_live_windows import HearthstoneWindow
            from core.log_reader import find_log_path
            path=find_log_path(current_session=True)
            if not path:
                raise RuntimeError('未找到炉石日志，请先进入酒馆战棋')
            self.session=LiveSession(HearthstoneWindow(),path,self.message.emit)
            if self.isInterruptionRequested():
                return
            self.session.run(self.count,90 if self.count==1 else 240)
        except Exception as error:
            # Never expose HTTP response bodies, headers or credentials.
            self.message.emit('已暂停：'+str(error)[:350] if isinstance(error,(RuntimeError,ValueError)) else '已暂停：执行或模型连接异常，请重新观察')

    def stop(self):
        self.requestInterruption()
        if self.session:
            self.session.stop.set()


class BattlegroundLivePanel(QDialog):
    def __init__(self,parent=None):
        super().__init__(parent)
        self.worker=None
        self.setWindowTitle('咕嘎 · 战棋实战操作')
        self.resize(760,460)
        self.setStyleSheet('QDialog{background:#111827} QLabel{color:#e5e7eb;font-size:14px} QPushButton{padding:12px;background:#27486b;color:white;border-radius:6px} QPlainTextEdit{background:#0b1220;color:#dbeafe;font-size:14px}')
        layout=QVBoxLayout(self)
        title=QLabel('咕嘎 · 模型决定，实际操作')
        title.setStyleSheet('font-size:23px;color:#93c5fd')
        layout.addWidget(title)
        note=QLabel('读取本机日志 → 配置的策略层（支持 DeepBattler 协议）→ 视觉定位 → 操作后核对。\n连续模式最多 12 步 / 4 分钟；按住 Esc 或点击停止可中止。\n支持免费战棋入口/英雄选择，以及买/出/卖随从、刷新、冻结、升本。\n每执行一步重新决策；发现、英雄技能与目标法术暂时交还给你。')
        note.setWordWrap(True)
        layout.addWidget(note)
        row=QHBoxLayout()
        self.buttons=[]
        for text,callback in [('打开 / 切回炉石',self.open_game),('模型执行一步',lambda:self.start(1)),('限时连续操作',lambda:self.start(12))]:
            b=QPushButton(text)
            b.clicked.connect(callback)
            row.addWidget(b)
            self.buttons.append(b)
        layout.addLayout(row)
        self.output=QPlainTextEdit()
        self.output.setReadOnly(True)
        layout.addWidget(self.output)
        stop=QPushButton('停止操作')
        stop.clicked.connect(self.stop)
        layout.addWidget(stop)

    def open_game(self):
        try:
            from core.bg_live_windows import HearthstoneWindow
            self.output.appendPlainText(HearthstoneWindow().open())
        except Exception:
            self.output.appendPlainText('请从战网打开炉石，登录后进入酒馆战棋。')

    def start(self,count):
        if self.worker and self.worker.isRunning():
            return
        for b in self.buttons:
            b.setEnabled(False)
        self.worker=LiveWorker(count,self)
        self.worker.message.connect(self.output.appendPlainText)
        self.worker.finished.connect(self.finished)
        self.output.appendPlainText('开始有限执行；将调用现有模型额度并操作当前游戏窗口。')
        self.worker.start()

    def finished(self):
        for b in self.buttons:
            b.setEnabled(True)

    def stop(self):
        if self.worker:
            self.worker.stop()
        self.output.appendPlainText('已请求停止；正在进行的模型请求返回后不会发送新动作。')

    def closeEvent(self,event):
        self.stop()
        if self.worker and self.worker.isRunning():
            self.output.appendPlainText('等待当前请求退出后即可关闭窗口。')
            event.ignore()
        else:
            event.accept()
