"""Offline-only Ollaya routing shadow test.

This script sends synthetic transcripts to the local Ollaya decision model and
compares its top route with a hand-labelled expected route. It never opens a
microphone, calls Qwen/DeepSeek, or executes the matched fast command.
"""
from __future__ import annotations

import json
import argparse
import statistics
import sys
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.fast_commands import match as fast_match


ENDPOINT = "http://127.0.0.1:11435/api/decide"
MODEL = "laya:multilingual"
QUESTIONS = {
    "route": {
        "type": "choice",
        "instructions": "Which route should handle `request`?",
        "criteria": {
            "fast_action": "One explicit built-in immediate action: open browser, app or known website; search; sing; gesture.",
            "chat": "Conversation or explanation with no computer action.",
            "tool_task": "One concrete website or desktop-app task beyond built-in fast actions.",
            "long_task": "Multi-step work needing planning or multiple tools, files or research.",
            "control": "Stop, cancel, pause, resume, or end a current task or call.",
            "clarify": "Ambiguous, incomplete or contradictory request needing a question.",
        },
    },
    "wants_stop": {
        "type": "noul",
        "instructions": "`request` 是否要求停止、取消、暂停或结束当前任务？",
    },
}

# Expected labels are routing test labels, not claims that an action should be
# executed without normal local policy and confirmation.
SAMPLES = [
    ("打开默认浏览器", "fast_action"),
    ("打开百度", "fast_action"),
    ("打开记事本", "fast_action"),
    ("帮我唱晴天", "fast_action"),
    ("戴上墨镜", "fast_action"),
    ("搜索一下今天的上海天气", "fast_action"),
    ("你今天心情怎么样", "chat"),
    ("为什么天空是蓝色的", "chat"),
    ("陪我聊一会儿", "chat"),
    ("刚才那句话是什么意思", "chat"),
    ("用简单的话解释一下什么是智能体", "chat"),
    ("给微信小军发一段简短的自我介绍并发送", "tool_task"),
    ("在记事本里输入明天的购物清单并保存", "tool_task"),
    ("打开哔哩哔哩网站并在搜索框输入炉石传说", "tool_task"),
    ("读取当前浏览器页面并告诉我标题", "tool_task"),
    ("把微信切到文件传输助手，准备一条消息先不要发送", "tool_task"),
    ("打开记事本并检查它现在是否在前台", "tool_task"),
    ("查一下最新酒馆战棋阵容，整理成文件，再发到微信文件传输助手", "long_task"),
    ("把桌宠项目所有语音测试跑一遍，找出失败项并修复", "long_task"),
    ("调研桌面宠物开源项目并写一份对比报告", "long_task"),
    ("把下载目录按文件类型整理，重复文件列出来", "long_task"),
    ("看完这个网页，提取要点并生成一份摘要文件", "long_task"),
    ("停下目前的任务", "control"),
    ("别做了，先停一下", "control"),
    ("暂停正在执行的整理任务", "control"),
    ("结束语音通话", "control"),
    ("帮我弄一下那个东西", "clarify"),
    ("把它发过去", "clarify"),
    ("打开那个软件", "clarify"),
    ("刚才那个再查一下", "clarify"),
]

# Direct actions need stronger evidence than simply entering the agent loop.
THRESHOLDS = {
    "fast_action": .80,
    "control": .70,
    "tool_task": .60,
    "long_task": .60,
    "chat": .60,
    "clarify": .60,
}


def decide(request_text: str, model: str = MODEL) -> tuple[dict, float]:
    payload = json.dumps(
        {"model": model, "state": {"request": request_text}, "questions": QUESTIONS},
        ensure_ascii=False,
    ).encode("utf-8")
    req = urllib.request.Request(
        ENDPOINT, data=payload, headers={"Content-Type": "application/json"}
    )
    started = time.perf_counter()
    with urllib.request.urlopen(req, timeout=10) as response:
        result = json.load(response)
    return result, round((time.perf_counter() - started) * 1000, 2)


def current_local_route(text: str) -> str:
    parsed = fast_match(text)
    if not parsed.get("matched"):
        return "no_fast_match"
    return "control" if parsed.get("action") == "stop_call" else "fast_action"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=MODEL)
    args = parser.parse_args()
    rows = []
    failures = []
    for index, (text, expected) in enumerate(SAMPLES, 1):
        try:
            result, wall_ms = decide(text, args.model)
            route = result["answers"]["route"]
            stop = result["answers"]["wants_stop"]
            predicted = route["choice"]
            confidence = float(route["confidence"])
            threshold = THRESHOLDS[predicted]
            accepted = confidence >= threshold
            safe_decision = predicted if accepted else "clarify"
            stop_probability = float(stop["noul"])
            stop_decision = "yes" if stop_probability >= .8 else "no" if stop_probability <= .2 else "unsure"
            rows.append(dict(
                index=index,
                request=text,
                expected=expected,
                predicted=predicted,
                confidence=round(confidence, 4),
                probabilities={k: round(float(v), 4) for k, v in route["probabilities"].items()},
                threshold=threshold,
                accepted=accepted,
                safe_decision=safe_decision,
                wants_stop=round(stop_probability, 4),
                stop_decision=stop_decision,
                current_fast=current_local_route(text),
                wall_ms=wall_ms,
                model_latency_ms=round(float(result.get("total_duration", 0)) / 1_000_000, 2),
            ))
        except (urllib.error.URLError, TimeoutError, KeyError, ValueError) as exc:
            failures.append(dict(index=index, request=text, error=f"{type(exc).__name__}: {exc}"))

    successes = [row for row in rows if row["accepted"]]
    top1_correct = sum(row["predicted"] == row["expected"] for row in rows)
    safe_correct = sum(row["safe_decision"] == row["expected"] for row in rows)
    per_class = defaultdict(lambda: {"count": 0, "top1_correct": 0, "safe_correct": 0})
    for row in rows:
        stats = per_class[row["expected"]]
        stats["count"] += 1
        stats["top1_correct"] += row["predicted"] == row["expected"]
        stats["safe_correct"] += row["safe_decision"] == row["expected"]

    control_rows = [row for row in rows if row["expected"] == "control"]
    stop_tp = sum(row["stop_decision"] == "yes" and row["expected"] == "control" for row in rows)
    stop_fn = sum(row["stop_decision"] != "yes" and row["expected"] == "control" for row in rows)
    stop_fp = sum(row["stop_decision"] == "yes" and row["expected"] != "control" for row in rows)
    stop_tn = sum(row["stop_decision"] == "no" and row["expected"] != "control" for row in rows)
    safe_false_actions = [
        row for row in rows
        if row["safe_decision"] in ("fast_action", "tool_task", "long_task")
        and row["expected"] in ("chat", "control", "clarify")
    ]
    latencies = [row["wall_ms"] for row in rows]
    summary = dict(
        generated_at=datetime.now(timezone.utc).isoformat(),
        internet_used=False,
        qwen_used=False,
        deepseek_used=False,
        model=args.model,
        samples=len(SAMPLES),
        completed=len(rows),
        failures=failures,
        top1_accuracy=round(top1_correct / max(1, len(rows)), 4),
        accuracy_after_confidence_gate=round(safe_correct / max(1, len(rows)), 4),
        confidence_gate_acceptance=round(len(successes) / max(1, len(rows)), 4),
        control_exact=sum(row["predicted"] == "control" for row in control_rows),
        control_samples=len(control_rows),
        control_safe=sum(row["safe_decision"] == "control" for row in control_rows),
        stop_confusion=dict(tp=stop_tp, fn=stop_fn, fp=stop_fp, tn=stop_tn,
                            unsure=sum(row["stop_decision"] == "unsure" for row in rows)),
        stop_precision=round(stop_tp / max(1, stop_tp + stop_fp), 4),
        stop_recall=round(stop_tp / max(1, stop_tp + stop_fn), 4),
        stop_false_yes=[row["request"] for row in rows if row["stop_decision"] == "yes" and row["expected"] != "control"],
        stop_gate_correct=sum(
            row["stop_decision"] == ("yes" if row["expected"] == "control" else "no")
            for row in rows
        ),
        unsafe_safe_actions=len(safe_false_actions),
        unsafe_examples=safe_false_actions,
        per_class={key: value for key, value in sorted(per_class.items())},
        latency_ms=dict(
            p50=round(statistics.median(latencies), 2) if latencies else None,
            p95=round(sorted(latencies)[max(0, int(len(latencies) * .95) - 1)], 2) if latencies else None,
            max=round(max(latencies), 2) if latencies else None,
        ),
        rows=rows,
    )
    folder = ROOT / "runtime" / "ollaya-shadow"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"shadow-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    target.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    printable = {key: value for key, value in summary.items() if key not in ("rows", "unsafe_examples")}
    print(json.dumps(printable, ensure_ascii=False, indent=2))
    print(f"REPORT={target}")
    return 0 if not failures and len(rows) == len(SAMPLES) else 1


if __name__ == "__main__":
    raise SystemExit(main())
