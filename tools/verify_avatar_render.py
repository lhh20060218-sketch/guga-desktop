"""One bounded real-GL render pass, 1x/2x DPI; exports preview and timings."""
import json
import statistics
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from launcher import _prepare_qt
_prepare_qt()
from PyQt5.QtWidgets import QApplication
from ui.avatar_renderer import GLPenguinRenderer
from PIL import Image, ImageDraw
app=QApplication([])
out=ROOT/'runtime/appearance-preview'
out.mkdir(exist_ok=True)
results=[]
for ratio in (1,2):
    r=GLPenguinRenderer(250,pixel_ratio=ratio)
    assert r.available, r.error
    frames=[];times=[]
    for i in range(60):
        r.motion.trigger_action('spin') if i==0 else None
        r.motion.advance(2.2/60)
        img=r.render();times.append(r._render_ms)
        assert not img.isNull()
        if i%5==0 or i==59:
            path=out/f'spin-{ratio}-{i:02}.png';img.save(str(path))
            pil=Image.open(path).convert('RGBA')
            assert pil.getextrema()[3][0]==0, 'Background must be transparent'
            assert pil.getextrema()[3][1]==255, 'Character must be opaque'
            bbox=pil.getbbox()
            assert bbox and bbox[0]>0 and bbox[1]>0 and bbox[2]<pil.width and bbox[3]<pil.height, 'Clipped character'
            if ratio==2: frames.append(pil.copy())
    r.motion.action='none';r.motion.advance(.05)
    for expr in r.EXPRESSIONS:
        r.set_expression(expr);r.render().save(str(out/f'expression-{ratio}-{expr}.png'))
    a=r.render();r.trigger_action('sunglasses');b=r.render()
    assert a!=b,'Glasses must change rendered pixels'
    b.save(str(out/f'glasses-{ratio}.png'))
    r.motion.trigger_action('sneak_peek')
    for _ in range(45):r.motion.advance(1/30)
    r.render().save(str(out/f'peek-{ratio}.png'))
    results.append(dict(dpi_ratio=ratio,render_median_ms=round(statistics.median(times),2),
                        render_p95_ms=round(sorted(times)[56],2),frames=len(times)))
    r.close()
    if frames:
        # Preview has a visible backdrop, separate from the transparent runtime.
        gif=[]
        for frame in frames:
            bg=Image.new('RGB',frame.size,'#e9eff4');bg.paste(frame,mask=frame.getchannel('A'));gif.append(bg)
        gif[0].save(out/'guga-spin.gif',save_all=True,append_images=gif[1:],duration=180,loop=0)

sheet=Image.new('RGB',(1000,420),'#e9eff4');draw=ImageDraw.Draw(sheet)
for i,name in enumerate(('spin-2-00','spin-2-15','spin-2-30','glasses-2')):
    im=Image.open(out/(name+'.png')).convert('RGBA');im.thumbnail((240,370))
    sheet.paste(im,(i*250+(250-im.width)//2,30),im)
    draw.text((i*250+12,10),('Front','Side','Back','Accessory')[i],fill='#283645')
sheet.save(out/'overview.png')
(out/'verification.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
print(json.dumps(dict(ok=True,results=results,preview=str(out/'overview.png'))))
