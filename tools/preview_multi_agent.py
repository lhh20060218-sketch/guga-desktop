"""Finite offscreen companion art review. No audio, model or network calls."""
import argparse,io,json,os,sys
from pathlib import Path
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from launcher import _prepare_qt
_prepare_qt()
from PyQt5.QtCore import Qt,QRectF,QBuffer,QIODevice
from PyQt5.QtGui import QImage,QPainter,QColor,QFont,QFontDatabase
from PyQt5.QtWidgets import QApplication
from ui.mascot_animator import MascotAnimator

def make_anim(name,width=225,candidate=False):
    manifest=ROOT/'resources/multiagent'/name/'v2/manifest.json' if candidate and name!='guga' else None
    return MascotAnimator(name,width,manifest)

def settle(anim,seconds=.2):
    for _ in range(max(1,round(seconds/.05))):anim.advance(.05)

def text(p,x,y,value,size=12,color='#423a49',bold=False):
    p.setPen(QColor(color));p.setFont(QFont('Microsoft YaHei UI',size,QFont.Bold if bold else QFont.Normal));p.drawText(x,y,value)

def canvas(w,h):
    result=QImage(w,h,QImage.Format_ARGB32);result.fill(QColor('#f1f0f6'))
    p=QPainter(result);p.setRenderHint(QPainter.Antialiasing);p.setRenderHint(QPainter.SmoothPixmapTransform)
    return result,p

def render_team(animations,note='高清原画 · 透明轮廓 · 呼吸轻摆 · 偶尔关注鼠标'):
    image,p=canvas(1080,510)
    text(p,26,36,'咕嘎小队 · 原画互动审核',18,bold=True)
    for i,(anim,name,role) in enumerate(zip(animations,['咕嘎','大肥鱼','Dora'],['001 · 总执行官','002 · 技术审查员','003 · 橘子创意搭档'])):
        x=20+i*354
        p.setPen(Qt.NoPen);p.setBrush(QColor('#ffffff'));p.drawRoundedRect(QRectF(x,54,332,438),20,20)
        text(p,x+18,85,name,16,bold=True);text(p,x+18,110,role,10,color='#81738c')
        anim.draw(p,x+(332-anim.width)/2,125)
        text(p,x+18,477,'完整轮廓 / 独立窗口 / 保留原画',10,color='#82798d')
    p.end();return image

def run():
    parser=argparse.ArgumentParser();parser.add_argument('--candidate',action='store_true');parser.add_argument('--motion',action='store_true')
    args=parser.parse_args();app=QApplication.instance() or QApplication([])
    for name in ('msyh.ttc','msyhbd.ttc'):QFontDatabase.addApplicationFont('C:/Windows/Fonts/'+name)
    out=ROOT/'runtime/multiagent-review';out.mkdir(parents=True,exist_ok=True)
    animations=[make_anim(name,candidate=args.candidate) for name in ('guga','dafish','dora')]
    for a in animations:settle(a)
    team=out/'three-pets-review-v2.png';render_team(animations).save(str(team))
    image,p=canvas(1280,848);text(p,20,30,'Dora / 大肥鱼 · 真实表情素材审核',17,bold=True)
    rows=[('dora',['happy','sad','angry','sleepy'],['吃橘子 / 开心','哭泣 / 委屈','生气','困倦（保持至主动互动）']),
          ('dafish',['normal','happy','sad','sleepy'],['指点 / 日常','开心','委屈','困倦（保持至主动互动）'])]
    for row,(name,expressions,labels) in enumerate(rows):
        for col,(expression,label) in enumerate(zip(expressions,labels)):
            x=col*320;y=45+row*398
            p.setPen(Qt.NoPen);p.setBrush(QColor('#ffffff'));p.drawRoundedRect(QRectF(x+8,y,304,384),16,16)
            a=make_anim(name,215,args.candidate);a.set_expression(expression);settle(a)
            a.draw(p,x+(320-a.width)/2,y+12)
            text(p,x+20,y+362,label,11,color='#695c77');a.stop()
    p.end();sheet=out/'expressions-review-v2.png';image.save(str(sheet))
    result=dict(team=str(team),expressions=str(sheet))
    if args.motion:
        from PIL import Image
        frames=[]
        for frame in range(60):
            for i,a in enumerate(animations):
                if frame==6:a.look_at(.8,-.3)
                if frame==20:a.trigger_action('bounce')
                if frame==37:a.trigger_action('sneak_peek')
                if frame==52:a.look_at(0,0)
                a.advance(1/15)
            rendered=render_team(animations)
            buffer=QBuffer();buffer.open(QIODevice.WriteOnly);rendered.save(buffer,'PNG')
            with Image.open(io.BytesIO(bytes(buffer.data()))) as shot:frames.append(shot.convert('RGB').copy())
        gif=out/'motion-review-v2.gif'
        frames[0].save(gif,save_all=True,append_images=frames[1:],duration=67,loop=0,optimize=False)
        for frame in frames:frame.close()
        result['motion']=str(gif)
    for a in animations:a.stop()
    print(json.dumps(result,ensure_ascii=False))
    return 0

if __name__=='__main__':sys.exit(run())
