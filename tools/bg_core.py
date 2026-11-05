"""Independent game-core probe / one decision; does not start the pet or send input."""
import argparse
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('probe', 'plan'))
    parser.add_argument('--memory', action='store_true', help='Probe actual HearthMirror read access')
    parser.add_argument('--strategy', choices=('fast', 'model', 'deepbattler'), default=None)
    parser.add_argument('--deepbattler-endpoint', help='Use a local or HTTPS /generate_actions service')
    parser.add_argument('--output', type=Path, help='Save a sanitized JSON receipt')
    args = parser.parse_args()
    if args.command == 'probe':
        from core.bg_diagnostics import probe
        result = probe(args.memory)
    else:
        from core.bg_live import LiveReader, observed_phase
        from core.bg_pipeline import StrategyEngine
        from core.bg_agent import load_config
        from core.log_reader import find_log_path
        path = find_log_path(current_session=True)
        if not path:
            raise RuntimeError('没有找到 Power.log；未调用模型')
        reader = LiveReader(path, latest_game=True)
        reader.poll()
        if observed_phase(reader.parser) != 'recruit':
            raise RuntimeError('当前日志未确认招募阶段；未调用模型')
        config = load_config()
        if args.strategy:
            config['strategy_mode'] = args.strategy
        if args.deepbattler_endpoint:
            config.update(strategy_mode='deepbattler',bg_deepbattler_transport='endpoint',
                          bg_deepbattler_endpoint=args.deepbattler_endpoint)
        started = time.monotonic()
        plan = StrategyEngine(config).plan(reader.state())
        elapsed = round((time.monotonic()-started)*1000, 2)
        reader.poll()
        from core.bg_action_contract import compile_option
        request = (dict(executed=False,wait=True) if plan.get('wait') else
                   compile_option(plan['state'], reader.state(), plan['action'], observed_phase(reader.parser)))
        result = dict(input_sent=False, decision_ms=elapsed, operation_request=request,
                      **{k:v for k,v in plan.items() if k not in ('state','metadata','actions')})
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text+'\n', encoding='utf-8')
    print(text)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        message = str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__
        print(json.dumps(dict(ok=False, error=message, input_sent=False), ensure_ascii=False))
        sys.exit(2)
