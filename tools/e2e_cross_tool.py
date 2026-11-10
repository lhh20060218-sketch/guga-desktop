"""跨工具链真端到端探针：WorkBuddy 提示词 → JoyCode 网站 → 浏览器核验。

用法：
  python tools/e2e_cross_tool.py "做一个介绍桌面 AI 助手咕嘎的单页网站，简洁科技风，中文文案"
  python tools/e2e_cross_tool.py --timeout 1200 "第二条不同需求"
"""
import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from core import cross_tool_pipeline  # noqa: E402


def brief(value):
    keep = ('ok', 'stage', 'error', 'message', 'task_id', 'folder', 'answer_chars',
            'page_chars', 'prompt_chars', 'timings', 'total_ms', 'decision_basis',
            'answer_path', 'receipt')
    return {key: value.get(key) for key in keep if key in value}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('requirement')
    parser.add_argument('--timeout', type=int, default=900)
    parser.add_argument('--why', default='需要外部提示词工具和代码生成工具接力，产出高质量网页')
    args = parser.parse_args()
    result = cross_tool_pipeline.run(args.requirement, timeout=args.timeout, why=args.why)
    print(json.dumps(brief(result), ensure_ascii=False, indent=2, default=str))
    verify = result.get('verify') or {}
    if verify:
        print('verify:', json.dumps({key: verify.get(key) for key in
              ('ok', 'ready_state', 'title', 'dom_chars', 'sections', 'links',
               'unique_colors', 'gray_stddev', 'render_ms', 'entry', 'screenshot', 'error')},
              ensure_ascii=False, default=str))
    receipt = result.get('receipt') or {}
    print('receipt status:', receipt.get('status'), '| self_check:', str(receipt.get('self_check') or '')[:200])
    print('RESULT:', 'PASS' if result.get('ok') else 'FAIL')


if __name__ == '__main__':
    main()
