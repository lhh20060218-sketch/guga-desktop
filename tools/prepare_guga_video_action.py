"""Finite local video-to-alpha candidate preparation. Never installs artwork.

Uses original decoded frames, fixed framing and a local segmentation model.
No frame interpolation, generative repainting, optical flow or crossfades.
"""
import argparse
import bisect
import json
import os
import time
from fractions import Fraction
from pathlib import Path

import av
import cv2
import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]


def clean_alpha(mask):
    """Remove disconnected scene remnants without mixing adjacent frames."""
    alpha = np.asarray(mask.convert('L'), dtype=np.uint8)
    foreground = (alpha >= 128).astype(np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(foreground, 8)
    if count <= 1:
        raise ValueError('No foreground detected')
    largest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    keep = (labels == largest).astype(np.uint8)
    # Preserve the original local soft edge, discard distant background haze.
    edge = cv2.dilate(keep, np.ones((3, 3), np.uint8))
    alpha = np.where(edge, alpha, 0).astype(np.uint8)
    return Image.fromarray(alpha)


def fill_enclosed_holes(mask):
    """Keep light interior details (beak/eyes) mistaken for background."""
    alpha = np.asarray(mask.convert('L'), dtype=np.uint8).copy()
    solid = (alpha >= 128).astype(np.uint8)*255
    padded = cv2.copyMakeBorder(solid, 1, 1, 1, 1, cv2.BORDER_CONSTANT, value=0)
    flooded = padded.copy()
    cv2.floodFill(flooded, None, (0, 0), 255)
    holes = (flooded[1:-1, 1:-1] == 0) & (solid == 0)
    alpha[holes] = 255
    return Image.fromarray(alpha)


def intersect_mattes(primary, secondary):
    # Intersect silhouettes, not RGB frames: no temporal blur/double outlines.
    a = np.asarray(fill_enclosed_holes(clean_alpha(primary)))
    b = np.asarray(fill_enclosed_holes(clean_alpha(secondary)))
    if np.count_nonzero(b > 128) < .6*np.count_nonzero(a > 128):
        raise ValueError('Segmentation models disagree; candidate must be reviewed')
    return clean_alpha(Image.fromarray(np.minimum(a, b)))


def protect_costume_yellow(image, mask, reference=None, beak_band=(.15,.35), feet_band=(.76,.86)):
    """Clip-specific rotoscoping aid; restores existing beak/feet pixels only.

    It never repaints RGB. Source must be frontal black-penguin costume, and the
    result remains quarantined for visual review rather than auto-approved.
    """
    alpha = np.asarray(mask).copy()
    h, w = alpha.shape
    roi = np.zeros(alpha.shape, dtype=np.uint8)
    # Manually traced ranges for the fixed frontal source shot. Do not infer the
    # feet ROI from an already damaged mask, which would preserve that damage.
    roi[int(beak_band[0]*h):int(beak_band[1]*h), int(.25*w):int(.75*w)] = 1
    roi[int(feet_band[0]*h):int(feet_band[1]*h), int(.20*w):int(.80*w)] = 1
    hsv = cv2.cvtColor(np.asarray(image.convert('RGB')), cv2.COLOR_RGB2HSV)
    yellow = ((hsv[:,:,0] >= 14) & (hsv[:,:,0] <= 40) &
              (hsv[:,:,1] >= 115) & (hsv[:,:,2] >= 100) & (roi > 0)).astype(np.uint8)
    yellow = cv2.morphologyEx(yellow, cv2.MORPH_CLOSE, np.ones((3,3), np.uint8))
    yellow = cv2.dilate(yellow, np.ones((3,3), np.uint8))
    alpha[yellow > 0] = 255
    return Image.fromarray(alpha)


def remove_tiny_islands(mask):
    alpha = np.asarray(mask).copy()
    _, labels, stats, _ = cv2.connectedComponentsWithStats((alpha > 32).astype(np.uint8), 8)
    for index in range(1, len(stats)):
        if stats[index, cv2.CC_STAT_AREA] < 32:
            alpha[labels == index] = 0
    return Image.fromarray(alpha)


def prepare(args):
    os.environ['U2NET_HOME'] = str(ROOT/'runtime/build-tools')
    os.environ.setdefault('OMP_NUM_THREADS', '2')
    source = Path(args.source).resolve()
    out = Path(args.output).resolve()
    out.mkdir(parents=True, exist_ok=True)
    if (out/'metadata.json').exists():
        raise ValueError('Choose a new output folder; existing review is preserved')
    ensemble = args.model == 'ensemble'
    cache = None
    if args.reuse_masks:
        cache_path = Path(args.reuse_masks).resolve()
        cache = json.loads((cache_path/'metadata.json').read_text(encoding='utf-8'))
        if Path(cache['source']).resolve() != source or args.start < cache['source_start']-1e-6 or args.start+args.seconds > cache['source_start']+cache['requested_seconds']+1e-6:
            raise ValueError('Mask cache must match source and contain the requested interval')
    else:
        from rembg import new_session, remove
        session = new_session('u2netp' if ensemble else args.model, providers=['CPUExecutionProvider'])
        secondary = new_session('isnet-anime', providers=['CPUExecutionProvider']) if ensemble else None
    start_clock = time.monotonic()
    frames = []
    bounds = []
    source_times = []
    with av.open(str(source)) as video:
        native_rate = video.streams.video[0].average_rate
        if not native_rate or not 20 <= float(native_rate) <= 60:
            raise ValueError('Source must have native 20–60 fps')
        for frame in video.decode(video=0):
            if frame.time is None or frame.time < args.start:
                continue
            if frame.time >= args.start + args.seconds:
                break
            if len(frames) >= 300 or time.monotonic()-start_clock > 360:
                raise TimeoutError('Candidate preparation budget exceeded')
            image = frame.to_image().convert('RGB')
            if args.max_width and image.width>args.max_width:
                image=image.resize((args.max_width,round(image.height*args.max_width/image.width)),Image.Resampling.LANCZOS)
            if cache is not None:
                index = bisect.bisect_left(cache['source_times'], frame.time-1e-6)
                if abs(frame.time-cache['source_times'][index]) > 1e-6:
                    raise ValueError('Cached mask frame timestamp mismatch')
                with Image.open(cache_path/'frames'/f'{index:04}.png') as cached:
                    alpha = Image.new('L', image.size, 0)
                    alpha.paste(cached.getchannel('A'), tuple(cache['fixed_crop'][:2]))
                mask = alpha
            else:
                mask = remove(image, session=session, only_mask=True)
                alpha = (intersect_mattes(mask, remove(image, session=secondary, only_mask=True))
                         if ensemble else clean_alpha(mask))
            if args.protect_yellow:
                alpha = protect_costume_yellow(image, alpha, mask, args.beak_band, args.feet_band)
            if args.erase_rect:
                if args.erase_warm_background_only:
                    hsv = cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2HSV)
                    warm = ((hsv[:,:,0]>=10) & (hsv[:,:,0]<=40) &
                            (hsv[:,:,1]>=70) & (hsv[:,:,1]<=180) & (hsv[:,:,2]>=90))
                    region = Image.new('L', image.size, 0)
                    draw = ImageDraw.Draw(region)
                    for rect in args.erase_rect:
                        draw.rectangle(tuple(rect), fill=255)
                    pixels = np.asarray(alpha).copy()
                    pixels[warm & (np.asarray(region)>0)] = 0
                    alpha = Image.fromarray(pixels)
                else:
                    alpha = alpha.copy()
                    draw = ImageDraw.Draw(alpha)
                    for rect in args.erase_rect:
                        draw.rectangle(tuple(rect), fill=0)
            alpha = remove_tiny_islands(alpha)
            cut = image.convert('RGBA')
            cut.putalpha(alpha)
            box = alpha.point(lambda x: 255 if x > 128 else 0).getbbox()
            if box is None:
                raise ValueError('Empty frame')
            bounds.append(box)
            frames.append(cut)
            source_times.append(frame.time)
            if len(frames) % 15 == 0:
                print(f'processed {len(frames)} native frames', flush=True)
    if not frames:
        raise ValueError('Requested interval contains no frames')
    margin = 8
    box = (max(0, min(b[0] for b in bounds)-margin),
           max(0, min(b[1] for b in bounds)-margin),
           min(frames[0].width, max(b[2] for b in bounds)+margin),
           min(frames[0].height, max(b[3] for b in bounds)+margin))
    frame_dir = out/'frames'
    frame_dir.mkdir(exist_ok=True)
    crops = [frame.crop(box) for frame in frames]
    for i, frame in enumerate(crops):
        frame.save(frame_dir/f'{i:04}.png')
    # WebP supports full alpha and complete frames; GIF would quantize hair/face.
    durations = [round((i+1)*1000/float(native_rate))-round(i*1000/float(native_rate))
                 for i in range(len(crops))]
    crops[0].save(out/'candidate.webp', save_all=True, append_images=crops[1:],
                  duration=durations, loop=0, lossless=True, method=4)
    # Side-by-side light/dark backgrounds make dirty edges visible.
    w, h = crops[0].size
    width = (2*w+60+1)//2*2
    height = (h+60+1)//2*2
    previews = []
    with av.open(str(out/'alpha-review.mp4'), 'w') as video:
        stream = video.add_stream('libx264', rate=native_rate)
        stream.width, stream.height = width, height
        stream.pix_fmt = 'yuv420p'
        stream.options = {'crf': '18', 'preset': 'fast'}
        for i, crop in enumerate(crops):
            canvas = Image.new('RGB', (width, height), '#e9edf2')
            ImageDraw.Draw(canvas).rectangle((w+30, 0, width, height), fill='#252932')
            canvas.paste(crop, (15, 30), crop)
            canvas.paste(crop, (w+45, 30), crop)
            ImageDraw.Draw(canvas).text((8, 8), f'Native {float(native_rate):.3f} FPS | {i+1}/{len(crops)} | CANDIDATE', fill='#345')
            frame = av.VideoFrame.from_image(canvas)
            frame.pts = i
            frame.time_base = 1/native_rate
            for packet in stream.encode(frame):
                video.mux(packet)
            if i in set(np.linspace(0, len(crops)-1, 8, dtype=int)):
                previews.append(canvas)
        for packet in stream.encode():
            video.mux(packet)
    sheet = Image.new('RGB', (4*320, 2*240), '#e9edf2')
    for i, preview in enumerate(previews):
        preview.thumbnail((320, 240))
        sheet.paste(preview, (i%4*320, i//4*240))
    sheet.save(out/'contact.png')
    metadata = dict(source=str(source), public_source=args.url, model=args.model,
                    source_start=args.start, requested_seconds=args.seconds,
                    native_fps=float(native_rate), frames=len(frames),
                    costume_yellow_protection=args.protect_yellow,
                    beak_band=args.beak_band, feet_band=args.feet_band,
                    manual_background_rects=args.erase_rect,
                    erase_warm_background_only=args.erase_warm_background_only,
                    reused_masks=str(cache_path) if cache is not None else None,
                    source_times=source_times, fixed_crop=box,
                    interpolation=False, crossfade=False, installed=False,
                    review='pending', redistribution='not_verified',
                    processing_seconds=round(time.monotonic()-start_clock, 2))
    (out/'metadata.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in metadata.items() if k != 'source_times'}, ensure_ascii=True))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--url', required=True)
    parser.add_argument('--start', type=float, default=0)
    parser.add_argument('--seconds', type=float, default=2)
    parser.add_argument('--model', default='ensemble')
    parser.add_argument('--protect-yellow', action='store_true')
    parser.add_argument('--max-width', type=int, default=None, help='Downscale before local matte; preserve aspect ratio')
    parser.add_argument('--beak-band', nargs=2, type=float, default=(.15,.35))
    parser.add_argument('--feet-band', nargs=2, type=float, default=(.76,.86))
    parser.add_argument('--erase-rect', nargs=4, type=int, action='append', default=[],
                        help='Manually reviewed background rectangle in source pixels')
    parser.add_argument('--erase-warm-background-only', action='store_true',
                        help='Within rectangles erase only medium-saturation warm floor color')
    parser.add_argument('--reuse-masks', help='Exact-interval review folder; skips inference')
    args = parser.parse_args()
    if args.start < 0 or not 0 < args.seconds <= 12:
        parser.error('Use a nonnegative start and 0–12 seconds')
    if args.max_width is not None and not 160 <= args.max_width <= 1920:
        parser.error('max-width must be 160–1920')
    if any(not 0 <= a < b <= 1 for a,b in (args.beak_band,args.feet_band)):
        parser.error('Costume bands must be ordered fractions of source height')
    if any(x0 < 0 or y0 < 0 or x0 >= x1 or y0 >= y1 for x0,y0,x1,y1 in args.erase_rect):
        parser.error('Background rectangles must have positive area')
    prepare(args)
