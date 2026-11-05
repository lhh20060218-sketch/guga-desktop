"""Bounded CPU RIFE 4.8 interpolation for transparent animation keyframes.

Input frames are composited onto an opaque neutral matte for flow estimation;
alpha is interpolated independently. The tool refuses malformed sequences.
"""
import argparse,json
from pathlib import Path
import cv2
import numpy as np
import onnxruntime as ort
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
MODEL=ROOT/'runtime/build-tools/rife48-mirror.onnx'
EXPERIMENTAL=ROOT/'runtime/guga-dance-review-20261031'
MATTE=np.array([237.,242.,246.],np.float32)


def load_frame(path,size=None):
    with Image.open(path) as source:
        rgba=source.convert('RGBA')
        if size is not None and rgba.size!=size:rgba=rgba.resize(size,Image.Resampling.LANCZOS)
        image=np.asarray(rgba).copy()
    return cv2.cvtColor(image,cv2.COLOR_RGBA2BGRA)


def matte(frame):
    rgb=frame[:,:,:3].astype(np.float32);a=frame[:,:,3:4].astype(np.float32)/255
    return rgb*a+MATTE*(1-a)


def infer(session,a,b):
    h,w=a.shape[:2]
    if h%32 or w%32:raise ValueError('RIFE dimensions must be divisible by 32')
    # Both leading layouts use channel-first BGR. Alpha is not sent to RGB flow.
    ia=(matte(a)/255.).transpose(2,0,1)[None].astype(np.float32)
    ib=(matte(b)/255.).transpose(2,0,1)[None].astype(np.float32)
    out=session.run(None,{'img0':ia,'img1':ib,'timestep':np.array([.5],np.float32)})[0]
    composite=np.clip(out[0].transpose(1,2,0)*255,0,255).astype(np.float32)
    alpha=((a[:,:,3].astype(np.float32)+b[:,:,3].astype(np.float32))*.5)/255.
    # RIFE flowed an opaque matte. Remove that shared matte from color while
    # preserving genuine shadows, then clear near-invisible interpolation haze.
    rgb=np.clip((composite-MATTE*(1-alpha[:,:,None]))/np.maximum(alpha[:,:,None],.06),0,255)
    alpha_u8=np.clip(alpha*255,0,255).astype(np.uint8)
    alpha_u8[alpha_u8<7]=0
    rgb[alpha_u8==0]=0
    return np.dstack((rgb.astype(np.uint8),alpha_u8))


def midpoint(session,a,b,depth):
    mid=infer(session,a,b)
    if depth<=0:return [mid]
    return midpoint(session,a,mid,depth-1)+[mid]+midpoint(session,mid,b,depth-1)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--levels',type=int,default=3)
    parser.add_argument('--input',type=Path,default=EXPERIMENTAL/'keyframes')
    parser.add_argument('--output',type=Path,default=EXPERIMENTAL/'rife')
    args=parser.parse_args()
    if not 1<=args.levels<=4:raise SystemExit('levels must be 1..4')
    paths=sorted(args.input.glob('*.png'))
    if len(paths)<2:raise SystemExit('at least two RGBA keyframes are required')
    frames=[load_frame(p) for p in paths];size=(frames[0].shape[1],frames[0].shape[0])
    session=ort.InferenceSession(str(MODEL),providers=['CPUExecutionProvider'])
    args.output.mkdir(parents=True,exist_ok=True)
    for old in args.output.glob('*.png'):old.unlink()
    rendered=[];index=0
    for start,following in zip(frames,frames[1:]+frames[:1]):
        between=midpoint(session,start,following,args.levels)
        for frame in [start]+between:
            Image.fromarray(cv2.cvtColor(frame,cv2.COLOR_BGRA2RGBA),'RGBA').save(args.output/f'frame_{index:04d}.png');rendered.append(frame);index+=1
    report={'model':'RIFE 4.8 ONNX','providers':session.get_providers(),'source_keyframes':len(frames),
            'interpolation_levels':args.levels,'rendered_frames':len(rendered),'size':list(size),
            'status':'experimental review; inspect face, hood and foot transitions before install'}
    (args.output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))

if __name__=='__main__':main()
