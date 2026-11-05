"""Bounded real-GL motion verification and a side-by-side animation preview."""
import dataclasses
import hashlib
import json
import statistics
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from launcher import _prepare_qt
_prepare_qt()
from PyQt5.QtWidgets import QApplication
from ui.avatar_renderer import GLPenguinRenderer
from PIL import Image,ImageDraw

app=QApplication([])
out=ROOT/'runtime/motion-v2';out.mkdir(exist_ok=True)
summary=[];gallery={}
for ratio in (1,2):
    r=GLPenguinRenderer(250,pixel_ratio=ratio)
    assert r.available,r.error
    for action,duration in [('spin',2.6),('sneak_peek',3.4),('wave',2.2),('dance',4.0)]:
        from ui.avatar_motion import AvatarMotion
        r.motion=AvatarMotion();r.trigger_action(action)
        if action=='dance':r.sunglasses=True;r._sunglasses_until=0
        frames=[];timings=[]
        count=round(duration*30)
        for i in range(count):
            p=r.motion.advance(1/30)
            image=r.render();timings.append(r._render_ms)
            image=image.convertToFormat(image.Format_RGBA8888)
            bits=image.bits();bits.setsize(image.byteCount())
            pil=Image.frombytes('RGBA',(image.width(),image.height()),bytes(bits))
            bbox=pil.getbbox()
            assert bbox and bbox[0]>0 and bbox[1]>0 and bbox[2]<pil.width and bbox[3]<pil.height,(action,ratio,i,'clipped')
            assert pil.getextrema()[3]==(0,255),(action,'alpha')
            if ratio==1:
                frames.append(pil.resize((220,316),Image.Resampling.LANCZOS))
        # An ablation of depth/foot/flipper channels must alter actual pixels.
        if action=='dance':
            before=r.render()
            original=r.motion.pose
            r.motion.pose=dataclasses.replace(original,depth=0,foot_left_pitch=0,
                foot_right_pitch=0,foot_left_lift=0,foot_right_lift=0,
                wing_left_pitch=0,wing_right_pitch=0,wing_left_yaw=0,wing_right_yaw=0)
            after=r.render()
            assert before!=after,'3D channels were not applied by the renderer'
            r.motion.pose=original
        summary.append(dict(action=action,ratio=ratio,frames=count,
            median_ms=round(statistics.median(timings),2),p95_ms=round(sorted(timings)[int(count*.95)],2)))
        if ratio==1:gallery[action]=frames
    r.close()

labels=['TURN','LEAN / LOOK','WAVE','DANCE / STEP']
names=['spin','sneak_peek','wave','dance']
gif=[]
for i in range(96):
    canvas=Image.new('RGB',(880,350),'#e9eff4');draw=ImageDraw.Draw(canvas)
    for col,name in enumerate(names):
        frame=gallery[name][min(i,len(gallery[name])-1)]
        canvas.paste(frame,(col*220,25),frame)
        draw.text((col*220+12,8),labels[col],fill='#283645')
    gif.append(canvas)
gif[0].save(out/'guga-motion-v2.gif',save_all=True,append_images=gif[1:],duration=33,loop=0)
gif[38].save(out/'overview.png')
(out/'verification.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
print(json.dumps(dict(ok=True,frames=sum(s['frames'] for s in summary),results=summary,
                      preview=str(out/'guga-motion-v2.gif'))))
