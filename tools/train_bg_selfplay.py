"""Bounded CPU experiment: teacher imitation -> eight-seat PPO -> held-out evaluation.

No network requests, game client operations or changes to the pet's model config.
Third-party engine remains in an explicit external checkout.
"""
from __future__ import annotations

import argparse
import copy
from collections import Counter
import gzip
import hashlib
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.bg_selfplay import (Arena, FEATURE_DIM, PROFILE, load_engine,
                              save_json, teacher_policy, top4_credit)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", required=True)
    parser.add_argument("--output", required=True, help="New output directory; existing results are not overwritten")
    parser.add_argument("--bc-games", type=int, default=8)
    parser.add_argument("--rl-games", type=int, default=24)
    parser.add_argument("--bc-epochs", type=int, default=60)
    parser.add_argument("--objective", choices=("top4", "placement"), default="top4")
    parser.add_argument("--eval-games", type=int, default=16)
    parser.add_argument("--seed", type=int, default=1000)
    parser.add_argument("--max-seconds", type=int, default=600)
    parser.add_argument('--expert-battles',nargs='+',default=[],
                        help='Matching-profile DeepSeek trajectory files; no extra API calls')
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not (1 <= args.bc_games <= 100 and 0 <= args.rl_games <= 1000
            and 8 <= args.eval_games <= 128 and 30 <= args.max_seconds <= 7200
            and 1 <= args.bc_epochs <= 200):
        parser.error("Experiment budget out of range")
    if not args.worker:
        try:
            worker_env = os.environ.copy()
            worker_env["PYTHONHASHSEED"] = str(args.seed % (2**32))
            result = subprocess.run([sys.executable, *sys.argv, "--worker"],
                                    timeout=args.max_seconds + 15, env=worker_env)
            return result.returncode
        except subprocess.TimeoutExpired:
            print("Training worker terminated at wall-time budget", file=sys.stderr)
            return 124
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    # A finite outer process watchdog is provided by the launcher, in addition
    # to these per-game and stage checks.
    started = time.monotonic()
    deadline = started + args.max_seconds
    import torch
    from torch import nn
    from core.bg_policy import LabPolicy, safety_action
    torch.set_num_threads(2)
    torch.manual_seed(args.seed)
    rng = random.Random(args.seed)
    arena = Arena(load_engine(args.engine), seconds=min(120, args.max_seconds))

    Policy = LabPolicy

    def batch(rows):
        length = max(len(s["x"]) for s in rows)
        x = torch.zeros(len(rows), length, FEATURE_DIM)
        mask = torch.zeros(len(rows), length, dtype=torch.bool)
        for i, sample in enumerate(rows):
            count = len(sample["x"])
            x[i, :count] = torch.tensor(sample["x"], dtype=torch.float32)
            mask[i, :count] = True
        return x, mask

    def policy_fn(model, *, stochastic=False, records=None):
        def choose(rows, teacher):
            with torch.no_grad():
                x = torch.tensor([rows], dtype=torch.float32)
                dist, value = model(x, torch.ones(1, len(rows), dtype=torch.bool))
                action = dist.sample() if stochastic else dist.logits.argmax(-1)
                if not stochastic:
                    action = torch.tensor(safety_action(int(action.item()), teacher, rows))
                if records is not None:
                    records.append((float(dist.log_prob(action)), float(value)))
                return int(action.item())
        return choose

    def check_time():
        if time.monotonic() > deadline:
            raise TimeoutError("Experiment stage budget exceeded")

    metrics = dict(profile=PROFILE, engine_revision=arena.e["revision"], seed=args.seed,
                   python_hash_seed=os.environ.get("PYTHONHASHSEED"),
                   device="cpu", torch_version=torch.__version__, config=vars(args),
                   limitations=["neutral training heroes; exported current heroes/trinkets/anomalies are not yet activated",
                                "fixed first-option helper for targeting/discover",
                                "unscripted current cards use vanilla stat/keyword fallback",
                                "all simulator pool tribes enabled; live lobby race rotation is not sampled",
                                "10-bit card identity hash; complete effect text is not encoded"],
                   data_coverage=arena.e.get("coverage"),
                   games=[], evaluations={})
    source_root = Path(__file__).resolve().parents[1]
    metrics["source_sha256"] = {}
    for relative in ("core/bg_selfplay.py", "core/bg_policy.py", "core/bg_expert_data.py", "tools/train_bg_selfplay.py"):
        content = (source_root / relative).read_bytes()
        snapshot = output / "source" / relative
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        snapshot.write_bytes(content)
        metrics["source_sha256"][relative] = hashlib.sha256(content).hexdigest()
    tracefile = gzip.open(output / "trajectories.jsonl.gz", "wt", encoding="utf-8")

    def run(policies, seed, phase, collect=False):
        check_time()
        result = arena.run(policies, seed, collect=collect)
        summary = {k:v for k,v in result.items() if k != "trajectories"}
        summary["phase"] = phase
        metrics["games"].append(summary)
        if not result["finished"] or result["action_limit_hits"]:
            raise RuntimeError(f"Unusable game seed={seed}: truncated or action-budget exhausted")
        tracefile.write(json.dumps(dict(phase=phase, **result)) + "\n")
        tracefile.flush()
        return result

    model = Policy()
    metrics["parameters"] = sum(p.numel() for p in model.parameters())
    optimizer = torch.optim.Adam(model.parameters(), lr=0.002)
    samples = []
    try:
        if args.expert_battles:
            from core.bg_expert_data import load_expert_samples
            expert_info=[]
            for expert_path in args.expert_battles:
                expert_samples,info=load_expert_samples(expert_path)
                samples.extend(expert_samples);expert_info.append(info)
            metrics['expert_supervision'] = expert_info
        for i in range(args.bc_games):
            r = run([teacher_policy] * 8, args.seed + i, "imitation", True)
            samples += [s for t in r["trajectories"] for s in t]
        initial = {k:v.clone() for k,v in model.state_dict().items()}
        losses = []
        for epoch in range(args.bc_epochs):
            check_time()
            rng.shuffle(samples)
            total = 0
            for start in range(0, len(samples), 128):
                rows = samples[start:start+128]
                dist, _ = model(*batch(rows))
                loss = -dist.log_prob(torch.tensor([s["teacher"] for s in rows])).mean()
                optimizer.zero_grad()
                loss.backward()
                nn.utils.clip_grad_norm_(model.parameters(), 1.)
                optimizer.step()
                total += float(loss.detach()) * len(rows)
            losses.append(total / len(samples))
        metrics["imitation"] = dict(samples=len(samples), loss=losses,
                                    teacher_kinds=dict(Counter(s.get("kind", "expert") for s in samples)))
        bc_model = copy.deepcopy(model).eval()
        torch.save(dict(schema=1, profile=PROFILE, engine_revision=arena.e["revision"],
                        feature_dim=FEATURE_DIM, state_dict=model.state_dict()), output / "imitation.pt")
        print(json.dumps(dict(stage="imitation", games=args.bc_games, samples=len(samples),
                              loss_first=losses[0], loss_last=losses[-1])), flush=True)

        def evaluate(name, learner):
            places = []
            top4 = []
            action_counts = Counter()
            disagreements = avoidable_ends = decisions = 0
            for i in range(args.eval_games):
                seat = i % 8
                policies = [teacher_policy] * 8
                policies[seat] = learner
                # Fixed seed/seat schedule identical across policies, disjoint from training.
                r = run(policies, 1000000 + args.seed + i, "eval_" + name, True)
                for step in r["trajectories"][seat]:
                    decisions += 1
                    action_counts[step["kind"]] += 1
                    disagreements += step["action"] != step["teacher"]
                    avoidable_ends += (step["kind"] == "END" and step.get("teacher_kind") == "PLAY")
                places.append(r["placements"][seat])
                top4.append(top4_credit(r["placements"], seat))
            metrics["evaluations"][name] = dict(games=len(places), mean_placement=sum(places)/len(places),
                                               placements=places,
                                               top4_rate=sum(top4)/len(places),
                                               actions=dict(action_counts), decisions=decisions,
                                               teacher_disagreements=disagreements,
                                               ends_with_playable_minion=avoidable_ends)
            print(json.dumps(dict(stage="eval", policy=name, **metrics["evaluations"][name])), flush=True)

        untrained = Policy()
        untrained.load_state_dict(initial)
        evaluate("heuristic", teacher_policy)
        evaluate("untrained", policy_fn(untrained))
        evaluate("imitation", policy_fn(bc_model))
        optimizer = torch.optim.Adam(model.parameters(), lr=0.00015)
        frozen = copy.deepcopy(bc_model)
        for i in range(args.rl_games):
            records = [[] for _ in range(8)]
            train_seats = {(i+j) % 8 for j in range(4)}
            policies = [policy_fn(model, stochastic=True, records=records[s]) if s in train_seats
                        else (teacher_policy if (s+i) % 2 else policy_fn(frozen)) for s in range(8)]
            r = run(policies, args.seed + 10000 + i, "ppo", True)
            rows = []
            for seat in train_seats:
                trajectory = r["trajectories"][seat]
                if len(trajectory) != len(records[seat]):
                    raise RuntimeError("Rollout/log-prob alignment mismatch")
                utility = ((2 * top4_credit(r["placements"], seat) - 1) if args.objective == "top4"
                           else (4.5 - r["placements"][seat]) / 3.5)
                last_turn = trajectory[-1]["turn"]
                for sample, (logp, value) in zip(trajectory, records[seat]):
                    target = utility * .99 ** (last_turn - sample["turn"])
                    rows.append(dict(**sample, old_logp=logp, advantage=target-value, target=target))
            for epoch in range(2):
                check_time()
                rng.shuffle(rows)
                for start in range(0, len(rows), 128):
                    part = rows[start:start+128]
                    dist, value = model(*batch(part))
                    logp = dist.log_prob(torch.tensor([s["action"] for s in part]))
                    ratio = (logp - torch.tensor([s["old_logp"] for s in part])).exp()
                    adv = torch.tensor([s["advantage"] for s in part])
                    clipped = ratio.clamp(.8, 1.2) * adv
                    actor_loss = -torch.minimum(ratio * adv, clipped).mean()
                    value_loss = (value - torch.tensor([s["target"] for s in part])).square().mean()
                    loss = actor_loss + .5 * value_loss - .005 * dist.entropy().mean()
                    if not torch.isfinite(loss):
                        raise RuntimeError("Non-finite training loss")
                    optimizer.zero_grad()
                    loss.backward()
                    nn.utils.clip_grad_norm_(model.parameters(), 1.)
                    optimizer.step()
            if (i+1) % 8 == 0:
                frozen = copy.deepcopy(model).eval()
                print(json.dumps(dict(stage="ppo", completed_games=i+1, elapsed=round(time.monotonic()-started,1))), flush=True)
        evaluate("ppo", policy_fn(model))
        torch.save(dict(schema=1, profile=PROFILE, engine_revision=arena.e["revision"],
                        feature_dim=FEATURE_DIM, state_dict=model.state_dict()), output / "ppo.pt")
        baseline = metrics["evaluations"]["heuristic"]
        final = metrics["evaluations"]["ppo"]
        coverage=arena.e.get("coverage") or {}
        metrics["admission"] = dict(deployable=False,
            reason="Current-data candidate is not promoted: effect-script gaps and insufficient independent evaluation",
            patch=arena.e.get("patch"),effect_coverage=coverage,
            mean_placement_gain=baseline["mean_placement"]-final["mean_placement"],
            top4_gain=final["top4_rate"]-baseline["top4_rate"],
            minimum_evaluation_games=64, sufficient_sample=args.eval_games >= 64)
        metrics["status"] = "complete"
        metrics["elapsed_seconds"] = round(time.monotonic()-started, 2)
        save_json(output / "report.json", metrics)
        print(json.dumps(dict(status="complete", games=len(metrics["games"]),
                              elapsed_seconds=metrics["elapsed_seconds"])), flush=True)
    except Exception as exc:
        metrics["status"] = "failed"
        metrics["error"] = f"{type(exc).__name__}: {exc}"
        save_json(output / "report.json", metrics)
        raise
    finally:
        tracefile.close()


if __name__ == "__main__":
    sys.exit(main() or 0)
