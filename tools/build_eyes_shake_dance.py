"""Build the full-body squint-and-shake dance as transparent PNG frames.

`body_open.png` and `body_closed.png` are style-matched full-body keyframes.
The face never floats independently: the complete pet sways as one silhouette,
with the head leading and the feet nearly anchored.
"""
import math
from pathlib import Path

import cv2
import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
ACTION = ROOT / 'resources' / 'actions' / 'eyes_shake_dance'
OPENED = ACTION / 'body_open.png'
CLOSED = ACTION / 'body_closed.png'
FRAMES = ACTION / 'frames'
CANVAS = (227, 326)
FRAME_COUNT = 36
FPS = 24.0


def load_rgba(path):
    image = Image.open(path).convert('RGBA')
    if image.size != CANVAS:
        image = image.resize(CANVAS, Image.Resampling.LANCZOS)
    return cv2.cvtColor(np.array(image), cv2.COLOR_RGBA2BGRA)


def dance_warp(frame, phase):
    """Small head-led sway with a nearly fixed lower body."""
    height, width = frame.shape[:2]
    neck = int(height * .50)
    top = int(height * .03)
    yy, xx = np.indices((height, width), dtype=np.float32)
    head_weight = np.clip((neck - yy) / (neck - top), 0, 1) ** 1.55
    body_shift = 1.15 * math.sin(phase * 2)
    head_shift = 4.2 * math.sin(phase * 2)
    yaw = math.sin(phase * 2)
    bob = 1.05 * (1 - math.cos(phase * 4))
    dx = body_shift + head_shift * head_weight + yaw * (yy - neck) * .020 * head_weight
    dy = bob * head_weight + .20 * math.sin(phase * 4)
    return cv2.remap(frame, xx - dx, yy - dy, cv2.INTER_LINEAR,
                     borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))


def main():
    opened = load_rgba(OPENED)
    closed = load_rgba(CLOSED)
    width, height = CANVAS

    FRAMES.mkdir(parents=True, exist_ok=True)
    for old in FRAMES.glob('frame_*.png'):
        old.unlink()

    rendered = []
    for index in range(FRAME_COUNT):
        phase = 2 * math.pi * index / FRAME_COUNT
        # The eye change happens between two frames, like a real blink. A
        # long crossfade would expose both open and closed eyelashes at once.
        source = closed if 7 <= index < 23 else opened
        frame = dance_warp(source, phase)
        Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGRA2RGBA), 'RGBA').save(
            FRAMES / f'frame_{index:02d}.png')
        rendered.append(frame)

    preview = []
    yy, xx = np.indices((height, width))
    checker = np.where(((yy // 10 + xx // 10) % 2)[..., None], 244, 214).astype(np.uint8)
    checker = np.repeat(checker, 3, axis=2)
    for frame in rendered:
        alpha = frame[..., 3:4].astype(np.float32) / 255
        rgb = cv2.cvtColor(frame[..., :3], cv2.COLOR_BGR2RGB).astype(np.float32)
        shown = np.clip(rgb * alpha + checker * (1 - alpha), 0, 255).astype(np.uint8)
        preview.append(Image.fromarray(shown, 'RGB'))
    preview[0].save(ACTION / 'preview.gif', save_all=True, append_images=preview[1:],
                    duration=round(1000 / FPS), loop=0, disposal=2)
    print(f'wrote {len(rendered)} full-body frames to {FRAMES}')


if __name__ == '__main__':
    main()
