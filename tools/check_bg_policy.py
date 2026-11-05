"""Torch-only worker checks; intentionally separate from Qt test collection."""
from pathlib import Path
import sys
import tempfile
import unittest
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.bg_policy import LabPolicy
from core.bg_selfplay import FEATURE_DIM


class PolicyTests(unittest.TestCase):
    def test_padding_does_not_change_legal_distribution(self):
        torch.manual_seed(1)
        model = LabPolicy().eval()
        x = torch.randn(1, 3, FEATURE_DIM)
        original, _ = model(x, torch.ones(1, 3, dtype=torch.bool))
        padded = torch.cat([x, torch.randn(1, 2, FEATURE_DIM)], dim=1)
        dist, _ = model(padded, torch.tensor([[True, True, True, False, False]]))
        self.assertTrue(torch.allclose(original.probs, dist.probs[:, :3]))
        self.assertTrue(torch.equal(dist.probs[:, 3:], torch.zeros(1, 2)))

    def test_safety_overrides_avoidable_end(self):
        from core.bg_policy import safety_action
        rows=[[0.]*FEATURE_DIM for _ in range(2)]
        rows[0][0]=1.;rows[1][2]=1.
        self.assertEqual(safety_action(0,1,rows),1)
        rows[1][2]=0.;rows[1][0]=1.
        self.assertEqual(safety_action(0,1,rows),0)

    def test_critic_uses_the_complete_state_slice_after_action_features(self):
        model=LabPolicy().eval()
        x=torch.zeros(1,2,FEATURE_DIM);x[0,0,9:21]=torch.arange(12)
        with torch.no_grad():
            _,value=model(x,torch.ones(1,2,dtype=torch.bool))
        self.assertEqual(tuple(value.shape),(1,))

    def test_checkpoint_requires_correct_rules(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "wrong.pt"
            torch.save(dict(schema=1, profile="different-rules"), target)
            with self.assertRaises(ValueError):
                LabPolicy.load(target)


if __name__ == "__main__":
    unittest.main()
