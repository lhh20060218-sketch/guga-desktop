"""Deterministic confirmation for stopping a running task.

Ollaya shadow tests showed that stop intent should not directly cancel work.
This gate keeps the decision local and inexpensive: an explicit stop request
enters a short confirmation state, while unrelated input cannot cancel a task.
"""
from __future__ import annotations

import re
import time
import unicodedata


def _normalize(text: str) -> str:
    value = unicodedata.normalize("NFKC", str(text or "")).strip()
    value = re.sub(r"[\s，。！？!?,、；;：:]+", "", value)
    return value


class TaskControlGate:
    YES = {
        "对", "是", "是的", "确定", "确认", "好的", "好", "停", "停止",
        "停吧", "停止吧", "就这样", "可以停止", "确定停止", "对停止",
    }
    NO = {
        "不", "不要", "不用", "别停", "不要停", "不用停", "继续", "继续吧",
        "取消停止", "取消", "算了", "先不", "先不要",
    }
    _STOP_PATTERNS = (
        re.compile(r"^(?:请|帮我|麻烦)?(?:先)?停止(?:当前|现在|目前|正在执行)?(?:的)?任务$"),
        re.compile(r"^(?:请|帮我|麻烦)?(?:先)?取消(?:当前|现在|目前|正在执行)?(?:的)?任务$"),
        re.compile(r"^(?:停止|取消)(?:当前|现在|目前)?执行$"),
        re.compile(r"^(?:别执行了|别做了|停一下|先停一下|停下|停下来)$"),
        re.compile(r"^停下(?:当前|现在|目前|正在执行)?(?:的)?任务$"),
        re.compile(r"^(?:暂停|暂时停止)(?:当前|现在|目前|正在执行)(?:的)?任务$"),
    )

    def __init__(self, expiry_seconds: float = 30.0):
        self.expiry_seconds = max(5.0, float(expiry_seconds))
        self._pending = False
        self._created = 0.0

    @property
    def pending(self) -> bool:
        return self._pending

    def reset(self) -> None:
        self._pending = False
        self._created = 0.0

    def _expired(self, now: float) -> bool:
        return self._pending and now - self._created > self.expiry_seconds

    def _is_stop_request(self, text: str) -> bool:
        value = _normalize(text)
        if not value:
            return False
        if any(term in value for term in ("唱歌", "音乐", "对话", "通话", "语音")):
            return False
        return any(pattern.fullmatch(value) for pattern in self._STOP_PATTERNS)

    def observe(self, text: str, busy: bool, now: float | None = None) -> dict:
        """Return one of none/ask_stop/cancel/continue/pending."""
        now = time.monotonic() if now is None else float(now)
        if not busy:
            self.reset()
            return {"action": "none", "pending": False}
        if self._expired(now):
            self.reset()

        value = _normalize(text)
        if self._pending:
            if value in self.YES:
                self.reset()
                return {"action": "cancel", "pending": False}
            if value in self.NO:
                self.reset()
                return {"action": "continue", "pending": False}
            if "继续" in value and value.startswith(("不用", "不要", "别", "先不")):
                self.reset()
                return {"action": "continue", "pending": False}
            if self._is_stop_request(text):
                self._created = now
                return {"action": "ask_stop", "pending": True}
            return {"action": "pending", "pending": True}

        if self._is_stop_request(text):
            self._pending = True
            self._created = now
            return {"action": "ask_stop", "pending": True}
        return {"action": "none", "pending": False}
