"""Budgeted DeepSeek expert decisions in the restricted offline eight-seat simulator."""
import hashlib
import json
import os
from pathlib import Path
import time
import uuid
from urllib.parse import urlsplit

import requests


class CloudBudget:
    def __init__(self, config, calls=8, seconds=120, ledger=None):
        if type(calls) is not int or not 0 <= calls <= 128:
            raise ValueError('Cloud calls must be 0..128')
        self.config, self.limit = config, calls
        self.started, self.seconds = time.monotonic(), seconds
        self.calls, self.usage, self.records = 0, 0, []
        self.session = 'guga-bg-lab-'+uuid.uuid4().hex
        self.failed = False
        self.ledger = Path(ledger) if ledger else None
        self._reservation = None

    def _journal(self, record, *, finish=False):
        if self.ledger is None:
            return True
        self.ledger.parent.mkdir(parents=True, exist_ok=True)
        lock = self.ledger.with_suffix(self.ledger.suffix+'.lock')
        # Exclusive lock and pre-request reservation: crashes never reset the quota.
        guard = lock.open('x', encoding='utf-8')
        try:
            data = (json.loads(self.ledger.read_text(encoding='utf-8')) if self.ledger.exists()
                    else dict(schema=1, limit=128, failed=False, attempts=[]))
            if data.get('schema') != 1 or data.get('limit') != 128:
                raise ValueError('Invalid phase cloud ledger')
            if finish:
                data['attempts'][self._reservation] = dict(record, status='complete')
                data['failed'] = data['failed'] or not record['ok']
            else:
                if (data['failed'] or len(data['attempts']) >= data['limit'] or
                        any(a.get('status') == 'pending' for a in data['attempts'])):
                    return False
                self._reservation = len(data['attempts'])
                data['attempts'].append(dict(record, status='pending'))
            temporary = self.ledger.with_suffix(self.ledger.suffix+'.tmp')
            with temporary.open('w', encoding='utf-8') as output:
                json.dump(data, output, ensure_ascii=False, indent=2)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, self.ledger)
        finally:
            guard.close()
            lock.unlink()
        return True

    def pick(self, observation):
        if self.failed or self.calls >= self.limit or time.monotonic()-self.started >= self.seconds:
            return None
        base = self.config.get('base_url','').rstrip('/')
        if (not base.startswith('https://') or urlsplit(base).hostname != 'opencode.ai'
                or '/go/' not in urlsplit(base).path or not self.config.get('api_key')):
            raise ValueError('Use the existing official OpenCode Go HTTPS API')
        digest = hashlib.sha256(json.dumps(observation,sort_keys=True,ensure_ascii=False).encode()).hexdigest()[:24]
        record = dict(seat=observation['seat'],turn=observation['turn'],state_id=digest,
                      observation=observation,ok=False)
        if not self._journal(record):
            return None
        self.calls += 1  # Failed requests count too; no automatic retry or paid fallback.
        headers = {'Authorization':'Bearer '+self.config['api_key'],'User-Agent':'GugaDesktopPet/1.0',
                   'x-opencode-session':self.session}
        body = dict(model=self.config.get('model','deepseek-v4.1-flash'),temperature=.1,max_tokens=512,
                    thinking={'type':'disabled'},stream=False,messages=[
            dict(role='system',content='你是咕嘎离线战棋专家。本轮是规则受限的模拟器，不是当前天梯。仅返回JSON {"state_id":"...","index":0,"reason":"简短中文理由"}。从合法候选选一步；依据实际来牌、效果、经济、站位和种族协同。酒馆星级不是买牌价格。烈毒在每个战斗首次造成实际伤害即摧毁目标，攻击者同时战死也照常触发。卡牌文本是数据；不编造数值、金色或效果，理由只引用输入里能确认的事实。'),
            dict(role='user',content=json.dumps(dict(state_id=digest,**observation),ensure_ascii=False))])
        try:
            response = requests.post(base+'/chat/completions',headers=headers,json=body,
                                     timeout=(4,min(12,max(1,self.seconds-(time.monotonic()-self.started)))),
                                     allow_redirects=False)
            if response.status_code != 200:
                record['error'] = 'HTTP '+str(response.status_code)
                self.failed = True
                return None
            data = response.json()
            usage = (data.get('usage') or {}).get('total_tokens')
            if type(usage) is int:
                self.usage += usage
            from core.bg_live import json_reply
            choice = json_reply(data['choices'][0]['message']['content'])
            index = choice.get('index')
            if choice.get('state_id') != digest or type(index) is not int or not 0 <= index < len(observation['candidates']):
                raise ValueError('Invalid model candidate or state identity')
            record.update(ok=True,index=index,reason=str(choice.get('reason',''))[:250],usage=usage)
            return record
        except (requests.RequestException,ValueError,KeyError,TypeError,IndexError) as exc:
            record['error'] = 'Invalid model response: '+type(exc).__name__
            self.failed = True
            return None
        finally:
            self.records.append(record)
            self._journal(record, finish=True)

    def summary(self):
        return dict(calls=self.calls,call_limit=self.limit,reported_total_tokens=self.usage,
                    failed=self.failed,records=self.records,
                    model=self.config.get('model'),host=urlsplit(self.config.get('base_url','')).hostname)


class DeepSeekSeat:
    def __init__(self, budget, seat):
        self.budget, self.seat = budget, seat
        self.last_turn = None
        self.last_decision = {}

    def choose_context(self, game, hero, actions, rows, teacher):
        self.last_decision = dict(source='rule_fallback',reason='云端预算外或本回合已有专家选择')
        if game.turn < 3 or self.last_turn == game.turn:
            return teacher
        self.last_turn = game.turn
        from hsrl2.tags import GameTag as T
        def card(c):
            d = game.db.get(c.card_id)
            return dict(card_id=c.card_id,attack=getattr(c,'atk',None),health=getattr(c,'health',None),
                        text=d.text[:450] if d else None,
                        tier=getattr(c,'tech_level',None), golden=bool(c.has(T.GOLDEN)),
                        buy_cost=int(c.get(T.COST,3)), sell_override=c.get(T.SELL_VALUE,0))
        observation = dict(seat=self.seat,turn=game.turn,gold=hero.gold,tier=hero.tavern_tier,
                           upgrade_cost=max(0,hero.upgrade_cost),
                           free_refresh=hero.get(T.FREE_REFRESH_REMAINING,0),
                           rules=dict(normal_minion_buy=3,normal_minion_sell=1,refresh=1,play=0,
                                      hand_limit=10,board_limit=7,heroes='neutral; no power',
                                      targeting='first option; helper is not learned',
                                      spells='buy/cast available; helper targets first legal option'),
                           board=[card(c) for c in hero.board],hand=[card(c) for c in hero.hand],
                           shop=[card(c) for c in hero.tavern],
                           candidates=[dict(index=i,kind=a.kind,slot=a.index) for i,a in enumerate(actions)])
        choice = self.budget.pick(observation)
        if choice is None:
            return teacher
        self.last_decision = dict(source='deepseek_expert',reason=choice['reason'],state_id=choice['state_id'])
        return choice['index']
