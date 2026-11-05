"""Finite read-only Power.log capture. Does not control Hearthstone or call APIs."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.bg_log_capture import EventParser


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--log", help="Explicit Power.log; otherwise reuse pet's discovery, read-only")
    ap.add_argument("--output", required=True, help="New local output directory")
    ap.add_argument("--seconds", type=int, default=180)
    ap.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = ap.parse_args()
    if not 0 <= args.seconds <= 1800:
        ap.error("seconds must be between 0 and 1800")
    if not args.worker:
        try:
            return subprocess.run([sys.executable, *sys.argv, "--worker"],
                                  timeout=args.seconds+30).returncode
        except subprocess.TimeoutExpired:
            print("Read-only observer terminated at finite wall-time budget", file=sys.stderr)
            return 124
    if args.log:
        path = Path(args.log).resolve()
    else:
        from core.log_reader import find_log_path
        discovered = find_log_path()
        if not discovered:
            raise FileNotFoundError("No Power.log found; logging settings are left unchanged")
        path = Path(discovered)
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    parser = EventParser()
    counts = Counter()
    start, offset, carry = time.monotonic(), 0, b""
    stopped = "duration_reached"
    report = dict(schema=1, started_at=utc_now(), log_session=path.parent.name,
                  observation_only=True, contains_raw_lines=False,
                  identity_confirmed=False, training_ready=False, seconds=args.seconds,
                  limitations=["No model requests or game input",
                               "No inferred local identity/effective cost/action labels",
                               "Processed PowerTaskList events only; no duplicate GameState power stream",
                               "Missing tags remain unknown; observed options may be incomplete"],
                  event_counts={}, source_initial_bytes=path.stat().st_size)
    with (output / "events.jsonl").open("x", encoding="utf-8") as events:
        while True:
            size = path.stat().st_size
            if size < offset:
                stopped = "source_truncated"
                break
            with path.open("rb") as source:
                source.seek(offset)
                data = source.read(min(size-offset, 4*1024*1024))
            data_start = offset-len(carry)
            offset += len(data)
            lines = (carry+data).splitlines(keepends=True)
            carry = b""
            if lines and not lines[-1].endswith(b"\n"):
                carry = lines.pop()
            position = data_start
            for line in lines:
                for event in parser.feed(line.decode("utf-8", "replace")):
                    counts[event["type"]] += 1
                    event.update(source_byte_offset=position, observed_at=utc_now())
                    events.write(json.dumps(event, ensure_ascii=True)+"\n")
                position += len(line)
            events.flush()
            snapshot = parser.snapshot()
            (output / "latest.json").write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
            report.update(event_counts=dict(counts), entity_count=len(parser.entities),
                          source_bytes_read=offset, source_age_seconds=round(time.time()-path.stat().st_mtime, 1),
                          updated_at=utc_now(), game_index=parser.game_index)
            (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
            if len(parser.entities) > 20000:
                stopped = "entity_budget_exceeded"
                break
            # Read existing large files in bounded chunks before waiting. A
            # zero-second replay still has a finite 20-second bootstrap budget.
            if offset < size and time.monotonic()-start < max(20, args.seconds):
                continue
            if offset < size:
                stopped = "source_backlog_budget_exceeded"
                break
            if time.monotonic()-start >= args.seconds:
                break
            time.sleep(.5)
    report.update(stopped=stopped, elapsed_seconds=round(time.monotonic()-start, 2), finished_at=utc_now())
    (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k:v for k,v in report.items() if k not in ("limitations",)}), flush=True)
    return 0 if stopped == "duration_reached" else 2


if __name__ == "__main__":
    sys.exit(main())
