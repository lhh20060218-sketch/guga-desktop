"""Offline visual review of the actual Qt renderer and original alpha clips."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import json
from pathlib import Path
import av
from launcher import _prepare_qt
_prepare_qt()
from PyQt5.QtCore import QRectF,Qt
from PyQt5.QtGui import QImage,QPainter,QColor,QFont
from PyQt5.QtWidgets import QApplication
from ui.video_mascot import VideoMascotAnimator,PACK
from ui.sprite_animator import SpriteAnimator
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'runtime/dsh-pet-upgrade'


def frames(name,count=96,skip=0):
    with av.open(str(PACK/(name+'.webm'))) as container:
        codec=av.CodecContext.create('libvpx-vp9','r');i=0
        for packet in container.demux(video=0):
            for frame in codec.decode(packet):
                if i>=skip:
                    rgba=frame.to_ndarray(format='rgba');h,w=rgba.shape[:2]
                    yield QImage(rgba.data,w,h,rgba.strides[0],QImage.Format_RGBA8888).copy()
                i+=1
                if i>=skip+count:return


def main():
    app=QApplication([]);OUT.mkdir(exist_ok=True,parents=True)
    clips=['待机呼吸休闲','小幅度原地360度旋转展示','吃白饭','被鼠标拖拽悬空反馈','睡觉-循环','工作状态-忙碌点按']
    a=VideoMascotAnimator(210)
    sheet=QImage(1200,720,QImage.Format_ARGB32);sheet.fill(QColor('#edf3f7'))
    p=QPainter(sheet);p.setFont(QFont('Microsoft YaHei',12))
    for i,name in enumerate(clips):
        x=(i%3)*400;y=(i//3)*360
        p.setPen(Qt.NoPen);p.setBrush(QColor('#ffffff'));p.drawRoundedRect(QRectF(x+8,y+8,384,340),18,18)
        a._video_frame=next(frames(name,1,72))
        p.save();p.translate(x+200-a.width*.36,y+16);p.scale(.72,.72);a.draw(p,0,0);p.restore()
        p.setPen(QColor('#3d5369'));p.drawText(x+16,y+326,name)
    p.end();sheet.save(str(OUT/'native-animation-review.png'))
    g=SpriteAnimator(str(ROOT/'resources'),display_width=210);g.stop()
    images=[]
    for i,im in enumerate(frames('小幅度原地360度旋转展示',240)):
        if i%3:continue
        a._video_frame=im;g._tick()
        if i==24:g.tap()
        shot=QImage(900,420,QImage.Format_RGBA8888);shot.fill(QColor('#edf3f7'))
        painter=QPainter(shot);painter.setFont(QFont('Microsoft YaHei',12));painter.setPen(QColor('#3d5369'))
        painter.drawText(24,32,'咕嘎：保留原画 / 点击轻回弹');painter.drawText(410,32,'大肥鱼：原版透明转身动画')
        g.draw(painter,90,90);a.draw(painter,350,70);painter.end()
        ptr=shot.bits();ptr.setsize(shot.sizeInBytes())
        images.append(Image.frombytes('RGBA',(shot.width(),shot.height()),bytes(ptr)).convert('RGB'))
    images[0].save(OUT/'native-motion-review.gif',save_all=True,append_images=images[1:],duration=125,loop=0)
    for im in images:im.close()
    a.stop();g.stop()
    print(json.dumps({'sheet':str(OUT/'native-animation-review.png'),'motion':str(OUT/'native-motion-review.gif')},ensure_ascii=False))

if __name__=='__main__':main()
