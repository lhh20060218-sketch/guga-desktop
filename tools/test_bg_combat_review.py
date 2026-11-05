import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.bg_combat_review import parse_hdt_records, render_review, load_card_metadata, snapshot_review

COMBAT = """第1回合，托奇 VS 沃金
我方随从：美味龙虾（金）（44-22）；囤食土狼（84-68）；
对方随从：
模拟结果（模拟20000次）：0.3%抬走对面，0.3%赢，2.9%平，96.8%输，79.2%被抬走
实际结果：输，被对面打了15，我被抬走了！
"""


class CombatReviewTests(unittest.TestCase):
    def first(self, text=COMBAT):
        return parse_hdt_records(text)["groups"][0]["rounds"][0]

    def test_estimated_probabilities_separate_from_actual_and_lethal(self):
        r = self.first()
        e = r["estimates"][0]
        self.assertEqual(e["simulations"], 20000)
        self.assertAlmostEqual(e["probabilities"]["own_lethal"], .792)
        self.assertEqual(e["issues"], [])
        self.assertEqual(r["actuals"][0], dict(outcome="loss", damage=15, damage_direction="received", own_alive=False))

    def test_golden_name_and_empty_board(self):
        r = self.first()
        self.assertEqual(r["own_board"][0]["name"], "美味龙虾（金）")
        self.assertEqual(r["own_board"][0]["attack"], 44)
        self.assertEqual(r["opponent_board"], [])

    def test_missing_or_malformed_board_not_empty(self):
        self.assertIsNone(self.first("第1回合，甲 VS 乙")["own_board"])
        self.assertIsNone(self.first("第1回合，甲 VS 乙\n我方随从：不完整（4-")["own_board"])

    def test_duplicate_headers_and_estimates_deduplicated(self):
        r = self.first(COMBAT + COMBAT)
        self.assertEqual(r["duplicate_headers"], 1)
        self.assertEqual(len(r["estimates"]), 1)
        self.assertEqual(len(r["actuals"]), 1)
        self.assertIn(6, r["source_lines"])

    def test_changed_board_and_conflicting_estimates_preserved(self):
        report = parse_hdt_records(COMBAT + COMBAT.replace("96.8%输", "90%输"))
        r = report["groups"][0]["rounds"][0]
        self.assertEqual(len(r["estimates"]), 2)
        self.assertTrue(r["estimates"][1]["issues"])
        report = parse_hdt_records(COMBAT + COMBAT.replace("84-68", "90-68"))
        self.assertEqual(len(report["groups"][0]["rounds"]), 2)

    def test_explicit_end_and_round_reset_boundaries(self):
        report = parse_hdt_records(COMBAT + "游戏结束，战绩：第5名，原分数987654321，现分数0\n" + COMBAT)
        self.assertEqual(len(report["groups"]), 2)
        self.assertEqual(report["groups"][0]["placements"], [5])
        self.assertNotIn("987654321", json.dumps(report))
        self.assertNotIn("原分数", json.dumps(report, ensure_ascii=False))
        report = parse_hdt_records(COMBAT.replace("第1回合", "第8回合") + COMBAT)
        self.assertEqual(report["groups"][1]["boundary_evidence"], "round_decreased_unverified")

    def test_hero_transformation_does_not_split_group(self):
        report = parse_hdt_records(COMBAT + COMBAT.replace("第1回合，托奇", "第2回合，雷诺"))
        self.assertEqual(len(report["groups"]), 1)

    def test_missing_round_marker_not_interpreted_as_actual(self):
        r = self.first("第7回合，我直接拔线~")
        self.assertTrue(r["missing_combat"])
        self.assertEqual(r["actuals"], [])
        self.assertEqual(r["estimates"], [])

    def test_truncated_last_round_and_unmatched_sources(self):
        report = parse_hdt_records(COMBAT + "第2回合，甲 VS 乙\n我方随从：")
        self.assertFalse(report["training_ready"])
        self.assertEqual(report["groups"][0]["power_log_join"], "unmatched")
        self.assertEqual(report["groups"][0]["rounds"][-1]["estimates"], [])
        self.assertIsNone(report["groups"][0]["rounds"][-1]["own_board"])
        self.assertIn("未校验规则覆盖", render_review(report))

    def test_invalid_probabilities_flagged_not_corrected(self):
        e = self.first(COMBAT.replace("79.2%被抬走", "99.9%被抬走"))["estimates"][0]
        self.assertIn("lethal_exceeds_loss", e["issues"])
        self.assertAlmostEqual(e["probabilities"]["own_lethal"], .999)

    def test_snapshot_missing_health_and_gold_remain_unknown(self):
        snap = {"entities": {"2": {"CARDTYPE": "PLAYER", "CONTROLLER": 1, "HERO_ENTITY": 4, "RESOURCES": 10},
                             "4": {"HEALTH": 30}}}
        r = snapshot_review(snap, 1, {})
        self.assertIsNone(r["health"])
        self.assertIsNone(r["gold"])
        snap["entities"]["4"]["DAMAGE"] = 11
        snap["entities"]["2"].update(TEMP_RESOURCES=0, RESOURCES_USED=6)
        r = snapshot_review(snap, 1, {})
        self.assertEqual((r["health"], r["gold"]), (19, 4))
        self.assertIsNone(r["plugin_win_rate"])
        self.assertFalse(r["phase_and_stability_confirmed"])

    def test_selective_card_cache_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cards.xml"
            path.write_text('<CardDefs><Entity CardID="BG_X"><Tag name="CARDNAME"><zhCN>龙虾</zhCN></Tag>'
                            '<Tag name="CARDTEXT"><zhCN>+{0}/+{1}</zhCN></Tag>'
                            '<Tag name="BACON_SUBSET_BEAST" value="1"/></Entity>'
                            '<Entity CardID="OTHER"/></CardDefs>', encoding="utf-8")
            cards = load_card_metadata(path, {"BG_X"})
        self.assertEqual(list(cards), ["BG_X"])
        self.assertEqual(cards["BG_X"]["pool_subsets"], ["BEAST"])
        self.assertEqual(cards["BG_X"]["text_template"], "+{0}/+{1}")


if __name__ == "__main__":
    unittest.main()
