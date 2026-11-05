"""Offline ranking contracts and optional real-engine integration tests."""
import os
from pathlib import Path
import subprocess
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.bg_selfplay import (Arena, FEATURE_DIM, load_engine, placement_from_groups,
                              teacher_policy, top4_credit)


class RankingTests(unittest.TestCase):
    def test_same_round_deaths_share_rank_without_seat_bias(self):
        ranks = placement_from_groups([[3], [5], [1, 7], [0, 2, 4, 6]])
        self.assertEqual(ranks, [6.5, 3.5, 6.5, 1., 6.5, 2., 6.5, 3.5])
        self.assertEqual(sum(ranks), 36)

    def test_missing_or_duplicate_seats_rejected(self):
        for groups in ([[0], [1, 2]], [[0, 1, 2, 3, 4, 5, 6, 7, 0]]):
            with self.assertRaises(ValueError):
                placement_from_groups(groups)

    def test_top4_tie_has_fractional_credit(self):
        ranks = placement_from_groups([[0], [1], [2, 3, 4], [5], [6], [7]])
        self.assertAlmostEqual(top4_credit(ranks, 2), 2/3)
        self.assertAlmostEqual(sum(top4_credit(ranks, i) for i in range(8)), 4.)


class LocalPolicyTests(unittest.TestCase):
    def test_policy_in_isolated_training_process(self):
        # Windows Qt/Torch DLL loading can conflict in a shared process. The
        # supported training/inference entrypoints are independent workers.
        result = subprocess.run([sys.executable, str(Path(__file__).with_name("check_bg_policy.py"))],
                                text=True, capture_output=True, timeout=40)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


@unittest.skipUnless(os.environ.get("GUGA_BG_ENGINE"), "Set GUGA_BG_ENGINE to pinned external checkout")
class EngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = load_engine(os.environ["GUGA_BG_ENGINE"])

    def test_complete_game_deterministic_and_real_eliminations(self):
        arena = Arena(self.engine)
        a = arena.run([teacher_policy]*8, 42, collect=True)
        b = arena.run([teacher_policy]*8, 42)
        self.assertTrue(a["finished"])
        self.assertEqual(a["placements"], b["placements"])
        self.assertEqual(a["turns"], b["turns"])
        self.assertEqual(a["action_limit_hits"], 0)
        self.assertGreater(a["combat_phases"], 0)
        self.assertEqual(sum(a["placements"]), 36)
        self.assertEqual(sum(len(t["eliminated"]) for t in a["turns"]), 7)
        for trajectory in a["trajectories"]:
            for step in trajectory:
                self.assertLess(step["action"], len(step["x"]))
                self.assertTrue(all(len(row) == FEATURE_DIM for row in step["x"]))

    def test_truncation_never_fabricates_placement_reward(self):
        result = Arena(self.engine, turn_limit=1).run([teacher_policy]*8, 0)
        self.assertFalse(result["finished"])
        self.assertIsNone(result["placements"])

    def test_wrong_policy_count_rejected(self):
        with self.assertRaises(ValueError):
            Arena(self.engine).run([teacher_policy]*7, 1)

    def test_invalid_action_rejected(self):
        with self.assertRaises(ValueError):
            Arena(self.engine).run([lambda rows, teacher: len(rows)]*8, 1)


if __name__ == "__main__":
    unittest.main()
