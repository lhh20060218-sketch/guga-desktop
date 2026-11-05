"""Local task-event choreography. No LLM call, progress text or random success."""
import time


class TaskAnimationDirector:
    GESTURES={'thinking':'tilt','working':'nod','waiting':'sneak_peek',
              'result':'tilt','success':'nod','error':'head_shake'}
    PRIORITY={'working':4,'thinking':3,'result':2,'waiting':1}
    THINKING_VARIANTS=('tilt',)

    def __init__(self,clock=None):
        self.clock=clock or time.monotonic
        self.jobs={};self.terminal=None;self.started=None
        self.last_state=None;self.last_action=-100.;self.count=0
        self.thinking_count=0

    @property
    def active(self):
        return bool(self.jobs or (self.terminal and self.clock()<self.terminal[1]))

    @property
    def state(self):
        if self.jobs:return max(self.jobs.values(),key=lambda x:self.PRIORITY.get(x,0))
        if self.terminal and self.clock()<self.terminal[1]:return self.terminal[0]
        return 'idle'

    def update(self,state,task_id='main'):
        if state not in (*self.GESTURES,'idle','cancelled'):return False
        now=self.clock();key=str(task_id)
        if state in ('idle','cancelled','success','error','result'):
            existed=self.jobs.pop(key,None)
            # A background worker still running prevents a premature celebration.
            if state in ('success','error','result') and existed and not self.jobs and now-(self.started or 0)>=1.2:
                self.terminal=(state,now+5.)
            elif not self.jobs:self.terminal=None
        else:
            if not self.jobs:self.started=now;self.last_state=None
            self.jobs[key]=state;self.terminal=None
        return True

    def poll(self,blocked=False):
        now=self.clock();state=self.state
        if blocked or state=='idle':return None
        # Brief actions should not flash a thinking pose after they have ended.
        if self.started is not None and now-self.started<1.2:return None
        interval=10. if state==self.last_state else 2.5
        if now-self.last_action<interval:return None
        if state in ('success','error','result') and state==self.last_state:return None
        self.last_action=now;self.last_state=state;self.count+=1
        if not self.jobs:self.terminal=None
        gesture=self.GESTURES[state]
        if state=='thinking':
            gesture=self.THINKING_VARIANTS[self.thinking_count%len(self.THINKING_VARIANTS)]
            self.thinking_count+=1
        return dict(state=state,gesture=gesture)

    def snapshot(self):
        return dict(state=self.state,active_jobs=len(self.jobs),triggered=self.count)
