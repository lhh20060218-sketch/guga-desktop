import threading,time,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from core.bg_live_prior import features,rank
from core.bg_auto import prepare_battleground


def fixture_state():
    entities={
        '1':dict(CARD_ID='BG_DRAGON',CONTROLLER=1,ZONE='PLAY',CARDTYPE='MINION',ATK=6,HEALTH=6,ZONE_POSITION=1),
        '2':dict(CARD_ID='BG_BEAST',CONTROLLER=0,ZONE='PLAY',CARDTYPE='MINION',ATK=4,HEALTH=5),
        '3':dict(CARD_ID='TB_BaconShop_8p_Reroll_Button',CONTROLLER=1,ZONE='PLAY')}
    return dict(controller=1,client_build=254477,round=6,tier=3,health=24,armor=2,resources=dict(RESOURCES=8,RESOURCES_USED=5),
        entities=entities,options=[],targets={},fingerprint='fixture')


class PriorTests(unittest.TestCase):
    def test_trained_champion_ranks_only_for_matching_patch(self):
        state=fixture_state()
        actions=[dict(kind='BUY',target='2',entity_id='2',action_id='buy'),
                 dict(kind='REFRESH',entity_id='3',action_id='refresh')]
        rows=features(state,actions,{})
        self.assertTrue(all(len(r)==48 for r in rows))
        result=rank(state,actions,{})
        # The 36.2 laboratory champion must be disabled in the 37.0 client.
        self.assertFalse(result['available'])
        self.assertEqual(result['reason'],'version_mismatch')
        with patch('core.bg_version.client_patch',return_value='36.2.2.249896'):
            result=rank(state,actions,{})
        self.assertTrue(result['available'])
        self.assertEqual({x['action_id'] for x in result['ranked']},{'buy','refresh'})

    def test_live_reader_exposes_client_build_for_versioned_human_model(self):
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            from core.bg_live import LiveReader
            path=Path(folder)/'Power.log';path.write_text('',encoding='utf-8');reader=LiveReader(path)
            self.assertIsNone(reader.client_build)

    def test_live_model_receives_current_build_human_advisory(self):
        import json
        from types import SimpleNamespace
        from core.bg_live import model_pick
        state=fixture_state();actions=[dict(kind='BUY',target='2',entity_id='2',action_id='buy')]
        reply=dict(state_id=state['fingerprint'],action_id='buy',reason='当前战力')
        response=SimpleNamespace(status_code=200,json=lambda:dict(choices=[dict(message=dict(content=json.dumps(reply)))],usage={}))
        with patch('core.bg_live.requests.post',return_value=response) as post:
            result=model_pick(state,actions,{},dict(base_url='https://example.test',api_key='offline',model='fixture'))
        payload=post.call_args.kwargs['json']
        prompt=payload['messages'][0]['content']
        self.assertIn('human_learning_advisory',prompt)
        self.assertEqual(result['action']['action_id'],'buy')

    def test_missing_model_returns_no_action(self):
        result=rank(fixture_state(),[dict(kind='REFRESH',action_id='x')],{},Path('missing-file.json'))
        self.assertFalse(result['available']);self.assertEqual(result['ranked'],[])


class BootstrapTests(unittest.TestCase):
    def test_already_live_game_stops_before_any_click(self):
        backend=SimpleNamespace(find=lambda:1,open=lambda:None)
        reader=SimpleNamespace(poll=lambda:[])
        with patch('core.log_reader.find_log_path',return_value='Power.log'), \
             patch('core.log_reader.read_current_board',return_value=dict(active=True)), \
             patch('core.bg_live.LiveReader',return_value=reader), \
             patch('core.bg_auto._ready',return_value=dict(phase='recruit',state={})), \
             patch('core.bg_live.lobby_step') as click:
            result=prepare_battleground(backend,{},print,threading.Event(),time.monotonic()+2)
        self.assertEqual(result['phase'],'recruit');self.assertEqual(result['log_path'],'Power.log')
        click.assert_not_called()

    def test_deadline_never_claims_entry(self):
        backend=SimpleNamespace(find=lambda:(_ for _ in ()).throw(RuntimeError('closed')),open=lambda:None)
        with patch('core.log_reader.find_log_path',return_value=None), \
             patch('core.log_reader.read_current_board',return_value=dict(active=False)), \
             patch('core.bg_auto.time.sleep'):
            with self.assertRaisesRegex(RuntimeError,'未进入可决策'):
                prepare_battleground(backend,{},lambda _:None,threading.Event(),time.monotonic()-.01)


if __name__=='__main__':unittest.main()
