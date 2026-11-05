"""Bounded offline dictation. Edge TTS is used separately for reply playback."""
import threading
from PyQt5.QtCore import QObject,pyqtSignal


class ShortVoice(QObject):
    state=pyqtSignal(str)
    transcript=pyqtSignal(str)
    failed=pyqtSignal(str)
    def __init__(self,parent=None,factory=None):
        super().__init__(parent);self.active=False;self.recorder=None;self.generation=0;self.factory=factory
        self.stop_event=threading.Event()

    def start(self):
        if self.active:return
        self.active=True;self.generation+=1;generation=self.generation
        stop=self.stop_event=threading.Event();self.state.emit('preparing')
        def run():
            try:
                if self.recorder is None:
                    from core.asr import ASRRecorder
                    self.recorder=(self.factory or ASRRecorder)()
                if not self.recorder.available:raise RuntimeError('离线语音识别未就绪，请检查 Vosk 模型和麦克风依赖')
                if stop.is_set():return
                self.recorder.start()
                if self.recorder.error:raise RuntimeError(self.recorder.error)
                if generation==self.generation:self.state.emit('recording')
                stop.wait(30)
                if generation==self.generation:self.state.emit('transcribing')
                text=self.recorder.stop()
                if generation!=self.generation:return
                if self.recorder.error:raise RuntimeError(self.recorder.error)
                if text.strip():self.transcript.emit(text.strip())
                else:self.failed.emit('没有识别到语音，请靠近麦克风再试一次')
            except Exception as exc:
                if generation==self.generation:self.failed.emit(str(exc))
            finally:
                self.active=False
                if generation==self.generation:self.state.emit('idle')
        threading.Thread(target=run,daemon=True).start()

    def stop(self,cancel=False):
        if cancel:self.generation+=1;self.state.emit('idle')
        self.stop_event.set()
