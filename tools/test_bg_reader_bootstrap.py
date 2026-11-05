import tempfile
from pathlib import Path
import unittest

from core.bg_live import LiveReader, observed_phase, fingerprint

POWER = 'D 12:00:00.0 PowerTaskList.DebugPrintPower() - '


class ReaderBootstrapTests(unittest.TestCase):
    def test_player_mapping_before_game_start_resolves_named_updates(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'Power.log'
            text = 'D 12:00:00.0 GameState.DebugPrintGame() - PlayerID=1, PlayerName=TestPlayer#123\n'
            text += POWER+'CREATE_GAME\n'+POWER+'Player EntityID=8 PlayerID=1\n'
            text += POWER+'TAG_CHANGE Entity=TestPlayer#123 tag=RESOURCES_USED value=7\n'
            text += POWER+'TAG_CHANGE Entity=TestPlayer#123 tag=PLAYSTATE value=LOST\n'
            path.write_bytes(text.encode())
            a,b = LiveReader(path), LiveReader(path,latest_game=True)
            a.poll(); b.poll()
            self.assertEqual(a.parser.entities,b.parser.entities)
            self.assertEqual(b.parser.entities[8]['RESOURCES_USED'],7)
            self.assertEqual(b.parser.entities[8]['PLAYSTATE'],'LOST')

    def reader_fixture(self):
        reader = LiveReader('unused')
        reader.parser.entities = {
            7: dict(CARDTYPE='GAME', BACON_IN_COMBAT_PHASE=0),
            8: dict(CARDTYPE='PLAYER', CONTROLLER=1, PLAYSTATE='PLAYING'),
            9: dict(CARD_ID='TB_BaconShop_DragBuy', CONTROLLER=1, ZONE='PLAY'),
            10: dict(CARD_ID='BG_CARD', CARDTYPE='MINION', CONTROLLER=9, ZONE='PLAY'),
        }
        reader.parser.options = {1:dict(index=1, entity_id=9, error_code='NONE')}
        reader.targets = {1:[10]}
        return reader

    def test_historical_ui_helpers_do_not_bloat_state(self):
        reader = self.reader_fixture()
        reader.parser.entities[20] = dict(CARD_ID='TB_BaconShop_DragBuy', CARDTYPE='MOVE_MINION_HOVER_TARGET',
                                          CONTROLLER=1, ZONE='PLAY')
        reader.parser.entities[21] = dict(CARD_ID='BG_HAND', CARDTYPE='MINION', CONTROLLER=1, ZONE='HAND')
        current = reader.state()
        self.assertNotIn('20', current['entities'])
        self.assertIn('21', current['entities'])
        self.assertIn('9', current['entities'])

    def test_upgrade_cost_uses_active_button_and_preserves_zero(self):
        reader = self.reader_fixture()
        reader.parser.entities[22] = dict(CARD_ID='TB_BaconShopTechUp02_Button', CONTROLLER=1, COST=0)
        reader.parser.options[2] = dict(index=2, entity_id=22, error_code='NONE')
        self.assertEqual(reader.state()['upgrade_cost'], 0)
        reader.parser.entities[8]['BACON_TAVERN_UPGRADE_COST'] = 4
        self.assertEqual(reader.state()['upgrade_cost'], 4)

    def test_rule_keywords_and_prices_invalidate_old_decision(self):
        current = self.reader_fixture().state()
        old = fingerprint(current)
        current['entities']['10']['DIVINE_SHIELD'] = 1
        self.assertNotEqual(fingerprint(current), old)
        old = fingerprint(current)
        current['upgrade_cost'] = 0
        self.assertNotEqual(fingerprint(current), old)

    def test_reverse_scan_finds_start_beyond_last_chunk(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'Power.log'
            text = POWER+'CREATE_GAME\n'+POWER+'GameEntity EntityID=1\n'
            start = len(text.encode())
            text += POWER+'CREATE_GAME\n'+POWER+'GameEntity EntityID=7\n'
            text += 'unrelated animation\n'*200
            path.write_bytes(text.encode())
            reader = LiveReader(path, latest_game=True)
            reader.BOOTSTRAP_CHUNK = 256
            reader.poll()
            self.assertEqual(reader.game_start_offset, start)
            self.assertEqual(reader.parser.game_index, 1)

    def test_latest_game_matches_full_replay_and_retains_build(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'Power.log'
            text = 'D 12:00:00.0 GameState.DebugPrintGame() - BuildNumber=254477\n'
            text += POWER+'CREATE_GAME\n'+POWER+'GameEntity EntityID=1\n'
            text += POWER+'TAG_CHANGE Entity=GameEntity tag=BACON_IN_COMBAT_PHASE value=1\n'
            second_offset = len(text.encode())
            text += POWER+'CREATE_GAME\n'+POWER+'GameEntity EntityID=7\n'
            text += POWER+'TAG_CHANGE Entity=GameEntity tag=BACON_IN_COMBAT_PHASE value=0\n'
            path.write_bytes(text.encode())
            full, latest = LiveReader(path), LiveReader(path, latest_game=True)
            full.poll(); latest.poll()
            self.assertEqual(full.parser.entities, latest.parser.entities)
            self.assertEqual(latest.client_build, 254477)
            self.assertEqual(latest.game_start_offset, second_offset)
            self.assertEqual(observed_phase(latest.parser), 'recruit')
            self.assertEqual(latest.offset, path.stat().st_size)

    def test_incremental_partial_line_is_completed_once(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'Power.log'
            path.write_text(POWER+'CREATE_GAME\n'+POWER+'GameEntity EntityID=7\n'+
                            POWER+'TAG_CHANGE Entity=GameEntity tag=BACON_IN_COMBAT_PHASE value=', encoding='utf-8')
            reader = LiveReader(path, latest_game=True); reader.poll()
            self.assertEqual(observed_phase(reader.parser), 'unknown')
            with path.open('a', encoding='utf-8') as out: out.write('0\n')
            reader.poll()
            self.assertEqual(observed_phase(reader.parser), 'recruit')
            revision = reader.parser.revision
            reader.poll()
            self.assertEqual(reader.parser.revision, revision)

    def test_no_marker_falls_back_to_normal_replay(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'Power.log'
            path.write_text(POWER+'GameEntity EntityID=7\n', encoding='utf-8')
            reader = LiveReader(path, latest_game=True); reader.poll()
            self.assertEqual(reader.parser.entities[7]['CARDTYPE'], 'GAME')

    def test_snapshot_targets_are_detached_from_reader(self):
        reader = LiveReader('unused')
        reader.parser.entities = {
            7: dict(CARDTYPE='GAME', BACON_IN_COMBAT_PHASE=0),
            8: dict(CARDTYPE='PLAYER', CONTROLLER=1, PLAYSTATE='PLAYING'),
            9: dict(CARD_ID='TB_BaconShop_DragBuy', CONTROLLER=1, ZONE='PLAY'),
            10: dict(CARD_ID='BG_CARD', CARDTYPE='MINION', CONTROLLER=9, ZONE='PLAY'),
        }
        reader.parser.options = {1:dict(index=1, entity_id=9, error_code='NONE')}
        reader.targets = {1:[10]}
        snapshot = reader.state()
        old_hash = fingerprint(snapshot)
        reader.targets[1].append(11)
        reader.parser.options[1]['error_code'] = 'REQ_ENOUGH_MANA'
        self.assertEqual(snapshot['targets'], {1:[10]})
        self.assertEqual(snapshot['options'][0]['error_code'], 'NONE')
        self.assertEqual(fingerprint(snapshot), old_hash)

    def test_new_game_changes_origin_and_resets_targets(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'Power.log'
            path.write_text(POWER+'CREATE_GAME\n', encoding='utf-8')
            reader = LiveReader(path, latest_game=True); reader.poll()
            first = reader.game_start_offset
            reader.targets[3] = [10]
            with path.open('a', encoding='utf-8') as out: out.write(POWER+'CREATE_GAME\n')
            reader.poll()
            self.assertGreater(reader.game_start_offset, first)
            self.assertEqual(reader.targets, {})


if __name__ == '__main__': unittest.main()
