"""Decision CLI. Offline by default; --model explicitly uses configured API quota."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.bg_agent import DecisionEngine, ROOT, SnapshotError, load_config, log_diagnostic


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", nargs="?", help="JSON observation (default: synthetic demo)")
    parser.add_argument("--model", action="store_true", help="Call existing configured model")
    parser.add_argument("--log-check", action="store_true", help="Diagnose legacy log data completeness")
    parser.add_argument("--ui", action="store_true", help="Open the standalone decision panel")
    parser.add_argument("--tag-observation", action="store_true", help="Normalize an explicit entity-tag snapshot")
    args = parser.parse_args()
    if args.ui:
        from launcher import _prepare_qt
        _prepare_qt()
        from PyQt5.QtWidgets import QApplication
        from ui.bg_agent_panel import BattlegroundAgentPanel
        app = QApplication(sys.argv[:1])
        panel = BattlegroundAgentPanel()
        panel.show()
        return app.exec_()
    if args.log_check:
        print(json.dumps(log_diagnostic(), ensure_ascii=False, indent=2))
        return 0
    path = Path(args.snapshot) if args.snapshot else ROOT / "data/bg_agent/demo.json"
    try:
        if path.stat().st_size > 100000:
            raise SnapshotError("文件超过 100 KB")
        snapshot = json.loads(path.read_text(encoding="utf-8-sig"))
        if args.tag_observation:
            from core.bg_observation import normalize_tag_observation
            snapshot = normalize_tag_observation(snapshot)
        result = DecisionEngine(load_config() if args.model else {}).decide(snapshot, args.model)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2 if result["status"] == "blocked" else 0
    except (OSError, ValueError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)[:200]}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
