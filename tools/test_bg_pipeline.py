import threading,time,unittest
from types import SimpleNamespace
from unittest.mock import patch
from core.bg_pipeline import StrategyEngine,OperationEngine,backend_capabilities


def live_state():
    return dict(game=1,option_set=1,controller=1,client_build=254477,round=3,tier=2,health=30,armor=0,
        resources=dict(RESOURCES=5,RESOURCES_USED=0),entities={},options=[],targets={},fingerprint='fp')


class PipelineTests(unittest.TestCase):
    def test_unknown_upgrade_price_is_not_assumed_to_be_free(self):
        from core.bg_pipeline import fast_choice
        state = live_state()
        state.update(round=10, tier=2, upgrade_cost=None)
        self.assertIsNone(fast_choice(state, [dict(kind='UPGRADE', entity_id='9', action_id='upgrade')]))

    def test_strategy_never_captures_screen(self):
        picked=dict(action=dict(kind='REFRESH',action_id='r'),reason='refresh',trained_prior={},human_prior={})
        with patch('core.bg_live.candidates',return_value=[picked['action']]), \
             patch('core.bg_live.model_pick',return_value=picked) as model:
            plan=StrategyEngine(dict(api_key='offline',strategy_mode='model')).plan(live_state())
        self.assertFalse(plan['screen_used']);model.assert_called_once()

    def test_operation_refuses_non_recruit_without_capture(self):
        backend=SimpleNamespace(capture=lambda:(_ for _ in ()).throw(AssertionError('capture must not run')),
                                cancelled=lambda:False)
        reader=SimpleNamespace(parser=SimpleNamespace(entities={}),poll=lambda:[])
        with self.assertRaisesRegex(RuntimeError,'招募阶段'):
            OperationEngine(backend,{}).execute(dict(state=live_state(),action=dict(kind='REFRESH')),reader,threading.Event(),time.monotonic(),30)

    def test_operation_executes_only_recruit_and_returns_log_ack(self):
        backend=SimpleNamespace(capture=lambda:('image',(1,2,3,4,5)),geometry=lambda h:(1,2,3,4,5),
                                find=lambda:1,cancelled=lambda:False,execute=lambda *a:None)
        reader=SimpleNamespace(parser=SimpleNamespace(entities={'1':dict(CARDTYPE='GAME',BACON_IS_COMBAT_PHASE=0)}),
                               poll=lambda:[],state=live_state)
        with patch('core.bg_live.ground_action',return_value=dict(phase='recruit',confidence=1,source=[.5,.5])), \
             patch('core.bg_live.acknowledged',return_value=True):
            outcome=OperationEngine(backend,{}).execute(dict(state=live_state(),action=dict(kind='REFRESH'),metadata={},reason='x'),
                reader,threading.Event(),time.monotonic(),30)
        self.assertTrue(outcome['executed']);self.assertTrue(outcome['verified'])

    def test_memory_write_is_not_claimed(self):
        self.assertIn('not available',backend_capabilities()['memory_write'])

    def test_obvious_refresh_uses_fast_local_path_without_model(self):
        state=live_state();state['entities']={'9':dict(CARD_ID='TB_BaconShop_8p_Reroll_Button',CONTROLLER=1,ZONE='PLAY')}
        action=dict(kind='REFRESH',entity_id='9',action_id='r')
        with patch('core.bg_live.candidates',return_value=[action]),patch('core.bg_live.model_pick') as model:
            plan=StrategyEngine(dict(api_key='offline')).plan(state)
        self.assertTrue(plan['local']);model.assert_not_called()

    def test_fixed_button_grounding_is_cached_after_verified_action(self):
        calls=[]
        backend=SimpleNamespace(capture=lambda:(calls.append('capture') or ('image',(1,2,3,4,5))),
            geometry=lambda h:(1,2,3,4,5),find=lambda:1,cancelled=lambda:False,execute=lambda *a:None)
        reader=SimpleNamespace(parser=SimpleNamespace(entities={'1':dict(CARDTYPE='GAME',BACON_IS_COMBAT_PHASE=0)}),poll=lambda:[],state=live_state)
        plan=dict(state=live_state(),action=dict(kind='REFRESH',entity_id='9'),metadata={},reason='x')
        with patch('core.bg_live.ground_action',return_value=dict(phase='recruit',confidence=1,source=[.5,.5])) as ground, \
             patch('core.bg_live.acknowledged',return_value=True):
            engine=OperationEngine(backend,{});engine.execute(plan,reader,threading.Event(),time.monotonic(),30)
            engine.execute(plan,reader,threading.Event(),time.monotonic(),30)
        self.assertEqual(calls.count('capture'),1);self.assertEqual(ground.call_count,1)

if __name__=='__main__':unittest.main()
