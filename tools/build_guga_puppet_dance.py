"""Build a seamless, single-exposure Guga dance from two aligned full-body poses.

Every pixel is sampled once per output frame. Redundant optical-flow composites
are intentionally absent, eliminating double silhouettes and afterimages.
"""
import argparse,json,math
from pathlib import Path
import cv2
import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'resources/actions/eyes_shake_dance'
OUT=ROOT/'runtime/guga-puppet-dance-20261101';TARGET=ROOT/'resources/actions/joy_sway_dance'
CANVAS=(384,552);FPS=25;FRAMES=125


def smoothstep(a,b,x):
    u=np.clip((x-a)/max(1e-6,b-a),0,1);return u*u*(3-2*u)


def read(path):
    with Image.open(path) as im:
        rgba=np.asarray(im.convert('RGBA')).copy()
    return cv2.cvtColor(rgba,cv2.COLOR_RGBA2BGRA)


def clean(rgba):
    a=rgba[:,:,3];rgba[a<10]=0
    # The generated full-body source contains a few red/green spill pixels at
    # the feet. Keep yellow footwear and remove only strongly saturated fringes.
    r,g,b=[rgba[:,:,i].astype(np.int16) for i in range(3)]
    yy=np.indices(a.shape)[0]
    spill=(yy>a.shape[0]*.86)&(((r>150)&(r>g*1.8)&(r>b*1.7))|((g>155)&(g>r*1.65)&(g>b*1.4)))
    rgba[spill]=0
    return rgba


def load_pair():
    source=[clean(read(SOURCE/'body_open.png')),clean(read(SOURCE/'body_closed.png'))]
    masks=[]
    for rgba in source:
        binary=(rgba[:,:,3]>12).astype(np.uint8)
        count,labels,stats,_=cv2.connectedComponentsWithStats(binary,8)
        keep=np.zeros_like(binary)
        for label in range(1,count):
            if stats[label,cv2.CC_STAT_AREA]>5000:keep[labels==label]=1
        masks.append(keep)
    union=masks[0]|masks[1];ys,xs=np.where(union>0);bbox=(xs.min(),ys.min(),xs.max()+1,ys.max()+1)
    bw,bh=bbox[2]-bbox[0],bbox[3]-bbox[1]
    scale=min(CANVAS[0]*.90/bw,CANVAS[1]*.90/bh)
    resized=[cv2.resize(im,None,fx=scale,fy=scale,interpolation=cv2.INTER_LANCZOS4) for im in source]
    output=[]
    for rgba in resized:
        canvas=np.zeros((CANVAS[1],CANVAS[0],4),np.uint8)
        m=(rgba[:,:,3]>12).astype(np.uint8);count,labels,stats,_=cv2.connectedComponentsWithStats(m,8)
        for label in range(1,count):
            if stats[label,cv2.CC_STAT_AREA]<1000:rgba[labels==label]=0
        ys,xs=np.where(rgba[:,:,3]>12);x0=round(CANVAS[0]/2-(xs.min()+xs.max()+1)/2);y1=round(CANVAS[1]*.965)
        y0=y1-rgba.shape[0];x0=max(0,min(CANVAS[0]-rgba.shape[1],x0));y0=max(0,min(CANVAS[1]-rgba.shape[0],y0))
        canvas[y0:y0+rgba.shape[0],x0:x0+rgba.shape[1]]=rgba;output.append(canvas)
    return output[0],output[1]


def ellipse_weight(X,Y,cx,cy,rx,ry,power=2.):
    return np.exp(-(np.abs((X-cx)/rx)**power)-((Y-cy)/ry)**2)


def rotated_maps(X,Y,pivot,degrees):
    t=math.radians(degrees);c=math.cos(-t);s=math.sin(-t)
    px,py=pivot;vx=X-px;vy=Y-py
    return px+c*vx-s*vy,py+s*vx+c*vy


def motion_maps(width,height,phase):
    X,Y=np.meshgrid(np.arange(width,dtype=np.float32),np.arange(height,dtype=np.float32))
    nx=X/width;ny=Y/height;cx=width*.5
    # The sway moves the body gently while feet remain visually anchored.
    body_w=smoothstep(.58,.94,1-ny)
    head_w=smoothstep(.55,.78,1-ny)
    dx=.018*width*body_w*math.sin(phase)
    dy=-.007*height*head_w*(1-math.cos(phase*2))*.5
    yaw=.65*math.sin(phase*2+.25)+.35*math.sin(phase+.15)
    dx+=(cx+(X-cx)*(1-.052*yaw*head_w))-X
    dx+=.008*width*head_w*math.sin(phase*2+.45)
    # Hair follows with a delayed, restrained response.
    side=np.exp(-((np.abs(nx-.5)/.34)**4))*smoothstep(.10,.27,ny)*smoothstep(.72,.50,ny)
    dx+=.007*width*side*math.sin(phase*2-.35)
    # Alternating flipper lifts. Rotation around separate shoulders gives
    # articulated motion while preserving one clean silhouette.
    right=max(0.,math.sin(phase+.15))**2
    left=max(0.,math.sin(phase+math.pi+.15))**2
    both=max(0.,math.sin(phase*2-.25))**4
    for side_name,pivot_x,angle,pulse in (('right',.735,-27*right-8*both,'right'),('left',.265,27*left+8*both,'left')):
        wgt=ellipse_weight(nx,ny,pivot_x,.635,.205,.205,2.2)
        if side_name=='right':wgt*=smoothstep(.59,.68,nx)
        else:wgt*=smoothstep(.41,.32,nx)
        rx,ry=rotated_maps(X,Y,(pivot_x*width,.555*height),angle)
        dx+=(rx-X)*wgt;dy+=(ry-Y)*wgt
    # Alternating toe taps; the other foot remains planted.
    step_l=max(0.,math.sin(phase*2))**8
    step_r=max(0.,-math.sin(phase*2))**8
    for foot_x,step in ((.35,step_l),(.65,step_r)):
        wgt=ellipse_weight(nx,ny,foot_x,.938,.105,.080,3.)
        dx+=(-.010*width*step)*wgt
        dy+=(.020*height*step)*wgt
    # Light chain swings as a separate mass after the body.
    chain=ellipse_weight(nx,ny,.50,.745,.19,.14,2.5)
    dx+=.009*width*chain*math.sin(phase-.55)
    dy+=.003*height*chain*(1-math.cos(phase-.55))*.5
    # A compact two-beat bounce, bounded to avoid clipping.
    hop=max(0.,math.sin(phase*2))**7
    dy-= .020*height*hop
    return X+dx,Y+dy,hop


def render(open_frame,closed_frame):
    h,w=open_frame.shape[:2]
    rendered=[]
    for i in range(FRAMES):
        phase=2*math.pi*i/FRAMES;mx,my,hop=motion_maps(w,h,phase)
        index=0 if i<35 or i>=58 and i<101 or i>=106 else 1
        source=closed_frame if index==1 else open_frame
        out=cv2.remap(source,mx,my,cv2.INTER_CUBIC,borderMode=cv2.BORDER_CONSTANT,borderValue=(0,0,0,0))
        out[out[:,:,3]<10]=0
        # Bring tiny motion highlights through a soft rim without duplicating
        # character contours: alpha is sampled from the same map.
        rendered.append(out)
    return rendered


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--install',action='store_true');args=parser.parse_args()
    if args.install:
        raise SystemExit('此动作已被视觉审核否决；只允许生成审核预览，禁止覆盖正式资源。')
    OUT.mkdir(parents=True,exist_ok=True)
    opened,closed=load_pair()
    frames=render(opened,closed);shots=OUT/'frames';shots.mkdir(exist_ok=True)
    for old in shots.glob('*.png'):old.unlink()
    preview=[];baselines=[]
    for i,frame in enumerate(frames):
        Image.fromarray(cv2.cvtColor(frame,cv2.COLOR_BGRA2RGBA),'RGBA').save(shots/f'frame_{i:04d}.png',optimize=True)
        a=frame[:,:,3];ys,xs=np.where(a>24);baselines.append(int(ys.max()))
        if i%2==0:
            rgba=cv2.cvtColor(frame,cv2.COLOR_BGRA2RGBA);im=Image.fromarray(rgba,'RGBA');bg=Image.new('RGBA',im.size,'#edf2f6');bg.alpha_composite(im);preview.append(bg.convert('RGB'))
    preview[0].save(OUT/'preview.gif',save_all=True,append_images=preview[1:],duration=40*2,loop=0,optimize=True)
    # Eight representative cells for visual QA.
    sheet=Image.new('RGB',(384*4,552*2),'#edf2f6')
    for j,i in enumerate((0,16,32,48,64,80,96,112)):
        with Image.open(shots/f'frame_{i:04d}.png') as im:
            bg=Image.new('RGBA',im.size,'#edf2f6');bg.alpha_composite(im.convert('RGBA'));sheet.paste(bg.convert('RGB'),((j%4)*384,(j//4)*552))
    sheet.save(OUT/'contact-review.png');sheet.resize((960,276),Image.Resampling.LANCZOS).save(OUT/'thumbnail.png')
    metadata={'name':'joy_sway_dance','method':'single-exposure layered warp; no optical-flow compositing',
              'source':'body_open/body_closed', 'frames':FRAMES,'fps':FPS,'seconds':5.0,'canvas':list(CANVAS),
              'foot_baseline':[min(baselines),max(baselines)],'clipped_frames':sum(1 for f in frames if (f[0,:,3]>24).any() or (f[-1,:,3]>24).any() or (f[:,0,3]>24).any() or (f[:,-1,3]>24).any()),
              'ghost_prevention':'each output frame samples exactly one source pose per pixel; expression changes are discrete'}
    if metadata['clipped_frames']:raise SystemExit('animation is clipped')
    if max(baselines)-min(baselines)>24:raise SystemExit('foot baseline drift')
    (OUT/'metadata.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
    if args.install:
        target=TARGET/'frames';target.mkdir(parents=True,exist_ok=True)
        for old in target.glob('*.png'):old.unlink()
        for i,frame in enumerate(frames):Image.fromarray(cv2.cvtColor(frame,cv2.COLOR_BGRA2RGBA),'RGBA').save(target/f'frame_{i:04d}.png',optimize=True)
        preview[0].save(TARGET/'preview.gif',save_all=True,append_images=preview[1:],duration=80,loop=0,optimize=True)
        sheet.resize((768,552),Image.Resampling.LANCZOS).save(TARGET/'thumbnail.png')
        (TARGET/'metadata.json').write_text(json.dumps(dict(metadata,installed=True),ensure_ascii=False,indent=2),encoding='utf-8')
        (TARGET/'README.md').write_text('咕嘎开心摆鳍舞 V2\n单源部件形变，每帧只采样一次，无插帧叠影。\n右键或说“跳舞”触发。\n',encoding='utf-8')
    print(json.dumps(metadata,ensure_ascii=False))

if __name__=='__main__':main()
