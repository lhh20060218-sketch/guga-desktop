"""Anonymized tag-observation tests; no files from real players are read."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.bg_agent import SnapshotError, local_decision
from core.bg_observation import available_gold, normalize_tag_observation, remaining_health


class ObservationTests(unittest.TestCase):
    def observation(self):
        return {"game_id": "synthetic", "revision": 1, "patch": "reference", "source": "offline",
            "phase": "recruit", "local_controller": 1, "shop_controller": 9,
            "hero_entity_id": "h", "player_entity_id": "p", "entities": {
                "h": {"CARDTYPE": "HERO", "CONTROLLER": 1, "HEALTH": 30, "DAMAGE": 7, "ARMOR": 2, "PLAYER_TECH_LEVEL": 2},
                "p": {"CONTROLLER": 1, "RESOURCES": 6, "TEMP_RESOURCES": 1, "RESOURCES_USED": 3},
                "s": {"CARDTYPE": "MINION", "CONTROLLER": 9, "ZONE": "PLAY", "CARD_ID": "X", "ATK": 4, "HEALTH": 4, "DAMAGE": 0, "COST": 0}}}

    def test_current_resources_and_health(self):
        state = normalize_tag_observation(self.observation())
        self.assertEqual(state["gold"], 4)
        self.assertEqual(state["health"], 23)
        self.assertEqual(state["shop"][0]["entity_id"], "s")

    def test_mana_cost_does_not_become_purchase_price(self):
        state = normalize_tag_observation(self.observation())
        self.assertIsNone(state["shop"][0]["buy_cost"])
        self.assertEqual(local_decision(state)["status"], "blocked")

    def test_missing_damage_and_spent_resources_remain_unknown(self):
        self.assertIsNone(remaining_health({"HEALTH": 30}))
        self.assertIsNone(available_gold({"RESOURCES": 6, "TEMP_RESOURCES": 0}))
        self.assertIsNone(available_gold({"RESOURCES": 1, "TEMP_RESOURCES": 0, "RESOURCES_USED": 4}))

    def test_unconfirmed_identity_rejected(self):
        for field, value in (("local_controller", 9), ("hero_entity_id", "missing")):
            raw = self.observation()
            raw[field] = value
            with self.assertRaises(SnapshotError):
                normalize_tag_observation(raw)

    def test_explicit_effective_price_is_required(self):
        raw = self.observation()
        raw.update(rules_profile="vanilla-recruit-v1", economy_confirmed=True,
                   effective_costs={"s": {"buy_cost": 3, "currency": "gold"}})
        d = local_decision(normalize_tag_observation(raw))
        self.assertTrue(any(x["kind"] == "BUY" for x in d["candidates"]))


if __name__ == "__main__":
    unittest.main()
