"""Bounded, deduplicated task updates: progress is sparse, questions are timely."""
import time
from collections import deque
from core.agent_memory import safe_text


class TaskSpeechQueue:
    def __init__(self,clock=None):
        self.clock=clock or time.monotonic
        self.pending=deque(maxlen=4);self.seen=deque(maxlen=80)
        self.last=-1000.

    def offer(self,key,text,important=False):
        text=safe_text(text).replace('\n',' ')[:260]
        if not text or key in self.seen:return False
        self.seen.append(key)
        item=dict(key=key,text=text,important=bool(important),at=self.clock())
        if important:
            # Final/decision messages replace stale progress instead of waiting behind it.
            self.pending=deque([x for x in self.pending if x['important']],maxlen=4)
        else:
            self.pending=deque([x for x in self.pending if x['important']],maxlen=4)
        self.pending.append(item);return True

    def next(self,busy=False):
        if busy:return None
        now=self.clock()
        while self.pending and now-self.pending[0]['at']>(300 if self.pending[0]['important'] else 150):
            self.pending.popleft()
        if not self.pending:return None
        item=self.pending[0]
        if now-self.last<(10 if item['important'] else 30):return None
        self.pending.popleft();self.last=now;return item

    def clear(self):self.pending.clear()
