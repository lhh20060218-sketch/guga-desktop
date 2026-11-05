"""Export an original-art interaction sample; --window shows a 120s review UI.
Does not import PetWindow, use APIs, or alter the live pet/preferences.
"""
import argparse
import math
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from launcher import _prepare_qt
_prepare_qt()
from PyQt5.QtWidgets import QApplication,QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton
from PyQt5.QtGui import QPainter,QImage,QColor,QCursor
from PyQt5.QtCore import Qt,QTimer,QPointF
from ui.sprite_animator import SpriteAnimator
from ui.attention_preview import AttentionPreview


class Review(QWidget):
    def __init__(self):
        super().__init__();self.setWindowTitle('咕嘎 · 原画互动审核（不影响桌宠）');self.resize(520,540)
        self.a=SpriteAnimator(str(ROOT/'resources'),250);self.attention=AttentionPreview(seed=1)
        self.a._idle_expr_countdown=1000;self.a._idle_action_countdown=1000
        self.timer=QTimer(self);self.timer.setInterval(33);self.timer.timeout.connect(self.tick)
        layout=QVBoxLayout(self);layout.addWidget(QLabel('审核样机：偶尔关注鼠标，保持指定表情；120 秒后自动关闭。'))
        layout.addStretch(1);row=QHBoxLayout()
        for label,expr in [('日常','normal'),('困倦','sleepy'),('惊讶','surprised'),('委屈','sad')]:
            b=QPushButton(label);b.clicked.connect(lambda checked=False,e=expr:self.a.set_expression(e));row.addWidget(b)
        layout.addLayout(row);self.timer.start();QTimer.singleShot(120000,self.close)
    def tick(self):
        cursor=self.mapFromGlobal(QCursor.pos())
        x=(cursor.x()-self.width()/2)/180;y=(cursor.y()-180)/180
        self.a.look_at(*self.attention.update(1/30,x,y));self.a._tick();self.update()
    def paintEvent(self,event):
        p=QPainter(self);p.fillRect(self.rect(),QColor('#edf3f7'));self.a.draw(p,(self.width()-250)//2,80);p.end()
    def closeEvent(self,event):self.timer.stop();self.a.stop();event.accept()


def export():
    from PIL import Image,ImageDraw,ImageFont
    out=ROOT/'runtime/avatar-review-20261026';out.mkdir(exist_ok=True)
    a=SpriteAnimator(str(ROOT/'resources'),250);a._idle_expr_countdown=a._idle_action_countdown=1000
    controller=AttentionPreview(seed=1);frames=[]
    font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',16)
    for i in range(160):
        if i==40:a.set_expression('sleepy')
        x=-.8+1.6*i/159;y=.3*math.sin(i/20)
        a.look_at(*controller.update(.05,x,y));a._tick();a._tick()
        im=QImage(380,420,QImage.Format_RGBA8888);im.fill(QColor('#edf3f7'))
        p=QPainter(im);a.draw(p,65,48);p.setBrush(QColor('#4b7bd5'));p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(190+x*150,150+y*120),5,5);p.end()
        bits=im.bits();bits.setsize(im.byteCount());pil=Image.frombytes('RGBA',(380,420),bytes(bits)).convert('RGB')
        ImageDraw.Draw(pil).text((12,10),'原画关注鼠标 · '+('困倦保持' if i>=40 else '日常'),font=font,fill='#223244')
        frames.append(pil)
    assert a.expression=='sleepy'
    frames[0].save(out/'original-attention.gif',save_all=True,append_images=frames[1:],duration=50,loop=0)
    frames[110].save(out/'sleepy-held.png')
    print(str(out/'original-attention.gif'))

if __name__=='__main__':
    app=QApplication([])
    if '--window' in sys.argv:r=Review();r.show();sys.exit(app.exec_())
    export()
