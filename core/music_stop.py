"""Only local stop phrases are recognized while speaker-mode song echo is gated."""
import queue,threading
from PyQt5.QtCore import QObject,pyqtSignal


def is_stop_phrase(text):
    text=''.join(str(text).split())
    return any(word in text for word in ('停止唱歌','停止音乐','别唱了','停歌'))


class MusicStopListener(QObject):
    stop_requested=pyqtSignal()
    def __init__(self,parent=None):
        super().__init__(parent);self.active=False;self.available=False;self.input=None
        self.cancel=threading.Event();self.model=None;self.lock=threading.Lock()

    def feed(self,raw):
        if not self.active or self.input is None:return
        try:self.input.put_nowait(raw)
        except queue.Full:
            try:self.input.get_nowait();self.input.put_nowait(raw)
            except (queue.Empty,queue.Full):pass

    def enable(self,active):
        if active==self.active:return
        self.cancel.set();self.active=bool(active)
        if not active:self.input=None;return
        cancel=self.cancel=threading.Event();audio=self.input=queue.Queue(maxsize=30)
        def listen():
            try:
                import json,vosk
                from core.asr import MODEL_DIR
                with self.lock:
                    if self.model is None:self.model=vosk.Model(MODEL_DIR)
                if cancel.is_set():return
                recognizer=vosk.KaldiRecognizer(self.model,16000);self.available=True
                while not cancel.is_set():
                    try:raw=audio.get(timeout=.2)
                    except queue.Empty:continue
                    complete=recognizer.AcceptWaveform(raw)
                    value=json.loads(recognizer.Result() if complete else recognizer.PartialResult())
                    if is_stop_phrase(value.get('text') or value.get('partial')):
                        if not cancel.is_set():self.stop_requested.emit()
                        break
            except Exception:self.available=False
        threading.Thread(target=listen,daemon=True).start()
