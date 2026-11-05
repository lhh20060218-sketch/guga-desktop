"""Time-based, renderer-independent character motion. No model/API calls."""
import math
from dataclasses import dataclass


@dataclass
class Pose:
    yaw: float = 0.0
    pitch: float = 0.0
    roll: float = 0.0
    head_yaw: float = 0.0
    head_pitch: float = 0.0
    head_roll: float = 0.0
    lift: float = 0.0
    side: float = 0.0
    depth: float = 0.0
    framing: float = 1.0
    squash: float = 1.0
    wing_left: float = 0.0
    wing_right: float = 0.0
    wing_left_pitch: float = 0.0
    wing_right_pitch: float = 0.0
    wing_left_yaw: float = 0.0
    wing_right_yaw: float = 0.0
    foot_left_pitch: float = 0.0
    foot_right_pitch: float = 0.0
    foot_left_yaw: float = 0.0
    foot_right_yaw: float = 0.0
    foot_left_lift: float = 0.0
    foot_right_lift: float = 0.0
    pendant_roll: float = 0.0
    hair: float = 0.0
    blink: float = 1.0
    mouth: float = 0.0


class AvatarMotion:
    DURATIONS = {'spin': 2.2, 'sneak_peek': 3.0, 'peek': 2.4,
                 'bounce': .9, 'shake': .65, 'wave': 1.8, 'point': 1.8,
                 'nod': 1.3, 'head_shake': 1.5, 'tilt': 1.7, 'tsundere': 1.5}

    def __init__(self):
        self.time = 0.0
        self.action = 'none'
        self.elapsed = 0.0
        self.dancing = False
        self.sunglasses = False
        self.sunglasses_until = 0.0
        self.mouth_open = 0.0
        self.bpm = 110.0
        self.dragging = False
        self._gaze_target = [0.0, 0.0]
        self._gaze = [0.0, 0.0]
        self._velocity = [0.0, 0.0]
        self._drag = 0.0
        self._drag_target = 0.0
        self._hair = 0.0
        self._hair_velocity = 0.0
        self._dance_blend = 0.0
        self._drag_lift = 0.0
        self._turn_lag = self._turn_velocity = 0.0
        self._previous_yaw = 0.0
        self._pendant = self._pendant_velocity = 0.0
        self.pose = Pose()

    def look_at(self, x, y):
        self._gaze_target = [max(-1., min(1., x)), max(-1., min(1., y))]

    def set_dragging(self, active, speed=0.0):
        self.dragging = bool(active)
        self._drag_target = max(-18., min(18., speed * .08)) if active else 0.0

    def trigger_action(self, action):
        from core.embodiment import ALIASES
        action = ALIASES.get(action, action)
        if action in ('sunglasses', 'remove_sunglasses'):
            self.sunglasses = action == 'sunglasses'
            self.sunglasses_until = self.time + 8 if self.sunglasses else 0
        elif action in ('dance', 'stop_dance'):
            self.dancing = action == 'dance'
        elif action in self.DURATIONS:
            self.action, self.elapsed = action, 0.0

    def advance(self, dt):
        # Bound suspension gaps. Frame rate must not change animation speed.
        dt = max(0.0, min(float(dt), .1))
        self.time += dt
        self.elapsed += dt
        if self.sunglasses_until and self.time >= self.sunglasses_until:
            self.sunglasses, self.sunglasses_until = False, 0.0
        # Critically damped gaze with stable substeps.
        steps = max(1, math.ceil(dt / .016))
        h = dt / steps
        for _ in range(steps):
            for i in range(2):
                self._velocity[i] += (100 * (self._gaze_target[i] - self._gaze[i])
                                      - 20 * self._velocity[i]) * h
                self._gaze[i] += self._velocity[i] * h
        self._drag += (self._drag_target - self._drag) * (1 - math.exp(-dt * 8))
        self._drag_lift += ((.12 if self.dragging else 0) - self._drag_lift) * (1-math.exp(-dt*10))
        self._dance_blend += ((1. if self.dancing else 0.)-self._dance_blend) * (1-math.exp(-dt*8))
        t = self.time
        p = Pose(head_yaw=self._gaze[0] * 18, head_pitch=self._gaze[1] * 9,
                 roll=self._drag, lift=.012 * math.sin(t * 2.4),
                 squash=1 + .009 * math.sin(t * 2.4))
        p.head_roll = -self._drag * .35
        p.lift += self._drag_lift
        if self.dragging:
            p.wing_left = p.wing_right = 18
            p.wing_left_pitch = p.wing_right_pitch = -22
            p.foot_left_pitch = p.foot_right_pitch = 16
        if self._dance_blend > .001:
            blend = self._dance_blend
            p.framing = 1-.18*blend
            beat = t * self.bpm / 60 * 2 * math.pi
            p.roll += blend * 7 * math.sin(beat / 2)
            p.yaw += blend * 18 * math.sin(beat / 4)
            p.pitch += blend * 5 * math.sin(beat / 2 + .4)
            p.depth = blend * .13 * math.sin(beat / 4)
            p.side = blend * .075 * math.sin(beat / 2)
            p.lift += blend * .035 * abs(math.sin(beat))
            p.head_roll += blend * -6 * math.sin(beat / 2 - .45)
            p.head_pitch += blend * 3 * math.sin(beat - .4)
            p.wing_left = blend * (22 + 20 * math.sin(beat))
            p.wing_right = blend * (22 + 20 * math.sin(beat + .9))
            p.wing_left_pitch = blend * -30 * math.sin(beat / 2)
            p.wing_right_pitch = blend * 30 * math.sin(beat / 2 + .5)
            p.wing_left_yaw = blend * 18 * math.sin(beat / 2 + .8)
            p.wing_right_yaw = blend * -18 * math.sin(beat / 2 + .8)
            step_l, step_r = max(0., math.sin(beat)), max(0., -math.sin(beat))
            p.foot_left_lift = blend * .10 * step_l
            p.foot_right_lift = blend * .10 * step_r
            p.foot_left_pitch = blend * -28 * step_l
            p.foot_right_pitch = blend * -28 * step_r
            p.foot_left_yaw = blend * 10 * math.sin(beat / 2)
            p.foot_right_yaw = blend * -10 * math.sin(beat / 2)
        duration = self.DURATIONS.get(self.action, 0)
        if duration and self.elapsed < duration:
            u = self.elapsed / duration
            envelope = math.sin(math.pi * u) ** 2
            a = self.action
            if a == 'spin':
                ease = u * u * (3 - 2 * u)
                p.yaw += 360 * ease
                p.lift += .14 * envelope
                p.pitch += -7 * math.sin(2*math.pi*u) * envelope
                p.wing_left = p.wing_right = 25 * envelope
                p.wing_left_pitch = p.wing_right_pitch = -18 * envelope
                p.foot_left_pitch = -20 * max(0.,math.sin(u*math.pi*4)) * envelope
                p.foot_right_pitch = -20 * max(0.,-math.sin(u*math.pi*4)) * envelope
            elif a in ('peek', 'sneak_peek'):
                p.side += .16 * envelope
                p.roll += -10 * envelope
                p.head_yaw += 32 * envelope
                p.head_roll += 14 * envelope
                p.head_pitch += -6 * envelope
                p.lift -= .07 * envelope
                p.depth += .42 * envelope
                p.pitch += -9 * envelope
                p.wing_right_pitch += -22 * envelope
            elif a == 'bounce':
                p.lift += .3 * abs(math.sin(math.pi * u * 2)) * (1 - u)
                p.squash += -.12 * math.sin(math.pi * u * 4) * (1 - u)
                p.wing_left = p.wing_right = 25 * envelope
                p.foot_left_pitch = p.foot_right_pitch = 22 * envelope
            elif a == 'shake':
                p.side += .05 * math.sin(u * 40) * envelope
            elif a in ('head_shake', 'tsundere'):
                p.head_yaw += 24 * math.sin(u * math.pi * 5) * envelope
            elif a == 'nod':
                p.head_pitch += 18 * math.sin(u * math.pi * 4) * envelope
            elif a == 'tilt':
                p.head_roll += 18 * envelope
            elif a in ('wave', 'point'):
                # Pull the framing back while the arm extends beyond the
                # resting silhouette; keep the desktop window/bubble fixed.
                p.framing = min(p.framing,1-.18*envelope)
                p.wing_right += (65 + 15 * math.sin(u * 24)) * envelope
                p.wing_right_pitch += -48 * math.sin(u*math.pi*3) * envelope
                p.wing_right_yaw += 16 * math.sin(u*math.pi*4) * envelope
                p.yaw -= 9 * envelope
                p.head_roll -= 7 * envelope
        elif duration:
            self.action = 'none'
        # Angular velocity drives a delayed head response. Wrapped differences
        # keep a completed 360° spin from looking like an abrupt reverse turn.
        delta_yaw = (p.yaw-self._previous_yaw+180)%360-180
        angular_speed = max(-480.,min(480.,delta_yaw/max(dt,.001)))
        self._previous_yaw = p.yaw
        target_lag = max(-22.,min(22.,-angular_speed*.055))
        for _ in range(steps):
            self._turn_velocity += (90*(target_lag-self._turn_lag)-18*self._turn_velocity)*h
            self._turn_lag += self._turn_velocity*h
        p.head_yaw += self._turn_lag
        # Hair lags behind the head/body, then settles without a snap.
        target = -p.head_yaw * .12 - p.roll * .35
        for _ in range(steps):
            self._hair_velocity += (65 * (target - self._hair) - 12 * self._hair_velocity) * h
            self._hair += self._hair_velocity * h
        p.hair = self._hair
        # The existing chain mesh is a separate renderer group; its mass lags
        # behind body roll rather than behaving like a painted-on necklace.
        target_pendant = -p.roll*.8 - p.pitch*.3
        for _ in range(steps):
            self._pendant_velocity += (75*(target_pendant-self._pendant)-9*self._pendant_velocity)*h
            self._pendant += self._pendant_velocity*h
        p.pendant_roll = self._pendant
        blink_phase = t % 4.7
        p.blink = 1 - .96 * math.sin(math.pi * blink_phase / .18) if blink_phase < .18 else 1
        p.mouth = max(0., min(1., self.mouth_open))
        p.head_pitch += p.mouth * 1.5 * math.sin(t*11)
        self.pose = p
        return p
