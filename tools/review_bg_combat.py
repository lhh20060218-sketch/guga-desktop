"""Export a finite, read-only local HDT combat review. No model or game input."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.bg_combat_review import parse_hdt_records, render_review, load_card_metadata, snapshot_review


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--hdt-record", required=True)
    ap.add_argument("--output", required=True, help="A new output directory")
    ap.add_argument("--power-snapshot", help="Optional sanitized observe_bg_logs latest.json")
    ap.add_argument("--local-controller", type=int)
    ap.add_argument("--carddefs", help="Optional local HDT CardDefs.base.xml")
    args = ap.parse_args()
    if args.power_snapshot and args.local_controller is None:
        ap.error("--local-controller is required with --power-snapshot")
    path = Path(args.hdt_record)
    # Read a single finite snapshot even if the producer is still appending.
    with path.open("rb") as source:
        data = source.read(16 * 1024 * 1024 + 1)
    if len(data) > 16 * 1024 * 1024:
        ap.error("HDT text exceeds the 16 MiB review budget")
    report = parse_hdt_records(data.decode("utf-8-sig"))
    report["source_snapshot"] = dict(file=path.name, bytes=len(data), sha256=hashlib.sha256(data).hexdigest(),
                                     modified_at=datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
                                     captured_at=datetime.now(timezone.utc).isoformat())
    if args.power_snapshot:
        snapshot = json.loads(Path(args.power_snapshot).read_text(encoding="utf-8"))
        ids = {e.get("CARD_ID") for e in snapshot.get("entities", {}).values() if e.get("CARD_ID")}
        metadata = load_card_metadata(args.carddefs, ids) if args.carddefs else {}
        report["separate_power_snapshot"] = snapshot_review(snapshot, args.local_controller, metadata)
        report["separate_power_snapshot"]["source_file"] = Path(args.power_snapshot).name
        report["separate_power_snapshot"]["source_modified_at"] = datetime.fromtimestamp(
            Path(args.power_snapshot).stat().st_mtime, timezone.utc).isoformat()
        if args.carddefs:
            report["card_metadata_source"] = dict(file=Path(args.carddefs).name,
                modified_at=datetime.fromtimestamp(Path(args.carddefs).stat().st_mtime, timezone.utc).isoformat(),
                matches_client_build="unverified", dynamic_templates_not_resolved=True)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    (output / "combat-review.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "combat-review.md").write_text(render_review(report), encoding="utf-8")
    rounds = [r for g in report["groups"] for r in g["rounds"]]
    print(json.dumps(dict(groups=len(report["groups"]), rounds=len(rounds),
        with_estimates=sum(bool(r["estimates"]) for r in rounds),
        with_actuals=sum(bool(r["actuals"]) for r in rounds),
        duplicate_headers_merged=sum(r["duplicate_headers"] for r in rounds),
        power_log_join="unmatched", training_ready=False)))


if __name__ == "__main__":
    main()
