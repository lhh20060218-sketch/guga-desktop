# 眯眼摇头跳舞

`source_open.png` 与 `source_closed.png` 是原始表情包的两个关键姿态。
`body_open.png` 与 `body_closed.png` 是以原有全身立绘为骨架、按这两个表情
重建的同画风全身关键帧。`frames/` 由构建脚本生成 36 帧透明动画，24fps
循环 1.5 秒。头、发梢和身体一起做小幅摆动，脚底基本固定；桌宠触发
`dance` 或播放歌曲时会自动使用它。

重新生成：

```powershell
python tools/build_eyes_shake_dance.py
```

生成脚本使用 OpenCV 做静态资源预处理；桌宠运行时只使用 Pillow 和 PNG 帧。
