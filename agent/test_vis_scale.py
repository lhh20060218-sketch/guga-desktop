# -*- coding: utf-8 -*-
"""跨分辨率/DPI 的换算单测（不点鼠标、不联网、不需要真实窗口）。
覆盖 v0.12 新增的三条口径：
  ① 送模型图宽自适应（固定 800 是跨机失效的根）；
  ② locate 的坐标换算（含 zone 裁剪与越界拒绝）；
  ③ 固定像素尺寸随 DPI 缩放。
运行：python test_vis_scale.py
"""
import unittest
from unittest import mock

import guga_executor as dex

FAIL = []


def check(cond, name, detail=""):
    if cond:
        print(f"  ✓ {name}")
    else:
        print(f"  ✗ {name}  {detail}")
        FAIL.append(name)


print("=" * 60)
print("  跨分辨率换算单测")
print("=" * 60)

# ① 自适应图宽
print("\n[1] 送模型图宽（小窗省带宽，大窗保清晰）")
check(dex._fit_vis_width(700) == 800, "700px 小窗 → 保底 800", dex._fit_vis_width(700))
check(dex._fit_vis_width(1180) == 1180, "1180px 窗口 → 原尺寸不缩", dex._fit_vis_width(1180))
check(dex._fit_vis_width(1936) == 1600, "1936px 满屏 → 封顶 1600", dex._fit_vis_width(1936))
check(dex._fit_vis_width(3800) == 1600, "3800px 4K → 封顶 1600", dex._fit_vis_width(3800))

# ② 视觉密度：量化跨机退化
print("\n[2] 视觉密度（14px 正文送进模型后剩几像素）")
d1366 = dex._vis_density(1366, 800)
d1936 = dex._vis_density(1936, 1600)
d3800 = dex._vis_density(3800, 1600)
check(d1366 >= 7, "1366 屏 → 可靠", f"{d1366:.1f}px")
check(d1936 >= 7, "1936 屏（改后）→ 可靠", f"{d1936:.1f}px")
check(dex._vis_density(1936, 800) < 6, "1936 屏（改前 800 宽）→ 不足", f"{dex._vis_density(1936, 800):.1f}px")
check(d3800 > dex._vis_density(3800, 800), "4K 比改前好一倍", f"{d3800:.1f} vs {dex._vis_density(3800, 800):.1f}")

# ③ 坐标换算：全窗
print("\n[3] locate 坐标换算（x/y 分别换算）")
info = {"b64": "x", "img_w": 800, "img_h": 600, "x0": 100, "y0": 50, "cw": 1600, "ch": 1200}
with mock.patch.object(dex, "_shot_window", return_value=info), \
     mock.patch.object(dex, "_vision", return_value='{"x":400,"y":300}'):
    p = dex.locate(None, "输入框")
check(p == (900, 650), "模型(400,300) → 屏幕(900,650)", p)

# 图被夹成非等比时，y 必须用 sy 而不是 sx
info2 = {"b64": "x", "img_w": 800, "img_h": 400, "x0": 0, "y0": 0, "cw": 1600, "ch": 1000}
with mock.patch.object(dex, "_shot_window", return_value=info2), \
     mock.patch.object(dex, "_vision", return_value='{"x":800,"y":400}'):
    p2 = dex.locate(None, "按钮")
check(p2 == (1600, 1000), "非等比图：右下角对齐到区域右下角", p2)

# 找不到 / 越界
print("\n[4] 拒绝无效回答")
with mock.patch.object(dex, "_shot_window", return_value=info), \
     mock.patch.object(dex, "_vision", return_value='{"x":-1,"y":-1}'):
    check(dex.locate(None, "不存在") is None, "模型答 -1 → 返回 None")
with mock.patch.object(dex, "_shot_window", return_value=info), \
     mock.patch.object(dex, "_vision", return_value='{"x":9999,"y":300}'):
    check(dex.locate(None, "越界") is None, "坐标越界 → 拒绝（不点窗外）")
with mock.patch.object(dex, "_shot_window", return_value=info), \
     mock.patch.object(dex, "_vision", return_value="看不懂这张图"):
    check(dex.locate(None, "乱答") is None, "非 JSON → 返回 None")

# ⑤ 两级定位：全窗失败后放大区域
print("\n[5] 两级定位（全窗找不着 → 区域放大再看）")
calls = []
def fake_locate(w, desc, zone=None):
    calls.append(zone)
    return (5, 5) if zone else None
with mock.patch.object(dex, "locate", side_effect=fake_locate):
    p3 = dex.locate_deep(None, "底部输入框", [(0, 0.55, 1, 0.45)])
check(p3 == (5, 5), "第二个区域命中 → 返回其坐标", p3)
check(calls == [None, (0, 0.55, 1, 0.45)], "先全窗、再区域", calls)

with mock.patch.object(dex, "locate", return_value=None):
    check(dex.locate_deep(None, "没有", [(0, 0, 1, 0.5)]) is None, "两处都找不到 → None")

# ⑥ DPI 缩放下的固定尺寸
print("\n[6] 固定像素随 DPI 缩放")
dex._DPI_SCALE[0] = 1.0
a1 = dex._sig_area()
dex._DPI_SCALE[0] = 1.5
a2 = dex._sig_area()
check(a1 == 1200, "96dpi 变化面积阈值 1200", a1)
check(a2 == 2700, "150% 缩放面积 ×2.25（1200→2700）", a2)

rect = (0, 0, 1600, 900)
dex._DPI_SCALE[0] = 1.0
z1 = dex._clip_zone((800, 800), rect)
dex._DPI_SCALE[0] = 1.5
z2 = dex._clip_zone((800, 800), rect)
check(z1[2] == 380 and z1[3] == 78, "96dpi 校验区 380x78", z1)
check(z2[2] == 570 and z2[3] == 117, "150% 校验区 570x117（等比放大）", z2)

# 校验区永不为负（历史崩溃点回归）
print("\n[7] 回归：任何输入都不产出负宽高")
bad = [(0, 0, 1600, 900), (1000, 500, 300, 200), (-500, -500, 3200, 2400), (0, 0, 2, 2)]
neg = 0
for r in bad:
    for pt in ((0, 0), (9999, 9999), (-9999, 0), (1600, 900)):
        z = dex._clip_zone(pt, r)
        if z and (z[2] <= 0 or z[3] <= 0):
            neg += 1
check(neg == 0, "16 组畸形输入均无负宽高", f"{neg} 处负值")

print("-" * 60)
if FAIL:
    print(f"  失败 {len(FAIL)} 项：{FAIL}")
    raise SystemExit(1)
print("  全部通过")
