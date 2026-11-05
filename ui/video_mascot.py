"""DSH-independent Qt host for upstream dsh-pet's original transparent clips.

Rendering, voice, memory and menus remain owned by Guga. A bounded decoder
queue keeps file/codec work outside the Qt event loop; stale generations are
discarded. VP9 must use libvpx-vp9, since FFmpeg's native decoder drops alpha.
"""
import json
import logging
import queue
import random
import threading
import time
from pathlib import Path

from PyQt5.QtCore import QRectF, Qt
from PyQt5.QtGui import QImage

from ui.mascot_animator import MascotAnimator
from ui.pet_physics import squash_scale

PACK = Path(__file__).resolve().parents[1]/'resources/multiagent/dafish/dsh-pet'


def decode_clip(path, width, cancel, frames):
    """Worker only owns QImages, never QPixmaps or GUI objects."""
    def deliver(item):
        while not cancel.is_set():
            try:
                frames.put(item, timeout=.05)
                return True
            except queue.Full:
                pass
        return False
    try:
        import av
        with av.open(str(path)) as container:
            stream = container.streams.video[0]
            codec = av.CodecContext.create('libvpx-vp9', 'r')
            codec.thread_count = 2
            duration = 1/float(stream.average_rate or 24)
            for packet in container.demux(stream):
                if cancel.is_set():
                    return
                for frame in codec.decode(packet):
                    if cancel.is_set():
                        return
                    rgba = frame.to_ndarray(format='rgba')
                    # Lossy VP9 alpha can leave value 1 in the green-screen void.
                    # Clear invisible pixels so the native hit-test has no halo.
                    rgba[rgba[:,:,3] <= 3] = 0
                    h, w = rgba.shape[:2]
                    image = QImage(rgba.data, w, h, rgba.strides[0], QImage.Format_RGBA8888).copy()
                    image = image.scaledToWidth(width, Qt.SmoothTransformation)
                    if not deliver(('frame', image, duration)):
                        return
        deliver(('end', None, 0))
    except Exception as exc:
        deliver(('error', type(exc).__name__+': '+str(exc), 0))


class VideoMascotAnimator(MascotAnimator):
    """Original asset choreography, native menus and per-agent identity."""
    def __init__(self, display_width=225):
        import av  # Validate optional playback dependency before replacing fallback.
        av.CodecContext.create('libvpx-vp9', 'r')
        self.pack = json.loads((PACK/'manifest.json').read_text(encoding='utf-8'))
        self.pools = self.pack['animations']
        self._video_frame = None
        self._cancel = threading.Event()
        self._workers = []
        self._queue = queue.Queue(6)
        self._generation = 0
        self._running = False
        self._mode = 'normal'
        self._dragging = False
        self._roaming = False
        self._speaking = False
        self._held_expression = None
        self.current_clip = ''
        self.decode_error = ''
        self.on_move = None
        self._random = random.Random()
        self._tap_time = -1.
        self._tap_amount = .86
        super().__init__('dafish', display_width)
        # Preserve the entire source canvas: props, hair and feet must not crop.
        self.width = round(display_width*640/260)
        self.height = round(self.width*360/640)
        self.available_expressions = ('normal','happy','sad','sleepy','surprised','playful','angry','eating')
        self._timer.setInterval(16)

    def start(self):
        self._running = True
        super().start()
        self._play(self.pools['idle'][0], 'normal')

    def stop(self):
        self._running = False
        super().stop()
        self._cancel.set()
        for worker in self._workers:
            worker.join(.15)
        self._workers = [w for w in self._workers if w.is_alive()]

    def _play(self, name, mode=None):
        path = PACK/(name+'.webm')
        if name not in {Path(x).stem for x in self.pack['assets']} or not path.is_file():
            return False
        if mode is not None:
            self._mode = mode
        self.current_clip, self.path = name, str(path)
        self._cancel.set()
        self._cancel = threading.Event()
        self._queue = queue.Queue(6)
        self._generation += 1
        self._due = 0.
        self._workers = [w for w in self._workers if w.is_alive()]
        worker = threading.Thread(target=decode_clip, args=(path,self.width,self._cancel,self._queue),
                                  name='pet-vp9-alpha', daemon=True)
        self._workers.append(worker)
        worker.start()
        return True

    def play_clip(self, name):
        if self.expression == 'sleepy':
            return False
        self._held_expression = None
        return self._play(name, 'once')

    def tap(self, amount=.86):
        self._tap_time, self._tap_amount = time.monotonic(), amount

    def click(self):
        self.tap()
        self._play(self._random.choice(self.pools['clicks']), 'once')

    def user_interaction(self):
        if self.expression != 'sleepy':
            return False
        self.expression = 'happy'
        self._context_expression = self._held_expression = None
        if self._running:
            self._play(self.pools['sleep'][0]['end'][0], 'wake')
        return True

    def set_expression(self, expression):
        from ui.mascot_animator import ALIASES
        expression = ALIASES.get(expression, expression)
        if expression not in self.available_expressions:
            return False
        if self.expression == 'sleepy' and expression != 'sleepy':
            return False
        if expression == self.expression and self.current_clip:
            return True
        self.expression = expression
        self._context_expression = None if expression == 'normal' else expression
        self._held_expression = expression if expression in ('sleepy','sad','angry','eating') else None
        if not self._running:
            return True
        clips = {'normal':self.pools['idle'][0],'happy':self.pools['clicks'][0],
                 'playful':'原地专心玩魔方','sad':'工作状态-垂头叹气冒汗',
                 'angry':'点击回应-傲娇生气','surprised':'被吓一跳','eating':'吃白饭',
                 'sleepy':self.pools['sleep'][0]['start'][0]}
        return self._play(clips[expression], 'sleep_start' if expression=='sleepy' else 'once')

    def set_dragging(self, active, speed=0):
        # Ordinary positioning only; original suspension clip remains menu-playable.
        self._dragging = bool(active)

    def set_speaking(self, active):
        if bool(active) == self._speaking:
            return
        self._speaking = bool(active)
        if self._running and self.expression != 'sleepy' and not self._dragging:
            self._play(self.pools['events']['whisper'][0] if active else self.pools['idle'][0],
                       'speech' if active else 'normal')

    def set_work_state(self, state):
        if self.expression == 'sleepy' or self._dragging or self._speaking:
            return False
        states = ('thinking','working','result','waiting','success','error')
        if state not in states:
            return False
        clip=self.pools['events']['workStatus'][states.index(state)]
        if clip==self.current_clip:return True
        return self._play(clip, 'once')

    def trigger_action(self, name):
        if self.expression == 'sleepy':
            return
        mapping = {'spin':'小幅度原地360度旋转展示','perspective_spin':'小幅度原地360度旋转展示',
                   'sneak_peek':'东张西望','peek':'东张西望','wave':'点击回应-元气挥手',
                   'bounce':'点击回应-开心跃动','dance':'轻快摇摆舞','stop_dance':self.pools['idle'][0],
                   'nod':'女仆屈膝礼仪','eat':'吃白饭'}
        super().trigger_action(name)
        if name in mapping:
            self._play(mapping[name], 'dance' if name=='dance' else 'once')

    def _ended(self):
        if self._mode in ('sleep_start','sleep_loop'):
            self._play(self.pools['sleep'][0]['loop'][0], 'sleep_loop')
        elif self._dragging or self._mode in ('dance','speech'):
            self._play(self.current_clip)
        elif self._held_expression:
            # Keep the settled end frame. No random animation may undo this.
            self._mode = 'held'
        elif self._mode in ('once','wake','held'):
            self._play(self.pools['idle'][0], 'normal')
        else:
            # Upstream categories, bounded idle cadence and no repeated action.
            if self._roaming and self.on_move and self._random.random() < .12:
                move = self._random.choice(self.pools['moves']['actions'])
                self._play(move['name'], 'once')
                params = dict(self.pools['moves']['default'], **move.get('params', {}))
                self.on_move(self._random.choice((-1,1))*self._random.uniform(params['minDist'],params['maxDist']),
                             10.,params['leadSec'],params['tailSec'])
            elif self._random.random() < .65:
                categories = self.pools['categories']
                pool = self._random.choices(categories, weights=[c['weight'] for c in categories])[0]['actions']
                choices = [n for n in pool if n != self.current_clip]
                self._play(self._random.choice(choices or pool), 'once')
            else:
                self._play(self.pools['idle'][0], 'normal')

    def _tick(self):
        now = time.monotonic()
        self.advance(now-self._last_tick)
        self._last_tick = now
        for _ in range(4):
            if now < self._due:
                break
            try:
                kind, data, duration = self._queue.get_nowait()
            except queue.Empty:
                break
            if kind == 'frame':
                self._video_frame = data
                self._due = max(self._due, now-.1)+duration
            elif kind == 'end':
                self._ended()
                break
            else:
                self.decode_error = data
                logging.warning('Pet video: %s', data)
                # Stop on failure instead of creating a retry/decode loop.
                self.stop()
                break
        if self.on_update:
            self.on_update()

    def draw(self, painter, x, y):
        if self._video_frame is None:
            frame = self._frames[self._index]
            painter.drawPixmap(round(x+(self.width-frame.width())/2),
                               round(y+self.height-frame.height()), frame)
            return
        painter.save()
        age = time.monotonic()-self._tap_time
        sy = squash_scale(age/.22, self._tap_amount) if 0 <= age < .22 else 1.
        # Videos carry their own depth, hair and body motion; no fake 3D card turn.
        painter.translate(x+self.width/2, y+self.height*.9)
        painter.scale(1+(1-sy)*.5, sy)
        painter.translate(-self.width/2, -self.height*.9)
        painter.drawImage(QRectF(0,0,self.width,self.height), self._video_frame)
        if self.sunglasses:
            from PyQt5.QtGui import QColor
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor('#101920'))
            w, h = self.width, self.height
            painter.drawRoundedRect(QRectF(w*.436,h*.42,w*.06,h*.041),4,4)
            painter.drawRoundedRect(QRectF(w*.504,h*.42,w*.06,h*.041),4,4)
            painter.drawRect(QRectF(w*.494,h*.435,w*.012,h*.006))
        painter.restore()
