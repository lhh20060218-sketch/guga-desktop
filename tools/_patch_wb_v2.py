# -*- coding: utf-8 -*-
"""Patch workbuddy_bridge.py composer finder v2: exclude whole-window controls."""
from pathlib import Path

TARGET = Path(__file__).resolve().parents[1] / 'core' / 'workbuddy_bridge.py'
src = TARGET.read_text(encoding='utf-8')

# Patch 1: _is_composer_candidate - add "not too large" check
old1 = '''def _is_composer_candidate(item, left, top, right, bottom):
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
    return True'''

new1 = '''def _is_composer_candidate(item, left, top, right, bottom):
    """从 snapshot 元素 dict 判断是否像 composer：位置 + 面积 + 可编辑特征。

    **关键约束**：面积不能超过窗口的 60%——Chromium canvas 自绘会暴露整窗大小的
    Document/Pane/Custom 控件，它们不是 composer。
    """
    rect = item.get('rect') or {}
    rl = float(rect.get('left', 0))
    rt = float(rect.get('top', 0))
    rr = float(rect.get('right', 0))
    rb = float(rect.get('bottom', 0))
    w, h = rr - rl, rb - rt
    if w < 240 or h < 28:
        return False
    ww = right - left
    hh = bottom - top
    if ww > 0 and (rl - left) / ww < 0.30:
        return False
    if ww > 0 and w / ww > 0.92:       # 宽度占 92%+ → 整窗，排除
        return False
    if hh > 0 and h / hh > 0.80:       # 高度占 80%+ → 整窗，排除
        return False
    if (not item.get('text_pattern')
            and not item.get('keyboard_focusable')
            and 'value' not in item
            and 'SetValuePattern' not in (item.get('patterns') or [])):
        return False
    return True'''

assert old1 in src, 'old1 not found'
src = src.replace(old1, new1)

# Patch 2: In _uia_composer_at_point, FromPoint first path also needs size guard
# Replace the kind check with kind + size check that excludes whole-window controls
old2 = '''    def _from_element(element):
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
        return None'''

new2 = '''    def _from_element(element):
        try:
            kind_full = str(element.Current.ControlType.ProgrammaticName)
            kind = kind_full.replace('ControlType.', '')
            box = element.Current.BoundingRectangle
            w, h = float(box.Width), float(box.Height)
        except Exception:
            return None
        if kind not in _UIA_COMPOSER_TYPES:
            return None
        if w < 240 or h < 28:
            return None
        # 排除整窗大小控件（Chromium canvas 自绘的根节点）
        win_w = right - left
        win_h = bottom - top
        if win_w > 0 and w / win_w > 0.92:
            return None
        if win_h > 0 and h / win_h > 0.80:
            return None
        item, _ = backend._entry(element, hwnd)
        if item:
            backend.elements[item['ref']] = (element, time.monotonic(), int(hwnd))
            return dict(ref=item['ref'], rect=item.get('rect') or {}, element=item)
        return None'''

assert old2 in src, 'old2 not found'
src = src.replace(old2, new2)

TARGET.write_text(src, encoding='utf-8')
print('OK: patches applied')
print('file size:', len(src))
