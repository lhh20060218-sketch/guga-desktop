"""Six-second deterministic review of installed task-event choreography."""
import os,json
from pathlib import Path
from fractions import Fraction
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from launcher import _prepare_qt
_prepare_qt()
import av,numpy as np
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QImage,QPainter,QColor,QFont
from ui.sprite_animator import SpriteAnimator
from core.task_animation import TaskAnimationDirector

ROOT=Path(__file__).resolve().parents[1]


def main():
    app=QApplication.instance() or QApplication([])
    pet=SpriteAnimator(str(ROOT/'resources'),245);pet.stop();pet.set_expression('happy')
    clock=[0.];pet._task_motion=TaskAnimationDirector(lambda:clock[0])
    out=ROOT/'runtime/video-action-review-20261102/installed-automatic-preview.mp4'
    seen=[];old=None
    with patch('ui.sprite_animator.time.monotonic',side_effect=lambda:clock[0]),av.open(str(out),'w') as video:
        stream=video.add_stream('libx264',rate=30);stream.width=800;stream.height=480;stream.pix_fmt='yuv420p'
        stream.options={'crf':'18','preset':'fast'}
        for i in range(180):
            clock[0]=i/30
            if i==3:pet.set_work_state('working','demo')
            if i==120:pet.set_work_state('cancelled','demo')
            pet._tick()
            if pet._clip!=old:
                seen.append(dict(second=round(clock[0],2),clip=pet._clip));old=pet._clip
            image=QImage(800,480,QImage.Format_RGBA8888);image.fill(QColor('#e9edf2'))
            p=QPainter(image);p.fillRect(400,0,400,480,QColor('#252932'))
            p.setPen(QColor('#344258'));p.setFont(QFont('Arial',12))
            p.drawText(20,30,'Installed clip / automatic task event / offline review')
            pet.draw(p,77,70);pet.draw(p,477,70);p.end()
            ptr=image.bits();ptr.setsize(image.sizeInBytes());data=np.frombuffer(ptr,dtype=np.uint8).reshape(480,800,4)
            frame=av.VideoFrame.from_ndarray(data[:,:,:3].copy(),format='rgb24');frame.pts=i;frame.time_base=Fraction(1,30)
            for packet in stream.encode(frame):video.mux(packet)
        for packet in stream.encode():video.mux(packet)
    pet.stop();(out.with_suffix('.json')).write_text(json.dumps(dict(events=seen,offline_demo=True),indent=2),encoding='utf-8')
    print(json.dumps(dict(events=seen,frames=180,seconds=6)))


if __name__=='__main__':main()
