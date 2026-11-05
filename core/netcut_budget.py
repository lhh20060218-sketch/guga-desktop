"""Persistent per-game disconnect budget; at most nine actual cuts."""
import json
import os
from pathlib import Path
import tempfile
import time

MAX_CUTS = 9
MIN_INTERVAL = 15
RECONNECT_SECONDS = 30


def _write_atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=path.name+'.', dir=path.parent)
    try:
        with os.fdopen(handle, 'w', encoding='utf-8') as output:
            json.dump(data, output, ensure_ascii=False, indent=2)
            output.flush(); os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        try: os.unlink(temporary)
        except FileNotFoundError: pass


class DisconnectBudget:
    def __init__(self, path=None, clock=time.time, disconnect=None):
        self.path=Path(path) if path else Path(__file__).resolve().parents[1]/'runtime/netcut-budget.json'
        self.clock=clock
        self._disconnect=disconnect

    def _load(self):
        try:
            data=json.loads(self.path.read_text(encoding='utf-8'))
            if data.get('schema')!=1:raise ValueError
            return data
        except (FileNotFoundError,OSError,ValueError,TypeError):
            return dict(schema=1,game_key='',count=0,attempts=[],last_at=0)

    def status(self, game_key=''):
        data=self._load();now=self.clock()
        if game_key and data.get('game_key')!=game_key:
            return dict(game_key=game_key,count=0,remaining=MAX_CUTS,last_at=0,
                        cooldown_remaining=0,exhausted=False)
        last=float(data.get('last_at',0) or 0)
        count=int(data.get('count',0)) if data.get('game_key')==game_key else 0
        return dict(game_key=game_key,count=count,remaining=max(0,MAX_CUTS-count),last_at=last,
                    cooldown_remaining=max(0,MIN_INTERVAL-(now-last)) if last else 0,
                    exhausted=count>=MAX_CUTS,
                    combat_ids=[a.get('combat_id') for a in data.get('attempts',[])
                                if a.get('status') in ('pending','success')])

    def cut(self, game_key, combat_id, *, disconnect=None):
        if not game_key or not combat_id:
            raise ValueError('无法识别当前对局或战斗，未拔线')
        data=self._load();now=self.clock()
        if data.get('game_key')!=game_key:
            data=dict(schema=1,game_key=game_key,count=0,attempts=[],last_at=0)
        if data['count']>=MAX_CUTS:
            raise RuntimeError('本局已拔线 9 次，达到硬上限')
        if any(a.get('combat_id')==combat_id and a.get('status') in ('pending','success')
               for a in data.get('attempts',[])):
            raise RuntimeError('本次战斗已经拔过线，未重复执行')
        if now-float(data.get('last_at',0) or 0)<MIN_INTERVAL:
            wait=MIN_INTERVAL-(now-float(data.get('last_at',0) or 0))
            raise RuntimeError(f'重连保护中，约 {int(wait)+1} 秒后可再次拔线')
        attempt=dict(combat_id=str(combat_id),at=now,status='pending')
        data['attempts'].append(attempt);data['count']+=1;data['last_at']=now
        _write_atomic(self.path,data)
        try:
            if disconnect is None:
                disconnect=self._disconnect
            if disconnect is None:
                from core.netcut import force_disconnect_hearthstone
                disconnect=force_disconnect_hearthstone
            closed,detail=disconnect()
            if not (type(closed) is int and closed>0):
                attempt['status']='failed';attempt['error']=str(detail)[:200]
                data['count']-=1
                _write_atomic(self.path,data)
                return dict(ok=False,error=str(detail),**self.status(game_key))
            attempt.update(status='success',closed=closed,source=str(detail))
            _write_atomic(self.path,data)
            return dict(ok=True,closed=closed,source=str(detail),**self.status(game_key))
        except Exception as exc:
            attempt['status']='failed';attempt['error']=type(exc).__name__+': '+str(exc)[:160]
            data['count']-=1
            _write_atomic(self.path,data)
            raise
