"""Parser evidence contracts; no real logs, network or client inputs required."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.bg_log_capture import EventParser
from tools.build_bg_demonstrations import reconstruct


def power(message):
    return "D 17:00:00.1234567 PowerTaskList.DebugPrintPower() - " + message


class CaptureTests(unittest.TestCase):
    def test_updating_entity_and_indented_tags_cross_chunks(self):
        p = EventParser()
        p.feed(power("FULL_ENTITY - Updating [entityName=Private name id=41 zone=PLAY zonePos=1 cardId=BG_TEST player=1] CardID=BG_TEST"))
        p.feed(power("    tag=CARDTYPE value=MINION"))
        p.feed(power("    tag=CONTROLLER value=1"))
        p.feed(power("    tag=HEALTH value=9"))
        self.assertEqual(p.entities[41]["HEALTH"], 9)
        self.assertNotIn("DAMAGE", p.entities[41])
        self.assertNotIn("Private name", json.dumps(p.snapshot()))

    def test_player_named_resource_change_resolves_without_persisting_name(self):
        p = EventParser()
        p.feed("D 17:00:00.0 GameState.DebugPrintGame() - PlayerID=1, PlayerName=ExampleName#123")
        p.feed(power("Player EntityID=2 PlayerID=1 GameAccountId=[hi=999 lo=888]"))
        out = p.feed(power("TAG_CHANGE Entity=ExampleName#123 tag=RESOURCES_USED value=4"))
        self.assertEqual(p.entities[2]["RESOURCES_USED"], 4)
        self.assertNotIn("ExampleName", json.dumps(out)+json.dumps(p.snapshot()))
        self.assertNotIn("999", json.dumps(p.snapshot()))

    def test_duplicate_power_stream_not_replayed(self):
        p = EventParser()
        p.feed(power("FULL_ENTITY - Creating ID=41 CardID=BG_TEST"))
        p.feed(power("    tag=ATK value=3"))
        ignored = p.feed("D 17:00:00.0 GameState.DebugPrintPower() - TAG_CHANGE Entity=41 tag=ATK value=100")
        self.assertFalse(ignored)
        self.assertEqual(p.entities[41]["ATK"], 3)

    def test_current_option_set_is_attached_and_not_reused_after_reset(self):
        p = EventParser()
        prefix = "D 17:00:00.0 GameState.DebugPrintOptions() - "
        p.feed(prefix+"id=12")
        p.feed(prefix+"option 3 type=POWER mainEntity=[entityName=Hidden id=55 zone=PLAY player=9] error=NONE")
        sent = p.feed("D 17:00:01.0 GameState.SendOption() - selectedOption=3 selectedSubOption=-1 selectedTarget=0 selectedPosition=1")[0]
        self.assertEqual(sent["option_set_id"], 12)
        self.assertEqual(sent["option"]["entity_id"], 55)
        p.feed(prefix+"id=13")
        sent = p.feed("D 17:00:02.0 GameState.SendOption() - selectedOption=3")[0]
        self.assertIsNone(sent["option"])

    def test_unknown_numeric_tag_preserved_without_inventing_semantics(self):
        p = EventParser()
        p.feed(power("FULL_ENTITY - Creating ID=41 CardID=BG_TEST"))
        p.feed(power("    tag=4901 value=2"))
        self.assertEqual(p.entities[41]["4901"], 2)
        self.assertFalse(p.feed(power("    tag=ACCOUNT_NAME value=Someone")))

    def test_unknown_entity_with_nested_brackets_resolves_numeric_identity(self):
        p = EventParser()
        out = p.feed(power("TAG_CHANGE Entity=[entityName=UNKNOWN ENTITY [cardType=INVALID] id=77 zone=PLAY zonePos=1 cardId= player=1] tag=ZONE value=HAND"))
        self.assertEqual(out[0]["entity_id"], 77)
        self.assertEqual(p.entities[77]["ZONE"], "HAND")

    def test_game_entity_alias_maps_to_actual_entity(self):
        p = EventParser()
        p.feed(power("GameEntity EntityID=13"))
        p.feed(power("TAG_CHANGE Entity=GameEntity tag=TURN value=8"))
        self.assertEqual(p.entities[13]["TURN"], 8)
        self.assertNotIn(0, p.entities)

    def test_unmapped_player_is_marked_unresolved_not_guessed(self):
        p = EventParser()
        out = p.feed(power("TAG_CHANGE Entity=Unseen#123 tag=RESOURCES value=8"))
        self.assertEqual(out[0]["type"], "unresolved_tag")
        self.assertNotIn("Unseen", json.dumps(out))

    def test_selected_option_does_not_invent_buy_action(self):
        p = EventParser()
        out = p.feed("D 17:00:00.0 GameState.SendOption() - selectedOption=2")[0]
        self.assertIsNone(out["option"])
        self.assertNotIn("BUY", json.dumps(out))

    def test_replay_context_is_before_action_and_is_immutable(self):
        events = [
            dict(type="game_start"),
            dict(type="entity", entity_id=40, card_id="BG_TEST"),
            dict(type="tag", entity_id=40, tag="CONTROLLER", after=1),
            dict(type="tag", entity_id=40, tag="ZONE", after="HAND"),
            dict(type="option_set", option_set_id=2),
            dict(type="option", level="option", index=1, entity_id=40, type_code="POWER", error_code="NONE"),
            dict(type="selected_option", game_index=1, log_time="17:00:00", source_byte_offset=500,
                 option_set_id=2, fields=dict(selectedOption=1, selectedPosition=3)),
            dict(type="tag", entity_id=40, tag="ZONE", after="PLAY"),
        ]
        samples = list(reconstruct(events, 1))
        self.assertEqual(samples[0]["observed_entities"]["40"]["ZONE"], "HAND")
        self.assertEqual(samples[0]["selected"]["selectedPosition"], 3)
        self.assertTrue(samples[0]["matched"])
        self.assertFalse(samples[0]["training_ready"])

    def test_finite_cli_does_not_process_incomplete_final_line(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            log = root / "Power.log"
            log.write_text(power("FULL_ENTITY - Creating ID=4 CardID=BG_TEST")+"\n"+
                           power("    tag=HEALTH value=10")+"\n"+
                           power("    tag=DAMAGE value=3"), encoding="utf-8")
            cmd = [sys.executable, str(Path(__file__).with_name("observe_bg_logs.py")),
                   "--log", str(log), "--output", str(root/"out"), "--seconds", "0"]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            state = json.loads((root/"out/latest.json").read_text())
            self.assertEqual(state["entities"]["4"]["HEALTH"], 10)
            self.assertNotIn("DAMAGE", state["entities"]["4"])
            report = json.loads((root/"out/report.json").read_text())
            self.assertFalse(report["training_ready"])


if __name__ == "__main__":
    unittest.main()
