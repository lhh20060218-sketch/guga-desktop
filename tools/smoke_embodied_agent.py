"""Render existing pet art as a real head gesture; no model/image API needed."""
import io
import os
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
os.environ['QT_QPA_PLATFORM']='offscreen'
from launcher import _prepare_qt
_prepare_qt()
from PyQt5.QtCore import Qt,QBuffer,QIODevice
from PyQt5.QtGui import QImage,QPainter,QColor,QFontDatabase,QFont
from PyQt5.QtWidgets import QApplication
from PIL import Image
from ui.sprite_animator import SpriteAnimator

app=QApplication([])
QFontDatabase.addApplicationFont('C:/Windows/Fonts/msyh.ttc')
anim=SpriteAnimator(str(ROOT/'resources'),250)
def frame():
    image=QImage(anim.width,anim.height,QImage.Format_ARGB32);image.fill(Qt.transparent)
    painter=QPainter(image);anim._draw_sprite(painter,0,0,anim._src);painter.end()
    return image
neutral=frame();frames=[]
anim.trigger_action('head_shake')
for index in range(42):
    anim._tick_action();image=frame();frames.append(image)
    assert image.copy(0,int(anim.height*.72),anim.width,int(anim.height*.25))==neutral.copy(0,int(anim.height*.72),anim.width,int(anim.height*.25)), 'Body should remain anchored'
assert any(image!=neutral for image in frames)
assert anim.action=='none'
output=ROOT/'runtime/chat';output.mkdir(parents=True,exist_ok=True)
canvas=QImage(anim.width*3,anim.height+42,QImage.Format_ARGB32);canvas.fill(QColor('#edf0f7'))
p=QPainter(canvas);p.setPen(QColor('#3a3654'));p.setFont(QFont('Microsoft YaHei UI',12))
for n,index in enumerate((4,12,21)):
    p.drawText(n*anim.width+20,30,('向左摇头','回摆','向右摇头')[n]);p.drawImage(n*anim.width,42,frames[index])
p.end();canvas.save(str(output/'guga-gesture-preview.png'))
pil=[]
for image in frames:
    buffer=QBuffer();buffer.open(QIODevice.WriteOnly);image.save(buffer,'PNG')
    foreground=Image.open(io.BytesIO(bytes(buffer.data()))).convert('RGBA')
    background=Image.new('RGBA',foreground.size,'#edf0f7');background.alpha_composite(foreground)
    pil.append(background.convert('RGB'))
pil[0].save(output/'guga-head-shake.gif',save_all=True,append_images=pil[1:],duration=33,loop=0)
print('PASS: real head deformation across 42 frames; lower body anchored; animation returns to idle')
print(str(output/'guga-gesture-preview.png'))
