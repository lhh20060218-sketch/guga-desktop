import copy
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core.bg_live import LiveReader,candidates,fingerprint,validate_grounding,acknowledged,json_reply


def state():
    es={'10':dict(CARD_ID='TB_BaconShop_DragBuy',CONTROLLER=1,ZONE='PLAY'),
        '11':dict(CARD_ID='BG_MINION',CARDTYPE='MINION',CONTROLLER=9,ZONE='PLAY'),
        '12':dict(CARD_ID='BG_HAND',CARDTYPE='MINION',CONTROLLER=1,ZONE='HAND'),
        '13':dict(CARD_ID='TB_BaconShop_8p_Reroll_Button',CONTROLLER=1,ZONE='PLAY')}
    s=dict(game=1,option_set=4,controller=1,round=1,tier=1,resources={},entities=es,
           options=[dict(index=1,entity_id=10,error_code='NONE'),dict(index=2,entity_id=12,error_code='NONE'),
                    dict(index=3,entity_id=13,error_code='REQ_ENOUGH_MANA')],targets={1:[11]})
    s['fingerprint']=fingerprint(s)
    return s


class LiveTests(unittest.TestCase):
    def test_play_receipt_must_match_requested_and_actual_position(self):
        before=state()
        action=next(a for a in candidates(before) if a['kind']=='PLAY')
        after=copy.deepcopy(before)
        after['entities']['12'].update(ZONE='PLAY', ZONE_POSITION=action['position'])
        selected=[dict(option_set_id=4,fields=dict(selectedOption=2,selectedPosition=action['position']))]
        self.assertTrue(acknowledged(before,after,action,selected))
        after['entities']['12']['ZONE_POSITION']=action['position']+1
        self.assertFalse(acknowledged(before,after,action,selected))
        after['entities']['12']['ZONE_POSITION']=action['position']
        selected[0]['fields']['selectedPosition']=action['position']+1
        self.assertFalse(acknowledged(before,after,action,selected))

    def test_missing_entity_is_not_a_freeze_acknowledgement(self):
        before=state(); after=copy.deepcopy(before)
        before['entities']['11']['FROZEN']=0
        del after['entities']['11']
        action=dict(kind='FREEZE',option=3,entity_id='13')
        selected=[dict(option_set_id=4,fields=dict(selectedOption=3))]
        self.assertFalse(acknowledged(before,after,action,selected))

    def test_only_client_valid_candidates(self):
        actions=candidates(state())
        self.assertEqual({a['kind'] for a in actions},{'BUY','PLAY'})
        self.assertEqual(next(a for a in actions if a['kind']=='BUY')['target'],11)

    def test_targeted_hand_not_played_blindly(self):
        s=state()
        s['targets'][2]=[11]
        self.assertNotIn('PLAY',{a['kind'] for a in candidates(s)})

    def test_full_board_has_no_play(self):
        s=state()
        for i in range(7):
            s['entities'][str(100+i)]=dict(CARDTYPE='MINION',CARD_ID='BG_A',CONTROLLER=1,ZONE='PLAY')
        self.assertNotIn('PLAY',{a['kind'] for a in candidates(s)})

    def test_fingerprint_tracks_changes_not_animation(self):
        s=state()
        old=fingerprint(s)
        s['entities']['11']['UNKNOWN_ANIMATION']=5
        self.assertEqual(old,fingerprint(s))
        s['entities']['11']['ATK']=50
        self.assertNotEqual(old,fingerprint(s))

    def test_no_mouse_for_combat_low_confidence_or_nan(self):
        for reply in [dict(phase='combat',confidence=1,source=[.5,.5]),
                      dict(phase='recruit',confidence=.8,source=[.5,.5]),
                      dict(phase='recruit',confidence=1,source=[float('nan'),.5])]:
            with self.assertRaises(RuntimeError):
                validate_grounding(reply,{'kind':'REFRESH'})

    def test_drag_needs_destination(self):
        with self.assertRaises(RuntimeError):
            validate_grounding(dict(phase='recruit',confidence=1,source=[.5,.5]),{'kind':'BUY'})

    def test_lobby_phase_and_action_allowlist(self):
        validate_grounding(dict(phase='battlegrounds_lobby',confidence=1,source=[.5,.5]),{'kind':'START_BG'})
        for kind in ('PURCHASE','DELETE','RUN_SHELL'):
            with self.assertRaises(RuntimeError):
                validate_grounding(dict(phase='recruit',confidence=1,source=[.5,.5]),{'kind':kind})

    def test_ack_requires_client_selection_and_state_effect(self):
        before=state()
        action=next(a for a in candidates(before) if a['kind']=='BUY')
        after=copy.deepcopy(before)
        after['entities']['11'].update(CONTROLLER=1,ZONE='HAND')
        self.assertFalse(acknowledged(before,after,action,[]))
        selected=[dict(option_set_id=4,fields=dict(selectedOption=1,selectedTarget=11))]
        self.assertTrue(acknowledged(before,after,action,selected))
        self.assertFalse(acknowledged(before,before,action,selected))
        selected[0]['fields']['selectedTarget']=999
        self.assertFalse(acknowledged(before,after,action,selected))

    def test_incremental_targets_and_generation_reset(self):
        prefix='D 12:00:00.0 GameState.DebugPrintOptions() - '
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'Power.log'
            p.write_text(prefix+'id=3\n'+prefix+'  option 2 type=POWER mainEntity=[id=8 zone=PLAY] error=NONE\n'+
                         prefix+'    target 0 entity=[id=11 zone=PLAY] error=NONE\n'+
                         prefix+'    target 1 entity=[id=12 zone=PLAY] error=REQ_ENEMY_TARGET\n',encoding='utf-8')
            r=LiveReader(p)
            r.poll()
            self.assertEqual(r.targets,{2:[11]})
            with p.open('a',encoding='utf-8') as f:
                f.write(prefix+'id=4\n')
            r.poll()
            self.assertEqual(r.targets,{})

    def test_json_fences(self):
        self.assertEqual(json_reply('```json\n{"action_id":"WAIT"}\n```')['action_id'],'WAIT')


if __name__=='__main__':
    unittest.main()
