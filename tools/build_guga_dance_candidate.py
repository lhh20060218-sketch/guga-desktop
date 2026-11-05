"""Turn the generated keyframe sheet into review-only animation artifacts.

This is deterministic sprite extraction/compositing, not a video model.
Optical-flow intermediates are labelled experimental and never auto-installed.
"""
import argparse
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image,ImageDraw

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'runtime/guga-dance-review-20261031'


def extract(sheet):
    source=np.asarray(Image.open(sheet).convert('RGBA')).copy()
    h,w=source.shape[:2];frames=[];details=[]
    for i in range(16):
        row,col=divmod(i,4)
        im=source[round(row*h/4):round((row+1)*h/4),round(col*w/4):round((col+1)*w/4)].copy()
        # Small transparent-generation speckles are not part of the silhouette.
        mask=(im[:,:,3]>100).astype('uint8')
        count,labels,stats,centers=cv2.connectedComponentsWithStats(mask,8)
        label=1+int(np.argmax(stats[1:,cv2.CC_STAT_AREA]))
        body=cv2.dilate((labels==label).astype('uint8'),np.ones((3,3),'uint8'))
        im[body==0]=0
        # Remove generated green/red fringe at feet, preserve skin/mouth above.
        r,g,b=im[:,:,:3].astype('float32').transpose(2,0,1)
        yy,xx=np.indices(im.shape[:2])
        spill=(yy>im.shape[0]*.7)&(((r>140)&(r>g*1.7)&(r>b*1.7))|((g>150)&(g>r*1.5)&(g>b*1.4)))
        im[spill]=0
        # Reference feet are yellow: ignore hallucinated dust below their line.
        yellow=(r>135)&(g>95)&(b<135)&(r>b*1.4)&(yy>im.shape[0]*.65)&(im[:,:,3]>150)
        foot_rows=np.flatnonzero(yellow.sum(axis=1)>3)
        baseline=int(foot_rows[-1])+1 if len(foot_rows) else int(np.where(im[:,:,3]>150)[0].max())+1
        im[min(im.shape[0],baseline+3):]=0
        # Keep a fixed pixel scale. Centre on the white belly, not extended arms.
        white=(r>170)&(g>170)&(b>165)&(np.maximum.reduce([r,g,b])-np.minimum.reduce([r,g,b])<35)
        white&=(yy>baseline*.57)&(yy<baseline*.88)&(im[:,:,3]>200)
        center=float(np.median(xx[white])) if white.sum()>30 else im.shape[1]/2
        canvas=Image.new('RGBA',(384,416))
        lift=10 if i==8 else 0
        offset=(round(192-center),round(388-baseline-lift))
        canvas.alpha_composite(Image.fromarray(im),offset)
        frames.append(np.array(canvas))
        details.append({'frame':i+1,'source_baseline':baseline,'source_center':round(center,2),'lift':lift})
    return frames,details


def flow_gray(frame):
    alpha=frame[:,:,3:4].astype('float32')/255
    composed=frame[:,:,:3]*alpha+230*(1-alpha)
    return cv2.cvtColor(composed.astype('uint8'),cv2.COLOR_RGB2GRAY)


def intermediates(a,b,steps=5):
    engine=cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
    f=engine.calc(flow_gray(a),flow_gray(b),None)
    g=engine.calc(flow_gray(b),flow_gray(a),None)
    h,w=a.shape[:2];yy,xx=np.mgrid[:h,:w].astype('float32')
    def premult(im):
        im=im.astype('float32')/255
        im[:,:,:3]*=im[:,:,3:4]
        return im
    pa,pb=premult(a),premult(b)
    for n in range(steps):
        t=n/steps
        left=cv2.remap(pa,xx-t*f[:,:,0],yy-t*f[:,:,1],cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT)
        right=cv2.remap(pb,xx-(1-t)*g[:,:,0],yy-(1-t)*g[:,:,1],cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT)
        blend=left*(1-t)+right*t
        blend[:,:,:3]/=np.maximum(.001,blend[:,:,3:4])
        blend[blend[:,:,3]<.025]=0
        yield np.clip(blend*255,0,255).astype('uint8')


def export_gif(frames,path,duration,background=None):
    images=[]
    for arr in frames:
        im=Image.fromarray(arr)
        if background:
            bg=Image.new('RGBA',im.size,background);bg.alpha_composite(im);im=bg.convert('RGB')
            images.append(im)
        else:
            # GIF's binary alpha and palette are a preview limitation. Master is APNG.
            alpha=im.getchannel('A');quant=im.convert('RGB').quantize(colors=255)
            palette=quant.getpalette()[:765]+[0,0,0];quant.putpalette(palette)
            quant.paste(255,mask=alpha.point(lambda x:255 if x<100 else 0))
            quant.info['transparency']=255;images.append(quant)
    kwargs={} if background else {'transparency':255,'disposal':2}
    images[0].save(path,save_all=True,append_images=images[1:],duration=duration,loop=0,optimize=False,**kwargs)
    for im in images:im.close()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--flow',action='store_true');args=parser.parse_args()
    OUT.mkdir(exist_ok=True,parents=True)
    frames,details=extract(OUT/'guga-dance-sheet-v1.png')
    for i,arr in enumerate(frames):
        target=OUT/'keyframes';target.mkdir(exist_ok=True)
        Image.fromarray(arr).save(target/f'{i+1:02d}.png')
    master=[Image.fromarray(a) for a in frames]
    master[0].save(OUT/'guga-dance-keyframes.apng',save_all=True,append_images=master[1:],duration=180,loop=0,disposal=1,blend=0)
    export_gif(frames,OUT/'guga-dance-keyframes.gif',180)
    used=frames
    if args.flow:
        used=[f for i,a in enumerate(frames) for f in intermediates(a,frames[(i+1)%len(frames)])]
        export_gif(used,OUT/'guga-dance-flow-preview.gif',40)
        export_gif(used,OUT/'guga-dance-flow-on-gray.gif',40,'#edf2f6')
        # Midpoints reveal flow deformation more clearly than small moving previews.
        contact=Image.new('RGB',(384*4,416*2),'#edf2f6')
        for i,index in enumerate([2,7,17,27,37,47,57,67]):
            im=Image.fromarray(used[index]);contact.paste(im,((i%4)*384,(i//4)*416),im)
        contact.save(OUT/'flow-intermediate-review.png')
    report={'source':'built-in image generation; original Guga reference images',
            'keyframes':16,'rendered_frames':len(used),'frame_size':[384,416],
            'video_model_used':False,'flow_interpolation':args.flow,'installed_into_pet':False,
            'status':'review candidate; not approved as production dance','normalization':details}
    (OUT/'candidate-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='normalization'},ensure_ascii=False))

if __name__=='__main__':main()
