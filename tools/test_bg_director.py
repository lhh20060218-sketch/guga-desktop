"""Offline director/voice/backend regression: no game input or paid API calls."""
import json
import inspect
import os
from pathlib import Path
from types import SimpleNamespace
import sys
import threading
import time
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from launcher import _prepare_qt
_prepare_qt()
from PyQt5.QtWidgets import QApplication
from core.bg_director import BattlegroundDirector, review_text
from core.bg_live import observed_phase, LiveSession, _LIVE_GATE
from core.bg_cloud_policy import CloudBudget, DeepSeekSeat
from core.realtime_agent import AgentRealtimeVoice
from core.realtime_voice import DEFAULTS
from core.bg_memory import normalize_cards
from core.bg_expert_data import load_expert_samples
from core.bg_selfplay import PROFILE, ENGINE_REVISION, FEATURE_DIM

APP = QApplication.instance() or QApplication([])


class DirectorTests(unittest.TestCase):
    def test_background_auto_watch_never_calls_netcut(self):
        from ui.pet_window import PetWindow
        source=inspect.getsource(PetWindow._auto_watch)
        self.assertNotIn('_netcut(',source)

    def test_phase_requires_explicit_consistent_game_tags(self):
        p = SimpleNamespace(entities={1:dict(CARDTYPE='GAME')})
        self.assertEqual(observed_phase(p),'unknown')
        p.entities[1]['BACON_IS_COMBAT_PHASE']=1
        self.assertEqual(observed_phase(p),'combat')
        p.entities[1]['BACON_IN_COMBAT']=0
        self.assertEqual(observed_phase(p),'unknown')
        p.entities[1]['BACON_IS_COMBAT_PHASE']=0
        self.assertEqual(observed_phase(p),'recruit')

    def test_review_excludes_unconfirmed_actions_and_preserves_reason(self):
        rows=[dict(verified=False,action={'kind':'BUY'},reason='不该出现'),
              dict(verified=True,action={'kind':'UPGRADE'},reason='金币足够并保留战力')]
        text=review_text(rows)
        self.assertIn('1 步',text)
        self.assertNotIn('不该出现',text)
        self.assertIn('金币足够',text)
        self.assertNotIn('战斗结束',text)

    def test_legacy_and_voice_executors_cannot_overlap(self):
        session=LiveSession(None,'unused')
        _LIVE_GATE.acquire()
        try:
            with self.assertRaises(RuntimeError):session.run()
        finally:_LIVE_GATE.release()

    def test_step_runs_background_and_produces_only_verified_summary(self):
        record=dict(verified=True,action={'kind':'BUY'},reason='补充当前战力')
        class Session:
            stop=threading.Event()
            reader=SimpleNamespace(parser=SimpleNamespace(entities={}),poll=lambda:time.sleep(.03))
            def run(self,count,seconds):
                callback(dict(type='action_confirmed',record=record))
                return dict(records=[record])
        callback=None
        def factory(cb):
            nonlocal callback
            callback=cb
            return Session()
        director=BattlegroundDirector(session_factory=factory)
        director.conversation_id='chat-a'
        reply=director.start('step',seconds=10)
        director._worker.join(2)
        self.assertTrue(reply['accepted'])
        state=director.status()
        self.assertFalse(state['running'])
        self.assertEqual(state['confirmed'],1)
        self.assertTrue(any(e['type']=='review' for e in state['recent']))
        self.assertTrue(all(e['conversation_id']=='chat-a' for e in state['recent']))
        self.assertEqual(len({e['event_id'] for e in state['recent']}),len(state['recent']))

    def test_read_only_observer_never_calls_executor_and_stops(self):
        class Session:
            stop=threading.Event()
            reader=SimpleNamespace(parser=SimpleNamespace(entities={}),poll=lambda:[])
            def run(self,*args):raise AssertionError('Observer must not send input')
        director=BattlegroundDirector(session_factory=lambda cb:Session())
        director.start('observe',seconds=10)
        with self.assertRaises(RuntimeError):director.start('step',seconds=10)
        director.stop()
        director._worker.join(2)
        self.assertFalse(director.status()['running'])
        self.assertFalse(director.status()['memory_execution_available'])

    def test_memory_read_projects_only_card_fields(self):
        card=SimpleNamespace(CardId='BG_TEST',EntityId=12,ZonePosition=2,AccountId='private')
        self.assertEqual(normalize_cards([card]),[dict(card_id='BG_TEST',entity_id=12,position=2)])
        self.assertIsNone(normalize_cards(None))

    def test_netcut_requires_explicit_combat_and_respects_budget(self):
        from core.netcut_budget import DisconnectBudget
        with tempfile.TemporaryDirectory() as folder:
            ledger=Path(folder)/'budget.json'
            budget=DisconnectBudget(ledger,clock=lambda:1000.,disconnect=lambda:(1,'日志'))
            self.assertTrue(budget.cut('game','3:2')['ok'])
            with self.assertRaisesRegex(RuntimeError,'已经拔过'):
                budget.cut('game','3:2')
            director=BattlegroundDirector(session_factory=lambda cb:None)
            with patch('core.log_reader.read_current_board',return_value=dict(active=True,theirs=[])):
                director.start('netcut',seconds=10);director._worker.join(2)
            self.assertFalse(director.status()['running'])

    def test_netcut_combat_path_uses_shared_budget_and_emits_narration(self):
        calls=[]
        class FakeBudget:
            def cut(self,game,combat):
                calls.append((game,combat))
                return dict(ok=True,count=1,remaining=8,closed=1,source='日志')
            def status(self,game):
                return dict(count=1,remaining=8,exhausted=False,combat_ids=['4:1'])
        board=dict(active=True,theirs=[{'name':'X'}],turn=4,game_key='game-key')
        director=BattlegroundDirector(session_factory=lambda cb:None)
        with patch('core.log_reader.read_current_board',return_value=board), \
             patch('core.netcut_budget.DisconnectBudget',FakeBudget):
            director.start('netcut',seconds=10);director._worker.join(2)
            state=director.status()
        self.assertEqual(calls,[('game-key','4:1')])
        self.assertTrue(any(e['type']=='netcut' for e in state['recent']))
        self.assertEqual(state['netcut']['remaining'],8)


class VoiceNoticeTests(unittest.TestCase):
    def engine(self):
        e=AgentRealtimeVoice();e._cfg=dict(DEFAULTS)
        e._last_activity=time.monotonic()-5
        return e

    def drain(self,e):
        while not e._commands.empty():e._process_command(e._commands.get_nowait())

    def test_notice_waits_for_user_and_existing_generation_then_deduplicates(self):
        e=self.engine()
        e._user_speaking=True
        e.notify_battleground('one','已确认买入')
        e.notify_battleground('one','已确认买入')
        with patch.object(e,'_send') as send:
            self.drain(e)
            send.assert_not_called()
            e._user_speaking=False;e._generating=True;e._process_command(None)
            send.assert_not_called()
            e._generating=False;e._process_command(None)
            self.assertEqual(send.call_count,2)
            self.assertEqual(send.call_args_list[0].args[0]['item']['content'][0]['type'],'input_text')
            self.assertEqual(send.call_args.args[0]['type'],'response.create')
            self.assertFalse(e._notices)

    def test_notice_cannot_execute_new_tool_and_interrupt_drops_queued_review(self):
        e=self.engine();events=[]
        e.task_requested.connect(lambda *args:events.append(args))
        e._notice_active=True
        with patch.object(e,'_send'):
            e._accept_call(dict(call_id='bad',name='ask_deepseek',arguments='{"request":"再买一个"}'))
            self.drain(e)
        self.assertEqual(events,[])
        e._notices.append(('old',time.monotonic()))
        e.interrupt()
        self.assertFalse(e._notices)

    def test_old_notice_and_stopped_call_are_not_spoken(self):
        e=self.engine()
        e._notices.append(('stale',time.monotonic()-91))
        with patch.object(e,'_send') as send:e._process_command(None);send.assert_not_called()
        e._stop.set()
        self.assertFalse(e.notify_battleground('x','不应播报'))

    def test_interrupt_invalidates_notice_still_in_command_queue(self):
        e=self.engine()
        e.notify_battleground('queued','旧任务的播报')
        e.interrupt()
        with patch.object(e,'_send') as send:
            self.drain(e)
            self.assertFalse(any(c.args[0]['type']=='response.create' for c in send.call_args_list))

    def test_notice_function_call_seen_only_at_response_done_cannot_execute(self):
        e=self.engine();events=[]
        e.task_requested.connect(lambda *args:events.append(args))
        e._notice_active=True
        e._handle_event(dict(type='response.created',response=dict(id='notice-r')))
        item=dict(type='function_call',call_id='late',name='ask_deepseek',arguments='{"request":"买牌"}')
        with patch.object(e,'_record_usage'):
            e._handle_event(dict(type='response.done',response=dict(id='notice-r',output=[item])))
        self.assertEqual(events,[])
        self.assertFalse(e._notice_active)


class CloudTests(unittest.TestCase):
    def test_zero_budget_never_connects(self):
        budget=CloudBudget({},calls=0)
        with patch('core.bg_cloud_policy.requests.post') as post:
            self.assertIsNone(budget.pick({}))
            post.assert_not_called()

    def test_quota_failure_stops_all_future_requests_and_redacts_body(self):
        budget=CloudBudget(dict(base_url='https://opencode.ai/zen/go/v1',api_key='offline-key'),calls=8)
        with patch('core.bg_cloud_policy.requests.post',return_value=SimpleNamespace(status_code=402)) as post:
            self.assertIsNone(budget.pick(dict(seat=0,turn=1,candidates=[])))
            self.assertIsNone(budget.pick(dict(seat=1,turn=1,candidates=[])))
            self.assertEqual(post.call_count,1)
        self.assertNotIn('offline-key',json.dumps(budget.summary()))
        self.assertTrue(budget.failed)

    def test_valid_candidate_and_state_identity(self):
        budget=CloudBudget(dict(base_url='https://opencode.ai/zen/go/v1',api_key='offline-key'),calls=1)
        def respond(*args,**kwargs):
            state=json.loads(kwargs['json']['messages'][-1]['content'])['state_id']
            return SimpleNamespace(status_code=200,json=lambda:dict(choices=[dict(message=dict(content=json.dumps(
                dict(state_id=state,index=0,reason='保留经济'))))],usage=dict(total_tokens=100)))
        observation=dict(seat=0,turn=1,candidates=[dict(kind='END')])
        with patch('core.bg_cloud_policy.requests.post',side_effect=respond) as post:
            self.assertEqual(budget.pick(observation)['index'],0)
            self.assertIsNone(budget.pick(observation))
            self.assertEqual(post.call_count,1)
        self.assertEqual(budget.summary()['reported_total_tokens'],100)

    def test_phase_ledger_survives_restart_and_stops_after_first_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            ledger=Path(folder)/'phase.json'
            config=dict(base_url='https://opencode.ai/inference/go/openai/v1',api_key='offline-key')
            observation=dict(seat=0,turn=3,candidates=[dict(kind='END')])
            first=CloudBudget(config,calls=128,ledger=ledger)
            with patch('core.bg_cloud_policy.requests.post',return_value=SimpleNamespace(status_code=402)) as post:
                first.pick(observation)
                second=CloudBudget(config,calls=128,ledger=ledger)
                second.pick(observation)
                self.assertEqual(post.call_count,1)
            data=json.loads(ledger.read_text(encoding='utf-8'))
            self.assertTrue(data['failed'])
            self.assertEqual(len(data['attempts']),1)
            self.assertFalse(ledger.with_suffix('.json.lock').exists())
            self.assertNotIn('offline-key',ledger.read_text(encoding='utf-8'))

    def test_pending_reservation_and_exhausted_phase_never_call_api(self):
        with tempfile.TemporaryDirectory() as folder:
            ledger=Path(folder)/'phase.json'
            for attempts in ([dict(status='pending')],[dict(status='complete')]*128):
                ledger.write_text(json.dumps(dict(schema=1,limit=128,failed=False,attempts=attempts)),encoding='utf-8')
                budget=CloudBudget(dict(base_url='https://opencode.ai/zen/go/v1',api_key='offline-key'),ledger=ledger)
                with patch('core.bg_cloud_policy.requests.post') as post:
                    self.assertIsNone(budget.pick(dict(seat=0,turn=3,candidates=[])))
                    post.assert_not_called()

    def test_expert_labels_use_selected_action_and_reject_wrong_profile_or_nan(self):
        sample=dict(x=[[0.]*FEATURE_DIM,[1.]*FEATURE_DIM],action=1,teacher=0,
                    decision=dict(source='deepseek_expert',reason='未经核对的解释不会训练'))
        game=dict(profile=PROFILE,engine_revision=ENGINE_REVISION,finished=True,
                  action_limit_hits=0,trajectories=[[sample]])
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'expert.json'
            path.write_text(json.dumps(dict(games=[game])),encoding='utf-8')
            samples,info=load_expert_samples(path)
            self.assertEqual(samples[0]['teacher'],1)
            self.assertNotIn('reason',samples[0])
            self.assertEqual(info['samples'],1)
            sample['x'][0][0]=float('nan')
            path.write_text(json.dumps(dict(games=[game])),encoding='utf-8')
            with self.assertRaises(ValueError):load_expert_samples(path)
            game['profile']='live-unverified'
            path.write_text(json.dumps(dict(games=[game])),encoding='utf-8')
            with self.assertRaises(ValueError):load_expert_samples(path)


if __name__=='__main__':unittest.main()
