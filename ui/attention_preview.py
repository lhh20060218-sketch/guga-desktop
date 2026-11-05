"""Review-only social attention controller. Not connected to PetWindow."""
import math
import random


class AttentionPreview:
    def __init__(self, seed=None):
        self.rng=random.Random(seed)
        self.time=0.;self.state='idle';self.until=0.;self.cooldown=0.
        self._previous=None;self._near=False;self._dwell=0.;self._tried=False
        self.target=(0.,0.)

    def update(self,dt,x,y,busy=False):
        dt=max(0.,min(.1,float(dt)));self.time+=dt
        near=abs(x)<1.4 and abs(y)<1.4
        movement=math.hypot(x-self._previous[0],y-self._previous[1]) if self._previous else 0.
        self._previous=(x,y)
        if near and not self._near:self._tried=False;self._dwell=0.
        self._near=near
        self._dwell=self._dwell+dt if near else 0.
        if self.state=='following' and (not near or self.time>=self.until or busy):
            self.state='returning';self.until=self.time+.8
            self.cooldown=self.time+self.rng.uniform(7,12)
        elif self.state=='returning' and self.time>=self.until:
            self.state='idle'
        if self.state=='idle' and near and not busy and self.time>=self.cooldown:
            if self._tried and movement>.06:self._tried=False
            if not self._tried and self._dwell>.55:
                self._tried=True
                if self.rng.random()<.72:
                    self.state='following';self.until=self.time+self.rng.uniform(2.2,4)
                else:self.cooldown=self.time+5
        self.target=(max(-1.,min(1.,x)),max(-1.,min(1.,y))) if self.state=='following' else (0.,0.)
        return self.target
