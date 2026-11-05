# -*- coding: utf-8 -*-
"""几何边界单测：治"窗口矩形漂移 → 颠倒裁剪区 → pyscreeze 崩整轮"。
覆盖 _sanitize（截图求交/正宽高）、_rect_ok（矩形可信判据）、_clip_zone（校验区裁剪）。
不碰鼠标，纯函数级。"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pyautogui
from guga_executor import _clip_zone, _sanitize, _rect_ok, _screen_bounds

SW, SH = pyautogui.size()
VX, VY, VW, VH = _screen_bounds()
print(f"主屏 {SW}x{SH} / 虚拟桌面 ({VX},{VY},{VW}x{VH})")


def check_zone(name, zone, rect):
    assert zone, f"{name}: 裁剪区为空"
    x, y, cw, ch = zone
    assert cw > 0 and ch > 0, f"{name}: 负宽高 {zone}"
    assert cw >= 40 and ch >= 20, f"{name}: 裁剪区过小 {zone}"
    rx, ry, rw, rh = rect
    assert rx <= x and x + cw <= rx + rw, f"{name}: x 越窗 {zone} vs {rect}"
    assert ry <= y and y + ch <= ry + rh, f"{name}: y 越窗 {zone} vs {rect}"
    print(f"  ✓ {name}: zone={zone}")


# ── 1. _clip_zone：正常 / 漂移 / 贴边 / 小窗 / 副屏负坐标 ──
r = (100, 100, 1200, 800)
check_zone("正常居中", _clip_zone((600, 850), r), r)
check_zone("点击点在窗口左侧外", _clip_zone((50, 400), r), r)
check_zone("点击点在窗口上方外", _clip_zone((600, 30), r), r)
check_zone("点击点完全在外", _clip_zone((-500, -500), r), r)
check_zone("点击点在窗口下方外(负高宽事故现场)", _clip_zone((600, 2000), r), r)

r2 = (0, 0, 800, 600)
check_zone("贴边窗口正常点", _clip_zone((400, 520), r2), r2)
check_zone("贴边窗口越界点", _clip_zone((900, 700), r2), r2)

r3 = (200, 200, 300, 200)
check_zone("小窗口正常点", _clip_zone((350, 360), r3), r3)
check_zone("小窗口出界点", _clip_zone((1000, 900), r3), r3)

if VX < 0:
    # 真有左副屏：负坐标窗口必须能正常裁出校验区（虚拟桌面口径）
    r4 = (VX, 0, -VX, min(VH, 1080))
    check_zone("左副屏负坐标窗口", _clip_zone((VX + 200, 900), r4), r4)
else:
    # 单屏：屏外区域宁可不截也不截错，必须优雅返回 None（回退全屏）
    r4 = (-1920, 0, 1920, 1080)
    assert _clip_zone((-960, 900), r4) is None, "屏外区域应回退，而不是截出黑块"
    print("  ✓ 屏外负坐标窗口（本机无左副屏）：优雅回退 None")

assert _clip_zone((10, 10), None) is None, "空矩形应返回 None"
print("  ✓ 空矩形返回 None")

# ── 2. _sanitize：任何离谱 region 都必须变成正宽高且屏内 ──
cases = [
    ("负高（本次事故签名）", (100, 800, 400, -300)),
    ("负宽", (100, 100, -400, 300)),
    ("全负坐标", (-5000, -5000, 300, 300)),
    ("远超屏幕", (1500, 900, 3000, 3000)),
    ("零宽高", (100, 100, 0, 0)),
    ("超出下边", (0, SH - 50, 200, 500)),
]
for name, reg in cases:
    out = _sanitize(reg)
    if out:
        x, y, cw, ch = out
        assert cw > 0 and ch > 0, f"{name}: 仍有负宽高 {out}"
        assert VX <= x and x + cw <= VX + VW and VY <= y and y + ch <= VY + VH, f"{name}: 未夹进虚拟桌面 {out}"
        print(f"  ✓ {name}: {reg} → {out}")
    else:
        print(f"  ✓ {name}: {reg} → None（回退全屏）")

assert _sanitize(None) is None
print("  ✓ None region → None")

# ── 3. _rect_ok：窗口矩形可信判据 ──
assert _rect_ok((100, 100, 1200, 800)) is True
assert _rect_ok((100, 100, -1200, 800)) is False, "负宽必须判死"
assert _rect_ok((100, 100, 1200, -800)) is False, "负高必须判死"
assert _rect_ok((100, 100, 50, 800)) is False, "过窄（启动动画壳窗口）必须判死"
assert _rect_ok((SW + 100, 0, 800, 600)) is False, "完全在屏幕外必须判死"
assert _rect_ok(None) is False
print("  ✓ _rect_ok：负宽/负高/过窄/屏外 全部判死")

print("\n全部通过：任何点击点 / 窗口矩形 / 离谱 region 都不会产出颠倒、越界或负宽高")
