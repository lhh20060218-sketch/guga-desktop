import tempfile
import unittest
from pathlib import Path

from core import log_reader as lr
from core import match_history as mh


class BattlegroundResultTests(unittest.TestCase):
    def test_uses_latest_local_hero_placement_at_final_screen(self):
        saved = {name: getattr(lr, name) for name in (
            "_ents", "_local_controller", "_player_id_to_ent", "_players",
            "_player_order", "_hero_order", "_game_serial", "LOG_PATH")}
        try:
            lr._ents = {
                0: {"CARDTYPE": "GAME", "STEP": "FINAL_GAMEOVER", "TURN": 22},
                11: {"CARDTYPE": "PLAYER", "CONTROLLER": 4,
                     "HERO_ENTITY": 31, "PLAYSTATE": "PLAYING"},
                31: {"CARDTYPE": "HERO", "CONTROLLER": 4,
                     "CARD_ID": "TB_BaconShop_HERO_PH", "ZONE": "SETASIDE"},
                96: {"CARDTYPE": "HERO", "CONTROLLER": 4,
                     "CARD_ID": "TB_BaconShop_HERO_78_SKIN_E",
                     "ZONE": "GRAVEYARD", "PLAYER_LEADERBOARD_PLACE": 6},
                19653: {"CARDTYPE": "HERO", "CONTROLLER": 4,
                         "CARD_ID": "TB_BaconShop_HERO_78_SKIN_E",
                         "ZONE": "SETASIDE", "PLAYER_LEADERBOARD_PLACE": 4},
            }
            lr._local_controller = 4
            lr._player_id_to_ent = {4: 11}
            lr._players = {}
            lr._player_order = []
            lr._hero_order = []
            lr._game_serial = 1
            lr.LOG_PATH = "test-power.log"

            result = lr._build_board()
            self.assertEqual(result["reason"], "game_over")
            self.assertEqual(result["place"], 4)
            self.assertEqual(result["playstate"], "LOST")
            self.assertFalse(result["active"])
        finally:
            for name, value in saved.items():
                setattr(lr, name, value)

    def test_duplicate_game_key_is_not_recorded_twice(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_path, old_cache = mh._PATH, mh._cache
            try:
                mh._PATH = str(Path(tmp) / "history.json")
                mh._cache = None
                first = mh.record_result("loss", 4, 22, game_key="same-game")
                second = mh.record_result("loss", 4, 22, game_key="same-game")
                self.assertEqual(len(first), 1)
                self.assertEqual(len(second), 1)
            finally:
                mh._PATH, mh._cache = old_path, old_cache


if __name__ == "__main__":
    unittest.main()
