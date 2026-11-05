"""Run bounded offline eight-player battles, optionally with a local checkpoint."""
import argparse
import os
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.bg_selfplay import Arena, load_engine, save_json, teacher_policy


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", required=True)
    parser.add_argument("--checkpoint")
    parser.add_argument("--games", type=int, default=1)
    parser.add_argument('--max-seconds', type=int, default=120, help='Finite whole-run budget, 30..600 seconds')
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", required=True)
    parser.add_argument('--cloud-calls',type=int,default=0,help='Explicit DeepSeek request budget, 0..128; consumes existing plan quota')
    parser.add_argument('--cloud-ledger', help='Shared phase ledger; maximum 128 attempts, persistent failure stop')
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not 1 <= args.games <= 100:
        parser.error("games must be between 1 and 100")
    if not 30 <= args.max_seconds <= 600:
        parser.error('max-seconds must be between 30 and 600')
    if not 0 <= args.cloud_calls <= 128 or (args.cloud_calls and args.checkpoint):
        parser.error('cloud-calls must be 0..128 and cannot combine with checkpoint')
    if args.cloud_calls and not args.cloud_ledger:
        parser.error('Cloud collection requires --cloud-ledger shared across this phase')
    if not args.worker:
        try:
            worker_env = os.environ.copy()
            worker_env["PYTHONHASHSEED"] = str(args.seed % (2**32))
            return subprocess.run([sys.executable, *sys.argv, "--worker"],
                                  timeout=args.max_seconds+5, env=worker_env).returncode
        except subprocess.TimeoutExpired:
            print("Offline battle worker terminated at wall-time budget", file=sys.stderr)
            return 124
    output = Path(args.output)
    if output.exists():
        raise FileExistsError("Choose a new output file; existing battles are not overwritten")
    import time
    deadline = time.monotonic()+args.max_seconds
    arena = Arena(load_engine(args.engine), seconds=args.max_seconds)
    policy = teacher_policy
    if args.checkpoint:
        import torch
        from core.bg_policy import LabPolicy
        torch.set_num_threads(2)
        policy = LabPolicy.load(args.checkpoint).choose
    results = []
    cloud = None
    if args.cloud_calls:
        from core.bg_agent import load_config
        from core.bg_cloud_policy import CloudBudget, DeepSeekSeat
        cloud = CloudBudget(load_config(),calls=args.cloud_calls,seconds=240,
                            ledger=args.cloud_ledger)
    for i in range(args.games):
        remaining = deadline-time.monotonic()
        if remaining <= 0:
            raise TimeoutError('Offline battle whole-run budget reached')
        arena.seconds = remaining
        policies = [DeepSeekSeat(cloud,seat) for seat in range(8)] if cloud else [policy]*8
        r = arena.run(policies, args.seed+i, collect=True)
        results.append(r)
        save_json(output, dict(checkpoint=args.checkpoint, games=results,cloud=cloud.summary() if cloud else None))
        print(f"seed={r['seed']} finished={r['finished']} turns={r['combat_phases']} "
              f"placements={r['placements']} action_limit_hits={r['action_limit_hits']}", flush=True)
    return 0 if all(r["finished"] and not r["action_limit_hits"] for r in results) else 2


if __name__ == "__main__":
    sys.exit(main())
