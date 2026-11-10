# -*- coding: utf-8 -*-
"""Patch workbuddy_bridge.py composer finder: expand UIA types + snapshot fallback."""
from pathlib import Path

TARGET = Path(__file__).resolve().parents[1] / 'core' / 'workbuddy_bridge.py'

src = TARGET.read_text(encoding='utf-8')

marker_start = 'def _uia_composer_at_point(backend, hwnd):'
marker_end = '\ndef _uia_focus('
s = src.index(marker_start)
e = src.index(marker_end, s)

new_func = '''#: Chromium contenteditable 在 UIA 树里可能暴露成 Edit/Document/Pane/Group/Text 等多种类型；
#: 只要面积达标、有 TextPattern 或 keyboard_focusable，都有可能是 composer。
_UIA_COMPOSER_TYPES = frozenset(('Edit', 'Document', 'Pane', 'Group', 'Text', 'Custom'))


def _is_composer_candidate(item, left, top, right, bottom):
    """从 snapshot 元素 dict 判断是否像 composer：位置（右半边）+ 面积 + 可编辑特征。"""
    rect = item.get('rect') or {}
    rl = float(rect.get('left', 0))
    rt = float(rect.get('top', 0))
    rr = float(rect.get('right', 0))
    rb = float(rect.get('bottom', 0))
    w, h = rr - rl, rb - rt
    if w < 240 or h < 28:
        return False
    ww = right - left
    if ww > 0 and (rl - left) / ww < 0.30:
        return False
    if (not item.get('text_pattern')
            and not item.get('keyboard_focusable')
            and 'value' not in item
            and 'SetValuePattern' not in (item.get('patterns') or [])):
        return False
    return True


def _uia_composer_at_point(backend, hwnd):
    """网格采样 + 整树 snapshot 两路找 composer。

    第一路：FromPoint 网格采样，接受 Chromium 常见的多种控件类型。
    第二路（fallback）：FromPoint 全 miss 时用整树 snapshot，扫所有元素里面积达标 +
    可编辑特征的最大那个。
    """
    Point = _uia_point_class()
    left, top, right, bottom = _rect(hwnd)
    width, height = right - left, bottom - top
    if width <= 0 or height <= 0:
        return None
    AE = backend.AutomationElement
    walker = backend.walker

    def _from_element(element):
        try:
            kind_full = str(element.Current.ControlType.ProgrammaticName)
            kind = kind_full.replace('ControlType.', '')
            box = element.Current.BoundingRectangle
            w, h = float(box.Width), float(box.Height)
        except Exception:
            return None
        if kind in _UIA_COMPOSER_TYPES and w >= 240 and h >= 28:
            item, _ = backend._entry(element, hwnd)
            if item:
                backend.elements[item['ref']] = (element, time.monotonic(), int(hwnd))
                return dict(ref=item['ref'], rect=item.get('rect') or {}, element=item)
        return None

    # ---- 第一路：FromPoint 网格采样，接受扩展类型 ----
    for yi in range(13, -1, -1):
        y = int(top + height * (0.30 + 0.05 * yi))
        for xf in (0.58, 0.72, 0.86):
            x = int(left + width * xf)
            try:
                element = AE.FromPoint(Point(x, y))
            except Exception:
                continue
            for _ in range(6):
                if element is None:
                    break
                hit = _from_element(element)
                if hit:
                    return hit
                try:
                    element = walker.GetParent(element)
                except Exception:
                    break

    # ---- 第二路：整树 snapshot fallback ----
    try:
        snap = backend.snapshot(int(hwnd), limit=400, time_budget=3.0)
    except Exception:
        return None
    if not snap or not snap.get('elements'):
        return None
    candidates = []
    for item in snap['elements']:
        if not _is_composer_candidate(item, left, top, right, bottom):
            continue
        if item.get('offscreen'):
            continue
        rect = item.get('rect') or {}
        area = (float(rect.get('right', 0)) - float(rect.get('left', 0))) * \
               (float(rect.get('bottom', 0)) - float(rect.get('top', 0)))
        candidates.append((area, item))
    if not candidates:
        return None
    candidates.sort(key=lambda c: c[0], reverse=True)
    _, best = candidates[0]
    ref = best.get('ref')
    if ref and ref in backend.elements:
        return dict(ref=ref, rect=best.get('rect') or {}, element=best)
    try:
        again = backend._find(int(hwnd), ref=ref) if ref else None
    except Exception:
        again = None
    if again:
        return dict(ref=ref, rect=again.get('rect') or {}, element=again)
    return None
'''

new_src = src[:s] + new_func + src[e:]
TARGET.write_text(new_src, encoding='utf-8')
print('OK: replaced from offset', s, 'to', e)
print('new length:', len(new_src), 'old length:', len(src))
