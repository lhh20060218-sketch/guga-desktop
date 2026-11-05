"""Offline tests: legality, lookahead boundaries, stale decisions, provider failures."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import requests
from core.bg_agent import (Action, DecisionEngine, ROOT, SnapshotError, blockers,
    decision_is_current, legal_actions, local_decision, rank_actions, state_id,
    transition, validate_snapshot)


def demo():
    return json.loads((ROOT / "data/bg_agent/demo.json").read_text(encoding="utf-8"))


class RulesTests(unittest.TestCase):
    def setUp(self):
        self.s = validate_snapshot(demo())

    def test_demo_prefers_stronger_purchase(self):
        d = local_decision(self.s)
        self.assertEqual((d["action"]["kind"], d["action"]["entity_id"]), ("BUY", "shop-1"))
        self.assertEqual(d["action"]["lookahead"]["kind"], "PLAY")
        self.assertFalse(d["executable"])

    def test_budget_is_available_gold_not_maximum(self):
        self.s["gold"] = 2
        self.assertFalse(any(a.kind == "BUY" for a in legal_actions(self.s)))

    def test_unknown_cost_is_never_free(self):
        self.s["shop"][0]["buy_cost"] = None
        self.assertNotIn(Action("BUY", "shop-1"), legal_actions(self.s))
        self.s["refresh_cost"] = None
        self.assertNotIn(Action("REFRESH"), legal_actions(self.s))

    def test_health_currency_is_not_treated_as_gold(self):
        self.s["shop"][0]["currency"] = "health"
        self.assertNotIn(Action("BUY", "shop-1"), legal_actions(self.s))

    def test_full_hand_prevents_purchase(self):
        self.s["hand"] = [{**self.s["board"][0], "entity_id": f"hand-{i}"} for i in range(10)]
        self.assertFalse(any(a.kind == "BUY" for a in legal_actions(self.s)))

    def test_full_board_prevents_play(self):
        self.s["hand"] = [{**self.s["board"][0], "entity_id": "hand-1"}]
        self.s["board"] = [{**self.s["board"][0], "entity_id": f"b-{i}"} for i in range(7)]
        self.assertFalse(any(a.kind == "PLAY" for a in legal_actions(self.s)))

    def test_special_hand_effect_is_not_blindly_played(self):
        self.s["hand"] = [{**self.s["board"][0], "entity_id": "hand-1", "effect": "targeted"}]
        self.assertFalse(any(a.kind == "PLAY" for a in legal_actions(self.s)))

    def test_spells_are_explicitly_outside_subset(self):
        self.s["shop"][0]["kind"] = "spell"
        self.assertNotIn(Action("BUY", "shop-1"), legal_actions(self.s))
        self.assertTrue(any("法术" in w for w in local_decision(self.s)["warnings"]))

    def test_vanilla_purchase_and_play_preserve_identity(self):
        before = deepcopy(self.s)
        n = transition(self.s, Action("BUY", "shop-1"))
        self.assertEqual(n["gold"], 2)
        self.assertEqual(n["hand"][0]["entity_id"], "shop-1")
        n2 = transition(n, Action("PLAY", "shop-1", 1))
        self.assertEqual(n2["board"][1]["entity_id"], "shop-1")
        self.assertEqual(self.s, before)

    def test_unknown_effect_stops_search(self):
        self.s["shop"][0]["effect"] = "unknown"
        self.assertIsNone(transition(self.s, Action("BUY", "shop-1")))

    def test_other_card_triggers_and_global_unknowns_stop_search(self):
        self.s["board"][0]["effect"] = "unknown"
        self.assertIsNone(transition(self.s, Action("BUY", "shop-1")))
        self.s["board"][0]["effect"] = "vanilla"
        self.s["vanilla_transitions_confirmed"] = False
        self.assertIsNone(transition(self.s, Action("BUY", "shop-1")))

    def test_triple_stops_search_before_fabricating_discover(self):
        self.s["board"] = [{**self.s["shop"][0], "entity_id": f"pair-{i}"} for i in range(2)]
        self.assertIsNone(transition(self.s, Action("BUY", "shop-1")))

    def test_refresh_does_not_invent_shop(self):
        self.assertIsNone(transition(self.s, Action("REFRESH")))

    def test_illegal_action_cannot_transition(self):
        with self.assertRaises(SnapshotError):
            transition(self.s, Action("BUY", "invented-card"))

    def test_free_refresh_and_freeze_do_not_loop(self):
        self.s["refresh_cost"] = 0
        rows = rank_actions(self.s)
        self.assertLess(len(rows), 40)
        self.s["frozen"] = True
        self.assertNotIn(Action("FREEZE"), legal_actions(self.s))

    def test_unconfirmed_economy_and_unknown_phase_block(self):
        for changes in ({"economy_confirmed": False}, {"phase": "unknown"},
                        {"gold": None}, {"phase": "combat"}, {"phase": "ended"}):
            with self.subTest(changes=changes):
                s = {**self.s, **changes}
                self.assertEqual(local_decision(s)["status"], "blocked")

    def test_choices_have_own_phase_and_effective_cost(self):
        self.s["phase"] = "choice"
        self.s["choices"] = [{**self.s["shop"][0], "entity_id": "choice-1", "choice_cost": 6}]
        self.assertEqual(local_decision(self.s)["status"], "blocked")
        self.s["choices"][0]["choice_cost"] = 0
        self.assertEqual(legal_actions(self.s), [Action("CHOOSE", "choice-1")])
        self.s["phase"] = "recruit"
        self.assertTrue(blockers(self.s))

    def test_old_or_future_live_observations_block(self):
        self.s.update(source="live", observed_at=time.time() - 10)
        self.assertEqual(local_decision(self.s)["status"], "blocked")
        self.s["observed_at"] = time.time() + 10
        self.assertEqual(local_decision(self.s)["status"], "blocked")

    def test_editing_gold_revision_or_entities_invalidates_decision(self):
        decision = local_decision(self.s)
        self.assertTrue(decision_is_current(decision, self.s))
        for key, value in (("gold", 0), ("revision", 2), ("game_id", "different")):
            with self.subTest(key=key):
                self.assertFalse(decision_is_current(decision, {**self.s, key: value}))

    def test_duplicate_ids_bool_numbers_and_nan_rejected(self):
        invalid = []
        duplicate = demo()
        duplicate["shop"][0]["entity_id"] = duplicate["board"][0]["entity_id"]
        invalid.append(duplicate)
        for key, value in (("gold", True), ("gold", -1), ("gold", "?"),
                           ("gold", float("nan")), ("revision", False), ("schema_version", True)):
            invalid.append({**demo(), key: value})
        for raw in invalid:
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError):
                    validate_snapshot(raw)

    def test_malformed_card_metadata_is_a_validation_error(self):
        for key, value in (("currency", []), ("effect", {}), ("kind", 123)):
            s = demo()
            s["shop"][0][key] = value
            with self.assertRaises(SnapshotError):
                validate_snapshot(s)

    def test_rules_revision_change_invalidates_decision(self):
        decision = local_decision(self.s)
        with patch("core.bg_agent.rule_context", return_value={"revision": "new-rules"}):
            self.assertFalse(decision_is_current(decision, self.s))


class ModelTests(unittest.TestCase):
    def setUp(self):
        self.s = validate_snapshot(demo())
        self.engine = DecisionEngine({"api_key": "test-secret-do-not-print",
            "base_url": "https://opencode.ai/inference/go/openai/v1", "model": "deepseek-v4.1-flash"})

    def response(self, picked=None):
        if picked is None:
            picked = {"state_id": state_id(self.s), "action_id": legal_actions(self.s)[0].action_id,
                      "explanation": "当前保留金币；仅为测试输出"}
        return Mock(status_code=200, json=lambda: {
            "choices": [{"message": {"content": json.dumps(picked)}}],
            "usage": {"total_tokens": 30}})

    @patch("core.bg_agent.requests.post")
    def test_model_is_explicit_and_blocked_state_never_calls(self, post):
        self.engine.decide(self.s)
        self.engine.decide({**self.s, "phase": "combat"}, True)
        post.assert_not_called()

    @patch("core.bg_agent.requests.post")
    def test_valid_choice_reuses_session_and_exact_configured_route(self, post):
        post.return_value = self.response()
        first = self.engine.decide(self.s, True)
        second = self.engine.decide(self.s, True)
        self.assertEqual(first["source"], "configured_model")
        self.assertTrue(decision_is_current(second, self.s))
        self.assertEqual(post.call_args.args[0], self.engine.config["base_url"] + "/chat/completions")
        ids = [c.kwargs["headers"]["x-opencode-session"] for c in post.call_args_list]
        self.assertEqual(ids[0], ids[1])
        self.assertFalse(post.call_args.kwargs["allow_redirects"])

    @patch("core.bg_agent.requests.post")
    def test_invented_actions_and_stale_model_state_fall_back(self, post):
        for picked in ({"state_id": state_id(self.s), "action_id": "BUY-FAKE", "explanation": "x"},
                       {"state_id": "old", "action_id": legal_actions(self.s)[0].action_id}):
            post.return_value = self.response(picked)
            d = self.engine.decide(self.s, True)
            self.assertEqual(d["status"], "fallback")
            self.assertEqual(d["source"], "local_heuristic")

    @patch("core.bg_agent.requests.post")
    def test_timeout_quota_and_bad_json_do_not_retry_or_leak_secrets(self, post):
        for response in (requests.Timeout("secret"), Mock(status_code=429),
                         Mock(status_code=200, json=lambda: {"choices": []})):
            post.reset_mock(side_effect=True)
            if isinstance(response, Exception):
                post.side_effect = response
            else:
                post.side_effect = None
                post.return_value = response
            d = self.engine.decide(self.s, True)
            self.assertEqual(d["status"], "fallback")
            self.assertEqual(post.call_count, 1)
            self.assertNotIn("test-secret", json.dumps(d))

    @patch("core.bg_agent.requests.post")
    def test_payload_whitelists_game_data(self, post):
        post.return_value = self.response()
        s = deepcopy(self.s)
        s["account_id"] = "private-account"
        s["shop"][0]["api_key"] = "accidental-card-secret"
        self.engine.decide(s, True)
        payload = json.dumps(post.call_args.kwargs["json"])
        self.assertNotIn("private-account", payload)
        self.assertNotIn("accidental-card-secret", payload)
        self.assertNotIn("test-secret", payload)

    @patch("core.bg_agent.requests.post")
    def test_missing_key_falls_back_without_network(self, post):
        d = DecisionEngine().decide(self.s, True)
        self.assertEqual(d["model_error"], "missing_api_key")
        post.assert_not_called()

    @patch("core.bg_agent.requests.post")
    def test_invalid_endpoint_does_not_crash(self, post):
        self.engine.config["base_url"] = "https://[invalid"
        self.assertEqual(self.engine.decide(self.s, True)["model_error"], "invalid_endpoint")
        post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
