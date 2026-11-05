"""Finite 30fps review of the real renderer's automatic task gestures.

No microphone, network, keyboard hooks or live task. Produces an MP4 and timing
record so a successful test cannot be confused with new external art approval.
"""
import os,json,random
from fractions import Fraction
from pathlib import Path
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from launcher import _prepare_qt
_prepare_qt()
import av,numpy as np
from PyQt5.QtCore import QRectF,Qt
from PyQt5.QtGui import QImage,QPainter,QColor,QFont
from PyQt5.QtWidgets import QApplication
from ui.sprite_animator import SpriteAnimator
from core.task_animation import TaskAnimationDirector

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'runtime/task-motion-review-20261102'


def main():
    app=QApplication.instance() or QApplication([]);random.seed(59)
    OUT.mkdir(parents=True,exist_ok=True)
    a=SpriteAnimator(str(ROOT/'resources'),260);a.set_expression('happy')
    clock=[0.];a._task_motion=TaskAnimationDirector(lambda:clock[0])
    sequence=[(0.,'thinking','摸下巴 / 挠头（演示）'),(15.,'working','工具开始执行'),
              (18.5,'waiting','等待外部结果'),(22.,'success','已核验完成（演示）')]
    index=0;label='';events=[];count=0;contact=[]
    with av.open(str(OUT/'automatic-task-motion-30fps.mp4'),'w') as video:
        stream=video.add_stream('libx264',rate=30)
        stream.width=640;stream.height=480;stream.pix_fmt='yuv420p'
        stream.options={'crf':'20','preset':'fast'}
        for frame_index in range(26*30):
            clock[0]=frame_index/30
            if index<len(sequence) and clock[0]>=sequence[index][0]:
                _,state,label=sequence[index];a.set_work_state(state,'demo');index+=1
            a._tick()
            if count!=a._task_motion.count:
                count=a._task_motion.count
                events.append(dict(second=round(clock[0],3),state=a._task_motion.last_state,gesture=a.action))
            canvas=QImage(640,480,QImage.Format_RGBA8888);canvas.fill(QColor('#eef2f6'))
            p=QPainter(canvas);p.setFont(QFont('Microsoft YaHei UI',15));p.setPen(QColor('#24354b'))
            p.drawText(28,38,'咕嘎任务动作 · 原画 / 30 FPS')
            p.setFont(QFont('Microsoft YaHei UI',11));p.drawText(28,67,'离线演示：'+label)
            a.draw(p,185,102)
            p.setFont(QFont('Microsoft YaHei UI',10));p.drawText(28,454,'只演示自动触发；未替换原画，未接入低帧率候选素材。');p.end()
            ptr=canvas.bits();ptr.setsize(canvas.sizeInBytes())
            pixels=np.frombuffer(ptr,dtype=np.uint8).reshape(480,640,4)
            frame=av.VideoFrame.from_ndarray(pixels[:,:,:3].copy(),format='rgb24')
            frame.pts=frame_index;frame.time_base=Fraction(1,30)
            for packet in stream.encode(frame):video.mux(packet)
            if frame_index in (70,95,370,390,470,500,580,700):contact.append(canvas.copy())
        for packet in stream.encode():video.mux(packet)
    sheet=QImage(1280,480,QImage.Format_RGBA8888);sheet.fill(QColor('#eef2f6'));p=QPainter(sheet)
    for i,im in enumerate(contact):p.drawImage(QRectF((i%4)*320,(i//4)*240,320,240),im)
    p.end();sheet.save(str(OUT/'contact.png'))
    (OUT/'events.json').write_text(json.dumps(dict(fps=30,seconds=26,external_assets_installed=False,events=events),ensure_ascii=False,indent=2),encoding='utf-8')
    a.stop();print(json.dumps(dict(video=str(OUT/'automatic-task-motion-30fps.mp4'),events=events),ensure_ascii=True))

if __name__=='__main__':main()
