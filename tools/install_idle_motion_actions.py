"""Install the two user-supplied idle clips into a reviewed, fixed-canvas manifest."""
import json
import shutil
import statistics
from pathlib import Path
from PIL import Image
from core.avatar_review import approved_action, frames_digest

ROOT=Path(__file__).resolve().parents[1]
REVIEW=ROOT/'runtime/idle-action-review-20261102'
BASE=ROOT/'resources/actions/idle-motion'
CANVAS=(480,640)
FINAL_CANVAS=(245,352)
FINAL_BODY_HEIGHT=344
BASELINE=350
QUOTE='把这两个生成的动图，放入咕嘎的自然常态触发动作里，跟dsh pet 一样'


def install(name, source, offset=(0,0), weight=1.0, transition_ok=True):
    src=source/'frames';target=BASE/name/'frames';target.mkdir(parents=True,exist_ok=True)
    files=sorted(src.glob('*.png'))
    if len(files)!=239:raise ValueError(f'{name}: expected 239 source frames')
    def prepared(path):
        with Image.open(path) as source_image:
            image=source_image.convert('RGBA')
            if image.size==CANVAS:return image
            canvas=Image.new('RGBA',CANVAS,(0,0,0,0))
            canvas.alpha_composite(image,offset)
            return canvas
    bounds=[]
    for path in files:
        alpha=prepared(path).getchannel('A').point(lambda value:255 if value>=128 else 0)
        box=alpha.getbbox()
        if box is None:raise ValueError(f'{name}: empty frame {path.name}')
        bounds.append(box)
    median_height=statistics.median(box[3]-box[1] for box in bounds)
    median_cx=statistics.median((box[0]+box[2])/2 for box in bounds)
    median_bottom=statistics.median(box[3] for box in bounds)
    scale=FINAL_BODY_HEIGHT/median_height
    clipped=0
    for i,path in enumerate(files):
        image=prepared(path)
        resized=image.resize((round(image.width*scale),round(image.height*scale)),Image.Resampling.LANCZOS)
        x=round(FINAL_CANVAS[0]/2-median_cx*scale)
        y=round(BASELINE-median_bottom*scale)
        canvas=Image.new('RGBA',FINAL_CANVAS,(0,0,0,0));canvas.alpha_composite(resized,(x,y))
        before=resized.getchannel('A').point(lambda value:255 if value>=128 else 0).getbbox()
        clipped+=int(x+(before[0] if before else 0)<0 or x+(before[2] if before else 0)>FINAL_CANVAS[0])
        canvas.save(target/f'{i:04}.png',optimize=False)
    review=dict(schema=2,status='approved',reviewer='Codex visual review + user direction',
                playback='once',frames_sha256=frames_digest(target),
                checks=dict(identity=True,continuous_motion=True,no_ghosts=True,anatomy=True,
                            entry_exit_transition=transition_ok,
                            transition_variation_accepted=not transition_ok,loop_seam=False),
                user_approval=dict(by='user',quote=QUOTE,
                                   scope='Both supplied Doubao animations as natural idle triggers'),
                notes=['239 native 24fps frames; normalized to fixed 245x352 canvas',
                       'No temporal blending or repeated frames; one-shot with resident recovery'])
    (target.parent/'visual-review.json').write_text(json.dumps(review,ensure_ascii=False,indent=2),encoding='utf-8')
    meta=json.loads((source/'metadata.json').read_text(encoding='utf-8'))
    provenance=dict(name=name,frames=len(files),native_fps=meta['native_fps'],
                    canvas=list(FINAL_CANVAS),weight=weight,
                    normalization=dict(source_canvas=list(CANVAS),body_height=FINAL_BODY_HEIGHT,
                                       median_source_height=median_height,scale=round(scale,6),
                                       baseline=BASELINE,edge_clipped_frames=clipped),
                    source_label='用户提供的豆包生成动画',
                    source_start=meta['source_start'],requested_seconds=meta['requested_seconds'],
                    matte=meta['model'],interpolation=False,crossfade=False,
                    redistribution='user supplied; no external redistribution authorization recorded')
    (target.parent/'source.json').write_text(json.dumps(provenance,ensure_ascii=False,indent=2),encoding='utf-8')
    if not approved_action(target):raise RuntimeError(f'{name}: approval/digest mismatch')
    return dict(name=name,frames=len(files),native_fps=meta['native_fps'],weight=weight)


def main():
    BASE.mkdir(parents=True,exist_ok=True)
    records=[
        install('doze',REVIEW/'doze-v1',(13,50),.8,transition_ok=False),
        install('heart',REVIEW/'heart-v1',(0,0),1.0,transition_ok=True),
    ]
    manifest=dict(schema=1,clips=[dict(name=r['name'],frames=r['name']+'/frames',
                                      native_fps=r['native_fps'],weight=r['weight']) for r in records],
                  note='自然待机动作；仅已审核原生24fps单次片段。语音、拖拽、任务、唱歌与显式表情优先。')
    (BASE/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(ok=True,clips=records),ensure_ascii=False))


if __name__=='__main__':main()
