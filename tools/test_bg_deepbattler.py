"""Offline contract tests: no desktop inputs and no real API requests."""
import copy
import json
import unittest
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from core.bg_deepbattler import policy_state, bind_first, model_pick
from core.bg_live import candidates, fingerprint
from core.bg_pipeline import StrategyEngine


def fixture():
    entities = {
        '1': dict(CARD_ID='BG_BOARD', CARDTYPE='MINION', CONTROLLER=1, ZONE='PLAY', ZONE_POSITION=1),
        '2': dict(CARD_ID='BG_SHOP_B', CARDTYPE='MINION', CONTROLLER=9, ZONE='PLAY', ZONE_POSITION=2),
        '3': dict(CARD_ID='BG_SHOP_A', CARDTYPE='MINION', CONTROLLER=9, ZONE='PLAY', ZONE_POSITION=1),
        '4': dict(CARD_ID='BG_HAND', CARDTYPE='MINION', CONTROLLER=1, ZONE='HAND', ZONE_POSITION=2),
        '5': dict(CARD_ID='SPELL', CARDTYPE='SPELL', CONTROLLER=1, ZONE='HAND', ZONE_POSITION=1),
        '10': dict(CARD_ID='TB_BaconShop_DragBuy', CONTROLLER=1, ZONE='PLAY'),
        '11': dict(CARD_ID='TB_BaconShop_DragSell', CONTROLLER=1, ZONE='PLAY'),
        '12': dict(CARD_ID='TB_BaconShop_8p_Reroll_Button', CONTROLLER=1, ZONE='PLAY'),
        '13': dict(CARD_ID='TB_BaconShopLockAll_Button', CONTROLLER=1, ZONE='PLAY'),
    }
    state = dict(game=1, option_set=7, controller=1, round=3, tier=2, health=30, armor=0,
        resources=dict(RESOURCES=5, RESOURCES_USED=2), entities=entities,
        options=[dict(index=i,entity_id=eid,error_code='NONE')
                 for i,eid in enumerate((10,11,12,13,4),1)], targets={1:[2,3],2:[1]})
    state['fingerprint'] = fingerprint(state)
    return state


class DeepBattlerTests(unittest.TestCase):
    def setUp(self):
        self.state=fixture()
        self.actions=candidates(self.state)
        self.context=policy_state(self.state,{})

    def bind(self, **action):
        return bind_first(dict(actions=[action]), self.state, self.actions, self.context)

    def test_sort_shop_and_bind_identity(self):
        result=self.bind(type='BUY_FROM_TAVERN',tavern_index=0,card_name='BG_SHOP_A')
        self.assertEqual(result['action']['entity_id'],'3')
        self.assertEqual(result['action']['target'],3)
        self.assertEqual(self.context['resources']['available_gold'],3)

    def test_hand_spell_preserves_indices_and_play_position(self):
        result=self.bind(type='PLAY_FROM_HAND',hand_index=1,board_index=0)
        self.assertEqual(result['action']['entity_id'],'4')
        self.assertEqual(result['action']['position'],1)
        with self.assertRaisesRegex(RuntimeError,'合法候选'):
            self.bind(type='PLAY_FROM_HAND',hand_index=0,board_index=0)

    def test_sell_and_fixed_buttons(self):
        self.assertEqual(self.bind(type='SELL_FROM_BOARD',board_index=0)['action']['entity_id'],'1')
        self.assertEqual(self.bind(type='ROLL')['action']['kind'],'REFRESH')
        self.assertEqual(self.bind(type='FREEZE')['action']['kind'],'FREEZE')

    def test_invalid_index_name_and_position(self):
        for index in (-1,True,99,'0',None):
            with self.assertRaises(RuntimeError):self.bind(type='BUY_FROM_TAVERN',tavern_index=index)
        with self.assertRaisesRegex(RuntimeError,'卡名'):
            self.bind(type='BUY_FROM_TAVERN',tavern_index=0,card_name='different')
        with self.assertRaisesRegex(RuntimeError,'站位'):
            self.bind(type='PLAY_FROM_HAND',hand_index=1,board_index=2)

    def test_disallowed_first_action_does_not_skip_to_later_buy(self):
        with self.assertRaisesRegex(RuntimeError,'尚不支持'):
            bind_first(dict(actions=[dict(type='HERO_POWER'),dict(type='BUY_FROM_TAVERN',tavern_index=0)]),
                       self.state,self.actions,self.context)

    def test_only_first_action_is_bound(self):
        result=bind_first(dict(actions=[dict(type='ROLL'),dict(type='BUY_FROM_TAVERN',tavern_index=0)]),
                          self.state,self.actions,self.context)
        self.assertEqual(result['discarded_tail'],1)
        self.assertEqual(result['action']['kind'],'REFRESH')

    def test_end_turn_empty_and_already_frozen_do_not_send_input(self):
        self.assertTrue(self.bind(type='END_TURN')['wait'])
        self.assertTrue(bind_first(dict(actions=[]),self.state,self.actions,self.context)['wait'])
        context=copy.deepcopy(self.context)
        context['board_state']['tavern_entities'][0]['frozen']=True
        self.assertTrue(bind_first(dict(actions=[dict(type='FREEZE')]),self.state,self.actions,context)['wait'])

    def test_no_valid_option_no_action(self):
        with self.assertRaisesRegex(RuntimeError,'合法候选'):
            bind_first(dict(actions=[dict(type='ROLL')]),self.state,[],self.context)

    def test_existing_api_and_strategy_routing(self):
        config=dict(base_url='https://example.test/v1',api_key='offline',model='test',strategy_mode='deepbattler')
        response=SimpleNamespace(status_code=200,json=lambda:dict(choices=[dict(message=dict(content='{"actions":[{"type":"ROLL"}]}'))],usage=dict(total_tokens=42)))
        with patch('core.bg_deepbattler.requests.post',return_value=response) as post:
            result=StrategyEngine(config).plan(self.state)
        self.assertEqual(result['action']['kind'],'REFRESH')
        self.assertFalse(result['upstream_weights'])
        self.assertFalse(result['screen_used'])
        self.assertEqual(result['usage']['total_tokens'],42)
        self.assertEqual(post.call_args.kwargs['timeout'],(5,18))
        self.assertFalse(post.call_args.kwargs['allow_redirects'])
        self.assertTrue(post.call_args.kwargs['headers']['x-opencode-session'])
        self.assertEqual(post.call_args.kwargs['headers']['User-Agent'],'GugaBattlegroundAgent/1.0')

    def test_stable_session_changes_with_game_not_move(self):
        from core.bg_transport import model_headers
        config=dict(api_key='offline')
        before=model_headers(config,self.state)['x-opencode-session']
        changed=copy.deepcopy(self.state);changed['option_set']+=1
        self.assertEqual(before,model_headers(config,changed)['x-opencode-session'])
        changed['game']+=1
        self.assertNotEqual(before,model_headers(config,changed)['x-opencode-session'])

    def test_endpoint_never_receives_chat_key(self):
        response=SimpleNamespace(status_code=200,json=lambda:dict(actions=[dict(type='ROLL')]))
        with patch('core.bg_deepbattler.requests.post',return_value=response) as post:
            result=model_pick(self.state,self.actions,{},dict(bg_deepbattler_transport='endpoint',
                bg_deepbattler_endpoint='http://127.0.0.1:7860',api_key='chat-secret'))
        self.assertEqual(post.call_args.kwargs['headers'],{})
        self.assertEqual(post.call_args.args[0],'http://127.0.0.1:7860/generate_actions')
        self.assertEqual(result['transport'],'endpoint')

    def test_endpoint_validation_and_http_failure(self):
        for address in ('http://example.test','https://user:password@example.test','https://example.test/?key=x'):
            with self.assertRaises(RuntimeError),patch('core.bg_deepbattler.requests.post') as post:
                model_pick(self.state,self.actions,{},dict(bg_deepbattler_transport='endpoint',bg_deepbattler_endpoint=address))
            post.assert_not_called()
        response=SimpleNamespace(status_code=503)
        with patch('core.bg_deepbattler.requests.post',return_value=response):
            with self.assertRaisesRegex(RuntimeError,'HTTP 503'):
                model_pick(self.state,self.actions,{},dict(bg_deepbattler_transport='endpoint',bg_deepbattler_endpoint='http://localhost:7860'))

    def test_wait_never_captures_or_executes(self):
        from core.bg_pipeline import OperationEngine
        backend=SimpleNamespace(capture=lambda:self.fail('capture'),execute=lambda:self.fail('execute'))
        result=OperationEngine(backend,{}).execute(dict(wait=True,reason='wait'),None,None,0,0)
        self.assertFalse(result['executed'])

    def test_fresh_process_without_power_log_does_not_reuse_old_game(self):
        from core.log_reader import _select_log_path
        with tempfile.TemporaryDirectory() as folder:
            old=Path(folder)/'Hearthstone_2026_10_22_17_51_27';old.mkdir()
            new=Path(folder)/'Hearthstone_2026_10_23_13_14_31';new.mkdir()
            old_log=old/'Power.log';old_log.write_text('old game')
            self.assertIsNone(_select_log_path([str(old_log)],[str(old),str(new)],True))
            self.assertEqual(_select_log_path([str(old_log)],[str(old),str(new)]),str(old_log))
            new_log=new/'Power.log';new_log.write_text('new game')
            self.assertEqual(_select_log_path([str(old_log),str(new_log)],[str(old),str(new)],True),str(new_log))


if __name__=='__main__':unittest.main()
