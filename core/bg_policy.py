"""Optional local policy network for the explicit simulator laboratory profile.

Torch is deliberately isolated here; ordinary chat, TTS and the pet UI do not
import it. Checkpoints are never implicitly selected for real-game decisions.
"""
from pathlib import Path
import torch
from torch import nn
from torch.distributions import Categorical

from core.bg_selfplay import (ACTION_DIM, ENGINE_REVISION, FEATURE_DIM, KINDS,
                              PROFILE, STATE_DIM)


def safety_action(chosen, teacher, rows):
    """Never end recruitment while the legal state has a minion to play."""
    if (chosen == KINDS.index("END") and 0 <= teacher < len(rows)
            and rows[teacher][KINDS.index("PLAY")] == 1.):
        return teacher
    return chosen


class LabPolicy(nn.Module):
    def __init__(self):
        super().__init__()
        self.actor = nn.Sequential(nn.Linear(FEATURE_DIM, 64), nn.Tanh(),
                                   nn.Linear(64, 64), nn.Tanh(), nn.Linear(64, 1))
        self.critic = nn.Sequential(nn.Linear(STATE_DIM, 64), nn.Tanh(), nn.Linear(64, 1))

    def forward(self, x, mask):
        logits = self.actor(x).squeeze(-1).masked_fill(~mask, -1e9)
        return (Categorical(logits=logits),
                self.critic(x[:, 0, ACTION_DIM:ACTION_DIM+STATE_DIM]).squeeze(-1))

    @classmethod
    def load(cls, path):
        path = Path(path)
        if path.stat().st_size > 10_000_000:
            raise ValueError("Laboratory checkpoint exceeds 10 MB")
        checkpoint = torch.load(path, map_location="cpu", weights_only=True)
        if (checkpoint.get("schema") != 1 or checkpoint.get("profile") != PROFILE
                or checkpoint.get("engine_revision") != ENGINE_REVISION
                or checkpoint.get("feature_dim") != FEATURE_DIM):
            raise ValueError("Checkpoint profile, engine revision or feature schema mismatch")
        model = cls()
        model.load_state_dict(checkpoint["state_dict"], strict=True)
        if any(not torch.isfinite(p).all() for p in model.parameters()):
            raise ValueError("Checkpoint contains non-finite parameters")
        return model.eval()

    def choose(self, rows, teacher):
        with torch.no_grad():
            dist, _ = self(torch.tensor([rows], dtype=torch.float32),
                           torch.ones(1, len(rows), dtype=torch.bool))
            return safety_action(int(dist.logits.argmax(-1).item()), teacher, rows)
