"""Isolated real-renderer review; candidate clips never enter live manifest."""
import json
import os
from fractions import Fraction
from pathlib import Path
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from launcher import _prepare_qt
_prepare_qt()
import av
import numpy as np
from PIL import Image
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QImage, QPainter, QColor, QFont
from PyQt5.QtWidgets import QApplication
from ui.sprite_animator import SpriteAnimator

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT/'runtime/video-action-review-20261102'


def main():
    app = QApplication.instance() or QApplication([])
    # Stop all timers; render only. No main window, hooks, mic, tasks or network.
    pet = SpriteAnimator(str(ROOT/'resources'), 245)
    pet.stop()
    pet.set_expression('happy')
    pet._transition = 1.
    pet._idle_expr_countdown = 9999
    candidates = ['front-response-v3', 'look-up-step-v3']
    for name in candidates:
        folder = BASE/name
        meta = json.loads((folder/'metadata.json').read_text(encoding='utf-8'))
        pixmaps = []
        for path in sorted((folder/'frames').glob('*.png')):
            with Image.open(path) as image:
                pixmaps.append(pet._pil_to_pixmap(image.convert('RGBA')))
        # Explicit test-only memory injection. No approval files/asset loading
        # bypass is added to the application itself.
        pet.clips['task:review'] = dict(type='frames', frames=pixmaps, fps=30., loop=False)
        duration = 2.+len(pixmaps)/30
        samples = []
        with av.open(str(folder/'resident-transition-review.mp4'), 'w') as video:
            stream = video.add_stream('libx264', rate=30)
            stream.width, stream.height = 800, 480
            stream.pix_fmt = 'yuv420p'
            stream.options = {'crf':'18', 'preset':'fast'}
            for i in range(round(duration*30)):
                t = i/30
                image = QImage(800,480,QImage.Format_RGBA8888)
                image.fill(QColor('#e9edf2'))
                painter = QPainter(image)
                painter.fillRect(400,0,400,480,QColor('#252932'))
                painter.setFont(QFont('Arial',12))
                painter.setPen(QColor('#344258'))
                painter.drawText(20,30,'Resident -> candidate -> resident | REVIEW ONLY')
                pet._clip = 'task:review' if 1 <= t < 1+len(pixmaps)/30 else None
                pet._clip_frame = max(0, min(len(pixmaps)-1, int((t-1)*30)))
                pet.draw(painter,77,70)
                pet.draw(painter,477,70)
                painter.end()
                ptr = image.bits();ptr.setsize(image.sizeInBytes())
                pixels = np.frombuffer(ptr,dtype=np.uint8).reshape(480,800,4)
                frame = av.VideoFrame.from_ndarray(pixels[:,:,:3].copy(),format='rgb24')
                frame.pts=i;frame.time_base=Fraction(1,30)
                for packet in stream.encode(frame):video.mux(packet)
                if i in (29,30,31,round((1+len(pixmaps)/30)*30)-1,round((1+len(pixmaps)/30)*30)):
                    samples.append(image.copy())
            for packet in stream.encode():video.mux(packet)
        sheet=QImage(5*400,240,QImage.Format_RGBA8888);sheet.fill(QColor('#e9edf2'))
        painter=QPainter(sheet)
        for i,im in enumerate(samples):painter.drawImage(i*400,0,im.scaled(400,240,Qt.IgnoreAspectRatio,Qt.SmoothTransformation))
        painter.end();sheet.save(str(folder/'transition-contact.png'))
        pet._clip=None
        print(name, 'review rendered', flush=True)


if __name__=='__main__':main()
