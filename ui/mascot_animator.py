"""Original-art companions with expression bundles and bounded 2.5D motion."""
import json,math,time
from pathlib import Path
from PyQt5.QtCore import Qt,QTimer,QRectF,QPointF
from PyQt5.QtGui import QPixmap,QColor,QRadialGradient,QImageReader,QPainter
from ui.avatar_motion import AvatarMotion
ROOT=Path(__file__).resolve().parents[1]
EXPRESSIONS=('normal','happy','sleepy','surprised','sad','playful','angry','eating')
ALIASES={'cry':'sad','crying':'sad','eat':'eating','困倦':'sleepy','生气':'angry'}

def asset_for(appearance):
    base=ROOT/'resources/multiagent'
    if appearance=='dafish':
        cut=base/'dafish/avatar-cutout.png'
        return cut if cut.exists() else base/'dafish/avatar.gif'
    if appearance=='dora':
        cut=base/'dora/base-cutout.png'
        return cut if cut.exists() else base/'dora/reference.png'
    return ROOT/'resources/expressions/happy_transparent.png'

class MascotAnimator:
    def __init__(self,appearance='dora',display_width=185,manifest_path=None):
        self.appearance=appearance;self.display_width=max(80,int(display_width))
        self.expression='happy';self._context_expression=None
        self._prev_expression=self.expression;self._transition=1.
        self.action='none';self._presence=AvatarMotion()
        from core.task_animation import TaskAnimationDirector
        self._task_motion=TaskAnimationDirector();self._being_dragged=False;self._speaking=False
        self._last_tick=self._frame_started=time.monotonic()
        self._index=0;self._frames=[];self._durations=[];self._bundles={};self._fallbacks={}
        self._pad=math.ceil(self.display_width*.17);self._art_height=round(self.display_width*1.16)
        self.width=self.display_width+2*self._pad;self.height=self._art_height+2*self._pad
        self.on_update=None
        self.manifest_path=Path(manifest_path) if manifest_path else ROOT/'resources/multiagent'/appearance/'manifest.json'
        self._load_bundle();self._select(self.expression)
        self._timer=QTimer();self._timer.setInterval(33);self._timer.timeout.connect(self._tick)

    def _safe_asset(self,value):
        base=self.manifest_path.parent.resolve();path=(base/str(value)).resolve()
        if not path.is_relative_to(base):raise ValueError('Avatar assets must remain inside their bundle')
        if not path.is_file():raise FileNotFoundError(str(path))
        return path

    def _load_bundle(self):
        if self.manifest_path.exists():
            data=json.loads(self.manifest_path.read_text(encoding='utf-8-sig'))
            if data.get('schema')!=1:raise ValueError('Unsupported companion expression bundle')
            self._fallbacks=data.get('fallbacks',{})
            for expression,relative in data.get('expressions',{}).items():
                if expression in EXPRESSIONS:self._bundles[expression]=self._load_frames(self._safe_asset(relative))
            if not self._bundles:raise ValueError('Expression bundle is empty')
        else:self._bundles['normal']=self._load_frames(asset_for(self.appearance))
        self.available_expressions=tuple(self._bundles)

    def _load_frames(self,path):
        reader=QImageReader(str(path));frames=[];durations=[]
        while len(frames)<120:
            image=reader.read()
            if image.isNull():break
            pm=QPixmap.fromImage(image).scaled(self.display_width,self._art_height,Qt.KeepAspectRatio,Qt.SmoothTransformation)
            frames.append(pm);durations.append(max(35,min(250,reader.nextImageDelay() or 80)))
            if not reader.supportsAnimation() or not reader.canRead():break
        if not frames:raise ValueError('Cannot decode companion image: '+str(path))
        return frames,durations,str(path)

    def _resolve(self,expression):
        if expression in self._bundles:return expression
        fallback=self._fallbacks.get(expression)
        if fallback in self._bundles:return fallback
        return 'normal' if 'normal' in self._bundles else next(iter(self._bundles))

    def _select(self,expression):
        self._frames,self._durations,self.path=self._bundles[self._resolve(expression)]
        self._index=0;self._frame_started=time.monotonic()

    def start(self):self._last_tick=time.monotonic();self._timer.start()
    def stop(self):self._timer.stop()
    def look_at(self,x,y):
        self._presence.look_at(*((0.,0.) if self.expression=='sleepy' else (x,y)))
    def set_dragging(self,active,speed=0):
        self._being_dragged=bool(active);self._presence.set_dragging(False,0.)
    def set_work_state(self,state,task_id='main'):return self._task_motion.update(state,task_id)
    def set_speaking(self,active):self._speaking=bool(active)
    def user_interaction(self):
        if self.expression!='sleepy':return False
        self._context_expression=None;self.set_expression('happy');return True
    def set_expression(self,expression):
        expression=ALIASES.get(expression,expression)
        if expression not in EXPRESSIONS or (self._context_expression=='sleepy' and expression!='sleepy'):return False
        self._context_expression=None if expression=='normal' else expression
        if expression==self.expression:return True
        self._old_frame=self._frames[self._index];self._prev_expression=self.expression
        self.expression=expression;self._select(expression);self._transition=0.
        if expression=='sleepy':self._presence.look_at(0.,0.)
        return True

    @property
    def sunglasses(self):return self._presence.sunglasses
    @sunglasses.setter
    def sunglasses(self,value):
        self._presence.sunglasses=bool(value);self._presence.sunglasses_until=0.
    @property
    def dancing(self):return self._presence.dancing
    @dancing.setter
    def dancing(self,value):self._presence.dancing=bool(value)
    def set_music_stage(self,active):
        self._presence.dancing=bool(active);self._presence.sunglasses=bool(active)
        self._presence.sunglasses_until=0.

    def trigger_action(self,name):
        from core.embodiment import ALIASES as ACTION_ALIASES
        name=ACTION_ALIASES.get(name,name)
        if name in ('think_chin','scratch_head'):name='tilt'
        self._presence.trigger_action('spin' if name=='perspective_spin' else name)
        self.action=self._presence.action

    def advance(self,dt):
        """Time-based motion; deterministic bounded step for visual review."""
        blocked=(self.expression=='sleepy' or self._being_dragged or self._speaking or self.dancing or self.action!='none')
        event=self._task_motion.poll(blocked)
        if event:self.trigger_action(event['gesture'])
        dt=max(0.,min(.1,float(dt)));self._presence.advance(dt)
        self.action=self._presence.action;self._transition=min(1.,self._transition+dt/.16)
    def _tick(self):
        now=time.monotonic();self.advance(now-self._last_tick);self._last_tick=now
        if len(self._frames)>1 and (now-self._frame_started)*1000>=self._durations[self._index]:
            self._index=(self._index+1)%len(self._frames);self._frame_started=now
        if self.on_update:self.on_update()
    def _draw_frame(self,p,frame,opacity):
        p.setOpacity(opacity);p.drawPixmap(round(-frame.width()/2),-frame.height(),frame)
    def draw(self,p,x,y):
        pose=self._presence.pose;t=self._presence.time;gain=.28 if self.expression=='sleepy' else 1.
        phase=min(1.,self._presence.elapsed/max(.01,self._presence.DURATIONS.get(self.action,1.)))
        envelope=math.sin(math.pi*phase)**2 if self.action!='none' else 0.
        # Only a front texture exists: shallow turns preserve the original art.
        # Never invent a fake back, rotate the card upside-down or squash the face.
        turn=math.sin(phase*2*math.pi)*envelope if self.action=='spin' else 0.
        sway=gain*(math.sin(t*.7)*1.4+pose.side*22)
        lift=max(-8.,min(28.,pose.lift*72))*gain
        roll=max(-7.,min(7.,pose.roll*.36+pose.head_roll*.16+turn*6.))
        sx=1+math.sin(t*2.2)*.004*gain-abs(turn)*.055
        sy=1+math.sin(t*2.2)*.006*gain
        cx=x+self.width/2+sway+pose.head_yaw*.12*gain;baseline=y+self._pad+self._art_height
        p.save()
        gradient=QRadialGradient(QPointF(cx,baseline+3),self.display_width*.42)
        gradient.setColorAt(0,QColor(43,47,65,max(7,int(35-abs(lift)*.8))))
        gradient.setColorAt(1,QColor(43,47,65,0))
        p.setPen(Qt.NoPen);p.setBrush(gradient)
        p.drawEllipse(QRectF(cx-self.display_width*.36,baseline-2,self.display_width*.72,11))
        p.translate(cx,baseline-lift);p.rotate(roll)
        p.shear(pose.head_yaw*.00045*gain,pose.head_pitch*.00016*gain);p.scale(sx,sy)
        p.setRenderHint(QPainter.SmoothPixmapTransform,True)
        if self._transition<1 and hasattr(self,'_old_frame'):self._draw_frame(p,self._old_frame,1-self._transition)
        self._draw_frame(p,self._frames[self._index],self._transition)
        if self.sunglasses:
            frame=self._frames[self._index];w=frame.width()
            ey=-frame.height()*(.55 if self.appearance=='dora' else .64)
            lens_w=w*.24;lens_h=w*.09;gap=w*.025
            p.setOpacity(1.);p.setPen(Qt.NoPen);p.setBrush(QColor('#101920'))
            p.drawEllipse(QRectF(-gap-lens_w,ey-lens_h/2,lens_w,lens_h))
            p.drawEllipse(QRectF(gap,ey-lens_h/2,lens_w,lens_h))
            p.fillRect(QRectF(-gap,ey-1,gap*2,2),QColor('#101920'))
        p.restore()
