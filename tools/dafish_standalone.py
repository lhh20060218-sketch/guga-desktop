"""Native standalone pet, independent of DSH and without model/microphone.

Explicit --seconds is for finite visual QA; normal user launch stays open.
"""
import argparse
import json
import sys
import time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from launcher import _prepare_qt
_prepare_qt()
from PyQt5.QtCore import Qt,QPoint,QTimer
from PyQt5.QtGui import QPainter
from PyQt5.QtWidgets import QApplication,QWidget,QMenu,QInputDialog
from ui.video_mascot import VideoMascotAnimator
from ui.pet_physics import DesktopPetPhysics


class StandaloneFish(QWidget):
    def __init__(self):
        super().__init__(None,Qt.FramelessWindowHint|Qt.Tool|Qt.WindowStaysOnTopHint)
        self.setWindowTitle('大肥鱼 · 独立动画版（无需 DSH）')
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.anim=VideoMascotAnimator(240)
        self.scale=1.
        self.resize(self.anim.width,self.anim.height)
        self.physics=DesktopPetPhysics(self,self.anim)
        self.anim.on_move=self.physics.walk
        self.anim.on_update=self.update
        self.drag=None;self.moved=False
        area=self.screen().availableGeometry()
        self.move(area.right()-self.width(),area.bottom()-self.height())
        self.anim.start();self.show()

    def paintEvent(self,event):
        p=QPainter(self);p.scale(self.scale,self.scale);self.anim.draw(p,0,0)

    def mousePressEvent(self,event):
        if event.button()==Qt.LeftButton:
            self.woke=self.anim.user_interaction()
            self.physics.press(event.globalPos());self.drag=event.globalPos()-self.pos();self.moved=False
            self.press=event.globalPos()

    def mouseMoveEvent(self,event):
        if self.drag is not None and event.buttons()&Qt.LeftButton:
            if (event.globalPos()-self.press).manhattanLength()<4:return
            self.anim.set_dragging(True)
            self.physics.sample(event.globalPos());self.move(event.globalPos()-self.drag);self.moved=True

    def mouseReleaseEvent(self,event):
        if event.button()==Qt.LeftButton:
            self.anim.set_dragging(False);self.physics.release(self.moved)
            if not self.moved and not self.woke:self.anim.click()
            self.drag=None

    def contextMenuEvent(self,event):
        self.physics.stop();menu=QMenu(self)
        for category in self.anim.pools['categories']:
            group=menu.addMenu(category['id'])
            for clip in category['actions']:
                group.addAction(clip).triggered.connect(lambda checked=False,n=clip:self.anim.play_clip(n))
        menu.addAction('睡觉 / 叫醒').triggered.connect(self.sleep)
        roam=menu.addAction('桌面漫游');roam.setCheckable(True);roam.setChecked(self.anim._roaming)
        roam.toggled.connect(lambda on:setattr(self.anim,'_roaming',on))
        menu.addAction('调整大小…').triggered.connect(self.resize_pet)
        menu.addAction('退出独立动画版').triggered.connect(self.close)
        menu.exec_(event.globalPos());menu.deleteLater()

    def sleep(self):
        if self.anim.expression=='sleepy':self.anim.user_interaction()
        else:self.anim.set_expression('sleepy')

    def resize_pet(self):
        value,ok=QInputDialog.getInt(self,'大肥鱼大小','百分比（原尺寸为最大值）',round(self.scale*100),40,100)
        if ok:
            self.physics.stop();self.scale=value/100
            self.resize(round(self.anim.width*self.scale),round(self.anim.height*self.scale))

    def closeEvent(self,event):
        self.physics.stop();self.anim.stop();event.accept()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--seconds',type=float,default=0)
    parser.add_argument('--receipt',type=Path)
    args=parser.parse_args();app=QApplication(sys.argv);app.setQuitOnLastWindowClosed(True)
    fish=StandaloneFish()
    if args.seconds:
        def finish():
            result={'visible':fish.isVisible(),'frames_received':fish.anim._video_frame is not None,
                    'clip':fish.anim.current_clip,'decode_error':fish.anim.decode_error,
                    'queue_size':fish.anim._queue.qsize(),'dsh_required':False,'microphone_opened':False}
            if args.receipt:
                args.receipt.parent.mkdir(parents=True,exist_ok=True)
                fish.grab().save(str(args.receipt.with_suffix('.png')))
                args.receipt.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
            fish.close();app.quit()
        QTimer.singleShot(round(min(60,max(1,args.seconds))*1000),finish)
    return app.exec_()

if __name__=='__main__':sys.exit(main())
