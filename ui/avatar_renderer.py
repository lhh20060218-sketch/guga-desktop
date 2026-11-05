"""Blender mesh → offscreen OpenGL → transparent Qt image.

No embedded GL child window: menus, bubbles and dragging remain native Qt.
"""
import gzip
import json
import math
import time
from pathlib import Path
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import (QImage, QSurfaceFormat, QOpenGLContext, QOffscreenSurface,
                        QOpenGLFramebufferObject, QOpenGLFramebufferObjectFormat)
from ui.avatar_motion import AvatarMotion

try:
    from OpenGL import GL
    from OpenGL.GLU import gluPerspective
    _GL_ERROR = None
except ImportError as exc:
    _GL_ERROR = str(exc)

ROOT = Path(__file__).resolve().parents[1]


class GLPenguinRenderer:
    EXPRESSIONS = ('normal', 'happy', 'sleepy', 'surprised', 'sad', 'playful')

    def __init__(self, display_width=250, pixel_ratio=None):
        from PyQt5.QtWidgets import QApplication
        self.width = display_width
        self.height = round(display_width * 326 / 227)
        screen = QApplication.primaryScreen()
        ratio = pixel_ratio or (screen.devicePixelRatio() if screen else 1.)
        self._ratio = min(2., max(1., ratio))
        self.on_update = None
        self.motion = AvatarMotion()
        self.expression = 'normal'
        self._ctx = self._surface = self._fbo = None
        self._lists, self._textures = [], {}
        self._ready = False
        self._cached_img = None
        self.error = _GL_ERROR
        self._clip = None
        self._last_tick = None
        self._render_ms = 0.
        self._timer = QTimer()
        self._timer.setInterval(33)
        self._timer.setTimerType(Qt.PreciseTimer)
        self._timer.timeout.connect(self._tick)

    @property
    def available(self):
        if not self._ready and not self._init_gl():
            return False
        if self._cached_img is None:
            self._render_cached()
        return self._cached_img is not None

    def _init_gl(self):
        if self._ready: return True
        if _GL_ERROR: return False
        try:
            with gzip.open(ROOT / 'resources/models/guga_3d/avatar.mesh.json.gz', 'rt', encoding='utf-8') as f:
                data = json.load(f)
            if data.get('version') != 1: raise ValueError('不支持的模型版本')
            self._pivots = data['pivots']
            self._pivots['pendant'] = [0.03, -0.08, 0.66]
            self._projection = data.get('projection', 'perspective')
            fmt = QSurfaceFormat()
            fmt.setVersion(2, 1)
            fmt.setProfile(QSurfaceFormat.CompatibilityProfile)
            fmt.setAlphaBufferSize(8)
            fmt.setDepthBufferSize(24)
            self._ctx = QOpenGLContext()
            self._ctx.setFormat(fmt)
            if not self._ctx.create(): raise RuntimeError('OpenGL context creation failed')
            self._surface = QOffscreenSurface()
            self._surface.setFormat(self._ctx.format())
            self._surface.create()
            if not self._surface.isValid() or not self._ctx.makeCurrent(self._surface):
                raise RuntimeError('OpenGL offscreen surface unavailable')
            fbo_fmt = QOpenGLFramebufferObjectFormat()
            fbo_fmt.setAttachment(QOpenGLFramebufferObject.CombinedDepthStencil)
            fbo_fmt.setSamples(4)
            self._fbo = QOpenGLFramebufferObject(round(self.width * self._ratio), round(self.height * self._ratio), fbo_fmt)
            if not self._fbo.isValid(): raise RuntimeError('Framebuffer unavailable')
            for mesh in data['meshes']:
                handle = GL.glGenLists(1)
                GL.glNewList(handle, GL.GL_COMPILE)
                GL.glBegin(GL.GL_TRIANGLES)
                v = mesh['vertices']
                for i in range(0, len(v), 8):
                    GL.glNormal3f(*v[i+3:i+6])
                    if mesh['textured']: GL.glTexCoord2f(*v[i+6:i+8])
                    GL.glVertex3f(*v[i:i+3])
                GL.glEnd()
                GL.glEndList()
                group = 'pendant' if mesh['name'].startswith('Chain link') else mesh['group']
                self._lists.append((handle, group, mesh['color'], mesh['textured']))
            for expr in self.EXPRESSIONS:
                path = ROOT / 'resources/expressions' / (expr + '_transparent.png')
                img = QImage(str(path)).convertToFormat(QImage.Format_RGBA8888).mirrored()
                if img.isNull(): continue
                bits = img.bits()
                bits.setsize(img.byteCount())
                handle = GL.glGenTextures(1)
                GL.glBindTexture(GL.GL_TEXTURE_2D, handle)
                for key in (GL.GL_TEXTURE_MIN_FILTER, GL.GL_TEXTURE_MAG_FILTER):
                    GL.glTexParameteri(GL.GL_TEXTURE_2D, key, GL.GL_LINEAR)
                for key in (GL.GL_TEXTURE_WRAP_S, GL.GL_TEXTURE_WRAP_T):
                    GL.glTexParameteri(GL.GL_TEXTURE_2D, key, GL.GL_CLAMP_TO_EDGE)
                GL.glTexImage2D(GL.GL_TEXTURE_2D, 0, GL.GL_RGBA, img.width(), img.height(), 0,
                                GL.GL_RGBA, GL.GL_UNSIGNED_BYTE, bytes(bits))
                self._textures[expr] = handle
            self._ctx.doneCurrent()
            self._ready = True
            return True
        except Exception as exc:
            self.error = str(exc)
            self.close()
            return False

    def start(self):
        if self.available:
            self._last_tick = time.perf_counter()
            self._timer.start()

    def stop(self):
        self._timer.stop()

    def close(self):
        self.stop()
        if self._ctx and self._surface and self._ctx.makeCurrent(self._surface):
            for handle, *_ in self._lists: GL.glDeleteLists(handle, 1)
            if self._textures: GL.glDeleteTextures(list(self._textures.values()))
            self._fbo = None
            self._ctx.doneCurrent()
        self._lists.clear()
        self._textures.clear()
        self._surface = self._ctx = None
        self._ready = False

    def set_expression(self, expr):
        self.expression = expr if expr in self.EXPRESSIONS else 'normal'

    def update_mood(self, emoji):
        self.set_expression({'😢':'sad', '😭':'sad', '😴':'sleepy', '😄':'happy', '😊':'happy', '😱':'surprised'}.get(emoji, 'normal'))

    def trigger_action(self, action): self.motion.trigger_action(action)
    def trigger_bounce(self): self.trigger_action('bounce')
    def set_music_stage(self, active):
        self.motion.dancing=bool(active);self.motion.sunglasses=bool(active)
        self.motion.sunglasses_until=0.
    def look_at(self, x, y): self.motion.look_at(x, y)
    def set_dragging(self, active, speed=0.): self.motion.set_dragging(active, speed)

    @property
    def mouth_open(self): return self.motion.mouth_open
    @mouth_open.setter
    def mouth_open(self, value): self.motion.mouth_open = float(value)
    @property
    def sunglasses(self): return self.motion.sunglasses
    @sunglasses.setter
    def sunglasses(self, value): self.motion.sunglasses = bool(value)
    @property
    def _sunglasses_until(self): return self.motion.sunglasses_until
    @_sunglasses_until.setter
    def _sunglasses_until(self, value): self.motion.sunglasses_until = value
    @property
    def dancing(self): return self.motion.dancing
    @dancing.setter
    def dancing(self, active): self.motion.dancing = bool(active)

    def set_talking(self, active):
        if not active: self.mouth_open = 0
    @property
    def sticker_names(self): return []
    def play_sticker(self, name): self.trigger_action('bounce')
    def play_clip(self, name, loop=None):
        self._clip = name
        if name in ('jump', 'wave'): self.trigger_action('bounce' if name == 'jump' else name)
    def stop_clip(self): self._clip = None
    @property
    def active_clip(self): return self._clip

    def _tick(self):
        now = time.perf_counter()
        dt = now - self._last_tick if self._last_tick else 1/30
        self._last_tick = now
        self.motion.advance(dt)
        self._render_cached()
        if self.on_update: self.on_update()

    def _render_cached(self):
        try: self._cached_img = self.render()
        except Exception as exc:
            self.error, self._cached_img = str(exc), None

    def paint_image(self): return self._cached_img

    def _pivot_rotate(self, group, x=0, y=0, z=0):
        pivot = self._pivots[group]
        GL.glTranslatef(*pivot)
        GL.glRotatef(z, 0, 0, 1)
        GL.glRotatef(y, 0, 1, 0)
        GL.glRotatef(x, 1, 0, 0)
        GL.glTranslatef(*(-v for v in pivot))

    def render(self):
        if not self._ready and not self._init_gl(): return None
        start = time.perf_counter()
        if not self._ctx.makeCurrent(self._surface): raise RuntimeError('OpenGL context lost')
        try:
            self._fbo.bind()
            GL.glViewport(0, 0, self._fbo.width(), self._fbo.height())
            GL.glClearColor(0, 0, 0, 0)
            GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)
            for flag in (GL.GL_DEPTH_TEST, GL.GL_NORMALIZE, GL.GL_MULTISAMPLE, GL.GL_BLEND): GL.glEnable(flag)
            GL.glDepthFunc(GL.GL_LEQUAL)
            GL.glBlendFuncSeparate(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA, GL.GL_ONE, GL.GL_ONE_MINUS_SRC_ALPHA)
            GL.glMatrixMode(GL.GL_PROJECTION)
            GL.glLoadIdentity()
            if self._projection == 'orthographic':
                half_y = 1.80
                half_x = half_y * self.width / self.height
                GL.glOrtho(-half_x, half_x, -half_y, half_y, .1, 30)
            else:
                gluPerspective(32, self.width / self.height, .1, 30)
            GL.glMatrixMode(GL.GL_MODELVIEW)
            GL.glLoadIdentity()
            GL.glTranslatef(0, -.06, -6.3)
            framing = self.motion.pose.framing
            GL.glScalef(framing, framing, framing)
            # A soft, ground-anchored contact shadow gives the feet weight.
            GL.glDisable(GL.GL_LIGHTING)
            GL.glDepthMask(False)
            pose = self.motion.pose
            # Contact shadow follows the mass and softens when the pet jumps.
            shadow_size = 1 + max(0.,pose.lift)*.8
            shadow_alpha = .18/(1+max(0.,pose.lift)*3)
            GL.glBegin(GL.GL_TRIANGLE_FAN)
            GL.glColor4f(0, 0, 0, shadow_alpha)
            GL.glVertex3f(pose.side*.65, -1.35, -.15)
            for i in range(49):
                angle = i * math.tau / 48
                GL.glColor4f(0, 0, 0, 0)
                GL.glVertex3f(pose.side*.65+.68*shadow_size*math.cos(angle), -1.35+.065*shadow_size*math.sin(angle), -.15)
            GL.glEnd()
            GL.glDepthMask(True)
            for flag in (GL.GL_LIGHTING, GL.GL_LIGHT0, GL.GL_LIGHT1, GL.GL_COLOR_MATERIAL): GL.glEnable(flag)
            GL.glLightfv(GL.GL_LIGHT0, GL.GL_POSITION, (-3, 4, 5, 0))
            GL.glLightfv(GL.GL_LIGHT0, GL.GL_DIFFUSE, (.82, .80, .76, 1))
            GL.glLightfv(GL.GL_LIGHT0, GL.GL_AMBIENT, (.38, .40, .45, 1))
            GL.glLightfv(GL.GL_LIGHT1, GL.GL_POSITION, (3, 2, -3, 0))
            GL.glLightfv(GL.GL_LIGHT1, GL.GL_DIFFUSE, (.32, .40, .52, 1))
            GL.glColorMaterial(GL.GL_FRONT_AND_BACK, GL.GL_AMBIENT_AND_DIFFUSE)
            GL.glMaterialfv(GL.GL_FRONT_AND_BACK, GL.GL_SPECULAR, (.22,.22,.22,1))
            GL.glMaterialf(GL.GL_FRONT_AND_BACK, GL.GL_SHININESS, 36)
            p = self.motion.pose
            GL.glTranslatef(p.side, p.lift, p.depth)
            # Weak perspective preserves the reference art at rest, while
            # forward/backward movement acquires the expected size change.
            depth_scale = 6.3 / max(4.8, 6.3-p.depth)
            GL.glScalef(depth_scale, depth_scale, depth_scale)
            GL.glRotatef(p.roll, 0, 0, 1)
            GL.glRotatef(p.yaw, 0, 1, 0)
            GL.glRotatef(p.pitch, 1, 0, 0)
            GL.glScalef(1/math.sqrt(p.squash), p.squash, 1/math.sqrt(p.squash))
            for handle, group, color, textured in self._lists:
                if group == 'glasses' and not self.sunglasses: continue
                GL.glPushMatrix()
                if group in ('head', 'hair', 'glasses'):
                    self._pivot_rotate('head', p.head_pitch, p.head_yaw, p.head_roll)
                    if group == 'hair': self._pivot_rotate('hair', z=p.hair)
                elif group in ('wing_left', 'wing_right'):
                    left = group == 'wing_left'
                    self._pivot_rotate(group,
                        x=p.wing_left_pitch if left else p.wing_right_pitch,
                        y=p.wing_left_yaw if left else p.wing_right_yaw,
                        z=-p.wing_left if left else p.wing_right)
                elif group in ('foot_left', 'foot_right'):
                    left = group == 'foot_left'
                    GL.glTranslatef(0,p.foot_left_lift if left else p.foot_right_lift,0)
                    self._pivot_rotate(group,
                        x=p.foot_left_pitch if left else p.foot_right_pitch,
                        y=p.foot_left_yaw if left else p.foot_right_yaw)
                elif group == 'pendant':
                    self._pivot_rotate('pendant', x=-p.pitch*.2, z=p.pendant_roll)
                if textured and self._textures:
                    # Authored shading is part of the identity: do not relight
                    # the original eyes/beak/hair into a different character.
                    GL.glDisable(GL.GL_LIGHTING)
                    GL.glEnable(GL.GL_ALPHA_TEST)
                    GL.glAlphaFunc(GL.GL_GREATER, .03)
                    GL.glEnable(GL.GL_TEXTURE_2D)
                    GL.glBindTexture(GL.GL_TEXTURE_2D, self._textures.get(self.expression, self._textures['normal']))
                    GL.glColor3f(1, 1, 1)
                else:
                    GL.glEnable(GL.GL_LIGHTING)
                    GL.glDisable(GL.GL_ALPHA_TEST)
                    GL.glDisable(GL.GL_TEXTURE_2D)
                    GL.glColor3f(*color)
                GL.glCallList(handle)
                GL.glPopMatrix()
            GL.glDisable(GL.GL_TEXTURE_2D)
            GL.glDisable(GL.GL_ALPHA_TEST)
            GL.glDisable(GL.GL_LIGHTING)
            # Read before releasing the producing GL context.
            img = self._fbo.toImage()
            img.setDevicePixelRatio(self._ratio)
            self._render_ms = (time.perf_counter() - start) * 1000
            return img
        finally:
            self._fbo.release()
            self._ctx.doneCurrent()
